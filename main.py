import asyncio
import logging
import signal
import time

from config import load_config
from src.bot import CommandBot
from src.client import PromoListener
from src.commands import CommandHandler
from src.filter_engine import FilterEngine
from src.notifier import Notifier
from src.processor import MessageProcessor
from src.repository import KeywordRepository

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s — %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
logger = logging.getLogger("main")


async def main() -> None:
    config = load_config()

    repo = KeywordRepository(config.database_path)
    await repo.initialize()

    processor = MessageProcessor()
    filter_engine = FilterEngine(repo, config.default_max_price)
    notifier = Notifier(config.bot_token, config.owner_chat_id)
    command_handler = CommandHandler(
        config=config,
        repository=repo,
        notifier=notifier,
        started_at=time.time(),
    )
    listener = PromoListener(config, filter_engine, processor, notifier, repo)
    command_bot = CommandBot(config.bot_token, command_handler)

    stop_event = asyncio.Event()

    def _handle_signal() -> None:
        logger.info("Sinal de parada recebido. Encerrando...")
        stop_event.set()

    loop = asyncio.get_running_loop()
    for sig in (signal.SIGINT, signal.SIGTERM):
        try:
            loop.add_signal_handler(sig, _handle_signal)
        except NotImplementedError:
            pass

    logger.info("Bot iniciado. Aguardando promoções...")

    listener_task = asyncio.create_task(listener.start(), name="listener")
    bot_task = asyncio.create_task(command_bot.start_polling(), name="bot")
    stop_task = asyncio.create_task(stop_event.wait(), name="stop")

    done, _pending = await asyncio.wait(
        {listener_task, bot_task, stop_task},
        return_when=asyncio.FIRST_COMPLETED,
    )

    if stop_task in done:
        logger.info("Encerrando componentes...")

    await listener.stop()
    await command_bot.stop()
    await notifier.close()

    for task in (listener_task, bot_task):
        if not task.done():
            task.cancel()
            try:
                await task
            except (asyncio.CancelledError, Exception):
                pass

    logger.info("Encerrado.")


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        pass
