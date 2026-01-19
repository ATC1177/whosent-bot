#!/usr/bin/env python3
# -*- coding: utf-8 -*-
# Whosent bot with simple i18n (ru/en) — aiogram v2 polling

import os
import time
import logging
import sqlite3
from datetime import datetime, timezone

from aiogram import Bot, Dispatcher, executor, types
from aiogram.utils.exceptions import BotBlocked, ChatNotFound, UserDeactivated
from dotenv import load_dotenv

load_dotenv()

# ---------------- CONFIG ----------------
BOT_TOKEN = os.getenv("BOT_TOKEN")
ADMIN_ID = int(os.getenv("ADMIN_ID") or 0)
ADMIN_USERNAME = os.getenv("ADMIN_USERNAME") or ""
BOT_USERNAME = os.getenv("BOT_USERNAME") or ""
SUPPORT_USERNAME = os.getenv("SUPPORT_USERNAME") or ""
REVEAL_PRICE_STARS = int(os.getenv("REVEAL_PRICE_STARS") or 25)
DB_PATH = os.getenv("DB_PATH") or "anon_bot.db"

if not BOT_TOKEN:
    raise SystemExit("BOT_TOKEN not set")

# ---------------- logging & bot ----------------
logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
logger = logging.getLogger(__name__)

bot = Bot(token=BOT_TOKEN)
dp = Dispatcher(bot)

# ---------------- i18n texts ----------------
TEXTS = {
    "ru": {
        "start_main": "Начните получать анонимные сообщения прямо сейчас.\n\n"
                      "Ваша персональная ссылка — поделитесь ею в профиле Telegram, Instagram, TikTok, в сторис и т.д.\n\n"
                      "Ваша ссылка:\n{link}\n\n"
                      "Разместите ссылку в профиле — люди смогут писать вам анонимно.",
        "prompt_write_msg": "✉️ Напишите анонимное сообщение для этого пользователя. Ваш username не будет показан (пока получатель не раскроет).",
        "invalid_link": "Неправильная ссылка.",
        "own_link": "Это ваша собственная ссылка — напишите что-нибудь для теста или поделитесь ссылкой.",
        "sent_ok": "✅ Сообщение отправлено анонимно. Если получатель ответит, ответ придёт через бота.",
        "new_msg_notify": "📩 У вас новое анонимное сообщение:\n\n{text}\n\nЧтобы раскрыть отправителя — нажмите «⭐ Раскрыть ({price}★)».\nВы также можете ответить через бота.",
        "menu_title": "Меню:",
        "menu_stats": "📊 Статистика",
        "menu_idea": "💡 Предложить идею",
        "menu_support": "🛠 Техподдержка",
        "idea_prompt": "Опишите вашу идею для бота (коротко):",
        "idea_sent": "✅ Идея отправлена администратору. Спасибо!",
        "support_text": "Техподдержка: https://t.me/{support}\n\nНапишите этому пользователю в случае проблем.",
        "reply_prompt": "Напишите ответ — он будет отправлен отправителю анонимно:",
        "reveal_confirm": "Вы собираетесь раскрыть отправителя (стоимость {price}★).\n\nВ демо-версии оплата симулируется. В проде здесь нужно подключить реальную оплату.",
        "revealed_username": "👤 Отправитель раскрыт:\n\nИмя: {name}\nUsername: @{username}\n\nНажмите, чтобы открыть профиль:",
        "revealed_hidden": "Отправитель раскрыт (username скрыт).",
        "report_prompt": "Опишите причину жалобы (коротко):",
        "report_ok": "Спасибо — жалоба принята, администратор получит уведомление.",
        "lang_choose": "Выберите язык / Choose language:",
        "lang_set": "Язык установлен: {lang}",
        "default_reply": "Я — бот для анонимных сообщений. Чтобы получить свою ссылку — отправь /start\n\nИли нажми '📋 Меню'."
    },
    "en": {
        "start_main": "Start receiving anonymous messages right now.\n\n"
                      "Your personal link — share it in your Telegram, Instagram, TikTok profile, Stories, etc.\n\n"
                      "Your link:\n{link}\n\n"
                      "Place the link in your profile so people can write to you anonymously.",
        "prompt_write_msg": "✉️ Write an anonymous message to this user. Your username will not be shown (unless revealed).",
        "invalid_link": "Invalid link.",
        "own_link": "This is your own link — write something for testing or share the link.",
        "sent_ok": "✅ Message sent anonymously. If the recipient replies, the reply will arrive through the bot.",
        "new_msg_notify": "📩 You have a new anonymous message:\n\n{text}\n\nTo reveal the sender — press «⭐ Reveal ({price}★)». You can also reply via the bot.",
        "menu_title": "Menu:",
        "menu_stats": "📊 Statistics",
        "menu_idea": "💡 Suggest an idea",
        "menu_support": "🛠 Support",
        "idea_prompt": "Describe your idea for the bot (short):",
        "idea_sent": "✅ Idea sent to admin. Thanks!",
        "support_text": "Support: https://t.me/{support}\n\nContact this person in case of issues.",
        "reply_prompt": "Write your reply — it will be sent to the sender anonymously:",
        "reveal_confirm": "You are about to reveal the sender (cost {price}★).\n\nIn demo this is simulated. In production you need to connect real payment.",
        "revealed_username": "👤 Sender revealed:\n\nName: {name}\nUsername: @{username}\n\nClick to open profile:",
        "revealed_hidden": "Sender revealed (username hidden).",
        "report_prompt": "Describe the reason for the report (short):",
        "report_ok": "Thanks — report accepted, admin will be notified.",
        "lang_choose": "Выберите язык / Choose language:",
        "lang_set": "Language set to: {lang}",
        "default_reply": "I am an anonymous messaging bot. To get your link — send /start\n\nOr press '📋 Menu'."
    }
}

