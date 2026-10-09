"""Cheap width-prediction proxy for candidate complexes (P2 phase 1).

FusionCell (arXiv'26) predicts a cell's performance from its netlist and
layout without running the full flow; we take the affordable slice of
that idea: a small regression over features known *before* layout

    n_cells          -- how many library cells are merged
    n_transistors    -- total transistor count of the merged netlist
    base_width_um    -- sum of the members' ASTRAN baseline widths

trained on the layouts already generated in this repository
(outputs/*/COMPLEX*.sp + .Astranlog, plus the 32-cell baseline).  The
proxy answers the question the ShrinkModel answers, but with the actual
netlist shape in the loop instead of only the cell count -- and it is
validated honestly (leave-one-out MAPE/R^2 on the same corpus).

Usage as a growth benefit estimator (same signature as
benefit.makeGrowthBenefitEstimator's closure):

    proxy = WidthProxy().fit(collectSamples(...))
    estimator = makeProxyBenefitEstimator(proxy, stdType2AstranArea,
                                          transistorCounts)
"""

import glob
import os
import re

_SUBCKT_RE = re.compile(r"^\.subckt\s+(\S+)\s+(.*)$")
_TRACE_EXT_RE = re.compile(r"\+([A-Za-z0-9]+)_c\d+[io]\d+")
_TRANSISTOR_RE = re.compile(r"^M\S*\s", re.M)


def countTransistorsPerType(spiceLibPath):
    """{typeName: transistor count} from a SPICE subckt library."""
    counts = {}
    curName = None
    for line in open(spiceLibPath):
        if (line.startswith(".subckt")):
            m = _SUBCKT_RE.match(line.strip())
            curName = m.group(1) if m else None
            if (curName):
                counts.setdefault(curName, 0)
        elif (line.startswith(".ends")):
            curName = None
        elif (curName and _TRANSISTOR_RE.match(line)):
            counts[curName] += 1
    return counts


def parseTraceTypes(trace):
    """Member type names of a pattern trace
    '[A,B,C]+D_c0o0+E_c1i0' -> ['A', 'B', 'C', 'D', 'E']."""
    base = trace.split("+")[0].strip("[]")
    types = [t for t in base.split(",") if t]
    types += _TRACE_EXT_RE.findall(trace)
    return types


def collectSamples(outputDirs, transistorCounts, stdType2Width):
    """Build the dataset from generated cells.

    Each sample: {"name", "n_cells", "n_transistors", "base_width_um",
                  "width_um"} -- targets from the .Astranlog Cell Size
    line; cells without a usable layout are skipped (0 x 0 included).
    """
    samples = []
    for outDir in outputDirs:
        for spPath in sorted(glob.glob(os.path.join(outDir,
                                                    "COMPLEX*.sp"))):
            name = os.path.splitext(os.path.basename(spPath))[0]
            logPath = os.path.join(outDir, name + ".Astranlog")
            if (not os.path.exists(logPath)):
                continue
            width = None
            for line in open(logPath, 'r', errors="ignore"):
                if (line.find("-> Cell Size (W x H): ") >= 0):
                    width = float(line.replace(
                        "-> Cell Size (W x H): ", "").split("x")[0])
            if (not width or width <= 0):
                continue
            text = open(spPath).read()
            traceM = re.search(r"^\* pattern code: (.+)$", text, re.M)
            if (not traceM):
                continue
            types = parseTraceTypes(traceM.group(1).strip())
            if (not types or any(t not in stdType2Width
                                 for t in types)):
                continue
            nTrans = sum(transistorCounts.get(t, 0) for t in types)
            if (nTrans == 0):
                continue
            samples.append({
                "name": name,
                "n_cells": len(types),
                "n_transistors": nTrans,
                "base_width_um": sum(stdType2Width[t] for t in types),
                "width_um": width,
            })
    return samples


def _features(sample):
    return [sample["n_cells"], sample["n_transistors"],
            sample["base_width_um"]]


class WidthProxy(object):
    """Ridge regression on (n_cells, n_transistors, base_width)."""

    def __init__(self):
        self.model = None
        self.nTrain = 0

    def fit(self, samples):
        from sklearn.linear_model import Ridge
        X = [_features(s) for s in samples]
        y = [s["width_um"] for s in samples]
        self.model = Ridge(alpha=1.0)
        self.model.fit(X, y)
        self.nTrain = len(samples)
        return self

    def predict(self, nCells, nTransistors, baseWidthUm):
        if (self.model is None):
            raise RuntimeError("WidthProxy used before fit()")
        return float(self.model.predict(
            [[nCells, nTransistors, baseWidthUm]])[0])


