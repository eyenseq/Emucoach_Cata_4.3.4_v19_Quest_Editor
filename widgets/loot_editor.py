from __future__ import annotations
from typing import Any, Callable, Dict, List, Optional, Tuple
from pathlib import Path
import struct

try:
    import config
except Exception:
    config = None


from PyQt6 import QtWidgets
from PyQt6.QtCore import Qt, QTimer

from widgets.generic_loot_editor import GenericLootEditor

def load_wdbc_id_name(
    path: str,
    *,
    name_field_index: Optional[int] = None,
    candidate_name_fields: Optional[List[int]] = None,
    max_rows_scan: int = 200,
) -> list[tuple[int, str]]:
    """
    Generic WDBC reader for "ID + Name" tables.
    - ID is fields[0]
    - Name is a string offset at some field index.
    If name_field_index isn't provided, we guess it by scanning candidate fields.
    """
    data = Path(path).read_bytes()
    if data[:4] != b"WDBC":
        raise ValueError(f"Not a valid WDBC file. Magic={data[:4]!r}")

    _magic, rec_count, field_count, rec_size, str_size = struct.unpack_from("<4s4I", data, 0)
    records_off = 20
    strings_off = records_off + rec_count * rec_size
    string_block = data[strings_off : strings_off + str_size]

    ints_per_record = rec_size // 4

    def read_cstr(off: int) -> str:
        if off <= 0 or off >= len(string_block):
            return ""
        end = string_block.find(b"\x00", off)
        if end == -1:
            return ""
        return string_block[off:end].decode("utf-8", "ignore").strip()

    # Choose a name field index if not provided
    if name_field_index is None:
        cands = candidate_name_fields or [
            1, 2, 3, 4, 5, 6, 7, 8,
            10, 11, 12, 13, 14,
            20, 21, 22, 23, 24, 25, 26, 27, 28,
        ]
        best_idx = None
        best_score = -1
        scan_n = min(rec_count, max_rows_scan)

        for idx in cands:
            score = 0
            for i in range(scan_n):
                roff = records_off + i * rec_size
                fields = struct.unpack_from("<" + "I" * ints_per_record, data, roff)
                if idx >= len(fields):
                    continue
                s = read_cstr(int(fields[idx]))
                if s and any(ch.isalpha() for ch in s):
                    score += 1
            if score > best_score:
                best_score = score
                best_idx = idx

        name_field_index = best_idx if best_idx is not None else 1

    out: list[tuple[int, str]] = []
    for i in range(rec_count):
        roff = records_off + i * rec_size
        fields = struct.unpack_from("<" + "I" * ints_per_record, data, roff)
        rid = int(fields[0]) if fields else 0
        noff = int(fields[name_field_index]) if len(fields) > name_field_index else 0
        name = read_cstr(noff) if noff else ""
        if rid:
            out.append((rid, name or f"ID {rid}"))

    out.sort(key=lambda t: (t[1] or "").lower())
    return out

class LootIDPickerDialog(QtWidgets.QDialog):
    """Type-as-you-type picker used by QuestLootEditor (no cross-imports).

    Modes:
      - "item" -> item_template (entry,name)
      - "creature" -> creature_template (entry,name)
      - "go" -> gameobject_template (entry,name)
      - "quest" -> quest_template (Id,Title)
    """

    def __init__(self, db, mode: str, parent=None):
        super().__init__(parent)
        self.db = db
        self.mode = mode
        self._selected_id: Optional[int] = None

        self.setWindowTitle(f"Pick {mode.title()} ID")
        self.setModal(True)
        self.resize(760, 420)

        self.q = QtWidgets.QLineEdit()
        self.q.setPlaceholderText("Type an ID or a name fragment")
        self.btn_search = QtWidgets.QPushButton("Search")

        self._live_timer = QTimer(self)
        self._live_timer.setSingleShot(True)
        self._live_timer.timeout.connect(self.run_search)

        top = QtWidgets.QHBoxLayout()
        top.addWidget(self.q, 1)
        top.addWidget(self.btn_search)

        self.table = QtWidgets.QTableWidget(0, 2)
        self.table.setHorizontalHeaderLabels(["ID", "Name"])
        self.table.horizontalHeader().setStretchLastSection(True)
        self.table.setSelectionBehavior(QtWidgets.QAbstractItemView.SelectionBehavior.SelectRows)
        self.table.setSelectionMode(QtWidgets.QAbstractItemView.SelectionMode.SingleSelection)
        self.table.setEditTriggers(QtWidgets.QAbstractItemView.EditTrigger.NoEditTriggers)

        self.btn_select = QtWidgets.QPushButton("Select")
        self.btn_cancel = QtWidgets.QPushButton("Cancel")

        btns = QtWidgets.QHBoxLayout()
        btns.addStretch(1)
        btns.addWidget(self.btn_cancel)
        btns.addWidget(self.btn_select)

        lay = QtWidgets.QVBoxLayout(self)
        lay.addLayout(top)
        lay.addWidget(self.table, 1)
        lay.addLayout(btns)

        self.btn_search.clicked.connect(self.run_search)
        self.btn_cancel.clicked.connect(self.reject)
        self.btn_select.clicked.connect(self.accept_selected)
        self.table.cellDoubleClicked.connect(lambda _r, _c: self.accept_selected())
        self.q.returnPressed.connect(self.run_search)
        self.q.textChanged.connect(lambda _t: self._live_timer.start(120))

        self.run_search()

    def selected_id(self) -> Optional[int]:
        return self._selected_id

    def _table_and_cols(self) -> tuple[str, str, str]:
        if self.mode == "item":
            return ("item_template", "entry", "name")
        if self.mode == "creature":
            return ("creature_template", "entry", "name")
        if self.mode == "go":
            return ("gameobject_template", "entry", "name")
        if self.mode == "quest":
            return ("quest_template", "entry", "Title")
        raise ValueError(f"Unknown mode: {self.mode}")

    def run_search(self) -> None:
        q = (self.q.text() or "").strip()
        tbl, idcol, namecol = self._table_and_cols()
        like = f"%{q}%"

        try:
            if q.isdigit():
                rows = self.db.fetch_all(
                    f"SELECT {idcol} AS id, {namecol} AS name FROM {tbl} WHERE {idcol}=%s LIMIT 200",
                    (int(q),),
                )
            else:
                rows = self.db.fetch_all(
                    f"SELECT {idcol} AS id, {namecol} AS name FROM {tbl} WHERE {namecol} LIKE %s ORDER BY {idcol} LIMIT 200",
                    (like,),
                )
        except Exception:
            rows = []

        self.table.setRowCount(0)
        for r in rows:
            rid = int(r.get("id") or 0)
            nm = str(r.get("name") or "").strip()
            row = self.table.rowCount()
            self.table.insertRow(row)
            self.table.setItem(row, 0, QtWidgets.QTableWidgetItem(str(rid)))
            self.table.setItem(row, 1, QtWidgets.QTableWidgetItem(nm))

    def accept_selected(self) -> None:
        sel = self.table.selectionModel().selectedRows()
        if not sel:
            return
        r = sel[0].row()
        it = self.table.item(r, 0)
        try:
            self._selected_id = int((it.text() or "0").strip()) if it else None
        except Exception:
            self._selected_id = None
        if self._selected_id is None:
            return
        self.accept()

