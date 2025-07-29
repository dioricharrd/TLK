import os
import logging
import tempfile
import pandas as pd
import pymysql
from dotenv import load_dotenv
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup, InputFile
from telegram.ext import (
    Application, CommandHandler, CallbackContext, ConversationHandler,
    CallbackQueryHandler, MessageHandler, filters
)

# Load ENV dan logging
load_dotenv()
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# State mesin
ASK_WITEL, ASK_FILE = range(2)
WITEL_OPTIONS = ["MLG", "MNZ", "KDR"]

# Kolom tabel yang harus diisi
COLUMNS = [
    "witel", "sto", "gpon_hostname", "gpon_ip", "gpon_merk", "gpon_tipe", "gpon_merk_tipe",
    "gpon_intf", "gpon_lacp", "neighbor_hostname", "neighbor_intf", "neighbor_lacp",
    "bw", "sfp", "vlan_sip", "vlan_internet", "Keterangan", "OTN-CROSS METRO"
]

# Konfigurasi DB
DB_CONFIG = {
    "host": os.getenv("DB_HOST", "localhost"),
    "user": os.getenv("DB_USER", "root"),
    "password": os.getenv("DB_PASS", ""),
    "db": os.getenv("DB_NAME", "tlkm"),
    "cursorclass": pymysql.cursors.DictCursor,
    "charset": "utf8mb4"
}

def get_connection():
    return pymysql.connect(**DB_CONFIG)

def clear_table(table):
    with get_connection() as conn:
        with conn.cursor() as cur:
            cur.execute(f"DELETE FROM `{table}`")
        conn.commit()

def insert_mysql(table, data):
    cols = ", ".join([f"`{col}`" for col in COLUMNS])
    placeholders = ", ".join(["%s"] * len(COLUMNS))

    sql = f"""
        INSERT INTO `{table}` ({cols})
        VALUES ({placeholders})
    """
    values = tuple(data.get(col, None) for col in COLUMNS)

    with get_connection() as conn:
        with conn.cursor() as cur:
            cur.execute(sql, values)
        conn.commit()

# Start /inputmetro
async def start_inputmetro(update: Update, context: CallbackContext) -> int:
    keyboard = [[InlineKeyboardButton(w, callback_data=f"witel|{w}")] for w in WITEL_OPTIONS]
    await update.message.reply_text(
        "📡 Silakan pilih *WITEL* untuk input data Metro:",
        reply_markup=InlineKeyboardMarkup(keyboard),
        parse_mode="Markdown"
    )
    return ASK_WITEL

# Setelah pilih WITEL
async def handle_witel(update: Update, context: CallbackContext) -> int:
    query = update.callback_query
    await query.answer()
    witel = query.data.split("|")[1]
    context.user_data["witel"] = witel.upper()

    await query.edit_message_text(
        f"📁 WITEL *{witel}* dipilih.\n\nSilakan upload file Excel (.xlsx) sesuai format berikut.\n\n📎 File contoh akan dikirim sebentar lagi...",
        parse_mode="Markdown"
    )

    contoh_path = "E:/Telkom/Telkom_Activity.bot/Uplink GPON-Metro Malang (rev).xlsx"
    if os.path.exists(contoh_path):
        with open(contoh_path, "rb") as f:
            await context.bot.send_document(chat_id=query.message.chat_id, document=InputFile(f), filename=os.path.basename(contoh_path))
    else:
        await context.bot.send_message(chat_id=query.message.chat_id, text="⚠️ Contoh file tidak ditemukan di server.")

    return ASK_FILE

# Bersihkan sel
def clean(val):
    return None if pd.isna(val) else str(val).strip()

# Handle upload file
async def handle_file(update: Update, context: CallbackContext) -> int:
    doc = update.message.document
    if not doc.file_name.endswith(".xlsx"):
        await update.message.reply_text("❌ File harus berformat .xlsx")
        return ConversationHandler.END

    await update.message.reply_text("📤 File diterima. Sedang diproses...")

    file = await doc.get_file()
    with tempfile.NamedTemporaryFile(delete=False, suffix=".xlsx") as tmp:
        path = tmp.name
        await file.download_to_drive(path)

    failed_rows = []
    try:
        df = pd.read_excel(path)
        df.columns = [c.strip().lower().replace(" ", "_").replace("-", "_") for c in df.columns]
        df = df.rename(columns={"otn_cross_metro": "OTN-CROSS METRO", "keterangan": "Keterangan"})

        witel = context.user_data.get("witel", "").strip().lower()
        df["witel"] = witel
        table = f"data_uplink_{witel}"

        clear_table(table)

        count, failed = 0, 0
        for i, row in df.iterrows():
            data = {col: clean(row.get(col.replace(" ", "_").replace("-", "_").lower())) for col in COLUMNS}
            try:
                insert_mysql(table, data)
                count += 1
            except Exception as e:
                failed += 1
                failed_rows.append(f"Baris {i+2}: {e}")
                logger.warning(f"Gagal insert baris {i+2}: {e}")

        await update.message.reply_text(
            f"📊 Ringkasan Input Data Metro:\n- Total Baris: {len(df)}\n- Berhasil: {count}\n- Gagal: {failed}",
            parse_mode="Markdown"
        )

        if failed_rows:
            with tempfile.NamedTemporaryFile(delete=False, suffix=".txt", mode="w", encoding="utf-8") as f:
                for line in failed_rows:
                    f.write(line + "\n")
                failed_path = f.name

            await update.message.reply_document(
                document=open(failed_path, "rb"),
                filename="data_gagal_input.txt",
                caption="📎 Berikut ini daftar baris yang gagal diinput:"
            )
            os.remove(failed_path)

    except Exception as e:
        logger.exception("Gagal memproses file:")
        await update.message.reply_text(f"❌ Gagal memproses file:\n{e}")
    finally:
        os.remove(path)

    return ConversationHandler.END

# Registrasi handler
def register_handler(application: Application):
    conv_handler = ConversationHandler(
        entry_points=[CommandHandler("inputmetro", start_inputmetro)],
        states={
            ASK_WITEL: [CallbackQueryHandler(handle_witel, pattern="^witel\\|")],
            ASK_FILE: [MessageHandler(filters.Document.ALL, handle_file)],
        },
        fallbacks=[],
    )
    application.add_handler(conv_handler)
