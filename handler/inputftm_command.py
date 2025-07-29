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

# Kolom target sesuai tabel SQL
COLUMNS = [
    "witel", "sto", "nama_gpon", "ip", "card", "port",
    "nama_lemari_ftm_eakses", "no_panel_eakses", "no_port_panel",
    "nama_lemari_ftm_oakses", "no_panel_oakses", 
    "no_core_feeder", "nama_segmen_feeder_utama", "status_feeder",
    "kapasitas_kabel_feeder_utama", "nama_odc"
]

# DB config
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
    sql = f"INSERT INTO `{table}` ({cols}) VALUES ({placeholders})"
    values = tuple(data.get(col, None) for col in COLUMNS)
    with get_connection() as conn:
        with conn.cursor() as cur:
            cur.execute(sql, values)
        conn.commit()

def clean(val):
    return None if pd.isna(val) else str(val).strip()

# Command /inputftm
async def start_inputftm(update: Update, context: CallbackContext) -> int:
    keyboard = [[InlineKeyboardButton(w, callback_data=f"witel|{w}")] for w in WITEL_OPTIONS]
    await update.message.reply_text(
        "📡 Silakan pilih *WITEL* untuk input data FTM:",
        reply_markup=InlineKeyboardMarkup(keyboard),
        parse_mode="Markdown"
    )
    return ASK_WITEL

async def handle_witel(update: Update, context: CallbackContext) -> int:
    query = update.callback_query
    await query.answer()
    witel = query.data.split("|")[1]
    context.user_data["witel"] = witel.lower()

    await query.edit_message_text(
        f"📁 WITEL *{witel}* dipilih.\n\nSilakan upload file Excel (.xlsx) sesuai format berikut.",
        parse_mode="Markdown"
    )

    contoh_path = "E:/Telkom/Telkom_Activity.bot/Input FTM.xlsx"
    if os.path.exists(contoh_path):
        with open(contoh_path, "rb") as f:
            await context.bot.send_document(chat_id=query.message.chat_id, document=InputFile(f), filename=os.path.basename(contoh_path))
    else:
        await context.bot.send_message(chat_id=query.message.chat_id, text="⚠️ Contoh file tidak ditemukan di server.")

    return ASK_FILE

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
        df_raw = pd.read_excel(path, header=0)
        df_raw.columns = [col.strip().lower().replace(" ", "_").replace("-", "_") for col in df_raw.columns]

        # Atasi duplikat kolom no_port_panel
        if df_raw.columns.tolist().count("no_port_panel") == 2:
            cols = []
            counter = 0
            for col in df_raw.columns:
                if col == "no_port_panel":
                    if counter == 0:
                        cols.append("no_port_panel_eakses")
                    else:
                        cols.append("no_port_panel_oakses")
                    counter += 1
                else:
                    cols.append(col)
            df_raw.columns = cols

        df = df_raw.copy()

        witel = context.user_data.get("witel", "").strip().lower()
        df["witel"] = witel
        table = f"data_ftm_{witel}"

        # Validasi kolom
        missing = [col for col in COLUMNS if col not in df.columns]
        if missing:
            await update.message.reply_text(f"❌ Kolom berikut tidak ditemukan di file:\n{', '.join(missing)}")
            return ConversationHandler.END

        clear_table(table)

        count, failed = 0, 0
        for i, row in df.iterrows():
            data = {col: clean(row.get(col)) for col in COLUMNS}
            try:
                insert_mysql(table, data)
                count += 1
            except Exception as e:
                failed += 1
                failed_rows.append(f"Baris {i+2}: {e}")
                logger.warning(f"Gagal insert baris {i+2}: {e}")

        await update.message.reply_text(
            f"📊 Ringkasan Input Data FTM:\n- Total Baris: {len(df)}\n- Berhasil: {count}\n- Gagal: {failed}",
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

def register_handler(application: Application):
    conv_handler = ConversationHandler(
        entry_points=[CommandHandler("inputftm", start_inputftm)],
        states={
            ASK_WITEL: [CallbackQueryHandler(handle_witel, pattern="^witel\\|")],
            ASK_FILE: [MessageHandler(filters.Document.ALL, handle_file)],
        },
        fallbacks=[],
    )
    application.add_handler(conv_handler)
