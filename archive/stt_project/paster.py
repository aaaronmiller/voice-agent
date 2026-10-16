import pyautogui
import time
from logger import setup_logger

logger = setup_logger(__name__)

class Paster:
    def __init__(self, paste_delay=0.1):
        """Initialize paster

        Args:
            paste_delay: Delay before paste in seconds (for reliability)
        """
        self.paste_delay = paste_delay
        # Disable pyautogui failsafe (moving mouse to corner won't stop script)
        pyautogui.FAILSAFE = False

    def paste_at_cursor(self):
        """Paste clipboard content at current cursor location

        Returns:
            True if successful
        """
        try:
            logger.info("Waiting for focus...")
            time.sleep(self.paste_delay)

            logger.info("Pasting at cursor...")
            pyautogui.hotkey('ctrl', 'v')
            logger.info("Paste completed")
            return True
        except Exception as e:
            logger.error(f"Failed to paste: {e}")
            return False

    def type_text(self, text):
        """Type text character by character (alternative to paste)

        Args:
            text: Text to type

        Returns:
            True if successful
        """
        try:
            logger.info(f"Typing {len(text)} characters...")
            pyautogui.typewrite(text, interval=0.01)
            logger.info("Typing completed")
            return True
        except Exception as e:
            logger.error(f"Failed to type: {e}")
            return False
