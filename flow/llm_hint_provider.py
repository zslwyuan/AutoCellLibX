"""Layout hint providers -- LLM-assisted optimisation resource (P2 stage 3).

The pipeline is deterministic and budgeted (ASTRAN ~5-10 min per cell), so
an LLM cannot sit in the hot loop; its value is *advice*: cheap, possibly
multimodal, human-readable layout hints computed before a cell costs an
ASTRAN run.  This module is the integration point for that resource:

- ``Hint`` -- one piece of advice (kind, target, value, source);
- ``OfflineHintProvider`` -- deterministic rule hints (wide transistors
  that must fold), no network, the default when no API key is set
  (AGENTS.md invariant 9: never let a nondeterministic call reach an
  output);
- ``OpenAiHintProvider`` -- multimodal LLM (text netlist + optional GDS
  screenshots -> JSON hints) behind the OpenAI-compatible chat API;
  *degrade, never crash*: any failure returns [] and logs, so a bad key,
  a timeout, or an unreachable endpoint leaves the flow untouched;
- ``suggest_hints_batch`` -- parallel batching over a thread pool plus a
  content-addressed response cache, the "resource integration speed-up":
  N cells are annotated concurrently and repeat runs hit the cache;
- ``get_hint_provider`` -- env-gated factory.  The pipeline consumes hints
  only when ``AUTOCELL_HINT_MODE`` is set (default ``off``: zero behaviour
  change, results byte-identical to a run without this module).

Env vars:
    AUTOCELL_HINT_MODE   off | offline | llm      (default off)
    AUTOCELL_LLM_API_KEY      API key (llm mode requires it)
    AUTOCELL_LLM_BASE_URL     OpenAI-compatible base URL (default OpenAI)
    AUTOCELL_LLM_MODEL        model name (default gpt-4o-mini)
    AUTOCELL_HINT_CACHE       cache file (default <temp>/autocell_hints.json)
    AUTOCELL_HINT_WORKERS     batch parallelism (default 4)
"""

import argparse
import dataclasses
import hashlib
import json
import os
import tempfile
import threading
from concurrent.futures import ThreadPoolExecutor

from core.log import get_flow_logger

_flowLog = get_flow_logger()

HINT_KINDS = ("fold_max", "row_order", "track_grid", "keepaway")
_FOLD_KIND = "fold_max"

_MODE_ENV = "AUTOCELL_HINT_MODE"
_KEY_ENV = "AUTOCELL_LLM_API_KEY"
_BASE_URL_ENV = "AUTOCELL_LLM_BASE_URL"
_MODEL_ENV = "AUTOCELL_LLM_MODEL"
_CACHE_ENV = "AUTOCELL_HINT_CACHE"
_WORKERS_ENV = "AUTOCELL_HINT_WORKERS"

DEFAULT_MODEL = "gpt-4o-mini"
DEFAULT_LLM_TIMEOUT_S = 60.0


@dataclasses.dataclass(frozen=True)
class Hint:
    kind: str
    target: str                 # device name / cell name
    value: float
    source: str                 # "offline" | "llm" | "cache"

    def as_dict(self):
        return {"kind": self.kind, "target": self.target,
                "value": self.value, "source": self.source}


def _cachePath(env=None):
    return env.get(_CACHE_ENV) if env else os.environ.get(_CACHE_ENV)
def default_cache_path():
    override = os.environ.get(_CACHE_ENV)
    if (override):
        return override
    return os.path.join(tempfile.gettempdir(), "autocell_hints.json")


def _loadCache(path):
    try:
        with open(path, 'r', encoding="utf-8") as f:
            data = json.load(f)
            return data if isinstance(data, dict) else {}
    except (OSError, ValueError):
        return {}


def _saveCache(path, cache):
    """Atomic write; a corrupt cache must never break the flow."""
    try:
        tmp = path + ".tmp"
        with open(tmp, 'w', encoding="utf-8") as f:
            json.dump(cache, f, sort_keys=True)
        os.replace(tmp, path)
    except OSError:
        pass


