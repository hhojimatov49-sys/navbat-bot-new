import os
import threading
from http.server import BaseHTTPRequestHandler, HTTPServer
from datetime import datetime, date

import gspread
from google.oauth2.service_account import Credentials

from telegram import Update, ReplyKeyboardMarkup
from telegram.ext import (
    Application,
    CommandHandler,
    MessageHandler,
    ContextTypes,
    ConversationHandler,
    filters,
)


# =========================================================
# ENVIRONMENT
# =========================================================

TOKEN = os.environ["BOT_TOKEN"]
SHEET_ID = os.environ["GOOGLE_SHEET_ID"]

PORT = int(os.environ.get("PORT", "10000"))

CREDENTIALS_FILE = os.environ.get(
    "GOOGLE_APPLICATION_CREDENTIALS",
    "/etc/secrets/google-service-account.json"
)


# =========================================================
# TRACTORLAR
# =========================================================

TRACTORS = [
    "60059KBA",
    "60227SBA",
    "60510KBA",
    "60501KBA",
    "60507KBA",
    "60511KBA",
    "60260SBA",
    "60515KBA",
    "60277KBA",
    "60110QBA",
    "60720SBA",
    "60545SBA",
    "60740SBA",
    "60730SBA",
    "60474SBA",
    "60373SBA",
    "60414SBA",
    "60755SBA",
    "60441SBA",
    "60442SBA",
    "60445SBA",
]


# =========================================================
# MENU
# =========================================================

MENU = ReplyKeyboardMarkup(
    [
        ["➕ Navbat berildi", "💰 Shoferdan olindi"],
        ["📊 Hisobot", "📥 Excel"],
    ],
    resize_keyboard=True
)


# =========================================================
# STATES
# =========================================================

ASK_DATE, ASK_TRUCK, ASK_AMOUNT = range(3)


# =========================================================
# GOOGLE SHEETS
# =========================================================

SCOPES = [
    "https://www.googleapis.com/auth/spreadsheets",
    "https://www.googleapis.com/auth/drive",
]

creds = Credentials.from_service_account_file(
    CREDENTIALS_FILE,
    scopes=SCOPES
)

gc = gspread.authorize(creds)
sh = gc.open_by_key(SHEET_ID)

try:
    ws = sh.worksheet("Navbat")
except gspread.WorksheetNotFound:
    ws = sh.add_worksheet(
        title="Navbat",
        rows=1000,
        cols=10
    )


HEADERS = [
    "ID",
    "Holat",
    "Berilgan sana",
    "Mashina",
    "Berilgan summa",
    "Olingan sana",
    "Olingan summa",
    "Farq",
    "Yaratilgan vaqt",
]


# =========================================================
# SHEETNI TAYYORLASH
# =========================================================

try:
    first_row = ws.row_values(1)

    if first_row != HEADERS:
        ws.update(
            "A1:I1",
            [HEADERS]
        )
except Exception as e:
    print("Header xatosi:", e)


# =========================================================
# YORDAMCHI FUNKSIYALAR
# =========================================================

def money(value):
    try:
        return f"{int(float(value)):,}".replace(",", " ")
    except Exception:
        return "0"


def today_str():
    return datetime.now().strftime("%d.%m.%Y")


def find_rows(truck, dt):
    """
    Mashina + sana bo'yicha barcha qatorlarni topadi.
    """
    records = ws.get_all_records()

    result = []

    for i, row in enumerate(records, start=2):
        row_truck = str(row.get("Mashina", "")).strip()
        row_date = str(row.get("Berilgan sana", "")).strip()

        if row_truck == truck and row_date == dt:
            result.append((i, row))

    return result


def add_given(truck, dt, amount):
    records = ws.get_all_records()

    new_id = len(records) + 1

    row = [
        new_id,
        "BERILDI",
        dt,
        truck,
        amount,
        "",
        "",
        amount,
        datetime.now().strftime("%d.%m.%Y %H:%M:%S"),
    ]

    ws.append_row(
        row,
        value_input_option="USER_ENTERED"
    )


def receive_latest(truck, dt, amount):
    rows = find_rows(truck, dt)

    if not rows:
        return False

    # Eng oxirgi mos qator
    row_number, row = rows[-1]

    given_amount = float(row.get("Berilgan summa", 0) or 0)

    difference = given_amount - amount

    ws.update(
        f"B{row_number}:H{row_number}",
        [[
            "OLINDI",
            dt,
            truck,
            given_amount,
            dt,
            amount,
            difference,
        ]]
    )

    return True


