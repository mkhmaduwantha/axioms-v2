import logging
import os

_LOG_DIR      = os.path.join(os.path.dirname(os.path.dirname(__file__)), "data")
_SIM_LOG      = os.path.join(_LOG_DIR, "simulation.log")   # all logs except raw LLM I/O
_LLM_LOG      = os.path.join(_LOG_DIR, "llm_prompts.log")  # raw prompts, responses, tool calls

# ── ANSI colour palette ──────────────────────────────────────────────────────
_R   = "\033[0m"
_BOLD= "\033[1m"
_GRAY= "\033[90m"
_CYAN= "\033[96m"
_GRN = "\033[92m"
_YLW = "\033[93m"
_MAG = "\033[95m"
_BLU = "\033[94m"
_RED = "\033[91m"
# ────────────────────────────────────────────────────────────────────────────


def _is_llm_raw(record: logging.LogRecord) -> bool:
    """True for the verbose DEBUG messages that contain raw LLM I/O."""
    if record.name != "axioms.llm" or record.levelno != logging.DEBUG:
        return False
    msg = record.getMessage()
    return any(tok in msg for tok in (
        "LLM CALL START", "LLM RESPONSE", "LLM TOOL RESULT",
    ))


class _ColorFormatter(logging.Formatter):
    def format(self, record: logging.LogRecord) -> str:
        base = super().format(record)

        if record.levelno >= logging.ERROR:
            return f"{_BOLD}{_RED}{base}{_R}"
        if record.levelno >= logging.WARNING:
            return f"{_RED}{base}{_R}"

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

        if record.levelno == logging.DEBUG:
            return f"{_GRAY}{base}{_R}"

        return base


class _ExcludeLLMRawFilter(logging.Filter):
    """Block raw LLM I/O DEBUG records — everything else passes."""
    def filter(self, record: logging.LogRecord) -> bool:
        return not _is_llm_raw(record)


class _LLMRawOnlyFilter(logging.Filter):
    """Pass only raw LLM I/O DEBUG records."""
    def filter(self, record: logging.LogRecord) -> bool:
        return _is_llm_raw(record)


class _ConsoleFilter(logging.Filter):
    """Console: INFO+ from all loggers, plus LLM raw DEBUG."""
    def filter(self, record: logging.LogRecord) -> bool:
        return record.levelno >= logging.INFO or _is_llm_raw(record)


def _build_logger() -> logging.Logger:
    root = logging.getLogger("axioms")
    if root.handlers:
        return root
    root.setLevel(logging.DEBUG)

    color_fmt = _ColorFormatter(
        "%(asctime)s [%(levelname)-8s] %(name)s: %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )

    # simulation.log — everything EXCEPT raw LLM I/O debug
    fh_sim = logging.FileHandler(_SIM_LOG, mode="a", encoding="utf-8")
    fh_sim.setLevel(logging.DEBUG)
    fh_sim.setFormatter(color_fmt)
    fh_sim.addFilter(_ExcludeLLMRawFilter())

    # llm_prompts.log — raw LLM I/O debug only
    fh_llm = logging.FileHandler(_LLM_LOG, mode="a", encoding="utf-8")
    fh_llm.setLevel(logging.DEBUG)
    fh_llm.setFormatter(color_fmt)
    fh_llm.addFilter(_LLMRawOnlyFilter())

    # Console — INFO+ and raw LLM debug (coloured)
    ch = logging.StreamHandler()
    ch.setLevel(logging.DEBUG)
    ch.setFormatter(color_fmt)
    ch.addFilter(_ConsoleFilter())

    root.addHandler(fh_sim)
    root.addHandler(fh_llm)
    root.addHandler(ch)
    return root


logger = _build_logger()


def get_logger(name: str) -> logging.Logger:
    return logging.getLogger(f"axioms.{name}")
