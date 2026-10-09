"""Visual identity: colours, QSS stylesheet and the GSCL45 layer table.

The layer numbers follow the project's calibrated stream map (metal1=49,
via1=50, metal2=51, ... while the base layers keep Cadence numbering:
active=1, poly=9, contact=10).  Keeping this table in one place means the
layout viewer, the layer legend and any exported image agree.
"""

# --- palette ---------------------------------------------------------------
BG = "#0f1319"
BG_ALT = "#151a22"
PANEL = "#1a212b"
PANEL_HI = "#212a36"
BORDER = "#2b3542"
TEXT = "#e6edf3"
TEXT_DIM = "#93a1b1"
TEXT_FAINT = "#6b7785"
ACCENT = "#4c8dff"
ACCENT_DIM = "#2f5fa8"
OK = "#3fb950"
WARN = "#d29922"
ERROR = "#f85149"
INFO = "#39c5cf"
RUN = "#8b7bf0"

# Cadence/stream layer table for the FreePDK45 (GSCL45) map.  ``layer`` is the
# GDS layer number, ``dt`` the datatype.  Colour is chosen so that the draw
# order (wells -> implants -> active -> poly -> contacts -> metals -> boundary)
# reads like a real layout editor.
LAYERS = [
    # (layer, datatype, name, purpose, colour, draw_order, visible_by_default)
    (3, 0, "nwell", "drawing", "#6d5c55", 10, True),
    (2, 0, "pwell", "drawing", "#7d6b60", 11, True),
    (4, 0, "nimplant", "drawing", "#c9b458", 20, False),
    (5, 0, "pimplant", "drawing", "#c98a3a", 21, False),
    (1, 0, "active", "drawing", "#3fa34d", 30, True),
    (9, 0, "poly", "drawing", "#d64545", 40, True),
    (10, 0, "contact", "drawing", "#b8b8b8", 50, True),
    (49, 0, "metal1", "drawing", "#3f8fd8", 60, True),
    (50, 0, "via1", "drawing", "#8fa6b8", 61, True),
    (51, 0, "metal2", "drawing", "#d05c9c", 70, True),
    (61, 0, "via2", "drawing", "#a08fb8", 71, True),
    (62, 0, "metal3", "drawing", "#4fc27a", 80, True),
    (30, 0, "via3", "drawing", "#8fb8a6", 81, True),
    (31, 0, "metal4", "drawing", "#5b6fd0", 90, True),
    (32, 0, "via4", "drawing", "#8fa0d8", 91, True),
    (33, 0, "metal5", "drawing", "#8a5bd0", 100, True),
    (235, 0, "pr_boundary", "drawing", "#e0b341", 5, True),
]

_LAYER_BY_KEY = {(l, d): (name, purpose, colour, order, vis)
                 for (l, d, name, purpose, colour, order, vis) in LAYERS}

UNKNOWN_LAYER_COLOUR = "#7a8794"

# Deterministic colours for layers of a *custom* PDK (streams not in the
# GSCL45 table): picked by hashing the layer name so the same PDK always
# gets the same palette.
FALLBACK_PALETTE = [
    "#e08f5b", "#7fc97f", "#beaed4", "#fdc086", "#ffff99", "#386cb0",
    "#f0027f", "#bf5b17", "#1b9e77", "#d95f02", "#7570b3", "#66a61e",
]


def fallback_colour(name):
    h = 0
    for ch in str(name):
        h = (h * 31 + ord(ch)) & 0xFFFF
    return FALLBACK_PALETTE[h % len(FALLBACK_PALETTE)]


def has_layer(layer, datatype=0):
    return (layer, datatype) in _LAYER_BY_KEY


def layer_info(layer, datatype=0):
    """(name, purpose, colour, draw_order, visible) for a GDS layer/datatype."""
    hit = _LAYER_BY_KEY.get((layer, datatype))
    if hit:
        return hit
    # Unknown datatype on a known layer (e.g. a pin on 49/0 recorded as 49/0).
    for (l, d), val in _LAYER_BY_KEY.items():
        if l == layer:
            return val
    return ("layer%d" % layer, "?", UNKNOWN_LAYER_COLOUR, 200, True)


def layer_colour(layer, datatype=0):
    return layer_info(layer, datatype)[2]


# Cadence-style metal ramp, used by the charts and the "metal only" preset.
METAL_COLOURS = {49: "#3f8fd8", 51: "#d05c9c", 62: "#4fc27a",
                 31: "#5b6fd0", 33: "#8a5bd0"}


