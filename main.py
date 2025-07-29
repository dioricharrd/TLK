# bot.py

import os
import logging
from dotenv import load_dotenv
from telegram.ext import Application

# Import fungsi register handler dari base_command
from handler.base_command import register_handler

def main():
    # Load environment variables
    load_dotenv()
    token = os.getenv("BOT_TOKEN")
    
    if not token:
        raise RuntimeError("BOT_TOKEN environment variable is not set in .env")

    # Optional: Logging ke console
    logging.basicConfig(
        format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
        level=logging.INFO
    )

    # Bangun aplikasi bot Telegram
    app = Application.builder().token(token).build()

    # Daftarkan semua command dan conversation handler
    register_handler(app)

    print("🤖 Bot is running... Tekan Ctrl+C untuk berhenti.")
    app.run_polling()

if __name__ == "__main__":
    main()
