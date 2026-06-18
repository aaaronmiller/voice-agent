"""
Unified Agent Interface — any model, any harness, any voice frontend.

Every agent implements the same text-in/text-out contract.
The SmartRouter classifies queries and dispatches to the right brain.
"""

from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable
from urllib.request import Request, urlopen


# ── Cost Tracker ────────────────────────────────────────────────────
@dataclass
class CostTracker:
    session_usd: float = 0.0
    call_usd: float = 0.0
    prompt_tokens: int = 0
    completion_tokens: int = 0
    start_time: float = field(default_factory=time.time)

    def add(self, pt: int, ct: int, prompt_price: float, completion_price: float) -> float:
        cost = (pt * prompt_price + ct * completion_price) / 1_000_000
        self.session_usd += cost
        self.call_usd = cost
        self.prompt_tokens = pt
        self.completion_tokens = ct
        return cost

    def add_dollar(self, usd: float) -> None:
        self.session_usd += usd
        self.call_usd = usd

    @property
    def rate_per_hour(self) -> float:
        elapsed = (time.time() - self.start_time) / 3600
        return self.session_usd / elapsed if elapsed > 0 else 0

    def reset(self) -> None:
        self.session_usd = 0.0
        self.call_usd = 0.0
        self.prompt_tokens = 0
        self.completion_tokens = 0
        self.start_time = time.time()


# ── Agent Result ────────────────────────────────────────────────────
@dataclass
class AgentResult:
    text: str
    elapsed: float
    cost: CostTracker
    agent: str
    model: str
    success: bool = True


# ── Base Agent Interface ────────────────────────────────────────────
class Agent:
    """All agents implement this interface. text_in -> text_out."""

    name: str = "base"
    model_name: str = ""
    cost_per_hour: str = "$0.00"
    supports_tools: bool = False
    supports_sessions: bool = False
    description: str = ""

    def respond(self, text: str, system: str = "", cost: CostTracker | None = None) -> AgentResult:
        raise NotImplementedError

    def get_capabilities(self) -> list[str]:
        return []


# ── HTTP Agent (OpenAI-compatible API) ──────────────────────────────
class HTTPAgent(Agent):
    """Generic agent for any OpenAI-compatible HTTP API."""

    def __init__(self, name: str, model: str, base_url: str, api_key: str,
                 prompt_price: float = 0, completion_price: float = 0,
                 cost_per_hour: str = "$0.00", description: str = "",
                 supports_tools: bool = False, supports_sessions: bool = False):
        self.name = name
        self.model_name = model
        self.base_url = base_url.rstrip("/")
        self.api_key = api_key
        self.prompt_price = prompt_price
        self.completion_price = completion_price
        self.cost_per_hour = cost_per_hour
        self.description = description
        self.supports_tools = supports_tools
        self.supports_sessions = supports_sessions

    def respond(self, text: str, system: str = "", cost: CostTracker | None = None) -> AgentResult:
        headers = {
            "Content-Type": "application/json",
            "Authorization": f"Bearer {self.api_key}",
        }
        messages = []
        if system:
            messages.append({"role": "system", "content": system})
        messages.append({"role": "user", "content": text})

        body = json.dumps({
            "model": self.model_name,
            "messages": messages,
            "max_tokens": 200,
            "stream": False,
        }).encode()

        t0 = time.perf_counter()
        try:
            req = Request(f"{self.base_url}/chat/completions", data=body, headers=headers, method="POST")
            resp = urlopen(req, timeout=120)
            data = json.loads(resp.read())
            elapsed = time.perf_counter() - t0

            content = data.get("choices", [{}])[0].get("message", {}).get("content", "")
            usage = data.get("usage", {})
            pt = usage.get("prompt_tokens", 0)
            ct = usage.get("completion_tokens", 0)

            ct_obj = cost or CostTracker()
            upstream = usage.get("cost_details", {}).get("upstream_inference_cost", 0)
            if upstream:
                ct_obj.add_dollar(upstream)
            elif self.prompt_price > 0:
                ct_obj.add(pt, ct, self.prompt_price, self.completion_price)

            return AgentResult(content, elapsed, ct_obj, self.name, self.model_name)

        except Exception as e:
            elapsed = time.perf_counter() - t0
            err = str(e)
            if hasattr(e, 'read'):
                try:
                    err += " | " + e.read().decode()[:200]
                except Exception:
                    pass
            return AgentResult(f"ERROR: {err}", elapsed, cost or CostTracker(), self.name, self.model_name, success=False)

    def get_capabilities(self) -> list[str]:
        caps = ["Text in/out via HTTP", f"Model: {self.model_name}"]
        if self.supports_tools:
            caps.append("Tool calling")
        if self.supports_sessions:
            caps.append("Session persistence")
        return caps


