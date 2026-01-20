#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Whosent bot (aiogram v3) — single-file implementation.

Requirements:
  aiogram==3.22.0
  aiohttp==3.12.15
  python-dotenv==1.0.0

.env file (example):
  BOT_TOKEN=...
  ADMIN_ID=6992171884
  ADMIN_USERNAME=ATC03
  BOT_USERNAME=whosent_bot
  SUPPORT_USERNAME=metopo
  REVEAL_PRICE_STARS=25
  DB_PATH=anon_bot.db
"""

import os
import sqlite3
import time
import logging
from datetime import datetime, timezone

from dotenv import load_dotenv

from aiogram import Bot, Dispatcher, types
from aiogram.filters import Command
from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton

load_dotenv()

# ----------------------------
# CONFIG (from .env)
# ----------------------------
BOT_TOKEN = os.getenv("BOT_TOKEN")
ADMIN_ID = int(os.getenv("ADMIN_ID", "0"))
ADMIN_USERNAME = os.getenv("ADMIN_USERNAME", "")
BOT_USERNAME = os.getenv("BOT_USERNAME", "whosent_bot")
SUPPORT_USERNAME = os.getenv("SUPPORT_USERNAME", "")
REVEAL_PRICE_STARS = int(os.getenv("REVEAL_PRICE_STARS", "25"))
DB_PATH = os.getenv("DB_PATH", "anon_bot.db")

if not BOT_TOKEN:
    raise SystemExit("BOT_TOKEN is required in .env")

# ----------------------------
# Logging
# ----------------------------
logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
logger = logging.getLogger(__name__)

# ----------------------------
# Bot & Dispatcher
# ----------------------------
bot = Bot(token=BOT_TOKEN)
dp = Dispatcher()

# ----------------------------
# In-memory states (simple)
# ----------------------------
pending_send_for_target = {}         # sender_id -> target_id
pending_reply_for_message = {}       # replier_id -> message_id
pending_idea_from_user = {}          # user_id -> True (user is entering idea text)
pending_appeal_from_user = {}        # user_id -> True (entering appeal text)

# ----------------------------
# Translations (all texts duplicated ru/en)
# Keys used throughout the code
# ----------------------------
TEXT = {
    "welcome": {
        "ru": "👋 Добро пожаловать!\n\nВыберите язык / Choose language:",
        "en": "👋 Welcome!\n\nPlease choose language / Пожалуйста, выберите язык:"
    },
    "choose_lang": {
        "ru": "Выберите язык:",
        "en": "Choose language:"
    },
    "start_onboarding": {
        "ru": "Начните получать анонимные сообщения прямо сейчас.\n\nВаша персональная ссылка:\n{link}\n\nРазместите ссылку в профиле — люди смогут писать вам анонимно.",
        "en": "Start receiving anonymous messages right now.\n\nYour personal link:\n{link}\n\nPlace the link in your profile so people can message you anonymously."
    },
    "enter_message_prompt": {
        "ru": "✉️ Напишите анонимное сообщение для этого пользователя. Ваш username не будет показан, если получатель не раскроет отправителя.",
        "en": "✉️ Write an anonymous message to this user. Your username will not be shown unless the recipient reveals the sender."
    },
    "message_sent_confirm": {
        "ru": "✅ Сообщение отправлено анонимно. Если получатель ответит, ответ придёт через бота.",
        "en": "✅ Message sent anonymously. If the recipient replies, the reply will come via the bot."
    },
    "new_msg_to_receiver": {
        "ru": "📩 У вас новое анонимное сообщение:\n\n{text}\n\nВы можете ответить бесплатно или пожаловаться.",
        "en": "📩 You have a new anonymous message:\n\n{text}\n\nYou can reply for free or report it."
    },
    "reply_request": {
        "ru": "Напишите ответ — он будет отправлен отправителю анонимно:",
        "en": "Write your reply — it will be sent to the sender anonymously:"
    },
    "reply_notification_to_sender": {
        "ru": "📨 На ваше сообщение ответили:\n\n{reply}",
        "en": "📨 Your message received a reply:\n\n{reply}"
    },
    "report_reason_prompt": {
        "ru": "Опишите причину жалобы (коротко):",
        "en": "Describe the reason for the report (brief):"
    },
    "report_received_user": {
        "ru": "Спасибо — ваша жалоба принята.",
        "en": "Thank you — your report has been received."
    },
    "report_admin_notify": {
        "ru": "🚨 Жалоба на сообщение #{mid}\nОтправитель (ID): {sender_id}\nUsername: {username}\nТекст: {preview}\nПричина: {reason}\nОт: {reporter}",
        "en": "🚨 Report on message #{mid}\nSender (ID): {sender_id}\nUsername: {username}\nText: {preview}\nReason: {reason}\nFrom: {reporter}"
    },
    "block_confirm_admin": {
        "ru": "Пользователь {uid} заблокирован.",
        "en": "User {uid} blocked."
    },
    "unblock_confirm_admin": {
        "ru": "Пользователь {uid} разблокирован.",
        "en": "User {uid} unblocked."
    },
    "ban_confirm_admin": {
        "ru": "Пользователь {uid} забанен навсегда.",
        "en": "User {uid} permanently banned."
    },
    "you_blocked": {
        "ru": "🚫 Вы временно заблокированы и не можете отправлять сообщения. У вас есть одна попытка подать апелляцию.",
        "en": "🚫 You are temporarily blocked and cannot send messages. You have one chance to file an appeal."
    },
    "you_banned": {
        "ru": "⛔ Вы заблокированы навсегда. Апелляции невозможны.",
        "en": "⛔ You are permanently banned. No appeals possible."
    },
    "appeal_prompt": {
        "ru": "Напишите вашу апелляцию (одна попытка):",
        "en": "Write your appeal (one attempt):"
    },
    "appeal_received_user": {
        "ru": "Ваша апелляция отправлена администратору.",
        "en": "Your appeal has been sent to the administrator."
    },
    "appeal_admin_notify": {
        "ru": "📝 Апелляция от {uid}\nUsername: {username}\nТекст:\n{appeal}",
        "en": "📝 Appeal from {uid}\nUsername: {username}\nText:\n{appeal}"
    },
    "lang_changed": {
        "ru": "✅ Язык сохранён.",
        "en": "✅ Language saved."
    },
    "invalid_link": {
        "ru": "Неправильная ссылка.",
        "en": "Invalid link."
    },
    "menu_text": {
        "ru": "Меню:",
        "en": "Menu:"
    },
    "stats_text": {
        "ru": "📈 Статистика:\nЗа сегодня: • сообщений: {m_today} • переходов: {v_today}\nЗа всё время: • сообщений: {m_total} • переходов: {v_total} • уникальных отправителей: {unique}",
        "en": "📈 Statistics:\nToday: • messages: {m_today} • visits: {v_today}\nAll time: • messages: {m_total} • visits: {v_total} • unique senders: {unique}"
    },
    "idea_prompt": {
        "ru": "Опишите вашу идею для бота (коротко):",
        "en": "Describe your idea for the bot (brief):"
    },
    "idea_thanks": {
        "ru": "Спасибо! Ваша идея отправлена администраторам.",
        "en": "Thanks! Your idea has been sent to the administrators."
    },
    "reveal_prompt": {
        "ru": "⭐ Раскрыть отправителя стоит {price}★ (симуляция).",
        "en": "⭐ Reveal sender costs {price}★ (simulation)."
    }
}

# ----------------------------
# Database (SQLite)
# ----------------------------
def init_db():
    con = sqlite3.connect(DB_PATH)
    cur = con.cursor()
    cur.execute("""
    CREATE TABLE IF NOT EXISTS users (
        user_id INTEGER PRIMARY KEY,
        username TEXT,
        first_name TEXT,
        language TEXT DEFAULT 'ru',
        messages_received INTEGER DEFAULT 0,
        appealed INTEGER DEFAULT 0
    );
    """)
    cur.execute("""
    CREATE TABLE IF NOT EXISTS messages (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        sender_id INTEGER,
        sender_username TEXT,
        sender_first_name TEXT,
        receiver_id INTEGER,
        text TEXT,
        revealed INTEGER DEFAULT 0,
        created_at INTEGER
    );
    """)
    cur.execute("""
    CREATE TABLE IF NOT EXISTS visits (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        visitor_id INTEGER,
        target_id INTEGER,
        created_at INTEGER
    );
    """)
    cur.execute("""
    CREATE TABLE IF NOT EXISTS reports (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        message_id INTEGER,
        reporter_id INTEGER,
        reason TEXT,
        created_at INTEGER
    );
    """)
    cur.execute("""
    CREATE TABLE IF NOT EXISTS ideas (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        from_user INTEGER,
        text TEXT,
        created_at INTEGER
    );
    """)
    cur.execute("""
    CREATE TABLE IF NOT EXISTS blocked (
        user_id INTEGER PRIMARY KEY,
        reason TEXT,
        blocked_at INTEGER,
        permanently INTEGER DEFAULT 0
    );
    """)
    cur.execute("""
    CREATE TABLE IF NOT EXISTS appeals (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        user_id INTEGER,
        text TEXT,
        created_at INTEGER,
        processed INTEGER DEFAULT 0
    );
    """)
    con.commit()
    con.close()

def db_execute(query, params=(), fetchone=False, fetchall=False, commit=False):
    con = sqlite3.connect(DB_PATH)
    cur = con.cursor()
    cur.execute(query, params)
    result = None
    if fetchone:
        result = cur.fetchone()
    if fetchall:
        result = cur.fetchall()
    if commit:
        con.commit()
    con.close()
    return result

# ----------------------------
# DB helpers
# ----------------------------
def ensure_user(user_id, username=None, first_name=None):
    row = db_execute("SELECT user_id FROM users WHERE user_id = ?", (user_id,), fetchone=True)
    if not row:
        db_execute("INSERT INTO users (user_id, username, first_name) VALUES (?, ?, ?)",
                   (user_id, username, first_name or ""), commit=True)
    else:
        db_execute("UPDATE users SET username = ?, first_name = ? WHERE user_id = ?",
                   (username, first_name or "", user_id), commit=True)

def set_user_language(user_id, lang):
    db_execute("UPDATE users SET language = ? WHERE user_id = ?", (lang, user_id), commit=True)

def get_user_language(user_id):
    row = db_execute("SELECT language FROM users WHERE user_id = ?", (user_id,), fetchone=True)
    return row[0] if row else "ru"

def create_visit(visitor_id, target_id):
    ts = int(time.time())
    db_execute("INSERT INTO visits (visitor_id, target_id, created_at) VALUES (?, ?, ?)",
               (visitor_id, target_id, ts), commit=True)

def create_message(sender_id, sender_username, sender_first_name, receiver_id, text):
    ts = int(time.time())
    db_execute("INSERT INTO messages (sender_id, sender_username, sender_first_name, receiver_id, text, created_at) VALUES (?, ?, ?, ?, ?, ?)",
               (sender_id, sender_username, sender_first_name, receiver_id, text, ts), commit=True)
    db_execute("UPDATE users SET messages_received = messages_received + 1 WHERE user_id = ?", (receiver_id,), commit=True)
    res = db_execute("SELECT last_insert_rowid()", fetchone=True)
    return res[0]

def get_message(mid):
    return db_execute("SELECT id, sender_id, sender_username, sender_first_name, receiver_id, text, revealed, created_at FROM messages WHERE id = ?", (mid,), fetchone=True)

def add_report(message_id, reporter_id, reason):
    ts = int(time.time())
    db_execute("INSERT INTO reports (message_id, reporter_id, reason, created_at) VALUES (?, ?, ?, ?)",
               (message_id, reporter_id, reason, ts), commit=True)

def count_unique_reports_against_sender(sender_id):
    # count distinct reporter_id for messages by sender_id
    rows = db_execute("""
        SELECT COUNT(DISTINCT r.reporter_id)
        FROM reports r
        JOIN messages m ON r.message_id = m.id
        WHERE m.sender_id = ?
    """, (sender_id,), fetchone=True)
    return rows[0] if rows else 0

def get_reports_for_sender(sender_id):
    rows = db_execute("""
        SELECT r.id, r.message_id, r.reporter_id, r.reason, r.created_at, m.text
        FROM reports r
        JOIN messages m ON r.message_id = m.id
        WHERE m.sender_id = ?
        ORDER BY r.created_at DESC
    """, (sender_id,), fetchall=True)
    return rows or []

def block_user(user_id, reason="", permanent=0):
    ts = int(time.time())
    db_execute("INSERT OR REPLACE INTO blocked (user_id, reason, blocked_at, permanently) VALUES (?, ?, ?, ?)",
               (user_id, reason, ts, permanent), commit=True)

def unblock_user(user_id):
    db_execute("DELETE FROM blocked WHERE user_id = ?", (user_id,), commit=True)

def is_blocked(user_id):
    row = db_execute("SELECT user_id, permanently FROM blocked WHERE user_id = ?", (user_id,), fetchone=True)
    return (True, bool(row[1])) if row else (False, False)

def save_appeal(user_id, text):
    ts = int(time.time())
    db_execute("INSERT INTO appeals (user_id, text, created_at) VALUES (?, ?, ?)", (user_id, text, ts), commit=True)
    res = db_execute("SELECT last_insert_rowid()", fetchone=True)
    return res[0]

def get_unprocessed_appeals():
    return db_execute("SELECT id, user_id, text, created_at FROM appeals WHERE processed = 0", fetchall=True) or []

def mark_appeal_processed(appeal_id):
    db_execute("UPDATE appeals SET processed = 1 WHERE id = ?", (appeal_id,), commit=True)

def save_idea(from_user, text):
    ts = int(time.time())
    db_execute("INSERT INTO ideas (from_user, text, created_at) VALUES (?, ?, ?)", (from_user, text, ts), commit=True)

def get_stats(user_id):
    start_today = datetime.now(timezone.utc).replace(hour=0, minute=0, second=0, microsecond=0).timestamp()
    m_today = db_execute("SELECT COUNT(*) FROM messages WHERE receiver_id = ? AND created_at >= ?", (user_id, int(start_today)), fetchone=True)[0]
    m_total = db_execute("SELECT COUNT(*) FROM messages WHERE receiver_id = ?", (user_id,), fetchone=True)[0]
    v_today = db_execute("SELECT COUNT(*) FROM visits WHERE target_id = ? AND created_at >= ?", (user_id, int(start_today)), fetchone=True)[0]
    v_total = db_execute("SELECT COUNT(*) FROM visits WHERE target_id = ?", (user_id,), fetchone=True)[0]
    unique = db_execute("SELECT COUNT(DISTINCT sender_id) FROM messages WHERE receiver_id = ?", (user_id,), fetchone=True)[0]
    return {"m_today": m_today, "m_total": m_total, "v_today": v_today, "v_total": v_total, "unique": unique}

# ----------------------------
# Utilities
# ----------------------------
def t(key, user_id=None, **kwargs):
    # translation helper: t("welcome", user_id)
    lang = "ru"
    if user_id:
        try:
            lang = get_user_language(user_id)
        except Exception:
            lang = "ru"
    txt = TEXT.get(key, {}).get(lang, "")
    if kwargs:
        return txt.format(**kwargs)
    return txt

async def safe_send(user_id: int, text: str, reply_markup=None, parse_mode=None):
    try:
        return await bot.send_message(user_id, text, reply_markup=reply_markup, parse_mode=parse_mode)
    except Exception as e:
        logger.warning("Failed to send to %s: %s", user_id, e)
        return None

def make_lang_keyboard():
    kb = InlineKeyboardMarkup(row_width=2)
    kb.add(InlineKeyboardButton("🇷🇺 Русский", callback_data="lang:ru"),
           InlineKeyboardButton("🇬🇧 English", callback_data="lang:en"))
    return kb

def make_onboarding_kb(user_id, personal_link):
    kb = InlineKeyboardMarkup(row_width=1)
    kb.add(InlineKeyboardButton("🔗 Открыть / Копировать ссылку", url=personal_link))
    kb.add(InlineKeyboardButton("🔁 Поделиться ссылкой", callback_data=f"share:{user_id}"))
    kb.add(InlineKeyboardButton("📋 Меню", callback_data="menu:open"))
    return kb

def make_receiver_kb(message_id, user_id):
    kb = InlineKeyboardMarkup(row_width=2)
    kb.add(InlineKeyboardButton("💬 Ответить", callback_data=f"reply:{message_id}"),
           InlineKeyboardButton(f"⭐ Раскрыть ({REVEAL_PRICE_STARS}★)", callback_data=f"reveal:{message_id}"))
    kb.add(InlineKeyboardButton("🚨 Пожаловаться", callback_data=f"report:{message_id}"))
    # Also add a small "reply back" when sender sees reply
    return kb

def make_menu_kb(user_id):
    kb = InlineKeyboardMarkup(row_width=1)
    kb.add(InlineKeyboardButton(t("menu_text", user_id), callback_data="menu:open"))
    return kb

# ----------------------------
# Handlers
# ----------------------------
@dp.message(Command(commands=["start"]))
async def cmd_start(message: types.Message):
    args = message.get_args()
    uid = message.from_user.id
    ensure_user(uid, message.from_user.username, message.from_user.first_name)
    lang = get_user_language(uid)

    # If user has no language explicitly set (default exists but check), present language selection on first visit
    if not args and (not message.from_user.username and get_user_language(uid) is None):
        # fallback, but normally language default is ru in DB
        pass

    # If no args => onboarding / show personal link
    if not args:
        # If user has not set language yet (or wants), show language choice first if language not set in DB
        lang_row = db_execute("SELECT language FROM users WHERE user_id = ?", (uid,), fetchone=True)
        lang_in_db = lang_row[0] if lang_row else None
        if not lang_in_db:
            await message.answer(t("welcome"), reply_markup=make_lang_keyboard())
            return
        me = await bot.get_me()
        personal_link = f"https://t.me/{me.username}?start={uid}"
        await message.answer(t("start_onboarding", uid, link=personal_link), reply_markup=make_onboarding_kb(uid, personal_link))
        return

    # args present -> deep link
    try:
        target_id = int(args)
    except ValueError:
        await message.answer(t("invalid_link", uid))
        return

    # record visit
    create_visit(uid, target_id)

    if target_id == uid:
        await message.answer(t("start_onboarding", uid, link=f"https://t.me/{BOT_USERNAME}?start={uid}"))
        return

    # Check if sender is blocked
    blocked, permanent = is_blocked(uid)
    if blocked:
        if permanent:
            await message.answer(t("you_banned", uid))
            return
        else:
            await message.answer(t("you_blocked", uid))
            # allow appeal option
            kb = InlineKeyboardMarkup().add(InlineKeyboardButton("Подать апелляцию / Appeal", callback_data="appeal:start"))
            await message.answer("", reply_markup=kb)
            return

    # Set pending state: user will write message to target
    pending_send_for_target[uid] = target_id
    await message.answer(t("enter_message_prompt", uid))

@dp.callback_query()
async def callbacks_handler(callback: types.CallbackQuery):
    data = callback.data or ""
    uid = callback.from_user.id

    # LANGUAGE selection
    if data.startswith("lang:"):
        lang = data.split(":", 1)[1]
        ensure_user(uid, callback.from_user.username, callback.from_user.first_name)
        set_user_language(uid, lang)
        await callback.message.answer(t("lang_changed", uid))
        await callback.message.delete()
        # After selecting language show onboarding link
        me = await bot.get_me()
        personal_link = f"https://t.me/{me.username}?start={uid}"
        await callback.message.answer(t("start_onboarding", uid, link=personal_link), reply_markup=make_onboarding_kb(uid, personal_link))
        await callback.answer()
        return

    # Share link
    if data.startswith("share:"):
        try:
            target_uid = int(data.split(":", 1)[1])
        except Exception:
            await callback.answer("Error", show_alert=True)
            return
        me = await bot.get_me()
        link = f"https://t.me/{me.username}?start={target_uid}"
        await bot.send_message(callback.from_user.id, f"Скопируйте/передайте ссылку:\n\n{link}")
        await callback.answer()
        return

    # Menu open or options
    if data == "menu:open":
        kb = InlineKeyboardMarkup(row_width=1)
        kb.add(InlineKeyboardButton("📊 Статистика / Statistics", callback_data="menu:stats"),
               InlineKeyboardButton("💡 Предложить идею / Idea", callback_data="menu:idea"),
               InlineKeyboardButton("🛠 Техподдержка / Support", callback_data="menu:support"),
               InlineKeyboardButton("⚙️ Настройки / Settings", callback_data="menu:settings"))
        await bot.send_message(callback.from_user.id, t("menu_text", callback.from_user.id), reply_markup=kb)
        await callback.answer()
        return

    # Menu stats
    if data == "menu:stats":
        stats = get_stats(callback.from_user.id)
        await bot.send_message(callback.from_user.id, t("stats_text", callback.from_user.id,
                                                        m_today=stats["m_today"],
                                                        v_today=stats["v_today"],
                                                        m_total=stats["m_total"],
                                                        v_total=stats["v_total"],
                                                        unique=stats["unique"]))
        await callback.answer()
        return

    # Menu idea
    if data == "menu:idea":
        pending_idea_from_user[callback.from_user.id] = True
        await bot.send_message(callback.from_user.id, t("idea_prompt", callback.from_user.id))
        await callback.answer()
        return

    # Support
    if data == "menu:support":
        if SUPPORT_USERNAME:
            await bot.send_message(callback.from_user.id, f"Support: https://t.me/{SUPPORT_USERNAME}")
        else:
            await bot.send_message(callback.from_user.id, "Support not set")
        await callback.answer()
        return

    # Settings -> language
    if data == "menu:settings":
        kb = InlineKeyboardMarkup(row_width=2)
        kb.add(InlineKeyboardButton("🇷🇺 Русский", callback_data="lang:ru"),
               InlineKeyboardButton("🇬🇧 English", callback_data="lang:en"))
        await bot.send_message(callback.from_user.id, t("choose_lang", callback.from_user.id), reply_markup=kb)
        await callback.answer()
        return

    # Reply to message (receiver wants to reply to sender)
    if data.startswith("reply:"):
        try:
            mid = int(data.split(":", 1)[1])
        except:
            await callback.answer("Error", show_alert=True)
            return
        # mark pending reply
        pending_reply_for_message[callback.from_user.id] = mid
        await bot.send_message(callback.from_user.id, t("reply_request", callback.from_user.id))
        await callback.answer()
        return

    # When sender sees "reply_to_sender" button -> they can reply back
    if data.startswith("reply_to_sender:"):
        try:
            mid = int(data.split(":", 1)[1])
        except:
            await callback.answer("Error", show_alert=True)
            return
        pending_reply_for_message[callback.from_user.id] = mid
        await bot.send_message(callback.from_user.id, t("reply_request", callback.from_user.id))
        await callback.answer()
        return

    # Reveal simulation
    if data.startswith("reveal:"):
        mid = int(data.split(":",1)[1])
        await bot.send_message(callback.from_user.id, t("reveal_prompt", callback.from_user.id, price=REVEAL_PRICE_STARS))
        await callback.answer()
        return

    # Report flow: ask reason
    if data.startswith("report:"):
        mid = int(data.split(":",1)[1])
        pending_reply_for_message[callback.from_user.id] = f"report::{mid}"
        await bot.send_message(callback.from_user.id, t("report_reason_prompt", callback.from_user.id))
        await callback.answer()
        return

    # Appeal start from blocked user
    if data == "appeal:start":
        # allow only if blocked and not appealed before
        blocked, permanent = is_blocked(callback.from_user.id)
        if not blocked:
            await bot.send_message(callback.from_user.id, "You are not blocked / Вы не заблокированы.")
            await callback.answer()
            return
        if permanent:
            await bot.send_message(callback.from_user.id, t("you_banned", callback.from_user.id))
            await callback.answer()
            return
        # check if already appealed using 'appealed' flag on user
        row = db_execute("SELECT appealed FROM users WHERE user_id = ?", (callback.from_user.id,), fetchone=True)
        if row and row[0]:
            await bot.send_message(callback.from_user.id, "Вы уже подавали апелляцию / You already appealed.")
            await callback.answer()
            return
        pending_appeal_from_user[callback.from_user.id] = True
        await bot.send_message(callback.from_user.id, t("appeal_prompt", callback.from_user.id))
        await callback.answer()
        return

    # Admin actions: block/unblock/ban via callback_data like admin:block:12345
    if data.startswith("admin:block:") or data.startswith("admin:unblock:") or data.startswith("admin:ban:") or data.startswith("admin:process_appeal:"):
        # only admin allowed
        if callback.from_user.id != ADMIN_ID:
            await callback.answer("Only admin", show_alert=True)
            return
        parts = data.split(":")
        action = parts[1]
        target = int(parts[2])
        if action == "block":
            block_user(target, reason="Blocked by admin", permanent=0)
            await bot.send_message(ADMIN_ID, t("block_confirm_admin", ADMIN_ID, uid=target))
            await callback.answer("User blocked")
            return
        if action == "unblock":
            unblock_user(target)
            await bot.send_message(ADMIN_ID, t("unblock_confirm_admin", ADMIN_ID, uid=target))
            await callback.answer("User unblocked")
            return
        if action == "ban":
            block_user(target, reason="Banned by admin", permanent=1)
            await bot.send_message(ADMIN_ID, t("ban_confirm_admin", ADMIN_ID, uid=target))
            await callback.answer("User banned permanently")
            return
        if action == "process_appeal":
            # parts: admin:process_appeal:<appeal_id>:<decision> where decision is accept/reject
            appeal_id = int(parts[2])
            decision = parts[3] if len(parts) > 3 else "reject"
            # left simple: mark processed
            mark_appeal_processed(appeal_id)
            await bot.send_message(ADMIN_ID, f"Appeal {appeal_id} processed: {decision}")
            await callback.answer("Appeal processed")
            return

    await callback.answer()  # fallback

@dp.message()
async def on_message(message: types.Message):
    uid = message.from_user.id
    text = (message.text or "").strip()
    ensure_user(uid, message.from_user.username, message.from_user.first_name)

    # If pending idea
    if pending_idea_from_user.pop(uid, None):
        save_idea(uid, text)
        # notify admin
        uname = f"@{message.from_user.username}" if message.from_user.username else "(no username)"
        await safe_send(ADMIN_ID, f"💡 Idea from {uname} (ID {uid}):\n\n{text}")
        await message.answer(t("idea_thanks", uid))
        return

    # If user is entering an appeal
    if pending_appeal_from_user.pop(uid, None):
        # save appeal and notify admin
        save_id = save_appeal(uid, text)
        # set appealed flag
        db_execute("UPDATE users SET appealed = 1 WHERE user_id = ?", (uid,), commit=True)
        await safe_send(ADMIN_ID, t("appeal_admin_notify", ADMIN_ID, uid=uid, username=f"@{message.from_user.username}" if message.from_user.username else "(no username)", appeal=text))
        await message.answer(t("appeal_received_user", uid))
        return

    # If user is replying to a message (pending_reply_for_message)
    pending = pending_reply_for_message.pop(uid, None)
    if pending:
        # report flow
        if isinstance(pending, str) and pending.startswith("report::"):
            mid = int(pending.split("::",1)[1])
            add_report(mid, uid, text)
            await message.answer(t("report_received_user", uid))
            # notify admin about this single report
            dbm = get_message(mid)
            sender_id = dbm[1] if dbm else None
            preview = (dbm[5][:200] + "...") if dbm and len(dbm[5])>200 else (dbm[5] if dbm else "")
            uname = f"@{dbm[2]}" if dbm and dbm[2] else "(no username)"
            await safe_send(ADMIN_ID, t("report_admin_notify", ADMIN_ID, mid=mid, sender_id=sender_id, username=uname, preview=preview, reason=text, reporter=uid))
            # Now check unique reports against sender and if >=3 notify admin with block buttons
            if sender_id:
                unique_count = count_unique_reports_against_sender(sender_id)
                if unique_count >= 3:
                    rows = get_reports_for_sender(sender_id)
                    msg = f"🚨 User {sender_id} has {unique_count} unique reports. Reports:\n"
                    for r in rows:
                        rid, rmid, reporter_id, reason, created_at, mtext = r
                        msg += f"- Report #{rid} on message #{rmid} by {reporter_id}: {reason}\n  msg: {mtext[:120]}\n"
                    # admin buttons: block/unblock/ban
                    kb = InlineKeyboardMarkup(row_width=1)
                    kb.add(InlineKeyboardButton("🔒 Block user", callback_data=f"admin:block:{sender_id}"),
                           InlineKeyboardButton("🔓 Unblock user", callback_data=f"admin:unblock:{sender_id}"),
                           InlineKeyboardButton("⛔ Ban permanently", callback_data=f"admin:ban:{sender_id}"))
                    await safe_send(ADMIN_ID, msg, reply_markup=kb)
            return

        # normal reply flow
        try:
            mid = int(pending)
            dbm = get_message(mid)
            if not dbm:
                await message.answer("Original message not found.")
                return
            sender_id = dbm[1]
            # send anonymous reply to original sender
            await safe_send(sender_id, t("reply_notification_to_sender", sender_id, reply=text),
                            reply_markup=InlineKeyboardMarkup().add(InlineKeyboardButton("💬 Reply", callback_data=f"reply_to_sender:{mid}")))
            await message.answer(t("message_sent_confirm", uid))
        except Exception as e:
            logger.exception("Error in reply flow: %s", e)
            await message.answer("Error sending reply.")
        return

    # If user is currently composing anonymous message to someone (came via link)
    if uid in pending_send_for_target:
        target_id = pending_send_for_target.pop(uid)
        # check block
        blocked, permanent = is_blocked(uid)
        if blocked:
            if permanent:
                await message.answer(t("you_banned", uid))
                return
            else:
                await message.answer(t("you_blocked", uid))
                return
        sender_username = message.from_user.username or None
        sender_first_name = message.from_user.first_name or ""
        mid = create_message(uid, sender_username, sender_first_name, target_id, text)
        await message.answer(t("message_sent_confirm", uid))
        # notify receiver
        kb = make_receiver_kb(mid, target_id)
        await safe_send(target_id, t("new_msg_to_receiver", target_id, text=text), reply_markup=kb)
        return

    # default fallback
    await message.answer("Use /start to get your link or open menu.")

# ----------------------------
# Startup
# ----------------------------
if __name__ == "__main__":
    init_db()
    logger.info("Bot starting...")
    dp.run_polling(bot)
