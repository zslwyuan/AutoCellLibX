"""Qt-free readers/writers for the PDK text files the GUI edits in place:
ASTRAN technology rules (``.rul``) and Cadence layer maps (``.map``).

Design goals:
* lossless round-trip -- every row keeps its original raw text, so comments,
  blank lines and whitespace survive an edit-untouched save;
* field explanations -- each parsed cell carries a Chinese+English
  explanation that the PDK editor shows next to the table;
* validation -- numeric cells must stay numeric before a file is written.
"""
import os
import re


# ---------------------------------------------------------------- decoding
# ASTRAN rule name notation: <prefix><class><layer>...  where
# S = spacing (间距), E = enclosure (包含/延伸), W = width (宽度),
# R = redundancy (冗余), A = area (面积).  Digits 1-3 are a rule class; two
# layer tokens mean a pair of layers.
RULE_PREFIX = {
    "S": "间距 spacing",
    "E": "包含/延伸 enclosure",
    "W": "宽度 width",
    "R": "冗余 redundancy",
    "A": "面积 area",
}

LAYER_TOKENS = {
    "P1": "poly 多晶硅", "P2": "poly2 第二层多晶硅",
    "DF": "diffusion 有源区", "CT": "contact 接触孔",
    "M1": "metal1", "M2": "metal2", "M3": "metal3", "M4": "metal4",
    "M5": "metal5", "M6": "metal6", "M7": "metal7", "M8": "metal8",
    "M9": "metal9", "M10": "metal10",
    "VI": "via1 过孔1", "V2": "via2", "V3": "via3", "V4": "via4", "V5": "via5",
    "V6": "via6", "V7": "via7", "V8": "via8", "V9": "via9", "V10": "via10",
    "DN": "nwell N阱", "DP": "pwell P阱", "NW": "nwell N阱", "PW": "pwell P阱",
    "IN": "N+注入 n+ implant", "IP": "P+注入 p+ implant",
    "ND": "N有源 n-diffusion", "PD": "P有源 p-diffusion",
    "CB": "单元边界 cell box", "IMP": "注入 implant",
}

RULE_GLOBALS = {
    "TECHNAME": ("工艺名 technology name",
                 "这个规则文件对应的工艺；ASTRAN 用于日志与校验。"),
    "MINSTEP": ("最小步长 minimum step (µm)",
                "所有坐标/尺寸的网格粒度；小于它的量会被吸附。"),
    "VDD": ("电源电压 supply voltage (V)",
            "逻辑电源电压，用于 ASTRAN 的电气参考。"),
    "MLAYERS": ("金属层数 metal layer count",
                "工艺支持的金属布线层总数。"),
}

PURPOSE_DESCRIPTIONS = {
    "NET": "信号走线 net routing",
    "SPNET": "特殊网络 special net",
    "PIN": "引脚 pin",
    "FILL": "填充 fill",
    "VIA": "过孔 via",
    "VIAFILL": "过孔填充 via fill",
    "DRAWING": "绘图 drawing",
}

NUMERIC_GLOBALS = {"MINSTEP", "VDD", "MLAYERS"}
INT_GLOBALS = {"MLAYERS"}
TEXT_GLOBALS = {"TECHNAME"}


def _split_tokens(text, tokens):
    """Greedy longest-match split of a rule name tail into layer tokens."""
    parts = []
    i = 0
    ordered = sorted(tokens, key=len, reverse=True)
    while i < len(text):
        for t in ordered:
            if text.startswith(t, i):
                parts.append(t)
                i += len(t)
                break
        else:
            parts.append(text[i])
            i += 1
    return parts


def decode_rule_name(name):
    """ASTRAN rule name -> (short, detailed) Chinese+English explanation."""
    if name in RULE_GLOBALS:
        return RULE_GLOBALS[name]
    m = re.match(r"^([SEWRA])(\d)(.+)$", name)
    if not m:
        return "未知规则 unknown rule", "规则名 %s 不在已知符号表中。" % name
    prefix, cls, rest = m.group(1), m.group(2), m.group(3)
    tokens = _split_tokens(rest, set(LAYER_TOKENS))
    labels = [LAYER_TOKENS.get(t, "%s(未知层)" % t) for t in tokens]
    rule = RULE_PREFIX.get(prefix, prefix)
    if len(tokens) >= 2:
        l1, l2 = labels[0], labels[1]
        if prefix == "S":
            short = "%s - %s 间距" % (tokens[0], tokens[1])
            detail = "第%s类间距规则：%s 与 %s 的最小距离（µm）。" % (cls, l1, l2)
        elif prefix == "E":
            short = "%s 包围 %s" % (tokens[0], tokens[1])
            detail = "第%s类包含规则：%s 相对 %s 的最小包含量（µm）。" % (cls, l1, l2)
        else:
            short = "%s/%s" % (tokens[0], tokens[1])
            detail = "第%s类%s规则：涉及 %s 与 %s（µm）。" % (cls, rule, l1, l2)
    else:
        short = tokens[0] if tokens else rest
        detail = "第%s类%s规则：作用于 %s（µm）。" % (cls, rule,
                                                "、".join(labels) or rest)
    return short, detail


