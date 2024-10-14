import logging
from rich.logging import RichHandler

logger = logging.getLogger(__name__)
logger.propagate = False 
def setup_logger(verbosity=0):
    level = logging.WARNING
    if verbosity == 1:
        level = logging.INFO
    elif verbosity >= 2:
        level = logging.DEBUG

    logger.setLevel(level)
    
    for handler in logger.handlers[:]:
        logger.removeHandler(handler)
        handler.close()

    handler = RichHandler(rich_tracebacks=True)
    formatter = logging.Formatter("%(message)s", datefmt="[%X]")
    handler.setFormatter(formatter)
    logger.addHandler(handler)