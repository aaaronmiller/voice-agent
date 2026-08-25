#!/usr/bin/env python3
"""
Echo-Node Live Monitoring Dashboard — Terminal UI.

CLI-first observability dashboard that connects to the gateway
via WebSocket and displays real-time latency metrics.

Usage:
  python -m echo_monitor              # Connect to local gateway
  python -m echo_monitor --url ws://localhost:3000/ws  # Custom URL
  python -m echo_monitor --history    # Replay last session from JSONL
"""

from __future__ import annotations

import argparse
import asyncio
import json
import os
import sys
import time
from pathlib import Path
from typing import Any

try:
    from rich.console import Console
    from rich.layout import Layout
    from rich.panel import Panel
    from rich.live import Live
    from rich.table import Table
    from rich.text import Text
    from rich import box
    RICH_AVAILABLE = True
except ImportError:
    RICH_AVAILABLE = False
    Console = None


class MetricsCollector:
    """Collects and aggregates latency and cost metrics from the gateway."""

    def __init__(self, window: int = 100):
        self.turns: list[dict[str, Any]] = []
        self.window = window
        self.start_time = time.time()
        self.total_cost: float = 0.0

    def add_turn(self, metrics: dict[str, Any]) -> None:
        self.turns.append(metrics)
        cost = metrics.get("costUsd", 0) or 0
        self.total_cost += cost
        if len(self.turns) > self.window:
            popped = self.turns.pop(0)
            popped_cost = popped.get("costUsd", 0) or 0
            self.total_cost -= popped_cost

    @property
    def total_turns(self) -> int:
        return len(self.turns)

    @property
    def session_duration(self) -> float:
        return time.time() - self.start_time

    @property
    def turns_per_minute(self) -> float:
        mins = self.session_duration / 60
        return self.total_turns / mins if mins > 0 else 0

    def average(self, key: str) -> float:
        vals = [t.get(key, 0) for t in self.turns if t.get(key, 0) > 0]
        return sum(vals) / len(vals) if vals else 0

    def percentile(self, key: str, p: int) -> float:
        vals = sorted([t.get(key, 0) for t in self.turns if t.get(key, 0) > 0])
        if not vals:
            return 0
        idx = max(0, min(len(vals) - 1, int(len(vals) * p / 100)))
        return vals[idx]

    def min_val(self, key: str) -> float:
        vals = [t.get(key, 0) for t in self.turns if t.get(key, 0) > 0]
        return min(vals) if vals else 0

    def max_val(self, key: str) -> float:
        vals = [t.get(key, 0) for t in self.turns if t.get(key, 0) > 0]
        return max(vals) if vals else 0

    def by_provider(self) -> dict[str, list[dict[str, Any]]]:
        result: dict[str, list[dict[str, Any]]] = {}
        for t in self.turns:
            provider = t.get("provider", "unknown")
            result.setdefault(provider, []).append(t)
        return result

    def provider_stats(self) -> list[dict[str, Any]]:
        stats = []
        for provider, turns in self.by_provider().items():
            ears = [t.get("earsToMouth", 0) for t in turns if t.get("earsToMouth", 0) > 0]
            cost = sum(t.get("costUsd", 0) or 0 for t in turns)
            stats.append({
                "provider": provider,
                "turns": len(turns),
                "avg_ears_to_mouth": sum(ears) / len(ears) if ears else 0,
                "cost": cost,
                "interrupts": sum(1 for t in turns if t.get("interrupted")),
                "errors": sum(1 for t in turns if t.get("error")),
            })
        return sorted(stats, key=lambda s: s["turns"], reverse=True)


