from __future__ import annotations
import json
import os
from pathlib import Path
from typing import Optional

from PyQt6 import QtWidgets, QtGui, QtCore

from db import DBConfig, Database
from widgets.search_panel import QuestSearchPanel
from widgets.quest_editor import QuestEditor
from widgets.loot_editor import QuestLootEditor


APP_TITLE = "EmuCoach Quest Editor (PyQt6)"


def apply_dark_theme(app: QtWidgets.QApplication) -> None:
    # A clean, professional dark theme (Fusion + palette).
    app.setStyle("Fusion")
    pal = QtGui.QPalette()
    pal.setColor(QtGui.QPalette.ColorRole.Window, QtGui.QColor(37, 37, 38))
    pal.setColor(QtGui.QPalette.ColorRole.WindowText, QtGui.QColor(220, 220, 220))
    pal.setColor(QtGui.QPalette.ColorRole.Base, QtGui.QColor(30, 30, 30))
    pal.setColor(QtGui.QPalette.ColorRole.AlternateBase, QtGui.QColor(45, 45, 45))
    pal.setColor(QtGui.QPalette.ColorRole.ToolTipBase, QtGui.QColor(255, 255, 220))
    pal.setColor(QtGui.QPalette.ColorRole.ToolTipText, QtGui.QColor(0, 0, 0))
    pal.setColor(QtGui.QPalette.ColorRole.Text, QtGui.QColor(220, 220, 220))
    pal.setColor(QtGui.QPalette.ColorRole.Button, QtGui.QColor(45, 45, 45))
    pal.setColor(QtGui.QPalette.ColorRole.ButtonText, QtGui.QColor(220, 220, 220))
    pal.setColor(QtGui.QPalette.ColorRole.BrightText, QtGui.QColor(255, 0, 0))
    pal.setColor(QtGui.QPalette.ColorRole.Link, QtGui.QColor(42, 130, 218))
    pal.setColor(QtGui.QPalette.ColorRole.Highlight, QtGui.QColor(42, 130, 218))
    pal.setColor(QtGui.QPalette.ColorRole.HighlightedText, QtGui.QColor(0, 0, 0))
    app.setPalette(pal)


class MainWindow(QtWidgets.QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle(APP_TITLE)
        self.resize(1400, 900)

        self.log_view = QtWidgets.QPlainTextEdit()
        self.log_view.setReadOnly(True)

        self.db = Database(self._load_config())
        self._connect_db_or_die()

        self.search = QuestSearchPanel(self.db, self.log)
        self.editor = QuestEditor(self.db, self.log)
        self.loot = QuestLootEditor(self.db, self.log)

        # Center: tabs (Quest editor + loot editor)
        center_tabs = QtWidgets.QTabWidget()
        center_tabs.addTab(self.editor, "Quest")
        center_tabs.addTab(self.loot, "Quest Loot (conditions)")
        center_tabs.setDocumentMode(True)

        # Split main area: left search / center tabs
        split = QtWidgets.QSplitter()
        split.setOrientation(QtCore.Qt.Orientation.Horizontal)
        split.addWidget(self.search)
        split.addWidget(center_tabs)
        split.setStretchFactor(0, 0)
        split.setStretchFactor(1, 1)
        split.setSizes([420, 980])

        self.setCentralWidget(split)

        # Bottom diagnostics dock
        dock = QtWidgets.QDockWidget("Diagnostics / Log", self)
        dock.setWidget(self.log_view)
        dock.setAllowedAreas(QtCore.Qt.DockWidgetArea.BottomDockWidgetArea)
        self.addDockWidget(QtCore.Qt.DockWidgetArea.BottomDockWidgetArea, dock)
        dock.setMinimumHeight(170)

        # Wire selection
        self.search.quest_selected.connect(self.open_quest)

        # Menu
        self._build_menu()

        self.log("Ready.")

    def _build_menu(self) -> None:
        m = self.menuBar()
        filem = m.addMenu("&File")

        act_cfg = QtGui.QAction("Open config.json", self)
        act_cfg.triggered.connect(self.open_config)
        filem.addAction(act_cfg)

        filem.addSeparator()
        act_quit = QtGui.QAction("Quit", self)
        act_quit.triggered.connect(self.close)
        filem.addAction(act_quit)

    def log(self, msg: str) -> None:
        self.log_view.appendPlainText(msg)

    def _config_path(self) -> Path:
        return Path(__file__).resolve().parent / "config.json"

    def _load_config(self) -> DBConfig:
        p = self._config_path()
        if not p.exists():
            # Create a default config if missing
            p.write_text(json.dumps({
                "host":"127.0.0.1",
                "port":3306,
                "user":"root",
                "password":"",
                "database":"world",
                "charset":"utf8mb4"
            }, indent=2), encoding="utf-8")

        data = json.loads(p.read_text(encoding="utf-8"))
        return DBConfig(**data)

    def open_config(self) -> None:
        QtGui.QDesktopServices.openUrl(QtCore.QUrl.fromLocalFile(str(self._config_path())))

    def _connect_db_or_die(self) -> None:
        try:
            self.db.connect()
        except Exception as e:
            QtWidgets.QMessageBox.critical(
                self,
                "DB Connection Failed",
                f"Could not connect to DB. Edit config.json and restart.\n\n{e}"
            )
            raise

    def open_quest(self, quest_id: int) -> None:
        self.editor.load(quest_id)
        self.loot.load(quest_id)


def main() -> None:
    app = QtWidgets.QApplication([])
    apply_dark_theme(app)
    w = MainWindow()
    w.show()
    app.exec()


if __name__ == "__main__":
    main()
