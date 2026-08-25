"""Status indicator widget for the Echo-Node TUI."""

from textual.widgets import Static


class StatusWidget(Static):
    """Connection and state status indicator."""

    def __init__(self, **kwargs):
        super().__init__("○ Disconnected", **kwargs)

    def set_state(self, state: str) -> None:
        """Update the state display."""
        colors = {
            "idle": "white",
            "listening": "green",
            "thinking": "yellow",
            "speaking": "cyan",
            "interrupted": "red",
            "error": "red",
        }
        color = colors.get(state, "white")
        self.update(f"[{color}]● {state}[/{color}]")
