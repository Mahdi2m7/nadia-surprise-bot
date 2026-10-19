import logging
import os
import random
import sqlite3
from pathlib import Path

from telegram import (
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    KeyboardButton,
    ReplyKeyboardMarkup,
    Update,
)
from telegram.error import TelegramError, Forbidden, BadRequest
from telegram.ext import (
    Application,
    CallbackQueryHandler,
    CommandHandler,
    ContextTypes,
    MessageHandler,
    filters,
)

TOKEN = os.getenv("BOT_TOKEN", "").strip()
ADMIN_ID_RAW = os.getenv("ADMIN_ID", "").strip()
DB_PATH = os.getenv("DB_PATH", "bot_data.sqlite3")

logging.basicConfig(
    format="%(asctime)s | %(levelname)s | %(name)s | %(message)s",
    level=logging.INFO,
)
logging.getLogger("httpx").setLevel(logging.WARNING)
log = logging.getLogger(__name__)

if not TOKEN:
    raise RuntimeError("BOT_TOKEN environment variable is missing.")
if not ADMIN_ID_RAW.isdigit():
    raise RuntimeError("ADMIN_ID must be your numeric Telegram user ID.")
ADMIN_ID = int(ADMIN_ID_RAW)


def connect_db():
    conn = sqlite3.connect(DB_PATH)
    conn.execute("PRAGMA foreign_keys = ON")
    return conn


def init_db():
    with connect_db() as conn:
        conn.execute("""
            CREATE TABLE IF NOT EXISTS users (
                user_id INTEGER PRIMARY KEY,
                first_seen TEXT DEFAULT CURRENT_TIMESTAMP
            )
        """)
        conn.execute("""
            CREATE TABLE IF NOT EXISTS songs (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                file_id TEXT NOT NULL,
                title TEXT NOT NULL,
                added_at TEXT DEFAULT CURRENT_TIMESTAMP
            )
        """)
        conn.execute("""
            CREATE TABLE IF NOT EXISTS goodnights (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                text TEXT NOT NULL
            )
        """)
        count = conn.execute("SELECT COUNT(*) FROM goodnights").fetchone()[0]
        if count == 0:
            conn.executemany(
                "INSERT INTO goodnights(text) VALUES (?)",
                [
                    ("شب بخیر نادیای من، امیدوارم امشب قشنگ‌ترین خواب‌ها رو ببینی. 🌙",),
                    ("روز تموم شد؛ فقط خواستم بگم یکی این گوشه به یادت بود. شب بخیر.",),
                    ("ماه امشب نگهبان خواباته؛ شب بخیررر.",),
                ],
            )


def is_admin(user_id: int) -> bool:
    return user_id == ADMIN_ID


def main_keyboard():
    return ReplyKeyboardMarkup(
        [
            [KeyboardButton("🎧 یه آهنگ رندوم"), KeyboardButton("🌙 شب بخیر")],
            [KeyboardButton("💌 یه پیام از متی"), KeyboardButton("🎁 سورپرایزم کن")],
        ],
        resize_keyboard=True,
        is_persistent=True,
    )


def admin_keyboard():
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("📣 ارسال پیام همگانی", callback_data="admin:broadcast")],
        [InlineKeyboardButton("🎵 اضافه‌کردن آهنگ", callback_data="admin:add_song"),
         InlineKeyboardButton("📝 اضافه‌کردن شب‌بخیر", callback_data="admin:add_goodnight")],
        [InlineKeyboardButton("📊 آمار بات", callback_data="admin:stats")],
        [InlineKeyboardButton("❌ لغو عملیات", callback_data="admin:cancel")],
    ])


async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    if not user or not update.message:
        return
    with connect_db() as conn:
        conn.execute("INSERT OR IGNORE INTO users(user_id) VALUES (?)", (user.id,))
    await update.message.reply_text(
        "سلاممم 🌙\nبه گوشه‌ی کوچیک خودت خوش اومدی.\nامشب دلت چی می‌خواد؟",
        reply_markup=main_keyboard(),
    )


async def admin_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    if not user or not update.message:
        return
    if not is_admin(user.id):
        await update.message.reply_text("این بخش در دسترس نیست.")
        return
    context.user_data.pop("admin_mode", None)
    await update.message.reply_text("پنل مدیریت مخفی", reply_markup=admin_keyboard())