class RichDashboard:
    """Terminal dashboard using Rich library."""

    def __init__(self, collector: MetricsCollector):
        self.collector = collector
        self.console = Console()
        self.layout = Layout()
        self.layout.split(
            Layout(name="header", size=3),
            Layout(name="body"),
            Layout(name="footer", size=3),
        )
        self.layout["body"].split_row(
            Layout(name="metrics", ratio=2),
            Layout(name="providers", ratio=1),
        )

    def render(self) -> Layout:
        c = self.collector

        # Header
        header_text = Text()
        header_text.append(" Echo-Node Live Metrics ", style="bold cyan")
        header_text.append(f"  •  {c.total_turns} turns", style="white")
        header_text.append(f"  •  {c.session_duration:.0f}s elapsed", style="white")
        if c.total_turns > 0:
            header_text.append(f"  •  {c.turns_per_minute:.1f} turns/min", style="white")
        self.layout["header"].update(Panel(header_text, box=box.HEAVY))

        # Metrics panel
        metrics_table = Table(show_header=False, box=box.SIMPLE, padding=(0, 2))
        metrics_table.add_column("Metric", style="cyan")
        metrics_table.add_column("Current", style="yellow")
        metrics_table.add_column("Avg", style="green")
        metrics_table.add_column("p50", style="white")
        metrics_table.add_column("p95", style="red")
        metrics_table.add_column("p99", style="red")
        metrics_table.add_column("Min", style="dim")
        metrics_table.add_column("Max", style="bold")

        for key, label in [
            ("earsToMouth", "Ears→Mouth"),
            ("llmFirstToken", "First Token"),
            ("totalLatency", "Total"),
        ]:
            latest = c.turns[-1].get(key, 0) if c.turns else 0
            metrics_table.add_row(
                label,
                f"{latest:.0f}ms" if c.turns else "—",
                f"{c.average(key):.0f}ms",
                f"{c.percentile(key, 50):.0f}ms",
                f"{c.percentile(key, 95):.0f}ms",
                f"{c.percentile(key, 99):.0f}ms",
                f"{c.min_val(key):.0f}ms",
                f"{c.max_val(key):.0f}ms",
            )

        # Add latency health indicator
        if c.turns:
            latest_etm = c.turns[-1].get("earsToMouth", 0)
            if latest_etm < 500:
                health = "🟢 Excellent"
            elif latest_etm < 1000:
                health = "🟡 Good"
            elif latest_etm < 2000:
                health = "🟠 Fair"
            else:
                health = "🔴 Poor"
            metrics_table.add_row("Health", health, "", "", "", "", "", "")

        # Cost row
        if c.total_cost > 0:
            latest_cost = c.turns[-1].get("costUsd", 0) if c.turns else 0
            pricing = c.turns[-1].get("pricingLabel", "") if c.turns else ""
            cost_str = f"${latest_cost:.4f}" if latest_cost >= 0.001 else "< $0.001"
            total_cost_str = f"${c.total_cost:.4f}" if c.total_cost >= 0.001 else "< $0.001"
            metrics_table.add_row(
                f"Cost ({pricing})" if pricing else "Cost",
                cost_str,
                total_cost_str,
                "", "", "", "", ""
            )

        self.layout["metrics"].update(Panel(
            metrics_table,
            title="Latency Metrics (ms)",
            box=box.ROUNDED,
        ))

        # Providers panel
        providers_table = Table(show_header=True, box=box.SIMPLE, padding=(0, 2))
        providers_table.add_column("Provider", style="cyan")
        providers_table.add_column("Turns", style="white", justify="right")
        providers_table.add_column("Avg E→M", style="green", justify="right")
        providers_table.add_column("Cost", style="yellow", justify="right")
        providers_table.add_column("Interrupts", style="yellow", justify="right")
        providers_table.add_column("Errors", style="red", justify="right")

        for ps in c.provider_stats():
            avg_cost = ps.get("cost", 0) / max(ps["turns"], 1)
            cost_col = f"${ps.get('cost', 0):.4f}" if ps.get('cost', 0) >= 0.001 else "—"
            providers_table.add_row(
                ps["provider"],
                str(ps["turns"]),
                f"{ps['avg_ears_to_mouth']:.0f}ms",
                cost_col,
                str(ps["interrupts"]),
                str(ps["errors"]),
            )

        self.layout["providers"].update(Panel(
            providers_table,
            title="Per-Provider",
            box=box.ROUNDED,
        ))

        # Footer
        status = "● Connected" if c.turns else "○ Waiting for data..."
        self.layout["footer"].update(Panel(
            f" {status}  |  Turn #{c.total_turns + 1}  |  Ctrl+C to quit",
            box=box.HEAVY,
        ))

        return self.layout


async def connect_to_gateway(url: str) -> None:
    """Connect to the gateway WebSocket and display live metrics."""
    import websockets

    collector = MetricsCollector()
    dashboard = RichDashboard(collector)

    print(f" Connecting to {url}...")

    async with websockets.connect(url) as ws:
        print(" Connected! Waiting for metrics...\n")

        with Live(dashboard.render(), console=dashboard.console, refresh_per_second=4) as live:
            async for message in ws:
                try:
                    data = json.loads(message)
                    if data.get("type") == "latency":
                        collector.add_turn(data.get("metrics", data))
                    elif data.get("type") == "latency_snapshot":
                        # Update with snapshot data
                        snapshot = data.get("snapshot", {})
                        # Could add per-provider breakdowns from snapshot
                        pass
                except json.JSONDecodeError:
                    pass

                live.update(dashboard.render())


def replay_history(log_dir: str = "logs") -> None:
    """Replay metrics from existing JSONL log files."""
    import glob

    collector = MetricsCollector()
    dashboard = RichDashboard(collector)

    log_path = Path(log_dir)
    log_files = sorted(log_path.glob("session_*.jsonl"))

    if not log_files:
        print(f"No session logs found in {log_dir}/")
        return

    latest = log_files[-1]
    print(f" Replaying: {latest.name}")

    with open(latest) as f:
        for line in f:
            record = json.loads(line)
            # Map ConversationLogger format to metrics format
            latencies = record.get("latencies_s", {})
            if latencies:
                metric = {
                    "earsToMouth": latencies.get("ears_to_mouth", 0) * 1000,
                    "llmFirstToken": latencies.get("llm_first_token", 0) * 1000,
                    "totalLatency": latencies.get("turn_total", 0) * 1000,
                    "provider": record.get("route", record.get("llm_model", "unknown")),
                    "interrupted": record.get("interrupted", False),
                    "error": record.get("error", ""),
                }
                collector.add_turn(metric)

    with Live(dashboard.render(), console=dashboard.console, refresh_per_second=4) as live:
        import time as _time
        for _ in range(10):  # Show for 10 seconds
            live.update(dashboard.render())
            _time.sleep(1)


def main():
    parser = argparse.ArgumentParser(description="Echo-Node Monitoring Dashboard")
    parser.add_argument("--url", default=os.environ.get("ECHO_GATEWAY_URL", "ws://127.0.0.1:3000/ws"),
                        help="Gateway WebSocket URL")
    parser.add_argument("--history", action="store_true",
                        help="Replay last session from JSONL logs")
    parser.add_argument("--log-dir", default=os.path.join(os.path.dirname(__file__), "..", "..", "v2", "logs"),
                        help="Log directory for --history mode")

    args = parser.parse_args()

    if not RICH_AVAILABLE:
        print("Error: 'rich' library required. Install: pip install rich", file=sys.stderr)
        sys.exit(1)

    if args.history:
        replay_history(args.log_dir)
    else:
        asyncio.run(connect_to_gateway(args.url))


if __name__ == "__main__":
    main()