def validate_number(text):
    t = str(text).strip()
    if t == "":
        raise ValueError("空值 empty value")
    return float(t)


def validate_int(text):
    t = str(text).strip()
    if t == "":
        raise ValueError("空值 empty value")
    return int(t)


# ------------------------------------------------------------ row model
class PdkRow(object):
    """One line of a PDK text file: raw text (lossless) + editable cells.

    ``cells`` is a list of (text, explanation, editable) aligned with the
    table columns the UI shows.  ``render()`` rebuilds ``raw`` from the cells.
    """

    __slots__ = ("raw", "kind", "cells", "error")

    def __init__(self, raw, kind, cells=None, error=None):
        self.raw = raw
        self.kind = kind          # comment | blank | rule | layer | row
        self.cells = cells or []
        self.error = error

    def __repr__(self):
        return "<PdkRow %s %r>" % (self.kind,
                                   self.cells[0][0] if self.cells else "")

    @property
    def name(self):
        return self.cells[0][0] if self.cells else ""


# ------------------------------------------------------------- .rul files
def parse_rul_file(path):
    """Parse an ASTRAN technology file into PdkRows (lossless)."""
    rows = []
    if not os.path.exists(path):
        return rows
    in_layers = False
    for raw in open(path, "r", errors="replace"):
        raw = raw.rstrip("\r\n")
        s = raw.strip()
        if not s:
            rows.append(PdkRow(raw, "blank"))
        elif s.startswith("*"):
            if "layers map" in s.lower():
                in_layers = True
            rows.append(PdkRow(raw, "comment"))
        elif in_layers:
            parts = s.split()
            if len(parts) >= 4:
                name, cif, gdsii, tech = parts[0], parts[1], parts[2], parts[3]
                rows.append(PdkRow(
                    raw, "layer", [
                        (name, "ASTRAN 内部层标识，供规则与版图代码引用", True),
                        (cif, "CIF 格式的层代码（本工具链主要用 GDSII 列）", True),
                        (gdsii, "GDSII 文件层号（stream number），必须为整数；"
                                "与版图查看器的层号对应", True),
                        (tech, "工艺层名（contact/poly/active/…），可读性参考", True),
                        ("层映射行", "把 ASTRAN 内部层名映射到 GDSII 流号", False),
                    ]))
            else:
                rows.append(PdkRow(raw, "comment", error="层表行格式不完整"))
        else:
            parts = s.split()
            if len(parts) >= 2:
                name, value = parts[0], " ".join(parts[1:])
                short, detail = decode_rule_name(name)
                if name in TEXT_GLOBALS:
                    unit, unit_expl = "", "文本值"
                elif name in INT_GLOBALS:
                    unit, unit_expl = "", "整数"
                elif name == "VDD":
                    unit, unit_expl = "V", "伏特"
                else:
                    unit, unit_expl = "µm", "微米"
                cells = [
                    (name, "ASTRAN 规则/参数名，按 S/E/W/R/A 记法命名", True),
                    (value, short + "。" + detail, True),
                    (unit, unit_expl + "；该规则值的单位", False),
                    (short, detail, False),
                ]
                try:
                    if name in INT_GLOBALS:
                        validate_int(value)
                    elif name in TEXT_GLOBALS:
                        pass
                    elif name in NUMERIC_GLOBALS:
                        validate_number(value)
                    else:
                        validate_number(value)
                except ValueError:
                    rows.append(PdkRow(raw, "rule", cells,
                                       error="数值非法 non-numeric"))
                    continue
                rows.append(PdkRow(raw, "rule", cells))
            else:
                rows.append(PdkRow(raw, "comment"))
    return rows


def render_rule_cells(name, value):
    """Rebuild a rule row's cells after the name/value columns were edited."""
    short, detail = decode_rule_name(name)
    if name in TEXT_GLOBALS:
        unit, unit_expl = "", "文本值"
    elif name in INT_GLOBALS:
        unit, unit_expl = "", "整数"
    elif name == "VDD":
        unit, unit_expl = "V", "伏特"
    else:
        unit, unit_expl = "µm", "微米"
    return [
        (name, "ASTRAN 规则/参数名，按 S/E/W/R/A 记法命名", True),
        (value, short + "。" + detail, True),
        (unit, unit_expl + "；该规则值的单位", False),
        (short, detail, False),
    ]


def render_rule_row(row, name, value):
    row.cells = render_rule_cells(name, value)
    row.raw = "%-10s %s" % (name, value)
    row.error = None


