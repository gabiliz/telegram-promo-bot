import logging
import time
from typing import Optional

from src.models import AppConfig
from src.notifier import Notifier, _format_price_brl
from src.repository import KeywordRepository


class CommandHandler:
    def __init__(
        self,
        config: AppConfig,
        repository: KeywordRepository,
        notifier: Notifier,
        started_at: Optional[float] = None,
    ) -> None:
        self._config = config
        self._repo = repository
        self._notifier = notifier
        self._started_at = started_at if started_at is not None else time.time()
        self._logger = logging.getLogger(__name__)

    async def handle(self, sender_id: int, text: str) -> None:
        if sender_id != self._config.owner_chat_id:
            return
        if not text or not text.startswith("/"):
            return

        parts = text.strip().split()
        command = parts[0].split("@", 1)[0].lower()
        args = parts[1:]

        try:
            if command == "/add":
                await self._cmd_add(args)
            elif command == "/remove":
                await self._cmd_remove(args)
            elif command == "/list":
                await self._cmd_list()
            elif command == "/price":
                await self._cmd_price(args)
            elif command == "/status":
                await self._cmd_status()
            elif command in ("/start", "/help"):
                await self._cmd_help()
            else:
                await self._notifier.send_text(
                    "⚠️ Comando desconhecido. Use /help para ver os comandos."
                )
        except Exception:
            self._logger.exception("Erro ao processar comando %s", command)
            await self._notifier.send_text("❌ Erro ao processar comando.")

    @staticmethod
    def _parse_term_and_price(
        args: list[str],
    ) -> tuple[str, Optional[float]]:
        if not args:
            return "", None
        try:
            price = float(args[-1].replace(",", "."))
            term = " ".join(args[:-1]).strip()
            if not term:
                return " ".join(args).strip(), None
            return term, price
        except ValueError:
            return " ".join(args).strip(), None

    async def _cmd_add(self, args: list[str]) -> None:
        if not args:
            await self._notifier.send_text(
                "Uso: `/add <keyword> [preço_máximo]`"
            )
            return
        term, price = self._parse_term_and_price(args)
        if not term:
            await self._notifier.send_text("⚠️ Informe uma keyword válida.")
            return
        keyword = await self._repo.add_keyword(term, price)
        if price is not None and keyword.max_price != price:
            await self._repo.update_keyword_price(term, price)
            keyword.max_price = price
        price_line = (
            f"💰 Preço máximo: {_format_price_brl(keyword.max_price)}"
            if keyword.max_price is not None
            else "💰 Preço máximo: sem filtro"
        )
        await self._notifier.send_text(
            "✅ Keyword adicionada!\n"
            f"🏷️ Term: {keyword.term}\n"
            f"{price_line}"
        )

    async def _cmd_remove(self, args: list[str]) -> None:
        if not args:
            await self._notifier.send_text("Uso: `/remove <keyword>`")
            return
        term = " ".join(args).strip()
        removed = await self._repo.remove_keyword(term)
        if removed:
            await self._notifier.send_text(f'✅ Keyword "{term}" removida.')
        else:
            await self._notifier.send_text("⚠️ Keyword não encontrada.")

    async def _cmd_list(self) -> None:
        keywords = await self._repo.get_all_keywords()
        if not keywords:
            await self._notifier.send_text(
                "📋 Nenhuma keyword cadastrada. Use /add para adicionar."
            )
            return
        lines = ["📋 *Keywords monitoradas:*", ""]
        for idx, kw in enumerate(keywords, start=1):
            if kw.max_price is None:
                lines.append(f"{idx}. {kw.term} — sem filtro de preço")
            else:
                lines.append(
                    f"{idx}. {kw.term} — até {_format_price_brl(kw.max_price)}"
                )
        await self._notifier.send_text("\n".join(lines))

    async def _cmd_price(self, args: list[str]) -> None:
        if len(args) < 2:
            await self._notifier.send_text("Uso: `/price <keyword> <novo_valor>`")
            return
        term, price = self._parse_term_and_price(args)
        if price is None or not term:
            await self._notifier.send_text(
                "⚠️ Forneça keyword e valor numérico. Use 0 para remover o filtro."
            )
            return
        new_price: Optional[float] = None if price == 0 else price
        updated = await self._repo.update_keyword_price(term, new_price)
        if not updated:
            await self._notifier.send_text(
                f'⚠️ Keyword "{term}" não encontrada.'
            )
            return
        if new_price is None:
            await self._notifier.send_text(
                f'✅ Filtro de preço removido para "{term}".'
            )
        else:
            await self._notifier.send_text(
                f'✅ Preço máximo de "{term}" atualizado para '
                f"{_format_price_brl(new_price)}."
            )

    async def _cmd_status(self) -> None:
        keywords = await self._repo.get_all_keywords()
        uptime_seconds = int(time.time() - self._started_at)
        hours, remainder = divmod(uptime_seconds, 3600)
        minutes = remainder // 60
        if self._config.default_max_price > 0:
            default_price = _format_price_brl(self._config.default_max_price)
        else:
            default_price = "sem limite"
        await self._notifier.send_text(
            "🤖 *Status do Bot*\n\n"
            f"📡 Grupos monitorados: {len(self._config.monitored_groups)}\n"
            f"🏷️ Keywords ativas: {len(keywords)}\n"
            f"💰 Preço máximo padrão: {default_price}\n"
            f"⏱️ Online há: {hours}h {minutes}min"
        )

    async def _cmd_help(self) -> None:
        await self._notifier.send_text(
            "🤖 *Telegram Promo Bot*\n\n"
            "/add <keyword> [preço] — adiciona keyword\n"
            "/remove <keyword> — remove keyword\n"
            "/list — lista keywords\n"
            "/price <keyword> <valor> — atualiza preço (0 = remover filtro)\n"
            "/status — exibe status do bot"
        )