def hint_cache_key(netlist_text, geometry, model):
    """Content-addressed cache key: same inputs -> same hints."""
    canonical = json.dumps(
        {"netlist": netlist_text, "geometry": geometry, "model": model},
        sort_keys=True)
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


class OfflineHintProvider(object):
    """Deterministic rule hints; the fallback for every other provider.

    Rules today: a transistor wider than the fold threshold gets a
    ``fold_max`` hint (fold count = ceil(w / max_leg_um)), which is exactly
    the manufacturing constraint the SMT reference implementation models.
    Pure function of the netlist text -- deterministic and thread-safe.
    """

    def __init__(self, max_leg_um=1.0):
        self.max_leg_um = max_leg_um

    def suggest_hints(self, cell_name, netlist_text, geometry=None):
        hints = []
        for line in netlist_text.splitlines():
            # M<name> d g s b PMOS|NMOS W=<w>u
            parts = line.split()
            if (not parts or not parts[0].startswith("M")):
                continue
            w = None
            for tok in parts:
                if (tok.startswith("W=") and tok.endswith("u")):
                    w = float(tok[2:-1])
            if (w is None or w <= self.max_leg_um):
                continue
            folds = int(-(-w // self.max_leg_um))      # ceil
            if (folds > 1):
                hints.append(Hint(_FOLD_KIND, parts[0], folds, "offline"))
        return hints

    def close(self):
        pass


class OpenAiHintProvider(object):
    """Multimodal LLM hint provider (OpenAI-compatible chat API).

    ``image_paths`` are PNG screenshots of the cell (e.g. the GDS viewer
    render) sent as image_url parts -- the multimodal half.  Every failure
    (missing module, bad key, timeout, non-JSON answer, unknown hint kind)
    degrades to [] and is logged, so llm mode can never break a run.
    Responses are cached by content hash; cache hits skip the network.
    """

    def __init__(self, api_key, base_url=None, model=DEFAULT_MODEL,
                 image_paths=(), timeout_s=DEFAULT_LLM_TIMEOUT_S,
                 cache_path=None):
        self.api_key = api_key
        self.base_url = base_url
        self.model = model
        self.image_paths = tuple(image_paths)
        self.timeout_s = timeout_s
        self.cache_path = cache_path or default_cache_path()
        self._lock = threading.Lock()
        self._cache = _loadCache(self.cache_path)
        self._client = None

    def _lazyClient(self):
        if (self._client is None):
            import openai
            kwargs = {"api_key": self.api_key}
            if (self.base_url):
                kwargs["base_url"] = self.base_url
            self._client = openai.OpenAI(**kwargs)
        return self._client

    @staticmethod
    def _systemPrompt():
        return (
            "You advise a transistor-level standard-cell layout tool. "
            "Given a SPICE subcircuit (and optionally layout screenshots), "
            "reply with ONLY a JSON array of hints, each "
            '{"kind": ..., "target": ..., "value": ...} where kind is one '
            'of "fold_max" (target: M-name, value: max parallel legs), '
            '"row_order" (target: M-name, value: 0 or 1 = preferred P/N '
            'diffusion row), "track_grid" (target: cell name, value: um '
            'routing pitch), "keepaway" (target: pin net name, value: um '
            'clearance). If nothing useful, reply []. No prose.')

    def suggest_hints(self, cell_name, netlist_text, geometry=None):
        key = hint_cache_key(netlist_text, geometry, self.model)
        with self._lock:
            if (key in self._cache):
                cached = self._cache[key]
                return [Hint(h["kind"], h["target"], h["value"], "cache")
                        for h in cached]
        try:
            client = self._lazyClient()
            content = [{"type": "text",
                        "text": "cell=%s\ngeometry=%s\nnetlist:\n%s"
                                % (cell_name, json.dumps(geometry or {}),
                                   netlist_text)}]
            for img in self.image_paths:
                import base64
                with open(img, 'rb') as f:
                    b64 = base64.b64encode(f.read()).decode("ascii")
                content.append({"type": "image_url",
                                "image_url": {"url": "data:image/png;base64,"
                                              + b64}})
            resp = client.chat.completions.create(
                model=self.model,
                messages=[{"role": "system", "content": self._systemPrompt()},
                          {"role": "user", "content": content}],
                timeout=self.timeout_s)
            text = resp.choices[0].message.content or "[]"
            data = json.loads(text)
            hints = [Hint(h["kind"], str(h["target"]),
                          float(h["value"]), "llm")
                     for h in data
                     if isinstance(h, dict)
                     and h.get("kind") in HINT_KINDS
                     and h.get("target") is not None
                     and h.get("value") is not None]
            with self._lock:
                self._cache[key] = [
                    {"kind": h.kind, "target": h.target, "value": h.value}
                    for h in hints]
                _saveCache(self.cache_path, self._cache)
            return hints
        except Exception as exc:               # degrade, never crash
            _flowLog.warning("llm hints for %s failed (%s); degrading",
                             cell_name, exc)
            return []

    def close(self):
        pass


def get_hint_provider(mode=None, env=None):
    """Env-gated factory.  Returns None (off), OfflineHintProvider, or
    OpenAiHintProvider (falling back to offline when the key is missing).

    ``mode=None`` resolves AUTOCELL_HINT_MODE (default "off"), so a
    pipeline that calls this keeps the deterministic default.
    """
    env = os.environ if env is None else env
    if (mode is None):
        mode = env.get(_MODE_ENV, "off")
    mode = mode.strip().lower()
    if (mode == "off"):
        return None
    if (mode == "offline"):
        return OfflineHintProvider()
    if (mode == "llm"):
        key = env.get(_KEY_ENV)
        if (not key):
            _flowLog.warning("AUTOCELL_HINT_MODE=llm but no %s set; "
                             "degrading to the offline provider", _KEY_ENV)
            return OfflineHintProvider()
        return OpenAiHintProvider(
            api_key=key, base_url=env.get(_BASE_URL_ENV),
            model=env.get(_MODEL_ENV, DEFAULT_MODEL))
    _flowLog.warning("unknown AUTOCELL_HINT_MODE %r; treating as off", mode)
    return None


def suggest_hints_batch(cells, provider, max_workers=4):
    """Annotate many cells concurrently; {name: [Hint, ...]}.

    ``cells`` is an iterable of (name, netlist_text[, geometry]).  The
    offline provider is a pure function, the LLM provider is cache-first
    and degrades per cell, so parallelising is safe.  Results keep input
    order (deterministic).
    """
    if (provider is None):
        return {c[0]: [] for c in cells}

    def one(cell):
        name, text = cell[0], cell[1]
        geom = cell[2] if len(cell) > 2 else None
        return name, provider.suggest_hints(name, text, geom)

    with ThreadPoolExecutor(max_workers=max_workers) as pool:
        return {name: hints for name, hints in pool.map(one, list(cells))}


def main(argv=None):
    ap = argparse.ArgumentParser(
        description="Layout hint providers (LLM-assisted optimisation)")
    ap.add_argument("--mode", choices=("offline", "llm"),
                    help="provider mode (default: AUTOCELL_HINT_MODE)")
    ap.add_argument("--sp", help="one .sp file")
    ap.add_argument("--dir", help="directory of .sp files")
    ap.add_argument("--workers", type=int, default=4)
    args = ap.parse_args(argv)
    provider = get_hint_provider(mode=args.mode)
    sp_files = [args.sp] if args.sp else []
    if (args.dir):
        sp_files += sorted(os.path.join(args.dir, f) for f in
                          os.listdir(args.dir) if f.endswith(".sp"))
    if (not sp_files):
        ap.error("pass --sp FILE or --dir DIR")
    cells = []
    for sp in sp_files:
        with open(sp, 'r', errors="ignore") as f:
            cells.append((os.path.basename(sp).replace(".sp", ""),
                          f.read()))
    annotated = suggest_hints_batch(cells, provider,
                                  max_workers=args.workers)
    for name in sorted(annotated):
        hints = annotated[name]
        print("%-14s %d hint(s): %s" % (
            name, len(hints),
            ", ".join("%s %s=%.2f[%s]" % (h.kind, h.target, h.value, h.source)
                      for h in hints) or "none"))


if (__name__ == "__main__"):
    main()
