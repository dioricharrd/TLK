import os  
import re
import asyncio
import tempfile
import logging
import pandas as pd
import pymysql
from dotenv import load_dotenv
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import (
    CallbackContext,
    Application,
    CommandHandler,
    ConversationHandler,
    MessageHandler,
    CallbackQueryHandler,
    filters,
)

# Load environment
load_dotenv()

# DB config
db_config = {
    "host": os.getenv("DB_HOST", "localhost"),
    "user": os.getenv("DB_USER", "root"),
    "password": os.getenv("DB_PASSWORD", ""),
    "db": os.getenv("DB_NAME", "tlkm"),
    "cursorclass": pymysql.cursors.DictCursor
}

# Logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# States
ASK_WITEL, ASK_STO, ASK_SUBSTO, ASK_FILE = range(4)

# Options
WITEL_OPTIONS = ["MLG", "MNZ", "KDR"]
STO_OPTIONS = {
    "MLG": ["BTU", "KEP", "MLG"],
    "MNZ": ["BJN", "MNZ", "NWI", "PON", "TNZ"],
    "KDR": ["BLR", "PAE", "KDI", "NJK", "TRE", "TUL"]
}
SUBSTO_OPTIONS = {
    # WITEL MLG
    "BTU": ["BTU", "KPO", "NTG"],
    "KEP": ["GKW", "KEP", "PGK", "SBP", "DPT", "SBM", "TUR", "BNR", "GDI", "APG", "DNO"],
    "MLG": ["BLB", "GDG", "KLJ", "MLG", "PKS", "TMP", "BRG", "SWJ", "LWG", "SGS"],

    # WITEL MNZ
    "BJN": ["BJN", "KDU", "PAD", "SMJ"],
    "MNZ": ["MNZ", "UTR", "MSP", "CRB"],
    "NWI": ["MGT", "NWI", "GGR", "SAR", "WKU", "JGO", "KRJ"],
    "PON": ["PON", "PNZ", "SMO", "PNG", "PLG", "SAT", "JEN", "SLH", "LOG"],
    "TNZ": ["BCR", "JTR", "KRK", "MRR", "RGL", "TNZ", "TAW"],

    # WITEL KDR
    "BLR": ["BLR", "SNT", "PAN", "BNU", "KBN", "LDY", "WGI"],
    "PAE": ["GUR", "WAT", "KAA", "PAE", "PPR"],
    "KDI": ["KDI", "MJT", "NDL", "SBI"],
    "NJK": ["GON", "NJK", "KTS", "PRB", "WRJ"],
    "TRE": ["DRN", "PRI", "TRE"],
    "TUL": ["CAT", "KWR", "NGU", "TUL"]
}

# SQL templates
INSERT_SQL = """
INSERT INTO `{table}` (
    witel, sto, gpon_hostname, gpon_ip, gpon_merk, gpon_tipe, gpon_merk_tipe,
    gpon_intf, gpon_lacp, neighbot_hostname, neighbor_intf, neighbor_lacp,
    bw, sfp, vlan_sip, vlan_internet, keterangan, otn_cross_metro
) VALUES (
    %(witel)s, %(sto)s, %(gpon_hostname)s, %(gpon_ip)s, %(gpon_merk)s,
    %(gpon_tipe)s, %(gpon_merk_tipe)s, %(gpon_intf)s, %(gpon_lacp)s,
    %(neighbot_hostname)s, %(neighbor_intf)s, %(neighbor_lacp)s,
    %(bw)s, %(sfp)s, %(vlan_sip)s, %(vlan_internet)s,
    %(keterangan)s, %(otn_cross_metro)s
)
"""

UPDATE_SQL = """
UPDATE `{table}` SET
    gpon_ip = %(gpon_ip)s,
    gpon_merk = %(gpon_merk)s,
    gpon_tipe = %(gpon_tipe)s,
    gpon_merk_tipe = %(gpon_merk_tipe)s,
    gpon_intf = %(gpon_intf)s,
    gpon_lacp = %(gpon_lacp)s,
    neighbot_hostname = %(neighbot_hostname)s,
    neighbor_intf = %(neighbor_intf)s,
    neighbor_lacp = %(neighbor_lacp)s,
    bw = %(bw)s,
    sfp = %(sfp)s,
    vlan_sip = %(vlan_sip)s,
    vlan_internet = %(vlan_internet)s,
    keterangan = %(keterangan)s,
    otn_cross_metro = %(otn_cross_metro)s
WHERE sto = %(sto)s AND gpon_hostname = %(gpon_hostname)s
"""

def upsert_data(table_name: str, row: dict):
    conn = pymysql.connect(**db_config)
    with conn:
        with conn.cursor() as cur:
            cur.execute(UPDATE_SQL.format(table=table_name), row)
            if cur.rowcount == 0:
                cur.execute(INSERT_SQL.format(table=table_name), row)
        conn.commit()

# Step 1
async def start_inputmetro(update: Update, context: CallbackContext) -> int:
    keyboard = [[InlineKeyboardButton(opt, callback_data=f"select_witel|{opt}")] for opt in WITEL_OPTIONS]
    await update.message.reply_text(
        "📂 Pilih WITEL untuk input data Metro:",
        reply_markup=InlineKeyboardMarkup(keyboard)
    )
    return ASK_WITEL

