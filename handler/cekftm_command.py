import os
import logging
import pymysql
from dotenv import load_dotenv
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.constants import ParseMode
from telegram.ext import (
    ContextTypes,
    CommandHandler,
    ConversationHandler,
    CallbackQueryHandler,
    MessageHandler,
    filters,
)

# Load .env
load_dotenv()

# Logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# DB Config
DB_CONFIG = {
    "host": os.getenv("DB_HOST", "localhost"),
    "user": os.getenv("DB_USER", "root"),
    "password": os.getenv("DB_PASS", ""),
    "db": os.getenv("DB_NAME", "tlkm"),
    "cursorclass": pymysql.cursors.DictCursor,
    "charset": "utf8mb4",
}

# Conversation States
ASK_WITEL, ASK_DATEL, ASK_HOSTNAME = range(3)

# MarkdownV2 escaper
def escape_md(text: str) -> str:
    escape_chars = r"\_*[]()~`>#+-=|{}.!<>"
    return ''.join(f'\\{c}' if c in escape_chars else c for c in text)

# STEP 1: Mulai command /cekftm
async def start_cekftm(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    try:
        conn = pymysql.connect(**DB_CONFIG)
        with conn.cursor() as cur:
            cur.execute("SHOW TABLES")
            tables = [list(row.values())[0] for row in cur.fetchall()]
            witel_list = [t.replace("data_ftm_", "").upper() for t in tables if t.startswith("data_ftm_")]
    except Exception as e:
        logger.exception("DB Error saat ambil WITEL")
        await update.message.reply_text(f"❌ Gagal mengambil daftar WITEL: {e}")
        return ConversationHandler.END
    finally:
        conn.close()

    keyboard = [[InlineKeyboardButton(witel, callback_data=f"select_witel|{witel}")] for witel in witel_list]

    await update.message.reply_text(
        "📡 Silakan pilih *WITEL* untuk cek FTM:",
        reply_markup=InlineKeyboardMarkup(keyboard),
        parse_mode=ParseMode.MARKDOWN
    )
    return ASK_WITEL

# STEP 2: Pilih WITEL → tampilkan STO
async def handle_witel(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    query = update.callback_query
    await query.answer()
    _, witel = query.data.split("|", 1)
    context.user_data["witel"] = witel

    try:
        conn = pymysql.connect(**DB_CONFIG)
        with conn.cursor() as cur:
            table_name = f"data_ftm_{witel.lower()}"
            cur.execute(f"SELECT DISTINCT sto FROM `{table_name}`")
            sto_rows = cur.fetchall()
            sto_list = sorted({row["sto"].upper() for row in sto_rows if row["sto"]})
    except Exception as e:
        logger.exception("DB Error saat ambil STO")
        await query.edit_message_text(f"❌ Gagal mengambil daftar STO: {e}")
        return ConversationHandler.END
    finally:
        conn.close()

    keyboard = []
    row = []
    for i, sto in enumerate(sto_list, 1):
        row.append(InlineKeyboardButton(sto, callback_data=f"select_datel|{sto}"))
        if i % 3 == 0:
            keyboard.append(row)
            row = []
    if row:
        keyboard.append(row)

    await query.edit_message_text(
        f"📌 WITEL: *{escape_md(witel)}*\n\nSilakan pilih *STO*: ",
        reply_markup=InlineKeyboardMarkup(keyboard),
        parse_mode=ParseMode.MARKDOWN_V2
    )
    return ASK_DATEL

# STEP 3: Pilih STO → input hostname
async def handle_datel(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    query = update.callback_query
    await query.answer()
    _, sto = query.data.split("|", 1)
    context.user_data["sto"] = sto

    witel = context.user_data.get("witel", "-")

    await query.edit_message_text(
        f"📌 WITEL: *{escape_md(witel)}*\n🏢 STO: *{escape_md(sto)}*\n\nSilakan masukkan *nama GPON* yang ingin dicari:",
        parse_mode=ParseMode.MARKDOWN_V2
    )
    return ASK_HOSTNAME

# STEP 4: Input nama GPON → tampilkan hasil
async def handle_hostname(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    hostname_input = update.message.text.strip().lower()
    witel = context.user_data.get("witel", "").lower()
    sto = context.user_data.get("sto", "").lower()
    table_name = f"data_ftm_{witel}"

    try:
        conn = pymysql.connect(**DB_CONFIG)
        with conn.cursor() as cur:
            cur.execute(f"""
                SELECT * FROM `{table_name}`
                WHERE LOWER(TRIM(sto)) = %s
                AND LOWER(TRIM(nama_gpon)) LIKE %s
            """, (sto, f"%{hostname_input}%"))
            results = cur.fetchall()
    except Exception as e:
        logger.exception("DB Error saat query GPON")
        await update.message.reply_text(f"❌ Terjadi kesalahan saat query DB: {e}")
        return ConversationHandler.END
    finally:
        conn.close()

    if not results:
        await update.message.reply_text("⚠️ Data tidak ditemukan.")
        return ConversationHandler.END

    for i, row in enumerate(results, 1):
        msg = (
            f"📡 *Data FTM #{i}*\n"
            f"💻 *Nama GPON:* {row.get('nama_gpon', '-')}\n"
            f"🌐 *IP:* {row.get('ip', '-')}\n"
            f"📦 *Card:* {row.get('card', '-')}\n"
            f"🔌 *Port:* {row.get('port', '-')}\n"
            f"📁 *Lemari Eakses:* {row.get('nama_lemari_ftm_eakses', '-')}\n"
            f"📂 *Panel Eakses:* {row.get('no_panel_eakses', '-')} | {row.get('no_port_panel_eakses', '-')}\n"
            f"📁 *Lemari Oakses:* {row.get('nama_lemari_ftm_oakses', '-')}\n"
            f"📂 *Panel Oakses:* {row.get('no_panel_oakses', '-')} | {row.get('no_port_panel_oakses', '-')}\n"
            f"🧵 *Core Feeder:* {row.get('no_core_feeder', '-')}\n"
            f"🔗 *Segmen Feeder:* {row.get('nama_segmen_feeder_utama', '-')}\n"
            f"🔋 *Status Feeder:* {row.get('status_feeder', '-')}\n"
            f"⚡ *Kapasitas Kabel:* {row.get('kapasitas_kabel_feeder_utama', '-')}\n"
            f"🏷️ *Nama ODC:* {row.get('nama_odc', '-')}"
        )
        await update.message.reply_text(msg, parse_mode=ParseMode.MARKDOWN)

    return ConversationHandler.END

# Daftarkan handler ke aplikasi utama
def register_handler(app) -> None:
    conv = ConversationHandler(
        entry_points=[CommandHandler("cekftm", start_cekftm)],
        states={
            ASK_WITEL: [CallbackQueryHandler(handle_witel, pattern=r"^select_witel\|")],
            ASK_DATEL: [CallbackQueryHandler(handle_datel, pattern=r"^select_datel\|")],
            ASK_HOSTNAME: [MessageHandler(filters.TEXT & ~filters.COMMAND, handle_hostname)],
        },
        fallbacks=[],
        allow_reentry=True,
    )
    app.add_handler(conv)
