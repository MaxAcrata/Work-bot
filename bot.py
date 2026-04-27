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
raise SystemExit("Temporary stop Railway bot")


# ===== ЗАГРУЗКА НАСТРОЕК =====

load_dotenv()

TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
TELEGRAM_CHAT_ID = os.getenv("TELEGRAM_CHAT_ID")
YANDEX_FORM_LINK = os.getenv("YANDEX_FORM_LINK")

# Список админов через запятую:
# ADMIN_IDS=123456789,987654321
ADMIN_IDS_RAW = os.getenv("ADMIN_IDS", "")
ADMIN_IDS = [int(x.strip()) for x in ADMIN_IDS_RAW.split(",") if x.strip()]


# ===== НАСТРОЙКИ АВТООТЧЁТА =====

REPORT_HOUR = 9
REPORT_MINUTE = 0
MAX_MESSAGE_LENGTH = 4000


# ===== ПРОВЕРКА ПРАВ =====

def is_admin(user_id: int) -> bool:
    """
    Проверяет, является ли пользователь администратором.
    Только админы могут запускать анализ.
    """

    return user_id in ADMIN_IDS


# ===== КЛАВИАТУРА =====

def get_keyboard_for_user(user_id: int):
    """
    Возвращает разные кнопки для админа и обычного пользователя.
    """

    if is_admin(user_id):
        keyboard = [
            ["📊 Анализ сейчас"],
            ["➕ Добавить заявку"],
        ]
    else:
        keyboard = [
            ["➕ Добавить заявку"],
        ]

    return ReplyKeyboardMarkup(
        keyboard,
        resize_keyboard=True,
    )


# ===== ОТПРАВКА ДЛИННЫХ СООБЩЕНИЙ =====

async def send_long_message(bot, chat_id, text: str):
    """
    Telegram ограничивает длину одного сообщения.
    Поэтому длинный отчёт отправляем несколькими частями.
    """

    for start_index in range(0, len(text), MAX_MESSAGE_LENGTH):
        part = text[start_index:start_index + MAX_MESSAGE_LENGTH]
        await bot.send_message(chat_id=chat_id, text=part)


# ===== КОМАНДА /start =====

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """
    Показывает пользователю меню.
    Админ видит анализ и добавление заявки.
    Коллеги видят только добавление заявки.
    """

    user_id = update.effective_user.id
    markup = get_keyboard_for_user(user_id)

    if is_admin(user_id):
        text = (
            "Бот запущен.\n"
            "Автоотчёт будет приходить каждый день в 09:00.\n\n"
            "Выбери действие:"
        )
    else:
        text = (
            "Бот для добавления заявок.\n\n"
            "Нажми кнопку ниже, чтобы создать заявку:"
        )

    await update.message.reply_text(
        text,
        reply_markup=markup,
    )


# ===== РУЧНОЙ АНАЛИЗ =====

async def run_analysis(update: Update):
    """
    Запускает анализ Яндекс Таблицы вручную.
    Доступно только администраторам.
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


# ===== ДОБАВЛЕНИЕ ЗАЯВКИ =====

async def send_form_link(update: Update):
    """
    Отправляет пользователю ссылку на Yandex Form.
    Через эту форму коллеги добавляют заявки.
    """

    if not YANDEX_FORM_LINK:
        await update.message.reply_text("Ссылка на форму не настроена.")
        return

    await update.message.reply_text(
        f"Заполни заявку по ссылке:\n{YANDEX_FORM_LINK}"
    )


# ===== АВТОМАТИЧЕСКИЙ ОТЧЁТ =====

async def scheduled_report(context: ContextTypes.DEFAULT_TYPE):
    """
    Автоматически запускает анализ каждый день в заданное время.
    Отчёт отправляется в TELEGRAM_CHAT_ID из переменных окружения.
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
    Обрабатывает нажатия кнопок и текстовые сообщения.
    """

    user_id = update.effective_user.id
    text = update.message.text

    # Анализ доступен только админам
    if text == "📊 Анализ сейчас":
        if not is_admin(user_id):
            await update.message.reply_text("Нет доступа к анализу.")
            return

        await run_analysis(update)
        return

    # Добавление заявки доступно всем
    if text == "➕ Добавить заявку":
        await send_form_link(update)
        return

    # Ответ на неизвестную команду
    await update.message.reply_text(
        "Не понял команду. Используй кнопки меню.",
        reply_markup=get_keyboard_for_user(user_id),
    )


# ===== ЗАПУСК БОТА =====

def main():
    """
    Запускает Telegram-бота и ставит ежедневный автоотчёт на 09:00.
    """

    if not TELEGRAM_BOT_TOKEN:
        raise ValueError("Не заполнен TELEGRAM_BOT_TOKEN")

    if not TELEGRAM_CHAT_ID:
        raise ValueError("Не заполнен TELEGRAM_CHAT_ID")

    app = ApplicationBuilder().token(TELEGRAM_BOT_TOKEN).build()

    # Команда /start
    app.add_handler(CommandHandler("start", start))

    # Обработка всех обычных текстовых сообщений
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))

    # Ежедневный отчёт только для основного chat_id
    app.job_queue.run_daily(
        scheduled_report,
        time=time(hour=REPORT_HOUR, minute=REPORT_MINUTE),
        chat_id=int(TELEGRAM_CHAT_ID),
        name="daily_report",
    )

    print(
        f"Бот запущен. Автоотчёт включён на "
        f"{REPORT_HOUR:02d}:{REPORT_MINUTE:02d}"
    )

    app.run_polling()


# ===== ТОЧКА ВХОДА =====

if __name__ == "__main__":
    main()