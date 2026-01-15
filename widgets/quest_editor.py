from __future__ import annotations
from typing import Any, Callable, Dict, List, Optional, Tuple
from dataclasses import dataclass
from PyQt6 import QtWidgets, QtCore
from PyQt6.QtCore import Qt
from PyQt6.QtCore import QTimer
from PyQt6.QtCore import pyqtSignal
from PyQt6.QtWidgets import QDialog, QTextBrowser

from db import Database
import struct
from pathlib import Path

from metadata import QUEST_TABS
from widgets.loot_editor import QuestLootEditor

from PyQt6.QtGui import QKeySequence, QShortcut

try:
    import config
except Exception:
    config = None
    
def load_skillline_dbc(path: str) -> list[tuple[int, str]]:
    """
    Reader for your SkillLine.dbc (WDBC, 7 fields, 28-byte records).
    Layout (based on your uploaded file):
      cols[0] = ID
      cols[2] = Name string offset
      cols[3] = Description string offset
    Returns [(id, name), ...]
    """
    import struct

    rows: list[tuple[int, str]] = []

    with open(path, "rb") as f:
        header = f.read(20)
        magic, records, fields, record_size, string_size = struct.unpack("<4s4i", header)
        if magic != b"WDBC":
            raise ValueError("Not a valid DBC file (expected WDBC)")

        recdata = f.read(records * record_size)
        strblock = f.read(string_size)

        def get_string(offset: int) -> str:
            if offset <= 0 or offset >= len(strblock):
                return ""
            end = strblock.find(b"\x00", offset)
            if end == -1:
                end = len(strblock)
            return strblock[offset:end].decode("utf-8", errors="ignore").strip()

        ints_per_record = record_size // 4

        for i in range(records):
            off = i * record_size
            cols = struct.unpack("<" + ("i" * ints_per_record), recdata[off : off + record_size])

            skill_id = int(cols[0])

            # ✅ Correct for YOUR file:
            name = get_string(int(cols[2]))
            if not name:
                name = f"(unnamed) SkillLine {skill_id}"

            rows.append((skill_id, name))

    return rows

QUEST_ID_MIN = 1000000
QUEST_ID_MAX = 2000000


# Columns that are TEXT in your quest_template schema
TEXT_COLS = {
    "Title",
    "Details",
    "Objectives",
    "OfferRewardText",
    "RequestItemsText",
    "EndText",
    "CompletedText",
    "ObjectiveText1",
    "ObjectiveText2",
    "ObjectiveText3",
    "ObjectiveText4",
    "QuestGiverPortraitText",
    "QuestGiverPortraitUnk",
    "QuestTurnInPortraitText",
    "QuestTurnInPortraitUnk",
}

TAB_GROUPS = {
    "Core": [
        "Core",
        "Chain",
        "Source",
        "Text",
        "Portraits",
        "Emotes",
        "Point",
        "Sounds/Scripts",
    ],
    "Objectives": [
        "Objective Text",
    ],
    "Requirements": [
        "Reputation Requirements",
        "Requirements - Items",
        "Requirements - Sources",
        "Requirements - NPC/GO",
        "Requirements - Spell Cast",
        "Requirements - Currency",
    ],
    "Rewards": [
        "Rewards - Choice Items",
        "Rewards - Guaranteed Items",
        "Rewards - Money/Spells/Mail",
        "Rewards - Skills/Honor",
        "Rewards - Reputation",
        "Rewards - Currency",
    ],
    
}

# --- Bitmask (checkbox picker) fields ---
# Add/remove fields here as you want
BITMASK_FIELDS = {
    # Quest core
    "QuestFlags": "quest_flags",
    
    # Masks
    "RequiredRaces": "race_mask",
    
}

# Minimal starter sets (you can expand these as needed)
# NOTE: Flag meanings vary slightly by core; treat this as a starter and adjust to match your server.
BITMASK_OPTIONS = {
    "quest_flags": [
        (0x00000001, "Stay Alive"),
        (0x00000002, "Party Accept"),
        (0x00000004, "Exploration"),
        (0x00000008, "Sharable"),
        (0x00000010, "Has Condition"),
        (0x00000020, "Hide Reward POI"),
        (0x00000040, "Raid"),
        (0x00000080, "TBC"),
        (0x00000100, "No Money at Max Level"),
        (0x00000200, "Hidden Rewards"),
        (0x00000400, "Tracking"),
        (0x00000800, "Deprecated Reputation"),
        (0x00001000, "Daily"),
        (0x00002000, "PvP"),
        (0x00004000, "Unavailable"),
        (0x00008000, "Weekly"),
        (0x00010000, "Auto Complete"),
        (0x00020000, "Display Item in Tracker"),
        (0x00040000, "Objective Text"),
        (0x00080000, "Auto Accept"),
    ],

    "race_mask": [
        (1, "Human"),
        (2, "Orc"),
        (4, "Dwarf"),
        (8, "Night Elf"),
        (16, "Undead"),
        (32, "Tauren"),
        (64, "Gnome"),
        (128, "Troll"),
        (256, "Goblin"),
        (512, "Blood Elf"),
        (1024, "Draenei"),
        (2097152, "Worgen"),
    ],

    # Used by SkillOrClassMask when in "Class Mask" mode
    "class_mask": [
        (1, "Warrior"),
        (2, "Paladin"),
        (4, "Hunter"),
        (8, "Rogue"),
        (16, "Priest"),
        (32, "Death Knight"),
        (64, "Shaman"),
        (128, "Mage"),
        (256, "Warlock"),
        (1024, "Druid"),
    ],
}

CLASS_ID_NAMES = {
    1: "Warrior",
    2: "Paladin",
    3: "Hunter",
    4: "Rogue",
    5: "Priest",
    6: "Death Knight",
    7: "Shaman",
    8: "Mage",
    9: "Warlock",
    11: "Druid",
}

# -----------------------------
# Dropdown (enum-ish) fields
# -----------------------------
ENUM_FIELDS = {
    "Method": "quest_method",
    "Type": "quest_type",  # ✅ quest_template.Type dropdown
}

ENUM_OPTIONS = {
    "quest_method": [
        ("0", "0 — Enabled, auto-completed"),
        ("1", "1 — Disabled (not yet implemented in core)"),
        ("2", "2 — Enabled (does not auto-complete)"),
        ("3", "3 — World Quest"),
    ],

    # ✅ Trinity-style quest_template.Type values (common set)
    "quest_type": [
        ("0",  "0 — Normal"),
        ("1",  "1 — Group"),
        ("21", "21 — Life"),
        ("41", "41 — PvP"),
        ("62", "62 — Raid"),
        ("81", "81 — Dungeon"),
        ("82", "82 — World Event"),
        ("83", "83 — Legendary"),
        ("84", "84 — Escort"),
        ("85", "85 — Heroic"),
        ("88", "88 — Raid (10)"),
        ("89", "89 — Raid (25)"),
    ],
}

def _normalize_plain_text(s: str) -> str:
    """Make pasted/loaded text consistent + safe for DB storage."""
    if s is None:
        return ""
    # Normalize Windows/Mac newlines to \n
    s = s.replace("\r\n", "\n").replace("\r", "\n")
    # Strip null chars (can break SQL drivers / UI)
    s = s.replace("\x00", "")
    return s

def _get_widget_text(w) -> str:
    """Read text from QLineEdit / QPlainTextEdit / QComboBox safely."""
    if isinstance(w, QtWidgets.QComboBox):
        # Prefer stored data value, fallback to visible text
        return _normalize_plain_text(w.currentData() or w.currentText() or "")
    if hasattr(w, "toPlainText"):  # QPlainTextEdit
        return _normalize_plain_text(w.toPlainText())
    return _normalize_plain_text(w.text())


def _set_widget_text(w, val: str) -> None:
    """Write text to QLineEdit / QPlainTextEdit / QComboBox safely."""
    val = "" if val is None else str(val)
    val = _normalize_plain_text(val)

    if isinstance(w, QtWidgets.QComboBox):
        # match by data first, then display text
        idx = w.findData(val)
        if idx >= 0:
            w.setCurrentIndex(idx)
            return
        idx = w.findText(val)
        if idx >= 0:
            w.setCurrentIndex(idx)
            return
        # allow arbitrary (editable) values
        if w.isEditable():
            w.setCurrentText(val)
        return

    if hasattr(w, "setPlainText"):  # QPlainTextEdit
        w.setPlainText(val)
    else:
        w.setText(val)


# --- Inline name lookups (Item / Creature / GameObject) ---

ITEM_ID_COLS = {
    # Quest source item
    "SrcItemId",

    # Required items
    "ReqItemId1", "ReqItemId2", "ReqItemId3", "ReqItemId4", "ReqItemId5", "ReqItemId6",

    # Reward choice items
    "RewChoiceItemId1", "RewChoiceItemId2", "RewChoiceItemId3",
    "RewChoiceItemId4", "RewChoiceItemId5", "RewChoiceItemId6",

    # Reward guaranteed items
    "RewItemId1", "RewItemId2", "RewItemId3", "RewItemId4",
}

CREATURE_GO_ID_COLS = {
    "ReqCreatureOrGOId1", "ReqCreatureOrGOId2", "ReqCreatureOrGOId3", "ReqCreatureOrGOId4",
}

def _try_int(s: str) -> Optional[int]:
    try:
        s = (s or "").strip()
        if not s:
            return None
        return int(s)
    except Exception:
        return None

class ClickableLabel(QtWidgets.QLabel):
    clicked = pyqtSignal()

    def mousePressEvent(self, ev):
        if ev.button() == Qt.MouseButton.LeftButton:
            self.clicked.emit()
        super().mousePressEvent(ev)


class IDPickerDialog(QtWidgets.QDialog):
    """
    Tiny ID picker for item/creature/gameobject templates.
    - Type search text (id or partial name)
    - Results list updates on Search
    - Double-click (or Select) returns chosen entry
    """
    def __init__(self, db: Database, mode: str, parent=None):
        super().__init__(parent)
        self.db = db
        self.mode = mode  # "item" | "creature" | "go"
        self._selected_id: Optional[int] = None

        self.setWindowTitle(f"Pick {mode.title()} ID")
        self.setModal(True)
        self.resize(720, 420)

        self.q = QtWidgets.QLineEdit()
        self.q.setPlaceholderText("Type an ID (e.g. 6948) or a name fragment (e.g. hearth)")
        self.btn_search = QtWidgets.QPushButton("Search")

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

        # Enter triggers search
        self.q.returnPressed.connect(self.run_search)

    def selected_id(self) -> Optional[int]:
        return self._selected_id

    def _table_name(self) -> str:
        if self.mode == "item":
            return "item_template"
        if self.mode == "creature":
            return "creature_template"
        if self.mode == "go":
            return "gameobject_template"
        raise ValueError(f"Unknown mode: {self.mode}")

    def run_search(self) -> None:
        text = (self.q.text() or "").strip()
        tbl = self._table_name()

        # If numeric, do exact ID lookup first (fast)
        rows = []
        try:
            qid = int(text)
            rows = self.db.fetch_all(
                f"SELECT entry, name FROM {tbl} WHERE entry=%s LIMIT 200",
                (qid,),
            )
        except Exception:
            like = f"%{text}%"
            rows = self.db.fetch_all(
                f"SELECT entry, name FROM {tbl} WHERE name LIKE %s ORDER BY entry DESC LIMIT 200",
                (like,),
            )

        self.table.setRowCount(0)
        for r in rows:
            rid = r.get("entry", "")
            nm = r.get("name", "") or ""
            row = self.table.rowCount()
            self.table.insertRow(row)
            self.table.setItem(row, 0, QtWidgets.QTableWidgetItem(str(rid)))
            self.table.setItem(row, 1, QtWidgets.QTableWidgetItem(nm))

        if self.table.rowCount() > 0:
            self.table.selectRow(0)

    def accept_selected(self) -> None:
        r = self.table.currentRow()
        if r < 0:
            return
        item = self.table.item(r, 0)
        if not item:
            return
        try:
            self._selected_id = int(item.text())
        except Exception:
            self._selected_id = None
        if self._selected_id is not None:
            self.accept()

