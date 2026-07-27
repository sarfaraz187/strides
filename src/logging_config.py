import logging
import sys


def setup_logging():
    logging.basicConfig(
        level=logging.INFO,
        stream=sys.stderr,
        format="%(levelname)s %(filename)s:%(lineno)d %(funcName)s — %(message)s",
    )
