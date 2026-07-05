"""Observability for the Ask VAXT web service.

Stdlib logging with a JSON formatter — no logging dependency. Every request
gets a `trace_id` (contextvar, so it flows through sync endpoints and can be
handed explicitly to worker threads). Tool-call logs redact the args that can
locate a grower (coordinates and free-text place strings); the user's question
is never logged as text, only its length.

Cost figures are ESTIMATES from a static price table (list USD per million
tokens, as of PRICE_TABLE_AS_OF) — they are not billing truth. An unknown
model logs a warning and reports `est_cost_usd: null` rather than a guess.
"""

import contextvars
import json
import logging
import time
import uuid

trace_id_var = contextvars.ContextVar("vaxt_trace_id", default="")

# List prices actually in effect, USD per million tokens (input, output). Only
# the models this system calls: the agent default and the live-eval judge.
# claude-sonnet-5 is in its introductory window ($2/$10 through 2026-08-31);
# after that it reverts to the durable $3/$15 — update this table then, or the
# est_cost_usd figures will read ~50% low.
PRICE_TABLE_AS_OF = "2026-07"
PRICE_TABLE: dict[str, tuple[float, float]] = {
    "claude-sonnet-5": (2.00, 10.00),   # intro rate; reverts to (3.00, 15.00) 2026-09-01
    "claude-opus-4-8": (5.00, 25.00),
}

# Tool args that can pinpoint a grower's farm: exact coordinates
# (match_varieties, get_climate_profile) and free-text place strings
# (get_journal_entries.location, get_growing_season.station).
REDACT_ARGS = frozenset({"lat", "lon", "location", "station"})

log = logging.getLogger("vaxt_agent.obs")


def new_trace_id() -> str:
    return uuid.uuid4().hex[:16]


def redact(args: dict) -> dict:
    """Mask location-bearing values; keep the key so logs show it was present."""
    return {
        k: "<redacted>" if k in REDACT_ARGS and v is not None else v
        for k, v in (args or {}).items()
    }


def est_cost_usd(model: str, input_tokens: int, output_tokens: int) -> float | None:
    """Estimated cost from the static list-price table; None if model unknown."""
    prices = PRICE_TABLE.get(model)
    if prices is None:
        log.warning("cost_model_unknown model=%s", model)
        return None
    in_per_mtok, out_per_mtok = prices
    return round(
        input_tokens / 1e6 * in_per_mtok + output_tokens / 1e6 * out_per_mtok, 6
    )


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
        tid = trace_id_var.get()
        if tid:
            entry["trace_id"] = tid
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


def log_tool_call(name: str, args: dict, row_count: int, latency_ms: float,
                  error: str | None = None) -> None:
    logging.getLogger("vaxt_agent.web").info(
        "tool_call %s", name,
        extra={
            "event": "tool_call",
            "tool": name,
            "args_redacted": redact(args),
            "row_count": row_count,
            "latency_ms": round(latency_ms, 1),
            **({"error": error} if error else {}),
        },
    )


def log_model_call(model: str, usage: dict, latency_ms: float) -> None:
    input_tokens = int(usage.get("input_tokens", 0) or 0)
    output_tokens = int(usage.get("output_tokens", 0) or 0)
    logging.getLogger("vaxt_agent.web").info(
        "model_call %s", model,
        extra={
            "event": "model_call",
            "model": model,
            "input_tokens": input_tokens,
            "output_tokens": output_tokens,
            "latency_ms": round(latency_ms, 1),
            "est_cost_usd": est_cost_usd(model, input_tokens, output_tokens),
        },
    )
