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

# Logger
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

# State
ASK_WITEL, ASK_DATEL, ASK_HOSTNAME = range(3)

WITEL_OPTIONS = ["MLG", "MNZ", "KDI"]

def escape_md(text: str) -> str:
    escape_chars = r"\_*[]()~`>#+-=|{}.!<>"
    return ''.join(f'\\{c}' if c in escape_chars else c for c in text)

# Start cek metro
async def start_cekmetro(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    user_id = update.effective_user.id
    message = update.effective_message

    logger.info(f"[STATE] start_cekmetro oleh user {user_id}")

    keyboard = [[InlineKeyboardButton(witel, callback_data=f"select_witel|{witel}")] for witel in WITEL_OPTIONS]
    await message.reply_text(
        "🚇 Silakan pilih *WITEL* untuk cek Metro:",
        reply_markup=InlineKeyboardMarkup(keyboard),
        parse_mode=ParseMode.MARKDOWN
    )
    return ASK_WITEL

# Pilih WITEL
async def handle_witel(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    query = update.callback_query
    await query.answer()
    _, witel = query.data.split("|", 1)
    context.user_data["witel"] = witel

    logger.info(f"[STATE] handle_witel: {witel}")

    try:
        conn = pymysql.connect(**DB_CONFIG)
        with conn.cursor() as cur:
            table_name = f"data_uplink_{witel.lower()}"
            cur.execute("SHOW TABLES")
            all_tables = [list(row.values())[0] for row in cur.fetchall()]
            if table_name not in all_tables:
                await query.edit_message_text("⚠️ Tabel data untuk WITEL ini belum tersedia di database.")
                return ConversationHandler.END

            cur.execute(f"SELECT DISTINCT sto FROM `{table_name}`")
            sto_rows = cur.fetchall()
            sto_list = sorted({row["sto"].upper() for row in sto_rows if row["sto"]})
        conn.close()
    except Exception as e:
        logger.exception("DB Error saat ambil STO")
        await query.edit_message_text(f"❌ Gagal mengambil daftar STO: {e}")
        return ConversationHandler.END

    if not sto_list:
        await query.edit_message_text("⚠️ Tidak ada data STO ditemukan di database.")
        return ConversationHandler.END

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

# Pilih DATEL
async def handle_datel(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    query = update.callback_query
    await query.answer()
    _, sto = query.data.split("|", 1)
    context.user_data["datel"] = sto

    witel = context.user_data.get("witel", "-")

    logger.info(f"[STATE] handle_datel: {sto}")

    message = (
        f"📌 WITEL: *{escape_md(witel)}*\n"
        f"🏢 STO: *{escape_md(sto)}*\n"
        "Silakan masukkan *gpon hostname* yang ingin dicari:"
    )

    await query.edit_message_text(
        message,
        parse_mode=ParseMode.MARKDOWN_V2
    )
    return ASK_HOSTNAME

# Masukkan GPON Hostname (pencarian berdasarkan gpon_hostname)
async def handle_hostname(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    logger.info(f"[STATE] handle_hostname oleh user {update.effective_user.id}")

    hostname_input = update.message.text.strip().lower()
    witel = context.user_data.get("witel", "").lower()
    sto = context.user_data.get("datel", "").lower()

    table_name = f"data_uplink_{witel}"

    try:
        conn = pymysql.connect(**DB_CONFIG)
        with conn.cursor() as cur:
            cur.execute("SHOW TABLES")
            all_tables = [list(row.values())[0] for row in cur.fetchall()]
            if table_name not in all_tables:
                await update.message.reply_text("⚠️ Tabel tidak ditemukan untuk WITEL tersebut.")
                return ConversationHandler.END

            cur.execute(f"""
                SELECT * FROM `{table_name}`
                WHERE LOWER(TRIM(sto)) = %s
                AND LOWER(TRIM(gpon_hostname)) LIKE %s
            """, (sto, f"%{hostname_input}%"))
            results = cur.fetchall()
        conn.close()
    except Exception as e:
        logger.exception("DB Error")
        await update.message.reply_text(f"❌ Terjadi kesalahan saat query DB: {e}")
        return ConversationHandler.END

    if not results:
        await update.message.reply_text("⚠️ Data tidak ditemukan.")
        return ConversationHandler.END

    context.user_data["last_results"] = results

    await update.message.reply_text(
        f"✅ Ditemukan *{len(results)}* data hasil pencarian.",
        parse_mode="Markdown"
    )

    for i, row in enumerate(results, 1):
        msg = (
            f"📡 *Data Metro #{i}*\n"
            f"📶 *Bandwidth:* {row.get('bw', '-')}\n"
            f"💻 *GPON Hostname:* `{row.get('gpon_hostname', '-')}`\n"
            f"🌐 *GPON IP:* `{row.get('gpon_ip', '-')}`\n"
            f"🧩 *Merk + Tipe:* {row.get('gpon_merk_tipe', '-')}\n"
            f"🔌 *GPON Interface:* `{row.get('gpon_intf', '-')}`\n"
            f"🧬 *GPON LACP:* `{row.get('gpon_lacp', '-')}`\n"
            f"🖧 *Neighbor Hostname:* `{row.get('neighbor_hostname', '-')}`\n"
            f"📍 *Neighbor Interface:* `{row.get('neighbor_intf', '-')}`\n"
            f"🧵 *Neighbor LACP:* `{row.get('neighbor_lacp', '-')}`\n"
            f"💡 *SFP:* {row.get('sfp', '-')}\n"
            f"📝 *Keterangan:* {row.get('Keterangan', '-')}\n"
            f"🔁 *OTN-CROSS METRO:* {row.get('OTN-CROSS METRO', '-')}"
        )
        await update.message.reply_text(msg, parse_mode="Markdown")

    keyboard = [
        [InlineKeyboardButton("🔢 Hitung Total Bandwidth", callback_data="hitung_bandwidth")],
    ]
    await update.message.reply_text(
        "Pilih opsi selanjutnya:",
        reply_markup=InlineKeyboardMarkup(keyboard)
    )
    return ConversationHandler.END

# Hitung Bandwidth
def parse_bw(bw: str) -> float:
    if not bw:
        return 0
    bw = bw.strip().upper().replace(" ", "")
    try:
        if "G" in bw:
            return float(bw.replace("G", "")) * 1000
        elif "M" in bw:
            return float(bw.replace("M", ""))
        else:
            return float(bw)
    except:
        return 0

async def hitung_total_bandwidth(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    query = update.callback_query
    await query.answer()

    results = context.user_data.get("last_results", [])
    if not results:
        await query.edit_message_text("⚠️ Tidak ada data untuk dihitung.")
        return

    total_mbps = sum(parse_bw(row.get("bw", "")) for row in results)
    total = f"{total_mbps:.2f} Mbps" if total_mbps < 1000 else f"{total_mbps / 1000:.2f} Gbps"

    await query.edit_message_text(
        f"📊 Total Bandwidth: *{total}*",
        parse_mode="Markdown"
    )

# Fallback jika input tidak dikenali
async def unknown_input(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    await update.message.reply_text("⚠️ Input tidak dikenali. Silakan ulangi /cekmetro.")
    return ConversationHandler.END

# Registrasi ke aplikasi bot
def register_handler(app) -> None:
    conv = ConversationHandler(
        entry_points=[CommandHandler("cekmetro", start_cekmetro)],
        states={
            ASK_WITEL: [CallbackQueryHandler(handle_witel, pattern=r"^select_witel\|")],
            ASK_DATEL: [CallbackQueryHandler(handle_datel, pattern=r"^select_datel\|")],
            ASK_HOSTNAME: [MessageHandler(filters.TEXT & ~filters.COMMAND, handle_hostname)],
        },
        fallbacks=[MessageHandler(filters.ALL, unknown_input)],
        allow_reentry=True,
    )

    app.add_handler(conv)
    app.add_handler(CallbackQueryHandler(hitung_total_bandwidth, pattern="^hitung_bandwidth$"))
