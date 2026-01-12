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
    
    # ConditionTypeOrReference dropdown (TrinityCore-style labels you provided)
    COND_TYPE_CHOICES = [
        (1,  "AURA"),
        (2,  "ITEM"),
        (3,  "ITEM_EQUIPPED"),
        (4,  "ZONE"),
        (5,  "AREA"),
        (6,  "REPUTATION"),
        (7,  "TEAM"),
        (8,  "QUEST_REWARDED"),
        (9,  "QUEST_TAKEN"),
        (10, "QUEST_NONE"),
        (11, "LEVEL"),
        (12, "QUEST_AVAILABLE"),
        (13, "SPELL_IMPLICIT_TARGET"),
        (14, "CLASS"),
        (15, "RACE"),
        (16, "SKILL"),
        (17, "SPELL"),
        (18, "MAP"),
        (19, "NPC_ALIVE"),
        (20, "NPC_DEAD"),
        (21, "NPC_FLAG"),
        (22, "GAME_EVENT"),
        (23, "ACHIEVEMENT"),
        (24, "QUEST_COMPLETE"),
        (25, "QUEST_ACTIVE"),
    ]

    # These types typically want ConditionValue1 = quest_id 
    QUEST_TYPES_NEED_QUEST_ID = {8, 9, 10, 12, 24, 25}
    ANCHOR_COND_TYPE = 25

    # SourceTypeOrReferenceId dropdown (TrinityCore-style)
    SRC_TYPE_CHOICES = [
        (1,  "CREATURE_LOOT"),
        (2,  "DISENCHANT_LOOT"),
        (3,  "FISHING_LOOT"),
        (4,  "GAMEOBJECT_LOOT"),
        (5,  "ITEM_LOOT"),
        (6,  "MAIL_LOOT"),
        (7,  "REFERENCE_LOOT"),
        (8,  "SPELL"),
        (9,  "GOSSIP_MENU"),
        (10, "GOSSIP_MENU_OPTION"),
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
        
        # Remember tab widget + indices for routing
        self.right_tabs = right_tabs
        self.TAB_CREATURE = 0
        self.TAB_OBJECT = 1

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
    
    def sync_from_required_items(self, item_ids: list[int]) -> None:
        """
        Ensure the Conditions list has rows for the quest's required items.

        Behavior:
          - If the item already exists in creature_loot_template as a quest drop
            (ChanceOrQuestChance < 0), create missing anchored condition rows for each
            (entry,item) pair.
          - If no quest-drop loot rows exist for an item, create ONE placeholder condition
            row with SourceGroup=0, SourceEntry=item so the user can fill SourceGroup later.
        """
        if self.quest_id is None:
            return

        # Normalize + de-dupe
        items = sorted({int(x) for x in item_ids if str(x).strip().isdigit() and int(x) > 0})
        if not items:
            return

        try:
            # Existing anchored rows for this quest (keyed by SourceType/Group/Entry)
            existing = self.db.fetch_all(
                """
                SELECT SourceTypeOrReferenceId, SourceGroup, SourceEntry
                FROM conditions
                WHERE ConditionTypeOrReference = %s
                    AND ConditionValue1 = %s

                """,
                (self.ANCHOR_COND_TYPE, self.quest_id),
            )
            have_pairs = {
                (int(r["SourceTypeOrReferenceId"]), int(r["SourceGroup"]), int(r["SourceEntry"]))
                for r in existing
            }

            # Next SourceId allocator (composite PK needs uniqueness)
            row = self.db.fetch_one(
                """
                SELECT COALESCE(MAX(SourceId), 0) AS m
                FROM conditions
                WHERE ConditionTypeOrReference = %s
                  AND ConditionValue1 = %s
                """,
                (self.ANCHOR_COND_TYPE, self.quest_id),
            )
            next_source_id = int(row["m"] or 0) + 1

            # 1) Discover existing quest-drop sources in creature_loot_template
            #    (ChanceOrQuestChance < 0 usually means quest-required drop)
            placeholders_needed = set(items)
            found_pairs: list[tuple[int, int]] = []

            # Chunk to avoid huge IN lists
            CHUNK = 50
            for i in range(0, len(items), CHUNK):
                chunk = items[i : i + CHUNK]
                ph = ",".join(["%s"] * len(chunk))

                rows = self.db.fetch_all(
                    f"""
                    SELECT DISTINCT entry, item
                    FROM creature_loot_template
                    WHERE item IN ({ph})
                      AND ChanceOrQuestChance < 0
                    """,
                    tuple(chunk),
                )
                for r in rows:
                    e = int(r["entry"])
                    it = int(r["item"])
                    found_pairs.append((e, it))
                    if it in placeholders_needed:
                        placeholders_needed.discard(it)


            inserts: list[tuple] = []

            # Insert missing discovered (entry,item) rows
            for entry, item in found_pairs:
                key = (1, int(entry), int(item))  # SourceType=1 creature loot
                if key in have_pairs:
                    continue

                inserts.append(
                    (
                        1,                 # SourceTypeOrReferenceId (CreatureLoot)
                        int(entry),         # SourceGroup
                        int(item),          # SourceEntry
                        next_source_id,     # SourceId (unique)
                        0,                 # ElseGroup
                        self.ANCHOR_COND_TYPE,  # ConditionTypeOrReference (Quest Active) anchor
                        0,                 # ConditionTarget
                        int(self.quest_id), # ConditionValue1
                        0, 0,              # ConditionValue2/3
                        0,                 # NegativeCondition
                        0,                 # ErrorTextId
                        "",                # ScriptName
                        "",                # Comment
                    )
                )
                next_source_id += 1

            # 2) Add placeholder rows for items that had no quest-drop sources
            #    Only if there isn't already ANY anchor row with SourceEntry=item
            # DISABLED: never insert placeholder rows
            placeholders_needed = set()
            if False and placeholders_needed:
                existing_entries = self.db.fetch_all(
                    f"""
                    SELECT DISTINCT SourceEntry
                    FROM conditions
                    WHERE ConditionTypeOrReference = %s
                      AND ConditionValue1 = %s
                      AND SourceTypeOrReferenceId = 1
                      AND SourceEntry IN ({",".join(["%s"] * len(placeholders_needed))})
                    """,
                    (self.ANCHOR_COND_TYPE, self.quest_id, *sorted(placeholders_needed)),
                )
                have_sourceentry = {int(r["SourceEntry"]) for r in existing_entries}

                for item in sorted(placeholders_needed):
                    if item in have_sourceentry:
                        continue

                    inserts.append(
                        (
                            1,                 # SourceTypeOrReferenceId (CreatureLoot)
                            0,                 # SourceGroup (unknown yet)
                            int(item),          # SourceEntry
                            next_source_id,     # SourceId (unique)
                            0,                 # ElseGroup
                            self.ANCHOR_COND_TYPE,   # ConditionTypeOrReference (Quest Active) anchor
                            0,                 # ConditionTarget
                            int(self.quest_id), # ConditionValue1
                            0, 0,              # ConditionValue2/3
                            0,                 # NegativeCondition
                            0,                 # ErrorTextId
                            "",                # ScriptName
                            "AUTO: placeholder from ReqItemId",  # Comment
                        )
                    )
                    next_source_id += 1

            # Perform inserts if needed
            if inserts:
                self.db.executemany(
                    """
                    INSERT INTO conditions (
                        SourceTypeOrReferenceId, SourceGroup, SourceEntry, SourceId, ElseGroup,
                        ConditionTypeOrReference, ConditionTarget,
                        ConditionValue1, ConditionValue2, ConditionValue3,
                        NegativeCondition, ErrorTextId, ScriptName, Comment
                    )
                    VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)
                    """,
                    inserts,
                )
                self.db.commit()
                self.log(f"Quest Loot: added {len(inserts)} condition row(s) from required items.")
            else:
                # nothing new
                return

            # Refresh UI
            self._load_conditions()

        except Exception as e:
            try:
                self.db.rollback()
            except Exception:
                pass
            self.log(f"Quest Loot sync failed: {type(e).__name__}: {e}")

    # -------------------------
    # Conditions
    # -------------------------
    def _load_conditions(self) -> None:
        assert self.quest_id is not None
        cols = "c." + ",c.".join(self.COND_COLS)

        # 1) Find all condition "groups" (same source key) anchored by:
        #    ConditionType=2 (Player has quest) and ConditionValue1 = quest_id
        keys = self.db.fetch_all(
            """
            SELECT DISTINCT
              SourceTypeOrReferenceId, SourceGroup, SourceEntry, SourceId
            FROM conditions
            WHERE ConditionTypeOrReference = %s
                AND ConditionValue1 = %s

            """,
            (self.ANCHOR_COND_TYPE, self.quest_id),
        )

        # If there are no anchor rows, show nothing (correct) but log why
        if not keys:
            self.cond_table.setRowCount(0)
            self.log(f"Loaded 0 condition row(s) for quest {self.quest_id} (no ConditionType=25 anchor rows found).")
            return

        # 2) Load ALL condition rows for those keys (class/race/level/etc included)
        # Build a tuple-IN: (a,b,c,d) IN ((...),(...)...)
        placeholders = ",".join(["(%s,%s,%s,%s)"] * len(keys))
        params = []
        for k in keys:
            params.extend([
                int(k.get("SourceTypeOrReferenceId", 0)),
                int(k.get("SourceGroup", 0)),
                int(k.get("SourceEntry", 0)),
                int(k.get("SourceId", 0)),
            ])

        rows = self.db.fetch_all(
            f"""
            SELECT
              {cols},
              COALESCE(ct.name, gt.name, '') AS SourceGroupName,
              IFNULL(it.name, '')            AS ItemName
            FROM conditions c
            LEFT JOIN creature_template   ct ON ct.entry = c.SourceGroup
            LEFT JOIN gameobject_template gt ON gt.entry = c.SourceGroup
            LEFT JOIN item_template       it ON it.entry = c.SourceEntry
            WHERE (c.SourceTypeOrReferenceId, c.SourceGroup, c.SourceEntry, c.SourceId) IN ({placeholders})
            ORDER BY c.SourceGroup, c.SourceEntry, c.SourceId, c.ElseGroup, c.ConditionTypeOrReference
            """,
            tuple(params),
        )

        self.cond_table.setRowCount(0)
        for r in rows:
            self._append_condition_row(r)

        self.log(f"Loaded {len(rows)} condition row(s) for quest {self.quest_id} across {len(keys)} source group(s).")

    def _append_condition_row(self, r: Dict[str, Any]) -> None:
        row = self.cond_table.rowCount()
        self.cond_table.insertRow(row)

        # Write DB columns first
        for i, col in enumerate(self.COND_COLS):
            val = r.get(col)
            txt = "" if val is None else str(val)
            
            # Dropdown for SourceTypeOrReferenceId
            if col == "SourceTypeOrReferenceId":
                cb = QtWidgets.QComboBox()
                for sid, name in self.SRC_TYPE_CHOICES:
                    cb.addItem(f"{sid} = {name}", sid)

                try:
                    cur = int(txt.strip() or "0")
                except Exception:
                    cur = 0

                idx = cb.findData(cur)
                cb.setCurrentIndex(idx if idx >= 0 else 0)
                cb.currentIndexChanged.connect(lambda _=None, cb=cb: self._on_source_type_changed(cb))

                self.cond_table.setCellWidget(row, i, cb)
                self.cond_table.setItem(row, i, QtWidgets.QTableWidgetItem(str(cur)))
                continue

            # Dropdown for ConditionTypeOrReference
            if col == "ConditionTypeOrReference":
                cb = QtWidgets.QComboBox()
                for cid, name in self.COND_TYPE_CHOICES:
                    cb.addItem(f"{cid} = {name}", cid)

                try:
                    cur = int(txt.strip() or "0")
                except Exception:
                    cur = 0

                # select current
                idx = cb.findData(cur)
                cb.setCurrentIndex(idx if idx >= 0 else 0)

                cb.currentIndexChanged.connect(lambda _=None, cb=cb: self._on_cond_type_changed(cb))
                self.cond_table.setCellWidget(row, i, cb)

                # keep an item too (optional but helps visuals/sorting)
                self.cond_table.setItem(row, i, QtWidgets.QTableWidgetItem(str(cur)))
                continue

            self.cond_table.setItem(row, i, QtWidgets.QTableWidgetItem(txt))

        # Then display-only columns
        for j, col in enumerate(self.COND_DISPLAY_COLS):
            idx = len(self.COND_COLS) + j
            val = r.get(col, "")
            item = QtWidgets.QTableWidgetItem("" if val is None else str(val))
            item.setFlags(item.flags() & ~Qt.ItemFlag.ItemIsEditable)  # read-only
            self.cond_table.setItem(row, idx, item)

    def _on_source_type_changed(self, cb: QtWidgets.QComboBox) -> None:
        row_idx = -1
        col_idx = self.COND_COLS.index("SourceTypeOrReferenceId")
        for r in range(self.cond_table.rowCount()):
            if self.cond_table.cellWidget(r, col_idx) is cb:
                row_idx = r
                break
        if row_idx < 0:
            return

        stype = int(cb.currentData() or 0)

        it = self.cond_table.item(row_idx, col_idx)
        if it:
            it.setText(str(stype))

        # If the row we changed is currently selected, refresh routing immediately
        if row_idx == self._selected_condition_row():
            self._on_condition_selected()

    def _cond_row_dict(self, row: int) -> Dict[str, Any]:
        d: Dict[str, Any] = {}
        for i, col in enumerate(self.COND_COLS):
            it = self.cond_table.item(row, i)
            if col == "SourceTypeOrReferenceId":
                w = self.cond_table.cellWidget(row, i)
                if isinstance(w, QtWidgets.QComboBox):
                    d[col] = int(w.currentData() or 0)
                    continue

            if col == "ConditionTypeOrReference":
                w = self.cond_table.cellWidget(row, i)
                if isinstance(w, QtWidgets.QComboBox):
                    d[col] = int(w.currentData() or 0)
                    continue

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

    def _set_cell_int(self, row: int, col_name: str, value: int) -> None:
        col = self.COND_COLS.index(col_name)
        it = self.cond_table.item(row, col)
        if it is None:
            it = QtWidgets.QTableWidgetItem("")
            self.cond_table.setItem(row, col, it)
        it.setText(str(int(value)))

    def _selected_condition_row(self) -> int:
        return self.cond_table.currentRow()

    def add_condition_row(self) -> None:
        if self.quest_id is None:
            QtWidgets.QMessageBox.information(self, "No quest", "Load a quest first.")
            return

        # Create a unique SourceId so multiple rows don't collide on the composite PK.
        # We pick next SourceId for this quest_id (ConditionValue1).
        try:
            row = self.db.fetch_one(
                """
                SELECT COALESCE(MAX(SourceId), 0) AS m
                FROM conditions
                WHERE ConditionTypeOrReference = %s
                  AND ConditionValue1 = %s
                """,
                (self.ANCHOR_COND_TYPE, self.quest_id),
            )
            next_source_id = int((row or {}).get("m") or 0) + 1
        except Exception:
            next_source_id = 1

        r: Dict[str, Any] = {c: 0 for c in self.COND_COLS}

        # ---- EmuCoach Cataclysm v18 defaults ----
        r["SourceTypeOrReferenceId"] = 1      # Creature Loot
        r["ConditionTypeOrReference"] = self.ANCHOR_COND_TYPE     # Player has quest (ANCHOR ROW)
        r["ConditionTarget"] = 0

        # Anchor this condition group to the quest
        r["ConditionValue1"] = self.quest_id

        # Required for composite PK uniqueness
        r["SourceId"] = next_source_id

        # Optional / cosmetic
        r["ScriptName"] = ""
        r["Comment"] = ""

        self._append_condition_row(r)
        new_row = self.cond_table.rowCount() - 1
        self.cond_table.setCurrentCell(new_row, 0)
        self.cond_table.scrollToItem(self.cond_table.item(new_row, 0))
        self.log(f"Added new condition row (defaults). SourceId={next_source_id}")

    def save_condition_selected(self) -> None:
        if self.quest_id is None:
            QtWidgets.QMessageBox.information(self, "No quest", "Load a quest first.")
            return

        row = self._selected_condition_row()
        if row < 0:
            QtWidgets.QMessageBox.information(self, "Pick a row", "Select a condition row to save.")
            return

        d = self._cond_row_dict(row)
        
        ctype = int(d.get("ConditionTypeOrReference", 0))
        if ctype == self.ANCHOR_COND_TYPE and int(d.get("ConditionValue1", 0)) <= 0:
            d["ConditionValue1"] = self.quest_id



        # --- Minimal sanity checks so it doesn't feel "broken"
        stype = int(d.get("SourceTypeOrReferenceId", 0))
        if stype in (1, 4):
            if int(d.get("SourceGroup", 0)) <= 0:
                QtWidgets.QMessageBox.warning(self, "Missing SourceGroup", "Set SourceGroup (creature/go entry).")
                return
            if int(d.get("SourceEntry", 0)) <= 0:
                QtWidgets.QMessageBox.warning(self, "Missing SourceEntry", "Set SourceEntry (item id).")
                return

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

            # Reload so display columns (SourceGroupName/ItemName) refresh
            self._load_conditions()

        except Exception as e:
            self.db.rollback()
            QtWidgets.QMessageBox.critical(self, "Save failed", str(e))
            self.log(f"ERROR saving condition row: {e}")

    def _on_cond_type_changed(self, cb: QtWidgets.QComboBox) -> None:
        # Find which row owns this combobox (cheap scan; row counts are small)
        row_idx = -1
        col_idx = self.COND_COLS.index("ConditionTypeOrReference")
        for r in range(self.cond_table.rowCount()):
            if self.cond_table.cellWidget(r, col_idx) is cb:
                row_idx = r
                break
        if row_idx < 0:
            return

        ctype = int(cb.currentData() or 0)

        # Keep the underlying item text in sync (optional but nice)
        it = self.cond_table.item(row_idx, col_idx)
        if it:
            it.setText(str(ctype))

        # --- Safe defaults (only fill if empty/zero) ---
        # ConditionTarget
        if int(self.cond_table.item(row_idx, self.COND_COLS.index("ConditionTarget")).text() or "0") == 0:
            self._set_cell_int(row_idx, "ConditionTarget", 0)

        # NegativeCondition
        if int(self.cond_table.item(row_idx, self.COND_COLS.index("NegativeCondition")).text() or "0") == 0:
            self._set_cell_int(row_idx, "NegativeCondition", 0)

        # ElseGroup
        if int(self.cond_table.item(row_idx, self.COND_COLS.index("ElseGroup")).text() or "0") == 0:
            self._set_cell_int(row_idx, "ElseGroup", 0)

        # Clear extra values unless user already typed something
        for vn in ("ConditionValue2", "ConditionValue3"):
            col = self.COND_COLS.index(vn)
            itv = self.cond_table.item(row_idx, col)
            if itv is None or itv.text().strip() == "":
                self._set_cell_int(row_idx, vn, 0)

        # --- Quest auto-fill ---
        # For quest-related types, set ConditionValue1 = currently loaded quest_id (if empty/zero)
        if self.quest_id is not None and ctype in self.QUEST_TYPES_NEED_QUEST_ID:
            col = self.COND_COLS.index("ConditionValue1")
            itv1 = self.cond_table.item(row_idx, col)
            cur = 0
            try:
                cur = int((itv1.text() if itv1 else "0").strip() or "0")
            except Exception:
                cur = 0
            if cur <= 0:
                self._set_cell_int(row_idx, "ConditionValue1", int(self.quest_id))

    def delete_condition_selected(self) -> None:
        if self.quest_id is None:
            return
        row = self._selected_condition_row()
        if row < 0:
            return

        d = self._cond_row_dict(row)

        sg = int(d.get("SourceGroup", 0))
        se = int(d.get("SourceEntry", 0))
        st = int(d.get("SourceTypeOrReferenceId", 0))
        sid = int(d.get("SourceId", 0))
        ctype = int(d.get("ConditionTypeOrReference", 0))
        cv1 = int(d.get("ConditionValue1", 0))

        # Anchor rows are what your loader uses to “find” a group
        is_anchor = (ctype == 2 and cv1 == int(self.quest_id))

        msg = (
            "Delete the ENTIRE condition group (and its loot row)?\n\n"
            f"SG={sg} SE={se} SourceId={sid} (anchor row)\n\n"
            "This will delete ALL conditions sharing this SourceId and the matching loot row."
            if is_anchor else
            "Delete ONLY this single condition row?\n\n"
            f"SG={sg} SE={se} SourceId={sid} CType={ctype}"
        )

        ok = QtWidgets.QMessageBox.question(self, "Confirm Delete", msg)
        if ok != QtWidgets.QMessageBox.StandardButton.Yes:
            return

        try:
            if is_anchor:
                # Delete the whole group (all conditions with the same source key)
                n = self.db.execute(
                    """
                    DELETE FROM conditions
                    WHERE SourceTypeOrReferenceId=%s
                      AND SourceGroup=%s
                      AND SourceEntry=%s
                      AND SourceId=%s
                      AND ConditionValue1=%s
                    """,
                    (st, sg, se, sid, int(self.quest_id)),
                )

                # Also delete the corresponding loot row
                if st == 1 and sg > 0 and se > 0:
                    self.db.execute(
                        "DELETE FROM creature_loot_template WHERE entry=%s AND item=%s",
                        (sg, se),
                    )
                elif st == 13 and sg > 0 and se > 0:
                    self.db.execute(
                        "DELETE FROM gameobject_loot_template WHERE entry=%s AND item=%s",
                        (sg, se),
                    )

            else:
                # Delete ONLY the selected row (exact composite key)
                where = " AND ".join([f"`{k}`=%s" for k in self.COND_PK])
                sql = f"DELETE FROM conditions WHERE {where}"
                params = [d.get(k, 0) for k in self.COND_PK]
                n = self.db.execute(sql, params)

            self.db.commit()
            self.log(f"Deleted {n} condition row(s).")
            self.clear_loot_form()
            self._load_conditions()

        except Exception as e:
            self.db.rollback()
            QtWidgets.QMessageBox.critical(self, "Delete failed", str(e))
            self.log(f"ERROR deleting condition(s): {e}")

    def _selected_source_type(self) -> int:
        row = self._selected_condition_row()
        if row < 0:
            return 0
        col = self.COND_COLS.index("SourceTypeOrReferenceId")
        w = self.cond_table.cellWidget(row, col)
        if isinstance(w, QtWidgets.QComboBox):
            return int(w.currentData() or 0)
        it = self.cond_table.item(row, col)
        try:
            return int((it.text() if it else "0").strip() or "0")
        except Exception:
            return 0

    # -------------------------
    # Linking to creature_loot_template
    # -------------------------
    def _on_condition_selected(self) -> None:
        st = self._selected_source_type()

        # Enable/disable the creature loot buttons depending on source type
        is_creature = (st == 1)
        is_object = (st == 4)

        self.btn_loot_load.setEnabled(is_creature)
        self.btn_loot_new.setEnabled(is_creature)
        self.btn_loot_save.setEnabled(is_creature)

        # Always compute key (SourceGroup, SourceEntry) and pass it to object editor too
        key = self._selected_loot_key()
        if key:
            entry, item = key
            self.obj_loot.set_key(entry, item)
        else:
            self.obj_loot.clear()

        if is_creature:
            # Switch to creature tab and auto-load creature loot
            self.right_tabs.setCurrentIndex(self.TAB_CREATURE)
            self.load_loot_for_selected_condition(auto=True)
            return

        if is_object:
            # Switch to object tab and auto-load object loot
            self.right_tabs.setCurrentIndex(self.TAB_OBJECT)
            # auto-load is optional; your object editor supports it
            if key:
                self.obj_loot.load_current()
            # Clear creature form so it doesn't mislead
            self.clear_loot_form()
            return

        # Not a loot source type we handle in this editor
        self.clear_loot_form()
        # leave object editor cleared via key logic above

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
        
        st = self._selected_source_type()
        if st == 4:
            # GameObject loot row: use object editor instead
            if key:
                entry, item = key
                self.obj_loot.set_key(entry, item)
                self.right_tabs.setCurrentIndex(self.TAB_OBJECT)
                self.obj_loot.load_current()
            if not auto:
                QtWidgets.QMessageBox.information(
                    self,
                    "GameObject loot",
                    "This condition row is SourceType=4 (GameObject). Use the Object Loot tab.",
                )
            self.clear_loot_form()
            return
        
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
        st = self._selected_source_type()
        if st == 4:
            QtWidgets.QMessageBox.information(
                self,
                "GameObject loot",
                "This condition row is SourceType=4 (GameObject). Use Object Loot → Create (if missing).",
            )
            self.right_tabs.setCurrentIndex(self.TAB_OBJECT)
            return

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
        """
        Save creature_loot_template for the currently selected condition row.

        If selected condition is SourceType=4 (GameObject), we route the user
        to the Object Loot tab instead of writing to creature_loot_template.
        """
        st = self._selected_source_type()
        if st == 4:
            QtWidgets.QMessageBox.information(
                self,
                "GameObject loot",
                "This condition row is SourceType=4 (GameObject). Use the Object Loot tab to save.",
            )
            self.right_tabs.setCurrentIndex(self.TAB_OBJECT)
            return

        key = self._selected_loot_key()
        if not key:
            QtWidgets.QMessageBox.information(
                self,
                "No key",
                "Select a condition row first (SourceGroup/SourceEntry).",
            )
            return

        entry, item = key
        vals = self._loot_form_values()

        try:
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
                vals.get("ChanceOrQuestChance", -100.0),
                vals.get("lootmode", 1),
                vals.get("groupid", 0),
                vals.get("mincountOrRef", 1),
                vals.get("maxcount", 1),
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
