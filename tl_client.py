from telethon import (
    TelegramClient,
    types as tl_types,
    functions as tl_functions,
    events as tl_events,
)
from dotenv import load_dotenv
import os


load_dotenv()

BOT_TOKEN = os.getenv("BOT_TOKEN")
API_ID = int(os.getenv("API_ID"))
API_HASH = os.getenv("API_HASH")

use_telethon = False
tl_bot = None
if API_ID != -1 and API_HASH != "":
    use_telethon = True

async def get_tl_bot():
    global tl_bot
    if tl_bot is None:
        tl_bot = await TelegramClient("bot", api_id=API_ID, api_hash=API_HASH).start(
            bot_token=BOT_TOKEN
        )
    return tl_bot
