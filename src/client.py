import asyncio
import logging
from typing import Any, Optional

from telethon import TelegramClient, events

from src.filter_engine import FilterEngine
from src.models import AppConfig, Promotion
from src.notifier import Notifier
from src.processor import MessageProcessor
from src.repository import KeywordRepository


class PromoListener:
    def __init__(
        self,
        config: AppConfig,
        filter_engine: FilterEngine,
        processor: MessageProcessor,
        notifier: Notifier,
        repository: KeywordRepository,
    ) -> None:
        self._config = config
        self._filter_engine = filter_engine
        self._processor = processor
        self._notifier = notifier
        self._repository = repository
        self._client = TelegramClient(
            config.session_name, config.api_id, config.api_hash
        )
        self._chat_entities: list[Any] = []
        self._stop_event = asyncio.Event()
        self._handler_registered = False
        self._logger = logging.getLogger(__name__)

    @property
    def client(self) -> TelegramClient:
        return self._client

    async def start(self) -> None:
        await self._client.start()  # type: ignore[func-returns-value]
        self._logger.info("Telethon conectado.")

        await self._seed_env_groups()
        await self.reload_groups()

        if not self._chat_entities:
            self._logger.error("Nenhum grupo válido para monitorar.")
        await self._stop_event.wait()

    async def stop(self) -> None:
        self._stop_event.set()
        if self._client.is_connected():
            await self._client.disconnect()  # type: ignore[func-returns-value]
        self._logger.info("Telethon desconectado.")

    async def _seed_env_groups(self) -> None:
        """Migra grupos definidos no .env para a lista gerenciada pelo bot.

        Idempotente: roda sempre na inicialização, mas só insere o que ainda
        não existir no banco. Depois disso o banco é a única fonte de verdade.
        """
        for raw in self._config.monitored_groups:
            if await self._repository.add_monitored_group(raw):
                self._logger.info("Grupo do .env migrado para o banco: %s", raw)

    async def _group_identifiers(self) -> list[str]:
        """Identificadores dos grupos monitorados (somente do banco)."""
        return [
            g["identifier"] for g in await self._repository.get_monitored_groups()
        ]

    async def reload_groups(self) -> None:
        """Re-resolve a lista de grupos e re-registra o handler com chats= atualizado."""
        identifiers = await self._group_identifiers()
        entities: list[Any] = []
        for raw in identifiers:
            try:
                entities.append(await self._resolve_entity(raw))
                self._logger.info("Monitorando grupo: %s", raw)
            except Exception:
                self._logger.exception("Falha ao resolver grupo %s", raw)

        self._chat_entities = entities

        if self._handler_registered:
            self._client.remove_event_handler(self._on_new_message)
            self._handler_registered = False

        if not entities:
            return

        self._client.add_event_handler(
            self._on_new_message,
            events.NewMessage(chats=entities),
        )
        self._handler_registered = True
        self._logger.info("Listener registrado para %d grupo(s).", len(entities))

    async def add_group(self, identifier: str) -> None:
        """Re-registra o handler para incluir o grupo recém-adicionado."""
        await self.reload_groups()

    async def remove_group(self, identifier: str) -> None:
        """Re-registra o handler sem o grupo removido."""
        await self.reload_groups()

    async def _resolve_entity(self, raw: str) -> Any:
        try:
            return await self._client.get_entity(int(raw))
        except ValueError:
            return await self._client.get_entity(raw)

    def _build_message_link(self, chat: Any, message_id: int) -> str:
        username = getattr(chat, "username", None)
        if username:
            return f"https://t.me/{username}/{message_id}"
        chat_id = getattr(chat, "id", None)
        if chat_id is not None:
            normalized_id = str(chat_id).removeprefix("-100")
            return f"https://t.me/c/{normalized_id}/{message_id}"
        return ""

    async def _on_new_message(self, event: events.NewMessage.Event) -> None:
        try:
            raw_text = event.message.text or ""
            if not raw_text.strip():
                return

            chat = await event.get_chat()
            normalized, price, coupon = self._processor.process_message(raw_text)

            should_notify, matched = await self._filter_engine.evaluate(
                normalized_text=normalized,
                extracted_price=price,
                message_id=event.message.id,
                group_id=event.chat_id,
            )

            if not should_notify:
                return

            link = self._build_message_link(chat, event.message.id)

            promotion = Promotion(
                message_id=event.message.id,
                group_id=event.chat_id,
                group_name=getattr(chat, "title", None) or "Desconhecido",
                group_username=getattr(chat, "username", None),
                raw_text=raw_text,
                normalized_text=normalized,
                extracted_price=price,
                coupon=coupon,
                matched_keywords=matched,
                message_link=link,
            )

            sent = await self._notifier.send_promotion(promotion)
            if sent:
                await self._repository.log_sent_notification(promotion)
        except Exception:
            msg_id: Optional[int] = getattr(getattr(event, "message", None), "id", None)
            self._logger.exception("Erro ao processar mensagem id=%s", msg_id)
