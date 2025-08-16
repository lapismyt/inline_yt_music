import os
from dotenv import load_dotenv


load_dotenv()

BOT_TOKEN = os.getenv("BOT_TOKEN")
SEARCH_LIMIT = int(os.getenv("SEARCH_LIMIT"))
LENGTH_LIMIT = int(os.getenv("LENGTH_LIMIT"))  # in minutes
CACHE_SIZE_LIMIT = int(os.getenv("CACHE_SIZE_LIMIT"))  # in seconds
ADMIN_ID = int(os.getenv("ADMIN_ID"))
# LOADING_GIF_URL = os.getenv('LOADING_GIF_URL')
CHAT_ID = int(os.getenv("CHAT_ID"))
API_ID = int(os.getenv("API_ID"))
API_HASH = os.getenv("API_HASH")
DATABASE_URL = os.getenv("DATABASE_URL")

queued = set()
