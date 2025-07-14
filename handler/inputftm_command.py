import os
import asyncio
import tempfile
import logging
import pandas as pd
from database.db import get_connection_database
from dotenv import load_dotenv
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import (
    CallbackContext,
    CommandHandler,
    ConversationHandler,
    MessageHandler,
    CallbackQueryHandler,
    filters,
)

# Load environment
load_dotenv()

# Logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# States
ASK_WITEL, ASK_STO, ASK_SUBSTO, ASK_FILE = range(4)

# WITEL and STO options
WITEL_OPTIONS = ["MLG", "MNZ", "KDR"]
STO_OPTIONS = {
    "MLG": ["BTU","KEP",  "MLG"],
    "MNZ": ["BJN", "MNZ", "NWI", "PON", "TNZ"],
    "KDR": ["BLR", "PAE", "KDI", "NJK", "TRE", "TUL"]
}

# Sub-STO options for specific STOs
SUBSTO_OPTIONS = {
    "BTU": ["BTU", "KPO", "NTG"],
    "KEP": ["GKW", "KEP", "PGK", "SBP", "DPT", "SBM", "TUR", "BNR", "GDI", "APG", "DNO"],
    "MLG": ["BLB", "GDG", "KLJ", "MLG", "PKS", "TMP", "BRG", "SWJ", "LWG", "SGS"],
    "BJN": ["BJN", "KDU", "PAD", "SMJ"],
    "MNZ": ["MNZ", "UTR", "MSP", "CRB"],
    "NWI": ["MGT", "NWI", "GGR", "SAR", "WKU", "JGO", "KRJ"],
    "PON": ["PON", "PNZ", "SMO", "PNG", "PLG", "SAT", "JEN", "SLH", "LOG"],
    "TNZ": ["BCR", "JTR", "KRK", "MRR", "RGL", "TNZ", "TAW"],
    "BLR": ["BLR", "SNT", "PAN", "BNU", "KBN", "LDY", "WGI"],
    "PAE": ["GUR", "WAT", "KAA", "PAE", "PPR"],
    "KDI": ["KDI", "MJT", "NDL", "SBI"],
    "NJK": ["GON", "NJK", "KTS", "PRB", "WRJ"],
    "TRE": ["DRN", "PRI", "TRE"],
    "TUL": ["CAT", "KWR", "NGU", "TUL"]
}

async def cancel_handler(update: Update, context: CallbackContext) -> int:
    await update.message.reply_text("❌ Operasi dibatalkan.")
    return ConversationHandler.END

async def start_inputftm(update: Update, context: CallbackContext) -> int:
    keyboard = [[InlineKeyboardButton(opt, callback_data=f"select_witel|{opt}")] for opt in WITEL_OPTIONS]
    await update.message.reply_text(
        "📂 Silakan pilih WITEL untuk input data FTM:",
        reply_markup=InlineKeyboardMarkup(keyboard)
    )
    return ASK_WITEL

async def handle_witel_selection(update: Update, context: CallbackContext) -> int:
    query = update.callback_query
    await query.answer()
    _, witel = query.data.split("|", 1)
    context.user_data["witel"] = witel

    sto_list = STO_OPTIONS.get(witel.upper(), [])
    if sto_list:
        keyboard = [[InlineKeyboardButton(sto, callback_data=f"select_sto|{sto}")] for sto in sto_list]
        await query.edit_message_text(
            f"🏢 WITEL *{witel.upper()}* dipilih. Pilih STO:",
            reply_markup=InlineKeyboardMarkup(keyboard),
            parse_mode="Markdown"
        )
        return ASK_STO
    else:
        await query.edit_message_text(
            f"📥 *WITEL:* {witel}\nSilakan kirim file Excel (.xlsx/.xls):",
            parse_mode="Markdown"
        )
        return ASK_FILE

async def handle_sto_selection(update: Update, context: CallbackContext) -> int:
    query = update.callback_query
    await query.answer()
    _, sto = query.data.split("|", 1)
    context.user_data["sto"] = sto

    if sto in SUBSTO_OPTIONS:
        keyboard = [
            [InlineKeyboardButton(sub, callback_data=f"select_substo|{sub}")]
            for sub in SUBSTO_OPTIONS[sto]
        ]
        await query.edit_message_text(
            f"📍 Sub-STO untuk {sto}, silakan pilih:",
            reply_markup=InlineKeyboardMarkup(keyboard)
        )
        return ASK_SUBSTO

    await query.edit_message_text(
        f"📥 *STO:* {sto}\nSilakan kirim file Excel (.xlsx/.xls):",
        parse_mode="Markdown"
    )
    return ASK_FILE

async def handle_substo_selection(update: Update, context: CallbackContext) -> int:
    query = update.callback_query
    await query.answer()
    _, substo = query.data.split("|", 1)
    context.user_data["sto"] = substo

    await query.edit_message_text(
        f"📥 *Sub-STO:* {substo}\nSilakan kirim file Excel (.xlsx/.xls):",
        parse_mode="Markdown"
    )
    return ASK_FILE

