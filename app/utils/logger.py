from __future__ import annotations

import contextvars
import logging
import sys
from collections.abc import Mapping
from typing import Any


request_id_var: contextvars.ContextVar[str] = contextvars.ContextVar(
    "request_id", default="-"
)


class RequestIdFilter(logging.Filter):
    def filter(self, record: logging.LogRecord) -> bool:
        record.request_id = request_id_var.get()
        return True


class ColorFormatter(logging.Formatter):
    COLORS = {
        "DEBUG": "\033[36m",
        "INFO": "\033[32m",
        "WARNING": "\033[33m",
        "ERROR": "\033[31m",
        "CRITICAL": "\033[35m",
    }
    RESET = "\033[0m"

    def format(self, record: logging.LogRecord) -> str:
        if sys.stderr.isatty() or sys.stdout.isatty():
            color = self.COLORS.get(record.levelname, "")
            record.levelname = f"{color}{record.levelname}{self.RESET}"
        return super().format(record)


def configure_logging(level: str = "INFO") -> None:
    root = logging.getLogger()
    root.handlers.clear()
    root.setLevel(level)

    handler = logging.StreamHandler()
    handler.setLevel(level)
    handler.addFilter(RequestIdFilter())
    handler.setFormatter(
        ColorFormatter(
            "%(asctime)s | %(levelname)-8s | %(name)s | request=%(request_id)s | %(message)s",
            datefmt="%H:%M:%S",
        )
    )
    root.addHandler(handler)

    for noisy_logger in ("python_multipart", "multipart"):
        logging.getLogger(noisy_logger).setLevel(logging.WARNING)


def get_logger(name: str) -> logging.Logger:
    return logging.getLogger(name)


def bind_request_id(request_id: str) -> contextvars.Token[str]:
    return request_id_var.set(request_id)


def reset_request_id(token: contextvars.Token[str]) -> None:
    request_id_var.reset(token)


def log_event(
    logger: logging.Logger,
    level: int,
    event: str,
    fields: Mapping[str, Any] | None = None,
) -> None:
    pairs = [f"event={event}"]
    for key, value in (fields or {}).items():
        pairs.append(f"{key}={_format_value(value)}")
    logger.log(level, " ".join(pairs))


def _format_value(value: Any) -> str:
    if value is None:
        return "null"
    if isinstance(value, bool):
        return str(value).lower()
    text = str(value)
    if any(ch.isspace() for ch in text):
        return repr(text)
    return text


def mask_identifier(value: str) -> str:
    if not value:
        return ""
    compact = value.strip()
    if len(compact) <= 4:
        return "*" * len(compact)
    return f"{'*' * (len(compact) - 4)}{compact[-4:]}"
