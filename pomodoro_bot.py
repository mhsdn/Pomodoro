import logging
import json
import os
import asyncio
# import openai  # ← Раскомментируй при использовании OpenAI
from telegram import (
    Update, ReplyKeyboardMarkup, KeyboardButton,
    InlineKeyboardMarkup, InlineKeyboardButton
)
from telegram.ext import (
    Application, CommandHandler, MessageHandler, CallbackQueryHandler,
    ContextTypes, filters
)
from dotenv import load_dotenv

# === Настройки и переменные ===
load_dotenv()
BOT_TOKEN = os.getenv("BOT_TOKEN")
# openai.api_key = os.getenv("OPENAI_API_KEY")  # ← Раскомментируй при использовании OpenAI

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

DATA_FILE = "tasks_data.json"
user_tasks = {}
user_settings = {}
user_timers = {}

# === Работа с данными ===
def load_data():
    global user_tasks, user_settings
    if os.path.exists(DATA_FILE):
        with open(DATA_FILE, 'r') as f:
            try:
                data = json.load(f)
                user_tasks.update(data.get("tasks", {}))
                user_settings.update(data.get("settings", {}))
            except Exception as e:
                logger.error(f"Ошибка при загрузке данных: {e}")

def save_data():
    try:
        with open(DATA_FILE, 'w') as f:
            json.dump({"tasks": user_tasks, "settings": user_settings}, f)
    except Exception as e:
        logger.error(f"Ошибка при сохранении данных: {e}")

# === Таймер Помодоро ===
async def start_pomodoro_timer(uid, context, task_text):
    duration = user_settings.get(str(uid), {}).get("duration", 25) * 60
    try:
        await context.bot.send_message(chat_id=uid, text=f"⏳ Помодоро начат: {task_text}\nДлительность: {duration // 60} минут.")
        await asyncio.sleep(duration)
        await context.bot.send_message(chat_id=uid, text="✅ Помодоро завершён!\nСделай короткий перерыв 🧘")
    except asyncio.CancelledError:
        await context.bot.send_message(chat_id=uid, text="⛔️ Таймер остановлен.")

# === Меню ===
def main_menu():
    return ReplyKeyboardMarkup([
        [KeyboardButton("🍅 Помодоро"), KeyboardButton("📝 Задачи")],
        [KeyboardButton("📊 Статистика"), KeyboardButton("⚙ Настройки")],
        [KeyboardButton("🤖 Помощь от ИИ")]
    ], resize_keyboard=True)

def task_menu():
    return ReplyKeyboardMarkup([
        [KeyboardButton("🛠 Управление задачами")],
        [KeyboardButton("🔙 Назад")]
    ], resize_keyboard=True)

def manage_menu():
    return ReplyKeyboardMarkup([
        [KeyboardButton("➕ Добавить"), KeyboardButton("✏ Редактировать"), KeyboardButton("❌ Удалить")],
        [KeyboardButton("🔙 Назад к задачам")]
    ], resize_keyboard=True)

def settings_menu():
    return ReplyKeyboardMarkup([
        [KeyboardButton("⏱ Установить время")],
        [KeyboardButton("🔙 Назад")]
    ], resize_keyboard=True)

# === Команды ===
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("👋 Привет! Главное меню:", reply_markup=main_menu())

async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("ℹ️ Напиши /start чтобы вернуться в главное меню.")

