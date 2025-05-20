import asyncio
import os
import re
import json
import logging
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo
from aiogram import Bot, Dispatcher, types
from aiogram.utils import executor

# Налаштування логування
logging.basicConfig(filename="bot.log", level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")

# Ініціалізація бота та диспетчера з токеном
TOKEN = os.environ.get("BOT_TOKEN", "")
if not TOKEN:
    raise RuntimeError("Будь ласка, встановіть токен бота в змінну середовища BOT_TOKEN")
bot = Bot(token=TOKEN)
dp = Dispatcher(bot)

# Файл для збереження задач (на локальній машині; на хостингах нестабільний)
TASKS_FILE = "tasks.json"

# Часова зона
KYIV = ZoneInfo("Europe/Kyiv")

# Завантаження існуючих задач з файлу (якщо файл не існує, починаємо з пустого списку)
tasks_data = {"tasks": []}
if os.path.exists(TASKS_FILE):
    try:
        with open(TASKS_FILE, "r", encoding="utf-8") as f:
            tasks_data = json.load(f)
    except json.JSONDecodeError:
        tasks_data = {"tasks": []}

# Допоміжна функція для збереження задач у файл
def save_tasks():
    with open(TASKS_FILE, "w", encoding="utf-8") as f:
        json.dump(tasks_data, f, ensure_ascii=False, indent=4)

pending_reminders = {}

# Регулярні вирази
time_pattern = re.compile(r"(\d{1,2}:\d{2})")
relative_pattern = re.compile(r"через\s+(\d+)\s*(год|хв)", flags=re.IGNORECASE)

@dp.message_handler(commands=["start", "help"])
async def send_welcome(message: types.Message):
    await message.reply(
        "Привіт! Я бот-нагадувач 🤖\n"
        "Надішліть мені повідомлення з задачею і часом, коли нагадати.\n"
        "Приклади:\n"
        "• `Нагадай мені про зустріч о 19:30`\n"
        "• `Поставка товару в 11:00`\n"
        "• `полити квіти через 2 години`"
    )

@dp.message_handler(lambda msg: time_pattern.search(msg.text) or relative_pattern.search(msg.text))
async def handle_reminder_request(message: types.Message):
    text = message.text.strip()
    user_id = message.from_user.id
    chat_id = message.chat.id

    abs_time_match = time_pattern.search(text)
    rel_time_match = relative_pattern.search(text)
    event_time = None
    desc = text

    if abs_time_match:
        time_str = abs_time_match.group(1)
        desc = text[:abs_time_match.start()]
        desc = re.sub(r"(?i)\bнагадай( мені)?\b", "", desc)
        desc = re.sub(r"(?i)\bпро\b", "", desc).strip(" ,.-:")
        try:
            hour, minute = map(int, time_str.split(":"))
        except ValueError:
            await message.reply("Не вдалося розпізнати час у форматі HH:MM.")
            return
        now = datetime.now(KYIV)
        event_time = datetime(now.year, now.month, now.day, hour, minute, tzinfo=KYIV)
        if event_time < now:
            event_time += timedelta(days=1)
    elif rel_time_match:
        number = int(rel_time_match.group(1))
        unit = rel_time_match.group(2).lower()
        desc = text[:rel_time_match.start()]
        desc = re.sub(r"(?i)\bнагадай( мені)?\b", "", desc)
        desc = re.sub(r"(?i)\bпро\b", "", desc).strip(" ,.-:")
        now = datetime.now(KYIV)
        if unit.startswith("год"):
            event_time = now + timedelta(hours=number)
        else:
            event_time = now + timedelta(minutes=number)
    else:
        return

    if not desc:
        desc = "подію"

    pending_reminders[user_id] = {"chat_id": chat_id, "text": desc, "time": event_time}
    keyboard = types.InlineKeyboardMarkup()
    keyboard.add(types.InlineKeyboardButton("🔔 Тільки в зазначений час", callback_data="remind_once"))
    keyboard.add(types.InlineKeyboardButton("⏰ За 10 хв, 5 хв і в час події", callback_data="remind_multiple"))
    await message.reply(
        f"📝 Я зафіксував задачу: **{desc}** о {event_time.strftime('%H:%M')}. Коли нагадати про неї?",
        parse_mode="Markdown",
        reply_markup=keyboard
    )

@dp.callback_query_handler(lambda call: call.data in ("remind_once", "remind_multiple"))
async def process_reminder_choice(call: types.CallbackQuery):
    user_id = call.from_user.id
    data = pending_reminders.pop(user_id, None)
    if not data:
        await call.answer("❌ Немає активної задачі для нагадування.", show_alert=True)
        return

    chat_id = data["chat_id"]
    desc = data["text"]
    event_time = data["time"]
    choice = call.data

    reminders_to_schedule = [(event_time, f"🔔 Нагадування: **{desc}** вже зараз!")]

    now = datetime.now(KYIV)
    if choice == "remind_multiple":
        for minutes, label in [(10, "через 10 хвилин"), (5, "через 5 хвилин")]:
            remind_time = event_time - timedelta(minutes=minutes)
            if remind_time > now:
                reminders_to_schedule.append((remind_time, f"🔔 Нагадування: **{desc}** {label}"))

    for remind_time, text in reminders_to_schedule:
        task_entry = {
            "chat_id": chat_id,
            "text": text,
            "time": remind_time.isoformat()
        }
        tasks_data["tasks"].append(task_entry)
        asyncio.create_task(send_reminder(chat_id, text, remind_time))

    save_tasks()
    await call.answer("✅ Нагадування налаштовано!", show_alert=False)
    await call.message.edit_text("✅ Нагадування заплановано успішно.")

async def send_reminder(chat_id: int, text: str, remind_time: datetime):
    delay = (remind_time - datetime.now(KYIV)).total_seconds()
    if delay > 0:
        await asyncio.sleep(delay)
    try:
        await bot.send_message(chat_id, text, parse_mode="Markdown")
    except Exception as e:
        logging.error(f"Помилка при відправленні нагадування: {e}")
    tasks_data["tasks"] = [t for t in tasks_data["tasks"] if not (
        t.get("chat_id") == chat_id and t.get("text") == text and t.get("time") == remind_time.isoformat()
    )]
    save_tasks()

async def on_startup(_):
    now = datetime.now(KYIV)
    new_task_list = []
    for task in tasks_data.get("tasks", []):
        try:
            task_time = datetime.fromisoformat(task["time"]).astimezone(KYIV)
        except Exception:
            continue
        if task_time > now:
            new_task_list.append(task)
            asyncio.create_task(send_reminder(task["chat_id"], task["text"], task_time))
    tasks_data["tasks"] = new_task_list
    save_tasks()
    logging.info(f"Бот запущено. Відновлено задач: {len(new_task_list)}")

if __name__ == "__main__":
    executor.start_polling(dp, on_startup=on_startup)
