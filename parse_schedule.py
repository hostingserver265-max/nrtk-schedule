import pdfplumber
import requests
import json
import io
import re
from datetime import datetime

# URL вашего PDF
PDF_URL = "https://cloud.nntc.nnov.ru/index.php/s/fYpXD39YccFB5gM/download/%D1%81%D0%B0%D0%B9%D1%82%20zameny2022-2023dist.pdf"

def download_pdf(url):
    """Скачивает PDF с сайта"""
    print("📥 Скачиваю PDF с сайта колледжа...")
    try:
        response = requests.get(url, timeout=30)
        response.raise_for_status()
        print(f"✅ PDF скачан ({len(response.content)} байт)")
        return response.content
    except requests.RequestException as e:
        print(f"❌ Ошибка скачивания: {e}")
        return None

def clean_text(text):
    """Очищает текст от лишних пробелов и переносов"""
    if not text:
        return ""
    return re.sub(r'\s+', ' ', str(text)).strip()

def extract_date_from_page(page):
    """Ищет дату на странице (над таблицей)"""
    text = page.extract_text()
    if not text:
        return None, None
    
    # Ищем: "понедельник 08 декабря" и т.д.
    date_pattern = re.search(
        r'(понедельник|вторник|среда|четверг|пятница|суббота)\s+(\d{1,2})\s+(января|февраля|марта|апреля|мая|июня|июля|августа|сентября|октября|ноября|декабря)',
        text,
        re.IGNORECASE
    )
    
    if date_pattern:
        day_of_week = date_pattern.group(1).lower()
        date_str = f"{date_pattern.group(2)} {date_pattern.group(3)}"
        return day_of_week, date_str
    return None, None

def parse_schedule(pdf_content):
    print("🔍 Парсю расписание (новая логика)...")
    schedule_data = []

    # Регулярка для поиска группы (например: 1РЭУС-25-1, 2ССА-24-1)
    # Ищем строку, которая похожа на название группы
    group_regex = re.compile(r'\b\d{1}[А-ЯA-Z]{2,5}-\d{2}-\d{1,2}[а-я]?к?с?\b')

    # Время пар
    time_map = {
        1: "08:10-09:40",
        2: "09:50-11:20",
        3: "11:30-13:00",
        4: "13:30-15:00",
        5: "15:10-16:40",
        6: "16:50-18:20",
        7: "18:30-20:00"
    }

    with pdfplumber.open(io.BytesIO(pdf_content)) as pdf:
        print(f"📄 Всего страниц: {len(pdf.pages)}")

        for page_num, page in enumerate(pdf.pages):
            # 1. Ищем дату
            day_of_week, current_date = extract_date_from_page(page)
            if not day_of_week:
                # Если даты нет, возможно это страница с расписанием звонков (стр 11)
                continue

            print(f"  📅 Стр {page_num+1}: {day_of_week}, {current_date}")

            # 2. Извлекаем таблицу
            # vertical_strategy="lines" работает хорошо, когда есть четкие границы
            tables = page.extract_tables(table_settings={
                "vertical_strategy": "lines", 
                "horizontal_strategy": "lines",
                "snap_tolerance": 3,
            })

            current_group = None

            for table in tables:
                for row in table:
                    # Очищаем ячейки (заменяем None на пустую строку)
                    row = [clean_text(cell) for cell in row]
                    
                    # Пропускаем совсем пустые строки
                    if not any(row):
                        continue

                    # Объединяем текст строки, чтобы найти группу (она может быть в первой ячейке или объединенной)
                    row_full_text = " ".join(row)

                    # --- ЛОГИКА 1: Поиск заголовка Группы ---
                    # Если в строке найдена группа И нет номера пары (значит это заголовок)
                    group_match = group_regex.search(row_full_text)
                    
                    # Проверяем, есть ли номер пары в 3-й колонке (индекс 2)
                    # Обычно структура: [Препод, Дисциплина, Пара, Кабинет]
                    has_para_num = False
                    if len(row) > 2 and re.search(r'\b[1-7]\b', row[2]):
                        has_para_num = True

                    if group_match and not has_para_num:
                        current_group = group_match.group(0)
                        continue # Переходим к следующей строке, это был заголовок

                    # Если группы нет, пропускаем
                    if not current_group:
                        continue
                    
                    # Пропускаем строки заголовков таблицы ("Преподаватель", "Дисциплина"...)
                    if "Преподаватель" in row[0] or "Дисциплина" in row[1]:
                        continue

                    # --- ЛОГИКА 2: Обработка строки с занятием ---
                    # Ожидаем структуру: [0:Teacher, 1:Subject, 2:Para, 3:Room]
                    # Иногда колонок может быть больше или меньше, но основные эти.
                    
                    if len(row) < 3:
                        continue

                    # Извлекаем номер пары
                    para_cell = row[2]
                    # Иногда пары записаны как "1-3 пары" или просто "1"
                    # Ищем первую цифру
                    para_match = re.search(r'\b([1-7])\b', para_cell)
                    
                    if not para_match:
                        # Иногда номер пары прилипает к дисциплине (редко, но бывает) или к кабинету
                        # Но в этом макете выглядит стабильно в 3-й колонке.
                        # Если нет номера пары, пропускаем (может это просто мусорная строка)
                        continue

                    para_num = int(para_match.group(1))
                    
                    teacher_text = row[0]
                    subject_text = row[1]
                    room_text = row[3] if len(row) > 3 else ""

                    # Проверка на "нет" пар
                    if "нет" in teacher_text.lower() or "нет" in subject_text.lower():
                        continue
                    
                    # Формируем запись
                    lesson_entry = {
                        "group": current_group,
                        "date": current_date,
                        "day_of_week": day_of_week,
                        "para_num": para_num,
                        "time": time_map.get(para_num, ""),
                        "subject": subject_text,
                        "teacher": teacher_text,
                        "room": room_text
                    }
                    schedule_data.append(lesson_entry)

    print(f"✅ Распознано {len(schedule_data)} занятий")
    return schedule_data

def save_to_json(data, filename='schedule.json'):
    print(f"💾 Сохраняю в {filename}...")
    data.sort(key=lambda x: (x['date'], x['group'], x['para_num']))
    
    with open(filename, 'w', encoding='utf-8') as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
    print("✅ Успешно сохранено!")

def main():
    pdf_content = download_pdf(PDF_URL)
    if pdf_content:
        schedule = parse_schedule(pdf_content)
        if schedule:
            save_to_json(schedule)
        else:
            print("⚠️ Список занятий пуст!")

if __name__ == "__main__":
    main()
