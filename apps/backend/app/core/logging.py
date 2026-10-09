import logging
import sys
from pathlib import Path

from loguru import logger

from .config import Settings


def configure_logging(settings: Settings) -> None:
    # httpx INFO includes URLs. WeChat requires secrets in its query; never emit client request logs.
    logging.getLogger("httpx").setLevel(logging.WARNING)
    logging.getLogger("httpcore").setLevel(logging.WARNING)
    logger.remove()
    logger.add(
        sys.stderr,
        level=settings.log_level,
        serialize=settings.environment == "production",
        backtrace=False,
        diagnose=False,
        enqueue=False,
    )
    if settings.log_file_enabled and settings.log_file_path:
        log_path = Path(settings.log_file_path)
        log_path.parent.mkdir(parents=True, exist_ok=True)
        logger.add(
            settings.log_file_path,
            level=settings.log_level,
            serialize=True,
            rotation=settings.log_file_rotation,
            retention=settings.log_file_retention,
            compression="zip",
            encoding="utf-8",
            enqueue=True,
            backtrace=False,
            diagnose=False,
        )
