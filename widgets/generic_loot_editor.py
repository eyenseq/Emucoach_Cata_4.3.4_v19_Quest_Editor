from __future__ import annotations
from typing import Callable, Dict
from PyQt6 import QtWidgets


class GenericLootEditor(QtWidgets.QWidget):
    """
    Generic editor for TrinityCore-style *_loot_template tables with the common schema:
      (entry, item, ChanceOrQuestChance, lootmode, groupid, mincountOrRef, maxcount)
    """

    LOOT_COLS = [
        "entry",
        "item",
        "ChanceOrQuestChance",
        "lootmode",
        "groupid",
        "mincountOrRef",
        "maxcount",
    ]

    def __init__(self, db, log: Callable[[str], None], table_name: str, parent=None):
        super().__init__(parent)
        self.db = db
        self.log = log
        self.table_name = table_name

        self._entry = 0
        self._item = 0

        form = QtWidgets.QFormLayout()
        self.inputs: Dict[str, QtWidgets.QLineEdit] = {}

        for col in self.LOOT_COLS:
            le = QtWidgets.QLineEdit()
            le.setPlaceholderText(col)
            if col in ("entry", "item"):
                le.setEnabled(False)
            self.inputs[col] = le
            form.addRow(col + ":", le)

        btn_load = QtWidgets.QPushButton("Load")
        btn_new = QtWidgets.QPushButton("Create (if missing)")
        btn_save = QtWidgets.QPushButton("Save")
        btn_del = QtWidgets.QPushButton("Delete")
        btn_clr = QtWidgets.QPushButton("Clear")

        btn_load.clicked.connect(self.load_current)
        btn_new.clicked.connect(self.create_if_missing)
        btn_save.clicked.connect(self.save)
        btn_del.clicked.connect(self.delete)
        btn_clr.clicked.connect(self.clear)

        btns = QtWidgets.QHBoxLayout()
        btns.addWidget(btn_load)
        btns.addWidget(btn_new)
        btns.addStretch(1)
        btns.addWidget(btn_del)
        btns.addWidget(btn_clr)
        btns.addWidget(btn_save)

        wrap = QtWidgets.QVBoxLayout()
        wrap.addLayout(form)
        wrap.addSpacing(8)
        wrap.addLayout(btns)
        wrap.addStretch(1)
        self.setLayout(wrap)

    def set_key(self, entry: int, item: int) -> None:
        self._entry = int(entry or 0)
        self._item = int(item or 0)
        self.inputs["entry"].setText(str(self._entry))
        self.inputs["item"].setText(str(self._item))

    def clear(self) -> None:
        for c in self.LOOT_COLS:
            if c in ("entry", "item"):
                continue
            self.inputs[c].setText("")

    def _values(self) -> Dict[str, int]:
        out: Dict[str, int] = {}
        for c in self.LOOT_COLS:
            t = (self.inputs[c].text() or "").strip()
            try:
                out[c] = int(t) if t else 0
            except Exception:
                out[c] = 0
        return out

    def load_current(self) -> None:
        if self._entry <= 0 or self._item <= 0:
            QtWidgets.QMessageBox.information(self, "Missing key", "Select a condition row with SourceGroup/SourceEntry first.")
            return
        try:
            cols = ", ".join(self.LOOT_COLS)
            row = self.db.fetch_one(
                f"SELECT {cols} FROM {self.table_name} WHERE entry=%s AND item=%s",
                (self._entry, self._item),
            )
            if not row:
                QtWidgets.QMessageBox.information(
                    self, "No loot row",
                    f"No {self.table_name} row exists for this (entry,item).\n\nUse 'Create (if missing)' first."
                )
                self.clear()
                return

            for c in self.LOOT_COLS:
                self.inputs[c].setText(str(row.get(c, 0)))
            self.log(f"Loaded {self.table_name} entry={self._entry} item={self._item}")
        except Exception as e:
            QtWidgets.QMessageBox.critical(self, "Load failed", str(e))
            self.log(f"ERROR loading {self.table_name}: {e}")

    def create_if_missing(self) -> None:
        if self._entry <= 0 or self._item <= 0:
            QtWidgets.QMessageBox.information(self, "Missing key", "Select a condition row with SourceGroup/SourceEntry first.")
            return
        try:
            self.db.execute(
                f"INSERT IGNORE INTO {self.table_name} (entry,item,ChanceOrQuestChance,lootmode,groupid,mincountOrRef,maxcount) "
                "VALUES (%s,%s,0,0,0,0,0)",
                (self._entry, self._item),
            )
            self.db.commit()
            self.log(f"Ensured {self.table_name} row exists entry={self._entry} item={self._item}")
        except Exception as e:
            self.db.rollback()
            QtWidgets.QMessageBox.critical(self, "Create failed", str(e))
            self.log(f"ERROR creating {self.table_name} row: {e}")

    def save(self) -> None:
        v = self._values()
        if v["entry"] <= 0 or v["item"] <= 0:
            QtWidgets.QMessageBox.information(self, "Missing key", "Select a condition row with SourceGroup/SourceEntry first.")
            return
        try:
            sql = f"""
            INSERT INTO {self.table_name}
              (entry,item,ChanceOrQuestChance,lootmode,groupid,mincountOrRef,maxcount)
            VALUES (%s,%s,%s,%s,%s,%s,%s)
            ON DUPLICATE KEY UPDATE
              ChanceOrQuestChance=VALUES(ChanceOrQuestChance),
              lootmode=VALUES(lootmode),
              groupid=VALUES(groupid),
              mincountOrRef=VALUES(mincountOrRef),
              maxcount=VALUES(maxcount)
            """
            self.db.execute(sql, (
                v["entry"], v["item"],
                v["ChanceOrQuestChance"],
                v["lootmode"],
                v["groupid"],
                v["mincountOrRef"],
                v["maxcount"],
            ))
            self.db.commit()
            self.log(f"Saved {self.table_name} entry={v['entry']} item={v['item']}")
        except Exception as e:
            self.db.rollback()
            QtWidgets.QMessageBox.critical(self, "Save failed", str(e))
            self.log(f"ERROR saving {self.table_name} row: {e}")

    def delete(self) -> None:
        if self._entry <= 0 or self._item <= 0:
            QtWidgets.QMessageBox.information(self, "Missing key", "Select a condition row with SourceGroup/SourceEntry first.")
            return

        ok = QtWidgets.QMessageBox.question(
            self, "Confirm delete",
            f"Delete {self.table_name} row for entry={self._entry} item={self._item}?"
        )
        if ok != QtWidgets.QMessageBox.StandardButton.Yes:
            return

        try:
            self.db.execute(
                f"DELETE FROM {self.table_name} WHERE entry=%s AND item=%s",
                (self._entry, self._item),
            )
            self.db.commit()
            self.clear()
            self.log(f"Deleted {self.table_name} entry={self._entry} item={self._item}")
        except Exception as e:
            self.db.rollback()
            QtWidgets.QMessageBox.critical(self, "Delete failed", str(e))
            self.log(f"ERROR deleting {self.table_name}: {e}")