async def handle_file_input_ftm(update: Update, context: CallbackContext) -> int:
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
        df = df.where(pd.notna(df), None)
        records = df.to_dict(orient="records")

        witel = context.user_data.get("witel")
        sto = context.user_data.get("sto")
        table_name = f"data_{sto.lower()}"

        total, success, failed = len(records), 0, []
        loop = asyncio.get_running_loop()

        for idx, row in enumerate(records, start=1):
            raw_sto = row.get("sto")
            sto_payload = raw_sto or sto
            if not sto_payload:
                failed.append(f"[Baris {idx}] STO kosong")
                continue

            payload = {
                "witel": witel,
                "sto": sto_payload,
                "nama_gpon": row.get("nama_gpon"),
                "ip": row.get("ip"),
                "card": row.get("card"),
                "port": row.get("port"),
                "category": witel,
                "nama_lemari_ftm_eakses": row.get("nama_lemari_ftm_eakses"),
                "no_panel_eakses": row.get("no_panel_eakses"),
                "no_port_panel": row.get("no_port_panel"),
                "nama_lemari_ftm_oakses": row.get("nama_lemari_ftm_oakses"),
                "no_panel_oakses": row.get("no_panel_oakses"),
                "no_port_panel_1": row.get("no_port_panel_1"),
                "no_core_feeder": row.get("no_core_feeder"),
                "nama_segmen_feeder_utama": row.get("nama_segmen_feeder_utama"),
                "status_feeder": row.get("status_feeder"),
                "kapasitas_kabel_feeder_utama": row.get("kapasitas_kabel_feeder_utama"),
                "nama_odc": row.get("nama_odc")
            }

            try:
                await loop.run_in_executor(None, upsert_data, table_name, payload)
                success += 1
            except Exception as e:
                logger.error("Baris %d gagal: %s | payload=%r", idx, e, payload)
                failed.append(f"{sto_payload}|{row.get('nama_gpon')}|{e}")

            if idx % 500 == 0 or idx == total:
                await update.message.reply_text(f"📦 Progress: {idx}/{total}")
                await asyncio.sleep(1)

        summary = (
            f"📊 *Ringkasan Input Data FTM:*\n"
            f"- Total Baris: {total}\n"
            f"- Berhasil: {success}\n"
            f"- Gagal: {len(failed)}"
        )
        await update.message.reply_text(summary, parse_mode="Markdown")

        if failed:
            content = "\n".join(failed)
            with tempfile.NamedTemporaryFile(suffix=".txt", delete=False) as tf:
                tf.write(content.encode('utf-8'))
                fail_path = tf.name
            with open(fail_path, 'rb') as fp:
                await update.message.reply_document(fp, filename="failed_ftm.txt")
            os.remove(fail_path)

    except Exception as e:
        logger.exception("Error proses file FTM: %s", e)
        await update.message.reply_text(f"❌ Gagal memproses file: `{e}`", parse_mode="Markdown")
    finally:
        os.remove(path)

    return ConversationHandler.END

# SQL templates
INSERT_SQL_TEMPLATE = """
INSERT INTO `{table}` (witel, sto, nama_gpon, ip, card, port, category, nama_lemari_ftm_eakses, no_panel_eakses, no_port_panel, nama_lemari_ftm_oakses, no_panel_oakses, no_port_panel_1, no_core_feeder, nama_segmen_feeder_utama, status_feeder, kapasitas_kabel_feeder_utama, nama_odc)
VALUES (%(witel)s, %(sto)s, %(nama_gpon)s, %(ip)s, %(card)s, %(port)s, %(category)s, %(nama_lemari_ftm_eakses)s, %(no_panel_eakses)s, %(no_port_panel)s, %(nama_lemari_ftm_oakses)s, %(no_panel_oakses)s, %(no_port_panel_1)s, %(no_core_feeder)s, %(nama_segmen_feeder_utama)s, %(status_feeder)s, %(kapasitas_kabel_feeder_utama)s, %(nama_odc)s)
"""

UPDATE_SQL_TEMPLATE = """
UPDATE `{table}` SET
    ip = %(ip)s,
    card = %(card)s,
    port = %(port)s,
    category = %(category)s,
    nama_lemari_ftm_eakses = %(nama_lemari_ftm_eakses)s,
    no_panel_eakses = %(no_panel_eakses)s,
    no_port_panel = %(no_port_panel)s,
    nama_lemari_ftm_oakses = %(nama_lemari_ftm_oakses)s,
    no_panel_oakses = %(no_panel_oakses)s,
    no_port_panel_1 = %(no_port_panel_1)s,
    no_core_feeder = %(no_core_feeder)s,
    nama_segmen_feeder_utama = %(nama_segmen_feeder_utama)s,
    status_feeder = %(status_feeder)s,
    kapasitas_kabel_feeder_utama = %(kapasitas_kabel_feeder_utama)s,
    nama_odc = %(nama_odc)s
WHERE sto = %(sto)s AND nama_gpon = %(nama_gpon)s
"""

def upsert_data(table_name: str, row: dict):
    try:
        conn = get_connection_database()
        insert_sql = INSERT_SQL_TEMPLATE.format(table=table_name)

        with conn:
            with conn.cursor() as cur:
                cur.execute(insert_sql, row)  # Hanya lakukan insert
            conn.commit()

    except Exception as e:
        raise Exception(f"[DB ERROR] {e}")


def register_handler(app) -> None:
    conv = ConversationHandler(
        entry_points=[CommandHandler("inputftm", start_inputftm)],
        states={
            ASK_WITEL: [CallbackQueryHandler(handle_witel_selection, pattern=r"^select_witel\|")],
            ASK_STO: [CallbackQueryHandler(handle_sto_selection, pattern=r"^select_sto\|")],
            ASK_SUBSTO: [CallbackQueryHandler(handle_substo_selection, pattern=r"^select_substo\|")],
            ASK_FILE: [MessageHandler(
                filters.Document.MimeType("application/vnd.openxmlformats-officedocument.spreadsheetml.sheet") |
                filters.Document.MimeType("application/vnd.ms-excel"),
                handle_file_input_ftm
            )],
        },
        fallbacks=[CommandHandler("cancel", cancel_handler)],
        allow_reentry=True,
    )
    app.add_handler(conv)
