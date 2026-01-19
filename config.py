from pathlib import Path

# Change this 
DBC_DIR = Path(r"C:\Path_To_Your\dbc")

# Optional: per-file overrides
SKILLLINE_DBC = DBC_DIR / "SkillLine.dbc"
SPELL_DBC     = DBC_DIR / "Spell.dbc"
AREATABLE_DBC = DBC_DIR / "AreaTable.dbc"

QUESTSORT_DBC = DBC_DIR / "QuestSort.dbc"

# Extra DBCs used by pickers
FACTION_DBC       = DBC_DIR / "Faction.dbc"
CURRENCYTYPES_DBC = DBC_DIR / "CurrencyTypes.dbc"
