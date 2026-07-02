"""MCP Server: wraps Hermes Agent (localhost:8642) as MCP tools.

This lets ANY MCP client (Gemini via LiveKit, Claude Code, Cursor, etc.)
use Hermes Agent's capabilities — web search, file ops, bash, data analysis.

Architecture:
  MCP Client (in AgentSession) ──stdio──→ hermes_mcp.py ──HTTP──→ Hermes Agent :8642

Usage (standalone, for testing):
  python mcp_servers/hermes.py

The AgentSession connects via stdio automatically when passed as mcp_servers.
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
import time
from typing import Any

from mcp.server import NotificationOptions, Server
from mcp.server.models import InitializationOptions
from mcp.server.stdio import stdio_server
from mcp.types import Tool, TextContent

# ── Config ─────────────────────────────────────────────────────────

HERMES_URL = os.getenv("HERMES_URL", "http://127.0.0.1:8642")
HERMES_API_KEY = os.getenv("HERMES_API_KEY", "pass")
HERMES_TIMEOUT = int(os.getenv("HERMES_TIMEOUT", "30"))

server = Server("hermes-agent")


def _hermes_request(prompt: str, tool_use: str | None = None) -> str:
    """Send a prompt to Hermes Agent API and return the response text.

    Args:
        prompt: The text prompt to send.
        tool_use: Optional tool context hint ("search", "bash", "read", "write").
    """
    import httpx
    
    payload = {
        "messages": [
            {
                "role": "system",
                "content": (
                    "You are a helpful assistant with access to web search, "
                    "file operations, and system commands. Answer concisely. "
                    "Return just the answer — no meta-commentary."
                ),
            },
            {"role": "user", "content": prompt},
        ],
        "max_tokens": 4096,
        "temperature": 0.3,
    }
    
    try:
        resp = httpx.post(
            f"{HERMES_URL}/v1/chat/completions",
            json=payload,
            headers={"Authorization": f"Bearer {HERMES_API_KEY}"},
            timeout=HERMES_TIMEOUT,
        )
        resp.raise_for_status()
        data = resp.json()
        return data["choices"][0]["message"]["content"]
    except httpx.TimeoutException:
        return f"[TIMEOUT] Hermes did not respond within {HERMES_TIMEOUT}s"
    except Exception as e:
        return f"[ERROR] Hermes call failed: {e}"


# ── MCP Tool Definitions ───────────────────────────────────────────

@server.list_tools()
async def list_tools() -> list[Tool]:
    return [
        Tool(
            name="hermes_search_web",
            description="Search the web for current information. Use for news, facts, research.",
            inputSchema={
                "type": "object",
                "properties": {
                    "query": {
                        "type": "string",
                        "description": "Search query (natural language)",
                    },
                },
                "required": ["query"],
            },
        ),
        Tool(
            name="hermes_run_command",
            description="Run a shell command on the host system. Returns stdout/stderr.",
            inputSchema={
                "type": "object",
                "properties": {
                    "command": {
                        "type": "string",
                        "description": "Shell command to execute",
                    },
                    "timeout": {
                        "type": "integer",
                        "description": "Timeout in seconds (default: 30)",
                        "default": 30,
                    },
                },
                "required": ["command"],
            },
        ),
        Tool(
            name="hermes_read_file",
            description="Read the contents of a file. Returns the text content.",
            inputSchema={
                "type": "object",
                "properties": {
                    "path": {
                        "type": "string",
                        "description": "Absolute or relative file path",
                    },
                },
                "required": ["path"],
            },
        ),
        Tool(
            name="hermes_write_file",
            description="Write content to a file. Creates parent directories if needed.",
            inputSchema={
                "type": "object",
                "properties": {
                    "path": {
                        "type": "string",
                        "description": "Absolute or relative file path",
                    },
                    "content": {
                        "type": "string",
                        "description": "Content to write",
                    },
                },
                "required": ["path", "content"],
            },
        ),
        Tool(
            name="hermes_analyze",
            description="Analyze data, answer questions, or perform research using Hermes.",
            inputSchema={
                "type": "object",
                "properties": {
                    "prompt": {
                        "type": "string",
                        "description": "Analysis question or research prompt",
                    },
                },
                "required": ["prompt"],
            },
        ),
        Tool(
            name="hermes_schedule_cron",
            description="Schedule a command or task via cron. Creates a one-shot or recurring job.",
            inputSchema={
                "type": "object",
                "properties": {
                    "command": {
                        "type": "string",
                        "description": "Command to run",
                    },
                    "schedule": {
                        "type": "string",
                        "description": "Cron expression (e.g., '0 9 * * 1' for Monday 9am) or 'now' for immediate",
                        "default": "now",
                    },
                    "description": {
                        "type": "string",
                        "description": "Human-readable description of the task",
                        "default": "",
                    },
                },
                "required": ["command"],
            },
        ),
    ]


@server.call_tool()
async def call_tool(name: str, arguments: dict[str, Any]) -> list[TextContent]:
    if name == "hermes_search_web":
        result = _hermes_request(f"Search the web for: {arguments['query']}", tool_use="search")
        return [TextContent(type="text", text=result)]

    elif name == "hermes_run_command":
        cmd = arguments["command"]
        timeout = arguments.get("timeout", 30)
        # Try direct execution first (faster), fall back to Hermes for complex commands
        try:
            result = subprocess.run(
                cmd, shell=True, capture_output=True, text=True, timeout=timeout,
            )
            output = result.stdout or result.stderr or "(no output)"
            return [TextContent(type="text", text=output[:4000])]
        except subprocess.TimeoutExpired:
            return [TextContent(type="text", text=f"[TIMEOUT] Command exceeded {timeout}s")]
        except Exception as e:
            return [TextContent(type="text", text=f"[ERROR] {e}")]

    elif name == "hermes_read_file":
        path = arguments["path"]
        try:
            with open(path) as f:
                content = f.read()
            return [TextContent(type="text", text=content[:8000])]
        except Exception as e:
            return [TextContent(type="text", text=f"[ERROR] Cannot read {path}: {e}")]

    elif name == "hermes_write_file":
        path = arguments["path"]
        content = arguments["content"]
        try:
            os.makedirs(os.path.dirname(os.path.abspath(path)), exist_ok=True)
            with open(path, "w") as f:
                f.write(content)
            return [TextContent(type="text", text=f"✅ Written {len(content)} bytes to {path}")]
        except Exception as e:
            return [TextContent(type="text", text=f"[ERROR] Cannot write {path}: {e}")]

    elif name == "hermes_analyze":
        result = _hermes_request(arguments["prompt"], tool_use="analyze")
        return [TextContent(type="text", text=result)]

    elif name == "hermes_schedule_cron":
        cmd = arguments["command"]
        schedule = arguments.get("schedule", "now")
        desc = arguments.get("description", "")
        
        if schedule == "now":
            # Run immediately in background
            subprocess.Popen(cmd, shell=True)
            return [TextContent(type="text", text=f"✅ Started: {cmd}")]
        else:
            # Schedule via crontab
            cron_line = f"{schedule} cd {os.getcwd()} && {cmd} >> /tmp/hermes-cron.log 2>&1"
            try:
                # Check if line already exists
                existing = subprocess.run(
                    "crontab -l", shell=True, capture_output=True, text=True,
                ).stdout
                if cron_line not in existing:
                    new_cron = existing.strip() + "\n" + cron_line + "\n"
                    proc = subprocess.run(
                        "crontab", input=new_cron, capture_output=True, text=True, shell=True,
                    )
                    if proc.returncode == 0:
                        return [TextContent(type="text", text=f"✅ Scheduled: `{cron_line}`")]
                    else:
                        return [TextContent(type="text", text=f"[ERROR] crontab: {proc.stderr}")]
                return [TextContent(type="text", text="Already scheduled")]
            except Exception as e:
                return [TextContent(type="text", text=f"[ERROR] {e}")]

    return [TextContent(type="text", text=f"Unknown tool: {name}")]


# ── Main ───────────────────────────────────────────────────────────

async def main():
    async with stdio_server() as (read_stream, write_stream):
        await server.run(
            read_stream,
            write_stream,
            InitializationOptions(
                server_name="hermes-agent",
                server_version="1.0.0",
                capabilities=server.get_capabilities(
                    notification_options=NotificationOptions(),
                    experimental_capabilities={},
                ),
            ),
        )

if __name__ == "__main__":
    import asyncio
    asyncio.run(main())
