"""Thin CLI over core.pipeline (architecture refactor).

All flow logic lives in flow/core/pipeline.py (run_pipeline); this file
only builds the FlowConfig and dispatches.  Tunables: env variables
AUTOCELL_REUSE_MODE=1 (synthesis-reuse dual mode) -- see
core/config.py.
"""

import matplotlib

from core.config import FlowConfig
from core.pipeline import run_pipeline


def main():
    cfg = FlowConfig.from_env()
    run_pipeline(cfg)


if __name__ == '__main__':
    matplotlib.use("Pdf")
    main()
