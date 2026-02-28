"""
Central logging setup for the roguelike.
Import `log` from this module wherever you need to emit a message.
The file is overwritten at the start of every run.
"""
import logging
import pathlib

_LOG_PATH = pathlib.Path(__file__).parent / "game.log"


def _setup() -> logging.Logger:
    logger = logging.getLogger("roguelike")
    logger.setLevel(logging.DEBUG)
    handler = logging.FileHandler(_LOG_PATH, mode="w", encoding="utf-8")
    handler.setFormatter(
        logging.Formatter(
            "%(asctime)s  %(levelname)-7s  %(message)s",
            datefmt="%H:%M:%S",
        )
    )
    logger.addHandler(handler)
    return logger


log = _setup()
