"""Application entry point.

Run either way::

    python -m gui          # from the repo root
    python gui/app.py

matplotlib is pinned to the Agg backend *before* the flow's pyplot is ever
imported: the flow draws its COMPLEX<n>.png pattern figures with pyplot, and
Agg keeps those off the GUI's Qt backend and its event loop.
"""
import os
import sys


def main():
    # Make `python gui/app.py` work too: put the repo root on sys.path so the
    # `gui` package and the flow flow import the same way as `python -m gui`.
    repo = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    if repo not in sys.path:
        sys.path.insert(0, repo)

    import matplotlib
    matplotlib.use("Agg")

    from PySide6.QtCore import Qt
    from PySide6.QtGui import QIcon
    from PySide6.QtWidgets import QApplication

    from gui import theme
    from gui.main_window import MainWindow

    QApplication.setApplicationName("AutoCellLibX")
    QApplication.setOrganizationName("AutoCellLibX")
    QApplication.setApplicationDisplayName("AutoCellLibX · 标准单元扩展工作台")

    app = QApplication(sys.argv)
    app.setStyle("Fusion")
    app.setStyleSheet(theme.STYLESHEET)

    window = MainWindow()
    window.show()
    window.raise_()
    window.activateWindow()
    sys.exit(app.exec())


if __name__ == "__main__":
    main()
