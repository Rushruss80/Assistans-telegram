
import os
import telebot
from datetime import datetime

BOT_TOKEN = os.getenv("BOT_TOKEN")
bot = telebot.TeleBot(BOT_TOKEN)

tasks = {}

@bot.message_handler(commands=['start'])
def start(message):
    bot.send_message(message.chat.id, "Привіт! Я твій асистент-планувальник. Напиши свою задачу.")

@bot.message_handler(func=lambda m: True)
def handle_task(message):
    user_id = message.chat.id
    text = message.text
    now = datetime.now().strftime("%Y-%m-%d %H:%M")

    if user_id not in tasks:
        tasks[user_id] = []

    tasks[user_id].append({"task": text, "time": now, "done": False})
    bot.send_message(user_id, f"Задачу записано: '{text}'
Я нагадаю тобі пізніше 😉")

bot.polling()