# ── CLI Agent (subprocess) ──────────────────────────────────────────
class CLIAgent(Agent):
    """Agent that runs as a CLI subprocess (Claude, Pi, Codex, etc.)."""

    def __init__(self, name: str, command: list[str], timeout: int = 60,
                 cost_per_hour: str = "$0.00", description: str = "",
                 supports_tools: bool = True, supports_sessions: bool = True):
        self.name = name
        self.command = command
        self.timeout = timeout
        self.cost_per_hour = cost_per_hour
        self.description = description
        self.supports_tools = supports_tools
        self.supports_sessions = supports_sessions
        self.model_name = command[0]

    def respond(self, text: str, system: str = "", cost: CostTracker | None = None) -> AgentResult:
        cmd = self.command + ["-p", text]
        t0 = time.perf_counter()
        try:
            result = subprocess.run(
                cmd, capture_output=True, text=True,
                timeout=self.timeout, env=os.environ.copy()
            )
            elapsed = time.perf_counter() - t0
            output = result.stdout.strip() or result.stderr.strip() or "(no output)"
            return AgentResult(output, elapsed, cost or CostTracker(), self.name, self.model_name)
        except subprocess.TimeoutExpired:
            elapsed = time.perf_counter() - t0
            return AgentResult(f"TIMEOUT after {self.timeout}s", elapsed, cost or CostTracker(),
                               self.name, self.model_name, success=False)
        except Exception as e:
            elapsed = time.perf_counter() - t0
            return AgentResult(f"ERROR: {e}", elapsed, cost or CostTracker(),
                               self.name, self.model_name, success=False)

    def get_capabilities(self) -> list[str]:
        caps = [f"CLI: {' '.join(self.command[:2])}", "Full tool access"]
        if self.supports_sessions:
            caps.append("Persistent tmux sessions")
        return caps


# ── Agent Profiles ──────────────────────────────────────────────────
def get_all_agents() -> dict[str, Agent]:
    """Return all configured agents keyed by short name."""
    OR_KEY = os.environ.get("OPENROUTER_API_KEY", "")  # injected at runtime
    OC_KEY = os.environ.get("OPENAI_API_KEY", "")  # injected at runtime

    return {
        "fast": HTTPAgent(
            name="🚀 Fast Free",
            model="nex-agi/nex-n2-pro:free",
            base_url="https://openrouter.ai/api/v1",
            api_key=OR_KEY,
            cost_per_hour="$0.00 (free)",
            description="0.7s responses via OpenRouter free tier",
        ),
        "hermes": HTTPAgent(
            name="🛠️ Hermes Agent",
            model="hermes-agent",
            base_url="http://127.0.0.1:8642/v1",
            api_key="pass",
            cost_per_hour="$0.00 (OC Zen free)",
            description="Full Hermes agent with tool calling",
            supports_tools=True,
            supports_sessions=True,
        ),
        "nemotron": HTTPAgent(
            name="🧠 Nemotron Ultra",
            model="nemotron-3-ultra-free",
            base_url="https://opencode.ai/zen/v1",
            api_key=OC_KEY,
            cost_per_hour="$0.00 (free)",
            description="550B model on OpenCode Zen, free tier",
        ),
        "gpt-audio-mini": HTTPAgent(
            name="🎤 GPT Audio Mini",
            model="openai/gpt-audio-mini",
            base_url="https://openrouter.ai/api/v1",
            api_key=OR_KEY,
            prompt_price=0.60,
            completion_price=2.40,
            cost_per_hour="~$0.14/hr",
            description="Native audio I/O, single API call",
        ),
        "gpt-audio": HTTPAgent(
            name="🎧 GPT Audio",
            model="openai/gpt-audio",
            base_url="https://openrouter.ai/api/v1",
            api_key=OR_KEY,
            prompt_price=2.50,
            completion_price=10.00,
            cost_per_hour="~$0.56/hr",
            description="Best quality audio I/O",
        ),
        "claude": CLIAgent(
            name="🤖 Claude Code",
            command=["xx", "cip"],
            cost_per_hour="$0.00 (via free OR)",
            description="Anthropic Claude via Clutch Gateway, full coding agent",
        ),
        "pi": CLIAgent(
            name="🧩 Pi Agent",
            command=["xx", "pip"],
            cost_per_hour="$0.00 (via free OR)",
            description="Pi coding assistant via Clutch Gateway",
        ),
        "codex": CLIAgent(
            name="📝 Codex",
            command=["xx", "xip"],
            cost_per_hour="$0.00 (via free OR)",
            description="OpenAI Codex via Clutch Gateway",
        ),
    }


