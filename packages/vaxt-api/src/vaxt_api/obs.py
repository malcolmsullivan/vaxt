"""Minimal JSON logging for the BrAPI server.

Deliberately duplicated (~40 lines of stdlib) rather than imported from
vaxt-agent: vaxt-api depends on nothing internal, and a logging formatter is
not worth inverting that — the agent stack (anthropic, mcp) must not enter
this package's install for the sake of a formatter. Extract a shared package
only if a third consumer ever appears.
"""

import json
import logging
import time


class JsonFormatter(logging.Formatter):
    """One JSON object per line. Extra fields passed via `extra=` are included."""

    _RESERVED = frozenset(
        logging.LogRecord("", 0, "", 0, "", (), None).__dict__
    ) | {"message", "taskName"}

    def format(self, record: logging.LogRecord) -> str:
        entry = {
            "ts": time.strftime("%Y-%m-%dT%H:%M:%S", time.gmtime(record.created))
            + f".{int(record.msecs):03d}Z",
            "level": record.levelname,
            "logger": record.name,
            "msg": record.getMessage(),
        }
        for k, v in record.__dict__.items():
            if k not in self._RESERVED and not k.startswith("_"):
                entry[k] = v
        if record.exc_info:
            entry["exc"] = self.formatException(record.exc_info)
        return json.dumps(entry, default=str)


def setup_json_logging(level: int = logging.INFO) -> None:
    """Route the root logger through the JSON formatter (idempotent)."""
    root = logging.getLogger()
    if any(isinstance(h.formatter, JsonFormatter) for h in root.handlers):
        return
    handler = logging.StreamHandler()
    handler.setFormatter(JsonFormatter())
    root.handlers = [handler]
    root.setLevel(level)
