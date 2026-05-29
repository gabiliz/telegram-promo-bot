import asyncio
import logging
from typing import Optional

import httpx

from src.commands import CommandHandler

_TELEGRAM_API_BASE = "https://api.telegram.org/bot{token}/{method}"
_LONG_POLL_TIMEOUT = 30


class CommandBot:
    def __init__(
        self,
        bot_token: str,
        command_handler: CommandHandler,
        http_client: Optional[httpx.AsyncClient] = None,
    ) -> None:
        self._token = bot_token
        self._handler = command_handler
        self._owns_client = http_client is None
        self._client = http_client or httpx.AsyncClient(
            timeout=httpx.Timeout(
                connect=10.0,
                read=float(_LONG_POLL_TIMEOUT + 10),
                write=10.0,
                pool=10.0,
            )
        )
        self._offset: int = 0
        self._running = False
        self._logger = logging.getLogger(__name__)

    async def start_polling(self) -> None:
        self._running = True
        self._logger.info("Bot de comandos iniciado (long polling).")
        while self._running:
            try:
                await self._poll_once()
            except asyncio.CancelledError:
                break
            except Exception:
                self._logger.exception("Erro no loop de polling. Aguardando 5s.")
                await asyncio.sleep(5)

    async def stop(self) -> None:
        self._running = False
        if self._owns_client:
            await self._client.aclose()

    async def _poll_once(self) -> None:
        url = _TELEGRAM_API_BASE.format(token=self._token, method="getUpdates")
        params = {
            "timeout": _LONG_POLL_TIMEOUT,
            "offset": self._offset,
            "allowed_updates": ["message"],
        }
        try:
            response = await self._client.get(url, params=params)
        except httpx.HTTPError as exc:
            self._logger.warning("Falha em getUpdates: %r", exc)
            await asyncio.sleep(2)
            return

        if response.status_code != 200:
            self._logger.warning(
                "getUpdates retornou status %s: %s",
                response.status_code,
                response.text[:200],
            )
            await asyncio.sleep(2)
            return

        data = response.json()
        if not data.get("ok"):
            self._logger.warning("Resposta inesperada: %s", data)
            return

        for update in data.get("result", []):
            self._offset = update["update_id"] + 1
            await self._dispatch(update)

    async def _dispatch(self, update: dict) -> None:
        message = update.get("message")
        if not message:
            return
        text = message.get("text")
        if not text or not text.startswith("/"):
            return
        sender = message.get("from") or {}
        sender_id = sender.get("id")
        if sender_id is None:
            return
        try:
            await self._handler.handle(sender_id, text)
        except Exception:
            self._logger.exception("Erro tratando comando.")
