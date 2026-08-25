"""Transcript display widget for the Echo-Node TUI."""

from textual.widgets import Static


class TranscriptWidget(Static):
    """Scrollable conversation transcript."""

    def __init__(self, **kwargs):
        super().__init__("", **kwargs)
        self._lines: list[str] = []
        self._max_lines = 200

    def add_line(self, text: str) -> None:
        """Add a line to the transcript."""
        from datetime import datetime
        timestamp = datetime.now().strftime("%H:%M:%S")
        self._lines.append(f"[{timestamp}] {text}")
        if len(self._lines) > self._max_lines:
            self._lines.pop(0)
        self.update("\n".join(self._lines[-50:]))  # Show last 50 lines