# =========================================================
# START
# =========================================================

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):

    context.user_data.clear()

    await update.message.reply_text(
        "Assalomu alaykum!\n\n"
        "Navbat hisob-kitob botiga xush kelibsiz.",
        reply_markup=MENU
    )


# =========================================================
# NAVBAT BERILDI
# =========================================================

async def given_start(update: Update, context: ContextTypes.DEFAULT_TYPE):

    context.user_data.clear()
    context.user_data["mode"] = "given"

    await update.message.reply_text(
        "📅 Sanani kiriting.\n\n"
        "Masalan: 26.09.2026"
    )

    return ASK_DATE


# =========================================================
# SHOFIRDAN OLINDI
# =========================================================

async def received_start(update: Update, context: ContextTypes.DEFAULT_TYPE):

    context.user_data.clear()
    context.user_data["mode"] = "received"

    await update.message.reply_text(
        "📅 Sanani kiriting.\n\n"
        "Masalan: 26.09.2026"
    )

    return ASK_DATE


# =========================================================
# DATE
# =========================================================

async def date_message(update: Update, context: ContextTypes.DEFAULT_TYPE):

    text = update.message.text.strip()

    try:
        datetime.strptime(text, "%d.%m.%Y")
    except ValueError:

        await update.message.reply_text(
            "❌ Sana noto‘g‘ri.\n\n"
            "Masalan: 26.09.2026"
        )

        return ASK_DATE

    context.user_data["date"] = text

    keyboard = []

    row = []

    for tractor in TRACTORS:

        row.append(tractor)

        if len(row) == 2:
            keyboard.append(row)
            row = []

    if row:
        keyboard.append(row)

    await update.message.reply_text(
        "🚛 Mashinani tanlang:",
        reply_markup=ReplyKeyboardMarkup(
            keyboard,
            resize_keyboard=True,
            one_time_keyboard=True
        )
    )

    return ASK_TRUCK


# =========================================================
# TRUCK
# =========================================================

async def truck_message(update: Update, context: ContextTypes.DEFAULT_TYPE):

    truck = update.message.text.strip()

    if truck not in TRACTORS:

        await update.message.reply_text(
            "❌ Iltimos, ro‘yxatdan mashinani tanlang."
        )

        return ASK_TRUCK

    context.user_data["truck"] = truck

    await update.message.reply_text(
        "💰 Summani kiriting.\n\n"
        "Masalan: 150000"
    )

    return ASK_AMOUNT


# =========================================================
# AMOUNT
# =========================================================

async def amount_message(update: Update, context: ContextTypes.DEFAULT_TYPE):

    text = (
        update.message.text
        .strip()
        .replace(" ", "")
        .replace(",", "")
    )

    try:
        amount = float(text)

        if amount < 0:
            raise ValueError

    except ValueError:

        await update.message.reply_text(
            "❌ Summa noto‘g‘ri.\n\n"
            "Masalan: 150000"
        )

        return ASK_AMOUNT

    truck = context.user_data["truck"]
    dt = context.user_data["date"]
    mode = context.user_data["mode"]

    # -----------------------------------------------------
    # BERILDI
    # -----------------------------------------------------

    if mode == "given":

        add_given(
            truck,
            dt,
            amount
        )

        await update.message.reply_text(
            "✅ Navbat berildi!\n\n"
            f"🚛 {truck}\n"
            f"📅 {dt}\n"
            f"💰 {money(amount)}",
            reply_markup=MENU
        )

    # -----------------------------------------------------
    # OLINDI
    # -----------------------------------------------------

    else:

        ok = receive_latest(
            truck,
            dt,
            amount
        )

        if ok:

            await update.message.reply_text(
                "✅ Shoferdan olindi!\n\n"
                f"🚛 {truck}\n"
                f"📅 {dt}\n"
                f"💰 {money(amount)}",
                reply_markup=MENU
            )

        else:

            await update.message.reply_text(
                f"❌ {truck} uchun {dt} sanada "
                "berilgan navbat topilmadi.",
                reply_markup=MENU
            )

    context.user_data.clear()

    return ConversationHandler.END


# =========================================================
# CANCEL
# =========================================================

async def cancel(update: Update, context: ContextTypes.DEFAULT_TYPE):

    context.user_data.clear()

    await update.message.reply_text(
        "❌ Bekor qilindi.",
        reply_markup=MENU
    )

    return ConversationHandler.END


# =========================================================
# HISOBOT
# =========================================================

