import os
import telebot
from datetime import datetime, timedelta
import threading
import re

BOT_TOKEN = os.getenv("BOT_TOKEN")
bot = telebot.TeleBot(BOT_TOKEN)

задачи = {}

@bot.message_handler(commands=['start'])
def начинать(сообщение):
    bot.send_message(сообщение.chat.id, "Привіт! Я твій асистент-планувальник. Напиши свою задачу.")

@bot.message_handler(func=lambda m: True)
def обрабатывать_задачу(сообщение):
    user_id = сообщение.chat.id
    текст = сообщение.text
    сейчас = datetime.now()

    if user_id not in задачи:
        задачи[user_id] = []

    задачи[user_id].append({"задача": текст, "время": сейчас, "сделаний": False})

    # Перевірка чи є час у форматі HH:MM
    time_match = re.search(r'(\d{1,2}:\d{2})', текст)
    if time_match:
        time_str = time_match.group(1)
        try:
            task_time = datetime.strptime(time_str, "%H:%M").replace(
                year=сейчас.year, month=сейчас.month, day=сейчас.day
            )
            delta = (task_time - сейчас).total_seconds()
            if delta > 0:
                def reminder():
                    bot.send_message(user_id, f"⏰ Нагадування: {текст}")
                threading.Timer(delta, reminder).start()
                bot.send_message(user_id, f"✅ Задача прийнята: {текст} (на {time_str})")
            else:
                bot.send_message(user_id, f"❌ Занадто пізно — час уже минув ({time_str})")
        except Exception as e:
            bot.send_message(user_id, f"❌ Помилка при обробці часу: {str(e)}")
    else:
        bot.send_message(user_id, f"✅ Задача прийнята: {текст}")
        bot.send_message(user_id, "Я нагадаю тобі пізніше")

bot.polling()
