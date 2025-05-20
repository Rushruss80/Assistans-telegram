import asyncio
import os
import re
import json
from datetime import datetime, timedelta
from aiogram import Bot, Dispatcher, types
from aiogram.utils import executor

# Ініціалізація бота та диспетчера з токеном
TOKEN = os.environ.get("BOT_TOKEN", "")  # Бажано зберігати токен у змінній середовища
if not TOKEN:
    raise RuntimeError("Будь ласка, встановіть токен бота в змінну середовища BOT_TOKEN")
bot = Bot(token=TOKEN)
dp = Dispatcher(bot)

# Файл для збереження задач
TASKS_FILE = "tasks.json"

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

# Словник для тимчасового зберігання нагадування, яке очікує вибору користувача (key: user_id)
pending_reminders = {}

# Регулярні вирази для пошуку часу в тексті
time_pattern = re.compile(r"(\d{1,2}:\d{2})")            # шукає підрядок як HH:MM
relative_pattern = re.compile(r"через\s+(\d+)\s*(год|хв)", flags=re.IGNORECASE)  # шукає "через X год/хв"

@dp.message_handler(commands=["start", "help"])
async def send_welcome(message: types.Message):
    """Обробник команди /start та /help – надсилає інструкцію користувачу."""
    await message.reply(
        "Привіт! Я бот-нагадувач 🤖\n"
        "Надішліть мені повідомлення з задачею і часом, коли нагадати.\n"
        "Приклади:\n"
        "• `Нагадай мені про зустріч о 19:30`\n"
        "• `Поставка товару в 11:00`\n"
        "• `полити квіти через 2 години`\n"
        "Після цього я запитаю, коли саме нагадати – в точно зазначений час чи ще й за 10 і 5 хвилин до події."
    )

