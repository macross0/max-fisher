import asyncio
import logging
from aiogram import Bot, Dispatcher, F
from aiogram.filters import Command
from aiogram.types import Message

from config import TELEGRAM_BOT_TOKEN, TELEGRAM_ADMIN_IDS

log = logging.getLogger(__name__)


def build_bot() -> tuple[Bot, Dispatcher] | tuple[None, None]:
    if not TELEGRAM_BOT_TOKEN:
        log.warning("TELEGRAM_BOT_TOKEN не задан — бот выключен.")
        return None, None

    bot = Bot(token=TELEGRAM_BOT_TOKEN)
    dp = Dispatcher()

    @dp.message(Command("start"))
    async def cmd_start(message: Message):
        await message.answer(
            "Привет! Я — панель управления fish.\n"
            "Доступные команды:\n"
            "/start — это сообщение\n"
            "/ping  — проверить, что бот жив"
        )

    @dp.message(Command("ping"))
    async def cmd_ping(message: Message):
        await message.answer("pong 🏓")

    @dp.message(F.text)
    async def echo(message: Message):
        if message.from_user and message.from_user.id in TELEGRAM_ADMIN_IDS:
            await message.answer(f"эхо: {message.text}")

    return bot, dp


async def run_bot() -> None:
    bot, dp = build_bot()
    if bot is None:
        return
    log.info("Telegram bot polling started.")
    try:
        await dp.start_polling(bot)
    finally:
        await bot.session.close()