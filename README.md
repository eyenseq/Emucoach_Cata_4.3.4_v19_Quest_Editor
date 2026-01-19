# WoW 4.3.4 Quest / Loot Editor Emucoach/TrinityCore (PyQt6)

This project is a desktop editor for a TrinityCore-style 4.3.4 (Cataclysm) database.  
It includes a quest editor and a **generic loot editor** that can edit multiple `*_loot_template` tables, plus quest-linked `conditions`.

## Notes for Testers
- This release focuses on **structural correctness and safety**, not polish.
- Conditions table is **MyISAM**: deletes are best-effort and not transactional.
- Please report:
  - Any missing loot deletions
  - Condition types that behave unexpectedly
  - UI layout issues at different resolutions
---

## What you need (first-time setup)

### 1) Install required software

**Windows 10/11**
1. **Python 3.11+** (3.11 or 3.12 recommended)  
   - During install, check **“Add Python to PATH”**
2. **Git** (optional, only if you want to clone instead of downloading zip)
3. **MariaDB or MySQL** (your TrinityCore/EmuCoach world database)

**Database requirement**
- A world database that contains at least:
  - `quest_template`
  - `conditions`
  - loot templates you intend to edit (ex: `creature_loot_template`, `gameobject_loot_template`, etc.)
  - lookup tables used for display names (ex: `item_template`, `creature_template`, `gameobject_template`)

---

## 2) Download / place the project

Put the project folder somewhere simple, for example:

- `C:\wow_tools\quest_editor\`

---

## 3) Open a command prompt

Open **Command Prompt** in the project folder and run:

Upgrade pip and install dependencies:

```bat
py -m pip install --upgrade pip
pip install -r requirements.txt
```

Your `requirements.txt` includes:
- PyQt6
- pymysql (DB connector)

```bat
pip install PyQt6 PyMySQL
```

---

## 4) Configure your DBC directory (required)

This project reads a few `.dbc` files for pickers/labels (ex: AreaTable, QuestSort, Spell, SkillLine).

Open:

- `config.py`

Edit **DBC_DIR** to your local folder that contains the DBC files.

In `config.py` (line numbers may vary slightly), you’ll see:

```py
DBC_DIR = Path(r"C:\path_to_your\dbc")

# Optional: per-file overrides
SKILLLINE_DBC = DBC_DIR / "SkillLine.dbc"
SPELL_DBC     = DBC_DIR / "Spell.dbc"
AREATABLE_DBC = DBC_DIR / "AreaTable.dbc"

QUESTSORT_DBC = DBC_DIR / "QuestSort.dbc"

# Extra DBCs used by pickers
FACTION_DBC       = DBC_DIR / "Faction.dbc"
CURRENCYTYPES_DBC = DBC_DIR / "CurrencyTypes.dbc"
```

### DBC files you must have in that folder
Make sure these files exist at the path you configured:

- `SkillLine.dbc`
- `Spell.dbc`
- `AreaTable.dbc`
- `QuestSort.dbc`
- `Faction.dbc`
- `CurrencyTypes.dbc`

If any are missing, the related picker/dropdown will show **“No rows loaded”** (or similar).

---

## 5) Configure database access

This app connects to your DB using **PyMySQL**.

Where to set DB host/user/password:
- In the UI (if your build prompts for connection details), **or**
- In your connection/config code (if you hardcoded defaults)

Typical values for a local TrinityCore/EmuCoach setup:
- host: `127.0.0.1`
- port: `3306`
- user: `root`
- password: `your_password`
- database: `world` (or whatever your world DB name is)

If you’re not sure where your build stores this, search the project for:
- `pymysql.connect(`
- `host=`
- `database=`
- `DbConfig`

---

## 6) Run the app

From the project folder (venv activated):

```bat
py app.py
```

If everything is configured correctly:
- The UI should load
- DBC pickers should populate (AreaTable / QuestSort / etc.)
- Database-backed views should work (quests, conditions, loot templates)

---

# Common configuration changes

## Change the default quest ID range

The quest list is typically limited to a range for performance and sanity.

Open:

- `widgets/quest_editor.py`

Find and change:

```py
QUEST_ID_MIN = ...
QUEST_ID_MAX = ...
```

Set them to whatever range you want your editor to show by default.

Example:
```py
QUEST_ID_MIN = 1
QUEST_ID_MAX = 500000
```

Tip: If your DB is huge, keep the range smaller to make the quest list faster.

---

## Change DBC directory later

Just edit `config.py` again:

```py
DBC_DIR = Path(r"D:\my_dbc_folder")
```

Restart the app.

---

# Troubleshooting

## “No rows loaded for Pick Sort (QuestSort)” / DBC pickers empty
- Confirm `DBC_DIR` points to the correct folder
- Confirm the required `.dbc` files exist (exact names)
- Confirm you restarted the app after changing `config.py`

## DB connection errors (Access denied, can’t connect)
- Verify user/pass/host/port/dbname
- Test logging in with a DB client first (HeidiSQL, MySQL Workbench)
- Make sure the DB server is running

## PyQt6 install issues
- Ensure you installed Python from python.org and checked **Add to PATH**
- Try:
  ```bat
  py -m pip install --upgrade pip
  pip install -r requirements.txt
  ```

---

# Notes

- `conditions` is often MyISAM in TrinityCore-style DBs, so it is not fully transactional.
- The project’s newer approach uses a **GenericLootEditor** so you can edit multiple loot tables through one consistent UI.

