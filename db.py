from __future__ import annotations
from dataclasses import dataclass
from typing import Any, Dict, Iterable, List, Optional, Sequence, Tuple

import pymysql


@dataclass
class DBConfig:
    host: str
    port: int
    user: str
    password: str
    database: str
    charset: str = "utf8mb4"

_LOOT_TABLE_BY_SOURCE = {
    1:  "creature_loot_template",
    2:  "disenchant_loot_template",
    3:  "fishing_loot_template",
    4:  "gameobject_loot_template",
    5:  "item_loot_template",
    6:  "mail_loot_template",
    7:  "milling_loot_template",
    8:  "pickpocketing_loot_template",
    9:  "prospecting_loot_template",
    10: "reference_loot_template",
    11: "skinning_loot_template",
    12: "spell_loot_template",
}

class Database:
    def __init__(self, cfg: DBConfig):
        self.cfg = cfg
        self._conn: Optional[pymysql.connections.Connection] = None
        
        # expose module mapping as an instance attribute (used by preview/delete)
        self._LOOT_TABLE_BY_SOURCE = _LOOT_TABLE_BY_SOURCE

    def connect(self) -> None:
        if self._conn:
            return
        self._conn = pymysql.connect(
            host=self.cfg.host,
            port=self.cfg.port,
            user=self.cfg.user,
            password=self.cfg.password,
            database=self.cfg.database,
            charset=self.cfg.charset,
            autocommit=False,
            cursorclass=pymysql.cursors.DictCursor,
        )

    def close(self) -> None:
        if self._conn:
            try:
                self._conn.close()
            finally:
                self._conn = None

    @property
    def conn(self) -> pymysql.connections.Connection:
        if not self._conn:
            raise RuntimeError("Database not connected")
        return self._conn

    def fetch_all(self, sql: str, params: Sequence[Any] = ()) -> List[Dict[str, Any]]:
        with self.conn.cursor() as cur:
            cur.execute(sql, params)
            return list(cur.fetchall())

    def next_quest_id(self) -> int:
        row = self.fetch_one("SELECT COALESCE(MAX(entry), 0) AS m FROM quest_template")
        return int(row["m"]) + 1

    def create_quest(self, entry: int) -> None:
        # Minimal safe insert; everything else uses table defaults
        self.execute(
            """
            INSERT INTO quest_template
            (entry, Method, QuestLevel, MinLevel, MaxLevel)
            VALUES (%s, %s, %s, %s, %s)
            """,
            (entry, 2, 1, 1, 1),
        )

    def preview_delete_quest(self, quest_id: int) -> dict:
        quest_id = int(quest_id)

        # Quest-linked condition types where ConditionValue1 = quest_id
        # NOTE: Do NOT include "2" (ITEM) here. It's not a quest id link.
        quest_ctypes = (8, 9, 14, 28, 43)

        ph_ct = ",".join(["%s"] * len(quest_ctypes))

        keys = self.fetch_all(
            f"""
            SELECT DISTINCT SourceTypeOrReferenceId, SourceGroup, SourceEntry, SourceId
            FROM conditions
            WHERE ConditionTypeOrReference IN ({ph_ct})
              AND ConditionValue1 = %s
            """,
            tuple(quest_ctypes) + (quest_id,),
        )

        result = {
            "quest_id": quest_id,
            "anchor_groups": len(keys),
            "conditions_rows": 0,
            "loot_rows_by_table": {},
        }

        if not keys:
            return result

        placeholders = ",".join(["(%s,%s,%s,%s)"] * len(keys))
        params = []
        for k in keys:
            params.extend([
                int(k["SourceTypeOrReferenceId"]),
                int(k["SourceGroup"]),
                int(k["SourceEntry"]),
                int(k["SourceId"]),
            ])

        row = self.fetch_one(
            f"""
            SELECT COUNT(*) AS n
            FROM conditions
            WHERE (SourceTypeOrReferenceId, SourceGroup, SourceEntry, SourceId)
                  IN ({placeholders})
            """,
            tuple(params),
        )
        result["conditions_rows"] = int(row["n"])

        by_table = {}
        for k in keys:
            table = self._LOOT_TABLE_BY_SOURCE.get(int(k["SourceTypeOrReferenceId"]))
            if table and int(k["SourceGroup"]) > 0 and int(k["SourceEntry"]) > 0:
                by_table.setdefault(table, set()).add(
                    (int(k["SourceGroup"]), int(k["SourceEntry"]))
                )

        for table, pairs in by_table.items():
            ph = ",".join(["(%s,%s)"] * len(pairs))
            p = []
            for e, i in pairs:
                p.extend([e, i])

            r = self.fetch_one(
                f"SELECT COUNT(*) AS n FROM {table} WHERE (entry,item) IN ({ph})",
                tuple(p),
            )
            result["loot_rows_by_table"][table] = int(r["n"])

        return result


    def delete_quest(self, quest_id: int) -> None:
        quest_id = int(quest_id)

        # Quest-linked condition types where ConditionValue1 = quest_id
        quest_ctypes = (8, 9, 14, 28, 43, 47)
        ph_ct = ",".join(["%s"] * len(quest_ctypes))

        keys = self.fetch_all(
            f"""
            SELECT DISTINCT SourceTypeOrReferenceId, SourceGroup, SourceEntry, SourceId
            FROM conditions
            WHERE ConditionTypeOrReference IN ({ph_ct})
              AND ConditionValue1 = %s
            """,
            tuple(quest_ctypes) + (quest_id,),
        )

        if keys:
            placeholders = ",".join(["(%s,%s,%s,%s)"] * len(keys))
            params = []
            for k in keys:
                params.extend([
                    int(k["SourceTypeOrReferenceId"]),
                    int(k["SourceGroup"]),
                    int(k["SourceEntry"]),
                    int(k["SourceId"]),
                ])

            # Delete ALL conditions for those groups (not just the anchor row)
            self.execute(
                f"""
                DELETE FROM conditions
                WHERE (SourceTypeOrReferenceId, SourceGroup, SourceEntry, SourceId)
                      IN ({placeholders})
                """,
                tuple(params),
            )

            # Delete matching loot rows per SourceType
            by_table = {}
            for k in keys:
                table = self._LOOT_TABLE_BY_SOURCE.get(int(k["SourceTypeOrReferenceId"]))
                if table and int(k["SourceGroup"]) > 0 and int(k["SourceEntry"]) > 0:
                    by_table.setdefault(table, set()).add(
                        (int(k["SourceGroup"]), int(k["SourceEntry"]))
                    )

            for table, pairs in by_table.items():
                ph = ",".join(["(%s,%s)"] * len(pairs))
                p = []
                for e, i in pairs:
                    p.extend([e, i])

                self.execute(
                    f"DELETE FROM {table} WHERE (entry,item) IN ({ph})",
                    tuple(p),
                )

        # Quest relations
        self.execute("DELETE FROM creature_quest_starter WHERE quest=%s", (quest_id,))
        self.execute("DELETE FROM creature_quest_ender WHERE quest=%s", (quest_id,))
        self.execute("DELETE FROM gameobject_questrelation WHERE quest=%s", (quest_id,))
        self.execute("DELETE FROM gameobject_involvedrelation WHERE quest=%s", (quest_id,))

        # IMPORTANT: your schema uses quest_template.entry (not Id)
        self.execute("DELETE FROM quest_template WHERE entry=%s", (quest_id,))

    def fetch_one(self, sql: str, params: Sequence[Any] = ()) -> Optional[Dict[str, Any]]:
        rows = self.fetch_all(sql, params)
        return rows[0] if rows else None

    def execute(self, sql: str, params: Sequence[Any] = ()) -> int:
        with self.conn.cursor() as cur:
            cur.execute(sql, params)
            return cur.rowcount

    def executemany(self, sql: str, seq_params: Iterable[Sequence[Any]]) -> int:
        with self.conn.cursor() as cur:
            cur.executemany(sql, seq_params)
            return cur.rowcount

    def commit(self) -> None:
        self.conn.commit()

    def rollback(self) -> None:
        self.conn.rollback()