LANG_NAMES = {"ru": "Русский", "en": "English"}

# ---------------- DB ----------------
def init_db():
    con = sqlite3.connect(DB_PATH)
    cur = con.cursor()
    cur.execute("""
    CREATE TABLE IF NOT EXISTS users (
        user_id INTEGER PRIMARY KEY,
        username TEXT,
        first_name TEXT,
        messages_received INTEGER DEFAULT 0,
        created_at INTEGER
    );
    """)
    # if lang column missing, add it
    cur.execute("PRAGMA table_info(users);")
    cols = [r[1] for r in cur.fetchall()]
    if "lang" not in cols:
        try:
            cur.execute("ALTER TABLE users ADD COLUMN lang TEXT DEFAULT 'ru';")
        except Exception:
            # sqlite on some versions may not allow; ignore if fails
            pass
    # other tables
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

# ---------------- DB helpers ----------------
def ensure_user_record(user_id: int, username: str = None, first_name: str = None):
    now = int(time.time())
    row = db_execute("SELECT user_id FROM users WHERE user_id = ?", (user_id,), fetchone=True)
    if not row:
        db_execute("INSERT INTO users (user_id, username, first_name, messages_received, created_at, lang) VALUES (?, ?, ?, 0, ?, ?)",
                   (user_id, username, first_name or "", now, "ru"), commit=True)
    else:
        db_execute("UPDATE users SET username = ?, first_name = ? WHERE user_id = ?",
                   (username, first_name or "", user_id), commit=True)

def set_user_lang(user_id: int, lang: str):
    if lang not in TEXTS:
        return
    db_execute("UPDATE users SET lang = ? WHERE user_id = ?", (lang, user_id), commit=True)

def get_user_lang(user_id: int):
    r = db_execute("SELECT lang FROM users WHERE user_id = ?", (user_id,), fetchone=True)
    if r and r[0]:
        return r[0]
    return "ru"

# ---------------- small i18n helper ----------------
def t(user_id: int, key: str, **kwargs):
    lang = get_user_lang(user_id)
    txt = TEXTS.get(lang, TEXTS["ru"]).get(key, "")
    if kwargs:
        try:
            return txt.format(**kwargs)
        except Exception:
            return txt
    return txt

# ---------------- utilities ----------------
def safe_send(user_id: int, text: str, reply_markup=None, parse_mode=None):
    try:
        return bot.send_message(user_id, text, reply_markup=reply_markup, parse_mode=parse_mode)
    except (BotBlocked, ChatNotFound, UserDeactivated) as e:
        logger.warning(f"Failed to send to {user_id}: {e}")
        return None
    except Exception as e:
        logger.exception(f"Error sending to {user_id}: {e}")
        return None

