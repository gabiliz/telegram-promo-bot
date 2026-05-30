import logging
from datetime import datetime, time
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

CREATE TABLE IF NOT EXISTS monitored_groups (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    identifier  TEXT NOT NULL UNIQUE,
    label       TEXT,
    added_at    TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS quiet_hours (
    id          INTEGER PRIMARY KEY,
    start_hour  INTEGER NOT NULL,
    start_min   INTEGER NOT NULL,
    end_hour    INTEGER NOT NULL,
    end_min     INTEGER NOT NULL,
    enabled     INTEGER NOT NULL DEFAULT 1,
    timezone    TEXT NOT NULL DEFAULT 'America/Sao_Paulo'
);
"""

# Colunas adicionadas a sent_notifications após a criação original.
# Aplicadas via ALTER TABLE condicional (PRAGMA table_info) por serem idempotentes.
_SENT_NOTIFICATIONS_EXTRA_COLUMNS = {
    "group_name": "TEXT",
    "price": "REAL",
    "coupon": "TEXT",
    "message_link": "TEXT",
}

_QUIET_HOURS_ID = 1


class KeywordRepository:
    def __init__(self, database_path: str) -> None:
        self._path = database_path
        self._logger = logging.getLogger(__name__)

    async def initialize(self) -> None:
        async with aiosqlite.connect(self._path) as db:
            await db.executescript(_SCHEMA)
            await self._migrate_sent_notifications(db)
            await db.commit()
        self._logger.info("Banco de dados inicializado em %s", self._path)

    async def _migrate_sent_notifications(self, db: aiosqlite.Connection) -> None:
        async with db.execute("PRAGMA table_info(sent_notifications)") as cursor:
            rows = await cursor.fetchall()
        existing = {row[1] for row in rows}
        for column, col_type in _SENT_NOTIFICATIONS_EXTRA_COLUMNS.items():
            if column not in existing:
                await db.execute(
                    f"ALTER TABLE sent_notifications ADD COLUMN {column} {col_type}"
                )
                self._logger.info(
                    "Migração: coluna %s adicionada a sent_notifications", column
                )

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
                "(message_id, group_id, matched_terms, sent_at, "
                "group_name, price, coupon, message_link) "
                "VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
                (
                    promotion.message_id,
                    promotion.group_id,
                    ",".join(promotion.matched_keywords),
                    datetime.utcnow().isoformat(),
                    promotion.group_name,
                    promotion.extracted_price,
                    promotion.coupon,
                    promotion.message_link,
                ),
            )
            await db.commit()

    # ------------------------------------------------------------------ #
    # Grupos monitorados dinamicamente
    # ------------------------------------------------------------------ #

    async def add_monitored_group(
        self, identifier: str, label: Optional[str] = None
    ) -> bool:
        identifier = identifier.strip()
        async with aiosqlite.connect(self._path) as db:
            cursor = await db.execute(
                "INSERT OR IGNORE INTO monitored_groups "
                "(identifier, label, added_at) VALUES (?, ?, ?)",
                (identifier, label, datetime.utcnow().isoformat()),
            )
            await db.commit()
            return cursor.rowcount > 0

    async def remove_monitored_group(self, identifier: str) -> bool:
        identifier = identifier.strip()
        async with aiosqlite.connect(self._path) as db:
            cursor = await db.execute(
                "DELETE FROM monitored_groups WHERE identifier = ?", (identifier,)
            )
            await db.commit()
            return cursor.rowcount > 0

    async def get_monitored_groups(self) -> list[dict]:
        async with aiosqlite.connect(self._path) as db:
            db.row_factory = aiosqlite.Row
            async with db.execute(
                "SELECT identifier, label FROM monitored_groups ORDER BY added_at"
            ) as cursor:
                rows = await cursor.fetchall()
        return [
            {"identifier": row["identifier"], "label": row["label"]} for row in rows
        ]

    # ------------------------------------------------------------------ #
    # Horário silencioso
    # ------------------------------------------------------------------ #

    async def set_quiet_hours(self, start: time, end: time) -> None:
        async with aiosqlite.connect(self._path) as db:
            await db.execute(
                "INSERT INTO quiet_hours "
                "(id, start_hour, start_min, end_hour, end_min, enabled) "
                "VALUES (?, ?, ?, ?, ?, 1) "
                "ON CONFLICT(id) DO UPDATE SET "
                "start_hour = excluded.start_hour, start_min = excluded.start_min, "
                "end_hour = excluded.end_hour, end_min = excluded.end_min, "
                "enabled = 1",
                (_QUIET_HOURS_ID, start.hour, start.minute, end.hour, end.minute),
            )
            await db.commit()

    async def get_quiet_hours(self) -> Optional[tuple[time, time]]:
        async with aiosqlite.connect(self._path) as db:
            db.row_factory = aiosqlite.Row
            async with db.execute(
                "SELECT start_hour, start_min, end_hour, end_min, enabled "
                "FROM quiet_hours WHERE id = ?",
                (_QUIET_HOURS_ID,),
            ) as cursor:
                row = await cursor.fetchone()
        if row is None or not row["enabled"]:
            return None
        start = time(hour=row["start_hour"], minute=row["start_min"])
        end = time(hour=row["end_hour"], minute=row["end_min"])
        return start, end

    async def disable_quiet_hours(self) -> None:
        async with aiosqlite.connect(self._path) as db:
            await db.execute(
                "UPDATE quiet_hours SET enabled = 0 WHERE id = ?", (_QUIET_HOURS_ID,)
            )
            await db.commit()

    # ------------------------------------------------------------------ #
    # Histórico e estatísticas
    # ------------------------------------------------------------------ #

    async def get_recent_notifications(self, limit: int = 10) -> list[dict]:
        async with aiosqlite.connect(self._path) as db:
            db.row_factory = aiosqlite.Row
            async with db.execute(
                "SELECT matched_terms, sent_at, group_name, price, coupon, "
                "message_link FROM sent_notifications ORDER BY sent_at DESC LIMIT ?",
                (limit,),
            ) as cursor:
                rows = await cursor.fetchall()
        return [
            {
                "matched_terms": row["matched_terms"],
                "sent_at": row["sent_at"],
                "group_name": row["group_name"],
                "price": row["price"],
                "coupon": row["coupon"],
                "message_link": row["message_link"],
            }
            for row in rows
        ]

    async def get_stats(self) -> dict:
        today_prefix = datetime.utcnow().date().isoformat()
        async with aiosqlite.connect(self._path) as db:
            db.row_factory = aiosqlite.Row

            async with db.execute(
                "SELECT COUNT(*) AS c FROM seen_promotions"
            ) as cursor:
                total_processed = (await cursor.fetchone())["c"]

            async with db.execute(
                "SELECT COUNT(*) AS c FROM sent_notifications"
            ) as cursor:
                total_notified = (await cursor.fetchone())["c"]

            async with db.execute(
                "SELECT COUNT(*) AS c FROM sent_notifications WHERE sent_at LIKE ?",
                (f"{today_prefix}%",),
            ) as cursor:
                notified_today = (await cursor.fetchone())["c"]

            async with db.execute(
                "SELECT matched_terms, COUNT(*) AS cnt FROM sent_notifications "
                "GROUP BY matched_terms ORDER BY cnt DESC LIMIT 5"
            ) as cursor:
                top_keywords = [
                    (row["matched_terms"], row["cnt"]) for row in await cursor.fetchall()
                ]

            async with db.execute(
                "SELECT group_name, COUNT(*) AS cnt FROM sent_notifications "
                "WHERE group_name IS NOT NULL "
                "GROUP BY group_name ORDER BY cnt DESC LIMIT 3"
            ) as cursor:
                top_groups = [
                    (row["group_name"], row["cnt"]) for row in await cursor.fetchall()
                ]

        return {
            "total_processed": total_processed,
            "total_notified": total_notified,
            "notified_today": notified_today,
            "top_keywords": top_keywords,
            "top_groups": top_groups,
        }
