import asyncio
import logging
from aiohttp import web

from config import SESSIONS_DIR
from database import init_db
from login_manager import LoginManager
from aiohttp_app import create_app
from aiogram_bot import run_bot


def setup_logging() -> None:
    logging.basicConfig(level=logging.DEBUG)
    logging.getLogger("aiosqlite").setLevel(logging.WARNING)
    logging.getLogger("aiogram").setLevel(logging.INFO)


async def main() -> None:
    setup_logging()

    await init_db()

    manager = LoginManager()
    app = create_app(manager)

    runner = web.AppRunner(app)
    await runner.setup()
    site = web.TCPSite(runner, "127.0.0.1", 8080)
    await site.start()
    print("Server started on http://127.0.0.1:8080")

    # Telegram-бот запускается параллельно; если токен не задан — просто не запустится
    bot_task = asyncio.create_task(run_bot())

    stop_event = asyncio.Event()

    try:
        await stop_event.wait()          # живём, пока не убьют Ctrl+C
    finally:
        bot_task.cancel()
        try:
            await bot_task
        except (asyncio.CancelledError, Exception):
            pass
        await runner.cleanup()
        print("Shutdown complete.")


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("\nServer stopped.")