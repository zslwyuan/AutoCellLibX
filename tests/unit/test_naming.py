"""Naming reform (direct rename, no aliases): the legacy camelCase names
must not appear anywhere in pySrc/gui/tests."""
import pathlib
import re

LEGACY = ["loadLibertyFile", "loadBoolGateFromBLIF",
          "genGraphFromLibertyAndBLIF", "loadSpiceSubcircuits",
          "extractAndEncodeSubgraph_Tree", "canonicalPatternCode",
          "escapeOutputCount", "heuristicLabelSomeNodesAndGetInitialClusters",
          "growASeqOfClusters", "getFlowLogger", "setFlowLogLevel"]


def test_no_legacy_names_in_code():
    root = pathlib.Path(__file__).resolve().parents[2]
    hits = []
    for path in list((root / "pySrc").rglob("*.py")) \
            + list((root / "gui").rglob("*.py")) \
            + list((root / "tests").rglob("*.py")):
        if path.name == "test_naming.py":    # the LEGACY list lives here
            continue
        text = path.read_text(encoding="utf-8", errors="ignore")
        for name in LEGACY:
            if re.search(r"(?<![A-Za-z0-9_])" + name + r"(?![A-Za-z0-9_])",
                         text):
                hits.append("%s: %s" % (path.name, name))
    assert not hits, hits
