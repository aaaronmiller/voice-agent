import pyperclip
from pathlib import Path
from logger import setup_logger

logger = setup_logger(__name__)

class ClipboardManager:
    def __init__(self, temp_dir=None):
        """Initialize clipboard manager

        Args:
            temp_dir: Directory for temp files
        """
        self.temp_dir = Path(temp_dir) if temp_dir else Path(__file__).parent / "temp_clipboard"
        self.temp_dir.mkdir(exist_ok=True)
        self.temp_file = self.temp_dir / "clipboard_backup.txt"

    def save_clipboard(self):
        """Save current clipboard content to temp file

        Returns:
            Content that was saved
        """
        try:
            content = pyperclip.paste()
            with open(self.temp_file, 'w', encoding='utf-8') as f:
                f.write(content)
            logger.info(f"Clipboard saved ({len(content)} chars)")
            return content
        except Exception as e:
            logger.error(f"Failed to save clipboard: {e}")
            return None

    def restore_clipboard(self):
        """Restore clipboard from temp file

        Returns:
            Restored content
        """
        try:
            if not self.temp_file.exists():
                logger.warning("No clipboard backup found")
                return None

            with open(self.temp_file, 'r', encoding='utf-8') as f:
                content = f.read()

            pyperclip.copy(content)
            logger.info(f"Clipboard restored ({len(content)} chars)")
            return content
        except Exception as e:
            logger.error(f"Failed to restore clipboard: {e}")
            return None

    def set_clipboard(self, text):
        """Set clipboard content

        Args:
            text: Text to set in clipboard

        Returns:
            True if successful
        """
        try:
            pyperclip.copy(text)
            logger.info(f"Clipboard set ({len(text)} chars)")
            return True
        except Exception as e:
            logger.error(f"Failed to set clipboard: {e}")
            return False

    def get_clipboard(self):
        """Get current clipboard content

        Returns:
            Clipboard content
        """
        try:
            return pyperclip.paste()
        except Exception as e:
            logger.error(f"Failed to get clipboard: {e}")
            return None