async def report(update: Update, context: ContextTypes.DEFAULT_TYPE):

    records = ws.get_all_records()

    if not records:

        await update.message.reply_text(
            "📊 Hozircha hisobot uchun ma'lumot yo‘q.",
            reply_markup=MENU
        )

        return

    lines = []

    total_given = 0
    total_received = 0

    for row in records:

        truck = str(row.get("Mashina", "")).strip()

        if not truck:
            continue

        given = float(row.get("Berilgan summa", 0) or 0)
        received = float(row.get("Olingan summa", 0) or 0)

        difference = given - received

        total_given += given
        total_received += received

        lines.append(
            f"{truck}: "
            f"Berilgan {money(given)} | "
            f"Olingan {money(received)} | "
            f"Farq {money(difference)}"
        )

    if not lines:

        await update.message.reply_text(
            "📊 Hozircha hisobot uchun ma'lumot yo‘q.",
            reply_markup=MENU
        )

        return

    text = "📊 NAVBAT HISOBOTI\n\n"

    text += "\n".join(lines)

    text += (
        "\n\n━━━━━━━━━━━━━━━━━━━━\n"
        f"Jami berilgan: {money(total_given)}\n"
        f"Jami olingan: {money(total_received)}\n"
        f"Jami farq: {money(total_given - total_received)}"
    )

    # Telegram 4096 belgidan uzun xabarni qabul qilmaydi
    if len(text) <= 4000:

        await update.message.reply_text(
            text,
            reply_markup=MENU
        )

    else:

        for i in range(0, len(text), 4000):

            await update.message.reply_text(
                text[i:i + 4000],
                reply_markup=MENU
            )


# =========================================================
# EXCEL
# =========================================================

async def excel(update: Update, context: ContextTypes.DEFAULT_TYPE):

    await update.message.reply_text(
        "📥 Excel funksiyasini keyingi bosqichda qo‘shamiz.",
        reply_markup=MENU
    )


# =========================================================
# MENU HANDLER
# =========================================================

async def menu(update: Update, context: ContextTypes.DEFAULT_TYPE):

    text = update.message.text

    if text == "➕ Navbat berildi":
        return await given_start(update, context)

    if text == "💰 Shoferdan olindi":
        return await received_start(update, context)

    if text == "📊 Hisobot":
        await report(update, context)
        return ConversationHandler.END

    if text == "📥 Excel":
        await excel(update, context)
        return ConversationHandler.END

    await update.message.reply_text(
        "Menyudan birini tanlang.",
        reply_markup=MENU
    )

    return ConversationHandler.END


# =========================================================
# HEALTH SERVER
# =========================================================

class HealthHandler(BaseHTTPRequestHandler):

    def do_GET(self):

        self.send_response(200)

        self.send_header(
            "Content-type",
            "text/plain"
        )

        self.end_headers()

        self.wfile.write(
            b"Navbat bot is alive!"
        )

    def log_message(self, format, *args):
        return


def run_health_server():

    server = HTTPServer(
        ("0.0.0.0", PORT),
        HealthHandler
    )

    print(
        f"Health server running on port {PORT}"
    )

    server.serve_forever()


# =========================================================
# MAIN
# =========================================================

def main():

    print("================================")
    print("NAVBAT BOT STARTING...")
    print("================================")

    # Render health server
    health_thread = threading.Thread(
        target=run_health_server,
        daemon=True
    )

    health_thread.start()

    # Telegram
    app = (
        Application
        .builder()
        .token(TOKEN)
        .build()
    )

    # Conversation
    conv = ConversationHandler(

        entry_points=[
            MessageHandler(
                filters.Regex("^➕ Navbat berildi$"),
                given_start
            ),
            MessageHandler(
                filters.Regex("^💰 Shoferdan olindi$"),
                received_start
            ),
        ],

        states={

            ASK_DATE: [
                MessageHandler(
                    filters.TEXT & ~filters.COMMAND,
                    date_message
                )
            ],

            ASK_TRUCK: [
                MessageHandler(
                    filters.TEXT & ~filters.COMMAND,
                    truck_message
                )
            ],

            ASK_AMOUNT: [
                MessageHandler(
                    filters.TEXT & ~filters.COMMAND,
                    amount_message
                )
            ],
        },

        fallbacks=[
            CommandHandler(
                "cancel",
                cancel
            )
        ],

        per_chat=True,
        per_user=True,
    )

    app.add_handler(
        CommandHandler(
            "start",
            start
        )
    )

    app.add_handler(conv)

    app.add_handler(
        MessageHandler(
            filters.Regex("^📊 Hisobot$"),
            report
        )
    )

    app.add_handler(
        MessageHandler(
            filters.Regex("^📥 Excel$"),
            excel
        )
    )

    print("BOT IS RUNNING!")

    # Polling
    app.run_polling(
        drop_pending_updates=True
    )


if __name__ == "__main__":
    main()
