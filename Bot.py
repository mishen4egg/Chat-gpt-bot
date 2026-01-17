import asyncio
import time
import sqlite3
import requests
import os
from datetime import timedelta

from aiogram import Bot, Dispatcher, F
from aiogram.types import Message, InlineKeyboardMarkup, InlineKeyboardButton
from aiogram.filters import CommandStart, Command

# ===== НАСТРОЙКИ =====

BOT_TOKEN = os.getenv("BOT_TOKEN")
OPENROUTER_API_KEY = os.getenv("OPENROUTER_API_KEY")

MODEL = "openai/gpt-4o-mini"

ADMINS = [123456789]  # ← замени на свой Telegram ID
MAX_MESSAGES = 100

# ====================

bot = Bot(token=BOT_TOKEN)
dp = Dispatcher()

# ===== БАЗА =====

conn = sqlite3.connect("users.db", check_same_thread=False)
cur = conn.cursor()

cur.execute("""
CREATE TABLE IF NOT EXISTS users (
    user_id INTEGER PRIMARY KEY,
    sub_until INTEGER,
    lifetime INTEGER DEFAULT 0,
    used INTEGER DEFAULT 0,
    trial_used INTEGER DEFAULT 0
)
""")
conn.commit()


def get_user(uid):
    cur.execute("SELECT * FROM users WHERE user_id=?", (uid,))
    return cur.fetchone()


def set_trial(uid):
    cur.execute(
        "REPLACE INTO users VALUES (?, ?, 0, 0, 1)",
        (uid, int(time.time()) + 3600)
    )
    conn.commit()


def has_access(uid):
    u = get_user(uid)
    if not u:
        return False
    _, until, lifetime, used, _ = u
    if used >= MAX_MESSAGES:
        return False
    if lifetime:
        return True
    return until > int(time.time())


def inc(uid):
    cur.execute("UPDATE users SET used = used + 1 WHERE user_id=?", (uid,))
    conn.commit()


def remaining(uid):
    u = get_user(uid)
    if not u:
        return 0, "нет доступа"
    _, until, lifetime, used, _ = u
    msgs = MAX_MESSAGES - used
    if lifetime:
        return msgs, "♾ навсегда"
    return msgs, str(timedelta(seconds=max(0, until - int(time.time()))))


def ask_gpt(text):
    r = requests.post(
        "https://openrouter.ai/api/v1/chat/completions",
        headers={
            "Authorization": f"Bearer {OPENROUTER_API_KEY}",
            "Content-Type": "application/json"
        },
        json={
            "model": MODEL,
            "messages": [{"role": "user", "content": text}]
        },
        timeout=60
    )
    return r.json()["choices"][0]["message"]["content"]


def sub_kb():
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🆓 Тест 1 час", callback_data="trial")]
    ])


# ===== ХЕНДЛЕРЫ =====

@dp.message(CommandStart())
async def start(m: Message):
    await m.answer(
        "🤖 GPT Бот\n"
        "🆓 Бесплатный тест 1 час\n"
        "📊 /status — статус",
        reply_markup=sub_kb()
    )


@dp.message(Command("status"))
async def status(m: Message):
    msgs, t = remaining(m.from_user.id)
    await m.answer(f"💬 Осталось: {msgs}\n⏳ Время: {t}")


@dp.callback_query(F.data == "trial")
async def trial(c):
    u = get_user(c.from_user.id)
    if u and u[4] == 1:
        await c.message.answer("❌ Тест уже использован")
        return
    set_trial(c.from_user.id)
    await c.message.answer("🆓 Тест активирован на 1 час!")


@dp.message()
async def chat(m: Message):
    if not has_access(m.from_user.id):
        await m.answer("❌ Нет доступа")
        return
    inc(m.from_user.id)
    await m.answer(ask_gpt(m.text))


# ===== ЗАПУСК =====

async def main():
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())
