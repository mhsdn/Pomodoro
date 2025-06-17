# pomodoro_bot_final.py
import logging
import json
import os
import asyncio
from datetime import datetime, timedelta
from telegram import Update, ReplyKeyboardMarkup, KeyboardButton
from telegram.ext import Application, CommandHandler, MessageHandler, ContextTypes, filters
from dotenv import load_dotenv

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
        with open(HISTORY_FILE, 'w') as f:
            json.dump(session_history, f)
    except Exception as e:
        logger.error(f"Ошибка при сохранении: {e}")

def count_sessions(uid, days):
    now = datetime.utcnow()
    cutoff = now - timedelta(days=days)
    return sum(1 for s in session_history.get(str(uid), []) if datetime.fromisoformat(s["time"]) >= cutoff)

def main_menu():
    return ReplyKeyboardMarkup([
        [KeyboardButton("🍅 Помодоро"), KeyboardButton("📝 Задачи")],
        [KeyboardButton("📊 Статистика"), KeyboardButton("⚙ Настройки")]
    ], resize_keyboard=True)

def task_menu():
    return ReplyKeyboardMarkup([
        [KeyboardButton("➕ Добавить"), KeyboardButton("✏ Редактировать"), KeyboardButton("❌ Удалить")],
        [KeyboardButton("🔙 Назад")]
    ], resize_keyboard=True)

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

    elif text == "📝 Задачи":
        task_list = "\n".join([f"{i+1}. {'✅' if t.get('done') else '•'} {t['text']}" for i, t in enumerate(tasks)])
        await update.message.reply_text(f"📋 Ваши задачи:\n{task_list}", reply_markup=task_menu())
        context.user_data["menu"] = "task_menu"

    elif text == "➕ Добавить":
        context.user_data["menu"] = "add_task"
        await update.message.reply_text("Введите текст задачи:")

    elif menu == "add_task":
        tasks.append({"text": text, "done": False})
        save_data()
        await update.message.reply_text("✅ Задача добавлена.", reply_markup=task_menu())
        context.user_data["menu"] = "task_menu"

    elif text == "✏ Редактировать":
        task_list = "\n".join([f"{i+1}. {t['text']}" for i, t in enumerate(tasks)])
        await update.message.reply_text(f"Введите номер задачи для редактирования:\n{task_list}")
        context.user_data["menu"] = "edit_task"

    elif menu == "edit_task" and text.isdigit():
        index = int(text) - 1
        if 0 <= index < len(tasks):
            context.user_data["edit_index"] = index
            context.user_data["menu"] = "edit_input"
            await update.message.reply_text(f"Введите новый текст задачи (было: {tasks[index]['text']}):")
        else:
            await update.message.reply_text("❗ Неверный номер.")

    elif menu == "edit_input":
        index = context.user_data.get("edit_index")
        tasks[index]["text"] = text
        save_data()
        await update.message.reply_text("✅ Задача обновлена.", reply_markup=task_menu())
        context.user_data["menu"] = "task_menu"

    elif text == "❌ Удалить":
        task_list = "\n".join([f"{i+1}. {t['text']}" for i, t in enumerate(tasks)])
        await update.message.reply_text(f"Введите номер задачи для удаления:\n{task_list}")
        context.user_data["menu"] = "delete_task"

    elif menu == "delete_task" and text.isdigit():
        index = int(text) - 1
        if 0 <= index < len(tasks):
            deleted = tasks.pop(index)
            save_data()
            await update.message.reply_text(f"🗑 Удалено: {deleted['text']}", reply_markup=task_menu())
            context.user_data["menu"] = "task_menu"
        else:
            await update.message.reply_text("❗ Неверный номер.")

    elif text == "📊 Статистика":
        today = count_sessions(uid, 1)
        week = count_sessions(uid, 7)
        month = count_sessions(uid, 30)
        total = len(tasks)
        done = sum(1 for t in tasks if t.get("done"))
        percent = int((done / total) * 100) if total else 0
        await update.message.reply_text(
            f"📈 Статистика:\nСегодня: {today} сессий\nНеделя: {week}\nМесяц: {month}\n\n📋 Выполнено задач: {done}/{total} ({percent}%)"
        )

    elif text == "⚙ Настройки":
        context.user_data["menu"] = "set_all"
        await update.message.reply_text("""Введите значения в формате:
25(сессия)/5(короткий)/15(длинный)""")

    elif menu == "set_all":
        try:
            session, short, long = map(int, text.split("/"))
            user_settings[uid] = {
                "duration": session,
                "break_short": short,
                "break_long": long
            }
            save_data()
            await update.message.reply_text("✅ Настройки обновлены!", reply_markup=main_menu())
            context.user_data["menu"] = None
        except:
            await update.message.reply_text("❗ Введите в формате 25/5/15")

    elif text == "/stop":
        timer = user_timers.get(uid_int)
        if timer and not timer.done():
            timer.cancel()
            await update.message.reply_text("⛔️ Помодоро остановлен.")
        else:
            await update.message.reply_text("❗ Нет активного таймера.")

    elif text == "🔙 Назад":
        context.user_data["menu"] = None
        await update.message.reply_text("🔙 Главное меню:", reply_markup=main_menu())

    else:
        await update.message.reply_text("🤖 Неизвестная команда. Напиши /start")

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("👋 Привет! Главное меню:", reply_markup=main_menu())

def main():
    if not BOT_TOKEN:
        raise RuntimeError("❌ BOT_TOKEN не установлен.")

    load_data()
    app = Application.builder().token(BOT_TOKEN).build()

    app.add_handler(CommandHandler("start", start))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_text))

    print("✅ Бот запущен")
    app.run_polling()

if __name__ == "__main__":
    main()