class BitmaskPickerDialog(QtWidgets.QDialog):
    def __init__(self, title: str, options: list[tuple[int, str]], value: int, parent=None):
        super().__init__(parent)
        self.setWindowTitle(title)
        self.setModal(True)
        self.resize(520, 420)

        self._options = options
        self._checks: list[tuple[int, QtWidgets.QCheckBox]] = []

        self.search = QtWidgets.QLineEdit()
        self.search.setPlaceholderText("Filter…")

        self.scroll = QtWidgets.QScrollArea()
        self.scroll.setWidgetResizable(True)
        inner = QtWidgets.QWidget()
        self.v = QtWidgets.QVBoxLayout(inner)
        self.v.setContentsMargins(8, 8, 8, 8)
        self.v.setSpacing(6)

        for bit, name in options:
            cb = QtWidgets.QCheckBox(f"{name}  (0x{bit:X})")
            cb.setChecked(bool(value & bit))
            self.v.addWidget(cb)
            self._checks.append((bit, cb))

        self.v.addStretch(1)
        self.scroll.setWidget(inner)

        self.btn_all = QtWidgets.QPushButton("All")
        self.btn_none = QtWidgets.QPushButton("None")

        # Faction quick buttons (only shown for race picker)
        self.btn_alliance = QtWidgets.QPushButton("Alliance")
        self.btn_horde = QtWidgets.QPushButton("Horde")
        self.btn_alliance.setVisible(False)
        self.btn_horde.setVisible(False)

        self.btn_ok = QtWidgets.QPushButton("OK")
        self.btn_cancel = QtWidgets.QPushButton("Cancel")

        btns = QtWidgets.QHBoxLayout()
        btns.addWidget(self.btn_all)
        btns.addWidget(self.btn_none)
        btns.addWidget(self.btn_alliance)
        btns.addWidget(self.btn_horde)
        btns.addStretch(1)
        btns.addWidget(self.btn_cancel)
        btns.addWidget(self.btn_ok)

        lay = QtWidgets.QVBoxLayout(self)
        lay.addWidget(self.search)
        lay.addWidget(self.scroll, 1)
        lay.addLayout(btns)

        self.btn_ok.clicked.connect(self.accept)
        self.btn_cancel.clicked.connect(self.reject)
        self.btn_all.clicked.connect(self._check_all)
        self.btn_none.clicked.connect(self._check_none)

        # Show + wire Alliance/Horde only for race-style lists
        opt_names = " ".join([name.lower() for _bit, name in self._options])
        is_race_picker = ("human" in opt_names and "orc" in opt_names and "undead" in opt_names)

        if is_race_picker:
            self.btn_alliance.setVisible(True)
            self.btn_horde.setVisible(True)
            self.btn_alliance.clicked.connect(lambda: self._set_race_faction("alliance"))
            self.btn_horde.clicked.connect(lambda: self._set_race_faction("horde"))

        self.search.textChanged.connect(self._apply_filter)

    def value(self) -> int:
        v = 0
        for bit, cb in self._checks:
            if cb.isChecked():
                v |= bit
        return v

    def _check_all(self):
        for _bit, cb in self._checks:
            cb.setChecked(True)

    def _check_none(self):
        for _bit, cb in self._checks:
            cb.setChecked(False)
    
    def _set_race_faction(self, which: str) -> None:
        alliance = {"human", "dwarf", "night elf", "gnome", "draenei", "worgen"}
        horde = {"orc", "undead", "tauren", "troll", "blood elf", "goblin"}

        for _bit, cb in self._checks:
            txt = cb.text().lower()
            if which == "alliance":
                cb.setChecked(any(n in txt for n in alliance))
            else:
                cb.setChecked(any(n in txt for n in horde))

    def _apply_filter(self, text: str):
        t = (text or "").strip().lower()
        for bit, cb in self._checks:
            cb.setVisible(t in cb.text().lower())

class QuestRelationPanel(QtWidgets.QWidget):
    """
    4 independent sections (no shared inputs):
      - Creature Starters: creature_quest_starter (id, quest)
      - Creature Enders:   creature_quest_ender   (id, quest)
      - GO Starters:       gameobject_questrelation    (id, quest)
      - GO Enders:         gameobject_involvedrelation (id, quest)
    """
    def __init__(self, db: Database, log, parent=None):
        super().__init__(parent)
        self.db = db
        self.log = log
        self.quest_id: Optional[int] = None

        # ---- helper to build one section ----
        def build_section(title: str, mode: str, rel_table: str, tmpl_table: str):
            # UI
            g = QtWidgets.QGroupBox(title)
            v = QtWidgets.QVBoxLayout(g)

            lst = QtWidgets.QListWidget()
            lst.setSelectionMode(QtWidgets.QAbstractItemView.SelectionMode.SingleSelection)
            v.addWidget(lst, 1)

            inp = QtWidgets.QLineEdit()
            inp.setReadOnly(True)
            inp.setPlaceholderText("Pick…")

            btn_pick = QtWidgets.QPushButton("Pick…")
            btn_add  = QtWidgets.QPushButton("Add")
            btn_rm   = QtWidgets.QPushButton("Remove Selected")

            row = QtWidgets.QHBoxLayout()
            row.addWidget(inp, 1)
            row.addWidget(btn_pick)
            row.addWidget(btn_add)
            row.addWidget(btn_rm)
            v.addLayout(row)

            # wiring
            btn_pick.clicked.connect(lambda: self._pick_into(mode, inp))
            btn_add.clicked.connect(lambda: self._add(rel_table, inp))
            btn_rm.clicked.connect(lambda: self._remove(rel_table, lst))
            lst.itemDoubleClicked.connect(lambda _it: self._remove(rel_table, lst))

            return g, lst, inp, rel_table, tmpl_table

        # ---- create 4 independent sections ----
        self.sec_cre_start = build_section(
            "Creature Starters", "creature", "creature_quest_starter", "creature_template"
        )
        self.sec_cre_end = build_section(
            "Creature Enders", "creature", "creature_quest_ender", "creature_template"
        )
        self.sec_go_start = build_section(
            "GO Starters", "go", "gameobject_questrelation", "gameobject_template"
        )
        self.sec_go_end = build_section(
            "GO Enders", "go", "gameobject_involvedrelation", "gameobject_template"
        )

        # ---- layout grid ----
        grid = QtWidgets.QGridLayout(self)
        grid.setContentsMargins(10, 10, 10, 10)
        grid.setHorizontalSpacing(10)
        grid.setVerticalSpacing(10)

        grid.addWidget(self.sec_cre_start[0], 0, 0)
        grid.addWidget(self.sec_cre_end[0],   1, 0)
        grid.addWidget(self.sec_go_start[0],  0, 1)
        grid.addWidget(self.sec_go_end[0],    1, 1)

    def _pick_into(self, mode: str, target: QtWidgets.QLineEdit) -> None:
        # reuse your existing IDPickerDialog
        dlg = IDPickerDialog(self.db, mode, self)
        cur = (target.text() or "").strip()
        if cur:
            dlg.q.setText(cur)
        dlg.run_search()
        if dlg.exec() == QtWidgets.QDialog.DialogCode.Accepted:
            picked = dlg.selected_id()
            if picked is not None:
                target.setText(str(picked))
    

    def load(self, quest_id: int) -> None:
        self.quest_id = quest_id
        self.reload_lists()

    def reload_lists(self) -> None:
        if not self.quest_id:
            return
        # each tuple = (groupbox, listwidget, input, rel_table, tmpl_table)
        for (_g, lst, _inp, rel_table, tmpl_table) in (
            self.sec_cre_start,
            self.sec_cre_end,
            self.sec_go_start,
            self.sec_go_end,
        ):
            self._fill_list(lst, rel_table, tmpl_table)

    def _fill_list(self, listw: QtWidgets.QListWidget, rel_table: str, tmpl_table: str) -> None:
        listw.clear()
        rows = self.db.fetch_all(
            f"""
            SELECT r.id AS entry, t.name AS name
            FROM {rel_table} r
            LEFT JOIN {tmpl_table} t ON t.entry = r.id
            WHERE r.quest = %s
            ORDER BY r.id
            """,
            (self.quest_id,),
        )
        for r in rows:
            eid = int(r.get("entry") or 0)
            nm = r.get("name") or "(no name)"
            it = QtWidgets.QListWidgetItem(f"{eid}  -  {nm}")
            it.setData(Qt.ItemDataRole.UserRole, eid)
            listw.addItem(it)

    def _add(self, rel_table: str, inputw: QtWidgets.QLineEdit) -> None:
        if not self.quest_id:
            return

        txt = (inputw.text() or "").strip()
        if not txt:
            QtWidgets.QMessageBox.warning(self, "Missing ID", "Pick an ID first.")
            return

        try:
            eid = int(txt)
        except Exception:
            QtWidgets.QMessageBox.warning(self, "Invalid", "ID must be numeric.")
            return

        try:
            self.db.execute(
                f"INSERT IGNORE INTO {rel_table} (id, quest) VALUES (%s, %s)",
                (eid, self.quest_id),
            )
            self.db.commit()
            self.log(f"Added id={eid} to {rel_table} for quest={self.quest_id}")
            self.reload_lists()
        except Exception as e:
            self.db.rollback()
            QtWidgets.QMessageBox.critical(self, "Add failed", str(e))

    def _remove(self, rel_table: str, listw: QtWidgets.QListWidget) -> None:
        if not self.quest_id:
            return
        it = listw.currentItem()
        if not it:
            return
        eid = int(it.data(Qt.ItemDataRole.UserRole))

        try:
            self.db.execute(
                f"DELETE FROM {rel_table} WHERE id=%s AND quest=%s",
                (eid, self.quest_id),
            )
            self.db.commit()
            self.log(f"Removed id={eid} from {rel_table} for quest={self.quest_id}")
            self.reload_lists()
        except Exception as e:
            self.db.rollback()
            QtWidgets.QMessageBox.critical(self, "Remove failed", str(e))

class SimplePickerDialog(QtWidgets.QDialog):
    """
    Tiny picker/search dialog.
    - Provide rows as [(id:int, name:str), ...]
    - User can filter via search box
    - Double click or Select returns chosen id
    """
    def __init__(self, title: str, rows, parent=None, initial_query: str = ""):
        super().__init__(parent)
        self.setWindowTitle(title)
        self.setModal(True)
        self.resize(520, 420)
        self._rows = list(rows)
        self._chosen = None

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

        # Fill initial search (supports typing a zone name before hitting Pick…)
        if initial_query:
            self.search.setText(initial_query)  # triggers _refill via textChanged
        else:
            self._refill()
            
    def chosen_id(self):
        return self._chosen

    def _refill(self):
        q = (self.search.text() or "").strip().lower()
        if not q:
            rows = self._rows
        else:
            rows = []
            for i, n in self._rows:
                if q in str(i).lower() or q in (n or "").lower():
                    rows.append((i, n))

        self.table.setRowCount(0)
        for i, n in rows[:2000]:
            r = self.table.rowCount()
            self.table.insertRow(r)
            self.table.setItem(r, 0, QtWidgets.QTableWidgetItem(str(i)))
            self.table.setItem(r, 1, QtWidgets.QTableWidgetItem(n or ""))

        if self.table.rowCount():
            self.table.selectRow(0)

    def _accept_selected(self):
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



@dataclass
class ObjRow:
    kind: str          # "Item", "Kill", "GO", "SpellCast", "Source"
    target_id: int
    count: int
    text: str          # tracker text (ObjectiveText#)

