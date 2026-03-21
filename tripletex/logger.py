"""
Logging setup.

- Local dev (LOG_FORMAT=pretty or unset): human-readable colored output
- Production / Cloud Run (LOG_FORMAT=json): JSON lines, parsed by GCP Cloud Logging

Set LOG_LEVEL env var to control verbosity (default: INFO).
"""

import json
import logging
import os
import sys
import traceback
from datetime import datetime, timezone


class _JsonFormatter(logging.Formatter):
    """Formats log records as single-line JSON for GCP Cloud Logging."""

    # Map Python level names to GCP severity strings
    _SEVERITY = {
        "DEBUG": "DEBUG",
        "INFO": "INFO",
        "WARNING": "WARNING",
        "ERROR": "ERROR",
        "CRITICAL": "CRITICAL",
    }

    def format(self, record: logging.LogRecord) -> str:
        payload: dict = {
            "severity": self._SEVERITY.get(record.levelname, record.levelname),
            "message": record.getMessage(),
            "timestamp": datetime.fromtimestamp(record.created, tz=timezone.utc).isoformat(),
            "logger": record.name,
        }
        # Attach any extra fields passed via the `extra` kwarg
        for key, value in record.__dict__.items():
            if key.startswith("_") or key in {
                "args", "asctime", "created", "exc_info", "exc_text", "filename",
                "funcName", "id", "levelname", "levelno", "lineno", "message",
                "module", "msecs", "msg", "name", "pathname", "process",
                "processName", "relativeCreated", "stack_info", "thread", "threadName",
            }:
                continue
            payload[key] = value

        if record.exc_info:
            payload["exception"] = self.formatException(record.exc_info)

        return json.dumps(payload, default=str)


class _PrettyFormatter(logging.Formatter):
    """Human-readable formatter for local development."""

    COLORS = {
        "DEBUG":    "\033[36m",   # cyan
        "INFO":     "\033[32m",   # green
        "WARNING":  "\033[33m",   # yellow
        "ERROR":    "\033[31m",   # red
        "CRITICAL": "\033[35m",   # magenta
    }
    RESET = "\033[0m"
    DIM = "\033[2m"
    BOLD = "\033[1m"

    def format(self, record: logging.LogRecord) -> str:
        color = self.COLORS.get(record.levelname, "")
        level = f"{color}{record.levelname:<8}{self.RESET}"
        name = f"{self.DIM}{record.name}{self.RESET}"
        msg = record.getMessage()

        # Collect extras
        skip = {
            "args", "asctime", "created", "exc_info", "exc_text", "filename",
            "funcName", "id", "levelname", "levelno", "lineno", "message",
            "module", "msecs", "msg", "name", "pathname", "process",
            "processName", "relativeCreated", "stack_info", "thread", "threadName",
        }
        extras = {k: v for k, v in record.__dict__.items() if not k.startswith("_") and k not in skip}

        line = f"{level} {name}: {self.BOLD}{msg}{self.RESET}"
        if extras:
            extras_str = "  ".join(f"{self.DIM}{k}={self.RESET}{v}" for k, v in extras.items())
            line += f"\n         {extras_str}"

        if record.exc_info:
            line += "\n" + self.formatException(record.exc_info)

        return line


def setup_logging() -> None:
    log_format = os.environ.get("LOG_FORMAT", "pretty").lower()
    log_level = os.environ.get("LOG_LEVEL", "INFO").upper()

    handler = logging.StreamHandler(sys.stdout)
    handler.setFormatter(_JsonFormatter() if log_format == "json" else _PrettyFormatter())

    root = logging.getLogger()
    root.setLevel(getattr(logging, log_level, logging.INFO))
    root.handlers = [handler]

    # Log all levels to file for analysis (fresh file each server start)
    log_file = os.environ.get("LOG_FILE")
    if log_file:
        fh = logging.FileHandler(log_file, mode="w")
        fh.setLevel(logging.DEBUG)
        fh.setFormatter(logging.Formatter("%(levelname)s %(name)s: %(message)s"))
        root.addHandler(fh)

    # Quiet noisy third-party loggers
    for noisy in ("httpx", "httpcore", "urllib3", "google", "grpc"):
        logging.getLogger(noisy).setLevel(logging.WARNING)


class _Logger:
    """Thin wrapper so callers can pass extra fields as kwargs instead of extra={}."""

    def __init__(self, name: str):
        self._log = logging.getLogger(name)

    def debug(self, msg: str, **kwargs):
        self._log.debug(msg, extra=kwargs, stacklevel=2)
        sys.stdout.flush()

    def info(self, msg: str, **kwargs):
        self._log.info(msg, extra=kwargs, stacklevel=2)
        sys.stdout.flush()

    def warning(self, msg: str, **kwargs):
        self._log.warning(msg, extra=kwargs, stacklevel=2)
        sys.stdout.flush()

    def error(self, msg: str, **kwargs):
        self._log.error(msg, extra=kwargs, stacklevel=2)
        sys.stdout.flush()

    def exception(self, msg: str, **kwargs):
        self._log.exception(msg, extra=kwargs, stacklevel=2)
        sys.stdout.flush()


def get_logger(name: str) -> _Logger:
    return _Logger(name)
