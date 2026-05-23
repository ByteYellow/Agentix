"""Small env-driven logging setup shared by host, runtime, and worker."""

from __future__ import annotations

import logging
import os
import socket
import sys
from typing import TextIO

LOG_CONTEXT_ATTR = "agentix_context"
DEFAULT_LOG_FORMAT = f"%(asctime)s [%({LOG_CONTEXT_ATTR})s] [%(name)s] %(message)s"

_context = "host"
_factory_installed = False
_previous_factory = logging.getLogRecordFactory()


class _SafeFormatMap(dict[str, str]):
    def __missing__(self, key: str) -> str:
        return "{" + key + "}"


def configure_logging(
    *,
    default_context: str = "host",
    stream: TextIO | None = None,
    force: bool = False,
) -> None:
    """Configure stdlib logging from Agentix env vars.

    Env vars:
      AGENTIX_LOG_LEVEL: logging level name, default INFO.
      AGENTIX_LOG_FORMAT: stdlib %-style format string.
      AGENTIX_LOG_CONTEXT: context template for this process.

    Context templates support `{uname}`, `{hostname}`, `{pid}`, and
    `{id}`. The worker spawner sets `AGENTIX_WORKER_ID`, which backs
    `{id}` inside worker processes.
    """
    set_log_context(os.environ.get("AGENTIX_LOG_CONTEXT", default_context))
    level_name = os.environ.get("AGENTIX_LOG_LEVEL", "INFO").upper()
    level = getattr(logging, level_name, logging.INFO)
    log_format = os.environ.get("AGENTIX_LOG_FORMAT", DEFAULT_LOG_FORMAT)
    logging.basicConfig(
        level=level,
        stream=stream or sys.stderr,
        format=log_format,
        force=force,
    )


def set_log_context(template: str) -> None:
    global _context
    _context = _expand_context(template)
    _install_record_factory()


def get_log_context() -> str:
    return _context


def _expand_context(template: str) -> str:
    hostname = socket.gethostname()
    values = _SafeFormatMap(
        {
            "hostname": hostname,
            "uname": hostname,
            "pid": str(os.getpid()),
            "id": os.environ.get("AGENTIX_WORKER_ID", str(os.getpid())),
        }
    )
    try:
        return template.format_map(values)
    except ValueError:
        return template


def _install_record_factory() -> None:
    global _factory_installed
    if _factory_installed:
        return

    def record_factory(*args, **kwargs):
        record = _previous_factory(*args, **kwargs)
        if not hasattr(record, LOG_CONTEXT_ATTR):
            setattr(record, LOG_CONTEXT_ATTR, _context)
        return record

    logging.setLogRecordFactory(record_factory)
    _factory_installed = True


__all__ = [
    "DEFAULT_LOG_FORMAT",
    "LOG_CONTEXT_ATTR",
    "configure_logging",
    "get_log_context",
    "set_log_context",
]