# Step 2
async def handle_witel_selection(update: Update, context: CallbackContext) -> int:
    query = update.callback_query
    await query.answer()
    _, witel = query.data.split("|", 1)
    context.user_data["witel"] = witel
    sto_list = STO_OPTIONS.get(witel.upper(), [])
    keyboard = [[InlineKeyboardButton(sto, callback_data=f"select_sto|{sto}")] for sto in sto_list]
    await query.edit_message_text(
        f"🏢 WITEL *{witel.upper()}* dipilih. Pilih STO:",
        reply_markup=InlineKeyboardMarkup(keyboard),
        parse_mode="Markdown"
    )
    return ASK_STO

# Step 3
async def handle_sto_selection(update: Update, context: CallbackContext) -> int:
    query = update.callback_query
    await query.answer()
    _, sto = query.data.split("|", 1)
    context.user_data["sto"] = sto
    substo_list = SUBSTO_OPTIONS.get(sto.upper())
    if substo_list:
        keyboard = [[InlineKeyboardButton(s, callback_data=f"select_substo|{s}")] for s in substo_list]
        await query.edit_message_text(
            f"🏢 STO *{sto.upper()}* dipilih.\nPilih Sub-STO:",
            reply_markup=InlineKeyboardMarkup(keyboard),
            parse_mode="Markdown"
        )
        return ASK_SUBSTO
    await query.edit_message_text(
        f"📥 *STO:* {sto}\nSilakan kirim file Excel (.xlsx/.xls):",
        parse_mode="Markdown"
    )
    return ASK_FILE

# Step 4
async def handle_substo_selection(update: Update, context: CallbackContext) -> int:
    query = update.callback_query
    await query.answer()
    _, substo = query.data.split("|", 1)
    context.user_data["substo"] = substo
    await query.edit_message_text(
        f"📥 *Sub-STO:* {substo}\nSilakan kirim file Excel (.xlsx/.xls):",
        parse_mode="Markdown"
    )
    return ASK_FILE

# String sanitizer
def clean_str(val, max_len):
    if val is None or pd.isna(val):
        return None
    s = str(val).strip()
    s = re.sub(r"[^\x20-\x7E]", "", s)
    return s[:max_len] or None

# Final Step
async def handle_file_input(update: Update, context: CallbackContext) -> int:
    doc = update.message.document
    if doc.mime_type not in (
        "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        "application/vnd.ms-excel"
    ):
        await update.message.reply_text("❌ Harap kirim file .xlsx/.xls.")
        return ConversationHandler.END

    with tempfile.NamedTemporaryFile(suffix=".xlsx", delete=False) as tmp:
        path = tmp.name
    file_obj = await doc.get_file()
    await file_obj.download_to_drive(path)
    await update.message.reply_text("📥 File diterima, memproses...")

    try:
        df = pd.read_excel(path)
        df.columns = df.columns.str.lower().str.strip().str.replace(" ", "_", regex=False)
        df = df.replace({pd.NA: None, "nan": None, "NaN": None, "": None})

        df["bw"] = df.get("bw").apply(lambda v: clean_str(v, 10))
        df["sfp"] = df.get("sfp").apply(lambda v: clean_str(v, 20))
        df["gpon_ip"] = df.get("gpon_ip").apply(lambda v: clean_str(v, 20))

        records = df.to_dict(orient="records")
        witel = context.user_data.get("witel")
        sto = context.user_data.get("substo") or context.user_data.get("sto")
        table_name = f"data_uplink_{sto.lower()}"

        total, success, failed = len(records), 0, []
        loop = asyncio.get_running_loop()

        for idx, row in enumerate(records, start=1):
            row["witel"] = witel
            row["sto"] = row.get("sto") or sto
            safe_row = {k: (str(v).strip() if v is not None else None) for k, v in row.items()}

            try:
                await loop.run_in_executor(None, upsert_data, table_name, safe_row)
                success += 1
            except Exception as e:
                logger.error("Baris %d gagal: %s | payload=%r", idx, e, safe_row)
                failed.append(f"[{idx}] {safe_row.get('gpon_hostname')} | {e}")

            if idx % 500 == 0 or idx == total:
                await update.message.reply_text(f"📦 Progress: {idx}/{total}")
                await asyncio.sleep(1)

        await update.message.reply_text(
            f"📊 *Ringkasan Input Data Metro:*\n- Total Baris: {total}\n- Berhasil: {success}\n- Gagal: {len(failed)}",
            parse_mode="Markdown"
        )

        if failed:
            content = "\n".join(failed)
            with tempfile.NamedTemporaryFile(suffix=".txt", delete=False) as tf:
                tf.write(content.encode("utf-8"))
                fail_path = tf.name
            with open(fail_path, "rb") as fp:
                await update.message.reply_document(fp, filename="failed_metro.txt")
            os.remove(fail_path)

    except Exception as e:
        logger.error("Error proses file metro: %s", e)
        await update.message.reply_text(f"❌ Gagal memproses file: `{e}`", parse_mode="Markdown")
    finally:
        os.remove(path)

    return ConversationHandler.END

# Register handler
def register_handler(app: Application) -> None:
    conv = ConversationHandler(
        entry_points=[CommandHandler(["inputmetro", "inputuplink"], start_inputmetro)],
        states={
            ASK_WITEL: [CallbackQueryHandler(handle_witel_selection, pattern=r"^select_witel\|")],
            ASK_STO: [CallbackQueryHandler(handle_sto_selection, pattern=r"^select_sto\|")],
            ASK_SUBSTO: [CallbackQueryHandler(handle_substo_selection, pattern=r"^select_substo\|")],
            ASK_FILE: [MessageHandler(filters.Document.ALL, handle_file_input)]
        },
        fallbacks=[],
        allow_reentry=True
    )
    app.add_handler(conv)