@dp.message_handler(lambda msg: time_pattern.search(msg.text) or relative_pattern.search(msg.text))
async def handle_reminder_request(message: types.Message):
    """Обробник повідомлень, що містять часовий вираз (створення нового нагадування)."""
    text = message.text.strip()
    user_id = message.from_user.id
    chat_id = message.chat.id

    # Спроба знайти конкретний час HH:MM або відносний час "через N ..."
    abs_time_match = time_pattern.search(text)
    rel_time_match = relative_pattern.search(text)

    event_time = None
    desc = text  # початково опис – увесь текст, потім будемо очищати

    if abs_time_match:
        # Витягнуто формат HH:MM
        time_str = abs_time_match.group(1)  # наприклад "15:30"
        # Опис задачі – все, що передує часу в тексті
        desc = text[:abs_time_match.start()]
        # Прибираємо типові слова-зайві фрази з опису
        desc = re.sub(r"(?i)\bнагадай( мені)?\b", "", desc)  # прибрати "Нагадай" або "Нагадай мені"
        desc = re.sub(r"(?i)\bпро\b", "", desc)              # прибрати слово "про" (якщо було "нагадай про X")
        desc = desc.strip(" ,.-:")  # очистити зайві символи з країв
        # Парсимо час
        try:
            hour, minute = map(int, time_str.split(":"))
        except ValueError:
            await message.reply("Не вдалося розпізнати час у форматі HH:MM.")
            return
        now = datetime.now()
        event_time = datetime(now.year, now.month, now.day, hour, minute)
        # Якщо час уже минув сьогодні, додамо 1 день (нагадування на завтра)
        if event_time < now:
            event_time = event_time + timedelta(days=1)
    elif rel_time_match:
        # Витягнуто формат "через N ... (год/хв)"
        number = int(rel_time_match.group(1))
        unit = rel_time_match.group(2).lower()  # "год" або "хв"
        desc = text[:rel_time_match.start()]
        desc = re.sub(r"(?i)\bнагадай( мені)?\b", "", desc)
        desc = re.sub(r"(?i)\bпро\b", "", desc)
        desc = desc.strip(" ,.-:")
        now = datetime.now()
        if unit.startswith("год"):
            event_time = now + timedelta(hours=number)
        else:
            event_time = now + timedelta(minutes=number)
    else:
        # Якщо не знайдено жодного часу (теоретично цей handler тоді не мав би викликатись)
        return

    # Якщо після очищення опис порожній – задати умовний текст
    if not desc:
        desc = "подію"

    # Збережемо дані і запропонуємо вибрати опцію нагадування
    pending_reminders[user_id] = {"chat_id": chat_id, "text": desc, "time": event_time}
    # Створення інлайн-клавіатури з двома варіантами
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
    """Обробник вибору часу нагадування (тільки в час події або додатково до події)."""
    user_id = call.from_user.id
    # Переконаємось, що для цього користувача є очікуюче нагадування
    data = pending_reminders.get(user_id)
    if not data:
        await call.answer("❌ Немає активної задачі для нагадування.", show_alert=True)
        return

    # Видаляємо з тимчасового сховища, бо починаємо планування
    pending_reminders.pop(user_id, None)

    chat_id = data["chat_id"]
    desc = data["text"]
    event_time: datetime = data["time"]
    choice = call.data

    # Формуємо список запланованих сповіщень (часи та тексти)
    reminders_to_schedule = []

    # Основне нагадування в час події
    reminders_to_schedule.append((event_time, f"🔔 Нагадування: **{desc}** вже зараз!"))

    if choice == "remind_multiple":
        # Додаткові нагадування за 10 хв і 5 хв до події
        remind_10 = event_time - timedelta(minutes=10)
        remind_5 = event_time - timedelta(minutes=5)
        now = datetime.now()
        if remind_10 > now:
            reminders_to_schedule.append((remind_10, f"🔔 Нагадування: **{desc}** через 10 хвилин"))
        if remind_5 > now:
            reminders_to_schedule.append((remind_5, f"🔔 Нагадування: **{desc}** через 5 хвилин"))

    # Заплануємо всі необхідні нагадування
    for remind_time, text in reminders_to_schedule:
        # Зберігаємо задачу у списку задач
        task_entry = {
            "chat_id": chat_id,
            "text": text,
            "time": remind_time.isoformat()
        }
        tasks_data["tasks"].append(task_entry)
        # Стартуємо асинхронне відкладене відправлення повідомлення
        asyncio.create_task(send_reminder(chat_id, text, remind_time))

    # Записуємо оновлений список задач у файл
    save_tasks()

    # Відповідаємо на callback, сповіщаючи користувача
    await call.answer("✅ Нагадування налаштовано!", show_alert=False)
    # Редагуємо попереднє повідомлення з кнопками, щоб підтвердити налаштування
    await call.message.edit_text("✅ Нагадування заплановано успішно.")

async def send_reminder(chat_id: int, text: str, remind_time: datetime):
    """Відкладено надсилає повідомлення-нагадування у заданий час."""
    # Розрахувати затримку (в секундах) до моменту нагадування
    delay = (remind_time - datetime.now()).total_seconds()
    if delay > 0:
        await asyncio.sleep(delay)
    try:
        # Надіслати повідомлення
        await bot.send_message(chat_id, text, parse_mode="Markdown")
    except Exception as e:
        print(f"Помилка при відправленні нагадування: {e}")
    # Після відправки – видалити цю задачу зі списку та зберегти файл
    tasks_data["tasks"] = [t for t in tasks_data["tasks"] if not (
        t.get("chat_id") == chat_id and t.get("text") == text and t.get("time") == remind_time.isoformat()
    )]
    save_tasks()

# Подія запуску бота: плануємо існуючі нагадування з файлу
async def on_startup(_):
    now = datetime.now()
    new_task_list = []
    for task in tasks_data.get("tasks", []):
        try:
            task_time = datetime.fromisoformat(task["time"])
        except Exception:
            continue
        # Якщо час ще не настав, повторно запланувати нагадування
        if task_time > now:
            new_task_list.append(task)
            asyncio.create_task(send_reminder(task["chat_id"], task["text"], task_time))
    # Оновлюємо список задач (відфільтрувавши просрочені, якщо були) і зберігаємо
    tasks_data["tasks"] = new_task_list
    save_tasks()
    print("Бот запущено. Відновлено задач:", len(new_task_list))

if __name__ == "__main__":
    # Запуск бота
    executor.start_polling(dp, on_startup=on_startup)

