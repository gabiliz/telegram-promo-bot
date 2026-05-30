import logging
from datetime import datetime
from typing import Optional
from zoneinfo import ZoneInfo

from src.repository import KeywordRepository

_QUIET_HOURS_TZ = ZoneInfo("America/Sao_Paulo")


class FilterEngine:
    def __init__(
        self,
        repository: KeywordRepository,
        default_max_price: float = 0.0,
    ) -> None:
        self._repo = repository
        self._default_max_price = default_max_price
        self._logger = logging.getLogger(__name__)

    async def evaluate(
        self,
        normalized_text: str,
        extracted_price: Optional[float],
        message_id: int,
        group_id: int,
    ) -> tuple[bool, list[str]]:
        if await self._is_quiet_time():
            return False, []

        if await self._repo.is_already_seen(message_id, group_id):
            return False, []

        keywords = await self._repo.get_all_keywords()
        matched = [kw for kw in keywords if kw.term in normalized_text]
        if not matched:
            return False, []

        passed: list[str] = []
        for kw in matched:
            effective_max = (
                kw.max_price
                if kw.max_price is not None
                else (self._default_max_price if self._default_max_price > 0 else None)
            )

            if effective_max is None:
                passed.append(kw.term)
                continue

            if extracted_price is None:
                continue
            if extracted_price <= effective_max:
                passed.append(kw.term)

        if not passed:
            return False, []

        await self._repo.mark_as_seen(message_id, group_id)
        return True, passed

    async def _is_quiet_time(self) -> bool:
        quiet = await self._repo.get_quiet_hours()
        if quiet is None:
            return False
        now = datetime.now(_QUIET_HOURS_TZ).time()
        start, end = quiet
        if start <= end:
            return start <= now <= end
        # Atravessa a meia-noite, ex.: 23:00 → 07:00
        return now >= start or now <= end