class DBCIdPickerDialog(QtWidgets.QDialog):
    """
    Search-as-you-type picker for DBC-derived rows: [(id, name), ...]
    """
    def __init__(self, title: str, rows: list[tuple[int, str]], parent=None, initial_query: str = ""):
        super().__init__(parent)
        self.setWindowTitle(title)
        self._rows = rows
        self._chosen: Optional[int] = None

        self.search = QtWidgets.QLineEdit()
        self.search.setPlaceholderText("Type to filter…")

        self.table = QtWidgets.QTableWidget(0, 2)
        self.table.setHorizontalHeaderLabels(["ID", "Name"])
        self.table.horizontalHeader().setStretchLastSection(True)
        self.table.setSelectionBehavior(QtWidgets.QAbstractItemView.SelectionBehavior.SelectRows)
        self.table.setSelectionMode(QtWidgets.QAbstractItemView.SelectionMode.SingleSelection)
        self.table.setEditTriggers(QtWidgets.QAbstractItemView.EditTrigger.NoEditTriggers)

        btn_select = QtWidgets.QPushButton("Select")
        btn_cancel = QtWidgets.QPushButton("Cancel")
        btn_select.clicked.connect(self._accept_selected)
        btn_cancel.clicked.connect(self.reject)

        bb = QtWidgets.QHBoxLayout()
        bb.addStretch(1)
        bb.addWidget(btn_cancel)
        bb.addWidget(btn_select)

        lay = QtWidgets.QVBoxLayout(self)
        lay.addWidget(self.search)
        lay.addWidget(self.table, 1)
        lay.addLayout(bb)

        self.search.textChanged.connect(self._refill)
        self.table.cellDoubleClicked.connect(lambda _r, _c: self._accept_selected())

        if initial_query:
            self.search.setText(initial_query)
        else:
            self._refill()

    def chosen_id(self) -> Optional[int]:
        return self._chosen

    def _refill(self) -> None:
        q = (self.search.text() or "").strip().lower()
        if not q:
            rows = self._rows
        else:
            rows = [(i, n) for (i, n) in self._rows if q in str(i) or q in (n or "").lower()]

        self.table.setRowCount(0)
        for i, n in rows[:2000]:
            r = self.table.rowCount()
            self.table.insertRow(r)
            self.table.setItem(r, 0, QtWidgets.QTableWidgetItem(str(i)))
            self.table.setItem(r, 1, QtWidgets.QTableWidgetItem(n or ""))

        if self.table.rowCount():
            self.table.selectRow(0)

    def _accept_selected(self) -> None:
        r = self.table.currentRow()
        if r < 0:
            return
        item = self.table.item(r, 0)
        if not item:
            return
        try:
            self._chosen = int(item.text())
        except Exception:
            self._chosen = None
        if self._chosen is None:
            return
        self.accept()

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

    # Generic loot-template columns (shared by *_loot_template tables)
    LOOT_COLS = [
        "entry",
        "item",
        "ChanceOrQuestChance",
        "lootmode",
        "groupid",
        "mincountOrRef",
        "maxcount",
    ]

    # These types typically want ConditionValue1 = quest_id
    QUEST_TYPES_NEED_QUEST_ID = {8, 9, 14, 28, 43, 47}
    ANCHOR_COND_TYPE = 9
    
    # ConditionTypeOrReference dropdown (leave out deprecated)
    COND_TYPE_CHOICES = [
        (0,  "NONE"),
        (1,  "AURA"),
        (2,  "ITEM"),
        (3,  "ITEM_EQUIPPED"),
        (4,  "ZONEID"),
        (5,  "REPUTATION_RANK"),
        (6,  "TEAM"),
        (7,  "SKILL"),
        (8,  "QUESTREWARDED"),
        (9,  "QUESTTAKEN"),
        (10, "DRUNKENSTATE"),
        (11, "WORLD_STATE"),
        (12, "ACTIVE_EVENT"),
        (13, "INSTANCE_INFO"),
        (14, "QUEST_NONE"),
        (15, "CLASS"),
        (16, "RACE"),
        (17, "ACHIEVEMENT"),
        (18, "TITLE"),
        # (19, "SPAWNMASK_DEPRECATED")  # excluded
        (20, "GENDER"),
        (21, "UNIT_STATE"),
        (22, "MAPID"),
        (23, "AREAID"),
        (24, "CREATURE_TYPE"),
        (25, "SPELL"),
        (26, "PHASEID"),
        (27, "LEVEL"),
        (28, "QUEST_COMPLETE"),
        (29, "NEAR_CREATURE"),
        (30, "NEAR_GAMEOBJECT"),
        (33, "RELATION_TO"),
        (34, "REACTION_TO"),
        (35, "DISTANCE_TO"),
        (36, "ALIVE"),
        (37, "HP_VAL"),
        (38, "HP_PCT"),
        (39, "REALM_ACHIEVEMENT"),
        (40, "IN_WATER"),
        (41, "TERRAIN_SWAP"),
        (42, "STAND_STATE"),
        (43, "DAILY_QUEST_DONE"),
        (44, "CHARMED"),
        (45, "PET_TYPE"),
        (46, "TAXI"),
        (47, "QUESTSTATE"),
        (48, "QUEST_OBJECTIVE_PROGRESS"),
        (49, "DIFFICULTY_ID"),
        (50, "GAMEMASTER"),
        (51, "OBJECT_ENTRY_GUID"),
        (52, "TYPE_MASK"),
        (53, "BATTLE_PET_COUNT"),
        (54, "SCENARIO_STEP"),
        (55, "SCENE_IN_PROGRESS"),
        (56, "PLAYER_CONDITION"),
        (57, "PRIVATE_OBJECT"),
        (58, "STRING_ID"),
        (59, "LABEL"),
    ]

    COND_TOOLTIP_HEADER = (
        "ConditionTypeOrReference:\n"
        "• If negative: ID of a reference (references SourceTypeOrReferenceId of another condition).\n"
        "• If positive: condition type to be applied."
    )

    COND_TOOLTIP_MAP = {
        # --- (your existing dict exactly as you pasted it) ---
        # Keep this whole dict block indented at 4 spaces.
        0: dict(name="CONDITION_NONE", ConditionValue1="(Never used)", ConditionValue2="(Never used)", ConditionValue3="(Never used)", Usage=""),
        1: dict(name="CONDITION_AURA", ConditionValue1="Spell ID from Spell.dbc", ConditionValue2="Effect index (0-31)", ConditionValue3="Always 0", Usage=""),
        2: dict(name="CONDITION_ITEM", ConditionValue1="item entry (item_template.entry)", ConditionValue2="item count", ConditionValue3="0 = not in bank\n1 = in bank", Usage=""),
        3: dict(name="CONDITION_ITEM_EQUIPPED", ConditionValue1="item entry (item_template.entry)", ConditionValue2="Always 0", ConditionValue3="Always 0", Usage=""),
        4: dict(name="CONDITION_ZONEID", ConditionValue1="Zone ID where this condition will be true.", ConditionValue2="Always 0", ConditionValue3="Always 0", Usage=""),
        5: dict(name="CONDITION_REPUTATION_RANK", ConditionValue1="Faction template ID from Faction.dbc",
                ConditionValue2=("rank:\n"
                                 "  1 = Hated\n  2 = Hostile\n  4 = Unfriendly\n  8 = Neutral\n"
                                 " 16 = Friendly\n 32 = Honored\n 64 = Revered\n128 = Exalted\n\n"
                                 "Add target ranks together for the condition to be true for all those ranks."),
                ConditionValue3="Always 0", Usage=""),
        6: dict(name="CONDITION_TEAM", ConditionValue1="TeamID:\nAlliance = 469\nHorde = 67", ConditionValue2="Always 0", ConditionValue3="Always 0", Usage=""),
        7: dict(name="CONDITION_SKILL", ConditionValue1="Required skill.\nSee SkillLine.db2.", ConditionValue2="Skill rank value (e.g. 1..450 for 3.3.5 branch)", ConditionValue3="Always 0", Usage=""),
        8: dict(name="CONDITION_QUESTREWARDED", ConditionValue1="Quest ID (quest_template.id)", ConditionValue2="Always 0", ConditionValue3="Always 0", Usage=""),
        9: dict(name="CONDITION_QUESTTAKEN", ConditionValue1="Quest ID (quest_template.id)", ConditionValue2="Always 0", ConditionValue3="Always 0", Usage=""),
        10: dict(name="CONDITION_DRUNKENSTATE", ConditionValue1="Sober = 0\nTipsy = 1\nDrunk = 2\nSmashed = 3", ConditionValue2="Always 0", ConditionValue3="Always 0", Usage=""),
        11: dict(name="CONDITION_WORLD_STATE", ConditionValue1="World state index", ConditionValue2="World state value", ConditionValue3="Always 0", Usage=""),
        12: dict(name="CONDITION_ACTIVE_EVENT", ConditionValue1="Event entry (game_event.eventEntry)", ConditionValue2="Always 0", ConditionValue3="Always 0", Usage=""),
        13: dict(name="CONDITION_INSTANCE_INFO", ConditionValue1="entry (see corresponding source script files)", ConditionValue2="data (see corresponding script source files)",
                 ConditionValue3=("0 = INSTANCE_INFO_DATA\n1 = INSTANCE_INFO_GUID_DATA\n2 = INSTANCE_INFO_BOSS_STATE\n3 = INSTANCE_INFO_DATA64"), Usage=""),
        14: dict(name="CONDITION_QUEST_NONE", ConditionValue1="Quest ID (quest_template.id)", ConditionValue2="Always 0", ConditionValue3="Always 0", Usage=""),
        15: dict(name="CONDITION_CLASS",
                 ConditionValue1=("Class mask from ChrClasses.dbc (sum flags):\n"
                                  "  1 = Warrior\n  4 = Hunter\n  8 = Rogue\n 16 = Priest\n"
                                  " 32 = Death Knight\n 64 = Shaman\n128 = Mage\n256 = Warlock\n"
                                  "512 = Monk\n1024 = Druid\n2048 = Demon Hunter\n4096 = Evoker"),
                 ConditionValue2="Always 0", ConditionValue3="Always 0", Usage=""),
        16: dict(name="CONDITION_RACE", ConditionValue1="Player must be this race.\nSee ChrRaces.dbc .\nAdd flags together for all races where condition is true.", ConditionValue2="Always 0", ConditionValue3="Always 0", Usage=""),
        17: dict(name="CONDITION_ACHIEVEMENT", ConditionValue1="Achievement ID (Achievement.dbc)", ConditionValue2="Always 0", ConditionValue3="Always 0", Usage=""),
        18: dict(name="CONDITION_TITLE", ConditionValue1="Title ID (CharTitles.dbc)", ConditionValue2="Always 0", ConditionValue3="Always 0", Usage=""),
        20: dict(name="CONDITION_GENDER", ConditionValue1="0 = Male\n1 = Female\n2 = None", ConditionValue2="Always 0", ConditionValue3="Always 0", Usage=""),
        21: dict(name="CONDITION_UNIT_STATE", ConditionValue1="UnitState (enum from Unit.h)", ConditionValue2="Always 0", ConditionValue3="Always 0", Usage=""),
        22: dict(name="CONDITION_MAPID", ConditionValue1="Map entry from Map.dbc (0=Eastern Kingdoms, 1=Kalimdor, ...)", ConditionValue2="Always 0", ConditionValue3="Always 0", Usage=""),
        23: dict(name="CONDITION_AREAID", ConditionValue1="Area ID from AreaTable.dbc", ConditionValue2="Always 0", ConditionValue3="Always 0", Usage=""),
        24: dict(name="CONDITION_CREATURE_TYPE", ConditionValue1="Creature type from creature_template.type (true if equals)", ConditionValue2="Always 0", ConditionValue3="Always 0", Usage=""),
        25: dict(name="CONDITION_SPELL", ConditionValue1="Spell ID from Spell.dbc", ConditionValue2="Always 0", ConditionValue3="Always 0", Usage=""),
        26: dict(name="CONDITION_PHASEID", ConditionValue1="PhaseID", ConditionValue2="Always 0", ConditionValue3="Always 0", Usage=""),
        27: dict(name="CONDITION_LEVEL", ConditionValue1="Player level",
                 ConditionValue2=("Optional:\n  0 = Level must be equal\n  1 = Level must be higher\n  2 = Level must be lower\n  3 = Level must be higher or equal\n  4 = Level must be lower or equal."),
                 ConditionValue3="Always 0", Usage=""),
        28: dict(name="CONDITION_QUEST_COMPLETE", ConditionValue1="Quest ID (quest_template.id)", ConditionValue2="Always 0", ConditionValue3="Always 0", Usage=""),
        29: dict(name="CONDITION_NEAR_CREATURE", ConditionValue1="Creature entry (creature_template.entry)", ConditionValue2="Distance in yards", ConditionValue3="Alive=0\nDead=1", Usage=""),
        30: dict(name="CONDITION_NEAR_GAMEOBJECT", ConditionValue1="Gameobject entry (gameobject_template.entry)", ConditionValue2="Distance in yards", ConditionValue3="Always 0", Usage=""),
        33: dict(name="CONDITION_RELATION_TO",
                 ConditionValue1="Target to which relation is checked (one of ConditionTargets available in current SourceType)",
                 ConditionValue2=("RelationType:\n0 RELATION_SELF\n1 RELATION_IN_PARTY\n2 RELATION_IN_RAID_OR_PARTY\n3 RELATION_OWNED_BY\n4 RELATION_PASSENGER_OF\n5 RELATION_CREATED_BY"),
                 ConditionValue3="Always 0", Usage=""),
        34: dict(name="CONDITION_REACTION_TO",
                 ConditionValue1="Target to which reaction is checked (one of ConditionTargets available in current SourceType)",
                 ConditionValue2=("rankMask allowed reactions:\n  1 Hated\n  2 Hostile\n  4 Unfriendly\n  8 Neutral\n 16 Friendly\n 32 Honored\n 64 Revered\n128 Exalted"),
                 ConditionValue3="Always 0", Usage=""),
        35: dict(name="CONDITION_DISTANCE_TO",
                 ConditionValue1="Target to which distance is checked (one of ConditionTargets available in current SourceType)",
                 ConditionValue2="Distance (yards) between current ConditionTarget and target specified in Value1",
                 ConditionValue3=("ComparisonType:\n0 equal\n1 higher than\n2 lower than\n3 equal or higher\n4 equal or lower"),
                 Usage=""),
        36: dict(name="CONDITION_ALIVE",
                 ConditionValue1=("Always 0.\nUse NegativeCondition:\n  NegativeCondition=0 => target must be ALIVE\n  NegativeCondition=1 => target must be DEAD.\n\nNOTE: corpse vs 'looks dead' are different."),
                 ConditionValue2="Always 0", ConditionValue3="Always 0", Usage=""),
        37: dict(name="CONDITION_HP_VAL", ConditionValue1="HP value",
                 ConditionValue2=("ComparisonType:\n0 equal\n1 higher\n2 lesser\n3 equal or higher\n4 equal or lower"),
                 ConditionValue3="Always 0", Usage=""),
        38: dict(name="CONDITION_HP_PCT", ConditionValue1="Percentage of max HP",
                 ConditionValue2=("ComparisonType:\n0 equal\n1 higher\n2 lower\n3 equal or higher\n4 equal or lower"),
                 ConditionValue3="Always 0", Usage=""),
        39: dict(name="CONDITION_REALM_ACHIEVEMENT", ConditionValue1="Achievement ID (Achievement.dbc)", ConditionValue2="Always 0", ConditionValue3="Always 0", Usage=""),
        40: dict(name="CONDITION_IN_WATER",
                 ConditionValue1=("Always 0.\nUse NegativeCondition:\n  NegativeCondition=0 => target must be on land\n  NegativeCondition=1 => target must be in water"),
                 ConditionValue2="Always 0", ConditionValue3="Always 0", Usage=""),
        41: dict(name="CONDITION_TERRAIN_SWAP", ConditionValue1="terrainSwap - true if object is in terrainswap [master only]", ConditionValue2="Always 0", ConditionValue3="Always 0", Usage=""),
        42: dict(name="CONDITION_STAND_STATE", ConditionValue1="stateType: 0=Exact state in Value2, 1=Any type of state in Value2",
                 ConditionValue2="Exact stand state or generic state; 0=Standing, 1=Sitting", ConditionValue3="Always 0", Usage=""),
        43: dict(name="CONDITION_DAILY_QUEST_DONE", ConditionValue1="Quest ID (quest_template.id)", ConditionValue2="Always 0", ConditionValue3="Always 0", Usage=""),
        44: dict(name="CONDITION_CHARMED", ConditionValue1="Always 0", ConditionValue2="Always 0", ConditionValue3="Always 0", Usage=""),
        45: dict(name="CONDITION_PET_TYPE", ConditionValue1="mask", ConditionValue2="Always 0", ConditionValue3="Always 0", Usage=""),
        46: dict(name="CONDITION_TAXI", ConditionValue1="Always 0", ConditionValue2="Always 0", ConditionValue3="Always 0", Usage=""),
        47: dict(name="CONDITION_QUESTSTATE", ConditionValue1="Quest ID (quest_template.id)",
                 ConditionValue2="state_mask:\n1 not taken\n2 completed\n8 in progress\n32 failed\n64 rewarded",
                 ConditionValue3="Always 0", Usage=""),
        48: dict(name="CONDITION_QUEST_OBJECTIVE_PROGRESS", ConditionValue1="Quest Objective ID", ConditionValue2="Always 0", ConditionValue3="Progress Value", Usage=""),
        49: dict(name="CONDITION_DIFFICULTY_ID", ConditionValue1="Difficulty (0 None, 1 Normal, etc)", ConditionValue2="Always 0", ConditionValue3="Always 0", Usage="true if target's map has difficulty id"),
        50: dict(name="CONDITION_GAMEMASTER", ConditionValue1="canBeGM", ConditionValue2="Always 0", ConditionValue3="Always 0", Usage="true if player is gamemaster (or can be gamemaster)"),
        51: dict(name="CONDITION_OBJECT_ENTRY_GUID", ConditionValue1="TypeID", ConditionValue2="entry", ConditionValue3="guid",
                 Usage="true if object is type TypeID and:\n• entry is 0 or matches object's entry\n• OR guid matches object's guid"),
        52: dict(name="CONDITION_TYPE_MASK", ConditionValue1="TypeMask", ConditionValue2="Always 0", ConditionValue3="Always 0", Usage="true if object's TypeMask matches provided TypeMask"),
        53: dict(name="CONDITION_BATTLE_PET_COUNT", ConditionValue1="SpeciesId", ConditionValue2="count", ConditionValue3="ComparisonType", Usage="true if player has count of battle pet species"),
        54: dict(name="CONDITION_SCENARIO_STEP", ConditionValue1="ScenarioStepId (Only >= 5.0.3)", ConditionValue2="Always 0", ConditionValue3="Always 0", Usage="true if object is at scenario with current step equal to ScenarioStepID"),
        55: dict(name="CONDITION_SCENE_IN_PROGRESS", ConditionValue1="SceneScriptPackageId", ConditionValue2="Always 0", ConditionValue3="Always 0", Usage="true if player is playing a scene with ScriptPackageId equal to given value"),
        56: dict(name="CONDITION_PLAYER_CONDITION", ConditionValue1="PlayerConditionId", ConditionValue2="Always 0", ConditionValue3="Always 0", Usage="true if player satisfies PlayerCondition"),
        57: dict(name="CONDITION_PRIVATE_OBJECT", ConditionValue1="Always 0", ConditionValue2="Always 0", ConditionValue3="Always 0", Usage="true if entity is private object"),
        58: dict(name="CONDITION_STRING_ID", ConditionValue1="Always 0", ConditionValue2="Always 0", ConditionValue3="Always 0", Usage="true if entity uses string id (ConditionStringValue1)"),
        59: dict(name="CONDITION_LABEL", ConditionValue1="Label", ConditionValue2="Always 0", ConditionValue3="Always 0", Usage="true if creature/gameobject has specified Label in CreatureLabel.db2/GameObjectLabel.db2"),
    }

    # SourceTypeOrReferenceId dropdown (leave out UNUSED 20)
    SRC_TYPE_CHOICES = [
        (0,  "NONE"),
        (1,  "CREATURE_LOOT_TEMPLATE"),
        (2,  "DISENCHANT_LOOT_TEMPLATE"),
        (3,  "FISHING_LOOT_TEMPLATE"),
        (4,  "GAMEOBJECT_LOOT_TEMPLATE"),
        (5,  "ITEM_LOOT_TEMPLATE"),
        (6,  "MAIL_LOOT_TEMPLATE"),
        (7,  "MILLING_LOOT_TEMPLATE"),
        (8,  "PICKPOCKETING_LOOT_TEMPLATE"),
        (9,  "PROSPECTING_LOOT_TEMPLATE"),
        (10, "REFERENCE_LOOT_TEMPLATE"),
        (11, "SKINNING_LOOT_TEMPLATE"),
        (12, "SPELL_LOOT_TEMPLATE"),
        (13, "SPELL_IMPLICIT_TARGET"),
        (14, "GOSSIP_MENU"),
        (15, "GOSSIP_MENU_OPTION"),
        (16, "CREATURE_TEMPLATE_VEHICLE"),
        (17, "SPELL"),
        (18, "SPELL_CLICK_EVENT"),
        (19, "QUEST_AVAILABLE"),
        # (20, "UNUSED")  # excluded
        (21, "VEHICLE_SPELL"),
        (22, "SMART_EVENT"),
        (23, "NPC_VENDOR"),
        (24, "SPELL_PROC"),
        (25, "TERRAIN_SWAP"),
        (26, "PHASE"),
        (27, "GRAVEYARD"),
        (28, "AREATRIGGER"),
        (29, "CONVERSATION_LINE"),
        (30, "AREATRIGGER_CLIENT_TRIGGERED"),
        (31, "TRAINER_SPELL"),
        (32, "OBJECT_ID_VISIBILITY"),
        (33, "SPAWN_GROUP"),
        (34, "PLAYER_CONDITION"),
        (35, "SKILL_LINE_ABILITY"),
        (36, "PLAYER_CHOICE_RESPONSE"),
    ]

    SRC_TOOLTIP_HEADER = (
        "SourceTypeOrReferenceId:\n"
        "• If negative: ID of a reference (referenced directly in ConditionTypeOrReference of another condition).\n"
        "• If positive: source type of the condition to be applied."
    )

    SRC_TOOLTIP_MAP = {
        0: dict(
            name="CONDITION_SOURCE_TYPE_NONE",
            SourceGroup="(Never used)",
            SourceEntry="(Never used)",
            SourceId="(Never used)",
            ConditionTarget="(Never used)",
            Notes="",
        ),

        1: dict(
            name="CONDITION_SOURCE_TYPE_CREATURE_LOOT_TEMPLATE",
            SourceGroup="creature_loot_template.Entry OR reference_loot_template.Entry",
            SourceEntry="Item ID (creature_loot_template.Item or reference_loot_template.Item)",
            SourceId="Always 0",
            ConditionTarget="Always 0",
            Notes="Used for creature loot drops.",
        ),

        2: dict(
            name="CONDITION_SOURCE_TYPE_DISENCHANT_LOOT_TEMPLATE",
            SourceGroup="disenchant_loot_template.Entry OR reference_loot_template.Entry",
            SourceEntry="Item ID (disenchant_loot_template.Item or reference_loot_template.Item)",
            SourceId="Always 0",
            ConditionTarget="Always 0",
            Notes="Used for disenchant results.",
        ),

        3: dict(
            name="CONDITION_SOURCE_TYPE_FISHING_LOOT_TEMPLATE",
            SourceGroup="fishing_loot_template.Entry OR reference_loot_template.Entry",
            SourceEntry="Item ID (fishing_loot_template.Item or reference_loot_template.Item)",
            SourceId="Always 0",
            ConditionTarget="Always 0",
            Notes="Used for fishing loot.",
        ),

        4: dict(
            name="CONDITION_SOURCE_TYPE_GAMEOBJECT_LOOT_TEMPLATE",
            SourceGroup="gameobject_loot_template.Entry OR reference_loot_template.Entry",
            SourceEntry="Item ID (gameobject_loot_template.Item or reference_loot_template.Item)",
            SourceId="Always 0",
            ConditionTarget="Always 0",
            Notes="Used for object loot (chests, nodes, etc).",
        ),

        5: dict(
            name="CONDITION_SOURCE_TYPE_ITEM_LOOT_TEMPLATE",
            SourceGroup="item_loot_template.Entry OR reference_loot_template.Entry",
            SourceEntry="Item ID (item_loot_template.Item or reference_loot_template.Item)",
            SourceId="Always 0",
            ConditionTarget="Always 0",
            Notes="Used for items that generate loot.",
        ),

        6: dict(
            name="CONDITION_SOURCE_TYPE_MAIL_LOOT_TEMPLATE",
            SourceGroup="mail_loot_template.Entry OR reference_loot_template.Entry",
            SourceEntry="Item ID (mail_loot_template.Item or reference_loot_template.Item)",
            SourceId="Always 0",
            ConditionTarget="Always 0",
            Notes="Used for mail attachments.",
        ),

        7: dict(
            name="CONDITION_SOURCE_TYPE_MILLING_LOOT_TEMPLATE",
            SourceGroup="milling_loot_template.Entry OR reference_loot_template.Entry",
            SourceEntry="Item ID (milling_loot_template.Item or reference_loot_template.Item)",
            SourceId="Always 0",
            ConditionTarget="Always 0",
            Notes="Used for milling results.",
        ),

        8: dict(
            name="CONDITION_SOURCE_TYPE_PICKPOCKETING_LOOT_TEMPLATE",
            SourceGroup="pickpocketing_loot_template.Entry OR reference_loot_template.Entry",
            SourceEntry="Item ID (pickpocketing_loot_template.Item or reference_loot_template.Item)",
            SourceId="Always 0",
            ConditionTarget="Always 0",
            Notes="Used for pickpocketing loot.",
        ),

        9: dict(
            name="CONDITION_SOURCE_TYPE_PROSPECTING_LOOT_TEMPLATE",
            SourceGroup="prospecting_loot_template.Entry OR reference_loot_template.Entry",
            SourceEntry="Item ID (prospecting_loot_template.Item or reference_loot_template.Item)",
            SourceId="Always 0",
            ConditionTarget="Always 0",
            Notes="Used for prospecting results.",
        ),

        10: dict(
            name="CONDITION_SOURCE_TYPE_REFERENCE_LOOT_TEMPLATE",
            SourceGroup="reference_loot_template.Entry",
            SourceEntry="Item ID (reference_loot_template.Item)",
            SourceId="Always 0",
            ConditionTarget="Always 0",
            Notes="Used for shared reference loot pools.",
        ),

        11: dict(
            name="CONDITION_SOURCE_TYPE_SKINNING_LOOT_TEMPLATE",
            SourceGroup="skinning_loot_template.Entry OR reference_loot_template.Entry",
            SourceEntry="Item ID (skinning_loot_template.Item or reference_loot_template.Item)",
            SourceId="Always 0",
            ConditionTarget="Always 0",
            Notes="Used for skinning loot.",
        ),

        12: dict(
            name="CONDITION_SOURCE_TYPE_SPELL_LOOT_TEMPLATE",
            SourceGroup="spell_loot_template.Entry OR reference_loot_template.Entry",
            SourceEntry="Item ID (spell_loot_template.Item or reference_loot_template.Item)",
            SourceId="Always 0",
            ConditionTarget="Always 0",
            Notes="Used for spell-triggered loot.",
        ),

        13: dict(
            name="CONDITION_SOURCE_TYPE_SPELL_IMPLICIT_TARGET",
            SourceGroup=(
                "Effect mask (bitmask):\n"
                "1 = EFFECT_0, 2 = EFFECT_1, 4 = EFFECT_2 ... 2^31 = EFFECT_31"
            ),
            SourceEntry="Spell ID",
            SourceId="Always 0",
            ConditionTarget="0 = Potential target\n1 = Spell caster",
            Notes="Do NOT rely on Wowhead effect counts; they may be incorrect.",
        ),

        14: dict(
            name="CONDITION_SOURCE_TYPE_GOSSIP_MENU",
            SourceGroup="gossip_menu.entry",
            SourceEntry="gossip_menu.text_id (npc_text.ID)",
            SourceId="Always 0",
            ConditionTarget="0 = Player\n1 = WorldObject",
            Notes="Controls gossip menu visibility.",
        ),

        15: dict(
            name="CONDITION_SOURCE_TYPE_GOSSIP_MENU_OPTION",
            SourceGroup="gossip_menu_option.menu_id",
            SourceEntry="gossip_menu_option.id",
            SourceId="Always 0",
            ConditionTarget="0 = Player\n1 = WorldObject",
            Notes="Controls individual gossip options.",
        ),

        16: dict(
            name="CONDITION_SOURCE_TYPE_CREATURE_TEMPLATE_VEHICLE",
            SourceGroup="Always 0",
            SourceEntry="creature_template.entry",
            SourceId="Always 0",
            ConditionTarget="0 = Player riding vehicle\n1 = Vehicle creature",
            Notes="Used for vehicle logic.",
        ),

        17: dict(
            name="CONDITION_SOURCE_TYPE_SPELL",
            SourceGroup="Always 0",
            SourceEntry="Spell ID",
            SourceId="Always 0",
            ConditionTarget="0 = Spell caster\n1 = Explicit target",
            Notes=(
                "Only explicit targets are affected.\n"
                "AoE/implicit targets require SPELL_IMPLICIT_TARGET.\n"
                "ElseGroup performs logical AND."
            ),
        ),

        18: dict(
            name="CONDITION_SOURCE_TYPE_SPELL_CLICK_EVENT",
            SourceGroup="npc_spellclick_spells.npc_entry",
            SourceEntry="npc_spellclick_spells.spell_id",
            SourceId="Always 0",
            ConditionTarget="0 = Clicker\n1 = Spellclick target",
            Notes="Used for spell-click NPCs.",
        ),

        19: dict(
            name="CONDITION_SOURCE_TYPE_QUEST_AVAILABLE",
            SourceGroup="Always 0",
            SourceEntry="quest_template.ID",
            SourceId="Always 0",
            ConditionTarget="Always 0",
            Notes="Controls quest availability.",
        ),

        21: dict(
            name="CONDITION_SOURCE_TYPE_VEHICLE_SPELL",
            SourceGroup="creature_template_spell.CreatureID",
            SourceEntry="creature_template_spell.Spell",
            SourceId="Always 0",
            ConditionTarget="0 = Player\n1 = Vehicle creature",
            Notes="Controls vehicle spell bar visibility.",
        ),

        22: dict(
            name="CONDITION_SOURCE_TYPE_SMART_EVENT",
            SourceGroup="smart_scripts.id + 1",
            SourceEntry="smart_scripts.entryorguid",
            SourceId="smart_scripts.source_type",
            ConditionTarget="0 = Invoker\n1 = Object",
            Notes="Used for SmartAI conditions.",
        ),

        23: dict(
            name="CONDITION_SOURCE_TYPE_NPC_VENDOR",
            SourceGroup="npc_vendor.entry",
            SourceEntry="npc_vendor.item",
            SourceId="Always 0",
            ConditionTarget="0 = Player\n1 = WorldObject",
            Notes="Controls vendor item visibility.",
        ),

        24: dict(
            name="CONDITION_SOURCE_TYPE_SPELL_PROC",
            SourceGroup="Always 0",
            SourceEntry="Spell ID of aura that triggers the proc",
            SourceId="Always 0",
            ConditionTarget="0 = Actor\n1 = ActionTarget",
            Notes="Used for proc conditions.",
        ),

        25: dict(
            name="CONDITION_SOURCE_TYPE_TERRAIN_SWAP",
            SourceGroup="Always 0",
            SourceEntry="terrain_swap_defaults.TerrainSwapMap",
            SourceId="Always 0",
            ConditionTarget="Always 0",
            Notes="Used for terrain swaps.",
        ),

        26: dict(
            name="CONDITION_SOURCE_TYPE_PHASE",
            SourceGroup="phase_area.PhaseId",
            SourceEntry="phase_area.AreaId (0 = any)",
            SourceId="Always 0",
            ConditionTarget="Always 0",
            Notes="Controls phase visibility.",
        ),

        27: dict(
            name="CONDITION_SOURCE_TYPE_GRAVEYARD",
            SourceGroup="graveyard_zone.GhostZone",
            SourceEntry="graveyard_zone.ID",
            SourceId="Always 0",
            ConditionTarget="Always 0",
            Notes="Controls graveyard usage.",
        ),

        28: dict(
            name="CONDITION_SOURCE_TYPE_AREATRIGGER",
            SourceGroup="areatrigger_template.Id",
            SourceEntry="areatrigger_template.IsCustom",
            SourceId="Always 0",
            ConditionTarget="Always 0",
            Notes="Used for area triggers.",
        ),

        29: dict(
            name="CONDITION_SOURCE_TYPE_CONVERSATION_LINE",
            SourceGroup="Always 0",
            SourceEntry="conversation_line_template.Id",
            SourceId="Always 0",
            ConditionTarget="Always 0",
            Notes="Used for conversation logic.",
        ),

        30: dict(
            name="CONDITION_SOURCE_TYPE_AREATRIGGER_CLIENT_TRIGGERED",
            SourceGroup="Always 0",
            SourceEntry="AreatriggerID",
            SourceId="Always 0",
            ConditionTarget="Always 0",
            Notes="Client-triggered areatriggers.",
        ),

        31: dict(
            name="CONDITION_SOURCE_TYPE_TRAINER_SPELL",
            SourceGroup="trainer_spell.TrainerId",
            SourceEntry="trainer_spell.SpellId",
            SourceId="Always 0",
            ConditionTarget="Always 0",
            Notes="Controls trainer spells.",
        ),

        32: dict(
            name="CONDITION_SOURCE_TYPE_OBJECT_ID_VISIBILITY",
            SourceGroup="ObjectType:\n5 = Unit\n8 = GameObject",
            SourceEntry="CreatureID / GameObjectID",
            SourceId="Always 0",
            ConditionTarget="0 = Player\n1 = WorldObject",
            Notes="Controls object visibility.",
        ),

        33: dict(
            name="CONDITION_SOURCE_TYPE_SPAWN_GROUP",
            SourceGroup="Always 0",
            SourceEntry="spawn_group_template.groupId",
            SourceId="Always 0",
            ConditionTarget="Always 0",
            Notes="Used for spawn groups.",
        ),

        34: dict(
            name="CONDITION_SOURCE_TYPE_PLAYER_CONDITION",
            SourceGroup="Always 0",
            SourceEntry="PlayerConditionID",
            SourceId="Always 0",
            ConditionTarget="Always 0",
            Notes="Links to PlayerCondition table.",
        ),

        35: dict(
            name="CONDITION_SOURCE_TYPE_SKILL_LINE_ABILITY",
            SourceGroup="Always 0",
            SourceEntry="ID from SkillLineAbility.db2",
            SourceId="Always 0",
            ConditionTarget="Always 0",
            Notes="Used for skill abilities.",
        ),

        36: dict(
            name="CONDITION_SOURCE_TYPE_PLAYER_CHOICE_RESPONSE",
            SourceGroup="playerchoice_response.ChoiceId",
            SourceEntry="playerchoice_response.ResponseId",
            SourceId="Always 0",
            ConditionTarget="Always 0",
            Notes="Used for player choice responses.",
        ),
    }

    # SourceType -> (Tab Label, loot table name)
    LOOT_TABS = {
        1:  ("Creature Loot",      "creature_loot_template"),
        2:  ("Disenchant Loot",    "disenchant_loot_template"),
        3:  ("Fishing Loot",       "fishing_loot_template"),
        4:  ("Object Loot",        "gameobject_loot_template"),
        5:  ("Item Loot",          "item_loot_template"),
        6:  ("Mail Loot",          "mail_loot_template"),
        7:  ("Milling Loot",       "milling_loot_template"),
        8:  ("Pickpocketing Loot", "pickpocketing_loot_template"),
        9:  ("Prospecting Loot",   "prospecting_loot_template"),
        10: ("Reference Loot",     "reference_loot_template"),
        11: ("Skinning Loot",      "skinning_loot_template"),
        12: ("Spell Loot",         "spell_loot_template"),
    }

    def __init__(self, db, log: Callable[[str], None], parent=None):
        super().__init__(parent)
        self.db = db
        self.log = log
        self.quest_id: Optional[int] = None
        self._is_loading: bool = False  # suppress auto-populate while loading from DB

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
        self.cond_table.cellDoubleClicked.connect(self._on_cond_cell_double_clicked)


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

        # --- Vertical splitter: conditions (top) / loot editors (bottom) ---
        split = QtWidgets.QSplitter(Qt.Orientation.Vertical)

        self.right_tabs = QtWidgets.QTabWidget()
        self._tab_for_source = {}
        self._editor_for_source = {}

        for st, (label, table) in sorted(self.LOOT_TABS.items()):
            ed = GenericLootEditor(self.db, self.log, table)
            idx = self.right_tabs.addTab(ed, label)
            self._tab_for_source[st] = idx
            self._editor_for_source[st] = ed

        split.addWidget(cond_widget)
        split.addWidget(self.right_tabs)

        # Give conditions MOST of the space
        split.setStretchFactor(0, 4)
        split.setStretchFactor(1, 2)

        # Initial size hint (adjust if needed)
        split.setSizes([700, 350])

        main = QtWidgets.QVBoxLayout(self)
        main.addWidget(split)

        self._last_loot_key: Optional[tuple[int, int]] = None  # (entry,item)
        # --- DBC picker caches (Spell/Faction/Currency) + unhandled picker tracking ---
        self._spell_rows: list[tuple[int, str]] = []
        self._spell_rank_by_id: dict[int, int] = {}

        self._faction_rows: list[tuple[int, str]] = []
        self._currency_rows: list[tuple[int, str]] = []

        self._picker_unhandled: set[str] = set()

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
            quest_types = (8, 9, 14, 28, 43, 47)
            ph = ",".join(["%s"] * len(quest_types))

            existing = self.db.fetch_all(
                f"""
                SELECT SourceTypeOrReferenceId, SourceGroup, SourceEntry
                FROM conditions
                WHERE ConditionTypeOrReference IN ({ph})
                  AND (
                        ConditionValue1 = %s
                     OR ConditionValue2 = %s
                     OR ConditionValue3 = %s
                  )
                """,
                (*quest_types, int(self.quest_id), int(self.quest_id), int(self.quest_id)),
            )

            have_pairs = {
                (int(r["SourceTypeOrReferenceId"]), int(r["SourceGroup"]), int(r["SourceEntry"]))
                for r in existing
            }

            row = self.db.fetch_one(
                f"""
                SELECT COALESCE(MAX(SourceId), 0) AS m
                FROM conditions
                WHERE ConditionTypeOrReference IN ({ph})
                  AND (
                        ConditionValue1 = %s
                     OR ConditionValue2 = %s
                     OR ConditionValue3 = %s
                  )
                """,
                (*quest_types, int(self.quest_id), int(self.quest_id), int(self.quest_id)),
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
    
    def _ensure_spell_rows(self) -> None:
        if self._spell_rows:
            return
        if config is None or not hasattr(config, "SPELL_DBC"):
            return
        p = Path(getattr(config, "SPELL_DBC"))
        if not p.exists():
            return
        try:
            self._spell_rows = load_wdbc_id_name(str(p))
        except Exception:
            self._spell_rows = []

        # Best-effort rank load from DB: spell_ranks(spell_id, rank)
        if not self._spell_rank_by_id:
            try:
                rs = self.db.fetch_all("SELECT spell_id, `rank` FROM spell_ranks")
                for r in rs:
                    sid = int(r.get("spell_id") or 0)
                    rk = int(r.get("rank") or 0)
                    if sid > 0 and rk > 0:
                        self._spell_rank_by_id[sid] = rk
            except Exception:
                pass

    def _ensure_faction_rows(self) -> None:
        if self._faction_rows:
            return
        if config is None or not hasattr(config, "FACTION_DBC"):
            return
        p = Path(getattr(config, "FACTION_DBC"))
        if not p.exists():
            return
        try:
            # You said: Faction.dbc name is field23
            self._faction_rows = load_wdbc_id_name(str(p), name_field_index=23)
        except Exception:
            self._faction_rows = []

    def _ensure_currency_rows(self) -> None:
        if self._currency_rows:
            return
        if config is None or not hasattr(config, "CURRENCYTYPES_DBC"):
            return
        p = Path(getattr(config, "CURRENCYTYPES_DBC"))
        if not p.exists():
            return
        try:
            self._currency_rows = load_wdbc_id_name(str(p))
        except Exception:
            self._currency_rows = []

    def _log_unhandled_picker(self, msg: str) -> None:
        # Deduplicate + log
        if msg in self._picker_unhandled:
            return
        self._picker_unhandled.add(msg)
        self.log(f"[Picker] No handler: {msg}")

    def _update_condition_display_cols(self, row: int) -> None:
        """
        Refresh any 'display' columns that show resolved names for the given
        conditions row (quest name, item name, faction name, spell name, etc.)
        after a picker changes an ID.
        Safe no-op if the display columns aren't present.
        """
        try:
            # If you already have a centralized refresh for the row, use it.
            # Many versions use _refresh_condition_row_display(row) or similar.
            fn = getattr(self, "_refresh_condition_row_display", None)
            if callable(fn):
                fn(row)
                return

            # Otherwise: do the minimal safe thing—re-run whatever you use to
            # rebuild display columns for the whole table, if it exists.
            fn2 = getattr(self, "_refresh_conditions_display", None)
            if callable(fn2):
                fn2()
                return

        except Exception:
            pass

    def _on_cond_cell_double_clicked(self, row, col_idx):
        if col_idx >= len(self.COND_COLS):
            return

        col = self.COND_COLS[col_idx]

        def cur_int(col_name: str) -> int:
            try:
                it = self.cond_table.item(row, self.COND_COLS.index(col_name))
                return int((it.text() or "0").strip()) if it else 0
            except Exception:
                return 0

        def setv(v: int) -> None:
            it = self.cond_table.item(row, col_idx)
            if it:
                it.setText(str(int(v)))
            else:
                self.cond_table.setItem(row, col_idx, QtWidgets.QTableWidgetItem(str(int(v))))
            self._update_condition_display_cols(row)

        st = cur_int("SourceTypeOrReferenceId")
        ct = cur_int("ConditionTypeOrReference")

        # -------------------------
        # SourceGroup picker
        # -------------------------
        if col == "SourceGroup":
            # Loot-template sources: SourceGroup is the "entry" key of that loot template.
            # For common loot templates, that entry is usually:
            #  1 (CreatureLoot): creature_template.entry
            #  4 (GO Loot): gameobject_template.entry
            #  5 (Item Loot): item_template.entry
            if st == 1:
                dlg = LootIDPickerDialog(self.db, "creature", self)
                if dlg.exec() and dlg.selected_id():
                    setv(dlg.selected_id())
                return

            if st == 4:
                dlg = LootIDPickerDialog(self.db, "go", self)
                if dlg.exec() and dlg.selected_id():
                    setv(dlg.selected_id())
                return

            if st == 5:
                dlg = LootIDPickerDialog(self.db, "item", self)
                if dlg.exec() and dlg.selected_id():
                    setv(dlg.selected_id())
                return

            # For other loot templates, SourceGroup is still an "entry", but may not map cleanly
            # to creature/go/item. We leave unhandled (as requested).
            self._log_unhandled_picker(f"col=SourceGroup st={st} ct={ct}")
            return

        # -------------------------
        # SourceEntry picker
        # -------------------------
        if col == "SourceEntry":
            # For loot templates and most condition sources, SourceEntry is an ItemId
            # (loot_template.item or reference_loot_template.item)
            if st in self.LOOT_TABS:
                dlg = LootIDPickerDialog(self.db, "item", self)
                if dlg.exec() and dlg.selected_id():
                    setv(dlg.selected_id())
                return

            # Some SourceTypes use SourceEntry differently; leave unhandled.
            self._log_unhandled_picker(f"col=SourceEntry st={st} ct={ct}")
            return

        # -------------------------
        # ConditionValue1 picker (based on ConditionType)
        # -------------------------
        if col == "ConditionValue1":
            # Quest-related types: open quest picker
            if ct in self.QUEST_TYPES_NEED_QUEST_ID:
                dlg = LootIDPickerDialog(self.db, "quest", self)
                if dlg.exec() and dlg.selected_id():
                    setv(dlg.selected_id())
                return

            # Item conditions (has item / equipped): item_template.entry
            if ct in (2, 3):
                dlg = LootIDPickerDialog(self.db, "item", self)
                if dlg.exec() and dlg.selected_id():
                    setv(dlg.selected_id())
                return

            # Near creature / near gameobject
            if ct == 29:
                dlg = LootIDPickerDialog(self.db, "creature", self)
                if dlg.exec() and dlg.selected_id():
                    setv(dlg.selected_id())
                return

            if ct == 30:
                dlg = LootIDPickerDialog(self.db, "go", self)
                if dlg.exec() and dlg.selected_id():
                    setv(dlg.selected_id())
                return

            # Reputation rank: faction id (Faction.dbc)
            if ct == 5:
                self._ensure_faction_rows()
                if not self._faction_rows:
                    self.log("[Picker] Faction.dbc not available; cannot open faction picker.")
                    return
                dlg = DBCIdPickerDialog("Pick Faction", self._faction_rows, self)
                if dlg.exec() == QtWidgets.QDialog.DialogCode.Accepted and dlg.chosen_id() is not None:
                    setv(int(dlg.chosen_id()))
                return

            # Spell-based conditions: Spell.dbc (+ show rank if known)
            if ct in (1, 25):
                self._ensure_spell_rows()
                if not self._spell_rows:
                    self.log("[Picker] Spell.dbc not available; cannot open spell picker.")
                    return

                # decorate spell names with rank if present
                rows = []
                for sid, nm in self._spell_rows:
                    rk = self._spell_rank_by_id.get(int(sid), 0)
                    rows.append((int(sid), f"{nm}{f' (Rank {rk})' if rk else ''}"))

                dlg = DBCIdPickerDialog("Pick Spell", rows, self)
                if dlg.exec() == QtWidgets.QDialog.DialogCode.Accepted and dlg.chosen_id() is not None:
                    setv(int(dlg.chosen_id()))
                return

            # Unknown / not implemented
            self._log_unhandled_picker(f"col=ConditionValue1 ct={ct} st={st}")
            return

        # Everything else: do nothing
        return

    # -------------------------
    # Conditions
    # -------------------------
    def _load_conditions(self) -> None:
        assert self.quest_id is not None
        cols = "c." + ",c.".join(self.COND_COLS)

        # 1) Find all condition "groups" (same source key) anchored by:
        #    ConditionType=2 (Player has quest) and ConditionValue1 = quest_id
        quest_types = (8, 9, 14, 28, 43, 47)
        ph = ",".join(["%s"] * len(quest_types))

        keys = self.db.fetch_all(
            f"""
            SELECT DISTINCT
              SourceTypeOrReferenceId, SourceGroup, SourceEntry, SourceId
            FROM conditions
            WHERE ConditionTypeOrReference IN ({ph})
              AND (
                    ConditionValue1 = %s
                 OR ConditionValue2 = %s
                 OR ConditionValue3 = %s
              )
            """,
            (*quest_types, int(self.quest_id), int(self.quest_id), int(self.quest_id)),
        )


        # If there are no anchor rows, show nothing (correct) but log why
        if not keys:
            self.cond_table.setRowCount(0)
            self.log(f"Loaded 0 condition row(s) for quest {self.quest_id} (no quest-related condition types found: {quest_types}).")
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

        self._is_loading = True
        self.cond_table.setRowCount(0)
        for r in rows:
            self._append_condition_row(r)
        self._is_loading = False

        self.log(f"Loaded {len(rows)} condition row(s) for quest {self.quest_id} across {len(keys)} source group(s).")
    
    def _apply_src_tooltip_to_row(self, row_idx: int) -> None:
        col = self.COND_COLS.index("SourceTypeOrReferenceId")
        w = self.cond_table.cellWidget(row_idx, col)
        if not isinstance(w, QtWidgets.QComboBox):
            return

        st = int(w.currentData() or 0)
        info = self.SRC_TOOLTIP_MAP.get(st)

        if not info:
            tip = self.SRC_TOOLTIP_HEADER + f"\n\n(Unknown SourceTypeOrReferenceId: {st})"
        else:
            parts = [
                self.SRC_TOOLTIP_HEADER,
                "",
                f"{st} = {info.get('name','')}",
                "",
                f"SourceGroup: {info.get('SourceGroup','')}",
                f"SourceEntry: {info.get('SourceEntry','')}",
                f"SourceId: {info.get('SourceId','')}",
                f"ConditionTarget: {info.get('ConditionTarget','')}",
            ]
            notes = (info.get("Notes") or "").strip()
            if notes:
                parts += ["", f"Notes: {notes}"]
            tip = "\n".join(parts).strip()

        # IMPORTANT: tooltip must be on the dropdown widget
        w.setToolTip(tip)

        # Optional: also set on the backing item (won’t show when hovering widget, but harmless)
        it = self.cond_table.item(row_idx, col)
        if it:
            it.setToolTip(tip)

    def _build_choice_combo(self, choices: list[tuple[int, str]], cur: int) -> QtWidgets.QComboBox:
        cb = QtWidgets.QComboBox()

        # Add known choices
        for v, name in choices:
            cb.addItem(f"{v} - {name}", v)

        # Try to find existing value
        idx = cb.findData(cur)

        # Known value
        if idx >= 0:
            cb.setCurrentIndex(idx)
            return cb

        # Negative values = reference
        if cur < 0:
            cb.insertItem(0, f"{cur} - Reference", cur)
            cb.setCurrentIndex(0)
            return cb

        # Unknown positive value
        cb.insertItem(0, f"{cur} - Unknown", cur)
        cb.setCurrentIndex(0)
        return cb
    
    def _current_loot_editor(self) -> Optional[GenericLootEditor]:
        st = self._selected_source_type()
        return self._editor_for_source.get(st)

    def save_loot(self) -> None:
        """
        Save loot row using the active GenericLootEditor (source of truth).
        """
        ed = self._current_loot_editor()
        if not ed:
            QtWidgets.QMessageBox.information(self, "No loot editor", "This SourceType has no loot editor tab.")
            return

        key = self._selected_loot_key()
        if not key:
            QtWidgets.QMessageBox.information(self, "No key", "Select a condition row with SourceGroup/SourceEntry > 0.")
            return

        entry, item = key
        ed.set_key(entry, item)
        ed.save_current()  # GenericLootEditor should upsert
        self.log(f"Saved loot via GenericLootEditor: entry={entry} item={item}")

    def create_loot_row_if_missing(self) -> None:
        """
        In the new model, 'save_current' can act as 'create if missing' (upsert).
        """
        ed = self._current_loot_editor()
        if not ed:
            QtWidgets.QMessageBox.information(self, "No loot editor", "This SourceType has no loot editor tab.")
            return

        key = self._selected_loot_key()
        if not key:
            QtWidgets.QMessageBox.information(self, "No selection", "Select a condition row first.")
            return

        entry, item = key
        ed.set_key(entry, item)

        # If your GenericLootEditor has a load check, use it; otherwise just upsert.
        ed.save_current()
        self.log(f"Created/updated loot via GenericLootEditor: entry={entry} item={item}")

    def _append_condition_row(self, r: Dict[str, Any]) -> None:
        row = self.cond_table.rowCount()
        self.cond_table.insertRow(row)

        # Write DB columns first
        for i, col in enumerate(self.COND_COLS):
            val = r.get(col)
            txt = "" if val is None else str(val)

            # Dropdown for SourceTypeOrReferenceId
            if col == "SourceTypeOrReferenceId":
                try:
                    cur = int(txt.strip() or "0")
                except Exception:
                    cur = 0

                cb = self._build_choice_combo(self.SRC_TYPE_CHOICES, cur)

                # IMPORTANT: don't allow signals during row build/load
                cb.blockSignals(True)
                self.cond_table.setCellWidget(row, i, cb)
                cb.blockSignals(False)

                # Keep raw value in the cell item too (used by your _cond_row_dict and sorting/visibility)
                self.cond_table.setItem(row, i, QtWidgets.QTableWidgetItem(str(cur)))

                # Connect AFTER the widget is placed (and after initial selection is set)
                cb.currentIndexChanged.connect(lambda _=None, cb=cb: self._on_source_type_changed(cb))
                continue

            # Dropdown for ConditionTypeOrReference
            if col == "ConditionTypeOrReference":
                try:
                    cur = int(txt.strip() or "0")
                except Exception:
                    cur = 0

                cb = self._build_choice_combo(self.COND_TYPE_CHOICES, cur)

                # IMPORTANT: don't allow signals during row build/load
                cb.blockSignals(True)
                self.cond_table.setCellWidget(row, i, cb)
                cb.blockSignals(False)

                # Keep raw value in the cell item too
                self.cond_table.setItem(row, i, QtWidgets.QTableWidgetItem(str(cur)))

                # Connect AFTER the widget is placed (and after initial selection is set)
                cb.currentIndexChanged.connect(lambda _=None, cb=cb: self._on_cond_type_changed(cb))
                continue

            self.cond_table.setItem(row, i, QtWidgets.QTableWidgetItem(txt))

        # Then display-only columns
        for j, col in enumerate(self.COND_DISPLAY_COLS):
            idx = len(self.COND_COLS) + j
            val = r.get(col, "")
            item = QtWidgets.QTableWidgetItem("" if val is None else str(val))
            item.setFlags(item.flags() & ~Qt.ItemFlag.ItemIsEditable)  # read-only
            self.cond_table.setItem(row, idx, item)
        self._refresh_condition_tooltips(row)


    def _on_source_type_changed(self, cb: QtWidgets.QComboBox) -> None:
        # Find owning row
        row_idx = -1
        col_idx = self.COND_COLS.index("SourceTypeOrReferenceId")
        for r in range(self.cond_table.rowCount()):
            if self.cond_table.cellWidget(r, col_idx) is cb:
                row_idx = r
                break
        if row_idx < 0:
            return

        st = int(cb.currentData() or 0)

        # Sync backing cell text
        it = self.cond_table.item(row_idx, col_idx)
        if it:
            it.setText(str(st))

        # Refresh ALL tooltips for the row (includes SourceType tooltip)
        self._refresh_condition_tooltips(row_idx)

        # Jump to correct loot tab
        if hasattr(self, "_tab_for_source") and st in getattr(self, "_tab_for_source", {}):
            self.right_tabs.setCurrentIndex(self._tab_for_source[st])

    def _get_cell_int(self, row: int, col_name: str, default: int = 0) -> int:
        col = self.COND_COLS.index(col_name)
        it = self.cond_table.item(row, col)
        if not it:
            return default
        try:
            return int((it.text() or "").strip() or default)
        except Exception:
            return default

    def _ensure_cell(self, row: int, col_name: str) -> QtWidgets.QTableWidgetItem:
        col = self.COND_COLS.index(col_name)
        it = self.cond_table.item(row, col)
        if it is None:
            it = QtWidgets.QTableWidgetItem("")
            self.cond_table.setItem(row, col, it)
        return it

    def _apply_source_type_defaults(self, row_idx: int, stype: int) -> None:
        """
        Apply SourceTypeOrReferenceId rules ONLY when the user changes SourceTypeOrReferenceId.
        Do NOT overwrite values the user already set (only fill if empty/0).
        """
        # Negative = reference id -> don't auto-force anything
        if stype < 0:
            return

        # Most loot-style SourceTypes want SourceId=0 and ConditionTarget=0
        # (Also matches your table for 1..12 and most others)
        if self._get_cell_int(row_idx, "SourceId", 0) != 0:
            # Only force to 0 if user hasn't typed something meaningful.
            # If you want to ALWAYS force SourceId=0 for positive types, remove this guard.
            pass
        else:
            self._set_cell_int(row_idx, "SourceId", 0)

        # ConditionTarget: default to 0 unless SourceType expects otherwise
        if self._get_cell_int(row_idx, "ConditionTarget", 0) == 0:
            self._set_cell_int(row_idx, "ConditionTarget", 0)

        # SourceType-specific ConditionTarget defaults (only if currently 0)
        # 13, 14, 15, 16, 17, 18, 21, 22, 23, 24, 32 have documented targets
        if stype in (13, 14, 15, 16, 17, 18, 21, 22, 23, 24, 32):
            # Keep whatever user already set (non-zero). Otherwise leave at 0.
            if self._get_cell_int(row_idx, "ConditionTarget", 0) == 0:
                self._set_cell_int(row_idx, "ConditionTarget", 0)

        # SourceType=0 "NONE": these columns are "never used" – optional cleanup
        # Only clear if currently empty/0, so we don't destroy loaded DB values.
        if stype == 0:
            for cn in ("SourceGroup", "SourceEntry", "SourceId", "ElseGroup"):
                if self._get_cell_int(row_idx, cn, 0) == 0:
                    self._set_cell_int(row_idx, cn, 0)

    def _apply_condition_type_defaults(self, row_idx: int, ctype: int) -> None:
        """
        Apply ConditionTypeOrReference rules ONLY when the user changes ConditionTypeOrReference.
        Do NOT overwrite user-entered values (only fill if empty/0/blank).
        """
        # Negative = reference -> don't auto-force anything
        if ctype < 0:
            return

        # Always-safe defaults if empty/0
        if self._get_cell_int(row_idx, "ConditionTarget", 0) == 0:
            self._set_cell_int(row_idx, "ConditionTarget", 0)
        if self._get_cell_int(row_idx, "NegativeCondition", 0) == 0:
            self._set_cell_int(row_idx, "NegativeCondition", 0)
        if self._get_cell_int(row_idx, "ElseGroup", 0) == 0:
            self._set_cell_int(row_idx, "ElseGroup", 0)

        # Helper: only set CV if currently empty/0
        def set_cv_if_empty(col_name: str, value: int) -> None:
            cur = self._get_cell_int(row_idx, col_name, 0)
            if cur == 0:
                self._set_cell_int(row_idx, col_name, value)

        # Default CV2/CV3 to 0 unless needed
        set_cv_if_empty("ConditionValue2", 0)
        set_cv_if_empty("ConditionValue3", 0)

        # Now apply per-type rules (from your table)
        # 1 AURA: CV1=SpellID (unknown), CV2=effect index (0..31), CV3=0
        if ctype == 1:
            set_cv_if_empty("ConditionValue2", 0)
            set_cv_if_empty("ConditionValue3", 0)
            return

        # 2 ITEM: CV1=item entry (unknown), CV2=count default 1, CV3=bank flag default 0
        if ctype == 2:
            set_cv_if_empty("ConditionValue2", 1)
            set_cv_if_empty("ConditionValue3", 0)
            return

        # 3 ITEM_EQUIPPED: CV1=item entry, CV2/CV3=0
        if ctype == 3:
            set_cv_if_empty("ConditionValue2", 0)
            set_cv_if_empty("ConditionValue3", 0)
            return

        # 4 ZONEID: CV1=zone id, CV2/CV3=0
        if ctype == 4:
            set_cv_if_empty("ConditionValue2", 0)
            set_cv_if_empty("ConditionValue3", 0)
            return

        # 5 REPUTATION_RANK: CV1=faction template id, CV2=rank mask, CV3=0
        if ctype == 5:
            # CV2 can't be guessed safely; leave if user hasn't filled it (0)
            set_cv_if_empty("ConditionValue3", 0)
            return

        # 6 TEAM: CV1 team id (469/67), others 0
        if ctype == 6:
            set_cv_if_empty("ConditionValue2", 0)
            set_cv_if_empty("ConditionValue3", 0)
            return

        # 7 SKILL: CV1 skill id, CV2 required rank, CV3 0
        if ctype == 7:
            # CV2 default can't be assumed; leave 0 unless you want default 1
            set_cv_if_empty("ConditionValue3", 0)
            return

        # 8/9/14/28/43/47: quest id in CV1 is usually the current quest (safe if quest loaded)
        if ctype in (8, 9, 14, 28, 43, 47):
            if self.quest_id is not None:
                set_cv_if_empty("ConditionValue1", int(self.quest_id))
            set_cv_if_empty("ConditionValue2", 0)
            set_cv_if_empty("ConditionValue3", 0)
            return

        # 10 DRUNKENSTATE: CV1 state 0..3
        if ctype == 10:
            set_cv_if_empty("ConditionValue2", 0)
            set_cv_if_empty("ConditionValue3", 0)
            return

        # 11 WORLD_STATE: CV1 index, CV2 value, CV3 0
        if ctype == 11:
            set_cv_if_empty("ConditionValue3", 0)
            return

        # 12 ACTIVE_EVENT: CV1 eventEntry
        if ctype == 12:
            set_cv_if_empty("ConditionValue2", 0)
            set_cv_if_empty("ConditionValue3", 0)
            return

        # 13 INSTANCE_INFO: CV1 entry, CV2 data, CV3 mode default 0
        if ctype == 13:
            set_cv_if_empty("ConditionValue3", 0)
            return

        # 15 CLASS, 16 RACE, 45 PET_TYPE, 52 TYPE_MASK: CV1 mask
        if ctype in (15, 16, 45, 52):
            set_cv_if_empty("ConditionValue2", 0)
            set_cv_if_empty("ConditionValue3", 0)
            return

        # 17 ACHIEVEMENT, 18 TITLE, 25 SPELL: CV1 id, others 0
        if ctype in (17, 18, 25):
            set_cv_if_empty("ConditionValue2", 0)
            set_cv_if_empty("ConditionValue3", 0)
            return

        # 19 is deprecated/unused: don't auto-fill anything
        if ctype == 19:
            return

        # 20 GENDER: CV1 default 0 (Male)
        if ctype == 20:
            set_cv_if_empty("ConditionValue2", 0)
            set_cv_if_empty("ConditionValue3", 0)
            return

        # 27 LEVEL: CV1 level, CV2 compare type default 0 (equal), CV3 0
        if ctype == 27:
            set_cv_if_empty("ConditionValue2", 0)
            set_cv_if_empty("ConditionValue3", 0)
            return

        # 29 NEAR_CREATURE: CV1 creature entry, CV2 dist default 5, CV3 alive/dead default 0
        if ctype == 29:
            set_cv_if_empty("ConditionValue2", 5)
            set_cv_if_empty("ConditionValue3", 0)
            return

        # 30 NEAR_GAMEOBJECT: CV1 go entry, CV2 dist default 5, CV3 0
        if ctype == 30:
            set_cv_if_empty("ConditionValue2", 5)
            set_cv_if_empty("ConditionValue3", 0)
            return

        # 33/34/35 use CV2 for relation/rank/compare, set CV3=0
        if ctype in (33, 34, 35):
            set_cv_if_empty("ConditionValue3", 0)
            return

        # 36 ALIVE: CV1 always 0, use NegativeCondition (0=alive,1=dead)
        if ctype == 36:
            set_cv_if_empty("ConditionValue1", 0)
            set_cv_if_empty("ConditionValue2", 0)
            set_cv_if_empty("ConditionValue3", 0)
            # Don't force NegativeCondition; leave whatever user wants (0 default already set)
            return

        # 37 HP_VAL / 38 HP_PCT: CV1 value, CV2 compare type default 0, CV3 0
        if ctype in (37, 38):
            set_cv_if_empty("ConditionValue2", 0)
            set_cv_if_empty("ConditionValue3", 0)
            return

        # 40 IN_WATER: CV1..3 unused, use NegativeCondition (0 land,1 water)
        if ctype == 40:
            set_cv_if_empty("ConditionValue1", 0)
            set_cv_if_empty("ConditionValue2", 0)
            set_cv_if_empty("ConditionValue3", 0)
            return

        # 42 STAND_STATE: CV1 stateType default 0, CV2 stand state default 0, CV3 0
        if ctype == 42:
            set_cv_if_empty("ConditionValue1", 0)
            set_cv_if_empty("ConditionValue2", 0)
            set_cv_if_empty("ConditionValue3", 0)
            return

        # 48 QUEST_OBJECTIVE_PROGRESS: CV1 objective id, CV3 progress value, CV2 0
        if ctype == 48:
            set_cv_if_empty("ConditionValue2", 0)
            # CV3 can't be guessed; leave 0
            return

        # Anything else: keep CV2/CV3 at 0 only if empty

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

        # All DB fields default to 0 (or empty strings where appropriate)
        r: Dict[str, Any] = {c: 0 for c in self.COND_COLS}

        # Anchor this condition group to the quest (keep your established method)
        r["ConditionTypeOrReference"] = self.ANCHOR_COND_TYPE  # typically 9 (QUESTTAKEN)
        r["ConditionValue1"] = int(self.quest_id)

        # SourceId is almost always 0 in real DB usage
        r["SourceId"] = 0

        # These are text fields in your schema
        r["ScriptName"] = ""
        r["Comment"] = ""

        # Append + select
        self._append_condition_row(r)
        new_row = self.cond_table.rowCount() - 1
        self.cond_table.setCurrentCell(new_row, 0)
        self.cond_table.scrollToItem(self.cond_table.item(new_row, 0))

        # Tooltips (safe now because new_row always exists)
        self._refresh_condition_tooltips(new_row)

        self.log("Added new condition row (all defaults = 0, SourceId=0).")

    def save_condition_selected(self) -> None:
        if self.quest_id is None:
            QtWidgets.QMessageBox.information(self, "No quest", "Load a quest first.")
            return

        row = self._selected_condition_row()
        if row < 0:
            QtWidgets.QMessageBox.information(self, "Pick a row", "Select a condition row to save.")
            return

        d = self._cond_row_dict(row)

        # ---- Normalize ints (prevents None/"" issues) ----
        def _i(key: str, default: int = 0) -> int:
            try:
                return int((d.get(key, default) or default))
            except Exception:
                return default

        # Always keep quest anchored properly (ONLY if user left it empty/zero)
        ctype = _i("ConditionTypeOrReference", 0)
        if ctype == self.ANCHOR_COND_TYPE and _i("ConditionValue1", 0) <= 0:
            d["ConditionValue1"] = int(self.quest_id)

        # SourceId is almost always 0; do not force uniqueness
        # If user left it blank/None, normalize to 0.
        d["SourceId"] = _i("SourceId", 0)

        # Also normalize other numeric fields that often come in as "" / None
        for k in (
            "SourceTypeOrReferenceId", "SourceGroup", "SourceEntry", "ElseGroup",
            "ConditionTarget", "ConditionValue1", "ConditionValue2", "ConditionValue3",
            "NegativeCondition", "ErrorType", "ErrorTextId",
        ):
            d[k] = _i(k, 0)

        # Text fields
        d["ScriptName"] = "" if d.get("ScriptName") is None else str(d.get("ScriptName"))
        d["Comment"] = "" if d.get("Comment") is None else str(d.get("Comment"))

        # ---- Minimal sanity checks (loot templates need SG/SE) ----
        stype = _i("SourceTypeOrReferenceId", 0)

        # Apply check to all loot-template source types you’re building tabs for:
        # 1..12 correspond to *_loot_template / reference_loot_template usage.
        if stype in self.LOOT_TABS:
            if d["SourceGroup"] <= 0:
                QtWidgets.QMessageBox.warning(self, "Missing SourceGroup", "Set SourceGroup (template entry).")
                return
            if d["SourceEntry"] <= 0:
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
                f"ST={d['SourceTypeOrReferenceId']} SG={d['SourceGroup']} SE={d['SourceEntry']} "
                f"CT={d['ConditionTypeOrReference']} Q={d['ConditionValue1']} SourceId={d['SourceId']}"
            )

            # Reload so display columns refresh
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

        # Don't do anything else while loading rows from DB
        if self._is_loading:
            return

        # NO AUTO-FILL. Only refresh tooltips based on the selected type.
        self._refresh_condition_tooltips(row_idx)

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
                if st in self.LOOT_TABS and sg > 0 and se > 0:
                    table = self.LOOT_TABS[st][1]
                    self.db.execute(
                        f"DELETE FROM {table} WHERE entry=%s AND item=%s",
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

    def _on_condition_selected(self) -> None:
        row = self._selected_condition_row()
        if row < 0:
            return

        d = self._cond_row_dict(row)
        st = int(d.get("SourceTypeOrReferenceId", 0) or 0)
        sg = int(d.get("SourceGroup", 0) or 0)
        se = int(d.get("SourceEntry", 0) or 0)

        # Always update tooltips for the selected row
        self._refresh_condition_tooltips(row)

        # Jump to loot tab (if this SourceType maps to a loot template)
        if st in self._tab_for_source:
            self.right_tabs.setCurrentIndex(self._tab_for_source[st])

            ed = self._editor_for_source.get(st)
            if ed:
                ed.set_key(sg, se)

                # Optional: auto-load if key is valid
                if sg > 0 and se > 0:
                    ed.load_current()
                else:
                    ed.clear()
        else:
            # Non-loot SourceType: do nothing special on right side
            pass
    
    def _refresh_condition_tooltips(self, row_idx: int) -> None:
        """
        Apply per-field tooltips based on the current SourceTypeOrReferenceId and ConditionTypeOrReference.
        No values are auto-changed here — tooltips only.
        """
        if row_idx < 0 or row_idx >= self.cond_table.rowCount():
            return

        # Prefer reading from dropdown widgets (source of truth)
        st = 0
        ct = 0

        # --- SourceTypeOrReferenceId ---
        try:
            st_col = self.COND_COLS.index("SourceTypeOrReferenceId")
            st_w = self.cond_table.cellWidget(row_idx, st_col)
            if isinstance(st_w, QtWidgets.QComboBox):
                st = int(st_w.currentData() or 0)
            else:
                it = self.cond_table.item(row_idx, st_col)
                st = int((it.text() if it else "0").strip() or "0")
        except Exception:
            st = 0

        # --- ConditionTypeOrReference ---
        try:
            ct_col = self.COND_COLS.index("ConditionTypeOrReference")
            ct_w = self.cond_table.cellWidget(row_idx, ct_col)
            if isinstance(ct_w, QtWidgets.QComboBox):
                ct = int(ct_w.currentData() or 0)
            else:
                it = self.cond_table.item(row_idx, ct_col)
                ct = int((it.text() if it else "0").strip() or "0")
        except Exception:
            ct = 0

        # =========================
        # SourceType tooltips
        # =========================
        if st < 0:
            st_tip = (
                "SourceTypeOrReferenceId is NEGATIVE:\n"
                "• This is a reference id.\n"
                "• It is referenced directly in ConditionTypeOrReference of another condition.\n"
                "• SourceGroup/SourceEntry meaning is defined by the referenced rule.\n"
            )
        else:
            info = self.SRC_TOOLTIP_MAP.get(st)
            if info:
                name = info.get("name", f"SourceType {st}")
                sg = info.get("SourceGroup", "")
                se = info.get("SourceEntry", "")
                sid = info.get("SourceId", "")
                tgt = info.get("ConditionTarget", "")
                notes = info.get("Notes", "")

                st_tip = (
                    f"{name}\n\n"
                    "What goes where:\n"
                    f"• SourceGroup = {sg}\n"
                    f"• SourceEntry = {se}\n"
                    f"• SourceId = {sid}\n"
                    f"• ConditionTarget = {tgt}\n"
                    + (f"\nNotes:\n{notes}\n" if notes else "")
                )
            else:
                st_tip = self.SRC_TOOLTIP_HEADER

        # Apply tooltip to SourceType dropdown widget
        try:
            col = self.COND_COLS.index("SourceTypeOrReferenceId")
            w = self.cond_table.cellWidget(row_idx, col)
            if w:
                w.setToolTip(st_tip)
        except Exception:
            pass

        # Apply tooltips to SourceGroup/SourceEntry/SourceId/ConditionTarget cells
        for field in ("SourceGroup", "SourceEntry", "SourceId", "ConditionTarget"):
            try:
                col = self.COND_COLS.index(field)
                item = self.cond_table.item(row_idx, col)
                if not item:
                    item = QtWidgets.QTableWidgetItem("")
                    self.cond_table.setItem(row_idx, col, item)

                if st < 0:
                    item.setToolTip("Reference-based SourceType (negative). Meaning depends on reference usage.")
                else:
                    info = self.SRC_TOOLTIP_MAP.get(st, {})
                    item.setToolTip(f"{field}:\n{info.get(field, '')}".strip())
            except Exception:
                pass

        # =========================
        # ConditionType tooltips
        # =========================
        if ct < 0:
            ct_tip = (
                "ConditionTypeOrReference is NEGATIVE:\n"
                "• This is a reference to another condition.\n"
                "• ConditionValue1/2/3 meaning depends on the referenced rule.\n"
            )
        else:
            info = self.COND_TOOLTIP_MAP.get(ct)
            if info:
                ct_tip = (
                    f"{info.get('name','')}\n\n"
                    f"CV1: {info.get('ConditionValue1','')}\n"
                    f"CV2: {info.get('ConditionValue2','')}\n"
                    f"CV3: {info.get('ConditionValue3','')}\n"
                    + (f"\nUsage: {info.get('Usage','')}\n" if info.get("Usage") else "")
                )
            else:
                ct_tip = self.COND_TOOLTIP_HEADER

        # Apply tooltip to ConditionType dropdown widget
        try:
            col = self.COND_COLS.index("ConditionTypeOrReference")
            w = self.cond_table.cellWidget(row_idx, col)
            if w:
                w.setToolTip(ct_tip)
        except Exception:
            pass

        # Apply tooltips to ConditionValue1/2/3 cells
        for field in ("ConditionValue1", "ConditionValue2", "ConditionValue3"):
            try:
                col = self.COND_COLS.index(field)
                item = self.cond_table.item(row_idx, col)
                if not item:
                    item = QtWidgets.QTableWidgetItem("")
                    self.cond_table.setItem(row_idx, col, item)

                if ct < 0:
                    item.setToolTip("Reference-based ConditionType (negative). Meaning depends on referenced rule.")
                else:
                    info = self.COND_TOOLTIP_MAP.get(ct, {})
                    item.setToolTip(f"{field}:\n{info.get(field,'')}".strip())
            except Exception:
                pass

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
    
    def clear_loot_form(self) -> None:
        """
        Old UI used self.loot_inputs dict. New UI uses tabbed GenericLootEditor(s).
        Clear whichever loot editor is currently selected.
        """
        # If tabs not built yet, nothing to clear
        if not hasattr(self, "right_tabs"):
            return

        w = self.right_tabs.currentWidget()
        if w is None:
            return

        # GenericLootEditor has clear() in our new model
        if hasattr(w, "clear") and callable(getattr(w, "clear")):
            w.clear()
            return

        # Fallback: if editor has clear_form()
        if hasattr(w, "clear_form") and callable(getattr(w, "clear_form")):
            w.clear_form()
            return

