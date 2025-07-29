# handler/base_command.py

from telegram import InlineKeyboardButton, InlineKeyboardMarkup, Update
from telegram.ext import CallbackContext, CommandHandler, CallbackQueryHandler

# Import register_handler dari tiap modul perintah
from handler.cekftm_command    import register_handler as register_cekgpon
from handler.cekmetro_command   import register_handler as register_cekmetro
from handler.inputftm_command   import register_handler as register_inputftm
from handler.inputmetro_command import register_handler as register_inputmetro

# /start
async def start(update: Update, context: CallbackContext) -> None:
    keyboard = [[InlineKeyboardButton("START", callback_data="help")]]
    reply_markup = InlineKeyboardMarkup(keyboard)
    await update.message.reply_text(
        "👋 Halo! Saya adalah bot untuk membantu Anda mengecek dan menginput data GPON dan Metro.\n\n"
        "Tekan tombol START untuk melihat perintah yang tersedia.",
        reply_markup=reply_markup
    )

# Callback untuk tombol START
async def help_callback(update: Update, context: CallbackContext) -> None:
    query = update.callback_query
    await query.answer()
    await query.edit_message_text(
        "📃 *Daftar Perintah yang Tersedia:*\n\n"
        "🔍 /cekgpon     - Cek data GPON\n"
        "🚇 /cekmetro    - Cek data Metro\n"
        "📥 /inputftm    - Input data FTM\n"
        "📥 /inputmetro  - Input data Metro\n"
        "❌ /end         - Mengakhiri sesi bot\n"
        "↩️ /kembali     - Kembali ke menu utama\n",
        parse_mode="Markdown"
    )

# Handler callback inline button
async def button_handler(update: Update, context: CallbackContext) -> None:
    query = update.callback_query
    await query.answer()
    if query.data == "help":
        await help_callback(update, context)

# /end
async def end(update: Update, context: CallbackContext) -> None:
    await update.message.reply_text("✅ Sesi bot telah diakhiri. Terima kasih!")

# /kembali
async def kembali(update: Update, context: CallbackContext) -> None:
    await start(update, context)

def register_handler(app) -> None:
    """Pasang semua handler: core commands + sub-module commands."""
    # Core commands
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("help", help_callback))

    # Sub-module commands
    register_cekgpon(app)
    register_cekmetro(app)
    register_inputftm(app)
    register_inputmetro(app)

    # Inline button callback & utility
    app.add_handler(CallbackQueryHandler(button_handler))
    app.add_handler(CommandHandler("end", end))
    app.add_handler(CommandHandler("kembali", kembali))
