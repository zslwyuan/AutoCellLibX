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
    top_thr: int = 5
    ratio_thr: float = 0.05
    cnt_thr: int = 30
    benchmarks: tuple = ("adder",)
    # special-case threshold for tc_008_arthmetic_sin (historical)
    tc008_ratio_thr: float = 0.025

    # --- growth / gates (were global_variables) ---
    grow_beam_width: int = 2
    routability_density_gate: float = None          # None = report only
    layout_sanity_gate: bool = True
    use_width_proxy_for_growth: bool = False
    require_reuse_eligible: bool = False

    # --- dual-mode (AUTOCELL_REUSE_MODE=1) ---
    reuse_mode: bool = False
    output_suffix: str = ""                        # "_reuse" in reuse mode

    # --- advisory layout hints (P2 stage 3; AUTOCELL_HINT_MODE) ---
    # off | offline | llm.  Default off: hints are report-only and a
    # default run is byte-identical to one without this feature.
    hint_mode: str = "off"

    # --- library / PDK paths (were Astran constants) ---
    liberty: str = "../stdCelllib/gscl45nm.lib"
    spice_lib: str = "../stdCelllib/cellsAstranFriendly.sp"
    lef: str = "../stdCelllib/gscl45nm.lef"
    blif_dir: str = "../benchmark/blif"
    astran_build_path: str = ""                     # empty = no layout runs

    def output_dir(self, benchmark_name):
        return "./outputs/" + benchmark_name + self.output_suffix + "/"

    @classmethod
    def from_env(cls):
        """Build a config honouring the supported environment variables."""
        reuse = os.environ.get("AUTOCELL_REUSE_MODE", "0") == "1"
        return cls(
            reuse_mode=reuse,
            output_suffix="_reuse" if reuse else "",
            require_reuse_eligible=reuse,
            hint_mode=os.environ.get("AUTOCELL_HINT_MODE", "off"),
        )

    def ratio_thr_for(self, benchmark_name):
        return (self.tc008_ratio_thr
                if benchmark_name == "tc_008_arthmetic_sin"
                else self.ratio_thr)
