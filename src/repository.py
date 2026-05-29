import logging
from datetime import datetime
from typing import Optional

import aiosqlite

from src.models import Keyword, Promotion

_SCHEMA = """
CREATE TABLE IF NOT EXISTS keywords (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    term        TEXT NOT NULL UNIQUE,
    max_price   REAL,
    created_at  TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS seen_promotions (
    message_id  INTEGER NOT NULL,
    group_id    INTEGER NOT NULL,
    seen_at     TEXT NOT NULL,
    PRIMARY KEY (message_id, group_id)
);

CREATE TABLE IF NOT EXISTS sent_notifications (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    message_id      INTEGER NOT NULL,
    group_id        INTEGER NOT NULL,
    matched_terms   TEXT NOT NULL,
    sent_at         TEXT NOT NULL
);
"""


class KeywordRepository:
    def __init__(self, database_path: str) -> None:
        self._path = database_path
        self._logger = logging.getLogger(__name__)

    async def initialize(self) -> None:
        async with aiosqlite.connect(self._path) as db:
            await db.executescript(_SCHEMA)
            await db.commit()
        self._logger.info("Banco de dados inicializado em %s", self._path)

    async def get_all_keywords(self) -> list[Keyword]:
        async with aiosqlite.connect(self._path) as db:
            db.row_factory = aiosqlite.Row
            async with db.execute(
                "SELECT id, term, max_price, created_at FROM keywords ORDER BY term"
            ) as cursor:
                rows = await cursor.fetchall()
        return [
            Keyword(
                id=row["id"],
                term=row["term"],
                max_price=row["max_price"],
                created_at=datetime.fromisoformat(row["created_at"]),
            )
            for row in rows
        ]

    async def add_keyword(
        self, term: str, max_price: Optional[float] = None
    ) -> Keyword:
        normalized = term.strip().lower()
        now_iso = datetime.utcnow().isoformat()
        async with aiosqlite.connect(self._path) as db:
            await db.execute(
                "INSERT OR IGNORE INTO keywords (term, max_price, created_at) "
                "VALUES (?, ?, ?)",
                (normalized, max_price, now_iso),
            )
            await db.commit()
            db.row_factory = aiosqlite.Row
            async with db.execute(
                "SELECT id, term, max_price, created_at FROM keywords WHERE term = ?",
                (normalized,),
            ) as cursor:
                row = await cursor.fetchone()
        assert row is not None
        return Keyword(
            id=row["id"],
            term=row["term"],
            max_price=row["max_price"],
            created_at=datetime.fromisoformat(row["created_at"]),
        )

    async def remove_keyword(self, term: str) -> bool:
        normalized = term.strip().lower()
        async with aiosqlite.connect(self._path) as db:
            cursor = await db.execute(
                "DELETE FROM keywords WHERE term = ?", (normalized,)
            )
            await db.commit()
            return cursor.rowcount > 0

    async def update_keyword_price(
        self, term: str, max_price: Optional[float]
    ) -> bool:
        normalized = term.strip().lower()
        async with aiosqlite.connect(self._path) as db:
            cursor = await db.execute(
                "UPDATE keywords SET max_price = ? WHERE term = ?",
                (max_price, normalized),
            )
            await db.commit()
            return cursor.rowcount > 0

    async def is_already_seen(self, message_id: int, group_id: int) -> bool:
        async with aiosqlite.connect(self._path) as db:
            async with db.execute(
                "SELECT 1 FROM seen_promotions WHERE message_id = ? AND group_id = ?",
                (message_id, group_id),
            ) as cursor:
                row = await cursor.fetchone()
        return row is not None

    async def mark_as_seen(self, message_id: int, group_id: int) -> None:
        async with aiosqlite.connect(self._path) as db:
            await db.execute(
                "INSERT OR IGNORE INTO seen_promotions "
                "(message_id, group_id, seen_at) VALUES (?, ?, ?)",
                (message_id, group_id, datetime.utcnow().isoformat()),
            )
            await db.commit()

    async def log_sent_notification(self, promotion: Promotion) -> None:
        async with aiosqlite.connect(self._path) as db:
            await db.execute(
                "INSERT INTO sent_notifications "
                "(message_id, group_id, matched_terms, sent_at) VALUES (?, ?, ?, ?)",
                (
                    promotion.message_id,
                    promotion.group_id,
                    ",".join(promotion.matched_keywords),
                    datetime.utcnow().isoformat(),
                ),
            )
            await db.commit()
