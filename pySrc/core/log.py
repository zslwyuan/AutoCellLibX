"""Flow logging (dfx layer).

A single logger for the mining pipeline: level-filtered, timestamped,
with a stage prefix.  The CLI sees the same lines it saw before (INFO
goes to stdout); the GUI bridges events separately through
PipelineHooks.  New modules should log through ``getFlowLogger()``
instead of bare ``print`` so runs stay diagnosable and greppable.
"""

import logging
import sys

_NAME = "autocelllibx"
_LEVEL = logging.INFO


def getFlowLogger():
    """Process-wide flow logger (created once, console handler attached)."""
    logger = logging.getLogger(_NAME)
    if (not logger.handlers):
        handler = logging.StreamHandler(sys.stdout)
        handler.setFormatter(
            logging.Formatter("%(asctime)s %(levelname)-7s %(message)s",
                              datefmt="%H:%M:%S"))
        logger.addHandler(handler)
        logger.setLevel(_LEVEL)
        logger.propagate = False
    return logger


def setFlowLogLevel(level):
    """Adjust the flow logger verbosity (logging.DEBUG/INFO/...)."""
    logger = logging.getLogger(_NAME)
    logger.setLevel(level)