def make_onboarding_keyboard(user_id: int, personal_link: str):
    kb = types.InlineKeyboardMarkup(row_width=1)
    kb.add(types.InlineKeyboardButton("🔗 " + ("Скопировать ссылку" if get_user_lang(user_id)=="ru" else "Copy link"), url=personal_link))
    kb.add(types.InlineKeyboardButton("🔁 " + ("Поделиться" if get_user_lang(user_id)=="ru" else "Share"), callback_data=f"share:{user_id}"))
    kb.add(types.InlineKeyboardButton("📋 " + ("Меню" if get_user_lang(user_id)=="ru" else "Menu"), callback_data="menu:open"))
    return kb

def make_receiver_keyboard(message_id, user_id_for_lang=None):
    kb = types.InlineKeyboardMarkup(row_width=2)
    kb.add(
        types.InlineKeyboardButton(("💬 Ответить анонимно" if (get_user_lang(user_id_for_lang)=="ru") else "💬 Reply anonymously"), callback_data=f"reply:{message_id}"),
        types.InlineKeyboardButton(f"⭐ {('Раскрыть' if get_user_lang(user_id_for_lang)=='ru' else 'Reveal')} ({REVEAL_PRICE_STARS}★)", callback_data=f"reveal:{message_id}")
    )
    kb.add(types.InlineKeyboardButton("🚫 " + ("Пожаловаться" if get_user_lang(user_id_for_lang)=="ru" else "Report"), callback_data=f"report:{message_id}"))
    return kb

# ---------------- message DB helpers (same as before) ----------------
def create_visit(visitor_id: int, target_id: int):
    ts = int(time.time())
    db_execute("INSERT INTO visits (visitor_id, target_id, created_at) VALUES (?, ?, ?)", (visitor_id, target_id, ts), commit=True)

def create_message_record(sender_id, sender_username, sender_first_name, receiver_id, text):
    ts = int(time.time())
    db_execute("INSERT INTO messages (sender_id, sender_username, sender_first_name, receiver_id, text, created_at) VALUES (?, ?, ?, ?, ?, ?)",
               (sender_id, sender_username, sender_first_name, receiver_id, text, ts), commit=True)
    ensure_user_record(receiver_id)
    db_execute("UPDATE users SET messages_received = messages_received + 1 WHERE user_id = ?", (receiver_id,), commit=True)
    res = db_execute("SELECT last_insert_rowid()", fetchone=True)
    return res[0]

def get_message_by_id(message_id):
    return db_execute("SELECT id, sender_id, sender_username, sender_first_name, receiver_id, text, revealed, created_at FROM messages WHERE id = ?", (message_id,), fetchone=True)

def set_message_revealed(message_id):
    db_execute("UPDATE messages SET revealed = 1 WHERE id = ?", (message_id,), commit=True)

def save_report(message_id, reporter_id, reason):
    ts = int(time.time())
    db_execute("INSERT INTO reports (message_id, reporter_id, reason, created_at) VALUES (?, ?, ?, ?)", (message_id, reporter_id, reason, ts), commit=True)

def save_idea(from_user, text):
    ts = int(time.time())
    db_execute("INSERT INTO ideas (from_user, text, created_at) VALUES (?, ?, ?)", (from_user, text, ts), commit=True)

# ---------------- stats helpers ----------------
def _start_of_today_ts():
    now = datetime.now(timezone.utc)
    start = datetime(year=now.year, month=now.month, day=now.day, tzinfo=timezone.utc)
    return int(start.timestamp())

def get_stats_for_user(user_id: int):
    start_today = _start_of_today_ts()
    messages_today = db_execute("SELECT COUNT(*) FROM messages WHERE receiver_id = ? AND created_at >= ?", (user_id, start_today), fetchone=True)[0]
    messages_total = db_execute("SELECT COUNT(*) FROM messages WHERE receiver_id = ?", (user_id,), fetchone=True)[0]
    visits_today = db_execute("SELECT COUNT(*) FROM visits WHERE target_id = ? AND created_at >= ?", (user_id, start_today), fetchone=True)[0]
    visits_total = db_execute("SELECT COUNT(*) FROM visits WHERE target_id = ?", (user_id,), fetchone=True)[0]
    unique_senders = db_execute("SELECT COUNT(DISTINCT sender_id) FROM messages WHERE receiver_id = ?", (user_id,), fetchone=True)[0]
    return {
        "messages_today": messages_today,
        "messages_total": messages_total,
        "visits_today": visits_today,
        "visits_total": visits_total,
        "unique_senders": unique_senders
    }

