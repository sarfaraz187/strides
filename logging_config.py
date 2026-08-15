import logging
import os
import sys


def setup_logging():
    level = os.environ.get("LOG_LEVEL", "INFO").upper()
    logging.basicConfig(
        level=level,
        stream=sys.stderr,
        format="%(levelname)s %(filename)s:%(lineno)d %(funcName)s — %(message)s",
    )
