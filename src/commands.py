import logging
import time
from datetime import datetime
from datetime import time as dtime
from typing import TYPE_CHECKING, Optional

from telethon import TelegramClient

from src.models import AppConfig
from src.notifier import Notifier, _format_price_brl
from src.repository import KeywordRepository

if TYPE_CHECKING:
    from src.client import PromoListener

_MAX_HISTORY = 20
_DEFAULT_HISTORY = 5


class CommandHandler:
    def __init__(
        self,
        config: AppConfig,
        repository: KeywordRepository,
        notifier: Notifier,
        telethon_client: Optional[TelegramClient] = None,
        listener: Optional["PromoListener"] = None,
        started_at: Optional[float] = None,
    ) -> None:
        self._config = config
        self._repo = repository
        self._notifier = notifier
        self._telethon = telethon_client
        self._listener = listener
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
            elif command == "/addgroup":
                await self._cmd_addgroup(args)
            elif command == "/removegroup":
                await self._cmd_removegroup(args)
            elif command == "/listgroups":
                await self._cmd_listgroups()
            elif command == "/quiet":
                await self._cmd_quiet(args)
            elif command == "/history":
                await self._cmd_history(args)
            elif command == "/stats":
                await self._cmd_stats()
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

    # ------------------------------------------------------------------ #
    # Grupos monitorados dinamicamente
    # ------------------------------------------------------------------ #

    async def _cmd_addgroup(self, args: list[str]) -> None:
        if not args:
            await self._notifier.send_text("Uso: `/addgroup <username_ou_id>`")
            return
        identifier = args[0].strip()
        label: Optional[str] = None
        if self._telethon is not None:
            try:
                entity = await self._resolve_entity(identifier)
                label = getattr(entity, "title", None) or getattr(
                    entity, "username", None
                )
            except Exception:
                self._logger.warning("Falha ao resolver grupo %s", identifier)
                await self._notifier.send_text(
                    "⚠️ Não foi possível adicionar o grupo.\n"
                    "Verifique se o username está correto e se sua conta "
                    "é membro do grupo."
                )
                return

        added = await self._repo.add_monitored_group(identifier, label)
        if not added:
            await self._notifier.send_text(
                f'⚠️ O grupo "{identifier}" já estava na lista.'
            )
            return

        if self._listener is not None:
            await self._listener.add_group(identifier)

        resolved_line = f"\n🏷️ Nome resolvido: {label}" if label else ""
        await self._notifier.send_text(
            "✅ Grupo adicionado!\n"
            f"📡 Identifier: {identifier}"
            f"{resolved_line}\n"
            "🔄 Monitoramento ativo imediatamente."
        )

    async def _cmd_removegroup(self, args: list[str]) -> None:
        if not args:
            await self._notifier.send_text("Uso: `/removegroup <username_ou_id>`")
            return
        identifier = args[0].strip()
        removed = await self._repo.remove_monitored_group(identifier)
        if not removed:
            await self._notifier.send_text(
                f'⚠️ Grupo "{identifier}" não encontrado na lista do bot.'
            )
            return
        if self._listener is not None:
            await self._listener.remove_group(identifier)
        await self._notifier.send_text(
            f'✅ Grupo "{identifier}" removido. Monitoramento interrompido.'
        )

    async def _cmd_listgroups(self) -> None:
        env_groups = list(self._config.monitored_groups)
        db_groups = [g["identifier"] for g in await self._repo.get_monitored_groups()]
        if not env_groups and not db_groups:
            await self._notifier.send_text("📡 Nenhum grupo monitorado.")
            return
        lines = ["📡 *Grupos monitorados:*", ""]
        idx = 1
        if env_groups:
            lines.append("Do .env:")
            for g in env_groups:
                lines.append(f"{idx}. {g}")
                idx += 1
        if db_groups:
            if env_groups:
                lines.append("")
            lines.append("Adicionados via bot:")
            for g in db_groups:
                lines.append(f"{idx}. {g}")
                idx += 1
        await self._notifier.send_text("\n".join(lines))

    async def _resolve_entity(self, raw: str):
        assert self._telethon is not None
        try:
            return await self._telethon.get_entity(int(raw))
        except ValueError:
            return await self._telethon.get_entity(raw)

    # ------------------------------------------------------------------ #
    # Horário silencioso
    # ------------------------------------------------------------------ #

    async def _cmd_quiet(self, args: list[str]) -> None:
        if not args:
            quiet = await self._repo.get_quiet_hours()
            if quiet is None:
                await self._notifier.send_text(
                    "🔔 Horário silencioso desativado.\n"
                    "Use `/quiet 23:00 07:00` para ativar."
                )
            else:
                start, end = quiet
                await self._notifier.send_text(
                    "🔕 Horário silencioso ativo:\n"
                    f"Das {start.strftime('%H:%M')} às {end.strftime('%H:%M')} "
                    "(horário de Brasília)"
                )
            return

        if args[0].lower() == "off":
            await self._repo.disable_quiet_hours()
            await self._notifier.send_text(
                "🔔 Horário silencioso desativado. Você voltará a receber notificações."
            )
            return

        if len(args) < 2:
            await self._notifier.send_text(
                "Uso: `/quiet 23:00 07:00` ou `/quiet off`"
            )
            return

        start = self._parse_time(args[0])
        end = self._parse_time(args[1])
        if start is None or end is None:
            await self._notifier.send_text(
                "⚠️ Formato inválido. Use HH:MM, ex.: `/quiet 23:00 07:00`."
            )
            return

        await self._repo.set_quiet_hours(start, end)
        await self._notifier.send_text(
            "🔕 Horário silencioso ativado!\n"
            f"Das {start.strftime('%H:%M')} às {end.strftime('%H:%M')} "
            "(horário de Brasília)\n"
            "Você não receberá notificações nesse período."
        )

    @staticmethod
    def _parse_time(raw: str) -> Optional[dtime]:
        parts = raw.split(":")
        if len(parts) != 2:
            return None
        try:
            hour = int(parts[0])
            minute = int(parts[1])
        except ValueError:
            return None
        if not (0 <= hour <= 23 and 0 <= minute <= 59):
            return None
        return dtime(hour=hour, minute=minute)

    # ------------------------------------------------------------------ #
    # Histórico e estatísticas
    # ------------------------------------------------------------------ #

    async def _cmd_history(self, args: list[str]) -> None:
        limit = _DEFAULT_HISTORY
        if args:
            try:
                limit = max(1, min(_MAX_HISTORY, int(args[0])))
            except ValueError:
                pass
        rows = await self._repo.get_recent_notifications(limit)
        if not rows:
            await self._notifier.send_text("📋 Nenhuma promoção notificada ainda.")
            return
        lines = [f"📋 *Últimas {len(rows)} promoções notificadas:*", ""]
        for idx, row in enumerate(rows, start=1):
            when = self._format_history_date(row["sent_at"])
            group = row["group_name"] or "Grupo desconhecido"
            lines.append(f"{idx}. {when} — {group}")
            detail = [f"🏷️ {row['matched_terms']}"]
            if row["price"] is not None:
                detail.append(f"💰 {_format_price_brl(row['price'])}")
            if row["coupon"]:
                detail.append(f"🎟️ {row['coupon']}")
            lines.append("   " + " | ".join(detail))
            if row["message_link"]:
                lines.append(f"   🔗 [Ver promoção]({row['message_link']})")
        await self._notifier.send_text("\n".join(lines))

    @staticmethod
    def _format_history_date(sent_at: str) -> str:
        try:
            return datetime.fromisoformat(sent_at).strftime("%d/%m %H:%M")
        except ValueError:
            return sent_at

    async def _cmd_stats(self) -> None:
        stats = await self._repo.get_stats()
        lines = [
            "📊 *Estatísticas do Bot*",
            "",
            f"📨 Mensagens processadas: {stats['total_processed']}",
            f"✅ Promoções notificadas: {stats['total_notified']}",
            f"📅 Hoje: {stats['notified_today']} notificações",
        ]
        if stats["top_keywords"]:
            lines.append("")
            lines.append("🏷️ *Top Keywords:*")
            for idx, (term, cnt) in enumerate(stats["top_keywords"], start=1):
                lines.append(f"{idx}. {term} — {cnt} matches")
        if stats["top_groups"]:
            lines.append("")
            lines.append("📡 *Top Grupos:*")
            for idx, (group, cnt) in enumerate(stats["top_groups"], start=1):
                lines.append(f"{idx}. {group} — {cnt} notificações")
        await self._notifier.send_text("\n".join(lines))

    async def _cmd_status(self) -> None:
        keywords = await self._repo.get_all_keywords()
        uptime_seconds = int(time.time() - self._started_at)
        hours, remainder = divmod(uptime_seconds, 3600)
        minutes = remainder // 60
        if self._config.default_max_price > 0:
            default_price = _format_price_brl(self._config.default_max_price)
        else:
            default_price = "sem limite"
        env_count = len(self._config.monitored_groups)
        db_count = len(await self._repo.get_monitored_groups())
        total_groups = env_count + db_count
        await self._notifier.send_text(
            "🤖 *Status do Bot*\n\n"
            f"📡 Grupos monitorados: {total_groups} "
            f"({env_count} do .env + {db_count} via bot)\n"
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
            "/addgroup <username_ou_id> — monitora novo grupo\n"
            "/removegroup <username_ou_id> — para de monitorar grupo\n"
            "/listgroups — lista grupos monitorados\n"
            "/quiet <HH:MM HH:MM | off> — horário silencioso\n"
            "/history [n] — últimas promoções notificadas\n"
            "/stats — estatísticas do bot\n"
            "/status — exibe status do bot"
        )