class QuestEditor(QtWidgets.QWidget):
    def __init__(self, db: Database, log: Callable[[str], None], parent=None):
        super().__init__(parent)
        self.db = db
        self.log = log

        # MUST exist before _build_tabs()
        self.current_id: Optional[int] = None
        self._orig: Dict[str, Any] = {}
        self._widgets: Dict[str, QtWidgets.QWidget] = {}
        self._soc_mode: Dict[str, QtWidgets.QComboBox] = {}
        self._soc_hint: Dict[str, QtWidgets.QLabel] = {}
        self._soc_refresh: Dict[str, Callable[[], None]] = {}
        self._zos_mode: Dict[str, QtWidgets.QComboBox] = {}
        self._zos_hint: Dict[str, QtWidgets.QLabel] = {}
        self._zos_refresh: Dict[str, Callable[[], None]] = {}   # ✅ add this

        self._ftypes: Dict[str, str] = {}  # col -> ftype from metadata

        # Inline lookup labels: col -> QLabel
        self._name_labels: Dict[str, QtWidgets.QLabel] = {}

        # Simple caches to reduce DB hits
        self._item_name_cache: Dict[int, str] = {}
        self._cre_name_cache: Dict[int, str] = {}
        self._go_name_cache: Dict[int, str] = {}
        self._bitmask_labels: Dict[str, QtWidgets.QLabel] = {}
        self._areatable_cache: List[Tuple[int, str]] = []
        self._areatable_name_by_id: Dict[int, str] = {}
        self._questsort_cache: List[Tuple[int, str]] = []
        self._questsort_name_by_id: Dict[int, str] = {}

        # Debounce lookups so typing doesn't spam DB
        self._lookup_timer = QTimer(self)
        self._lookup_timer.setSingleShot(True)
        self._lookup_pending: set[str] = set()
        self._lookup_timer.timeout.connect(self._run_pending_lookups)

        self.tabs = QtWidgets.QTabWidget()
        self._build_tabs()

        # Starters / Enders tab (relation tables)
        self.relations = QuestRelationPanel(self.db, self.log, self)
        self.tabs.addTab(self.relations, "Starters / Enders")

        # Quest Loot Conditions tab
        self.quest_loot = QuestLootEditor(self.db, self.log, self)
        self.tabs.addTab(self.quest_loot, "Quest Loot Conditions")

        # Auto-load loot editor when its tab is selected
        self.tabs.currentChanged.connect(self._on_tab_changed)

        self.btn_new = QtWidgets.QPushButton("New Quest")
        self.btn_delete = QtWidgets.QPushButton("Delete Quest")
        self.btn_preview = QtWidgets.QPushButton("Preview")
        self.btn_reload = QtWidgets.QPushButton("Reload")
        self.btn_save = QtWidgets.QPushButton("Save")

        self.btn_new.clicked.connect(self.new_quest)
        self.btn_delete.clicked.connect(self.delete_quest)
        self.btn_preview.clicked.connect(self.preview_quest)
        self.btn_reload.clicked.connect(self.reload)
        self.btn_save.clicked.connect(self.save)

        btns = QtWidgets.QHBoxLayout()
        btns.addStretch(1)
        btns.addWidget(self.btn_new)
        btns.addWidget(self.btn_delete)
        btns.addWidget(self.btn_preview)
        btns.addWidget(self.btn_reload)
        btns.addWidget(self.btn_save)

        lay = QtWidgets.QVBoxLayout(self)
        lay.addWidget(self.tabs, 1)
        lay.addLayout(btns)
        
        # Ctrl+S / Cmd+S to save
        sc = QShortcut(QKeySequence.StandardKey.Save, self)
        sc.activated.connect(self.save)
        sc_new = QShortcut(QKeySequence.StandardKey.New, self)
        sc_new.activated.connect(self.new_quest)
        sc_del = QShortcut(QKeySequence(Qt.Key.Key_Delete), self)
        sc_del.activated.connect(self.delete_quest)
        sc_prev = QShortcut(QKeySequence(Qt.Key.Key_P), self)
        sc_prev.setContext(Qt.ShortcutContext.WidgetWithChildrenShortcut)
        sc_prev.activated.connect(self.preview_quest)

    def _build_tabs(self) -> None:
        self.tabs.clear()

        # Build outer (group) tabs
        group_tabs: Dict[str, QtWidgets.QTabWidget] = {}
        for group_name in TAB_GROUPS.keys():
            inner = QtWidgets.QTabWidget()
            inner.setDocumentMode(True)
            inner.setMovable(True)
            group_tabs[group_name] = inner
            self.tabs.addTab(inner, group_name)

        def find_group(tab_name: str) -> str:
            for g, names in TAB_GROUPS.items():
                if tab_name in names:
                    return g
            return "Core"

        # Ensure storage exists (in case you removed it earlier)
        if not hasattr(self, "_bitmask_labels"):
            self._bitmask_labels: Dict[str, QtWidgets.QLabel] = {}

        # Build inner tabs from QUEST_TABS
        for tab_name, fields in QUEST_TABS:
            gname = find_group(tab_name)
            inner = group_tabs[gname]

            page = QtWidgets.QWidget()
            form = QtWidgets.QFormLayout(page)
            form.setLabelAlignment(Qt.AlignmentFlag.AlignRight)
            form.setFormAlignment(Qt.AlignmentFlag.AlignTop)

            for col, label, ftype in fields:

                # -----------------------------------------------
                # Case A: Trinity SkillOrClassMask signed selector
                #   >0 = SkillLine ID, <0 = -ClassId
                # -----------------------------------------------
                if col == "SkillOrClassMask":
                    roww = QtWidgets.QWidget()
                    h = QtWidgets.QHBoxLayout(roww)
                    h.setContentsMargins(0, 0, 0, 0)
                    h.setSpacing(8)

                    mode = QtWidgets.QComboBox()
                    mode.addItems(["Skill", "Class Mask"])
                    mode.setFixedWidth(90)

                    val_edit = QtWidgets.QLineEdit()
                    val_edit.setPlaceholderText("SkillLine ID or Class Mask")
                    val_edit.setFixedWidth(160)

                    hint = QtWidgets.QLabel("—")
                    hint.setStyleSheet("color: #A9B1BA;")
                    hint.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)

                    def refresh_hint(mode=mode, val_edit=val_edit, hint=hint):
                        txt = (val_edit.text() or "").strip()
                        try:
                            n = int(txt) if txt else 0
                        except Exception:
                            hint.setText("—")
                            return

                        if not n:
                            hint.setText("—")
                            return

                        if mode.currentText() == "Class Mask":
                            names = []
                            for bit, cname in BITMASK_OPTIONS.get("class_mask", []):
                                if n & bit:
                                    names.append(cname)

                            if names:
                                hint.setText(f"{', '.join(names)}   (mask={n}, 0x{n:X})")
                            else:
                                hint.setText(f"(none)   (mask={n}, 0x{n:X})")
                        else:
                            self._ensure_skillline_cache_loaded()
                            nm = getattr(self, "_skillline_name_by_id", {}).get(n, "")
                            hint.setText(f"{n} — {nm}" if nm else f"SkillLine {n}")

                    mode.currentIndexChanged.connect(lambda _i, rh=refresh_hint: (rh(), self._update_dirty_title()))
                    val_edit.textEdited.connect(lambda _t, rh=refresh_hint: (rh(), self._update_dirty_title()))
                    # allow load() to refresh decode after setting values
                    self._soc_refresh[col] = refresh_hint

                    # initialize hint immediately
                    refresh_hint()


                    btn_pick = QtWidgets.QPushButton("Pick…")
                    btn_pick.setFixedWidth(70)

                    def do_pick(_checked: bool = False, mode=mode, val_edit=val_edit):
                        # _checked comes from QPushButton.clicked(bool) — ignore it
                        if mode.currentText() == "Class Mask":
                            cur = 0
                            try:
                                cur = int((val_edit.text() or "0").strip() or "0")
                            except Exception:
                                cur = 0

                            chosen = self._open_bitmask_picker_value("class_mask", current=cur)
                            if chosen is None:
                                return
                            val_edit.setText(str(chosen))
                        else:
                            sid = self._pick_skillline_id_from_dbc()
                            if sid is None:
                                return
                            val_edit.setText(str(sid))

                        refresh_hint()
                        self._update_dirty_title()

                    btn_pick.clicked.connect(do_pick)

                    h.addWidget(mode, 0)
                    h.addWidget(val_edit, 0)
                    h.addWidget(btn_pick, 0)
                    h.addWidget(hint, 1)


                    # Store widgets for load/_collect special handling
                    self._widgets[col] = val_edit
                    self._soc_mode[col] = mode
                    self._soc_hint[col] = hint

                    form.addRow(label + ":", roww)
                    continue
                # -----------------------------------------------
                # Case: Trinity ZoneOrSort signed selector
                #   >=0 = AreaTable ID (zone)
                #   <0  = -SortId
                # -----------------------------------------------
                if col == "ZoneOrSort":
                    roww = QtWidgets.QWidget()
                    h = QtWidgets.QHBoxLayout(roww)
                    h.setContentsMargins(0, 0, 0, 0)
                    h.setSpacing(8)

                    mode = QtWidgets.QComboBox()
                    mode.addItem("Zone", "zone")
                    mode.addItem("Sort", "sort")
                    mode.setFixedWidth(90)

                    val_edit = QtWidgets.QLineEdit()
                    val_edit.setPlaceholderText("AreaTable ID (Zone) or Sort ID")
                    val_edit.setFixedWidth(160)

                    btn_pick = QtWidgets.QPushButton("Pick…")
                    btn_pick.setFixedWidth(70)

                    hint = QtWidgets.QLabel("—")
                    hint.setStyleSheet("color: #A9B1BA;")
                    hint.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)

                    # ✅ ADD widgets to the row layout
                    h.addWidget(mode, 0)
                    h.addWidget(val_edit, 0)
                    h.addWidget(btn_pick, 0)
                    h.addWidget(hint, 1)

                    # Store widgets so load/save logic can find them
                    self._widgets[col] = val_edit
                    self._zos_mode[col] = mode
                    self._zos_hint[col] = hint

                    def refresh_hint(mode=mode, val_edit=val_edit, hint=hint) -> None:
                        is_zone = (mode.currentData() == "zone")
                        try:
                            v = int((val_edit.text() or "").strip() or "0")
                        except Exception:
                            v = 0

                        if is_zone:
                            if v <= 0:
                                hint.setText("Zone: (unset)")
                                return
                            self._load_areatable_dbc()
                            name = self._areatable_name_by_id.get(v, "")
                            hint.setText(f"Zone: {v} - {name}" if name else f"Zone: {v} - Unknown")
                        else:
                            if v <= 0:
                                hint.setText("Sort: (unset)")
                                return
                            self._load_questsort_dbc()
                            name = self._questsort_name_by_id.get(v, "")
                            hint.setText(f"Sort: {v} - {name}" if name else f"Sort: {v} - Unknown")

                    def zos_do_pick(_checked: bool = False, mode=mode, val_edit=val_edit, refresh_hint=refresh_hint) -> None:
                        is_zone = (mode.currentData() == "zone")

                        if is_zone:
                            self._load_areatable_dbc()
                            rows = self._areatable_cache
                            title = "Pick Zone (AreaTable)"
                        else:
                            self._load_questsort_dbc()
                            rows = self._questsort_cache
                            title = "Pick Sort (QuestSort)"

                        if not rows:
                            QtWidgets.QMessageBox.information(self, "No data", f"No rows loaded for {title}.")
                            return

                        dlg = SimplePickerDialog(
                            title=title,
                            rows=rows,
                            parent=self,
                            initial_query=val_edit.text().strip(),
                        )
                        if dlg.exec() == QtWidgets.QDialog.DialogCode.Accepted:
                            chosen_id = dlg.chosen_id()
                            if chosen_id is None:
                                return
                            val_edit.setText(str(int(chosen_id)))
                            refresh_hint()
                            self._update_dirty_title()

                    # allow load() to refresh decode after setting values
                    self._zos_refresh[col] = refresh_hint

                    btn_pick.clicked.connect(zos_do_pick)
                    mode.currentIndexChanged.connect(lambda _i, rh=refresh_hint: (rh(), self._update_dirty_title()))
                    val_edit.textEdited.connect(lambda _t, rh=refresh_hint: (rh(), self._update_dirty_title()))

                    refresh_hint()

                    # ✅ ADD row to the form (this is what makes it appear)
                    form.addRow(label + ":", roww)
                    continue

                # -----------------------------
                # Normal editor build continues
                # -----------------------------
                editor = self._create_editor(col, label, ftype)
                # -----------------------------------
                # Objectives field with Builder button
                # -----------------------------------
                if col == "Objectives" and isinstance(editor, QtWidgets.QPlainTextEdit):
                    wrapper = QtWidgets.QWidget()
                    v = QtWidgets.QVBoxLayout(wrapper)
                    v.setContentsMargins(0, 0, 0, 0)
                    v.setSpacing(4)

                    # Cap the height so it doesn't eat the tab
                    editor.setMinimumHeight(120)
                    editor.setMaximumHeight(220)
                    editor.setSizePolicy(QtWidgets.QSizePolicy.Policy.Expanding,
                                         QtWidgets.QSizePolicy.Policy.Fixed)

                    v.addWidget(editor)

                    btn_build = QtWidgets.QPushButton("Build Objectives…")
                    btn_build.setFixedWidth(160)
                    btn_build.clicked.connect(self._open_objective_builder)

                    btn_row = QtWidgets.QHBoxLayout()
                    btn_row.addStretch(1)
                    btn_row.addWidget(btn_build)

                    v.addLayout(btn_row)

                    self._widgets[col] = editor
                    form.addRow(label + ":", wrapper)
                    continue


                self._widgets[col] = editor
                

                if col == "entry":
                    editor.setEnabled(True)
                    editor.setToolTip("Quest ID (Entry). Edit and press Enter to load.")

                    # Press Enter in the Entry box to load that quest ID
                    if isinstance(editor, QtWidgets.QLineEdit):
                        editor.returnPressed.connect(
                            lambda e=editor: self.load(int(e.text())) if (e.text() or "").strip().isdigit() else None
                        )

                # -----------------------------
                # Case B: Bitmask picker fields
                # -----------------------------
                if col in BITMASK_FIELDS and isinstance(editor, QtWidgets.QLineEdit):
                    roww = QtWidgets.QWidget()
                    h = QtWidgets.QHBoxLayout(roww)
                    h.setContentsMargins(0, 0, 0, 0)
                    h.setSpacing(8)

                    h.addWidget(editor, 1)

                    btn = QtWidgets.QPushButton("Pick…")
                    btn.setFixedWidth(70)
                    btn.clicked.connect(lambda _=False, c=col: self._open_bitmask_picker(c))
                    h.addWidget(btn, 0)

                    decoded = QtWidgets.QLabel("—")
                    decoded.setStyleSheet("color: #A9B1BA;")
                    decoded.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
                    h.addWidget(decoded, 2)

                    self._bitmask_labels[col] = decoded

                    # update decoded label when user types
                    editor.textEdited.connect(lambda _t, c=col: self._update_bitmask_label(c))

                    form.addRow(label + ":", roww)
                    continue

                

                # Default row
                form.addRow(label + ":", editor)



            inner.addTab(page, tab_name)
            
    def _load_areatable_dbc(self) -> None:
        """
        AreaTable.dbc reader (WDBC):
        - reads WDBC header
        - for each record: id = column 1 (fields[0])
                         name = column 12 (fields[11]) string offset
        """
        if getattr(self, "_areatable_cache", None):
            return

        if config is None or not hasattr(config, "AREATABLE_DBC"):
            QtWidgets.QMessageBox.warning(
                self,
                "Missing config.AREATABLE_DBC",
                "config.py must define:\nAREATABLE_DBC = DBC_DIR / 'AreaTable.dbc'",
            )
            return

        dbc_path = config.AREATABLE_DBC
        if dbc_path is None:
            QtWidgets.QMessageBox.warning(self, "DBC path is None", "config.AREATABLE_DBC is None.")
            return

        dbc_path = Path(dbc_path)
        if not dbc_path.exists():
            QtWidgets.QMessageBox.warning(
                self,
                "Missing AreaTable.dbc",
                f"AreaTable.dbc not found at:\n{dbc_path}",
            )
            return

        data = dbc_path.read_bytes()
        magic4 = data[:4]

        if magic4 != b"WDBC":
            QtWidgets.QMessageBox.critical(
                self,
                "DBC Error",
                f"Not a valid WDBC file. Magic={magic4!r}\n\nPath:\n{dbc_path}",
            )
            return

        try:
            _magic, rec_count, field_count, rec_size, str_size = struct.unpack_from("<4s4I", data, 0)
        except Exception as e:
            QtWidgets.QMessageBox.critical(self, "DBC Error", f"Header parse failed: {e}")
            return

        records_off = 20
        strings_off = records_off + rec_count * rec_size
        string_block = data[strings_off:strings_off + str_size]

        def read_cstr(off: int) -> str:
            if off < 0 or off >= len(string_block):
                return ""
            end = string_block.find(b"\x00", off)
            if end == -1:
                return ""
            raw = string_block[off:end]
            return raw.decode("utf-8", "ignore").strip()

        out: List[Tuple[int, str]] = []
        ints_per_record = rec_size // 4

        for i in range(rec_count):
            roff = records_off + i * rec_size
            fields = struct.unpack_from("<" + "I" * ints_per_record, data, roff)

            aid = int(fields[0])
            name_off = int(fields[11]) if len(fields) > 11 else 0
            name = read_cstr(name_off) if 0 <= name_off < str_size else ""

            if not name:
                name = f"Area {aid}"

            if aid:
                out.append((aid, name))

        out.sort(key=lambda t: t[1].lower())

        if not out:
            QtWidgets.QMessageBox.warning(
                self,
                "AreaTable parse produced 0 rows",
                f"rec_count={rec_count}, field_count={field_count}, rec_size={rec_size}, str_size={str_size}\n\nPath:\n{dbc_path}",
            )
            return

        self._areatable_cache = out
        self._areatable_name_by_id = {aid: name for aid, name in out}
    
    def _load_questsort_dbc(self) -> None:
        """
        QuestSort.dbc loader (WDBC).
        Typical layout: fields[0] = ID, fields[1] = Name string offset.
        Produces:
          self._questsort_cache: [(id, name), ...]
          self._questsort_name_by_id: {id: name}
        """
        if getattr(self, "_questsort_cache", None):
            return

        # ---- config path checks ----
        if config is None or not hasattr(config, "QUESTSORT_DBC"):
            QtWidgets.QMessageBox.warning(
                self,
                "Missing config.QUESTSORT_DBC",
                "config.py must define:\nQUESTSORT_DBC = DBC_DIR / 'QuestSort.dbc'",
            )
            return

        dbc_path = config.QUESTSORT_DBC
        if dbc_path is None:
            QtWidgets.QMessageBox.warning(self, "DBC path is None", "config.QUESTSORT_DBC is None.")
            return

        dbc_path = Path(dbc_path)
        if not dbc_path.exists():
            QtWidgets.QMessageBox.warning(
                self,
                "Missing QuestSort.dbc",
                f"QuestSort.dbc not found at:\n{dbc_path}",
            )
            return

        data = dbc_path.read_bytes()
        magic4 = data[:4]
        if magic4 != b"WDBC":
            QtWidgets.QMessageBox.critical(
                self,
                "DBC Error",
                f"Not a valid WDBC file. Magic={magic4!r}\n\nPath:\n{dbc_path}",
            )
            return

        # ---- header ----
        try:
            _magic, rec_count, field_count, rec_size, str_size = struct.unpack_from("<4s4I", data, 0)
        except Exception as e:
            QtWidgets.QMessageBox.critical(self, "DBC Error", f"Header parse failed: {e}")
            return

        records_off = 20
        strings_off = records_off + rec_count * rec_size
        string_block = data[strings_off:strings_off + str_size]

        def read_cstr(off: int) -> str:
            if off < 0 or off >= len(string_block):
                return ""
            end = string_block.find(b"\x00", off)
            if end == -1:
                return ""
            return string_block[off:end].decode("utf-8", "ignore").strip()

        ints_per_record = rec_size // 4
        out: list[tuple[int, str]] = []

        for i in range(rec_count):
            roff = records_off + i * rec_size
            fields = struct.unpack_from("<" + "I" * ints_per_record, data, roff)

            sid = int(fields[0]) if len(fields) > 0 else 0
            name_off = int(fields[1]) if len(fields) > 1 else 0
            name = read_cstr(name_off) if 0 <= name_off < str_size else ""

            if sid <= 0:
                continue
            if not name:
                name = f"Sort {sid}"

            out.append((sid, name))

        out.sort(key=lambda t: t[1].lower())

        if not out:
            QtWidgets.QMessageBox.warning(
                self,
                "QuestSort parse produced 0 rows",
                f"rec_count={rec_count}, field_count={field_count}, rec_size={rec_size}, str_size={str_size}\n\nPath:\n{dbc_path}\n\n"
                "If this is not a WDBC QuestSort.dbc or field[1] isn't the name offset, the format differs.",
            )
            return

        self._questsort_cache = out
        self._questsort_name_by_id = {sid: name for sid, name in out}

    def _pick_areatable_id_from_dbc(self) -> int | None:
        self._load_areatable_dbc()
        if not self._areatable_cache:
            return None

        dlg = SimplePickerDialog(
            title="Pick Zone (AreaTable)",
            rows=self._areatable_cache,   # [(id, name), ...]
            parent=self,
        )
        if dlg.exec() == QtWidgets.QDialog.DialogCode.Accepted:
            return dlg.chosen_id()
        return None
    
    def _pick_questsort_id_from_dbc(self) -> int | None:
        self._load_questsort_dbc()
        if not self._questsort_cache:
            return None

        dlg = SimplePickerDialog(
            title="Pick Sort (QuestSort)",
            rows=self._questsort_cache,
            parent=self,
        )
        if dlg.exec() == QtWidgets.QDialog.DialogCode.Accepted:
            return dlg.chosen_id()
        return None

    def _ensure_skillline_cache_loaded(self) -> None:
        """
        Load SkillLine.dbc into cache without opening any dialogs.
        This enables live decode of SkillOrClassMask when loading quests.
        """
        if hasattr(self, "_skillline_name_by_id") and getattr(self, "_skillline_name_by_id"):
            return

        # Needs config.SKILLLINE_DBC
        if config is None or not hasattr(config, "SKILLLINE_DBC"):
            return

        dbc_path = Path(config.SKILLLINE_DBC)
        if not dbc_path.exists():
            return

        try:
            self._skillline_cache = load_skillline_dbc(str(dbc_path))
            self._skillline_name_by_id = {
                sid: (name or f"SkillLine {sid}") for sid, name in self._skillline_cache
            }
        except Exception:
            # Don't pop errors during typing/loading; just skip decode
            self._skillline_cache = []
            self._skillline_name_by_id = {}

    def _pick_skillline_id_from_dbc(self) -> int | None:
        # Load once and cache
        if not hasattr(self, "_skillline_cache"):
            from config import SKILLLINE_DBC

            if not SKILLLINE_DBC.exists():
                QtWidgets.QMessageBox.warning(
                    self,
                    "Missing SkillLine.dbc",
                    f"SkillLine.dbc not found at:\n{SKILLLINE_DBC}",
                )
                return None

            try:
                self._skillline_cache = load_skillline_dbc(str(SKILLLINE_DBC))
                # id -> display name
                self._skillline_name_by_id = {
                    sid: (name or f"SkillLine {sid}")
                    for sid, name in self._skillline_cache
                }
            except Exception as e:
                QtWidgets.QMessageBox.critical(self, "DBC Error", str(e))
                return None

        dlg = SimplePickerDialog(
            title="Pick Skill Line",
            rows=self._skillline_cache,
            parent=self,
        )

        if dlg.exec() == QtWidgets.QDialog.DialogCode.Accepted:
            return dlg.chosen_id()

        return None
    
    def _refresh_zos_hint(self) -> None:
        mode = self._zos_mode.get("ZoneOrSort")
        hint = self._zos_hint.get("ZoneOrSort")
        ed = self._widgets.get("ZoneOrSort")

        if not mode or not hint or not ed:
            return

        is_zone = (mode.currentData() == "zone")

        try:
            val = int(ed.text().strip() or "0")
        except Exception:
            val = 0

        if is_zone:
            name = ""
            if val > 0:
                self._load_areatable_dbc()
                name = self._areatable_name_by_id.get(val, "")
            hint.setText(f"Zone: {val} — {name}" if name else f"Zone: {val}")
        else:
            sid = abs(val)
            name = ""
            if sid > 0:
                self._load_questsort_dbc()
                name = self._questsort_name_by_id.get(sid, "")
            hint.setText(f"Sort: {sid} — {name}" if name else f"Sort: {sid}")

    def _create_editor(self, col: str, label: str, ftype: str) -> QtWidgets.QWidget:
        # -----------------------------
        # ENUM dropdowns (Method, etc.)
        # -----------------------------
        if col in ENUM_FIELDS:
            key = ENUM_FIELDS[col]
            cb = QtWidgets.QComboBox()
            cb.setEditable(False)
            cb.setInsertPolicy(QtWidgets.QComboBox.InsertPolicy.NoInsert)

            cb.addItem("", "")  # blank
            for value, text in ENUM_OPTIONS.get(key, []):
                cb.addItem(text, value)

            cb.currentTextChanged.connect(lambda _t: self._update_dirty_title())
            return cb

        if ftype == "text" or col in TEXT_COLS:
            w = QtWidgets.QPlainTextEdit()
            w.setTabChangesFocus(True)
            w.setLineWrapMode(QtWidgets.QPlainTextEdit.LineWrapMode.WidgetWidth)
            w.setMinimumHeight(90)
            w.textChanged.connect(self._update_dirty_title)
        else:
            w = QtWidgets.QLineEdit()
            w.setPlaceholderText(label)
            w.textEdited.connect(self._update_dirty_title)

        w.setObjectName(col)
        return w

    def _pick_class_id(self, parent=None) -> Optional[int]:
        rows = [(cid, name) for cid, name in CLASS_ID_NAMES.items()]
        rows.sort(key=lambda x: x[0])
        dlg = SimplePickerDialog("Pick Class", rows, parent or self)
        if dlg.exec() == QtWidgets.QDialog.DialogCode.Accepted:
            return dlg.chosen_id()
        return None

    def _pick_skillline_id(self, parent=None) -> Optional[int]:
        """
        Try to pick SkillLine ID from DB if a skillline table exists.
        Falls back to manual ID entry if not available.
        """
        # Try a few common Trinity-ish tables/columns
        candidates = [
            ("skill_line", "id", "name"),
            ("skillline_dbc", "ID", "Name_Lang_enUS"),
            ("dbc_skillline", "ID", "Name_Lang_enUS"),
        ]

        for table, idcol, namecol in candidates:
            try:
                rows = self.db.fetch_all(
                    f"SELECT `{idcol}` AS id, `{namecol}` AS name FROM `{table}` ORDER BY `{idcol}` LIMIT 5000"
                )
                if rows:
                    data = [(int(r["id"]), str(r["name"] or "")) for r in rows]
                    dlg = SimplePickerDialog("Pick SkillLine", data, parent or self)
                    if dlg.exec() == QtWidgets.QDialog.DialogCode.Accepted:
                        return dlg.chosen_id()
                    return None
            except Exception:
                pass

        # Fallback: manual
        txt, ok = QtWidgets.QInputDialog.getInt(self, "SkillLine ID", "Enter SkillLine ID:", 0, 0, 2_000_000, 1)
        return int(txt) if ok else None

    def _bitmask_options_for_col(self, col: str) -> list[tuple[int, str]]:
        key = BITMASK_FIELDS.get(col)
        if not key:
            return []
        return BITMASK_OPTIONS.get(key, [])

    def _decode_mask(self, col: str, value: int) -> str:
        opts = self._bitmask_options_for_col(col)
        if not opts:
            return ""
        names = [name for bit, name in opts if value & bit]
        return ", ".join(names) if names else "—"
    
    def _open_bitmask_picker_value(self, options_key: str, current: int = 0) -> int | None:
        """
        Same idea as _open_bitmask_picker(), but returns an int instead of writing to a specific column.
        """
        opts = BITMASK_OPTIONS.get(options_key, [])
        if not opts:
            QtWidgets.QMessageBox.warning(self, "No options", f"No bitmask options for: {options_key}")
            return None

        dlg = QtWidgets.QDialog(self)
        dlg.setWindowTitle("Pick Flags")
        dlg.setModal(True)
        dlg.resize(420, 520)

        v = QtWidgets.QVBoxLayout(dlg)

        info = QtWidgets.QLabel("Check the flags you want set:")
        info.setStyleSheet("color: #A9B1BA;")
        v.addWidget(info)

        scroll = QtWidgets.QScrollArea()
        scroll.setWidgetResizable(True)
        v.addWidget(scroll, 1)

        inner = QtWidgets.QWidget()
        form = QtWidgets.QVBoxLayout(inner)
        form.setContentsMargins(10, 10, 10, 10)
        form.setSpacing(6)

        checks: list[tuple[int, QtWidgets.QCheckBox]] = []
        for bit, name in opts:
            cb = QtWidgets.QCheckBox(f"{name}  ({bit})")
            cb.setChecked(bool(current & bit))
            checks.append((bit, cb))
            form.addWidget(cb)

        form.addStretch(1)
        scroll.setWidget(inner)

        buttons = QtWidgets.QDialogButtonBox(
            QtWidgets.QDialogButtonBox.StandardButton.Ok
            | QtWidgets.QDialogButtonBox.StandardButton.Cancel
        )
        v.addWidget(buttons)

        buttons.accepted.connect(dlg.accept)
        buttons.rejected.connect(dlg.reject)

        if dlg.exec() != QtWidgets.QDialog.DialogCode.Accepted:
            return None

        val = 0
        for bit, cb in checks:
            if cb.isChecked():
                val |= bit
        return val

    def _open_bitmask_picker(self, col: str) -> None:
        w = self._widgets.get(col)
        if not w or not isinstance(w, QtWidgets.QLineEdit):
            return

        opts = self._bitmask_options_for_col(col)
        if not opts:
            QtWidgets.QMessageBox.information(self, "No options", f"No bitmask options configured for {col}.")
            return

        cur = 0
        try:
            cur = int((w.text() or "0").strip() or "0")
        except Exception:
            cur = 0

        dlg = BitmaskPickerDialog(f"{col} Picker", opts, cur, self)
        if dlg.exec() == QtWidgets.QDialog.DialogCode.Accepted:
            w.setText(str(dlg.value()))
            # update decoded label if present
            self._update_bitmask_label(col)
            self._update_dirty_title()

    def _update_bitmask_label(self, col: str) -> None:
        lbl = getattr(self, "_bitmask_labels", {}).get(col)
        if not lbl:
            return
        w = self._widgets.get(col)
        if not w or not isinstance(w, QtWidgets.QLineEdit):
            return
        try:
            v = int((w.text() or "0").strip() or "0")
        except Exception:
            v = 0
        lbl.setText(self._decode_mask(col, v))

    def _open_id_picker(self, col: str) -> None:
        # Decide picker type based on column
        if col in ITEM_ID_COLS:
            dlg = IDPickerDialog(self.db, "item", self)
            dlg.q.setText(_get_widget_text(self._widgets[col]))
            dlg.run_search()
            if dlg.exec() == QtWidgets.QDialog.DialogCode.Accepted:
                picked = dlg.selected_id()
                if picked is not None:
                    self._widgets[col].setText(str(picked))
                    self._update_inline_name(col)
                    self._update_dirty_title()
            return

        if col in CREATURE_GO_ID_COLS:
            # Tiny choice dialog: Creature vs GO
            m = QtWidgets.QMessageBox(self)
            m.setWindowTitle("Pick Type")
            m.setText("Search which template?")
            btn_cre = m.addButton("Creature", QtWidgets.QMessageBox.ButtonRole.AcceptRole)
            btn_go = m.addButton("GameObject", QtWidgets.QMessageBox.ButtonRole.AcceptRole)
            m.addButton("Cancel", QtWidgets.QMessageBox.ButtonRole.RejectRole)
            m.exec()

            clicked = m.clickedButton()
            if clicked not in (btn_cre, btn_go):
                return

            mode = "creature" if clicked == btn_cre else "go"
            dlg = IDPickerDialog(self.db, mode, self)
            dlg.q.setText(_get_widget_text(self._widgets[col]))
            dlg.run_search()
            if dlg.exec() == QtWidgets.QDialog.DialogCode.Accepted:
                picked = dlg.selected_id()
                if picked is not None:
                    self._widgets[col].setText(str(picked))
                    self._update_inline_name(col)
                    self._update_dirty_title()
            return

    def _run_pending_lookups(self) -> None:
        pending = list(self._lookup_pending)
        self._lookup_pending.clear()
        for col in pending:
            self._update_inline_name(col)

    def _schedule_lookup(self, col: str) -> None:
        if col not in self._name_labels:
            return
        self._lookup_pending.add(col)
        # Small delay so fast typing doesn't hit DB repeatedly
        self._lookup_timer.start(120)

    def _get_required_item_ids(self) -> list[int]:
        ids: list[int] = []
        for n in range(1, 7):
            w = self._widgets.get(f"ReqItemId{n}")
            if not w:
                continue
            try:
                raw = (w.text() or "").strip()
                v = int(raw) if raw else 0
            except Exception:
                v = 0
            if v > 0:
                ids.append(v)
        return ids


    def _hook_required_item_autosync(self) -> None:
        # connect ReqItemId fields -> debounce -> sync tab
        for n in range(1, 7):
            w = self._widgets.get(f"ReqItemId{n}")
            if not w:
                continue
            if hasattr(w, "textChanged"):
                w.textChanged.connect(lambda _=None: self._loot_sync_timer.start())


    def _sync_loot_from_required_items(self) -> None:
        if not hasattr(self, "quest_loot"):
            return
        if getattr(self, "current_id", None) is None:
            return
        item_ids = self._get_required_item_ids()
        # Ensure tab is on the correct quest + sync rows
        self.quest_loot.load(int(self.current_id))
        self.quest_loot.sync_from_required_items(item_ids)

    def _set_inline_label(self, col: str, text: str) -> None:
        lbl = self._name_labels.get(col)
        if not lbl:
            return
        lbl.setText(text)

    def _lookup_item_name(self, entry: int) -> str:
        if entry <= 0:
            return ""
        if entry in self._item_name_cache:
            return self._item_name_cache[entry]
        r = self.db.fetch_one("SELECT name FROM item_template WHERE entry=%s LIMIT 1", (entry,))
        name = (r.get("name") if r else "") or ""
        self._item_name_cache[entry] = name
        return name

    def _lookup_creature_name(self, entry: int) -> str:
        if entry <= 0:
            return ""
        if entry in self._cre_name_cache:
            return self._cre_name_cache[entry]
        r = self.db.fetch_one("SELECT name FROM creature_template WHERE entry=%s LIMIT 1", (entry,))
        name = (r.get("name") if r else "") or ""
        self._cre_name_cache[entry] = name
        return name

    def _lookup_go_name(self, entry: int) -> str:
        if entry <= 0:
            return ""
        if entry in self._go_name_cache:
            return self._go_name_cache[entry]
        r = self.db.fetch_one("SELECT name FROM gameobject_template WHERE entry=%s LIMIT 1", (entry,))
        name = (r.get("name") if r else "") or ""
        self._go_name_cache[entry] = name
        return name

    def _update_inline_name(self, col: str) -> None:
        w = self._widgets.get(col)
        if not w:
            return

        # We only attach inline name labels to ID line edits
        raw = _get_widget_text(w).strip()
        n = _try_int(raw)

        if not n or n <= 0:
            self._set_inline_label(col, "—")
            return

        if col in ITEM_ID_COLS:
            name = self._lookup_item_name(n)
            self._set_inline_label(col, name if name else "(not found)")
            return

        if col in CREATURE_GO_ID_COLS:
            cname = self._lookup_creature_name(n)
            if cname:
                self._set_inline_label(col, f"Creature: {cname}")
                return
            gname = self._lookup_go_name(n)
            if gname:
                self._set_inline_label(col, f"GO: {gname}")
                return
            self._set_inline_label(col, "(not found)")
            return

        # Default fallback (shouldn't happen if wired correctly)
        self._set_inline_label(col, "")

    def _open_objective_builder(self) -> None:
        # Pull current values from widgets
        get = lambda c: _get_widget_text(self._widgets[c]).strip() if c in self._widgets else ""
        cur = {
            "ObjectiveText1": get("ObjectiveText1"),
            "ObjectiveText2": get("ObjectiveText2"),
            "ObjectiveText3": get("ObjectiveText3"),
            "ObjectiveText4": get("ObjectiveText4"),
            "ReqCreatureOrGOId1": get("ReqCreatureOrGOId1"),
            "ReqCreatureOrGOId2": get("ReqCreatureOrGOId2"),
            "ReqCreatureOrGOId3": get("ReqCreatureOrGOId3"),
            "ReqCreatureOrGOId4": get("ReqCreatureOrGOId4"),
            "ReqCreatureOrGOCount1": get("ReqCreatureOrGOCount1"),
            "ReqCreatureOrGOCount2": get("ReqCreatureOrGOCount2"),
            "ReqCreatureOrGOCount3": get("ReqCreatureOrGOCount3"),
            "ReqCreatureOrGOCount4": get("ReqCreatureOrGOCount4"),
            "ReqItemId1": get("ReqItemId1"),
            "ReqItemId2": get("ReqItemId2"),
            "ReqItemId3": get("ReqItemId3"),
            "ReqItemId4": get("ReqItemId4"),
            "ReqItemId5": get("ReqItemId5"),
            "ReqItemId6": get("ReqItemId6"),
            "ReqItemCount1": get("ReqItemCount1"),
            "ReqItemCount2": get("ReqItemCount2"),
            "ReqItemCount3": get("ReqItemCount3"),
            "ReqItemCount4": get("ReqItemCount4"),
            "ReqItemCount5": get("ReqItemCount5"),
            "ReqItemCount6": get("ReqItemCount6"),
            "ReqSpellCast1": get("ReqSpellCast1"),
            "ReqSpellCast2": get("ReqSpellCast2"),
            "ReqSpellCast3": get("ReqSpellCast3"),
            "ReqSpellCast4": get("ReqSpellCast4"),
            "Objectives": get("Objectives"),
        }

        dlg = ObjectiveBuilderDialog(self, self.db, initial=cur)
        if dlg.exec() != QtWidgets.QDialog.DialogCode.Accepted:
            return

        out = dlg.result_values()

        # Write back into widgets
        for k, v in out.items():
            if k in self._widgets:
                _set_widget_text(self._widgets[k], v)

        # Refresh dirty + any inline lookups if you have them
        self._update_dirty_title()
        if hasattr(self, "_name_labels"):
            for c in list(getattr(self, "_name_labels", {}).keys()):
                self._schedule_lookup(c)

    def _on_tab_changed(self, idx: int) -> None:
        if self.current_id is None:
            return
        if self.tabs.widget(idx) is self.quest_loot:
            # Ensure loot editor is pointed at the current quest
            if getattr(self.quest_loot, "quest_id", None) != int(self.current_id):
                self.quest_loot.load(int(self.current_id))
   
    def load(self, quest_id: int) -> None:
        row = self.db.fetch_one("SELECT * FROM quest_template WHERE entry = %s", (quest_id,))
        if not row:
            QtWidgets.QMessageBox.warning(self, "Not found", f"Quest {quest_id} not found.")
            return

        self.current_id = quest_id
        self._orig = dict(row)

        # Populate fields we know about; ignore others.
        for col, widget in self._widgets.items():

            # --- Special decode: SkillOrClassMask ---
            if col == "SkillOrClassMask" and col in self._soc_mode:
                raw = row.get(col, 0) or 0
                try:
                    raw = int(raw)
                except Exception:
                    raw = 0

                mode = self._soc_mode[col]
                val_edit = widget

                if raw < 0:
                    mode.setCurrentText("Class Mask")
                    val_edit.setText(str(abs(raw)))
                else:
                    mode.setCurrentText("Skill")
                    val_edit.setText(str(raw))

                # refresh live decode label
                if hasattr(self, "_soc_refresh") and col in self._soc_refresh:
                    try:
                        self._soc_refresh[col]()
                    except Exception:
                        pass

                continue

            # --- Special decode: ZoneOrSort ---
            if col == "ZoneOrSort" and col in self._zos_mode:
                raw = row.get(col, 0) or 0
                try:
                    raw = int(raw)
                except Exception:
                    raw = 0

                mode = self._zos_mode[col]
                val_edit = widget

                if raw < 0:
                    mode.setCurrentText("Sort")
                    val_edit.setText(str(abs(raw)))
                else:
                    mode.setCurrentText("Zone")
                    val_edit.setText(str(raw))

                if hasattr(self, "_zos_refresh") and col in self._zos_refresh:
                    try:
                        self._zos_refresh[col]()
                    except Exception:
                        pass

                continue

            # --- Normal fields ---
            _set_widget_text(widget, row.get(col, ""))


        # Refresh inline names after loading
        for col in list(self._name_labels.keys()):
            self._update_inline_name(col)

        # Load starters/enders relation lists
        if hasattr(self, "relations"):
            self.relations.load(quest_id)

        # Auto-load + auto-sync quest loot conditions
        if hasattr(self, "quest_loot"):
            self.quest_loot.load(quest_id)
            self.quest_loot.sync_from_required_items(self._get_required_item_ids())

        self.log(f"Loaded quest {quest_id}: {row.get('Title','')}")
        self._update_dirty_title()
        # Refresh decoded bitmask labels after loading
        if hasattr(self, "_bitmask_labels"):
            for col in list(self._bitmask_labels.keys()):
                self._update_bitmask_label(col)
  
        
    def _collect(self) -> Dict[str, Any]:
        data: Dict[str, Any] = {}

        for col, widget in self._widgets.items():
            raw = _get_widget_text(widget).strip()
            ftype = self._ftypes.get(col, "str")
            # Special: Trinity SkillOrClassMask signed storage
            # Skill mode => +SkillLineId
            # Class mode => -ClassId
            if col == "SkillOrClassMask" and col in self._soc_mode:
                mode = self._soc_mode[col]
                if raw == "":
                    data[col] = 0
                else:
                    try:
                        n = int(raw)
                    except Exception:
                        n = 0
                    data[col] = (-abs(n)) if mode.currentText() == "Class Mask" else abs(n)
                continue
            
            # Special: ZoneOrSort signed storage
            # Zone mode => +AreaTableId
            # Sort mode => -SortId
            if col == "ZoneOrSort" and col in self._zos_mode:
                mode = self._zos_mode[col]
                if raw == "":
                    data[col] = 0
                else:
                    try:
                        n = int(raw)
                    except Exception:
                        n = 0
                    data[col] = (-abs(n)) if mode.currentText() == "Sort" else abs(n)
                continue

            # Treat schema TEXT columns as TEXT no matter what
            if col in TEXT_COLS or ftype == "text":
                data[col] = raw
                continue

            # Empty -> None for non-text fields (lets DB defaults apply if you use INSERT later)
            if raw == "":
                data[col] = None
                continue

            # Convert by ftype (metadata-driven)
            try:
                if ftype in ("int", "uint", "tinyint", "smallint", "mediumint", "bigint"):
                    data[col] = int(raw)
                elif ftype in ("float", "double", "decimal"):
                    data[col] = float(raw)
                else:
                    # fallback (string)
                    data[col] = raw
            except ValueError:
                # If someone types non-numeric into numeric field, store raw (and let DB complain if needed)
                data[col] = raw

        return data

    def _diff(self, data: Dict[str, Any]) -> List[Tuple[str, Any, Any]]:
        diffs = []
        for k, newv in data.items():
            oldv = self._orig.get(k)
            if str(oldv) != str(newv):
                diffs.append((k, oldv, newv))
        return diffs

    def _update_dirty_title(self) -> None:
        win = self.window()  # top-level window
        if not win:
            return

        if not self.current_id:
            win.setWindowTitle("Quest Editor")
            return

        diffs = self._diff(self._collect())
        mark = " *" if diffs else ""
        win.setWindowTitle(f"Quest {self.current_id}{mark}")
    
    def preview_quest(self) -> None:
        if self.current_id is None:
            return

        data = self._collect()
        dlg = QuestPreviewDialog(data, self)
        dlg.exec()

    def delete_quest(self) -> None:
        if self.current_id is None:
            return

        title = self._widgets.get("Title")
        title_text = ""
        if title:
            title_text = title.toPlainText() if hasattr(title, "toPlainText") else title.text()

        preview = self.db.preview_delete_quest(self.current_id)

        loot_lines = []
        for table, count in preview["loot_rows_by_table"].items():
            loot_lines.append(f"{table}: {count}")

        loot_text = "\n".join(loot_lines) if loot_lines else "(none)"

        msg = (
            f"DELETE QUEST {self.current_id}?\n\n"
            f"{title_text}\n\n"
            "This cannot be undone.\n\n"
            "Preview:\n"
            f"- Condition groups: {preview['anchor_groups']}\n"
            f"- Condition rows: {preview['conditions_rows']}\n"
            f"- Loot rows:\n{loot_text}"
        )
        
        if QtWidgets.QMessageBox.warning(
            self,
            "Delete Quest",
            msg,
            QtWidgets.QMessageBox.StandardButton.Yes
            | QtWidgets.QMessageBox.StandardButton.No,
        ) != QtWidgets.QMessageBox.StandardButton.Yes:
            return



        try:
            self.db.delete_quest(self.current_id)
            self.db.commit()
        except Exception as e:
            self.db.rollback()
            QtWidgets.QMessageBox.critical(self, "Delete failed", str(e))
            return

        self.log(f"Deleted quest {self.current_id}")

        # Clear editor
        self.current_id = None
        self._orig.clear()
        for w in self._widgets.values():
            if isinstance(w, QtWidgets.QPlainTextEdit):
                w.setPlainText("")
            elif isinstance(w, QtWidgets.QComboBox):
                # Clear selection safely
                if w.count() > 0:
                    w.setCurrentIndex(0)
                else:
                    w.setCurrentIndex(-1)
            elif isinstance(w, QtWidgets.QLineEdit):
                w.setText("")

        self.setWindowTitle("Quest Editor")

    def new_quest(self) -> None:
        # Prevent accidental overwrite of unsaved changes
        if self.current_id is not None:
            diffs = self._diff(self._collect())
            if diffs:
                r = QtWidgets.QMessageBox.question(
                    self,
                    "Unsaved Changes",
                    "You have unsaved changes.\nCreate a new quest anyway?",
                    QtWidgets.QMessageBox.StandardButton.Yes
                    | QtWidgets.QMessageBox.StandardButton.No,
                )
                if r != QtWidgets.QMessageBox.StandardButton.Yes:
                    return

        try:
            row = self.db.fetch_one(
                """
                SELECT COALESCE(MAX(entry), %s - 1) AS m
                FROM quest_template
                WHERE entry BETWEEN %s AND %s
                """,
                (QUEST_ID_MIN, QUEST_ID_MIN, QUEST_ID_MAX),
            )

            new_id = int(row["m"]) + 1
            if new_id > QUEST_ID_MAX:
                QtWidgets.QMessageBox.critical(
                    self,
                    "Quest ID Range Exhausted",
                    f"No free quest IDs in range {QUEST_ID_MIN}–{QUEST_ID_MAX}",
                )
                return

            self.db.create_quest(new_id)
            self.db.commit()
        except Exception as e:
            self.db.rollback()
            QtWidgets.QMessageBox.critical(self, "Create failed", str(e))
            return

        self.log(f"Created new quest {new_id}")
        self.load(new_id)

        # Focus Title field
        w = self._widgets.get("Title")
        if isinstance(w, QtWidgets.QPlainTextEdit):
            w.setFocus()
        elif isinstance(w, QtWidgets.QLineEdit):
            w.setFocus()

    def reload(self) -> None:
        if self.current_id is None:
            return
        self.load(self.current_id)
      
    def save(self) -> None:
        if self.current_id is None:
            return
        data = self._collect()
        data["entry"] = self.current_id

        diffs = self._diff(data)
        if not diffs:
            self.log("No changes to save.")
            return

        # Diff preview (small but professional)
        preview = "\n".join([f"{k}: {old}  ->  {new}" for k, old, new in diffs])
        ok = QtWidgets.QMessageBox.question(
            self,
            "Confirm Save",
            f"Save {len(diffs)} change(s) to quest {self.current_id}?\n\n{preview[:1800]}",
        )
        if ok != QtWidgets.QMessageBox.StandardButton.Yes:
            return

        # Build UPDATE for only changed columns (safer)
        cols = [k for k, _, _ in diffs if k != "entry"]
        sets = ", ".join([f"`{c}`=%s" for c in cols])
        sql = f"UPDATE quest_template SET {sets} WHERE entry=%s"
        params = [data[c] for c in cols] + [self.current_id]

        try:
            self.db.execute(sql, params)
            self.db.commit()
            self.log(f"Saved quest {self.current_id} ({len(cols)} fields).")
            self.load(self.current_id)  # refresh orig snapshot
        except Exception as e:
            self.db.rollback()
            QtWidgets.QMessageBox.critical(self, "Save failed", str(e))
            self.log(f"ERROR saving quest {self.current_id}: {e}")

