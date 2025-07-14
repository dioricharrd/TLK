import os
import logging
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
from database.db import get_connection_database

# Load environment
load_dotenv()

# Logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Conversation states
ASK_WITEL, ASK_STO, ASK_SUBSTO, ASK_GPON, ASK_CARD = range(5)

# Static options
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


async def start_cekgpon(update: Update, context: CallbackContext) -> int:
    keyboard = [[InlineKeyboardButton(w, callback_data=f"select_witel|{w}")] for w in WITEL_OPTIONS]
    await update.message.reply_text(
        "🔍 Silakan pilih *WITEL* untuk cek GPON:",
        reply_markup=InlineKeyboardMarkup(keyboard),
        parse_mode="Markdown"
    )
    return ASK_WITEL


async def handle_witel_selection(update: Update, context: CallbackContext) -> int:
    query = update.callback_query
    await query.answer()
    _, witel = query.data.split("|", 1)
    context.user_data['witel'] = witel

    try:
        conn = get_connection_database()
        with conn:
            with conn.cursor() as cur:
                cur.execute("SELECT DISTINCT sto FROM data_ftm WHERE witel=%s ORDER BY sto", (witel,))
                rows = cur.fetchall()
        sto_list = [r['sto'] for r in rows] or STO_OPTIONS.get(witel, [])
    except Exception:
        logger.warning("Gagal ambil STO dari DB, fallback ke default.")
        sto_list = STO_OPTIONS.get(witel, [])

    keyboard = [[InlineKeyboardButton(s, callback_data=f"select_sto|{s}")] for s in sto_list]
    await query.edit_message_text(
        f"🏢 *WITEL:* {witel}\nSilakan pilih *STO*:",
        reply_markup=InlineKeyboardMarkup(keyboard),
        parse_mode="Markdown"
    )
    return ASK_STO


async def handle_sto_selection(update: Update, context: CallbackContext) -> int:
    query = update.callback_query
    await query.answer()
    _, sto = query.data.split("|", 1)
    context.user_data['sto'] = sto

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
            f"🏢 *STO:* {sto}\nSilakan masukkan *nama GPON*:",
            parse_mode="Markdown"
        )
        return ASK_GPON


async def handle_substo_selection(update: Update, context: CallbackContext) -> int:
    query = update.callback_query
    await query.answer()
    _, substo = query.data.split("|", 1)
    context.user_data['sto'] = substo  # overwrite STO

    await query.edit_message_text(
        f"📍 *Sub-STO:* {substo}\nSilakan masukkan *nama GPON*:",
        parse_mode="Markdown"
    )
    return ASK_GPON


async def handle_gpon(update: Update, context: CallbackContext) -> int:
    context.user_data['gpon'] = update.message.text.strip()
    await update.message.reply_text(
        "📥 Silakan masukkan *Card/Port* (format `card/port`):",
        parse_mode="Markdown"
    )
    return ASK_CARD


async def handle_card(update: Update, context: CallbackContext) -> int:
    text = update.message.text.strip()
    if '/' not in text:
        await update.message.reply_text("❌ Format salah, gunakan `card/port`.", parse_mode="Markdown")
        return ASK_CARD

    card_str, port_str = map(str.strip, text.split('/', 1))
    if not (card_str.isdigit() and port_str.isdigit()):
        await update.message.reply_text("❌ Card dan port harus angka.", parse_mode="Markdown")
        return ASK_CARD

    witel = context.user_data['witel']
    sto = context.user_data['sto']
    gpon = context.user_data['gpon'].strip()
    card, port = int(card_str), int(port_str)
    table_name = f"data_{sto.lower()}"

    logger.info("[QUERY DEBUG] table=%s, gpon=%s, card=%s, port=%s", table_name, gpon, card, port)

    try:
        conn = get_connection_database()
        with conn:
            with conn.cursor() as cur:
                sql = (
                    f"SELECT witel, sto, nama_gpon, ip, card, port "
                    f"FROM `{table_name}` "
                    f"WHERE LOWER(TRIM(nama_gpon)) = LOWER(%s) AND card = %s AND port = %s"
                )
                cur.execute(sql, (gpon, card, port))
                row = cur.fetchone()
    except Exception as e:
        logger.error("DB error: %s", e)
        await update.message.reply_text(f"❌ Gagal query DB: `{e}`", parse_mode="Markdown")
        return ConversationHandler.END

    if row:
        msg = (
            "✅ *Data GPON Ditemukan!*\n"
            f"📌 *WITEL:* {row['witel']}\n"
            f"🏢 *STO:* {row['sto']}\n"
            f"🔢 *GPON:* {row['nama_gpon']}\n"
            f"🛜 *IP:* {row['ip']}\n"
            f"🛠 *Card:* {row['card']}\n"
            f"🔌 *Port:* {row['port']}"
        )
    else:
        msg = (
            "⚠️ Data tidak ditemukan di database.\n"
            f"📎 Tabel: `{table_name}`\n"
            f"📌 GPON: `{gpon}`\n"
            f"🛠 Card/Port: `{card}/{port}`"
        )

    await update.message.reply_text(msg, parse_mode="Markdown")
    return ConversationHandler.END


def register_handler(app) -> None:
    conv = ConversationHandler(
        entry_points=[CommandHandler('cekgpon', start_cekgpon)],
        states={
            ASK_WITEL: [CallbackQueryHandler(handle_witel_selection, pattern=r"^select_witel\|")],
            ASK_STO: [CallbackQueryHandler(handle_sto_selection, pattern=r"^select_sto\|")],
            ASK_SUBSTO: [CallbackQueryHandler(handle_substo_selection, pattern=r"^select_substo\|")],
            ASK_GPON: [MessageHandler(filters.TEXT & ~filters.COMMAND, handle_gpon)],
            ASK_CARD: [MessageHandler(filters.TEXT & ~filters.COMMAND, handle_card)],
        },
        fallbacks=[],
        allow_reentry=True,
    )
    app.add_handler(conv)
