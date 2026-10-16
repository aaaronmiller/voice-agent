import keyboard
import threading
from logger import setup_logger

logger = setup_logger(__name__)

class HotkeyListener:
    def __init__(self):
        """Initialize hotkey listener"""
        self.registered_hotkeys = {}
        self.running = False

    def register(self, hotkey, callback, description=""):
        """Register a global hotkey

        Args:
            hotkey: Hotkey string (e.g., "ctrl+shift+a")
            callback: Function to call when hotkey is pressed
            description: Optional description of the hotkey

        Returns:
            True if registered successfully
        """
        try:
            # Normalize hotkey format
            hotkey_lower = hotkey.lower()

            def _wrapper():
                try:
                    logger.info(f"Hotkey pressed: {hotkey_lower}")
                    callback()
                except Exception as e:
                    logger.error(f"Error in hotkey callback: {e}")

            keyboard.add_hotkey(hotkey_lower, _wrapper)
            self.registered_hotkeys[hotkey_lower] = {"callback": callback, "description": description}

            logger.info(f"Hotkey registered: {hotkey_lower} - {description}")
            return True
        except Exception as e:
            logger.error(f"Failed to register hotkey {hotkey}: {e}")
            return False

    def start(self, blocking=True):
        """Start listening for hotkeys

        Args:
            blocking: If True, blocks until stop() is called

        Returns:
            True if started successfully
        """
        try:
            logger.info(f"Hotkey listener starting with {len(self.registered_hotkeys)} hotkeys...")
            self.running = True

            if blocking:
                logger.info("Listening for hotkeys (blocking mode)...")
                keyboard.wait()  # Blocks indefinitely
            else:
                logger.info("Listening for hotkeys (non-blocking mode)...")

            return True
        except Exception as e:
            logger.error(f"Hotkey listener error: {e}")
            return False

    def stop(self):
        """Stop listening for hotkeys"""
        try:
            logger.info("Stopping hotkey listener...")
            keyboard.unhook_all()
            self.running = False
            logger.info("Hotkey listener stopped")
            return True
        except Exception as e:
            logger.error(f"Failed to stop hotkey listener: {e}")
            return False

    def unregister(self, hotkey):
        """Unregister a hotkey

        Args:
            hotkey: Hotkey string to unregister

        Returns:
            True if unregistered successfully
        """
        try:
            hotkey_lower = hotkey.lower()
            if hotkey_lower in self.registered_hotkeys:
                keyboard.remove_hotkey(hotkey_lower)
                del self.registered_hotkeys[hotkey_lower]
                logger.info(f"Hotkey unregistered: {hotkey_lower}")
                return True
            else:
                logger.warning(f"Hotkey not registered: {hotkey_lower}")
                return False
        except Exception as e:
            logger.error(f"Failed to unregister hotkey {hotkey}: {e}")
            return False

    def list_hotkeys(self):
        """List all registered hotkeys"""
        logger.info("Registered hotkeys:")
        for hotkey, info in self.registered_hotkeys.items():
            logger.info(f"  - {hotkey}: {info['description']}")
        return self.registered_hotkeys
