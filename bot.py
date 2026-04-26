import os
from datetime import time

from dotenv import load_dotenv
from telegram import Update, ReplyKeyboardMarkup
from telegram.ext import (
    ApplicationBuilder,
    CommandHandler,
    MessageHandler,
    ContextTypes,
    filters,
)

from core import analyze_yandex_table


# ===== ЗАГРУЗКА НАСТРОЕК =====

load_dotenv()

TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
TELEGRAM_CHAT_ID = os.getenv("TELEGRAM_CHAT_ID")


# ===== НАСТРОЙКИ =====

REPORT_HOUR = 9
REPORT_MINUTE = 0
MAX_MESSAGE_LENGTH = 4000


# ===== КНОПКИ =====

keyboard = [
    ["📊 Анализ сейчас"],
]

markup = ReplyKeyboardMarkup(
    keyboard,
    resize_keyboard=True,
)


# ===== ОТПРАВКА ДЛИННЫХ СООБЩЕНИЙ =====

async def send_long_message(bot, chat_id, text):
    """
    Telegram ограничивает длину сообщения.
    Поэтому длинный отчёт отправляем частями.
    """

    for start_index in range(0, len(text), MAX_MESSAGE_LENGTH):
        part = text[start_index:start_index + MAX_MESSAGE_LENGTH]
        await bot.send_message(chat_id=chat_id, text=part)


# ===== /start =====

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """
    Показывает главное меню.
    """

    await update.message.reply_text(
        "Бот запущен.\n"
        "Автоотчёт будет приходить каждый день в 09:00.\n\n"
        "Также можно запустить анализ вручную:",
        reply_markup=markup,
    )


# ===== РУЧНОЙ АНАЛИЗ =====

async def run_analysis(update: Update):
    """
    Запускает анализ вручную по кнопке.
    """

    await update.message.reply_text("Запускаю анализ...")

    try:
        result = analyze_yandex_table()

        await send_long_message(
            bot=update.message.get_bot(),
            chat_id=update.effective_chat.id,
            text=result,
        )

    except Exception as error:
        await update.message.reply_text(f"Ошибка при анализе: {error}")


# ===== АВТООТЧЁТ =====

async def scheduled_report(context: ContextTypes.DEFAULT_TYPE):
    """
    Автоматически запускает анализ по расписанию.
    """

    chat_id = context.job.chat_id

    try:
        result = analyze_yandex_table()

        await send_long_message(
            bot=context.bot,
            chat_id=chat_id,
            text=result,
        )

    except Exception as error:
        await context.bot.send_message(
            chat_id=chat_id,
            text=f"Ошибка автоматического отчёта: {error}",
        )


# ===== ОБРАБОТКА СООБЩЕНИЙ =====

async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """
    Обрабатывает нажатия кнопок.
    """

    text = update.message.text

    if text == "📊 Анализ сейчас":
        await run_analysis(update)
    else:
        await update.message.reply_text(
            "Не понял команду. Используй кнопку меню.",
            reply_markup=markup,
        )


# ===== ЗАПУСК БОТА =====

def main():
    """
    Запускает бота и ставит автоотчёт на 09:00.
    """

    if not TELEGRAM_BOT_TOKEN:
        raise ValueError("Не заполнен TELEGRAM_BOT_TOKEN")

    if not TELEGRAM_CHAT_ID:
        raise ValueError("Не заполнен TELEGRAM_CHAT_ID")

    app = ApplicationBuilder().token(TELEGRAM_BOT_TOKEN).build()

    app.add_handler(CommandHandler("start", start))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))

    app.job_queue.run_daily(
        scheduled_report,
        time=time(hour=REPORT_HOUR, minute=REPORT_MINUTE),
        chat_id=int(TELEGRAM_CHAT_ID),
        name="daily_report",
    )

    print(f"Бот запущен. Автоотчёт включён на {REPORT_HOUR:02d}:{REPORT_MINUTE:02d}")

    app.run_polling()


# ===== ТОЧКА ВХОДА =====

if __name__ == "__main__":
    main()