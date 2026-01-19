Jan-12-26
- Updated quest_editor.py indention error

Jan-15-26

### Core Architecture Changes
- **Unified loot editing system**
  - Replaced separate creature and object loot editors with a single `GenericLootEditor`.
  - Loot editors are now dynamically selected based on `SourceTypeOrReferenceId`.
  - Supports all standard `*_loot_template` tables through one shared implementation.

- **Quest Loot Editor redesign**
  - Conditions table and loot editors are fully synchronized.
  - Selecting a condition row automatically loads the correct loot editor and `(entry, item)` key.
  - Loot creation, editing, and saving now follow a consistent upsert model.

### Conditions System Improvements
- **Expanded ConditionType and SourceType support**
  - Full, non-deprecated `ConditionTypeOrReference` list implemented.
  - Full `SourceTypeOrReferenceId` list implemented with correct semantics.

- **Dynamic condition tooltips**
  - Context-aware tooltips added for:
    - `SourceTypeOrReferenceId`
    - `ConditionTypeOrReference`
    - `SourceGroup`, `SourceEntry`, `SourceId`
    - `ConditionValue1–3`
  - Tooltips update live when dropdown values change.
  - Tooltip data matches TrinityCore condition behavior.

- **Improved condition defaults**
  - Safer normalization of numeric fields before saving.
  - `SourceId` defaults to `0` (matches real-world DB usage).
  - Quest-anchored conditions auto-fill quest ID only when appropriate.

### Quest Deletion Enhancements
- **Delete preview added**
  - Deleting a quest now shows a detailed preview before confirmation:
    - Number of condition groups
    - Number of condition rows
    - Related loot rows per `*_loot_template`
  - Improves safety when removing quests with complex dependencies.

- **Expanded delete coverage**
  - Quest deletion now removes:
    - Quest template entry
    - Related condition rows
    - Related loot rows across all supported loot templates
    - Creature / GameObject starter and ender relations

### UI / UX Improvements
- **More usable layout**
  - SourceType and ConditionType columns widened for readability.
  - Center conditions grid given more visual priority.
  - Long field names no longer truncate important values.

- **Cleaner editor state handling**
  - Editor clears safely after quest deletion.
  - Loot editors reset correctly when no valid condition is selected.

### Cleanup & Maintenance
- Removed obsolete:
- `object_loot_editor.py`
- Reduced duplicated SQL and UI logic across editors.

Jan-19-26

# New features
- Conditions SourceEntry, SourceGroup, and ConditionValue1 can now be double clicked to bring up appropriate search **NOTE: not all *_loot_templates can be mapped back to quest_template. They are special case conditions**
- Most id fields have the appropriate search/pick button
