from __future__ import annotations
from typing import Any, Callable, Dict, Optional

from PyQt6 import QtWidgets
from PyQt6.QtCore import Qt

from widgets.object_loot_editor import ObjectLootEditor

class QuestLootEditor(QtWidgets.QWidget):
    """
    A combined editor for:
      - conditions (MyISAM) rows tied to a quest: ConditionValue1 = quest_id
      - creature_loot_template (InnoDB) row tied to a conditions row:
            entry = SourceGroup
            item  = SourceEntry

    Because conditions is MyISAM, writes aren't truly transactional. We still:
      - validate inputs,
      - use parameterized SQL,
      - provide explicit save/delete actions.

    Schema assumptions are based on your SHOW CREATE TABLE output.
    """

    # EXACT column order from your conditions schema (including ErrorType)
    COND_COLS = [
        "SourceTypeOrReferenceId",
        "SourceGroup",
        "SourceEntry",
        "SourceId",
        "ElseGroup",
        "ConditionTypeOrReference",
        "ConditionTarget",
        "ConditionValue1",
        "ConditionValue2",
        "ConditionValue3",
        "NegativeCondition",
        "ErrorType",
        "ErrorTextId",
        "ScriptName",
        "Comment",
    ]
    
    # Display-only columns (NOT stored in DB)
    COND_DISPLAY_COLS = [
        "SourceGroupName",  # creature_template.name OR gameobject_template.name
        "ItemName",         # item_template.name
    ]

    # Composite primary key columns (from your PRIMARY KEY clause)
    COND_PK = [
        "SourceTypeOrReferenceId",
        "SourceGroup",
        "SourceEntry",
        "SourceId",
        "ElseGroup",
        "ConditionTypeOrReference",
        "ConditionTarget",
        "ConditionValue1",
        "ConditionValue2",
        "ConditionValue3",
        "NegativeCondition",
    ]

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
        self.quest_id: Optional[int] = None

        # --- Conditions table ---
        headers = self.COND_COLS + self.COND_DISPLAY_COLS
        self.cond_table = QtWidgets.QTableWidget(0, len(headers))
        self.cond_table.setHorizontalHeaderLabels(headers)
        # Make display columns read-only visually (still a normal table item, just disabled editing)
        self._display_col_start = len(self.COND_COLS)


        self.cond_table.horizontalHeader().setStretchLastSection(True)
        self.cond_table.setSelectionBehavior(QtWidgets.QAbstractItemView.SelectionBehavior.SelectRows)
        self.cond_table.setSelectionMode(QtWidgets.QAbstractItemView.SelectionMode.SingleSelection)
        self.cond_table.itemSelectionChanged.connect(self._on_condition_selected)

        self.btn_cond_reload = QtWidgets.QPushButton("Reload")
        self.btn_cond_add = QtWidgets.QPushButton("Add Condition Row")
        self.btn_cond_save = QtWidgets.QPushButton("Save Condition (Upsert)")
        self.btn_cond_delete = QtWidgets.QPushButton("Delete Condition")

        self.btn_cond_reload.clicked.connect(self.reload)
        self.btn_cond_add.clicked.connect(self.add_condition_row)
        self.btn_cond_save.clicked.connect(self.save_condition_selected)
        self.btn_cond_delete.clicked.connect(self.delete_condition_selected)

        cond_btns = QtWidgets.QHBoxLayout()
        cond_btns.addWidget(self.btn_cond_reload)
        cond_btns.addWidget(self.btn_cond_add)
        cond_btns.addWidget(self.btn_cond_delete)
        cond_btns.addStretch(1)
        cond_btns.addWidget(self.btn_cond_save)

        cond_box = QtWidgets.QVBoxLayout()
        cond_box.addLayout(cond_btns)
        cond_box.addWidget(self.cond_table, 1)

        cond_widget = QtWidgets.QWidget()
        cond_widget.setLayout(cond_box)

        # --- Creature loot editor (form) ---
        self.loot_form = QtWidgets.QFormLayout()
        self.loot_inputs: Dict[str, QtWidgets.QLineEdit] = {}

        for col in self.LOOT_COLS:
            le = QtWidgets.QLineEdit()
            le.setPlaceholderText(col)
            if col in ("entry", "item"):
                le.setEnabled(False)  # driven by selected condition row
            self.loot_inputs[col] = le
            self.loot_form.addRow(col + ":", le)

        self.btn_loot_load = QtWidgets.QPushButton("Load Loot For Selected Condition")
        self.btn_loot_new = QtWidgets.QPushButton("Create Loot Row (if missing)")
        self.btn_loot_save = QtWidgets.QPushButton("Save Loot Row")
        self.btn_loot_clear = QtWidgets.QPushButton("Clear Loot Form")

        self.btn_loot_load.clicked.connect(self.load_loot_for_selected_condition)
        self.btn_loot_new.clicked.connect(self.create_loot_row_if_missing)
        self.btn_loot_save.clicked.connect(self.save_loot)
        self.btn_loot_clear.clicked.connect(self.clear_loot_form)

        loot_btns = QtWidgets.QHBoxLayout()
        loot_btns.addWidget(self.btn_loot_load)
        loot_btns.addWidget(self.btn_loot_new)
        loot_btns.addStretch(1)
        loot_btns.addWidget(self.btn_loot_clear)
        loot_btns.addWidget(self.btn_loot_save)

        loot_wrap = QtWidgets.QVBoxLayout()
        loot_wrap.addLayout(self.loot_form)
        loot_wrap.addSpacing(8)
        loot_wrap.addLayout(loot_btns)
        loot_wrap.addStretch(1)

        loot_widget = QtWidgets.QWidget()
        loot_widget.setLayout(loot_wrap)
        
        # --- Object loot editor ---
        self.obj_loot = ObjectLootEditor(self.db, self.log)

        # --- Splitter: conditions grid (left) / loot form (right) ---
        split = QtWidgets.QSplitter()

        right_tabs = QtWidgets.QTabWidget()
        right_tabs.addTab(loot_widget, "Creature Loot")
        right_tabs.addTab(self.obj_loot, "Object Loot")

        split.addWidget(cond_widget)
        split.addWidget(right_tabs)
        split.setStretchFactor(0, 2)
        split.setStretchFactor(1, 1)
        split.setSizes([900, 500])

        main = QtWidgets.QVBoxLayout(self)
        main.addWidget(split, 1)

        self._last_loot_key: Optional[tuple[int, int]] = None  # (entry,item)

    # -------------------------
    # Public API used by app.py
    # -------------------------
    def load(self, quest_id: int) -> None:
        self.quest_id = quest_id
        self._load_conditions()
        self.clear_loot_form()
        self.log(f"Quest Loot Editor ready for quest {quest_id}")

    def reload(self) -> None:
        if self.quest_id is not None:
            self._load_conditions()
            self.clear_loot_form()

    # -------------------------
    # Conditions
    # -------------------------
    def _load_conditions(self) -> None:
        assert self.quest_id is not None
        cols = "c." + ",c.".join(self.COND_COLS)

        rows = self.db.fetch_all(
            f"""
            SELECT
              {cols},
              COALESCE(ct.name, gt.name, '') AS SourceGroupName,
              IFNULL(it.name, '')            AS ItemName
            FROM conditions c
            LEFT JOIN creature_template  ct ON ct.entry = c.SourceGroup
            LEFT JOIN gameobject_template gt ON gt.entry = c.SourceGroup
            LEFT JOIN item_template      it ON it.entry = c.SourceEntry
            WHERE c.ConditionValue1 = %s
            ORDER BY c.SourceGroup, c.SourceEntry, c.SourceId
            """,
            (self.quest_id,),
        )

        self.cond_table.setRowCount(0)
        for r in rows:
            self._append_condition_row(r)
        self.log(f"Loaded {len(rows)} condition row(s) for quest {self.quest_id}")

    def _append_condition_row(self, r: Dict[str, Any]) -> None:
        row = self.cond_table.rowCount()
        self.cond_table.insertRow(row)

        # Write DB columns first
        for i, col in enumerate(self.COND_COLS):
            val = r.get(col)
            self.cond_table.setItem(row, i, QtWidgets.QTableWidgetItem("" if val is None else str(val)))

        # Then display-only columns
        for j, col in enumerate(self.COND_DISPLAY_COLS):
            idx = len(self.COND_COLS) + j
            val = r.get(col, "")
            item = QtWidgets.QTableWidgetItem("" if val is None else str(val))
            item.setFlags(item.flags() & ~Qt.ItemFlag.ItemIsEditable)  # read-only
            self.cond_table.setItem(row, idx, item)


    def _cond_row_dict(self, row: int) -> Dict[str, Any]:
        d: Dict[str, Any] = {}
        for i, col in enumerate(self.COND_COLS):
            it = self.cond_table.item(row, i)
            txt = it.text().strip() if it else ""

            if col == "Comment":
                d[col] = None if txt == "" else txt
                continue
            if col == "ScriptName":
                d[col] = txt
                continue

            # numeric columns
            d[col] = int(txt) if txt != "" else 0
        return d

    def _selected_condition_row(self) -> int:
        return self.cond_table.currentRow()

    def add_condition_row(self) -> None:
        if self.quest_id is None:
            return
        r: Dict[str, Any] = {c: 0 for c in self.COND_COLS}
        r["ConditionValue1"] = self.quest_id
        r["SourceTypeOrReferenceId"] = 1
        r["ScriptName"] = ""
        r["Comment"] = ""
        self._append_condition_row(r)
        self.log("Added new condition row (defaults).")

    def save_condition_selected(self) -> None:
        if self.quest_id is None:
            return
        row = self._selected_condition_row()
        if row < 0:
            QtWidgets.QMessageBox.information(self, "Pick a row", "Select a condition row to save.")
            return

        d = self._cond_row_dict(row)
        d["ConditionValue1"] = self.quest_id  # keep tied to currently loaded quest

        insert_cols = ",".join([f"`{c}`" for c in self.COND_COLS])
        placeholders = ",".join(["%s"] * len(self.COND_COLS))

        non_pk = [c for c in self.COND_COLS if c not in self.COND_PK]
        updates = ",".join([f"`{c}`=VALUES(`{c}`)" for c in non_pk])

        sql = f"""
        INSERT INTO conditions ({insert_cols})
        VALUES ({placeholders})
        ON DUPLICATE KEY UPDATE {updates}
        """

        params = [d[c] for c in self.COND_COLS]

        try:
            self.db.execute(sql, params)
            self.db.commit()
            self.log(
                "Upserted condition row: "
                f"SG={d['SourceGroup']} SE={d['SourceEntry']} Q={d['ConditionValue1']}"
            )
        except Exception as e:
            self.db.rollback()
            QtWidgets.QMessageBox.critical(self, "Save failed", str(e))
            self.log(f"ERROR saving condition row: {e}")

    def delete_condition_selected(self) -> None:
        if self.quest_id is None:
            return
        row = self._selected_condition_row()
        if row < 0:
            return

        d = self._cond_row_dict(row)

        ok = QtWidgets.QMessageBox.question(
            self,
            "Confirm Delete",
            "Delete this condition row?\n\n"
            f"SG={d.get('SourceGroup')} SE={d.get('SourceEntry')} Q={d.get('ConditionValue1')}"
        )
        if ok != QtWidgets.QMessageBox.StandardButton.Yes:
            return

        where = " AND ".join([f"`{k}`=%s" for k in self.COND_PK])
        sql = f"DELETE FROM conditions WHERE {where}"
        params = [d.get(k, 0) for k in self.COND_PK]

        try:
            n = self.db.execute(sql, params)
            self.db.commit()
            self.cond_table.removeRow(row)
            self.log(f"Deleted {n} row(s) from conditions.")
            self.clear_loot_form()
        except Exception as e:
            self.db.rollback()
            QtWidgets.QMessageBox.critical(self, "Delete failed", str(e))
            self.log(f"ERROR deleting condition row: {e}")

    # -------------------------
    # Linking to creature_loot_template
    # -------------------------
    def _on_condition_selected(self) -> None:
        # Auto-load loot form on selection (nice UX)
        self.load_loot_for_selected_condition(auto=True)
        
        key = self._selected_loot_key()
        if key:
            entry, item = key
            self.obj_loot.set_key(entry, item)
            # Optional: auto-load on selection
            # self.obj_loot.load_current()
        else:
            self.obj_loot.clear()

    def _selected_loot_key(self) -> Optional[tuple[int, int]]:
        row = self._selected_condition_row()
        if row < 0:
            return None
        d = self._cond_row_dict(row)
        entry = int(d.get("SourceGroup", 0))
        item = int(d.get("SourceEntry", 0))
        if entry <= 0 or item <= 0:
            return None
        return (entry, item)

    def load_loot_for_selected_condition(self, auto: bool = False) -> None:
        key = self._selected_loot_key()
        if not key:
            if not auto:
                QtWidgets.QMessageBox.information(
                    self, "No loot key",
                    "Select a condition row with SourceGroup (entry) and SourceEntry (item) > 0."
                )
            self.clear_loot_form()
            return

        entry, item = key
        row = self.db.fetch_one(
            "SELECT " + ",".join(self.LOOT_COLS) +
            " FROM creature_loot_template WHERE entry=%s AND item=%s",
            (entry, item),
        )

        # Always set key fields in the form
        self.loot_inputs["entry"].setText(str(entry))
        self.loot_inputs["item"].setText(str(item))

        if not row:
            # No loot row yet
            if not auto:
                QtWidgets.QMessageBox.information(
                    self, "No loot row",
                    "No creature_loot_template row exists for this (entry,item). "
                    "Use 'Create Loot Row (if missing)'."
                )
            self._last_loot_key = key
            self._set_loot_defaults()
            self.log(f"No loot row found for entry={entry} item={item}")
            return

        # Populate existing loot row
        for c in self.LOOT_COLS:
            self.loot_inputs[c].setText("" if row.get(c) is None else str(row.get(c)))

        self._last_loot_key = key
        self.log(f"Loaded creature_loot_template entry={entry} item={item}")

    def _set_loot_defaults(self) -> None:
        # Default values are typical; adjust if your workflow differs
        if self.loot_inputs["ChanceOrQuestChance"].text().strip() == "":
            self.loot_inputs["ChanceOrQuestChance"].setText("-100")  # common quest-drop style
        if self.loot_inputs["lootmode"].text().strip() == "":
            self.loot_inputs["lootmode"].setText("1")
        if self.loot_inputs["groupid"].text().strip() == "":
            self.loot_inputs["groupid"].setText("0")
        if self.loot_inputs["mincountOrRef"].text().strip() == "":
            self.loot_inputs["mincountOrRef"].setText("1")
        if self.loot_inputs["maxcount"].text().strip() == "":
            self.loot_inputs["maxcount"].setText("1")

    def create_loot_row_if_missing(self) -> None:
        key = self._selected_loot_key()
        if not key:
            QtWidgets.QMessageBox.information(self, "No selection", "Select a condition row first.")
            return

        entry, item = key
        existing = self.db.fetch_one(
            "SELECT entry FROM creature_loot_template WHERE entry=%s AND item=%s",
            (entry, item),
        )
        if existing:
            self.log("Loot row already exists; loaded instead.")
            self.load_loot_for_selected_condition(auto=False)
            return

        # Create a row with defaults (you can change ChanceOrQuestChance default)
        chance = float(self.loot_inputs["ChanceOrQuestChance"].text().strip() or "-100")
        lootmode = int(self.loot_inputs["lootmode"].text().strip() or "1")
        groupid = int(self.loot_inputs["groupid"].text().strip() or "0")
        minc = int(self.loot_inputs["mincountOrRef"].text().strip() or "1")
        maxc = int(self.loot_inputs["maxcount"].text().strip() or "1")

        try:
            self.db.execute(
                "INSERT INTO creature_loot_template "
                "(entry,item,ChanceOrQuestChance,lootmode,groupid,mincountOrRef,maxcount) "
                "VALUES (%s,%s,%s,%s,%s,%s,%s)",
                (entry, item, chance, lootmode, groupid, minc, maxc),
            )
            self.db.commit()
            self.log(f"Created creature_loot_template row entry={entry} item={item}")
            self.load_loot_for_selected_condition(auto=False)
        except Exception as e:
            self.db.rollback()
            QtWidgets.QMessageBox.critical(self, "Create failed", str(e))
            self.log(f"ERROR creating loot row: {e}")

    def _loot_form_values(self) -> Dict[str, Any]:
        d: Dict[str, Any] = {}
        for c in self.LOOT_COLS:
            txt = self.loot_inputs[c].text().strip()
            if c in ("entry", "item", "lootmode", "groupid", "mincountOrRef", "maxcount"):
                d[c] = int(txt) if txt != "" else 0
            elif c == "ChanceOrQuestChance":
                d[c] = float(txt) if txt != "" else 0.0
            else:
                d[c] = txt
        return d

    def save_loot(self) -> None:
        vals = self._loot_form_values()
        entry = vals.get("entry", 0)
        item = vals.get("item", 0)
        if entry <= 0 or item <= 0:
            QtWidgets.QMessageBox.information(self, "No key", "Select a condition row first (SourceGroup/SourceEntry).")
            return

        try:
            # Upsert via PK (entry,item)
            sql = """
            INSERT INTO creature_loot_template
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
                entry, item,
                vals["ChanceOrQuestChance"],
                vals["lootmode"],
                vals["groupid"],
                vals["mincountOrRef"],
                vals["maxcount"],
            ))
            self.db.commit()
            self.log(f"Saved creature_loot_template entry={entry} item={item}")
        except Exception as e:
            self.db.rollback()
            QtWidgets.QMessageBox.critical(self, "Save failed", str(e))
            self.log(f"ERROR saving loot row: {e}")

    def clear_loot_form(self) -> None:
        for c in self.LOOT_COLS:
            self.loot_inputs[c].setText("")
        self._last_loot_key = None
