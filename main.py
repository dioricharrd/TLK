# bot.py

import os
from dotenv import load_dotenv
from telegram.ext import Application

# Hanya satu import: fungsi yang mendaftarkan semua handler
from handler.base_command import register_handler

def main():
    # Muat environment variables dari .env
    load_dotenv()
    token = os.getenv("BOT_TOKEN")
    if not token:
        raise RuntimeError("BOT_TOKEN environment variable is not set")

    # Bangun Telegram Application
    app = Application.builder().token(token).build()

    # Daftarkan seluruh command & conversation handler
    register_handler(app)

    print("Bot running…")
    app.run_polling()

if __name__ == "__main__":
    main()
