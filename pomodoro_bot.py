import logging
import json
import os
import asyncio
from datetime import datetime, timedelta
from telegram import Update, ReplyKeyboardMarkup, KeyboardButton
from telegram.ext import (
    Application, CommandHandler, MessageHandler, ContextTypes, filters
)
from dotenv import load_dotenv

# === Настройки и переменные ===
load_dotenv()
BOT_TOKEN = os.getenv("BOT_TOKEN")

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

DATA_FILE = "tasks_data.json"
HISTORY_FILE = "session_history.json"

user_tasks = {}
user_settings = {}
user_timers = {}
user_sessions = {}
session_history = {}

# === Работа с данными ===
def load_data():
    global user_tasks, user_settings, session_history
    if os.path.exists(DATA_FILE):
        with open(DATA_FILE, 'r') as f:
            try:
                data = json.load(f)
                user_tasks.update(data.get("tasks", {}))
                user_settings.update(data.get("settings", {}))
            except Exception as e:
                logger.error(f"Ошибка при загрузке данных: {e}")
    if os.path.exists(HISTORY_FILE):
        with open(HISTORY_FILE, 'r') as f:
            try:
                session_history.update(json.load(f))
            except Exception as e:
                logger.error(f"Ошибка при загрузке истории: {e}")

def save_data():
    try:
        with open(DATA_FILE, 'w') as f:
            json.dump({"tasks": user_tasks, "settings": user_settings}, f)
    except Exception as e:
        logger.error(f"Ошибка при сохранении данных: {e}")
    try:
        with open(HISTORY_FILE, 'w') as f:
            json.dump(session_history, f)
    except Exception as e:
        logger.error(f"Ошибка при сохранении истории: {e}")

# === Подсчёт статистики ===
def count_sessions(uid, days):
    now = datetime.utcnow()
    cutoff = now - timedelta(days=days)
    sessions = session_history.get(str(uid), [])
    return sum(1 for s in sessions if datetime.fromisoformat(s["time"]) >= cutoff)

# === Таймер Pomodoro ===
async def start_pomodoro_timer(uid, context, task_text):
    settings = user_settings.get(str(uid), {})
    duration = settings.get("duration", 25) * 60
    short_break = settings.get("break_short", 5) * 60
    long_break = settings.get("break_long", 15) * 60

    user_sessions.setdefault(uid, 0)
    user_sessions[uid] += 1

    try:
        await context.bot.send_message(chat_id=uid, text=f"⏳ Помодоро начат: {task_text}\nДлительность: {duration // 60} минут.")
        await asyncio.sleep(duration)
        await context.bot.send_message(chat_id=uid, text="✅ Помодоро завершён!")

        now = datetime.utcnow().isoformat()
        session_history.setdefault(str(uid), []).append({"time": now, "task": task_text})
        save_data()

        if user_sessions[uid] % 4 == 0:
            await context.bot.send_message(chat_id=uid, text=f"💤 Длинный перерыв: {long_break // 60} минут.")
            await asyncio.sleep(long_break)
        else:
            await context.bot.send_message(chat_id=uid, text=f"🥤 Короткий перерыв: {short_break // 60} минут.")
            await asyncio.sleep(short_break)

        await context.bot.send_message(chat_id=uid, text="🔔 Перерыв окончен. Готов продолжать!")

    except asyncio.CancelledError:
        await context.bot.send_message(chat_id=uid, text="⛔️ Таймер остановлен.")

# === Главное меню ===
def main_menu():
    return ReplyKeyboardMarkup([
        [KeyboardButton("🍅 Помодоро"), KeyboardButton("📝 Задачи")],
        [KeyboardButton("📊 Статистика"), KeyboardButton("⚙ Настройки")]
    ], resize_keyboard=True)