def render_layer_row(row, name, cif, gdsii, tech):
    row.cells = [
        (name, "ASTRAN 内部层标识，供规则与版图代码引用", True),
        (cif, "CIF 格式的层代码（本工具链主要用 GDSII 列）", True),
        (gdsii, "GDSII 文件层号（stream number），必须为整数；"
                "与版图查看器的层号对应", True),
        (tech, "工艺层名（contact/poly/active/…），可读性参考", True),
        ("层映射行", "把 ASTRAN 内部层名映射到 GDSII 流号", False),
    ]
    row.raw = "%-9s %-5s %-4s  %s" % (name, cif, gdsii, tech)
    row.error = None


def rul_to_text(rows):
    return "\n".join(r.raw for r in rows) + ("\n" if rows else "")


def rul_rules(rows):
    return [r for r in rows if r.kind == "rule"]


def rul_layers(rows):
    return [r for r in rows if r.kind == "layer"]


# ------------------------------------------------------------- .map files
def parse_map_file(path):
    """Parse a Cadence layer map into PdkRows (lossless)."""
    rows = []
    if not os.path.exists(path):
        return rows
    for raw in open(path, "r", errors="replace"):
        raw = raw.rstrip("\r\n")
        s = raw.strip()
        if not s:
            rows.append(PdkRow(raw, "blank"))
        elif s.startswith("#"):
            rows.append(PdkRow(raw, "comment"))
        else:
            parts = s.split()
            if len(parts) >= 4:
                name, purpose, stream, datatype = parts[0], parts[1], \
                    parts[2], parts[3]
                purpose_desc = PURPOSE_DESCRIPTIONS.get(
                    purpose, "用途 purpose：%s" % purpose)
                cells = [
                    (name, "GDS 层显示名称", True),
                    (purpose, purpose_desc + "；同名层可有多种用途"
                     "（如 metal1 的 NET/PIN/FILL），GDSII 中共享同一流号", True),
                    (stream, "GDSII 文件层号（stream number），必须为整数；"
                             "版图查看器按它着色与命名", True),
                    (datatype, "GDSII 数据类型（通常为 0），必须为整数", True),
                    ("映射行", "层名 + 用途 → GDSII 流号/数据类型", False),
                ]
                try:
                    validate_int(stream)
                    validate_int(datatype)
                except ValueError:
                    rows.append(PdkRow(raw, "row", cells,
                                       error="流号/数据类型必须为整数"))
                    continue
                rows.append(PdkRow(raw, "row", cells))
            else:
                rows.append(PdkRow(raw, "comment"))
    return rows


def render_map_row(row, name, purpose, stream, datatype):
    purpose_desc = PURPOSE_DESCRIPTIONS.get(
        purpose, "用途 purpose：%s" % purpose)
    row.cells = [
        (name, "GDS 层显示名称", True),
        (purpose, purpose_desc + "；同名层可有多种用途"
         "（如 metal1 的 NET/PIN/FILL），GDSII 中共享同一流号", True),
        (stream, "GDSII 文件层号（stream number），必须为整数；"
                 "版图查看器按它着色与命名", True),
        (datatype, "GDSII 数据类型（通常为 0），必须为整数", True),
        ("映射行", "层名 + 用途 → GDSII 流号/数据类型", False),
    ]
    row.raw = "%-10s\t%-10s\t%s\t%s" % (name, purpose, stream, datatype)
    row.error = None


def map_to_text(rows):
    return "\n".join(r.raw for r in rows) + ("\n" if rows else "")


def map_entries(rows):
    out = []
    for r in rows:
        if r.kind != "row":
            continue
        try:
            out.append((r.cells[0][0], r.cells[1][0],
                        int(r.cells[2][0]), int(r.cells[3][0])))
        except ValueError:
            continue
    return out


# ---------------------------------------------------------------- validation
def validate_rows(rows):
    """Return (ok, message): rule values numeric, layer/map streams integers."""
    for i, row in enumerate(rows):
        if row.error:
            return False, "第 %d 行：%s" % (i + 1, row.error)
        if row.kind == "rule":
            name = row.cells[0][0]
            if name in TEXT_GLOBALS:
                continue
            try:
                validate_number(row.cells[1][0])
            except ValueError:
                return False, "第 %d 行规则 %s 的值 %r 不是数值" % (
                    i + 1, name, row.cells[1][0])
        elif row.kind in ("layer", "row"):
            # GDSII stream column must be an int; maps also have a datatype col
            int_cols = (2, 3) if row.kind == "row" else (2,)
            for col in int_cols:
                try:
                    validate_int(row.cells[col][0])
                except ValueError:
                    return False, "第 %d 行 %r 列的值 %r 不是整数" % (
                        i + 1, row.cells[0][0], row.cells[col][0])
    return True, ""
