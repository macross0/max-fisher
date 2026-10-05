import os

DB_FILE = "fish.db"
SESSIONS_DIR = "sessions"

# Telegram
TELEGRAM_BOT_TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN", "")
TELEGRAM_ADMIN_IDS = [
    int(x) for x in os.environ.get("TELEGRAM_ADMIN_IDS", "").split(",") if x.strip()
]