import telebot
import asyncio
import re
from datetime import datetime
import os

BOT_TOKEN = os.getenv("BOT_TOKEN")
if BOT_TOKEN is None:
    raise ValueError("❌ BOT_TOKEN не заданий в середовищі")

bot = telebot.TeleBot(BOT_TOKEN)

# ---- Обробка часу ----
def parse_time(message: str):
    moment_pattern = r"(?:о|в)\s?(\d{1,2}:\d{2})"
    interval_pattern = r"(?:з)\s?(\d{1,2}:\d{2})\s?(?:до)\s?(\d{1,2}:\d{2})"

    now = datetime.now()

    interval_match = re.search(interval_pattern, message)
    if interval_match:
        start_str, end_str = interval_match.groups()
        start = datetime.strptime(start_str, "%H:%M").replace(
            year=now.year, month=now.month, day=now.day)
        end = datetime.strptime(end_str, "%H:%M").replace(
            year=now.year, month=now.month, day=now.day)
        return ("interval", start, end)

    moment_match = re.search(moment_pattern, message)
    if moment_match:
        time_str = moment_match.group(1)
        scheduled = datetime.strptime(time_str, "%H:%M").replace(
            year=now.year, month=now.month, day=now.day)
        return ("moment", scheduled)

    return None

# ---- Запуск нагадування ----
async def schedule_reminder(chat_id, task_text, scheduled_time):
    now = datetime.now()
    delay = (scheduled_time - now).total_seconds()
    if delay > 0:
        await asyncio.sleep(delay)
        bot.send_message(chat_id, f"⏰ Нагадування: {task_text}")
    else:
        bot.send_message(chat_id, f"⚠️ Задача {task_text} вже в минулому")

# ---- Обробка вхідних повідомлень ----
@bot.message_handler(func=lambda msg: True)
def handle_task(message):
    text = message.text
    parsed = parse_time(text)

    if parsed:
        if parsed[0] == "moment":
            scheduled_time = parsed[1]
            asyncio.create_task(schedule_reminder(message.chat.id, text, scheduled_time))
            bot.send_message(message.chat.id, f"✅ Задача запланована на {scheduled_time.strftime('%H:%M')}")
        else:
            bot.send_message(message.chat.id, "🔁 Проміжок часу ще не підтримується, але буде 😉")
    else:
        bot.send_message(message.chat.id, "📝 Задача прийнята, але без часу")

# ---- Запуск ----
import threading

def run_bot():
    bot.infinity_polling()

threading.Thread(target=run_bot).start()