def _as_int(v, default=0) -> int:
    try:
        if v is None or v == "":
            return default
        return int(v)
    except Exception:
        return default

def _money_to_text(copper: int) -> str:
    sign = "-" if copper < 0 else ""
    copper = abs(copper)
    g = copper // 10000
    s = (copper % 10000) // 100
    c = copper % 100
    parts = []
    if g:
        parts.append(f"{g}g")
    if s:
        parts.append(f"{s}s")
    if c or not parts:
        parts.append(f"{c}c")
    return sign + " ".join(parts)

def _render_reward_lines(d: dict, lookup=None):
    """
    Returns (choice_lines, guaranteed_lines)
    lookup(kind, id)->name optional
    """
    def item_name(i):
        if lookup:
            n = lookup("item", i)
            if n:
                return n
        return f"Item {i}"

    def currency_name(i):
        if lookup:
            n = lookup("currency", i)
            if n:
                return n
        return f"Currency {i}"

    choice = []
    guaranteed = []

    # Choice items
    for n in range(1, 7):
        iid = _as_int(d.get(f"RewChoiceItemId{n}"))
        cnt = _as_int(d.get(f"RewChoiceItemCount{n}"), 1)
        if iid > 0:
            choice.append(f"{item_name(iid)} ×{cnt}")

    # Guaranteed items
    for n in range(1, 5):
        iid = _as_int(d.get(f"RewItemId{n}"))
        cnt = _as_int(d.get(f"RewItemCount{n}"), 1)
        if iid > 0:
            guaranteed.append(f"{item_name(iid)} ×{cnt}")

    # Money
    money = _as_int(d.get("RewOrReqMoney"))
    if money != 0:
        guaranteed.append(f"Money: {_money_to_text(money)}")

    # Currencies
    for n in range(1, 5):
        cid = _as_int(d.get(f"RewCurrencyId{n}"))
        cnt = _as_int(d.get(f"RewCurrencyCount{n}"))
        if cid > 0 and cnt > 0:
            guaranteed.append(f"{currency_name(cid)} ×{cnt}")

    # Spells
    rs = _as_int(d.get("RewSpell"))
    rsc = _as_int(d.get("RewSpellCast"))
    if rs > 0:
        guaranteed.append(f"Reward Spell: Spell {rs}")
    if rsc > 0:
        guaranteed.append(f"Cast on Turn-in: Spell {rsc}")

    return choice, guaranteed

