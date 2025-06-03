import asyncio

from loguru import logger

from tl_client import use_telethon, get_tl_bot
from database import prepare_db
from aiogram_client import aiogram_bot, aiogram_dp



async def main():
    await prepare_db()

    if use_telethon:
        tl_bot = await get_tl_bot()
        from tl_handlers import (
            tl_start_handler,
            tl_chosen_inline_result_handler,
            tl_inline_query_handler,
            tl_stats_handler,
            tl_mail_handler,
        )  # noqa: F401
        await tl_bot.run_until_disconnected()
    else:
        await aiogram_dp.start_polling(aiogram_bot)

if __name__ == "__main__":
    asyncio.run(main())