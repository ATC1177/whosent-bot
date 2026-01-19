#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Whosent bot — полный файл:
- Python + aiogram v2
- SQLite для хранения (anon messages, visits, reports, ideas, users)
- .env для конфигов (BOT_TOKEN и пр.)
- основная логика: /start, отправка анонимных сообщений, уведомления,
  меню (статистика, предложить идею, техподдержка), "Поделиться ссылкой",
  симуляция раскрытия отправителя за звёзды (реальную оплату можно подключить позже)
"""

import os
import logging
import sqlite3
import time
from datetime import datetime, timezone

from aiogram import Bot, Dispatcher, executor, types
from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton
from aiogram.utils.exceptions import BotBlocked, ChatNotFound, UserDeactivated
from dotenv import load_dotenv

load_dotenv()

# ----------------------------
# CONFIG (через .env)
# ----------------------------
BOT_TOKEN = os.getenv("BOT_TOKEN")  # ОБЯЗАТЕЛЬНО: положи сюда свой токен через .env
ADMIN_ID = int(os.getenv("ADMIN_ID", "6992171884"))          # по-умолчанию установлено из твоих данных
ADMIN_USERNAME = os.getenv("ADMIN_USERNAME", "ATC03")
BOT_USERNAME = os.getenv("BOT_USERNAME", "whosent_bot")
SUPPORT_USERNAME = os.getenv("SUPPORT_USERNAME", "metopo")
REVEAL_PRICE_STARS = int(os.getenv("REVEAL_PRICE_STARS", "25"))
DB_PATH = os.getenv("DB_PATH", "anon_bot.db")

# ----------------------------
# Логирование и бот
# ----------------------------
logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
logger = logging.getLogger(__name__)

if not BOT_TOKEN:
    logger.error("BOT_TOKEN не найден в окружении. Положи токен в .env и перезапусти.")
    raise SystemExit("BOT_TOKEN is required in .env")

bot = Bot(token=BOT_TOKEN)
dp = Dispatcher(bot)

# ----------------------------
# In-memory состояния (простая реализация)
# ----------------------------
pending_send_for_target = {}         # sender_id -> target_id
pending_reply_for_message = {}       # replier_id -> message_id
pending_idea_from_user = {}          # user_id -> True (user is entering idea text)

# ----------------------------
# База данных (SQLite)
# ----------------------------
def init_db():
    con = sqlite3.connect(DB_PATH)
    cur = con.cursor()
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
    CREATE TABLE IF NOT EXISTS users (
        user_id INTEGER PRIMARY KEY,
        username TEXT,
        first_name TEXT,
        messages_received INTEGER DEFAULT 0,
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

# ----------------------------
# DB helpers
# ----------------------------
def ensure_user_record(user_id: int, username: str = None, first_name: str = None):
    now = int(time.time())
    row = db_execute("SELECT user_id FROM users WHERE user_id = ?", (user_id,), fetchone=True)
    if not row:
        db_execute("INSERT INTO users (user_id, username, first_name, messages_received, created_at) VALUES (?, ?, ?, 0, ?)",
                   (user_id, username, first_name or "", now), commit=True)
    else:
        db_execute("UPDATE users SET username = ?, first_name = ? WHERE user_id = ?",
                   (username, first_name or "", user_id), commit=True)

def create_visit(visitor_id: int, target_id: int):
    ts = int(time.time())
    db_execute("INSERT INTO visits (visitor_id, target_id, created_at) VALUES (?, ?, ?)",
               (visitor_id, target_id, ts), commit=True)

def create_message_record(sender_id, sender_username, sender_first_name, receiver_id, text):
    ts = int(time.time())
    db_execute(
        "INSERT INTO messages (sender_id, sender_username, sender_first_name, receiver_id, text, created_at) VALUES (?, ?, ?, ?, ?, ?)",
        (sender_id, sender_username, sender_first_name, receiver_id, text, ts),
        commit=True
    )
    ensure_user_record(receiver_id)
    db_execute("UPDATE users SET messages_received = messages_received + 1 WHERE user_id = ?", (receiver_id,), commit=True)
    res = db_execute("SELECT last_insert_rowid()", fetchone=True)
    return res[0]

def get_message_by_id(message_id):
    return db_execute("SELECT id, sender_id, sender_username, sender_first_name, receiver_id, text, revealed, created_at FROM messages WHERE id = ?",
                      (message_id,), fetchone=True)

def set_message_revealed(message_id):
    db_execute("UPDATE messages SET revealed = 1 WHERE id = ?", (message_id,), commit=True)

def save_report(message_id, reporter_id, reason):
    ts = int(time.time())
    db_execute("INSERT INTO reports (message_id, reporter_id, reason, created_at) VALUES (?, ?, ?, ?)",
               (message_id, reporter_id, reason, ts), commit=True)

def save_idea(from_user, text):
    ts = int(time.time())
    db_execute("INSERT INTO ideas (from_user, text, created_at) VALUES (?, ?, ?)", (from_user, text, ts), commit=True)

# ----------------------------
# Статистика
# ----------------------------
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

# ----------------------------
# Утилиты отправки
# ----------------------------
def safe_send(user_id: int, text: str, reply_markup=None, parse_mode=None):
    try:
        return bot.send_message(user_id, text, reply_markup=reply_markup, parse_mode=parse_mode)
    except (BotBlocked, ChatNotFound, UserDeactivated) as e:
        logger.warning(f"Не удалось отправить сообщение {user_id}: {e}")
        return None
    except Exception as e:
        logger.exception(f"Ошибка при отправке сообщения {user_id}: {e}")
        return None

def make_onboarding_keyboard(user_id: int, personal_link: str):
    kb = InlineKeyboardMarkup(row_width=1)
    kb.add(InlineKeyboardButton("🔗 Открыть / Копировать ссылку", url=personal_link))
    kb.add(InlineKeyboardButton("🔁 Поделиться ссылкой", callback_data=f"share:{user_id}"))
    kb.add(InlineKeyboardButton("📋 Меню", callback_data="menu:open"))
    return kb

def make_receiver_keyboard(message_id):
    kb = InlineKeyboardMarkup(row_width=2)
    kb.add(
        InlineKeyboardButton("💬 Ответить анонимно", callback_data=f"reply:{message_id}"),
        InlineKeyboardButton(f"⭐ Раскрыть ({REVEAL_PRICE_STARS}★)", callback_data=f"reveal:{message_id}")
    )
    kb.add(InlineKeyboardButton("🚫 Пожаловаться", callback_data=f"report:{message_id}"))
    return kb

# ----------------------------
# Хендлеры
# ----------------------------
@dp.message_handler(commands=["start"])
async def cmd_start(message: types.Message):
    args = message.get_args()
    uid = message.from_user.id
    username = message.from_user.username or None
    first_name = message.from_user.first_name or ""
    ensure_user_record(uid, username, first_name)

    me = await bot.get_me()
    bot_username = me.username or BOT_USERNAME
    personal_link = f"https://t.me/{bot_username}?start={uid}"

    if not args:
        text = (
            "Начните получать анонимные сообщения прямо сейчас.\n\n"
            "Ваша персональная ссылка — поделитесь ею в профиле Telegram, Instagram, TikTok, в сторис и т.д.\n\n"
            f"Ваша ссылка:\n{personal_link}\n\n"
            "Разместите ссылку в профиле — люди смогут писать вам анонимно."
        )
        kb = make_onboarding_keyboard(uid, personal_link)
        await message.answer(text, reply_markup=kb)
        return

    # если есть аргумент — кто-то пришёл по ссылке
    try:
        target_id = int(args)
    except ValueError:
        await message.answer("Неправильная ссылка.")
        return

    # логируем визит
    create_visit(uid, target_id)

    if target_id == uid:
        await message.answer("Это ваша собственная ссылка — напишите что-нибудь для теста или поделитесь ссылкой.")
        return

    pending_send_for_target[uid] = target_id
    await message.answer("✉️ Напишите анонимное сообщение для этого пользователя. Ваш username не будет показан (пока получатель не раскроет).")

@dp.message_handler(commands=["menu"])
async def cmd_menu(message: types.Message):
    kb = InlineKeyboardMarkup(row_width=1)
    kb.add(InlineKeyboardButton("📊 Статистика", callback_data="menu:stats"))
    kb.add(InlineKeyboardButton("💡 Предложить идею", callback_data="menu:idea"))
    kb.add(InlineKeyboardButton("🛠 Техподдержка", callback_data="menu:support"))
    await message.answer("Меню:", reply_markup=kb)

@dp.message_handler(content_types=types.ContentTypes.TEXT)
async def text_handler(message: types.Message):
    uid = message.from_user.id
    text = message.text.strip()

    # обработка идеи (если пользователь нажал "Предложить идею")
    if pending_idea_from_user.get(uid):
        pending_idea_from_user.pop(uid, None)
        save_idea(uid, text)
        # отправляем админу уведомление
        uname = f"@{message.from_user.username}" if message.from_user.username else "(username отсутствует)"
        idea_preview = text if len(text) < 1000 else text[:1000] + "..."
        admin_msg = (
            f"💡 <b>Новая идея</b>\n\n"
            f"👤 Пользователь: {uname}\n"
            f"🆔 ID: <code>{uid}</code>\n\n"
            f"📝 Идея:\n{idea_preview}"
        )
        safe_send(ADMIN_ID, admin_msg, parse_mode="HTML")
        await message.answer("✅ Идея отправлена администратору. Спасибо!")
        return

    # reply flow (ответ на сообщение)
    if uid in pending_reply_for_message:
        message_id = pending_reply_for_message.pop(uid)
        db_msg = get_message_by_id(message_id)
        if not db_msg:
            await message.answer("Исходное сообщение не найдено.")
            return
        sender_id = db_msg[1]
        try:
            await bot.send_message(sender_id,
                                   f"📩 У вас новый ответ (через анонимный бот):\n\n{text}\n\n(Ответ пришёл через бот.)",
                                   reply_markup=InlineKeyboardMarkup().add(
                                       InlineKeyboardButton("💬 Ответить в боте", callback_data=f"reply_to_sender:{message_id}")
                                   ))
            await message.answer("Ответ отправлен отправителю через бота.")
        except Exception as e:
            logger.exception("Ошибка при отправке ответа: %s", e)
            await message.answer("Не удалось отправить ответ — возможно, отправитель заблокировал бота или удалил аккаунт.")
        return

    # send anonymous message flow (пользователь пришёл по чужой ссылке)
    if uid in pending_send_for_target:
        target_id = pending_send_for_target.pop(uid)
        sender_username = message.from_user.username or None
        sender_first_name = message.from_user.first_name or ""
        mid = create_message_record(uid, sender_username, sender_first_name, target_id, text)
        await message.answer("✅ Сообщение отправлено анонимно. Если получатель ответит, ответ придёт через бота.")
        human_text = (
            f"📩 У вас новое анонимное сообщение:\n\n"
            f"{text}\n\n"
            f"Чтобы раскрыть отправителя — нажмите «⭐ Раскрыть ({REVEAL_PRICE_STARS}★)».\n"
            f"Вы также можете ответить через бота."
        )
        kb = make_receiver_keyboard(mid)
        sent = safe_send(target_id, human_text, reply_markup=kb)
        if not sent:
            logger.info(f"Сообщение #{mid} сохранено, но уведомление доставить не удалось.")
        return

    # default
    await message.answer("Я — бот для анонимных сообщений. Чтобы получить свою ссылку — отправь /start\n\nИли нажми '📋 Меню'.")

# ----------------------------
# Callback handlers
# ----------------------------
@dp.callback_query_handler(lambda c: c.data and c.data.startswith("share:"))
async def cb_share(call: types.CallbackQuery):
    try:
        target_uid = int(call.data.split(":", 1)[1])
    except:
        await call.answer("Ошибка.", show_alert=True)
        return
    me = await bot.get_me()
    link = f"https://t.me/{me.username}?start={target_uid}"
    # Отправляем ссылку пользователю (чтобы он мог переслать)
    await bot.send_message(call.from_user.id,
                           f"Скопируйте и отправьте эту ссылку в профиль/чат/сторис:\n\n{link}\n\n"
                           "Поделитесь ею в Telegram, Instagram, TikTok, в сторис — чтобы вам могли писать.")
    await call.answer()

@dp.callback_query_handler(lambda c: c.data and c.data.startswith("menu:"))
async def cb_menu(call: types.CallbackQuery):
    cmd = call.data.split(":", 1)[1]
    if cmd == "open":
        kb = InlineKeyboardMarkup(row_width=1)
        kb.add(InlineKeyboardButton("📊 Статистика", callback_data="menu:stats"))
        kb.add(InlineKeyboardButton("💡 Предложить идею", callback_data="menu:idea"))
        kb.add(InlineKeyboardButton("🛠 Техподдержка", callback_data="menu:support"))
        await bot.send_message(call.from_user.id, "Меню:", reply_markup=kb)
        await call.answer()
        return

    if cmd == "stats":
        stats = get_stats_for_user(call.from_user.id)
        text = (
            f"📈 Статистика для вашего профиля:\n\n"
            f"За сегодня:\n"
            f"• Сообщений получено: {stats['messages_today']}\n"
            f"• Переходов по вашей ссылке: {stats['visits_today']}\n\n"
            f"За всё время:\n"
            f"• Сообщений получено: {stats['messages_total']}\n"
            f"• Переходов по ссылке: {stats['visits_total']}\n"
            f"• Уникальных отправителей: {stats['unique_senders']}\n\n"
            f"Рейтинг пока отключён — данные собираются."
        )
        await bot.send_message(call.from_user.id, text)
        await call.answer()
        return

    if cmd == "idea":
        pending_idea_from_user[call.from_user.id] = True
        await bot.send_message(call.from_user.id, "Опишите вашу идею для бота (коротко):")
        await call.answer()
        return

    if cmd == "support":
        if SUPPORT_USERNAME:
            await bot.send_message(call.from_user.id, f"Техподдержка: https://t.me/{SUPPORT_USERNAME}\n\nНапишите этому пользователю в случае проблем.")
        elif ADMIN_ID:
            await bot.send_message(call.from_user.id, f"Техподдержка доступна — отправьте сообщение администратору: {ADMIN_ID}")
        else:
            await bot.send_message(call.from_user.id, "Техподдержка пока не настроена. Попробуйте позже.")
        await call.answer()
        return

@dp.callback_query_handler(lambda c: c.data and c.data.startswith("reply:"))
async def cb_reply(call: types.CallbackQuery):
    message_id = int(call.data.split(":", 1)[1])
    db_msg = get_message_by_id(message_id)
    if not db_msg:
        await call.answer("Сообщение не найдено.", show_alert=True)
        return
    pending_reply_for_message[call.from_user.id] = message_id
    await call.answer()
    await bot.send_message(call.from_user.id, "Напишите ответ — он будет отправлен отправителю анонимно:")

@dp.callback_query_handler(lambda c: c.data and c.data.startswith("reply_to_sender:"))
async def cb_reply_to_sender(call: types.CallbackQuery):
    message_id = int(call.data.split(":", 1)[1])
    pending_reply_for_message[call.from_user.id] = message_id
    await call.answer()
    await bot.send_message(call.from_user.id, "Напишите ответ отправителю (он придёт через бота):")

@dp.callback_query_handler(lambda c: c.data and c.data.startswith("reveal:"))
async def cb_reveal(call: types.CallbackQuery):
    message_id = int(call.data.split(":", 1)[1])
    db_msg = get_message_by_id(message_id)
    if not db_msg:
        await call.answer("Сообщение не найдено.", show_alert=True)
        return
    await call.answer()
    # симуляция оплаты — в проде вставляется настоящий инвойс/проверка
    confirm_kb = InlineKeyboardMarkup().add(
        InlineKeyboardButton(f"Оплатить {REVEAL_PRICE_STARS}★ (симуляция)", callback_data=f"confirm_reveal:{message_id}")
    )
    await bot.send_message(call.from_user.id,
                           f"Вы собираетесь раскрыть отправителя (стоимость {REVEAL_PRICE_STARS}★).\n\n"
                           f"В демо-версии оплата симулируется. В проде здесь нужно подключить реальную оплату.",
                           reply_markup=confirm_kb)

@dp.callback_query_handler(lambda c: c.data and c.data.startswith("confirm_reveal:"))
async def cb_confirm_reveal(call: types.CallbackQuery):
    message_id = int(call.data.split(":", 1)[1])
    db_msg = get_message_by_id(message_id)
    if not db_msg:
        await call.answer("Сообщение не найдено.", show_alert=True)
        return
    sender_username = db_msg[2]
    sender_first_name = db_msg[3]
    set_message_revealed(message_id)
    if sender_username:
        await call.answer("Отправитель раскрыт!", show_alert=True)
        await bot.send_message(call.from_user.id,
                               f"👤 Отправитель раскрыт:\n\n"
                               f"Имя: {sender_first_name or '—'}\n"
                               f"Username: @{sender_username}\n\n"
                               f"Нажмите, чтобы открыть профиль:",
                               reply_markup=InlineKeyboardMarkup().add(
                                   InlineKeyboardButton("Открыть профиль", url=f"https://t.me/{sender_username}")
                               ))
    else:
        await call.answer("Отправитель раскрыт (username скрыт).", show_alert=True)
        await bot.send_message(call.from_user.id,
                               "У этого отправителя скрыт username — прямую ссылку показать нельзя.\n"
                               "Вы можете продолжить диалог в этом боте (нажмите «Ответить анонимно»), "
                               "или пожаловаться, если это оскорбления.",
                               reply_markup=InlineKeyboardMarkup().add(
                                   InlineKeyboardButton("💬 Ответить анонимно", callback_data=f"reply:{message_id}"),
                                   InlineKeyboardButton("🚫 Пожаловаться", callback_data=f"report:{message_id}")
                               ))

@dp.callback_query_handler(lambda c: c.data and c.data.startswith("report:"))
async def cb_report(call: types.CallbackQuery):
    message_id = int(call.data.split(":", 1)[1])
    pending_reply_for_message[call.from_user.id] = f"report::{message_id}"
    await call.answer()
    await bot.send_message(call.from_user.id, "Опишите причину жалобы (коротко):")

@dp.message_handler(lambda m: isinstance(pending_reply_for_message.get(m.from_user.id, None), str) and pending_reply_for_message[m.from_user.id].startswith("report::"), content_types=types.ContentTypes.TEXT)
async def handle_report_text(message: types.Message):
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
        report_text = (f"🚨 Жалоба на сообщение #{message_id}\n"
                       f"Отправитель (ID): {sender_id}\n"
                       f"Username: {sender_username}\n"
                       f"Текст: {text_preview}\n"
                       f"Причина: {reason}\n"
                       f"Отправитель жалобы: {message.from_user.id}")
        safe_send(ADMIN_ID, report_text)
    await message.answer("Спасибо — жалоба принята, администратор получит уведомление.")

# ----------------------------
# Админские команды (примеры)
# ----------------------------
@dp.message_handler(commands=["stats"])
async def cmd_stats(message: types.Message):
    if message.from_user.id != ADMIN_ID:
        await message.answer("Доступно только администратору.")
        return
    total = db_execute("SELECT COUNT(*) FROM messages", fetchone=True)[0]
    unrevealed = db_execute("SELECT COUNT(*) FROM messages WHERE revealed = 0", fetchone=True)[0]
    await message.answer(f"Всего сообщений: {total}\nНе раскрыты: {unrevealed}")

@dp.message_handler(commands=["admin_ideas"])
async def cmd_admin_ideas(message: types.Message):
    if message.from_user.id != ADMIN_ID:
        await message.answer("Доступно только админу.")
        return
    rows = db_execute("SELECT id, from_user, text, created_at FROM ideas ORDER BY created_at DESC LIMIT 50", fetchall=True) or []
    if not rows:
        await message.answer("Идей пока нет.")
        return
    out = []
    for r in rows:
        when = datetime.fromtimestamp(r[3]).strftime("%Y-%m-%d %H:%M")
        out.append(f"#{r[0]} {when} — от {r[1]}\n{r[2][:200]}")
    await message.answer("\n\n".join(out))

# ----------------------------
# СТАРТ
# ----------------------------
if __name__ == "__main__":
    init_db()
    logger.info("Starting Whosent bot...")
    executor.start_polling(dp, skip_updates=True)
