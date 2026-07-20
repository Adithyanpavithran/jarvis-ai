import os
import logging
from logging.handlers import RotatingFileHandler
from pathlib import Path

def get_app_dir() -> Path:
    """Get the standard application data directory for Jarvis."""
    app_data = os.environ.get("APPDATA")
    if app_data:
        base_dir = Path(app_data)
    else:
        base_dir = Path("~").expanduser()
    jarvis_dir = base_dir / "Jarvis"
    jarvis_dir.mkdir(parents=True, exist_ok=True)
    return jarvis_dir

def setup_logger() -> logging.Logger:
    """Setup a rotating file logger for Jarvis."""
    app_dir = get_app_dir()
    log_dir = app_dir / "logs"
    log_dir.mkdir(parents=True, exist_ok=True)
    log_file = log_dir / "jarvis.log"

    logger = logging.getLogger("jarvis")
    logger.setLevel(logging.INFO)

    # Avoid duplicate handlers if setup_logger is called multiple times
    if not logger.handlers:
        formatter = logging.Formatter(
            "%(asctime)s - %(name)s - %(levelname)s - %(message)s",
            datefmt="%Y-%m-%d %H:%M:%S"
        )

        # Rotating file handler: 10MB per file, keep 5 backups
        file_handler = RotatingFileHandler(
            log_file, maxBytes=10 * 1024 * 1024, backupCount=5, encoding="utf-8"
        )
        file_handler.setFormatter(formatter)
        logger.addHandler(file_handler)

        # Console handler
        console_handler = logging.StreamHandler()
        console_handler.setFormatter(formatter)
        logger.addHandler(console_handler)

    return logger

log = setup_logger()