# ── Smart Router ────────────────────────────────────────────────────
class SmartRouter:
    """Classifies queries and routes to the appropriate agent."""

    def __init__(self, agents: dict[str, Agent], default: str = "fast"):
        self.agents = agents
        self.default = default
        self.last_agent: str | None = None
        self.cost = CostTracker()

    def classify(self, text: str) -> str:
        """Determine which agent should handle this query."""
        lower = text.lower()

        # Check for complex reasoning FIRST (trumps length)
        complex_keywords = ["explain", "compare", "analyze", "why does", "how does",
                            "summarize", "difference between", "pros and cons",
                            "what is the", "tell me about"]
        if any(kw in lower for kw in complex_keywords):
            return "nemotron"

        # Tool-heavy → Hermes (needs web/API access)
        tool_keywords = ["search", "web", "find", "look up", "browse", "scrape",
                         "email", "send", "message", "slack", "discord",
                         "download", "upload", "api", "curl"]
        if any(kw in lower for kw in tool_keywords):
            return "hermes"

        # Coding tasks → Claude/Codex
        code_keywords = ["code", "debug", "refactor", "function", "class",
                         "git", "commit", "push", "pull", "merge",
                         "bash", "terminal", "npm", "pip", "install",
                         "write a", "create a file", "edit", "fix bug"]
        if any(kw in lower for kw in code_keywords):
            return "claude"

        # Very short queries → fast model
        if len(text.split()) <= 5:
            return "fast"

        return self.default

    def route(self, text: str, system: str = "") -> AgentResult:
        """Classify and route to the best agent."""
        agent_key = self.classify(text)
        agent = self.agents.get(agent_key)
        if not agent:
            agent_key = self.default
            agent = self.agents.get(self.default)
        if not agent:
            return AgentResult("No agent available", 0, self.cost, "none", "none", success=False)

        self.last_agent = agent_key
        return agent.respond(text, system, self.cost)

    def print_status(self) -> str:
        return (
            f"Router: {self.last_agent or 'idle'} | "
            f"Session: ${self.cost.session_usd:.4f} | "
            f"Rate: ${self.cost.rate_per_hour:.2f}/hr"
        )


# ── Agent Table ─────────────────────────────────────────────────────
def print_agent_table():
    """Print all agents in a formatted table."""
    agents = get_all_agents()
    print(f"\n{'Key':<8s} {'Agent':<22s} {'Cost/hr':<18s} {'Tools':<8s} {'Sessions':<10s} {'Description'}")
    print(f"{'-'*100}")
    for key, agent in sorted(agents.items()):
        print(f"{key:<8s} {agent.name:<22s} {agent.cost_per_hour:<18s} "
              f"{'✅' if agent.supports_tools else '❌':<8s} "
              f"{'✅' if agent.supports_sessions else '❌':<10s} "
              f"{agent.description[:35]}")
    print()
