import logging
import json
import os
import asyncio
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

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

DATA_FILE = "tasks_data.json"
user_tasks = {}
user_settings = {}
user_timers = {}  # user_id (int): asyncio.Task

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

# === Помодоро таймер ===
async def start_pomodoro_timer(uid, context, task_text, duration=25*60):
    try:
        await context.bot.send_message(chat_id=uid, text=f"⏳ Помодоро начат: {task_text}\nДлительность: {duration // 60} минут.")
        await asyncio.sleep(duration)
        await context.bot.send_message(chat_id=uid, text=f"✅ Помодоро завершён!\nСделай короткий перерыв 🧘")
    except asyncio.CancelledError:
        await context.bot.send_message(chat_id=uid, text="⛔️ Таймер остановлен.")

# === Меню ===
def main_menu():
    return ReplyKeyboardMarkup([
        [KeyboardButton("🍅 Помодоро"), KeyboardButton("📝 Задачи")],
        [KeyboardButton("📊 Статистика"), KeyboardButton("⚙ Настройки")]
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

# === Обработчики ===
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("👋 Привет! Главное меню:", reply_markup=main_menu())

async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("ℹ️ Помощь: /start чтобы начать, 🍅 — запустить помодоро.")

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

            # Остановим старый таймер, если есть
            old_timer = user_timers.get(uid_int)
            if old_timer and not old_timer.done():
                old_timer.cancel()

            # Запуск нового таймера
            task = asyncio.create_task(start_pomodoro_timer(uid_int, context, task_text))
            user_timers[uid_int] = task

            await update.message.reply_text(f"🍅 Начинаем Помодоро: {task_text}")
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
        await update.message.reply_text("Введите текст новой задачи:")

    elif menu == "add":
        tasks.append({"text": text, "done": False})
        save_data()
        context.user_data["menu"] = None
        await update.message.reply_text("✅ Задача добавлена.", reply_markup=task_menu())

    elif text == "✏ Редактировать":
        if not tasks:
            await update.message.reply_text("📭 Нет задач для редактирования.")
        else:
            task_list = "\n".join([f"{i+1}. {'✅' if t['done'] else '•'} {t['text']}" for i, t in enumerate(tasks)])
            await update.message.reply_text(f"📝 Введите номер задачи для редактирования:\n{task_list}")
            context.user_data["menu"] = "edit_select"

    elif menu == "edit_select":
        if text.isdigit():
            index = int(text) - 1
            if 0 <= index < len(tasks):
                context.user_data["edit_index"] = index
                context.user_data["menu"] = "edit_input"
                await update.message.reply_text(f"✏ Введите новый текст для задачи:\n📝 {tasks[index]['text']}")
            else:
                await update.message.reply_text("❗ Неверный номер задачи.")
        else:
            await update.message.reply_text("❗ Введите корректный номер.")

    elif menu == "edit_input":
        context.user_data["new_text"] = text
        index = context.user_data.get("edit_index")
        old_text = tasks[index]["text"]
        new_text = text
        keyboard = InlineKeyboardMarkup([
            [InlineKeyboardButton("✅ Подтвердить", callback_data="edit_confirm"),
             InlineKeyboardButton("❌ Отменить", callback_data="edit_cancel")]
        ])
        await update.message.reply_text(
            f"⚠️ Подтвердите изменение:\n\n📎 БЫЛО: {old_text}\n✏ СТАЛО: {new_text}",
            reply_markup=keyboard
        )
        context.user_data["menu"] = "edit_confirm"

    elif text == "❌ Удалить":
        if not tasks:
            await update.message.reply_text("📭 Нет задач для удаления.")
        else:
            task_list = "\n".join([f"{i+1}. {'✅' if t['done'] else '•'} {t['text']}" for i, t in enumerate(tasks)])
            await update.message.reply_text(f"🗑 Введите номер задачи для удаления:\n{task_list}")
            context.user_data["menu"] = "delete_select"

    elif menu == "delete_select":
        if text.isdigit():
            index = int(text) - 1
            if 0 <= index < len(tasks):
                context.user_data["delete_index"] = index
                keyboard = InlineKeyboardMarkup([
                    [InlineKeyboardButton("✅ Удалить", callback_data="delete_confirm"),
                     InlineKeyboardButton("❌ Отмена", callback_data="delete_cancel")]
                ])
                await update.message.reply_text(
                    f"⚠️ Удалить задачу:\n🗑 {tasks[index]['text']}?",
                    reply_markup=keyboard
                )
                context.user_data["menu"] = "delete_confirm"
            else:
                await update.message.reply_text("❗ Неверный номер задачи.")
        else:
            await update.message.reply_text("❗ Введите корректный номер.")

    elif text == "📊 Статистика":
        total = len(tasks)
        done = sum(1 for t in tasks if t.get("done"))
        percent = int((done / total) * 100) if total else 0
        await update.message.reply_text(f"📊 Готово: {done}/{total} задач ({percent}%)")

    elif text in ["🔙 Назад", "🔙 Назад к задачам"]:
        context.user_data["menu"] = None
        await update.message.reply_text("🔙 Главное меню:", reply_markup=main_menu())

    else:
        await update.message.reply_text("🤖 Неизвестная команда. Введите /start")

async def handle_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    uid = str(query.from_user.id)
    index = context.user_data.get("confirm_index")
    tasks = user_tasks.get(uid, [])

    if query.data == "confirm_done" and index is not None and 0 <= index < len(tasks):
        tasks[index]["done"] = True
        save_data()
        await query.edit_message_text(f"✅ Завершено: {tasks[index]['text']}")
        context.user_data["menu"] = None

    elif query.data == "cancel_done":
        await query.edit_message_text("❎ Отменено.")
        context.user_data["menu"] = None

    elif query.data == "edit_confirm":
        index = context.user_data.get("edit_index")
        new_text = context.user_data.get("new_text")
        if index is not None and 0 <= index < len(tasks):
            tasks[index]["text"] = new_text
            save_data()
            await query.edit_message_text(f"✅ Задача обновлена:\n{new_text}")
        else:
            await query.edit_message_text("❗ Ошибка при обновлении задачи.")
        context.user_data["menu"] = None

    elif query.data == "edit_cancel":
        await query.edit_message_text("❎ Редактирование отменено.")
        context.user_data["menu"] = None

    elif query.data == "delete_confirm":
        index = context.user_data.get("delete_index")
        if index is not None and 0 <= index < len(tasks):
            deleted_task = tasks.pop(index)
            save_data()
            await query.edit_message_text(f"🗑 Задача удалена:\n{deleted_task['text']}")
        else:
            await query.edit_message_text("❗ Ошибка при удалении задачи.")
        context.user_data["menu"] = None

    elif query.data == "delete_cancel":
        await query.edit_message_text("❎ Удаление отменено.")
        context.user_data["menu"] = None

# === Запуск ===
async def main():
    if not BOT_TOKEN:
        raise RuntimeError("❌ BOT_TOKEN не установлен. Проверь .env файл.")

    load_data()

    app = Application.builder().token(BOT_TOKEN).build()

    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("help", help_command))
    app.add_handler(CommandHandler("stop", handle_text))  # Добавлено для остановки таймера
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_text))
    app.add_handler(CallbackQueryHandler(handle_callback))

    print("✅ Бот запущен")
    await app.run_polling()

if __name__ == "__main__":
    import asyncio

    try:
        loop = asyncio.get_event_loop()
        loop.run_until_complete(main())
    except RuntimeError:
        # Если loop уже работает (например, в Jupyter)
        import nest_asyncio
        nest_asyncio.apply()
        asyncio.get_event_loop().run_until_complete(main())
    
