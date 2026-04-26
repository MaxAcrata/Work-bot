import os
import logging
from datetime import datetime

import pandas as pd
import requests
from dotenv import load_dotenv


# ===== ЛОГИ =====

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
)


# ===== ЗАГРУЗКА НАСТРОЕК =====

load_dotenv()

OVERDUE_DAYS = int(os.getenv("OVERDUE_DAYS", 3))
YANDEX_PUBLIC_LINK = os.getenv("YANDEX_PUBLIC_LINK")

DOWNLOADED_FILE_NAME = "yandex_table.xlsx"
REPORT_FILE_NAME = "report.txt"


# ===== ВАРИАНТЫ НАЗВАНИЙ КОЛОНОК =====

COLUMN_MAPPING = {
    "name": ["наименование", "название", "товар", "позиция"],
    "quantity": ["кол-во", "количество", "кол во"],
    "unit": ["ед", "ед.", "единица", "ед измерения"],
    "object": ["объект"],
    "request_date": ["дата заявки", "заявка"],
    "done_date": ["дата выполнения", "выполнение", "выполнено"],
    "notes": ["примечания", "комментарий", "комментарии"],
}


# ===== СКАЧИВАНИЕ ФАЙЛА =====

def download_yandex_public_file():
    """
    Скачивает Excel-файл с Яндекс.Диска по публичной ссылке.
    """

    if not YANDEX_PUBLIC_LINK:
        raise ValueError("Не заполнен YANDEX_PUBLIC_LINK")

    logging.info("Получаю ссылку на скачивание с Яндекс.Диска")

    api_url = "https://cloud-api.yandex.net/v1/disk/public/resources/download"

    response = requests.get(
        api_url,
        params={"public_key": YANDEX_PUBLIC_LINK},
        timeout=30,
    )
    response.raise_for_status()

    download_url = response.json()["href"]

    logging.info("Скачиваю файл с Яндекс.Диска")

    file_response = requests.get(download_url, timeout=60)
    file_response.raise_for_status()

    # Проверяем, что скачался именно Excel-файл .xlsx
    if not file_response.content.startswith(b"PK"):
        raise ValueError(
            "Скачанный файл не является Excel .xlsx. "
            "Проверь ссылку на Яндекс.Диске."
        )

    with open(DOWNLOADED_FILE_NAME, "wb") as file:
        file.write(file_response.content)

    logging.info("Файл успешно скачан")

    return DOWNLOADED_FILE_NAME


# ===== ЧТЕНИЕ ТАБЛИЦЫ =====

def load_tasks(file_path):
    """
    Загружает Excel или CSV.
    """

    if file_path.lower().endswith(".csv"):
        return pd.read_csv(file_path)

    try:
        return pd.read_excel(file_path, engine="calamine")
    except Exception as error:
        logging.warning(f"Не удалось прочитать через calamine: {error}")
        return pd.read_excel(file_path, engine="openpyxl")


def clean_column_names(df):
    """
    Очищает заголовки колонок.
    """

    df.columns = (
        df.columns
        .astype(str)
        .str.strip()
        .str.replace("\n", " ", regex=False)
        .str.replace("\r", " ", regex=False)
    )

    return df


def map_columns(df):
    """
    Автоматически находит нужные колонки.
    """

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
    """
    Преобразует дату к единому формату.
    """

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
    """
    Красиво выводит дату.
    """

    if pd.isna(value) or value == "":
        return "нет даты"

    return value.strftime("%d.%m.%Y")


# ===== ОТЧЁТ =====

def format_task(row, cols):
    """
    Формирует строку одной заявки.
    """

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
    """
    Формирует итоговый текст отчёта.
    """

    report = []

    if len(overdue_tasks) > 0:
        report.append("🚨 ВНИМАНИЕ: есть просроченные заявки!")
        report.append("")

    report.append("📊 Сводка по активным заявкам")
    report.append(f"Дата отчёта: {datetime.today().strftime('%d.%m.%Y %H:%M')}")
    report.append("")
    report.append(f"Всего активных позиций: {len(active_tasks)}")
    report.append(f"Заказано, но не выполнено: {len(ordered)}")
    report.append(f"Не заказано: {len(not_ordered)}")
    report.append(f"Просрочено больше {OVERDUE_DAYS} дней: {len(overdue_tasks)}")
    report.append("")

    report.append("🏭 По объектам:")

    by_object = active_tasks[cols["object"]].fillna("Не указан").value_counts()

    if len(by_object) == 0:
        report.append("- Нет активных заявок")
    else:
        for object_name, count in by_object.items():
            report.append(f"- {object_name}: {count}")

    report.append("")
    report.append(f"⚠️ Просрочено больше {OVERDUE_DAYS} дней:")

    overdue_sorted = overdue_tasks.sort_values(by=cols["request_date"])

    if len(overdue_sorted) == 0:
        report.append("- Нет")
    else:
        for _, row in overdue_sorted.iterrows():
            report.append(format_task(row, cols))

    report.append("")
    report.append("❗ Не заказано:")

    if len(not_ordered) == 0:
        report.append("- Нет")
    else:
        not_ordered_sorted = not_ordered.sort_values(by=cols["request_date"])

        for _, row in not_ordered_sorted.iterrows():
            report.append(format_task(row, cols))

    report.append("")
    report.append("✅ Заказано, но не выполнено:")

    if len(ordered) == 0:
        report.append("- Нет")
    else:
        ordered_sorted = ordered.sort_values(by=cols["request_date"])

        for _, row in ordered_sorted.iterrows():
            report.append(format_task(row, cols))

    return "\n".join(report)


# ===== ГЛАВНАЯ ФУНКЦИЯ АНАЛИЗА =====

def analyze_yandex_table():
    """
    Главная функция:
    скачивает таблицу, анализирует её и возвращает отчёт.
    """

    try:
        logging.info("Запускаю анализ таблицы")

        file_path = download_yandex_public_file()

        df = load_tasks(file_path)
        df = clean_column_names(df)

        # Убираем полностью пустые строки
        df = df.dropna(how="all")

        cols = map_columns(df)

        df[cols["request_date"]] = df[cols["request_date"]].apply(parse_date)
        df[cols["done_date"]] = df[cols["done_date"]].apply(parse_date)

        # Активные заявки: есть дата заявки, но нет даты выполнения
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
            active_tasks=active_tasks,
            ordered=ordered,
            not_ordered=not_ordered,
            overdue_tasks=overdue_tasks,
            cols=cols,
        )

        with open(REPORT_FILE_NAME, "w", encoding="utf-8") as file:
            file.write(result)

        logging.info("Анализ успешно завершён")

        return result

    except Exception as error:
        logging.error(f"Ошибка анализа: {error}")
        raise