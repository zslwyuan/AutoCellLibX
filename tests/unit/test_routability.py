"""Unit tests for pySrc/routability.py (P0-4)."""
from routability import parseAstranLogRoutability, loadCellRoutability


LOG = """-> Routing cell...
-> Routing finished in 49 attempts after 0.524 s
 Iteration 97; cost = 24258.000
-> Final cost: Width=33; Gate Mismatches=4; WL=64; Rt. Density=5; Nr. Gaps=4
-> Routing cell...
-> Routing finished in 35 attempts after 0.542 s
-> Final cost: Width=30; Gate Mismatches=2; WL=60; Rt. Density=4; Nr. Gaps=3
-> Compacting layout...
-> Cell Size (W x H): 4.37 x 2.47
"""


def test_parse_takes_last_final_cost_and_max_attempts(tmp_path):
    log = tmp_path / "C1.Astranlog"
    log.write_text(LOG)
    m = parseAstranLogRoutability(str(log))
    assert m.widthTracks == 30          # last Final cost wins
    assert m.gateMismatches == 2
    assert m.rtDensity == 4
    assert m.gaps == 3
    assert m.routingAttempts == 49      # max over all routes


def test_score_orders_by_density_then_defects():
    log = None
    from routability import RoutabilityMetrics
    easy = RoutabilityMetrics(30, 0, 50, 3, 1, 10)
    hard = RoutabilityMetrics(30, 4, 50, 6, 5, 40)
    assert hard.score() > easy.score()


def test_missing_log_returns_none(tmp_path):
    assert parseAstranLogRoutability(str(tmp_path / "nope")) is None
    assert loadCellRoutability(str(tmp_path), "NOPE") is None


def test_real_astran_log_parses(in_pysrc):
    m = loadCellRoutability("./outputs/adder", "COMPLEX1")
    assert m is not None
    assert m.rtDensity > 0
    assert m.routingAttempts > 0
    assert m.widthTracks > 0