STYLESHEET = """
QWidget {{
    background: {BG};
    color: {TEXT};
    font-family: "Segoe UI", "Microsoft YaHei UI", "Noto Sans CJK SC", sans-serif;
    font-size: 13px;
}}
QMainWindow, QDialog {{ background: {BG}; }}

QToolTip {{
    background: {PANEL_HI}; color: {TEXT};
    border: 1px solid {BORDER}; padding: 4px 6px;
}}

/* ---- left navigation ---- */
QListWidget#Nav {{
    background: {BG_ALT}; border: none; outline: none;
    padding: 6px 0;
}}
QListWidget#Nav::item {{
    padding: 11px 16px; margin: 1px 8px; border-radius: 7px;
    color: {TEXT_DIM};
}}
QListWidget#Nav::item:hover {{ background: {PANEL}; color: {TEXT}; }}
QListWidget#Nav::item:selected {{
    background: {ACCENT_DIM}; color: #ffffff;
    border: 1px solid {ACCENT};
}}

/* ---- text widgets ---- */
QLabel {{ background: transparent; }}
QLabel#H1 {{ font-size: 20px; font-weight: 600; }}
QLabel#H2 {{ font-size: 15px; font-weight: 600; color: {TEXT}; }}
QLabel#Subtle {{ color: {TEXT_DIM}; }}
QLabel#Faint {{ color: {TEXT_FAINT}; font-size: 12px; }}
QLabel#Badge {{
    background: {PANEL_HI}; border: 1px solid {BORDER}; border-radius: 5px;
    padding: 2px 7px; color: {TEXT_DIM}; font-size: 11px;
}}

QPlainTextEdit, QTextEdit {{
    background: #0b0f14; border: 1px solid {BORDER}; border-radius: 7px;
    selection-background-color: {ACCENT_DIM};
    font-family: "Cascadia Mono", "Consolas", monospace; font-size: 12px;
}}
QLineEdit {{
    background: {PANEL}; border: 1px solid {BORDER}; border-radius: 6px;
    padding: 4px 8px; min-height: 1.9em;
    selection-background-color: {ACCENT_DIM};
}}
QLineEdit:focus {{ border: 1px solid {ACCENT}; }}

/* ---- buttons ---- */
QPushButton {{
    background: {PANEL_HI}; border: 1px solid {BORDER}; border-radius: 6px;
    padding: 6px 14px; min-height: 1.6em; color: {TEXT};
}}
QPushButton:hover {{ background: #2a3644; border-color: #3b4859; }}
QPushButton:pressed {{ background: #1c2530; }}
QPushButton:disabled {{ color: {TEXT_FAINT}; background: {PANEL}; }}
QPushButton#Primary {{
    background: {ACCENT}; border-color: {ACCENT}; color: #ffffff;
    font-weight: 600;
}}
QPushButton#Primary:hover {{ background: #5b98ff; }}
QPushButton#Primary:disabled {{ background: {ACCENT_DIM}; border-color: {ACCENT_DIM};
    color: #c7d6ee; }}
QPushButton#Danger {{ background: #3a1f22; border-color: #6b2b31; color: #ffb4b4; }}
QPushButton#Danger:hover {{ background: #4a2529; }}
QPushButton#Primary:disabled, QPushButton#Danger:disabled {{
    background: {PANEL}; color: {TEXT_FAINT}; border-color: {BORDER};
}}

/* ---- inputs ---- */
QComboBox, QSpinBox, QDoubleSpinBox {{
    background: {PANEL}; border: 1px solid {BORDER}; border-radius: 6px;
    padding: 4px 8px; min-height: 1.9em;
}}
QComboBox:hover, QSpinBox:hover, QDoubleSpinBox:hover {{ border-color: #3b4859; }}
QComboBox:focus, QSpinBox:focus, QDoubleSpinBox:focus {{ border-color: {ACCENT}; }}
QComboBox QAbstractItemView {{
    background: {PANEL_HI}; border: 1px solid {BORDER};
    selection-background-color: {ACCENT_DIM}; outline: none;
}}
QCheckBox, QRadioButton {{ spacing: 7px; background: transparent; }}
QCheckBox::indicator, QRadioButton::indicator {{
    width: 15px; height: 15px; border: 1px solid {BORDER};
    border-radius: 4px; background: {PANEL};
}}
QCheckBox::indicator:checked, QRadioButton::indicator:checked {{
    background: {ACCENT}; border-color: {ACCENT};
}}
QSlider::groove:horizontal {{
    height: 4px; background: {BORDER}; border-radius: 2px;
}}
QSlider::handle:horizontal {{
    background: {ACCENT}; width: 13px; margin: -5px 0; border-radius: 6px;
}}

/* ---- containers ---- */
QGroupBox {{
    border: 1px solid {BORDER}; border-radius: 9px; margin-top: 14px;
    padding: 12px 12px 10px 12px; background: {PANEL};
}}
QGroupBox::title {{
    subcontrol-origin: margin; left: 12px; padding: 0 5px;
    color: {TEXT_DIM}; font-weight: 600;
}}
QFrame#Card {{
    background: {PANEL}; border: 1px solid {BORDER}; border-radius: 9px;
}}
QFrame#HLine {{ background: {BORDER}; max-height: 1px; border: none; }}

/* ---- tables / lists / trees ---- */
QTableWidget, QTableView, QTreeWidget, QTreeView, QListWidget {{
    background: {BG_ALT}; border: 1px solid {BORDER}; border-radius: 8px;
    alternate-background-color: #131922; gridline-color: {BORDER};
    selection-background-color: {ACCENT_DIM}; selection-color: #ffffff;
    outline: none;
}}
QHeaderView::section {{
    background: {PANEL}; color: {TEXT_DIM}; padding: 6px 8px; border: none;
    border-right: 1px solid {BORDER}; border-bottom: 1px solid {BORDER};
    font-weight: 600;
}}
QTableWidget::item {{ padding: 4px 6px; }}

/* ---- progress ---- */
QProgressBar {{
    background: {BG_ALT}; border: 1px solid {BORDER}; border-radius: 6px;
    text-align: center; color: {TEXT_DIM}; min-height: 1.5em;
}}
QProgressBar::chunk {{ background: {ACCENT}; border-radius: 5px; }}
QProgressBar#Stage::chunk {{ background: {RUN}; }}

/* ---- scrollbars ---- */
QScrollBar:vertical {{ background: transparent; width: 11px; margin: 0; }}
QScrollBar::handle:vertical {{
    background: #33404f; border-radius: 5px; min-height: 26px;
}}
QScrollBar::handle:vertical:hover {{ background: #405063; }}
QScrollBar:horizontal {{ background: transparent; height: 11px; }}
QScrollBar::handle:horizontal {{
    background: #33404f; border-radius: 5px; min-width: 26px;
}}
QScrollBar::add-line, QScrollBar::sub-line {{ height: 0; width: 0; }}
QScrollBar::add-page, QScrollBar::sub-page {{ background: transparent; }}

/* ---- tabs / splitter / dock ---- */
QTabWidget::pane {{ border: 1px solid {BORDER}; border-radius: 8px; top: -1px; }}
QTabBar::tab {{
    background: transparent; color: {TEXT_DIM}; padding: 7px 14px;
    border: 1px solid transparent; border-top-left-radius: 7px;
    border-top-right-radius: 7px;
}}
QTabBar::tab:selected {{ background: {PANEL}; color: {TEXT}; border-color: {BORDER}; }}
QSplitter::handle {{ background: {BORDER}; }}
QSplitter::handle:hover {{ background: {ACCENT_DIM}; }}

QDockWidget {{ titlebar-close-icon: none; }}
QDockWidget::title {{
    background: {PANEL}; padding: 6px 10px; border-bottom: 1px solid {BORDER};
    color: {TEXT_DIM}; font-weight: 600;
}}
QStatusBar {{ background: {BG_ALT}; border-top: 1px solid {BORDER}; color: {TEXT_DIM}; }}
QStatusBar::item {{ border: none; }}

QMenuBar {{ background: {BG_ALT}; border-bottom: 1px solid {BORDER}; }}
QMenuBar::item {{ padding: 6px 11px; background: transparent; }}
QMenuBar::item:selected {{ background: {PANEL}; }}
QMenu {{ background: {PANEL_HI}; border: 1px solid {BORDER}; padding: 4px; }}
QMenu::item {{ padding: 6px 22px; border-radius: 5px; }}
QMenu::item:selected {{ background: {ACCENT_DIM}; }}
QMenu::separator {{ height: 1px; background: {BORDER}; margin: 4px 8px; }}
""".format(**globals())


def status_colour(level):
    return {"ok": OK, "warn": WARN, "error": ERROR, "info": INFO,
            "run": RUN, "dim": TEXT_DIM}.get(level, TEXT_DIM)