async def admin_callbacks(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    if not query:
        return
    user = query.from_user
    if not is_admin(user.id):
        await query.answer("اجازه دسترسی نداری.", show_alert=True)
        return
    await query.answer()
    data = query.data or ""

    if data == "admin:broadcast":
        context.user_data["admin_mode"] = "broadcast"
        await query.message.reply_text(
            "پیام موردنظرت رو بفرست. متن، عکس، ویدیو، ویس یا فایل قابل ارساله.\n"
            "برای لغو، /cancel رو بزن."
        )
    elif data == "admin:add_song":
        context.user_data["admin_mode"] = "add_song"
        await query.message.reply_text(
            "حالا فایل آهنگ رو به‌صورت Audio بفرست (ترجیحاً MP3).\n"
            "برای لغو، /cancel رو بزن."
        )
    elif data == "admin:add_goodnight":
        context.user_data["admin_mode"] = "add_goodnight"
        await query.message.reply_text(
            "متن شب‌بخیر جدید رو بفرست.\nبرای لغو، /cancel رو بزن."
        )
    elif data == "admin:stats":
        with connect_db() as conn:
            users = conn.execute("SELECT COUNT(*) FROM users").fetchone()[0]
            songs = conn.execute("SELECT COUNT(*) FROM songs").fetchone()[0]
            nights = conn.execute("SELECT COUNT(*) FROM goodnights").fetchone()[0]
        await query.message.reply_text(
            f"📊 آمار بات\nکاربرها: {users}\nآهنگ‌ها: {songs}\nمتن‌های شب‌بخیر: {nights}"
        )
    elif data == "admin:cancel":
        context.user_data.pop("admin_mode", None)
        await query.message.reply_text("عملیات لغو شد.")


async def cancel(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user and is_admin(update.effective_user.id):
        context.user_data.pop("admin_mode", None)
        await update.message.reply_text("عملیات لغو شد.")
    else:
        await update.message.reply_text("دستوری برای لغو وجود ندارد.")


async def send_random_song(update: Update, context: ContextTypes.DEFAULT_TYPE):
    with connect_db() as conn:
        rows = conn.execute("SELECT file_id, title FROM songs").fetchall()
    if not rows:
        await update.message.reply_text("هنوز آهنگی به لیستم اضافه نشده؛ بعداً دوباره امتحان کن.")
        return
    file_id, title = random.choice(rows)
    await update.message.reply_audio(audio=file_id, caption=f"🎧 {title}")


async def send_goodnight(update: Update, context: ContextTypes.DEFAULT_TYPE):
    with connect_db() as conn:
        rows = conn.execute("SELECT text FROM goodnights").fetchall()
    if not rows:
        await update.message.reply_text("هنوز متن شب‌بخیر ندارم.")
        return
    await update.message.reply_text(random.choice(rows)[0])


async def surprise(update: Update, context: ContextTypes.DEFAULT_TYPE):
    choice = random.choice(["song", "goodnight", "message"])
    if choice == "song":
        await send_random_song(update, context)
    elif choice == "goodnight":
        await send_goodnight(update, context)
    else:
        await update.message.reply_text(
            "شاید امروز همه‌چی دقیقاً اون‌جوری که می‌خواستی پیش نرفته باشه، "
            "ولی یادت نره یه نفر هست که با دیدن اسمت لبخند می‌زنه. ♡"
        )


async def handle_user_buttons(update: Update, context: ContextTypes.DEFAULT_TYPE):
    message = update.message
    if not message or not update.effective_user:
        return

    # Admin input mode has priority over regular menu buttons.
    if is_admin(update.effective_user.id):
        mode = context.user_data.get("admin_mode")
        if mode == "broadcast":
            context.user_data.pop("admin_mode", None)
            with connect_db() as conn:
                user_ids = [row[0] for row in conn.execute("SELECT user_id FROM users").fetchall()]
            sent = 0
            failed = 0
            for user_id in user_ids:
                try:
                    await context.bot.copy_message(
                        chat_id=user_id,
                        from_chat_id=message.chat_id,
                        message_id=message.message_id,
                    )
                    sent += 1
                except (Forbidden, BadRequest, TelegramError) as exc:
                    failed += 1
                    log.info("Broadcast failed for %s: %s", user_id, exc)
                    if isinstance(exc, Forbidden):
                        with connect_db() as conn:
                            conn.execute("DELETE FROM users WHERE user_id = ?", (user_id,))
            await message.reply_text(f"ارسال همگانی تمام شد.\nموفق: {sent}\nناموفق: {failed}",
                                     reply_markup=main_keyboard())
            return

        if mode == "add_song":
            if not message.audio:
                await message.reply_text("لطفاً آهنگ رو به‌صورت فایل Audio بفرست، نه پیام متنی.")
                return
            title = message.audio.title or message.audio.file_name or "آهنگ بدون عنوان"
            with connect_db() as conn:
                conn.execute("INSERT INTO songs(file_id, title) VALUES (?, ?)",
                             (message.audio.file_id, title))
            context.user_data.pop("admin_mode", None)
            await message.reply_text(f"آهنگ «{title}» اضافه شد.", reply_markup=main_keyboard())
            return

        if mode == "add_goodnight":
            if not message.text or message.text.startswith("/"):
                await message.reply_text("لطفاً متن شب‌بخیر رو به‌صورت پیام متنی بفرست.")
                return
            with connect_db() as conn:
                conn.execute("INSERT INTO goodnights(text) VALUES (?)", (message.text,))
            context.user_data.pop("admin_mode", None)
            await message.reply_text("متن شب‌بخیر اضافه شد.", reply_markup=main_keyboard())
            return

    text = (message.text or "").strip()
    if text == "🎧 یه آهنگ رندوم":
        await send_random_song(update, context)
    elif text == "🌙 شب بخیر":
        await send_goodnight(update, context)
    elif text == "💌 یه پیام از متی":
        await message.reply_text(
            "یه پیام کوچیک از متی: حتی اگه روزت شلوغ و خسته‌کننده بوده، "
            "امیدوارم یه چیز کوچیک باعث لبخندت بشه. ♡"
        )
    elif text == "🎁 سورپرایزم کن":
        await surprise(update, context)
    else:
        await message.reply_text("از دکمه‌های پایین انتخاب کن 🌙", reply_markup=main_keyboard())


def main():
    init_db()
    app = Application.builder().token(TOKEN).build()
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("admin", admin_command))
    app.add_handler(CommandHandler("cancel", cancel))
    app.add_handler(CallbackQueryHandler(admin_callbacks, pattern=r"^admin:"))
    app.add_handler(MessageHandler(filters.ALL & ~filters.COMMAND, handle_user_buttons))
    log.info("Bot is running.")
    app.run_polling(allowed_updates=Update.ALL_TYPES)


if __name__ == "__main__":
    main()
