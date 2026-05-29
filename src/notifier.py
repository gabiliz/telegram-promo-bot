import asyncio
import logging
from typing import Optional

import httpx

from src.models import Promotion

_TELEGRAM_API_BASE = "https://api.telegram.org/bot{token}/{method}"
_MAX_TEXT_PREVIEW = 400
_MAX_RETRIES = 3
_RETRY_BACKOFF_SECONDS = 2.0


def _format_price_brl(value: float) -> str:
    formatted = f"{value:,.2f}"
    return "R$ " + formatted.replace(",", "X").replace(".", ",").replace("X", ".")


def _truncate(text: str, limit: int = _MAX_TEXT_PREVIEW) -> str:
    text = text.strip()
    if len(text) <= limit:
        return text
    return text[: limit - 3].rstrip() + "..."


def _escape_markdown(text: str) -> str:
    for ch in ("_", "*", "`", "["):
        text = text.replace(ch, "\\" + ch)
    return text


class Notifier:
    def __init__(
        self,
        bot_token: str,
        owner_chat_id: int,
        http_client: Optional[httpx.AsyncClient] = None,
    ) -> None:
        self._token = bot_token
        self._owner_chat_id = owner_chat_id
        self._owns_client = http_client is None
        self._client = http_client or httpx.AsyncClient(
            timeout=httpx.Timeout(connect=10.0, read=30.0, write=10.0, pool=10.0)
        )
        self._logger = logging.getLogger(__name__)

    async def close(self) -> None:
        if self._owns_client:
            await self._client.aclose()

    def _build_message(self, promotion: Promotion) -> str:
        lines = ["🔥 *Promoção encontrada!*", ""]
        lines.append(f"📌 *Grupo:* {_escape_markdown(promotion.group_name)}")
        lines.append(
            "🏷️ *Keywords:* "
            + _escape_markdown(", ".join(promotion.matched_keywords))
        )
        if promotion.extracted_price is not None:
            lines.append(
                f"💰 *Preço detectado:* {_format_price_brl(promotion.extracted_price)}"
            )
        lines.append("")
        lines.append(_escape_markdown(_truncate(promotion.raw_text)))
        lines.append("")
        if promotion.message_link:
            lines.append(f"🔗 [Ver promoção completa]({promotion.message_link})")
        lines.append(
            "⏰ _" + promotion.detected_at.strftime("%d/%m/%Y %H:%M") + "_"
        )
        return "\n".join(lines)

    async def send_promotion(self, promotion: Promotion) -> bool:
        text = self._build_message(promotion)
        payload = {
            "chat_id": self._owner_chat_id,
            "text": text,
            "parse_mode": "Markdown",
            "disable_web_page_preview": False,
        }
        return await self._send_message(payload)

    async def send_text(self, text: str, parse_mode: Optional[str] = "Markdown") -> bool:
        payload: dict = {
            "chat_id": self._owner_chat_id,
            "text": text,
        }
        if parse_mode:
            payload["parse_mode"] = parse_mode
        return await self._send_message(payload)

    async def _send_message(self, payload: dict) -> bool:
        url = _TELEGRAM_API_BASE.format(token=self._token, method="sendMessage")
        last_error: Optional[str] = None
        for attempt in range(1, _MAX_RETRIES + 1):
            try:
                response = await self._client.post(url, json=payload)
                if response.status_code == 200:
                    return True
                last_error = (
                    f"status={response.status_code} body={response.text[:200]}"
                )
            except httpx.HTTPError as exc:
                last_error = repr(exc)
            self._logger.warning(
                "Falha enviando mensagem (tentativa %s/%s): %s",
                attempt,
                _MAX_RETRIES,
                last_error,
            )
            if attempt < _MAX_RETRIES:
                await asyncio.sleep(_RETRY_BACKOFF_SECONDS)
        self._logger.error("Mensagem não enviada após %s tentativas: %s", _MAX_RETRIES, last_error)
        return False
