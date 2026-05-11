import logging
import os

_LOG_DIR  = os.path.join(os.path.dirname(os.path.dirname(__file__)), "data")
_LOG_FILE = os.path.join(_LOG_DIR, "simulation.log")

# ── ANSI colour palette ──────────────────────────────────────────────────────
_R   = "\033[0m"       # reset
_BOLD= "\033[1m"
_GRAY= "\033[90m"      # muted – DEBUG noise
_CYAN= "\033[96m"      # LLM prompt  (CALL START / SYSTEM / USER)
_GRN = "\033[92m"      # LLM final response
_YLW = "\033[93m"      # LLM tool-call request (ASSISTANT — tool calls)
_MAG = "\033[95m"      # Tool result returned to LLM
_BLU = "\033[94m"      # Axiom verdict INFO
_RED = "\033[91m"      # WARNING / ERROR
# ────────────────────────────────────────────────────────────────────────────


class _ColorFormatter(logging.Formatter):
    """Console formatter that colours by message type."""

    def format(self, record: logging.LogRecord) -> str:
        base = super().format(record)

        # Errors / warnings always red-ish
        if record.levelno >= logging.ERROR:
            return f"{_BOLD}{_RED}{base}{_R}"
        if record.levelno >= logging.WARNING:
            return f"{_RED}{base}{_R}"

        # LLM logger — colour by content
        if record.name == "axioms.llm":
            msg = record.getMessage()
            if record.levelno == logging.DEBUG:
                if msg.startswith("LLM CALL START"):
                    return f"{_CYAN}{base}{_R}"
                if "ASSISTANT — final" in msg:
                    return f"{_GRN}{base}{_R}"
                if "ASSISTANT — tool calls" in msg:
                    return f"{_YLW}{base}{_R}"
                if msg.startswith("LLM TOOL RESULT"):
                    return f"{_MAG}{base}{_R}"
            if record.levelno == logging.INFO:
                return f"{_BLU}{base}{_R}"

        # Other DEBUG – muted grey
        if record.levelno == logging.DEBUG:
            return f"{_GRAY}{base}{_R}"

        return base


class _LLMDebugFilter(logging.Filter):
    """Pass all INFO+ records AND DEBUG records from axioms.llm only.

    This lets LLM prompt/response DEBUG messages appear on the console
    without flooding it with per-agent step-level debug noise.
    """
    def filter(self, record: logging.LogRecord) -> bool:
        if record.levelno >= logging.INFO:
            return True
        return record.name == "axioms.llm"


def _build_logger() -> logging.Logger:
    root = logging.getLogger("axioms")
    if root.handlers:
        return root
    root.setLevel(logging.DEBUG)

    plain_fmt = logging.Formatter(
        "%(asctime)s [%(levelname)-8s] %(name)s: %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )
    color_fmt = _ColorFormatter(
        "%(asctime)s [%(levelname)-8s] %(name)s: %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )

    # File handler – coloured, all levels
    fh = logging.FileHandler(_LOG_FILE, mode="a", encoding="utf-8")
    fh.setLevel(logging.DEBUG)
    fh.setFormatter(color_fmt)

    # Console handler – coloured, INFO+ and LLM debug
    ch = logging.StreamHandler()
    ch.setLevel(logging.DEBUG)          # filter controls what passes, not the level
    ch.setFormatter(color_fmt)
    ch.addFilter(_LLMDebugFilter())

    root.addHandler(fh)
    root.addHandler(ch)
    return root


logger = _build_logger()


def get_logger(name: str) -> logging.Logger:
    """Return a child logger under the 'axioms' hierarchy."""
    return logging.getLogger(f"axioms.{name}")
