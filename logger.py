"""
Central logging setup for the roguelike.
Import `log` from this module wherever you need to emit a message.
The file is overwritten at the start of every run, then capped at 500 KB
with one backup (~1 MB max total on disk).
"""
import logging
import logging.handlers
import pathlib

_LOG_PATH = pathlib.Path(__file__).parent / "game.log"


def _setup() -> logging.Logger:
    logger = logging.getLogger("roguelike")
    logger.setLevel(logging.DEBUG)

    # Wipe the log from the previous run, then use a rotating handler so a
    # long demo session can never grow the file beyond ~1 MB total.
    _LOG_PATH.unlink(missing_ok=True)
    handler = logging.handlers.RotatingFileHandler(
        _LOG_PATH, maxBytes=500_000, backupCount=1, encoding="utf-8"
    )
    handler.setFormatter(
        logging.Formatter(
            "%(asctime)s  %(levelname)-7s  %(message)s",
            datefmt="%H:%M:%S",
        )
    )
    logger.addHandler(handler)
    return logger


log = _setup()