class IdPickerDialog(QtWidgets.QDialog):
    """
    Tiny searchable ID picker (single-file friendly).
    Supports: items, creatures, gameobjects.
    """
    def __init__(self, parent, db, kind: str):
        super().__init__(parent)
        self.db = db
        self.kind = kind
        self._chosen_id = None

        self.setWindowTitle(f"Pick {kind.title()} ID")
        self.resize(760, 520)

        self.search = QtWidgets.QLineEdit()
        self.search.setPlaceholderText("Type to search by name (or enter an ID)…")
        self.search.returnPressed.connect(self._run)

        self.btn = QtWidgets.QPushButton("Search")
        self.btn.clicked.connect(self._run)

        top = QtWidgets.QHBoxLayout()
        top.addWidget(self.search, 1)
        top.addWidget(self.btn, 0)

        self.table = QtWidgets.QTableWidget(0, 2)
        self.table.setHorizontalHeaderLabels(["ID", "Name"])
        self.table.setSelectionBehavior(QtWidgets.QAbstractItemView.SelectionBehavior.SelectRows)
        self.table.setEditTriggers(QtWidgets.QAbstractItemView.EditTrigger.NoEditTriggers)
        self.table.doubleClicked.connect(self._accept_from_selection)
        self.table.horizontalHeader().setStretchLastSection(True)

        btns = QtWidgets.QDialogButtonBox(
            QtWidgets.QDialogButtonBox.StandardButton.Cancel |
            QtWidgets.QDialogButtonBox.StandardButton.Ok
        )
        btns.accepted.connect(self._accept_from_selection)
        btns.rejected.connect(self.reject)

        lay = QtWidgets.QVBoxLayout(self)
        lay.addLayout(top)
        lay.addWidget(self.table, 1)
        lay.addWidget(btns)

        self._run()

    def _sql(self):
        if self.kind == "item":
            return "SELECT entry AS id, name FROM item_template WHERE name LIKE %s ORDER BY entry DESC LIMIT 250"
        if self.kind == "creature":
            return "SELECT entry AS id, name FROM creature_template WHERE name LIKE %s ORDER BY entry DESC LIMIT 250"
        if self.kind == "gameobject":
            return "SELECT entry AS id, name FROM gameobject_template WHERE name LIKE %s ORDER BY entry DESC LIMIT 250"
        raise ValueError("Unknown kind")

    def _run(self):
        q = (self.search.text() or "").strip()

        # If user typed an integer ID, we accept it immediately.
        if q and q.lstrip("-").isdigit():
            self._chosen_id = int(q)
            self.accept()
            return

        like = f"%{q}%" if q else "%"

        rows = self.db.fetch_all(self._sql(), (like,))
        self.table.setRowCount(0)
        for r in rows:
            rid = int(r["id"])
            name = r.get("name") or ""
            rowi = self.table.rowCount()
            self.table.insertRow(rowi)
            self.table.setItem(rowi, 0, QtWidgets.QTableWidgetItem(str(rid)))
            self.table.setItem(rowi, 1, QtWidgets.QTableWidgetItem(name))

        if self.table.rowCount():
            self.table.selectRow(0)

    def _accept_from_selection(self):
        sel = self.table.selectionModel().selectedRows()
        if not sel:
            return
        row = sel[0].row()
        it = self.table.item(row, 0)
        if not it:
            return
        try:
            self._chosen_id = int(it.text())
        except Exception:
            return
        self.accept()

    def chosen_id(self):
        return self._chosen_id