# ---------------- Handlers ----------------
@dp.message_handler(commands=["start"])
def cmd_start(message: types.Message):
    args = message.get_args()
    uid = message.from_user.id
    ensure_user_record(uid, message.from_user.username, message.from_user.first_name)
    me = bot.get_me()
    bot_username = me.username or BOT_USERNAME
    personal_link = f"https://t.me/{bot_username}?start={uid}"

    if not args:
        kb = make_onboarding_keyboard(uid, personal_link)
        message.answer(t(uid, "start_main", link=personal_link), reply_markup=kb)
        return

    try:
        target_id = int(args)
    except ValueError:
        message.answer(t(uid, "invalid_link"))
        return

    create_visit(uid, target_id)
    if target_id == uid:
        message.answer(t(uid, "own_link"))
        return

    # prepare to send anonymous
    # store pending target
    # we'll accept next text message as content
    # keep state in memory
    global pending_send_for_target
    pending_send_for_target[uid] = target_id
    message.answer(t(uid, "prompt_write_msg"))

@dp.message_handler(commands=["menu"])
def cmd_menu(message: types.Message):
    uid = message.from_user.id
    kb = types.InlineKeyboardMarkup(row_width=1)
    kb.add(types.InlineKeyboardButton(t(uid, "menu_stats"), callback_data="menu:stats"))
    kb.add(types.InlineKeyboardButton(t(uid, "menu_idea"), callback_data="menu:idea"))
    kb.add(types.InlineKeyboardButton(t(uid, "menu_support"), callback_data="menu:support"))
    kb.add(types.InlineKeyboardButton(("🌐 " + ("English" if get_user_lang(uid)=="ru" else "Русский")), callback_data="menu:lang"))
    message.answer(t(uid, "menu_title"), reply_markup=kb)

@dp.message_handler(commands=["lang"])
def cmd_lang(message: types.Message):
    uid = message.from_user.id
    ensure_user_record(uid, message.from_user.username, message.from_user.first_name)
    kb = types.InlineKeyboardMarkup(row_width=2)
    kb.add(types.InlineKeyboardButton("Русский", callback_data="setlang:ru"),
           types.InlineKeyboardButton("English", callback_data="setlang:en"))
    message.answer(t(uid, "lang_choose"), reply_markup=kb)

@dp.callback_query_handler(lambda c: c.data and c.data.startswith("setlang:"))
def cb_setlang(call: types.CallbackQuery):
    uid = call.from_user.id
    lang = call.data.split(":", 1)[1]
    ensure_user_record(uid, call.from_user.username, call.from_user.first_name)
    set_user_lang(uid, lang)
    call.answer()
    call.message.edit_text(t(uid, "lang_set", lang=LANG_NAMES.get(lang, lang)))

@dp.callback_query_handler(lambda c: c.data and c.data.startswith("menu:"))
def cb_menu(call: types.CallbackQuery):
    uid = call.from_user.id
    cmd = call.data.split(":", 1)[1]
    if cmd == "stats":
        stats = get_stats_for_user(uid)
        text = (
            f"📈 {t(uid, 'menu_stats')}\n\n"
            f"За сегодня:\n• {t(uid,'menu_stats')}: {stats['messages_today']}\n"
        )
        bot.send_message(uid, text)
        call.answer()
    elif cmd == "idea":
        pending_idea_from_user[uid] = True
        bot.send_message(uid, t(uid, "idea_prompt"))
        call.answer()
    elif cmd == "support":
        if SUPPORT_USERNAME:
            bot.send_message(uid, t(uid, "support_text", support=SUPPORT_USERNAME))
        elif ADMIN_ID:
            bot.send_message(uid, f"Support: {ADMIN_ID}")
        else:
            bot.send_message(uid, t(uid, "default_reply"))
        call.answer()
    elif cmd == "lang":
        # open language picker
        kb = types.InlineKeyboardMarkup(row_width=2)
        kb.add(types.InlineKeyboardButton("Русский", callback_data="setlang:ru"),
               types.InlineKeyboardButton("English", callback_data="setlang:en"))
        bot.send_message(uid, t(uid, "lang_choose"), reply_markup=kb)
        call.answer()