# === Обработка текста ===
async def handle_text(update: Update, context: ContextTypes.DEFAULT_TYPE):
    uid = str(update.message.from_user.id)
    uid_int = int(uid)
    text = update.message.text.strip()
    tasks = user_tasks.setdefault(uid, [])
    menu = context.user_data.get("menu")

    if text == "🍅 Помодоро":
        if not tasks:
            await update.message.reply_text("📭 Нет задач.", reply_markup=task_menu())
        else:
            task_list = "\n".join([f"{i+1}. {'✅' if t['done'] else '•'} {t['text']}" for i, t in enumerate(tasks)])
            await update.message.reply_text(f"📝 Выбери задачу:\n{task_list}")
            context.user_data["menu"] = "pomodoro_select"

    elif menu == "pomodoro_select" and text.isdigit():
        index = int(text) - 1
        if 0 <= index < len(tasks):
            task_text = tasks[index]['text']
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

    elif text == "📝 Задачи":
        if not tasks:
            await update.message.reply_text("📭 Нет задач.", reply_markup=task_menu())
        else:
            msg = "\n".join([f"{i+1}. {'✅' if t['done'] else '•'} {t['text']}" for i, t in enumerate(tasks)])
            await update.message.reply_text(f"📋 Ваши задачи:\n{msg}", reply_markup=task_menu())
        context.user_data["menu"] = None

    elif text == "🛠 Управление задачами":
        await update.message.reply_text("Выберите действие:", reply_markup=manage_menu())

    elif text == "➕ Добавить":
        context.user_data["menu"] = "add"
        await update.message.reply_text("Введите новую задачу:")

    elif menu == "add":
        tasks.append({"text": text, "done": False})
        save_data()
        context.user_data["menu"] = None
        await update.message.reply_text("✅ Задача добавлена.", reply_markup=task_menu())

    elif text == "✏ Редактировать":
        if not tasks:
            await update.message.reply_text("📭 Нет задач.")
        else:
            task_list = "\n".join([f"{i+1}. {t['text']}" for i, t in enumerate(tasks)])
            await update.message.reply_text(f"✏ Введите номер задачи:\n{task_list}")
            context.user_data["menu"] = "edit_select"

    elif menu == "edit_select":
        if text.isdigit():
            index = int(text) - 1
            if 0 <= index < len(tasks):
                context.user_data["edit_index"] = index
                context.user_data["menu"] = "edit_input"
                await update.message.reply_text(f"✏ Новый текст задачи ({tasks[index]['text']}):")
            else:
                await update.message.reply_text("❗ Неверный номер.")
        else:
            await update.message.reply_text("❗ Введите корректный номер.")

    elif menu == "edit_input":
        index = context.user_data.get("edit_index")
        tasks[index]["text"] = text
        save_data()
        await update.message.reply_text("✅ Обновлено.")
        context.user_data["menu"] = None

    elif text == "❌ Удалить":
        if not tasks:
            await update.message.reply_text("📭 Нет задач.")
        else:
            task_list = "\n".join([f"{i+1}. {t['text']}" for i, t in enumerate(tasks)])
            await update.message.reply_text(f"🗑 Введите номер задачи:\n{task_list}")
            context.user_data["menu"] = "delete_select"

    elif menu == "delete_select":
        if text.isdigit():
            index = int(text) - 1
            if 0 <= index < len(tasks):
                deleted = tasks.pop(index)
                save_data()
                await update.message.reply_text(f"🗑 Удалено: {deleted['text']}")
                context.user_data["menu"] = None
            else:
                await update.message.reply_text("❗ Неверный номер.")
        else:
            await update.message.reply_text("❗ Введите корректный номер.")

    elif text == "📊 Статистика":
        total = len(tasks)
        done = sum(1 for t in tasks if t.get("done"))
        percent = int((done / total) * 100) if total else 0
        await update.message.reply_text(f"📊 Выполнено: {done}/{total} ({percent}%)")

    elif text == "⚙ Настройки":
        await update.message.reply_text("Выберите настройку:", reply_markup=settings_menu())

    elif text == "⏱ Установить время":
        context.user_data["menu"] = "set_timer_duration"
        await update.message.reply_text("⏱ Введите длительность в минутах (например, 25):")

    elif menu == "set_timer_duration":
        if text.isdigit():
            minutes = int(text)
            if 1 <= minutes <= 120:
                user_settings.setdefault(uid, {})["duration"] = minutes
                save_data()
                await update.message.reply_text(f"✅ Установлено {minutes} минут.", reply_markup=main_menu())
                context.user_data["menu"] = None
            else:
                await update.message.reply_text("❗ Введите значение от 1 до 120.")
        else:
            await update.message.reply_text("❗ Введите число.")

    elif text == "🤖 Помощь от ИИ":
        context.user_data["menu"] = "ai_help"
        await update.message.reply_text("🧠 Задай вопрос, например:\n— Как сосредоточиться?\n— Сгенерируй задачи по теме 'экзамен'")

    elif menu == "ai_help":
        query = text.lower()

        # Примеры встроенных ответов
        if "концентрац" in query:
            response = "🧘 Чтобы улучшить концентрацию: убери отвлекающие факторы, используй технику Pomodoro, начни с простой задачи."
        elif "экзамен" in query:
            response = "📚 Задачи по теме 'экзамен':\n1. Повторить темы\n2. Пройти тесты\n3. Составить шпаргалку\n4. Сделать перерыв"
        else:
            response = "🤖 Заглушка: подключи OpenAI для умных ответов."

            # Для OpenAI — раскомментируй:
            # completion = openai.ChatCompletion.create(
            #     model="gpt-3.5-turbo",
            #     messages=[
            #         {"role": "system", "content": "Ты — помощник по продуктивности."},
            #         {"role": "user", "content": text}
            #     ]
            # )
            # response = completion.choices[0].message.content

        await update.message.reply_text(response)
        context.user_data["menu"] = None

    elif text in ["🔙 Назад", "🔙 Назад к задачам"]:
        context.user_data["menu"] = None
        await update.message.reply_text("🔙 Главное меню:", reply_markup=main_menu())

    else:
        await update.message.reply_text("🤖 Неизвестная команда. Используй /start")

# === Запуск ===
async def main():
    if not BOT_TOKEN:
        raise RuntimeError("❌ BOT_TOKEN не установлен.")

    load_data()
    app = Application.builder().token(BOT_TOKEN).build()

    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("help", help_command))
    app.add_handler(CommandHandler("stop", handle_text))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_text))

    print("✅ Бот запущен")
    await app.run_polling()

if __name__ == "__main__":
    import nest_asyncio
    nest_asyncio.apply()
    asyncio.get_event_loop().run_until_complete(main())
    
