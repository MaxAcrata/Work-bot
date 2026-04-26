import os
from datetime import datetime

import pandas as pd
import requests
from dotenv import load_dotenv

# ===== ЗАГРУЗКА НАСТРОЕК =====

load_dotenv()

OVERDUE_DAYS = int(os.getenv("OVERDUE_DAYS", 3))
YANDEX_PUBLIC_LINK = os.getenv("YANDEX_PUBLIC_LINK")
DOWNLOADED_FILE_NAME = "yandex_table.xlsx"
REPORT_FILE_NAME = "report.txt"

# ===== ВАРИАНТЫ НАЗВАНИЙ КОЛОНОК =====
# Код ищет нужные колонки не по точному названию,
# а по похожим словам в заголовке.

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
    Ссылка берётся из .env: YANDEX_PUBLIC_LINK.
    """

    if not YANDEX_PUBLIC_LINK:
        raise ValueError("Не заполнен YANDEX_PUBLIC_LINK в .env")

    api_url = "https://cloud-api.yandex.net/v1/disk/public/resources/download"

    response = requests.get(
        api_url,
        params={"public_key": YANDEX_PUBLIC_LINK},
        timeout=30,
    )
    response.raise_for_status()

    download_url = response.json()["href"]

    file_response = requests.get(download_url, timeout=60)
    file_response.raise_for_status()

    with open(DOWNLOADED_FILE_NAME, "wb") as file:
        file.write(file_response.content)

    return DOWNLOADED_FILE_NAME


# ===== ЧТЕНИЕ ТАБЛИЦЫ =====

def load_tasks(file_path):
    """
    Загружает данные из Excel или CSV.
    Для Excel сначала пробует calamine,
    затем openpyxl как запасной вариант.
    """

    if file_path.lower().endswith(".csv"):
        return pd.read_csv(file_path)

    try:
        return pd.read_excel(file_path, engine="calamine")
    except Exception:
        return pd.read_excel(file_path, engine="openpyxl")


def clean_column_names(df):
    """
    Очищает названия колонок:
    убирает лишние пробелы и переносы строк.
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
    Автоматически ищет нужные колонки в таблице.
    Возвращает словарь:
    name -> реальное название колонки в файле.
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
    Преобразует дату из Excel/CSV к формату Python date.
    Если дата пустая или не распознана — возвращает None.
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
    Форматирует дату для отчёта.
    """

    if pd.isna(value) or value == "":
        return "нет даты"

    return value.strftime("%d.%m.%Y")


# ===== ФОРМИРОВАНИЕ ОТЧЁТА =====

def format_task(row, cols):
    """
    Формирует строку одной заявки для текстового отчёта.
    """

    name = row.get(cols["name"], "")
    qty = row.get(cols["quantity"], "")
    unit = row.get(cols["unit"], "")
    request_date = row.get(cols["request_date"], "")

    name = "" if pd.isna(name) else str(name).strip()
    qty = "" if pd.isna(qty) else str(qty).strip()
    unit = "" if pd.isna(unit) else str(unit).strip()

    if name == "":
        name = "Без названия"

    qty_part = f"{qty} {unit}".strip()

    return f"- {name} — {qty_part}, заявка: {format_date(request_date)}"


def build_report(active_tasks, ordered, not_ordered, overdue_tasks, cols):
    """
    Формирует итоговый текст отчёта.
    """

    report = []

    overdue_sorted = overdue_tasks.sort_values(by=cols["request_date"])

    report.append("📊 Сводка по активным заявкам")
    report.append("")
    report.append(f"Всего активных позиций: {len(active_tasks)}")
    report.append(f"Заказано, но не выполнено: {len(ordered)}")
    report.append(f"Не заказано: {len(not_ordered)}")
    report.append(f"Просрочено больше {OVERDUE_DAYS} дней: {len(overdue_tasks)}")
    report.append("")

    report.append("")
    report.append(f"⚠️ Просрочено больше {OVERDUE_DAYS} дней:")

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
    Главная функция анализа:
    1. скачивает файл;
    2. читает таблицу;
    3. фильтрует активные заявки;
    4. считает просрочку;
    5. формирует отчёт.
    """

    file_path = download_yandex_public_file()

    df = load_tasks(file_path)
    df = clean_column_names(df)

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
        active_tasks=active_tasks,
        ordered=ordered,
        not_ordered=not_ordered,
        overdue_tasks=overdue_tasks,
        cols=cols,
    )

    with open(REPORT_FILE_NAME, "w", encoding="utf-8") as file:
        file.write(result)

    return result