@dp.message_handler(content_types=types.ContentTypes.TEXT)
def text_handler(message: types.Message):
    uid = message.from_user.id
    text = message.text.strip()

    # idea flow
    if pending_idea_from_user.get(uid):
        pending_idea_from_user.pop(uid, None)
        save_idea(uid, text)
        uname = f"@{message.from_user.username}" if message.from_user.username else "(username отсутствует)"
        admin_msg = (f"💡 Новая идея\n\nПользователь: {uname}\nID: {uid}\n\n{(text[:1000]+'...') if len(text)>1000 else text}")
        safe_send(ADMIN_ID, admin_msg)
        message.answer(t(uid, "idea_sent"))
        return

    # reply flow if waiting
    if uid in pending_reply_for_message:
        message_id = pending_reply_for_message.pop(uid)
        db_msg = get_message_by_id(message_id)
        if not db_msg:
            message.answer(t(uid, "default_reply"))
            return
        sender_id = db_msg[1]
        try:
            bot.send_message(sender_id,
                             f"📩 You have a reply (via bot):\n\n{text}\n\n",
                             reply_markup=types.InlineKeyboardMarkup().add(
                                 types.InlineKeyboardButton("💬 Reply in bot", callback_data=f"reply_to_sender:{message_id}")
                             ))
            message.answer("✅")
        except Exception:
            message.answer("Failed to send reply.")
        return

    # send anonymous message flow (user came by link earlier)
    if uid in pending_send_for_target:
        target_id = pending_send_for_target.pop(uid)
        sender_username = message.from_user.username or None
        sender_first_name = message.from_user.first_name or ""
        mid = create_message_record(uid, sender_username, sender_first_name, target_id, text)
        message.answer(t(uid, "sent_ok"))
        human_text = t(target_id, "new_msg_notify", text=text, price=REVEAL_PRICE_STARS)
        kb = make_receiver_keyboard(mid, user_id_for_lang=target_id)
        sent = safe_send(target_id, human_text, reply_markup=kb)
        if not sent:
            logger.info(f"Message #{mid} saved but deliver failed.")
        return

    # default
    message.answer(t(uid, "default_reply"))

# callback handlers for reply/reveal/report/share (basic translations)
@dp.callback_query_handler(lambda c: c.data and c.data.startswith("share:"))
def cb_share(call: types.CallbackQuery):
    try:
        target_uid = int(call.data.split(":", 1)[1])
    except:
        call.answer("Error", show_alert=True)
        return
    me = bot.get_me()
    link = f"https://t.me/{me.username}?start={target_uid}"
    bot.send_message(call.from_user.id, (f"Скопируйте ссылку:\n{link}" if get_user_lang(call.from_user.id)=="ru" else f"Copy link:\n{link}"))
    call.answer()

@dp.callback_query_handler(lambda c: c.data and c.data.startswith("reply:"))
def cb_reply(call: types.CallbackQuery):
    message_id = int(call.data.split(":", 1)[1])
    db_msg = get_message_by_id(message_id)
    if not db_msg:
        call.answer(get_user_lang(call.from_user.id)=="ru" and "Сообщение не найдено." or "Message not found.", show_alert=True)
        return
    pending_reply_for_message[call.from_user.id] = message_id
    call.answer()
    bot.send_message(call.from_user.id, t(call.from_user.id, "reply_prompt"))

@dp.callback_query_handler(lambda c: c.data and c.data.startswith("reveal:"))
def cb_reveal(call: types.CallbackQuery):
    message_id = int(call.data.split(":", 1)[1])
    db_msg = get_message_by_id(message_id)
    if not db_msg:
        call.answer(get_user_lang(call.from_user.id)=="ru" and "Сообщение не найдено." or "Message not found.", show_alert=True)
        return
    call.answer()
    confirm_kb = types.InlineKeyboardMarkup().add(
        types.InlineKeyboardButton(f"{('Оплатить' if get_user_lang(call.from_user.id)=='ru' else 'Pay')} {REVEAL_PRICE_STARS}★ (симуляция)", callback_data=f"confirm_reveal:{message_id}")
    )
    bot.send_message(call.from_user.id, t(call.from_user.id, "reveal_confirm", price=REVEAL_PRICE_STARS), reply_markup=confirm_kb)