class ObjectiveBuilderDialog(QtWidgets.QDialog):
    """
    Objective builder -> writes:
    - ObjectiveText1-4
    - ReqCreatureOrGOId1-4 (+ negative for GO)
    - ReqCreatureOrGOCount1-4
    - ReqItemId1-6 / ReqItemCount1-6
    - ReqSpellCast1-4
    - Objectives (main text) from objective lines
    """
    TYPES = ["None", "Creature", "GameObject", "Item", "SpellCast"]

    def __init__(self, parent, db, initial: dict):
        super().__init__(parent)
        self.db = db
        self.initial = initial
        self.setWindowTitle("Objective Builder")
        self.resize(920, 560)

        hint = QtWidgets.QLabel(
            "Creature objectives store positive IDs. GameObject objectives store NEGATIVE IDs in ReqCreatureOrGOId# (Trinity)."
        )
        hint.setStyleSheet("color: #A9B1BA;")

        # Grid of 4 objective slots
        self.rows = []
        grid = QtWidgets.QGridLayout()
        grid.setHorizontalSpacing(8)
        grid.setVerticalSpacing(6)

        headers = ["#", "Type", "ID", "", "Count", "Objective Text", "", "Name Preview"]
        for i, h in enumerate(headers):
            lab = QtWidgets.QLabel(h)
            lab.setStyleSheet("font-weight: 600;")
            grid.addWidget(lab, 0, i)

        for idx in range(1, 5):
            lbl = QtWidgets.QLabel(str(idx))

            typ = QtWidgets.QComboBox()
            typ.addItems(self.TYPES)
            typ.setFixedWidth(120)

            id_edit = QtWidgets.QLineEdit()
            id_edit.setPlaceholderText("ID")
            id_edit.setFixedWidth(140)

            btn_pick = QtWidgets.QPushButton("Pick…")
            btn_pick.setFixedWidth(70)

            cnt = QtWidgets.QSpinBox()
            cnt.setRange(0, 9999)
            cnt.setFixedWidth(70)

            text = QtWidgets.QLineEdit()
            text.setPlaceholderText(f"ObjectiveText{idx}")

            btn_auto = QtWidgets.QPushButton("Auto")
            btn_auto.setFixedWidth(60)
            btn_auto.setToolTip("Auto-fill Objective Text from Type/ID/Count")

            # ✅ FIX: define name label
            name = QtWidgets.QLabel("—")
            name.setStyleSheet("color: #A9B1BA;")
            name.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)

            # Add to layout
            grid.addWidget(lbl, idx, 0)
            grid.addWidget(typ, idx, 1)
            grid.addWidget(id_edit, idx, 2)
            grid.addWidget(btn_pick, idx, 3)
            grid.addWidget(cnt, idx, 4)
            grid.addWidget(text, idx, 5)
            grid.addWidget(btn_auto, idx, 6)
            grid.addWidget(name, idx, 7)

            # Store row widgets
            self.rows.append({
                "type": typ,
                "id": id_edit,
                "pick": btn_pick,
                "count": cnt,
                "text": text,
                "auto": btn_auto,
                "name": name,
            })

            # connect picker per row
            def make_pick(row_idx: int):
                def _pick():
                    t = self.rows[row_idx]["type"].currentText()
                    if t == "Item":
                        dlg = IdPickerDialog(self, self.db, "item")
                    elif t == "Creature":
                        dlg = IdPickerDialog(self, self.db, "creature")
                    elif t == "GameObject":
                        dlg = IdPickerDialog(self, self.db, "gameobject")
                    else:
                        return

                    if dlg.exec() == QtWidgets.QDialog.DialogCode.Accepted:
                        cid = dlg.chosen_id()
                        if cid is not None:
                            self.rows[row_idx]["id"].setText(str(cid))
                            # ✅ FIX: use row_idx, not row_index
                            self._autofill_objective_text(row_idx)
                            self._refresh_preview()
                return _pick

            def make_auto(row_idx: int):
                def _auto():
                    self._autofill_objective_text(row_idx)
                    self._refresh_preview()
                return _auto

            btn_pick.clicked.connect(make_pick(idx - 1))
            # ✅ FIX: actually connect auto button
            btn_auto.clicked.connect(make_auto(idx - 1))

            # optional: refresh preview as user types
            id_edit.textEdited.connect(lambda _t, _row=idx - 1: self._refresh_preview())
            text.textEdited.connect(lambda _t, _row=idx - 1: self._refresh_preview())
            cnt.valueChanged.connect(lambda _v, _row=idx - 1: self._refresh_preview())
            typ.currentIndexChanged.connect(lambda _i, _row=idx - 1: self._refresh_preview())

        # Preview of Objectives (main)
        self.preview = QtWidgets.QPlainTextEdit()
        self.preview.setReadOnly(True)
        self.preview.setMinimumHeight(140)

        self.btn_preview = QtWidgets.QPushButton("Update Preview")
        self.btn_preview.clicked.connect(self._refresh_preview)

        btns = QtWidgets.QDialogButtonBox(
            QtWidgets.QDialogButtonBox.StandardButton.Cancel |
            QtWidgets.QDialogButtonBox.StandardButton.Ok
        )
        btns.accepted.connect(self.accept)
        btns.rejected.connect(self.reject)

        lay = QtWidgets.QVBoxLayout(self)
        lay.addWidget(hint)
        lay.addLayout(grid)
        lay.addWidget(self.btn_preview, 0)
        lay.addWidget(QtWidgets.QLabel("Objectives (auto-built from objective lines):"))
        lay.addWidget(self.preview, 1)
        lay.addWidget(btns)

        self._load_from_initial()
        self._refresh_preview()

    def _load_from_initial(self):
        # Seed ObjectiveText lines
        for i in range(1, 5):
            self.rows[i - 1]["text"].setText((self.initial.get(f"ObjectiveText{i}") or "").strip())

        # Seed Creature/GO from ReqCreatureOrGO*
        for i in range(1, 5):
            rid = self.initial.get(f"ReqCreatureOrGOId{i}") or 0
            rct = self.initial.get(f"ReqCreatureOrGOCount{i}") or 0
            if not rid:
                continue
            try:
                n = int(rid)
            except Exception:
                continue
            if n < 0:
                self.rows[i - 1]["type"].setCurrentText("GameObject")
                self.rows[i - 1]["id"].setText(str(abs(n)))
            else:
                self.rows[i - 1]["type"].setCurrentText("Creature")
                self.rows[i - 1]["id"].setText(str(n))
            try:
                self.rows[i - 1]["count"].setValue(int(rct) if rct else 0)
            except Exception:
                pass

        # Seed Items into empty rows (best-effort)
        items = []
        for i in range(1, 7):
            iid = (self.initial.get(f"ReqItemId{i}") or "").strip()
            ict = (self.initial.get(f"ReqItemCount{i}") or "").strip()
            if iid and iid != "0":
                items.append((iid, ict))
        rowi = 0
        for iid, ict in items:
            while rowi < 4 and self.rows[rowi]["type"].currentText() != "None":
                rowi += 1
            if rowi >= 4:
                break
            self.rows[rowi]["type"].setCurrentText("Item")
            self.rows[rowi]["id"].setText(iid)
            try:
                self.rows[rowi]["count"].setValue(int(ict) if ict else 0)
            except Exception:
                pass
            rowi += 1

        # Seed SpellCast into empty rows (best-effort)
        spells = []
        for i in range(1, 5):
            sid = (self.initial.get(f"ReqSpellCast{i}") or "").strip()
            if sid and sid != "0":
                spells.append(sid)
        rowi = 0
        for sid in spells:
            while rowi < 4 and self.rows[rowi]["type"].currentText() != "None":
                rowi += 1
            if rowi >= 4:
                break
            self.rows[rowi]["type"].setCurrentText("SpellCast")
            self.rows[rowi]["id"].setText(sid)
            self.rows[rowi]["count"].setValue(1)
            rowi += 1
    
    def _safe_int(self, s: str, default: int = 0) -> int:
        """Parse an int safely from a QLineEdit string."""
        try:
            s = (s or "").strip()
            if s == "":
                return default
            return int(s)
        except Exception:
            return default
    
    def _lookup_name(self, typ: str, rid: int) -> str:
        """Lookup display name for an objective row based on type and id."""
        if not rid:
            return ""

        try:
            if typ == "Item":
                row = self.db.fetch_one(
                    "SELECT name FROM item_template WHERE entry=%s LIMIT 1",
                    (rid,),
                )
                return (row.get("name") or "").strip() if row else ""

            if typ == "Creature":
                row = self.db.fetch_one(
                    "SELECT name FROM creature_template WHERE entry=%s LIMIT 1",
                    (rid,),
                )
                return (row.get("name") or "").strip() if row else ""

            if typ == "GameObject":
                row = self.db.fetch_one(
                    "SELECT name FROM gameobject_template WHERE entry=%s LIMIT 1",
                    (rid,),
                )
                return (row.get("name") or "").strip() if row else ""

            if typ == "SpellCast":
                # Optional: if you later add spell lookup tables, hook here.
                return f"Spell {rid}"

        except Exception:
            # Don't crash the builder if lookup fails
            return ""

        return ""

    def _autofill_objective_text(self, row_index: int) -> None:
        r = self.rows[row_index]
        typ = r["type"].currentText()
        rid = self._safe_int(r["id"].text())
        cnt = int(r["count"].value())

        if typ == "None" or rid <= 0:
            return

        # Resolve display name when possible
        nm = ""
        if typ in ("Item", "Creature", "GameObject"):
            nm = self._lookup_name(typ, rid)
            if not nm or nm == "—":
                nm = ""
            # Update the inline name label for this row
            try:
                r["name"].setText(nm if nm else "—")
            except Exception:
                pass

        # Build a clean, client-style-ish objective line
        if typ == "Item":
            if cnt <= 0:
                cnt = 1
                r["count"].setValue(cnt)
            if nm:
                r["text"].setText(f"Collect {cnt} {nm}")
            else:
                r["text"].setText(f"Collect {cnt} item(s) ({rid})")

        elif typ == "Creature":
            if cnt <= 0:
                cnt = 1
                r["count"].setValue(cnt)
            if nm:
                r["text"].setText(f"Slay {cnt} {nm}")
            else:
                r["text"].setText(f"Slay {cnt} creature(s) ({rid})")

        elif typ == "GameObject":
            # Trinity convention stores GO negative in DB, but here we show positive entry.
            if cnt <= 0:
                cnt = 1
                r["count"].setValue(cnt)
            if nm:
                # Some quests say "Use" or "Interact with" rather than "Gather from"
                r["text"].setText(f"Interact with {nm} ({cnt})")
            else:
                r["text"].setText(f"Interact with gameobject ({rid}) ({cnt})")

        elif typ == "SpellCast":
            # Without a spell table, keep it generic.
            if nm:
                r["text"].setText(f"Cast {nm}")
            else:
                r["text"].setText(f"Cast spell {rid}")

    def _refresh_preview(self):
        lines = []
        for r in self.rows:
            t = (r["text"].text() or "").strip()
            if t:
                lines.append(t)
        self.preview.setPlainText("\n".join(lines))

    def result_values(self) -> dict:
        out = {}

        # Clear fields first
        for i in range(1, 5):
            out[f"ObjectiveText{i}"] = ""
            out[f"ReqCreatureOrGOId{i}"] = "0"
            out[f"ReqCreatureOrGOCount{i}"] = "0"
            out[f"ReqSpellCast{i}"] = "0"
        for i in range(1, 7):
            out[f"ReqItemId{i}"] = "0"
            out[f"ReqItemCount{i}"] = "0"

        # Fill objective text always by slot
        for i, r in enumerate(self.rows, start=1):
            out[f"ObjectiveText{i}"] = (r["text"].text() or "").strip()

        # Fill requirements
        item_slot = 1
        for slot, r in enumerate(self.rows, start=1):
            typ = r["type"].currentText()
            sid = (r["id"].text() or "").strip()
            cnt = int(r["count"].value())

            try:
                n = int(sid) if sid else 0
            except Exception:
                n = 0

            if typ == "Creature":
                out[f"ReqCreatureOrGOId{slot}"] = str(max(0, n))         # force positive
                out[f"ReqCreatureOrGOCount{slot}"] = str(max(0, cnt))
            elif typ == "GameObject":
                out[f"ReqCreatureOrGOId{slot}"] = str(-max(0, abs(n)))   # force negative
                out[f"ReqCreatureOrGOCount{slot}"] = str(max(0, cnt))

            elif typ == "Item":
                if item_slot <= 6:
                    out[f"ReqItemId{item_slot}"] = str(max(0, n))
                    out[f"ReqItemCount{item_slot}"] = str(max(0, cnt))
                    item_slot += 1
            elif typ == "SpellCast":
                out[f"ReqSpellCast{slot}"] = str(max(0, n))

        # Build the big Objectives text from ObjectiveText lines
        lines = []
        for i in range(1, 5):
            t = (out.get(f"ObjectiveText{i}") or "").strip()
            if t:
                lines.append(t)
        out["Objectives"] = "\n".join(lines)

        return out

