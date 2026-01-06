from __future__ import annotations
from typing import Callable, Optional

from PyQt6 import QtWidgets, QtCore
from PyQt6.QtCore import Qt

from db import Database


class QuestSearchPanel(QtWidgets.QWidget):
    quest_selected = QtCore.pyqtSignal(int)

    def __init__(self, db: Database, log: Callable[[str], None], parent=None):
        super().__init__(parent)
        self.db = db
        self.log = log

        self.edit = QtWidgets.QLineEdit()
        self.edit.setPlaceholderText("Search: quest entry or title substring…")
        self.btn = QtWidgets.QPushButton("Search")
        self.btn.clicked.connect(self.run_search)

        top = QtWidgets.QHBoxLayout()
        top.addWidget(self.edit, 1)
        top.addWidget(self.btn)

        self.table = QtWidgets.QTableWidget(0, 3)
        self.table.setHorizontalHeaderLabels(["entry", "Title", "MinLvl"])
        self.table.horizontalHeader().setStretchLastSection(True)
        self.table.setSelectionBehavior(QtWidgets.QAbstractItemView.SelectionBehavior.SelectRows)
        self.table.setEditTriggers(QtWidgets.QAbstractItemView.EditTrigger.NoEditTriggers)
        self.table.doubleClicked.connect(self._open_selected)

        lay = QtWidgets.QVBoxLayout(self)
        lay.addLayout(top)
        lay.addWidget(self.table, 1)

        self.edit.returnPressed.connect(self.run_search)

    def run_search(self) -> None:
        q = self.edit.text().strip()
        if not q:
            return

        # Prefer exact ID if numeric, else title search.
        rows = []
        try:
            qid = int(q)
            rows = self.db.fetch_all(
                "SELECT entry, Title, MinLevel FROM quest_template WHERE entry = %s LIMIT 200",
                (qid,),
            )
        except ValueError:
            like = f"%{q}%"
            rows = self.db.fetch_all(
                "SELECT entry, Title, MinLevel FROM quest_template WHERE Title LIKE %s ORDER BY entry DESC LIMIT 200",
                (like,),
            )

        self.table.setRowCount(0)
        for r in rows:
            row = self.table.rowCount()
            self.table.insertRow(row)
            self.table.setItem(row, 0, QtWidgets.QTableWidgetItem(str(r.get("entry",""))))
            self.table.setItem(row, 1, QtWidgets.QTableWidgetItem(str(r.get("Title",""))))
            self.table.setItem(row, 2, QtWidgets.QTableWidgetItem(str(r.get("MinLevel",""))))
        self.log(f"Search '{q}' → {len(rows)} result(s)")

    def _open_selected(self) -> None:
        row = self.table.currentRow()
        if row < 0:
            return
        try:
            qid = int(self.table.item(row, 0).text())
        except Exception:
            return
        self.quest_selected.emit(qid)
