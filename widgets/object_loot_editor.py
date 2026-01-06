from __future__ import annotations
from typing import Any, Callable, Dict, Optional

from PyQt6 import QtWidgets


class ObjectLootEditor(QtWidgets.QWidget):
    """
    Editor for gameobject_loot_template (MyISAM) rows.

    Table:
      gameobject_loot_template(entry, item, ChanceOrQuestChance, lootmode, groupid, mincountOrRef, maxcount)
      PK(entry,item)

    Can be driven by a selected conditions row:
      entry = conditions.SourceGroup
      item  = conditions.SourceEntry
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

    def __init__(self, db, log: Callable[[str], None], parent=None):
        super().__init__(parent)
        self.db = db
        self.log = log

        self.inputs: Dict[str, QtWidgets.QLineEdit] = {}
        form = QtWidgets.QFormLayout()

        for col in self.LOOT_COLS:
            le = QtWidgets.QLineEdit()
            le.setPlaceholderText(col)
            self.inputs[col] = le
            form.addRow(col + ":", le)

        self.btn_load = QtWidgets.QPushButton("Load")
        self.btn_create = QtWidgets.QPushButton("Create (if missing)")
        self.btn_save = QtWidgets.QPushButton("Save (Upsert)")
        self.btn_clear = QtWidgets.QPushButton("Clear")

        self.btn_load.clicked.connect(self.load_current)
        self.btn_create.clicked.connect(self.create_if_missing)
        self.btn_save.clicked.connect(self.save)
        self.btn_clear.clicked.connect(self.clear)

        btns = QtWidgets.QHBoxLayout()
        btns.addWidget(self.btn_load)
        btns.addWidget(self.btn_create)
        btns.addStretch(1)
        btns.addWidget(self.btn_clear)
        btns.addWidget(self.btn_save)

        lay = QtWidgets.QVBoxLayout(self)
        lay.addLayout(form)
        lay.addSpacing(8)
        lay.addLayout(btns)
        lay.addStretch(1)

        # Default suggestions (good for quest items)
        self.inputs["ChanceOrQuestChance"].setText("-100")
        self.inputs["lootmode"].setText("1")
        self.inputs["groupid"].setText("0")
        self.inputs["mincountOrRef"].setText("1")
        self.inputs["maxcount"].setText("1")

    # ---- helpers ----
    def set_key(self, entry: int, item: int) -> None:
        self.inputs["entry"].setText(str(entry))
        self.inputs["item"].setText(str(item))

    def key(self) -> tuple[int, int]:
        entry = int(self.inputs["entry"].text().strip() or "0")
        item = int(self.inputs["item"].text().strip() or "0")
        return entry, item

    def clear(self) -> None:
        for c in self.LOOT_COLS:
            self.inputs[c].setText("")
        # re-apply defaults
        self.inputs["ChanceOrQuestChance"].setText("-100")
        self.inputs["lootmode"].setText("1")
        self.inputs["groupid"].setText("0")
        self.inputs["mincountOrRef"].setText("1")
        self.inputs["maxcount"].setText("1")

    def _values(self) -> Dict[str, Any]:
        entry, item = self.key()
        chance = float(self.inputs["ChanceOrQuestChance"].text().strip() or "0")
        lootmode = int(self.inputs["lootmode"].text().strip() or "1")
        groupid = int(self.inputs["groupid"].text().strip() or "0")
        minc = int(self.inputs["mincountOrRef"].text().strip() or "1")
        maxc = int(self.inputs["maxcount"].text().strip() or "1")
        return {
            "entry": entry,
            "item": item,
            "ChanceOrQuestChance": chance,
            "lootmode": lootmode,
            "groupid": groupid,
            "mincountOrRef": minc,
            "maxcount": maxc,
        }

    # ---- actions ----
    def load_current(self) -> None:
        entry, item = self.key()
        if entry <= 0 or item <= 0:
            QtWidgets.QMessageBox.information(self, "Missing key", "Set entry and item first.")
            return

        row = self.db.fetch_one(
            "SELECT entry,item,ChanceOrQuestChance,lootmode,groupid,mincountOrRef,maxcount "
            "FROM gameobject_loot_template WHERE entry=%s AND item=%s",
            (entry, item),
        )
        if not row:
            QtWidgets.QMessageBox.information(
                self, "Not found",
                "No gameobject_loot_template row exists for this (entry,item). "
                "Use Create (if missing)."
            )
            self.log(f"No object loot row found for entry={entry} item={item}")
            return

        for c in self.LOOT_COLS:
            self.inputs[c].setText("" if row.get(c) is None else str(row.get(c)))
        self.log(f"Loaded gameobject_loot_template entry={entry} item={item}")

    def create_if_missing(self) -> None:
        entry, item = self.key()
        if entry <= 0 or item <= 0:
            QtWidgets.QMessageBox.information(self, "Missing key", "Set entry and item first.")
            return

        exists = self.db.fetch_one(
            "SELECT entry FROM gameobject_loot_template WHERE entry=%s AND item=%s",
            (entry, item),
        )
        if exists:
            self.log("Object loot row already exists; loaded instead.")
            self.load_current()
            return

        v = self._values()
        try:
            self.db.execute(
                "INSERT INTO gameobject_loot_template "
                "(entry,item,ChanceOrQuestChance,lootmode,groupid,mincountOrRef,maxcount) "
                "VALUES (%s,%s,%s,%s,%s,%s,%s)",
                (v["entry"], v["item"], v["ChanceOrQuestChance"], v["lootmode"], v["groupid"], v["mincountOrRef"], v["maxcount"]),
            )
            self.db.commit()
            self.log(f"Created gameobject_loot_template entry={entry} item={item}")
            self.load_current()
        except Exception as e:
            self.db.rollback()
            QtWidgets.QMessageBox.critical(self, "Create failed", str(e))
            self.log(f"ERROR creating object loot row: {e}")

    def save(self) -> None:
        v = self._values()
        if v["entry"] <= 0 or v["item"] <= 0:
            QtWidgets.QMessageBox.information(self, "Missing key", "Set entry and item first.")
            return

        try:
            sql = """
            INSERT INTO gameobject_loot_template
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
            self.log(f"Saved gameobject_loot_template entry={v['entry']} item={v['item']}")
        except Exception as e:
            self.db.rollback()
            QtWidgets.QMessageBox.critical(self, "Save failed", str(e))
            self.log(f"ERROR saving object loot row: {e}")
