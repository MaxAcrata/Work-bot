import os
import logging
from datetime import datetime

import pandas as pd
from dotenv import load_dotenv

# Google API
import gspread
from google.oauth2.service_account import Credentials

# ===== ЛОГИ =====

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
)

# ===== ЗАГРУЗКА НАСТРОЕК =====

load_dotenv()

OVERDUE_DAYS = int(os.getenv("OVERDUE_DAYS", 3))

# 👇 путь к JSON ключу сервисного аккаунта
GOOGLE_CREDENTIALS_FILE = os.getenv("GOOGLE_CREDENTIALS_FILE")

# 👇 ID таблицы (из URL)
GOOGLE_SHEET_ID = os.getenv("GOOGLE_SHEET_ID")

# 👇 имя листа
GOOGLE_SHEET_NAME = os.getenv("GOOGLE_SHEET_NAME", "Input")

REPORT_FILE_NAME = "report.txt"

# ===== ВАРИАНТЫ НАЗВАНИЙ КОЛОНОК =====

COLUMN_MAPPING = {
    "name": ["наименование", "название", "товар", "позиция"],
    "quantity": ["кол-во", "количество", "кол во"],
    "unit": ["ед", "ед.", "единица", "ед измерения" , "Ед. изм"],
    "request_date": ["дата заявки", "заявка"],
    "done_date": ["дата выполнения", "выполнение", "выполнено"],
    "initiator" : ["????"],
    "status": ["?????"],
    "object": ["объект"],
    "notes": ["примечания", "комментарий", "комментарии"],
}


# ===== GOOGLE SHEETS =====

def load_google_sheet():
    """
    Загружает данные из Google Sheets в DataFrame
    """

    if not GOOGLE_CREDENTIALS_FILE or not GOOGLE_SHEET_ID:
        raise ValueError("Не заданы GOOGLE_CREDENTIALS_FILE или GOOGLE_SHEET_ID")

    logging.info("Подключаюсь к Google Sheets")

    scopes = [
        "https://www.googleapis.com/auth/spreadsheets.readonly"
    ]

    credentials = Credentials.from_service_account_file(
        GOOGLE_CREDENTIALS_FILE,
        scopes=scopes
    )

    client = gspread.authorize(credentials)

    sheet = client.open_by_key(GOOGLE_SHEET_ID)
    worksheet = sheet.worksheet(GOOGLE_SHEET_NAME)

    logging.info("Читаю данные из таблицы")

    data = worksheet.get_all_values()

    if not data:
        raise ValueError("Таблица пустая")

    # первая строка — заголовки
    headers = data[0]
    rows = data[1:]

    df = pd.DataFrame(rows, columns=headers)

    return df


# ===== ОЧИСТКА =====

def clean_column_names(df):
    df.columns = (
        df.columns
        .astype(str)
        .str.strip()
        .str.replace("\n", " ", regex=False)
        .str.replace("\r", " ", regex=False)
    )
    return df


def map_columns(df):
    normalized_columns = {
        str(column).lower().strip(): column
        for column in df.columns
    }

    result = {}

    for key, variants in COLUMN_MAPPING.items():
        found_column = None

        for variant in variants:
            for normalized_name, original_name in normalized_columns.items():
                if variant in normalized_name:
                    found_column = original_name
                    break

            if found_column:
                break

        if not found_column:
            raise ValueError(
                f"Не найдена колонка для '{key}'. "
                f"Доступные колонки: {list(df.columns)}"
            )

        result[key] = found_column

    return result


# ===== ДАТЫ =====

def parse_date(value):
    if pd.isna(value) or str(value).strip() == "":
        return None

    if isinstance(value, datetime):
        return value.date()

    value = str(value).strip()

    for date_format in ("%d.%m.%Y", "%d/%m/%Y", "%Y-%m-%d", "%m/%d/%Y"):
        try:
            return datetime.strptime(value, date_format).date()
        except ValueError:
            continue

    return None


def format_date(value):
    if pd.isna(value) or value == "":
        return "нет даты"

    return value.strftime("%d.%m.%Y")


# ===== ОТЧЁТ (без изменений) =====

def format_task(row, cols):
    name = row.get(cols["name"], "")
    qty = row.get(cols["quantity"], "")
    unit = row.get(cols["unit"], "")
    obj = row.get(cols["object"], "")
    request_date = row.get(cols["request_date"], "")

    name = "" if pd.isna(name) else str(name).strip()
    qty = "" if pd.isna(qty) else str(qty).strip()
    unit = "" if pd.isna(unit) else str(unit).strip()
    obj = "Не указан" if pd.isna(obj) or str(obj).strip() == "" else str(obj).strip()

    if name == "":
        name = "Без названия"

    qty_part = f"{qty} {unit}".strip()

    return f"- {name} — {qty_part}, объект: {obj}, дата заявки: {format_date(request_date)}"


def build_report(active_tasks, ordered, not_ordered, overdue_tasks, cols):
    report = []

    report.append("📊 Сводка по активным заявкам")
    report.append(f"Дата отчёта: {datetime.today().strftime('%d.%m.%Y %H:%M')}")
    report.append("")

    report.append(f"Всего активных позиций: {len(active_tasks)}")
    report.append(f"Заказано, но не выполнено: {len(ordered)}")
    report.append(f"Не заказано: {len(not_ordered)}")
    report.append(f"Просрочено больше {OVERDUE_DAYS} дней: {len(overdue_tasks)}")
    report.append("")

    return "\n".join(report)


# ===== ГЛАВНАЯ ФУНКЦИЯ =====

def analyze_google_sheet():
    """
    Основной анализ Google Sheets
    """

    try:
        logging.info("Запускаю анализ Google таблицы")

        df = load_google_sheet()
        df = clean_column_names(df)

        df = df.dropna(how="all")

        cols = map_columns(df)

        df[cols["request_date"]] = df[cols["request_date"]].apply(parse_date)
        df[cols["done_date"]] = df[cols["done_date"]].apply(parse_date)

        active_tasks = df[
            (df[cols["request_date"]].notna()) &
            (df[cols["done_date"]].isna())
            ]

        notes = active_tasks[cols["notes"]].fillna("").astype(str).str.lower()

        ordered = active_tasks[notes.str.contains("заказ", na=False)]
        not_ordered = active_tasks[~notes.str.contains("заказ", na=False)]

        today = datetime.today().date()

        overdue_tasks = active_tasks[
            active_tasks[cols["request_date"]] < today - pd.Timedelta(days=OVERDUE_DAYS)
            ]

        result = build_report(
            active_tasks,
            ordered,
            not_ordered,
            overdue_tasks,
            cols,
        )

        with open(REPORT_FILE_NAME, "w", encoding="utf-8") as f:
            f.write(result)

        logging.info("Анализ завершён")

        return result

    except Exception as e:
        logging.error(f"Ошибка: {e}")
        raise
