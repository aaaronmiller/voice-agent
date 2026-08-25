"""Latency display widget for the Echo-Node TUI."""

from textual.widgets import Static
from typing import Any


class LatencyWidget(Static):
    """Live latency + cost metrics display."""

    def __init__(self, **kwargs):
        super().__init__("", **kwargs)
        self._metrics: dict[str, Any] = {}
        self._history: list[float] = []

    def update_metrics(self, metrics: dict[str, Any]) -> None:
        """Update with new metrics."""
        self._metrics = metrics
        etm = metrics.get("earsToMouth", 0)
        if etm:
            self._history.append(etm)
            if len(self._history) > 100:
                self._history.pop(0)

        self._render()

    def _render(self) -> None:
        """Render the metrics + cost display."""
        m = self._metrics
        etm = m.get("earsToMouth", 0)
        first_token = m.get("llmFirstToken", 0)
        total = m.get("totalLatency", 0)
        provider = m.get("provider", "—")
        cost_usd = m.get("costUsd", None)
        cumulative = m.get("cumulativeUsd", None)
        pricing_label = m.get("pricingLabel", "")

        # Color code based on latency
        etm_color = "green" if etm < 500 else ("yellow" if etm < 1000 else "red")

        lines = [
            f"Provider: [bold]{provider}[/bold]  ({pricing_label})",
            f"Ears→Mouth: [{etm_color}]{etm:.0f}ms[/{etm_color}]  "
            f"First Token: {first_token:.0f}ms  "
            f"Total: {total:.0f}ms",
        ]

        if cost_usd is not None:
            cost_str = f"${cost_usd:.4f}" if cost_usd >= 0.001 else "< $0.001"
            cumul_str = f"${cumulative:.4f}" if cumulative and cumulative >= 0.001 else "< $0.001"
            lines.append(f"Cost: [bold yellow]{cost_str}[/bold yellow] this turn  "
                         f"[bold yellow]{cumul_str}[/bold yellow] session total")

        if self._history:
            avg = sum(self._history) / len(self._history)
            p95 = sorted(self._history)[int(len(self._history) * 0.95)]
            lines.append(f"Rolling avg: {avg:.0f}ms  p95: {p95:.0f}ms  Turns: {len(self._history)}")

        self.update("\n".join(lines))
