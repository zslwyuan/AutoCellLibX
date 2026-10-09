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
benefit.make_growth_benefit_estimator's closure):

    proxy = WidthProxy().fit(collect_samples(...))
    estimator = make_proxy_benefit_estimator(proxy, astran_area_by_type,
                                          transistor_counts)
"""

import glob
import os
import re

_SUBCKT_RE = re.compile(r"^\.subckt\s+(\S+)\s+(.*)$")
_TRACE_EXT_RE = re.compile(r"\+([A-Za-z0-9]+)_c\d+[io]\d+")
_TRANSISTOR_RE = re.compile(r"^M\S*\s", re.M)


def count_transistors_per_type(spice_lib_path):
    """{type_name: transistor count} from a SPICE subckt library."""
    counts = {}
    cur_name = None
    for line in open(spice_lib_path):
        if (line.startswith(".subckt")):
            m = _SUBCKT_RE.match(line.strip())
            cur_name = m.group(1) if m else None
            if (cur_name):
                counts.setdefault(cur_name, 0)
        elif (line.startswith(".ends")):
            cur_name = None
        elif (cur_name and _TRANSISTOR_RE.match(line)):
            counts[cur_name] += 1
    return counts


def parse_trace_types(trace):
    """Member type names of a pattern trace
    '[A,B,C]+D_c0o0+E_c1i0' -> ['A', 'B', 'C', 'D', 'E']."""
    base = trace.split("+")[0].strip("[]")
    types = [t for t in base.split(",") if t]
    types += _TRACE_EXT_RE.findall(trace)
    return types


def collect_samples(output_dirs, transistor_counts, width_by_type):
    """Build the dataset from generated cells.

    Each sample: {"name", "n_cells", "n_transistors", "base_width_um",
                  "width_um"} -- targets from the .Astranlog Cell Size
    line; cells without a usable layout are skipped (0 x 0 included).
    """
    samples = []
    for out_dir in output_dirs:
        for sp_path in sorted(glob.glob(os.path.join(out_dir,
                                                    "COMPLEX*.sp"))):
            name = os.path.splitext(os.path.basename(sp_path))[0]
            log_path = os.path.join(out_dir, name + ".Astranlog")
            if (not os.path.exists(log_path)):
                continue
            width = None
            for line in open(log_path, 'r', errors="ignore"):
                if (line.find("-> Cell Size (W x H): ") >= 0):
                    width = float(line.replace(
                        "-> Cell Size (W x H): ", "").split("x")[0])
            if (not width or width <= 0):
                continue
            text = open(sp_path).read()
            trace_m = re.search(r"^\* pattern code: (.+)$", text, re.M)
            if (not trace_m):
                continue
            types = parse_trace_types(trace_m.group(1).strip())
            if (not types or any(t not in width_by_type
                                 for t in types)):
                continue
            n_trans = sum(transistor_counts.get(t, 0) for t in types)
            if (n_trans == 0):
                continue
            samples.append({
                "name": name,
                "n_cells": len(types),
                "n_transistors": n_trans,
                "base_width_um": sum(width_by_type[t] for t in types),
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
        self.n_train = 0

    def fit(self, samples):
        from sklearn.linear_model import Ridge
        X = [_features(s) for s in samples]
        y = [s["width_um"] for s in samples]
        self.model = Ridge(alpha=1.0)
        self.model.fit(X, y)
        self.n_train = len(samples)
        return self

    def predict(self, n_cells, n_transistors, base_width_um):
        if (self.model is None):
            raise RuntimeError("WidthProxy used before fit()")
        return float(self.model.predict(
            [[n_cells, n_transistors, base_width_um]])[0])


def evaluate_loo(samples):
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
    mean_y = sum(trues) / len(trues)
    ss_res = sum((p - t) ** 2 for p, t in zip(preds, trues))
    ss_tot = sum((t - mean_y) ** 2 for t in trues)
    r2 = 1.0 - ss_res / ss_tot if ss_tot > 0 else None
    return {"n": len(samples), "mape": mape, "r2": r2,
            "predictions": list(zip(
                [s["name"] for s in samples], preds, trues))}


def make_proxy_benefit_estimator(proxy, width_by_type, transistor_counts):
    """Growth-benefit estimator backed by the proxy (same signature as
    benefit.make_growth_benefit_estimator's closure)."""
    def estimate(member_type_names, neighbor_type_name, new_size, occurrences):
        types = list(member_type_names) + [neighbor_type_name]
        if (any(t not in width_by_type for t in types)):
            return float("inf")          # unknown width -> no opinion
        base_width = sum(width_by_type[t] for t in types)
        n_trans = sum(transistor_counts.get(t, 0) for t in types)
        predicted = proxy.predict(len(types), n_trans, base_width)
        return occurrences * (base_width - predicted)
    return estimate


# ---------------------------------------------------------------------------
# training pipeline: train -> persist -> load (performance layer)
# ---------------------------------------------------------------------------

def save_width_proxy(proxy, path):
    """Persist a trained WidthProxy (Ridge) as JSON (coef + intercept)."""
    import json as _json
    os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
    payload = {
        "coef": [float(c) for c in proxy.model.coef_],
        "intercept": float(proxy.model.intercept_),
        "n_train": proxy.n_train,
    }
    with open(path, "w") as fh:
        _json.dump(payload, fh)
    return path


def load_width_proxy(path):
    """Restore a WidthProxy previously saved by save_width_proxy."""
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
    proxy.n_train = payload["n_train"]
    return proxy


def width_proxy_model_stale(path, output_dirs):
    """Whether the persisted model is older than any training sample
    (new layouts invalidate the learned shrink behaviour)."""
    if (not os.path.exists(path)):
        return True
    model_mtime = os.path.getmtime(path)
    newest = 0.0
    for out_dir in output_dirs:
        for pat in ("COMPLEX*.sp", "COMPLEX*.Astranlog"):
            for f in glob.glob(os.path.join(out_dir, pat)):
                newest = max(newest, os.path.getmtime(f))
    return newest > model_mtime


def train_or_load_width_proxy(output_dirs, transistor_counts, width_by_type,
                          path=None):
    """Training-pipeline entry: (proxy, report).

    Loads the persisted model when it is fresh, otherwise retrains from
    the layout corpus, persists, and reports LOO quality.  Returns
    (None, report) when the corpus is too small to train.
    """
    if (path is None):
        path = os.path.join("outputs", "width_proxy.json")
    if (not width_proxy_model_stale(path, output_dirs)):
        try:
            proxy = load_width_proxy(path)
            return proxy, {"n": proxy.n_train, "source": "loaded"}
        except Exception:                       # noqa: BLE001
            pass                                # corrupt model -> retrain
    samples = collect_samples(output_dirs, transistor_counts, width_by_type)
    if (len(samples) < 4):
        return None, {"n": len(samples), "skipped": "too few samples"}
    proxy = WidthProxy().fit(samples)
    report = evaluate_loo(samples)
    report["source"] = "trained"
    try:
        save_width_proxy(proxy, path)
    except Exception as exc:                    # noqa: BLE001
        report["save_error"] = str(exc)
    return proxy, report
