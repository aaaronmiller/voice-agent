#!/usr/bin/env python3
"""
Voice Agent Configuration Wizard — powered by echo_node.agent_profiles.

Test any LLM/STT/TTS combination with live cost tracking.
All routes can delegate complex tasks to Hermes for agent capabilities.
"""

from __future__ import annotations

import os
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from echo_node.agent_profiles import get_all_agents, SmartRouter, CostTracker

# ── Terminal colors ─────────────────────────────────────────────────
_RESET = "\033[0m"
_BOLD = "\033[1m"
_DIM = "\033[2m"
_RED = "\033[91m"
_GREEN = "\033[92m"
_YELLOW = "\033[93m"
_CYAN = "\033[96m"
_MAGENTA = "\033[95m"


def c(text: str, color: str) -> str:
    return f"{color}{text}{_RESET}"


def bold(text: str) -> str:
    return f"{_BOLD}{text}{_RESET}"


# ── TTS test ────────────────────────────────────────────────────────
def test_tts(text: str) -> str:
    """Quick dots.tts benchmark."""
    try:
        from tts_dots import DotsTTS
        import tempfile
        tts = DotsTTS({"model_path": "models/dots-tts-mf", "num_steps": 4, "guidance_scale": 1.2})
        fd, path = tempfile.mkstemp(suffix=".wav")
        os.close(fd)
        t0 = time.perf_counter()
        tts.synthesize_to_wav(text, Path(path))
        elapsed = time.perf_counter() - t0
        size = os.path.getsize(path)
        os.unlink(path)
        tts.close()
        return f"{c('TTS:', _CYAN)} {elapsed:.2f}s → {size/1024:.0f}KB @ 48kHz"
    except Exception as e:
        return f"{c('TTS:', _YELLOW)} skip ({e})"


# ── Wizard ──────────────────────────────────────────────────────────
def main():
    agents = get_all_agents()
    agent_list = list(agents.items())
    cost_tracker = CostTracker()
    router = SmartRouter(agents)

    while True:
        os.system("clear")
        print(f"\n{c('╔══════════════════════════════════════════════════════════╗', _CYAN)}")
        print(f"{c('║', _CYAN)}        {c('VOICE AGENT WIZARD', _BOLD+_MAGENTA)}                          {c('║', _CYAN)}")
        print(f"{c('╚══════════════════════════════════════════════════════════╝', _CYAN)}")
        print()

        # Agent table
        print(f"  {c('ID', _BOLD+_CYAN):<5s} {c('Agent', _BOLD+_CYAN):<24s} {c('Model', _BOLD+_CYAN):<32s} {c('Cost/hr', _BOLD+_CYAN)}")
        print(f"  {c('─'*85, _DIM)}")
        for i, (key, agent) in enumerate(agent_list, 1):
            print(f"  {c(f'{i}.', _GREEN):<5s} {c(agent.name, _BOLD):<24s} {agent.model_name:<32s} {c(agent.cost_per_hour, _YELLOW)}")

        print(f"\n  {c('R.', _GREEN)} Smart Router (classify & route automatically)")
        print(f"  {c('T.', _GREEN)} Test Smart Router classification")
        print(f"  {c('A.', _GREEN)} Test {c('ALL', _BOLD)} agents sequentially")
        print(f"  {c('0.', _GREEN)} Exit")
        print(f"\n  {c(f'Session cost: ${cost_tracker.session_usd:.4f} | Rate: ${cost_tracker.rate_per_hour:.2f}/hr', _YELLOW)}")
        print()

        choice = input(f"{c('Pick', _CYAN)}> ").strip().lower()

        if choice == "0":
            print(f"\n{c('Bye!', _GREEN)} Total spent: ${cost_tracker.session_usd:.4f}")
            break

        elif choice == "r":
            # Test smart router
            os.system("clear")
            print(f"\n{bold('Smart Router — query classification test')}\n")
            while True:
                q = input(f"{c('Query', _CYAN)}> ").strip()
                if not q:
                    break
                route = router.classify(q)
                agent = agents.get(route)
                print(f"  → {c(route, _GREEN)} ({agent.name if agent else '?'})")
                print()

        elif choice == "t":
            # Test routing with actual API calls
            route = router.classify("What is the capital of France?")
            agent = agents.get(route)
            os.system("clear")
            print(f"\n{bold('Smart Router Test')}\n")
            print(f"  Query: {c('What is the capital of France?', _BOLD)}")
            print(f"  Routed to: {c(route, _GREEN)} ({agent.name})")
            result = agent.respond("What is the capital of France? Reply in one word.",
                                   "You are a concise assistant.", cost_tracker)
            print(f"  Response: {c(result.text[:80], _BOLD)}")
            print(f"  Latency: {result.elapsed:.2f}s")
            print(f"  Cost: ${result.cost.call_usd:.4f}")
            print(f"\n{c('Session:', _YELLOW)} ${cost_tracker.session_usd:.4f} | ${cost_tracker.rate_per_hour:.2f}/hr")
            input(f"\n{c('Enter to continue', _DIM)}")

        elif choice == "a":
            os.system("clear")
            for key, agent in agent_list:
                print(f"\n{c('▶', _GREEN)} Testing {c(agent.name, _BOLD)} ({agent.model_name})")
                result = agent.respond("What is the capital of France? Reply in one word.",
                                       "You are a concise assistant.", cost_tracker)
                print(f"  Response: {c(result.text[:60], _BOLD)}")
                print(f"  Latency: {result.elapsed:.2f}s  Cost: ${result.cost.call_usd:.4f}")
                print(f"  {test_tts(result.text[:60])}")
            print(f"\n{c('Session total: ${:.4f}'.format(cost_tracker.session_usd), _YELLOW)}")
            input(f"\n{c('Enter to continue', _DIM)}")

        elif choice.isdigit():
            idx = int(choice) - 1
            if 0 <= idx < len(agent_list):
                key, agent = agent_list[idx]
                os.system("clear")
                print(f"\n{c('▶', _GREEN)} {c(agent.name, _BOLD)} ({agent.model_name})")
                print(f"  {c('Cost:', _YELLOW)} {agent.cost_per_hour}")
                print(f"  {c('Tools:', _CYAN)} {'✅' if agent.supports_tools else '❌'}  {c('Sessions:', _CYAN)} {'✅' if agent.supports_sessions else '❌'}")
                print()

                prompt = input(f"{c('Query', _CYAN)}> ").strip() or "What is 2+2? Reply in one word."
                result = agent.respond(prompt, "You are a concise assistant.", cost_tracker)

                print(f"\n{c('Response:', _GREEN)} {c(result.text[:120], _BOLD)}")
                print(f"  {c('Time:', _CYAN)} {result.elapsed:.2f}s")
                print(f"  {c('Cost:', _YELLOW)} ${result.cost.call_usd:.4f} call | ${cost_tracker.session_usd:.4f} session | ${cost_tracker.rate_per_hour:.2f}/hr")
                if result.text:
                    print(f"  {test_tts(result.text[:80])}")
                print()
                input(f"{c('Enter to continue', _DIM)}")


if __name__ == "__main__":
    main()
