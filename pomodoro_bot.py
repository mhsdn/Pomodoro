import logging
import json
import os
import asyncio
from datetime import datetime, timedelta
from telegram import Update, ReplyKeyboardMarkup, KeyboardButton
from telegram.ext import Application, CommandHandler, MessageHandler, ContextTypes, filters
from dotenv import load_dotenv
import openai
from dateutil import parser

load_dotenv()
BOT_TOKEN = os.getenv("BOT_TOKEN")
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")
openai.api_key = OPENAI_API_KEY

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

DATA_FILE = "tasks_data.json"
HISTORY_FILE = "session_history.json"

user_tasks = {}
user_settings = {}
user_timers = {}
session_history = {}

def ask_gpt(prompt):
    try:
        response = openai.ChatCompletion.create(
            model="gpt-3.5-turbo",
            messages=[{"role": "user", "content": prompt}],
            temperature=0.7
        )
        return response["choices"][0]["message"]["content"].strip()
    except Exception as e:
        return f"⚠️ Ошибка GPT: {e}"

def load_data():
    global user_tasks, user_settings, session_history
    if os.path.exists(DATA_FILE):
        with open(DATA_FILE, 'r') as f:
            data = json.load(f)
            user_tasks.update(data.get("tasks", {}))
            user_settings.update(data.get("settings", {}))
    if os.path.exists(HISTORY_FILE):
        with open(HISTORY_FILE, 'r') as f:
            session_history.update(json.load(f))

def save_data():
    with open(DATA_FILE, 'w') as f:
        json.dump({"tasks": user_tasks, "settings": user_settings}, f)
    with open(HISTORY_FILE, 'w') as f:
        json.dump(session_history, f)

def count_sessions(uid, days):
    now = datetime.utcnow()
    cutoff = now - timedelta(days=days)
    return sum(1 for s in session_history.get(str(uid), []) if datetime.fromisoformat(s["time"]) >= cutoff)

def main_menu():
    return ReplyKeyboardMarkup([
        [KeyboardButton("🍅 Помодоро"), KeyboardButton("📝 Задачи")],
        [KeyboardButton("📊 Статистика"), KeyboardButton("⚙ Настройки")],
        [KeyboardButton("🤖 Помощь от ИИ")]
    ], resize_keyboard=True)

def format_due(due):
    try:
        dt = parser.isoparse(due)
        delta = dt - datetime.utcnow()
        hours = int(delta.total_seconds() // 3600)
        if hours <= 0:
            return "(срок истёк)"
        return f"(через {hours} час{'а' if 2 <= hours <= 4 else '' if hours == 1 else 'ов'})"
    except:
        return ""

async def start_pomodoro_timer(uid, context, task_text):
    settings = user_settings.get(str(uid), {})
    duration = settings.get("duration", 25) * 60
    short_break = settings.get("break_short", 5) * 60
    long_break = settings.get("break_long", 15) * 60

    await context.bot.send_message(chat_id=uid, text=f"⏳ Помодоро начат: {task_text}\nДлительность: {duration // 60} минут.")
    await asyncio.sleep(duration)

    await context.bot.send_message(chat_id=uid, text="✅ Сессия завершена!")
    session_history.setdefault(str(uid), []).append({"time": datetime.utcnow().isoformat(), "task": task_text})
    save_data()

    if len(session_history.get(str(uid), [])) % 4 == 0:
        await context.bot.send_message(chat_id=uid, text=f"💤 Длинный перерыв: {long_break // 60} минут.")
        await asyncio.sleep(long_break)
    else:
        await context.bot.send_message(chat_id=uid, text=f"🥤 Короткий перерыв: {short_break // 60} минут.")
        await asyncio.sleep(short_break)

    await context.bot.send_message(chat_id=uid, text="🔔 Перерыв окончен. Готов продолжать!")

async def handle_text(update: Update, context: ContextTypes.DEFAULT_TYPE):
    uid = str(update.message.from_user.id)
    text = update.message.text.strip()
    tasks = user_tasks.setdefault(uid, [])
    menu = context.user_data.get("menu")

    if text == "🍅 Помодоро":
        if not tasks:
            await update.message.reply_text("Задач нет.")
        else:
            task_list = "\n".join([f"{i+1}. {'✅' if t.get('done') else '•'} {t['text']} ⏳ {format_due(t.get('due', ''))}" for i, t in enumerate(tasks)])
            await update.message.reply_text(f"Выбери задачу:\n{task_list}")
            context.user_data["menu"] = "pomodoro_select"

    elif context.user_data.get("menu") == "pomodoro_select" and text.isdigit():
        index = int(text) - 1
        if 0 <= index < len(tasks):
            task_text = tasks[index]["text"]
            asyncio.create_task(start_pomodoro_timer(int(uid), context, task_text))
            context.user_data["menu"] = None
        else:
            await update.message.reply_text("❗ Неверный номер задачи.")

    elif text == "📝 Задачи":
        task_list = "\n".join([f"{i+1}. {'✅' if t.get('done') else '•'} {t['text']} ⏳ {format_due(t.get('due', ''))}" for i, t in enumerate(tasks)])
        await update.message.reply_text(f"📋 Задачи:\n{task_list}")
        context.user_data["menu"] = "task_menu"

    elif text == "📊 Статистика":
        today = count_sessions(uid, 1)
        week = count_sessions(uid, 7)
        total = len(tasks)
        done = sum(1 for t in tasks if t.get("done"))
        percent = int((done / total) * 100) if total else 0
        await update.message.reply_text(
            f"📈 Сегодня: {today} | Неделя: {week}\n📋 Выполнено задач: {done}/{total} ({percent}%)"
        )

    elif text == "⚙ Настройки":
        context.user_data["menu"] = "set_times"
        await update.message.reply_text("⏱ Введите 25/5/15 для сессии/малого/длинного перерыва")

    elif menu == "set_times":
        try:
            work, short, long = map(int, text.split("/"))
            user_settings[uid] = {
                "duration": work,
                "break_short": short,
                "break_long": long
            }
            save_data()
            await update.message.reply_text("✅ Настройки сохранены", reply_markup=main_menu())
            context.user_data["menu"] = None
        except:
            await update.message.reply_text("❗ Формат должен быть 25/5/15")

    elif text == "🤖 Помощь от ИИ":
        if not tasks:
            await update.message.reply_text("Нет задач для анализа.")
        else:
            task_list = "\n".join([f"{i+1}. {t['text']}" for i, t in enumerate(tasks)])
            gpt_input = f"Вот список моих задач:\n{task_list}\nС чего начать и почему?"
            reply = ask_gpt(gpt_input)
            if "pip install openai" in reply or "openai/openai-python" in reply:
                reply = "⚠️ ИИ не понял задачи. Попробуйте позже или проверьте ключ."
            await update.message.reply_text(reply)

    else:
        await update.message.reply_text("Неизвестная команда. Напиши /start", reply_markup=main_menu())

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("👋 Привет! Я твой Pomodoro бот.", reply_markup=main_menu())

def main():
    if not BOT_TOKEN:
        raise RuntimeError("❌ BOT_TOKEN не указан.")
    load_data()
    app = Application.builder().token(BOT_TOKEN).build()
    app.add_handler(CommandHandler("start", start))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_text))
    print("✅ Бот запущен")
    app.run_polling()

if __name__ == "__main__":
    main()
