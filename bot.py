import os
from datetime import time
from dotenv import load_dotenv

load_dotenv(dotenv_path=os.path.join(os.path.dirname(__file__), ".env"))
from core import analyze_google_sheet, GOOGLE_SHEET_ID

from telegram import Update, ReplyKeyboardMarkup
from telegram.ext import (
    ApplicationBuilder,
    CommandHandler,
    MessageHandler,
    ContextTypes,
    filters,
)

print("GOOGLE_SHEET_ID =", os.getenv("GOOGLE_SHEET_ID"))

# 🔹 (опционально) если используешь добавление строк напрямую
from google_sheets import add_row

# ===== ХРАНЕНИЕ СОСТОЯНИЯ ПОЛЬЗОВАТЕЛЕЙ =====

user_data = {}

# ===== ЗАГРУЗКА НАСТРОЕК =====

load_dotenv()

TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
TELEGRAM_CHAT_ID = os.getenv("TELEGRAM_CHAT_ID")

# 🔹 Ссылка теперь на Google Form
GOOGLE_FORM_LINK = os.getenv("GOOGLE_FORM_LINK")

# 🔹 Админы
ADMIN_IDS_RAW = os.getenv("ADMIN_IDS", "")
ADMIN_IDS = [int(x.strip()) for x in ADMIN_IDS_RAW.split(",") if x.strip()]

# ===== НАСТРОЙКИ АВТООТЧЁТА =====

REPORT_HOUR = 9
REPORT_MINUTE = 0
MAX_MESSAGE_LENGTH = 4000


# ===== ПРОВЕРКА ПРАВ =====

def is_admin(user_id: int) -> bool:
    """Проверяет, является ли пользователь администратором"""
    return user_id in ADMIN_IDS


# ===== КЛАВИАТУРА =====

def get_keyboard_for_user(user_id: int):
    """Разные кнопки для админа и обычного пользователя"""

    if is_admin(user_id):
        keyboard = [
            ["📊 Анализ сейчас"],
            ["➕ Добавить заявку"],
            [" ⛔ Выход"],
        ]
    else:
        keyboard = [
            ["➕ Добавить заявку"],
            [" ⛔ Выход"],
        ]

    return ReplyKeyboardMarkup(keyboard, resize_keyboard=True)


# ===== ОТПРАВКА ДЛИННЫХ СООБЩЕНИЙ =====

async def send_long_message(bot, chat_id, text: str):
    """
    Telegram ограничивает длину сообщения (~4096 символов),
    поэтому разбиваем длинный текст.
    """

    for start in range(0, len(text), MAX_MESSAGE_LENGTH):
        part = text[start:start + MAX_MESSAGE_LENGTH]
        await bot.send_message(chat_id=chat_id, text=part)


# ===== КОМАНДА /start =====

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Старт бота и показ меню"""

    user_id = update.effective_user.id
    markup = get_keyboard_for_user(user_id)

    if is_admin(user_id):
        text = (
            "Бот запущен.\n"
            "Автоотчёт из Google Sheets приходит каждый день в 09:00.\n\n"
            "Выбери действие:"
        )
    else:
        text = (
            "Бот для добавления заявок.\n\n"
            "Нажми кнопку ниже:"
        )

    await update.message.reply_text(text, reply_markup=markup)


# ===== РУЧНОЙ АНАЛИЗ =====

async def run_analysis(update: Update):
    """
    Запускает анализ Google таблицы вручную.
    Доступно только администраторам.
    """

    await update.message.reply_text("Запускаю анализ Google таблицы...")

    try:
        # 🔹 ВАЖНО: функция должна работать с Google Sheets
        result = analyze_google_sheet()

        await send_long_message(
            bot=update.message.get_bot(),
            chat_id=update.effective_chat.id,
            text=result,
        )

    except Exception as error:
        await update.message.reply_text(f"Ошибка анализа: {error}")


# ===== ДОБАВЛЕНИЕ ЗАЯВКИ =====

async def send_form_link(update: Update):
    """
    Отправляет ссылку на Google Form.
    Пользователь заполняет форму → данные попадают в Google Sheets.
    """

    if not GOOGLE_SHEET_ID:
        await update.message.reply_text("Ссылка на Google Form не настроена.")
        return

    await update.message.reply_text(
        f"Заполни заявку:\n{GOOGLE_FORM_LINK}"
    )


# ===== АВТОМАТИЧЕСКИЙ ОТЧЁТ =====

async def scheduled_report(context: ContextTypes.DEFAULT_TYPE):
    """
    Автоматический ежедневный отчёт из Google Sheets
    """

    chat_id = context.job.chat_id

    try:
        result = analyze_google_sheet()

        await send_long_message(
            bot=context.bot,
            chat_id=chat_id,
            text=result,
        )

    except Exception as error:
        await context.bot.send_message(
            chat_id=chat_id,
            text=f"Ошибка автоотчёта: {error}",
        )


# ===== ОБРАБОТКА СООБЩЕНИЙ =====

async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Обработка кнопок и текста"""

    user_id = update.effective_user.id
    text = update.message.text

    # 🔹 Анализ
    if text == "📊 Анализ сейчас":
        if not is_admin(user_id):
            await update.message.reply_text("Нет доступа.")
            return

        await run_analysis(update)
        return

    # 🔹 Добавление заявки
    if text == "➕ Добавить заявку":
        await send_form_link(update)
        return


# ===== ЗАПУСК БОТА =====

def main():
    """Точка входа"""

    if not TELEGRAM_BOT_TOKEN:
        raise ValueError("Не задан TELEGRAM_BOT_TOKEN")

    if not TELEGRAM_CHAT_ID:
        raise ValueError("Не задан TELEGRAM_CHAT_ID")

    app = ApplicationBuilder().token(TELEGRAM_BOT_TOKEN).build()

    app.add_handler(CommandHandler("start", start))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))

    # 🔹 Планировщик отчёта
    app.job_queue.run_daily(
        scheduled_report,
        time=time(hour=REPORT_HOUR, minute=REPORT_MINUTE),
        chat_id=int(TELEGRAM_CHAT_ID),
        name="daily_report",
    )

    print(f"Бот запущен. Отчёт в {REPORT_HOUR:02d}:{REPORT_MINUTE:02d}")

    app.run_polling()


# ===== ENTRY POINT =====

if __name__ == "__main__":
    main()