def evaluateLOO(samples):
    """Leave-one-out cross-validation; honest quality report."""
    if (len(samples) < 4):
        return {"n": len(samples), "mape": None, "r2": None}
    preds = []
    trues = []
    for i in range(len(samples)):
        train = samples[:i] + samples[i + 1:]
        proxy = WidthProxy().fit(train)
        preds.append(proxy.predict(*_features(samples[i])))
        trues.append(samples[i]["width_um"])
    errs = [abs(p - t) / t for p, t in zip(preds, trues) if t > 0]
    mape = sum(errs) / len(errs) if errs else None
    meanY = sum(trues) / len(trues)
    ssRes = sum((p - t) ** 2 for p, t in zip(preds, trues))
    ssTot = sum((t - meanY) ** 2 for t in trues)
    r2 = 1.0 - ssRes / ssTot if ssTot > 0 else None
    return {"n": len(samples), "mape": mape, "r2": r2,
            "predictions": list(zip(
                [s["name"] for s in samples], preds, trues))}


def makeProxyBenefitEstimator(proxy, stdType2Width, transistorCounts):
    """Growth-benefit estimator backed by the proxy (same signature as
    benefit.makeGrowthBenefitEstimator's closure)."""
    def estimate(memberTypeNames, neighborTypeName, newSize, occurrences):
        types = list(memberTypeNames) + [neighborTypeName]
        if (any(t not in stdType2Width for t in types)):
            return float("inf")          # unknown width -> no opinion
        baseWidth = sum(stdType2Width[t] for t in types)
        nTrans = sum(transistorCounts.get(t, 0) for t in types)
        predicted = proxy.predict(len(types), nTrans, baseWidth)
        return occurrences * (baseWidth - predicted)
    return estimate


# ---------------------------------------------------------------------------
# training pipeline: train -> persist -> load (performance layer)
# ---------------------------------------------------------------------------

def saveWidthProxy(proxy, path):
    """Persist a trained WidthProxy (Ridge) as JSON (coef + intercept)."""
    import json as _json
    os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
    payload = {
        "coef": [float(c) for c in proxy.model.coef_],
        "intercept": float(proxy.model.intercept_),
        "n_train": proxy.nTrain,
    }
    with open(path, "w") as fh:
        _json.dump(payload, fh)
    return path


def loadWidthProxy(path):
    """Restore a WidthProxy previously saved by saveWidthProxy."""
    import json as _json
    from sklearn.linear_model import Ridge
    with open(path) as fh:
        payload = _json.load(fh)
    import numpy as _np
    proxy = WidthProxy()
    proxy.model = Ridge(alpha=1.0)
    proxy.model.coef_ = _np.array([float(c) for c in payload["coef"]])
    proxy.model.intercept_ = payload["intercept"]
    proxy.model.n_features_in_ = len(payload["coef"])
    proxy.nTrain = payload["n_train"]
    return proxy


def widthProxyModelStale(path, outputDirs):
    """Whether the persisted model is older than any training sample
    (new layouts invalidate the learned shrink behaviour)."""
    if (not os.path.exists(path)):
        return True
    modelMtime = os.path.getmtime(path)
    newest = 0.0
    for outDir in outputDirs:
        for pat in ("COMPLEX*.sp", "COMPLEX*.Astranlog"):
            for f in glob.glob(os.path.join(outDir, pat)):
                newest = max(newest, os.path.getmtime(f))
    return newest > modelMtime


def trainOrLoadWidthProxy(outputDirs, transistorCounts, stdType2Width,
                          path=None):
    """Training-pipeline entry: (proxy, report).

    Loads the persisted model when it is fresh, otherwise retrains from
    the layout corpus, persists, and reports LOO quality.  Returns
    (None, report) when the corpus is too small to train.
    """
    if (path is None):
        path = os.path.join("outputs", "width_proxy.json")
    if (not widthProxyModelStale(path, outputDirs)):
        try:
            proxy = loadWidthProxy(path)
            return proxy, {"n": proxy.nTrain, "source": "loaded"}
        except Exception:                       # noqa: BLE001
            pass                                # corrupt model -> retrain
    samples = collectSamples(outputDirs, transistorCounts, stdType2Width)
    if (len(samples) < 4):
        return None, {"n": len(samples), "skipped": "too few samples"}
    proxy = WidthProxy().fit(samples)
    report = evaluateLOO(samples)
    report["source"] = "trained"
    try:
        saveWidthProxy(proxy, path)
    except Exception as exc:                    # noqa: BLE001
        report["save_error"] = str(exc)
    return proxy, report