# === Обработчик сообщений ===
async def handle_text(update: Update, context: ContextTypes.DEFAULT_TYPE):
    uid = str(update.message.from_user.id)
    uid_int = int(uid)
    text = update.message.text.strip()
    tasks = user_tasks.setdefault(uid, [])
    menu = context.user_data.get("menu")

    if text == "🍅 Помодоро":
        if not tasks:
            await update.message.reply_text("📭 Нет задач.")
        else:
            task_list = "\n".join([f"{i+1}. {'✅' if t.get('done') else '•'} {t['text']}" for i, t in enumerate(tasks)])
            await update.message.reply_text(f"Выбери задачу:\n{task_list}")
            context.user_data["menu"] = "pomodoro_select"

    elif menu == "pomodoro_select" and text.isdigit():
        index = int(text) - 1
        if 0 <= index < len(tasks):
            task_text = tasks[index]["text"]
            old_timer = user_timers.get(uid_int)
            if old_timer and not old_timer.done():
                old_timer.cancel()
            task = asyncio.create_task(start_pomodoro_timer(uid_int, context, task_text))
            user_timers[uid_int] = task
            await update.message.reply_text(f"🍅 Начинаем: {task_text}")
            context.user_data["menu"] = None
        else:
            await update.message.reply_text("❗ Неверный номер задачи.")

    elif text == "/stop":
        timer = user_timers.get(uid_int)
        if timer and not timer.done():
            timer.cancel()
            await update.message.reply_text("⛔️ Помодоро остановлен.")
        else:
            await update.message.reply_text("❗ Нет активного таймера.")

    elif text == "📊 Статистика":
        today = count_sessions(uid, 1)
        week = count_sessions(uid, 7)
        month = count_sessions(uid, 30)
        await update.message.reply_text(
            f"📈 Статистика:\nСегодня: {today} сессий\nЗа неделю: {week} сессий\nЗа месяц: {month} сессий"
        )

    elif text == "⚙ Настройки":
        context.user_data["menu"] = "settings"
        await update.message.reply_text(
            "Настройки:\n1 — Время сессии\n2 — Короткий перерыв\n3 — Длинный перерыв",
        )

    elif menu == "settings":
        if text == "1":
            context.user_data["menu"] = "set_duration"
            await update.message.reply_text("Введите длительность сессии (в минутах):")
        elif text == "2":
            context.user_data["menu"] = "set_short_break"
            await update.message.reply_text("Введите длительность короткого перерыва (в минутах):")
        elif text == "3":
            context.user_data["menu"] = "set_long_break"
            await update.message.reply_text("Введите длительность длинного перерыва (в минутах):")

    elif menu in {"set_duration", "set_short_break", "set_long_break"}:
        if text.isdigit():
            mins = int(text)
            key = {
                "set_duration": "duration",
                "set_short_break": "break_short",
                "set_long_break": "break_long"
            }[menu]
            user_settings.setdefault(uid, {})[key] = mins
            save_data()
            await update.message.reply_text(f"✅ Установлено: {mins} минут.", reply_markup=main_menu())
            context.user_data["menu"] = None
        else:
            await update.message.reply_text("❗ Введите корректное число.")

    else:
        await update.message.reply_text("🤖 Неизвестная команда. Напиши /start")

# === Команды ===
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("👋 Привет! Главное меню:", reply_markup=main_menu())

async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("ℹ️ Используй /start чтобы открыть меню.")

# === Запуск ===
async def main():
    if not BOT_TOKEN:
        raise RuntimeError("❌ BOT_TOKEN не установлен.")

    load_data()
    app = Application.builder().token(BOT_TOKEN).build()

    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("help", help_command))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_text))

    print("✅ Бот запущен")
    await app.run_polling()

if __name__ == "__main__":
    import asyncio

    try:
        asyncio.run(main())
    except RuntimeError as e:
        if "already running" in str(e):
            loop = asyncio.get_event_loop()
            loop.create_task(main())
            loop.run_forever()
        else:
            raise
    
