import os
import logging
import pymysql
from dotenv import load_dotenv
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import (
    CallbackContext,
    CommandHandler,
    ConversationHandler,
    CallbackQueryHandler,
    MessageHandler,
    filters,
)


# Load environment variables
load_dotenv()

# Setup logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Database config
DB_CONFIG = {
    "host": os.getenv("DB_HOST", "localhost"),
    "user": os.getenv("DB_USER", "root"),
    "password": os.getenv("DB_PASS", ""),
    "db": os.getenv("DB_NAME", "tlkm"),
    "cursorclass": pymysql.cursors.DictCursor
}

# Conversation states
ASK_WITEL, ASK_STO, ASK_SUBSTO, ASK_HOSTNAME = range(4)

# Static WITEL → STO → SubSTO references
WITEL_OPTIONS = ["MLG", "MNZ", "KDR"]

STO_OPTIONS = {
    "MLG": ["BTU", "KEP", "MLG"],
    "MNZ": ["BJN", "MNZ", "NWI", "PON", "TNZ"],
    "KDR": ["BLR", "PAE", "KDI", "NJK", "TRE", "TUL"]
}

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


async def start_cekmetro(update: Update, context: CallbackContext) -> int:
    keyboard = [[InlineKeyboardButton(w, callback_data=f"select_witel|{w}")] for w in WITEL_OPTIONS]
    await update.message.reply_text(
        "🚇 Silakan pilih *WITEL* untuk cek Metro:",
        reply_markup=InlineKeyboardMarkup(keyboard),
        parse_mode="Markdown"
    )
    return ASK_WITEL


async def handle_witel_selection(update: Update, context: CallbackContext) -> int:
    query = update.callback_query
    await query.answer()
    _, witel = query.data.split("|", 1)
    context.user_data["witel"] = witel

    sto_list = STO_OPTIONS.get(witel, [])
    keyboard = [[InlineKeyboardButton(s, callback_data=f"select_sto|{s}")] for s in sto_list]
    await query.edit_message_text(
        f"🏢 *WITEL:* {witel}\nSilakan pilih *STO*: ",
        reply_markup=InlineKeyboardMarkup(keyboard),
        parse_mode="Markdown"
    )
    return ASK_STO


async def handle_sto_selection(update: Update, context: CallbackContext) -> int:
    query = update.callback_query
    await query.answer()
    _, sto = query.data.split("|", 1)
    context.user_data["sto"] = sto  # STO utama tetap disimpan

    substo_list = SUBSTO_OPTIONS.get(sto)
    if substo_list:
        keyboard = [[InlineKeyboardButton(s, callback_data=f"select_substo|{s}")] for s in substo_list]
        await query.edit_message_text(
            f"🏢 *STO:* {sto}\nSilakan pilih *Sub-STO*:",
            reply_markup=InlineKeyboardMarkup(keyboard),
            parse_mode="Markdown"
        )
        return ASK_SUBSTO
    else:
        await query.edit_message_text(
            f"🏢 *STO:* {sto}\nSilakan masukkan *GPON Hostname*:",
            parse_mode="Markdown"
        )
        return ASK_HOSTNAME


async def handle_substo_selection(update: Update, context: CallbackContext) -> int:
    query = update.callback_query
    await query.answer()
    _, substo = query.data.split("|", 1)
    context.user_data["substo"] = substo  # ✅ sub-STO dipisah dari STO utama

    await query.edit_message_text(
        f"📍 *Sub-STO:* {substo}\nSilakan masukkan *GPON Hostname*:",
        parse_mode="Markdown"
    )
    return ASK_HOSTNAME


async def handle_hostname(update: Update, context: CallbackContext) -> int:
    hostname = update.message.text.strip()
    substo = context.user_data.get("substo") or context.user_data.get("sto")  # fallback ke STO utama
    table_name = f"data_uplink_{substo.lower()}"

    if not hostname:
        await update.message.reply_text("❌ Hostname tidak boleh kosong.")
        return ASK_HOSTNAME

    try:
        conn = pymysql.connect(**DB_CONFIG)
        with conn:
            with conn.cursor() as cur:
                sql = (
                    f"SELECT * FROM `{table_name}` "
                    "WHERE LOWER(TRIM(gpon_hostname)) = LOWER(TRIM(%s))"
                )
                cur.execute(sql, (hostname,))
                row = cur.fetchone()
    except Exception as e:
        logger.error("DB Error: %s", e)
        await update.message.reply_text(
            f"❌ Gagal mengakses database tabel `{table_name}`.",
            parse_mode="Markdown"
        )
        return ConversationHandler.END

    if row:
        msg = (
            "✅ *Data Metro Ditemukan!*\n"
            f"📌 *Witel:* {row.get('witel', '-')}\n"
            f"🏢 *STO:* {row.get('sto', '-')}\n"
            f"🔢 *GPON Hostname:* {row.get('gpon_hostname', '-')}\n"
            f"🛜 *IP:* {row.get('gpon_ip', '-')}\n"
            f"🧷 *Merk:* {row.get('gpon_merk', '-')}\n"
            f"📦 *Tipe:* {row.get('gpon_tipe', '-')}\n"
            f"🔌 *Interface:* {row.get('gpon_intf', '-')}\n"
            f"📶 *Bandwidth:* {row.get('bw', '-')}\n"
            f"📍 *VLAN SIP:* {row.get('vlan_sip', '-')}\n"
            f"🌐 *VLAN Internet:* {row.get('vlan_internet', '-')}\n"
            f"🗂 *OTN Cross Metro:* {row.get('otn_cross_metro', '-')}\n"
            f"📝 *Keterangan:* {row.get('keterangan', '-')}"
        )
    else:
        msg = (
            f"⚠️ Data Metro tidak ditemukan.\n"
            f"Tabel: `{table_name}`\nHostname: `{hostname}`"
        )

    await update.message.reply_text(msg, parse_mode="Markdown")
    return ConversationHandler.END


def register_handler(app) -> None:
    conv = ConversationHandler(
        entry_points=[CommandHandler("cekmetro", start_cekmetro)],
        states={
            ASK_WITEL: [CallbackQueryHandler(handle_witel_selection, pattern=r"^select_witel\|")],
            ASK_STO: [CallbackQueryHandler(handle_sto_selection, pattern=r"^select_sto\|")],
            ASK_SUBSTO: [CallbackQueryHandler(handle_substo_selection, pattern=r"^select_substo\|")],
            ASK_HOSTNAME: [MessageHandler(filters.TEXT & ~filters.COMMAND, handle_hostname)],
        },
        fallbacks=[],
        allow_reentry=True,
    )
    app.add_handler(conv)
