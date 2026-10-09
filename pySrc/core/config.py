"""FlowConfig: single configuration object for the mining pipeline.

Replaces the mutable module-level globals (global_variables.py) and the
hard-coded tunables at the top of main.py.  Defaults reproduce the
current behaviour exactly; ``FlowConfig.from_env()`` reads the
environment overrides (AUTOCELL_REUSE_MODE, AUTOCELL_PDK).
"""

import dataclasses
import os


@dataclasses.dataclass
class FlowConfig:
    # --- mining tunables (were main.py top-of-main locals) ---
    topThr: int = 5
    ratioThr: float = 0.05
    cntThr: int = 30
    benchmarks: tuple = ("adder",)
    # special-case threshold for tc_008_arthmetic_sin (historical)
    tc008RatioThr: float = 0.025

    # --- growth / gates (were global_variables) ---
    growBeamWidth: int = 2
    routabilityDensityGate: float = None          # None = report only
    layoutSanityGate: bool = True
    useWidthProxyForGrowth: bool = False
    requireReuseEligible: bool = False

    # --- dual-mode (AUTOCELL_REUSE_MODE=1) ---
    reuseMode: bool = False
    outputSuffix: str = ""                        # "_reuse" in reuse mode

    # --- advisory layout hints (P2 stage 3; AUTOCELL_HINT_MODE) ---
    # off | offline | llm.  Default off: hints are report-only and a
    # default run is byte-identical to one without this feature.
    hintMode: str = "off"

    # --- library / PDK paths (were Astran constants) ---
    liberty: str = "../stdCelllib/gscl45nm.lib"
    spiceLib: str = "../stdCelllib/cellsAstranFriendly.sp"
    lef: str = "../stdCelllib/gscl45nm.lef"
    blifDir: str = "../benchmark/blif"
    astranBuildPath: str = ""                     # empty = no layout runs

    def outputDir(self, benchmarkName):
        return "./outputs/" + benchmarkName + self.outputSuffix + "/"

    @classmethod
    def from_env(cls):
        """Build a config honouring the supported environment variables."""
        reuse = os.environ.get("AUTOCELL_REUSE_MODE", "0") == "1"
        return cls(
            reuseMode=reuse,
            outputSuffix="_reuse" if reuse else "",
            requireReuseEligible=reuse,
            hintMode=os.environ.get("AUTOCELL_HINT_MODE", "off"),
        )

    def ratioThrFor(self, benchmarkName):
        return (self.tc008RatioThr
                if benchmarkName == "tc_008_arthmetic_sin"
                else self.ratioThr)
