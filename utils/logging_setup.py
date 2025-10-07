"""Utilities for configuring application logging."""
from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Optional, Tuple


LOG_DIR = Path("logs")


@dataclass
class LoggingContext:
    """Represents configuration metadata for a logging session."""

    logger: logging.Logger
    log_path: Optional[Path]


class _GuiLogHandler(logging.Handler):
    """In-memory handler used by the GUI to surface live logs."""

    def __init__(self) -> None:
        super().__init__()
        self.messages: list[str] = []

    def emit(self, record: logging.LogRecord) -> None:
        msg = self.format(record)
        self.messages.append(msg)

    def consume(self) -> str:
        text = "\n".join(self.messages)
        self.messages.clear()
        return text


def setup_logging(enable_file_logging: bool, level: int = logging.INFO) -> LoggingContext:
    """Set up application logging.

    Parameters
    ----------
    enable_file_logging:
        Whether to create a timestamped file under ``logs/``.
    level:
        Logging level for the root logger.
    """

    LOG_DIR.mkdir(exist_ok=True)

    logger = logging.getLogger("vidub")
    logger.setLevel(level)

    # Remove existing handlers to avoid duplicates when called multiple times.
    for handler in list(logger.handlers):
        logger.removeHandler(handler)

    formatter = logging.Formatter("%(asctime)s | %(levelname)s | %(message)s")

    stream_handler = logging.StreamHandler()
    stream_handler.setFormatter(formatter)
    logger.addHandler(stream_handler)

    log_path: Optional[Path] = None
    if enable_file_logging:
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        log_path = LOG_DIR / f"run_{timestamp}.log"
        file_handler = logging.FileHandler(log_path, encoding="utf-8")
        file_handler.setFormatter(formatter)
        logger.addHandler(file_handler)

    return LoggingContext(logger=logger, log_path=log_path)


def attach_gui_handler(logger: logging.Logger) -> Tuple[_GuiLogHandler, logging.Handler]:
    """Attach a GUI buffer handler to ``logger`` and return it along with the
    formatter-equipped handler so that callers can consume log messages in
    batches."""

    gui_handler = _GuiLogHandler()
    gui_handler.setFormatter(logging.Formatter("%(asctime)s | %(levelname)s | %(message)s"))
    logger.addHandler(gui_handler)
    return gui_handler, gui_handler
