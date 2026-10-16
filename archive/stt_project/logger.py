import logging
import logging.handlers
from pathlib import Path

def setup_logger(name=__name__, log_file="stt_service.log"):
    """Setup file logging with rotation"""
    log_path = Path(__file__).parent / log_file

    logger = logging.getLogger(name)
    logger.setLevel(logging.INFO)

    # Rotating file handler (10MB max, 3 backups)
    handler = logging.handlers.RotatingFileHandler(
        log_path,
        maxBytes=10*1024*1024,
        backupCount=3
    )

    formatter = logging.Formatter(
        '%(asctime)s - %(name)s - %(levelname)s - %(message)s'
    )
    handler.setFormatter(formatter)

    logger.addHandler(handler)

    # Also log to console
    console_handler = logging.StreamHandler()
    console_handler.setFormatter(formatter)
    logger.addHandler(console_handler)

    return logger