@dp.callback_query_handler(lambda c: c.data and c.data.startswith("confirm_reveal:"))
def cb_confirm_reveal(call: types.CallbackQuery):
    message_id = int(call.data.split(":", 1)[1])
    db_msg = get_message_by_id(message_id)
    if not db_msg:
        call.answer(get_user_lang(call.from_user.id)=="ru" and "Сообщение не найдено." or "Message not found.", show_alert=True)
        return
    sender_username = db_msg[2]
    sender_first_name = db_msg[3]
    set_message_revealed(message_id)
    if sender_username:
        call.answer(get_user_lang(call.from_user.id)=="ru" and "Отправитель раскрыт!" or "Sender revealed!", show_alert=True)
        bot.send_message(call.from_user.id, t(call.from_user.id, "revealed_username", name=sender_first_name or "-", username=sender_username),
                         reply_markup=types.InlineKeyboardMarkup().add(types.InlineKeyboardButton("Open profile", url=f"https://t.me/{sender_username}")))
    else:
        call.answer()
        bot.send_message(call.from_user.id, t(call.from_user.id, "revealed_hidden"))

@dp.callback_query_handler(lambda c: c.data and c.data.startswith("report:"))
def cb_report(call: types.CallbackQuery):
    message_id = int(call.data.split(":", 1)[1])
    pending_reply_for_message[call.from_user.id] = f"report::{message_id}"
    call.answer()
    bot.send_message(call.from_user.id, t(call.from_user.id, "report_prompt"))

@dp.message_handler(lambda m: isinstance(pending_reply_for_message.get(m.from_user.id, None), str) and pending_reply_for_message[m.from_user.id].startswith("report::"), content_types=types.ContentTypes.TEXT)
def handle_report_text(message: types.Message):
    tag = pending_reply_for_message.pop(message.from_user.id)
    _, mid_str = tag.split("::", 1)
    message_id = int(mid_str)
    reason = message.text.strip()
    save_report(message_id, message.from_user.id, reason)
    db_msg = get_message_by_id(message_id)
    if db_msg and ADMIN_ID:
        sender_id = db_msg[1]
        sender_username = db_msg[2] or "(скрыт)"
        text_preview = db_msg[5][:300]
        report_text = (f"🚨 Жалоба на сообщение #{message_id}\nОтправитель (ID): {sender_id}\nUsername: {sender_username}\nТекст: {text_preview}\nПричина: {reason}\nОтправитель жалобы: {message.from_user.id}")
        safe_send(ADMIN_ID, report_text)
    message.answer(t(message.from_user.id, "report_ok"))

# ---------------- Admin commands ----------------
@dp.message_handler(commands=["stats"])
def cmd_stats(message: types.Message):
    if message.from_user.id != ADMIN_ID:
        message.answer("Only admin")
        return
    total = db_execute("SELECT COUNT(*) FROM messages", fetchone=True)[0]
    unrevealed = db_execute("SELECT COUNT(*) FROM messages WHERE revealed = 0", fetchone=True)[0]
    message.answer(f"Total messages: {total}\nUnrevealed: {unrevealed}")

@dp.message_handler(commands=["admin_ideas"])
def cmd_admin_ideas(message: types.Message):
    if message.from_user.id != ADMIN_ID:
        message.answer("Only admin")
        return
    rows = db_execute("SELECT id, from_user, text, created_at FROM ideas ORDER BY created_at DESC LIMIT 50", fetchall=True) or []
    if not rows:
        message.answer("No ideas")
        return
    out = []
    for r in rows:
        when = datetime.fromtimestamp(r[3]).strftime("%Y-%m-%d %H:%M")
        out.append(f"#{r[0]} {when} — from {r[1]}\n{r[2][:200]}")
    message.answer("\n\n".join(out))

# ---------------- start ----------------
if __name__ == "__main__":
    init_db()
    logger.info("Starting Whosent bot...")
    executor.start_polling(dp, skip_updates=True)