class QuestPreviewDialog(QDialog):
    def __init__(self, data: dict, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Quest Preview")
        self.resize(640, 520)

        tabs = QtWidgets.QTabWidget()

        self.details = QTextBrowser()
        self.progress = QTextBrowser()
        self.complete = QTextBrowser()

        for w in (self.details, self.progress, self.complete):
            w.setOpenExternalLinks(False)
            w.setReadOnly(True)

        tabs.addTab(self.details, "Details")
        tabs.addTab(self.progress, "Progress")
        tabs.addTab(self.complete, "Completion")

        layout = QtWidgets.QVBoxLayout(self)
        layout.addWidget(tabs)

        self._render(data)

    def _render(self, d: dict):
        title = d.get("Title", "")
        level = d.get("QuestLevel", "")
        details = d.get("Details", "")
        objectives = d.get("Objectives", "")
        request = d.get("RequestItemsText", "")
        offer = d.get("OfferRewardText", "")
        end = d.get("EndText", "")
        completed = d.get("CompletedText", "")

        choice_lines, guaranteed_lines = _render_reward_lines(d)

        def ul(lines):
            if not lines:
                return "<i>None</i>"
            return "<ul>" + "".join(f"<li>{l}</li>" for l in lines) + "</ul>"

        rewards_html = f"""
        <hr>
        <p><b>Rewards</b></p>
        <p><b>Choose one of:</b></p>
        {ul(choice_lines)}
        <p><b>You will receive:</b></p>
        {ul(guaranteed_lines)}
        """

        # Accept
        self.details.setHtml(f"""
        <h2>{title}</h2>
        <p><b>Level {level}</b></p>
        <p>{details}</p>
        <hr>
        <p><b>Objectives</b></p>
        <p>{objectives}</p>
        {rewards_html}
        """)

        # Progress
        self.progress.setHtml(f"""
        <h2>{title}</h2>
        <p>{request or "<i>You have not completed this quest.</i>"}</p>
        """)

        # Completion
        self.complete.setHtml(f"""
        <h2>{title}</h2>
        <p>{offer}</p>
        {rewards_html}
        <hr>
        <p>{end or completed}</p>
        """)
