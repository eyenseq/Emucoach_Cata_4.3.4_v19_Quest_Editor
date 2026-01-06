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


class Database:
    def __init__(self, cfg: DBConfig):
        self.cfg = cfg
        self._conn: Optional[pymysql.connections.Connection] = None

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

    def delete_quest(self, entry: int) -> None:
        # Order matters due to foreign references
        self.execute("DELETE FROM creature_quest_starter WHERE quest = %s", (entry,))
        self.execute("DELETE FROM creature_quest_ender WHERE quest = %s", (entry,))
        self.execute("DELETE FROM gameobject_questrelation WHERE quest = %s", (entry,))
        self.execute("DELETE FROM gameobject_involvedrelation WHERE quest = %s", (entry,))

        # Remove quest-related loot conditions
        # SourceType 19 = Quest
        self.execute(
            "DELETE FROM conditions WHERE SourceTypeOrReferenceId = 19 AND SourceEntry = %s",
            (entry,),
        )

        # Finally delete the quest itself
        self.execute("DELETE FROM quest_template WHERE entry = %s", (entry,))

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
