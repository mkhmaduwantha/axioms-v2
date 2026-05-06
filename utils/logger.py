import logging
import os

_LOG_DIR  = os.path.join(os.path.dirname(os.path.dirname(__file__)), "data")
_LOG_FILE = os.path.join(_LOG_DIR, "simulation.txt")

def _build_logger() -> logging.Logger:
    root = logging.getLogger("axioms")
    if root.handlers:
        return root
    root.setLevel(logging.DEBUG)

    fmt = logging.Formatter(
        "%(asctime)s [%(levelname)-8s] %(name)s: %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )

    fh = logging.FileHandler(_LOG_FILE, mode="a", encoding="utf-8")
    fh.setLevel(logging.DEBUG)
    fh.setFormatter(fmt)

    ch = logging.StreamHandler()
    ch.setLevel(logging.INFO)
    ch.setFormatter(fmt)

    root.addHandler(fh)
    root.addHandler(ch)
    return root

logger = _build_logger()

def get_logger(name: str) -> logging.Logger:
    """Return a child logger under the 'axioms' hierarchy."""
    return logging.getLogger(f"axioms.{name}")
