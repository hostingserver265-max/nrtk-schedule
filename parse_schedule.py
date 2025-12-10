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
    # Заменяем переносы на пробелы, убираем двойные пробелы
    text = re.sub(r'\s+', ' ', text).strip()
    return text

def capitalize_subject(subject):
    """Делает первую букву заглавной, остальные как есть (для аббревиатур типа МДК)"""
    if not subject:
        return ""
    # Если слово короткое (аббревиатура), оставляем капсом (МДК, УП, ОБЖ)
    if len(subject.split()[0]) <= 3 and subject.split()[0].isupper():
        return subject
    # Иначе делаем первую букву заглавной
    return subject[0].upper() + subject[1:]

def extract_date_from_page(page):
    """Ищет дату на странице через поиск текста (над таблицей)"""
    text = page.extract_text()
    if not text:
        return None, None
    
    # Ищем: "понедельник 08 декабря" или "среда 10 декабря"
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
    print("🔍 Парсю расписание (режим таблиц)...")
    schedule_data = []

    # Регулярки
    # Группа: 1РЭУС-25-1, 2ССА-24-1, ЗИСИП-23-1
    group_regex = re.compile(r'\b\d{0,1}[А-ЯA-Z]{2,5}-\d{2}-\d{1,2}[а-я]?к?с?\b')
    
    # Преподаватель: Фамилия И.О. (с дефисом или без)
    teacher_regex = re.compile(r'[А-ЯЁ][а-яё]+(?:-[А-ЯЁ][а-яё]+)?\s+[А-ЯЁ]\.\s?[А-ЯЁ]\.')
    
    # Время пар (стандартное расписание)
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

        for page in pdf.pages:
            # 1. Пытаемся найти дату на странице
            day_of_week, current_date = extract_date_from_page(page)
            if not day_of_week:
                # Если даты нет, возможно это не страница с расписанием
                continue

            print(f"  📅 Дата: {day_of_week}, {current_date}")

            # 2. Извлекаем таблицу
            # structure: settings помогают лучше определять границы, если линии нечеткие
            tables = page.extract_tables(table_settings={"vertical_strategy": "lines", "horizontal_strategy": "lines"})

            current_group = None

            for table in tables:
                for row in table:
                    # Очищаем ячейки от None
                    row = [cell if cell else "" for cell in row]
                    
                    # Пропускаем пустые строки или заголовки
                    if not any(row) or "Преподаватель" in row[0] or "Дисциплина" in row[0]:
                        continue

                    # В таблицах расписания обычно такая структура:
                    # [0]: Дисциплина + Группа + Преподаватель (смешано)
                    # [1]: Номер пары (иногда сдвоенные "1 2")
                    # [2]: Аудитория
                    # [3]: Время (иногда)

                    # --- Анализ Колонок ---
                    # Часто col[0] содержит всё основное
                    content_cell = row[0]
                    para_cell = row[1] if len(row) > 1 else ""
                    room_cell = row[2] if len(row) > 2 else ""

                    # --- 1. Поиск Группы ---
                    # Ищем группу в первой ячейке
                    group_match = group_regex.search(content_cell)
                    if group_match:
                        current_group = group_match.group(0)
                        # Удаляем группу из текста, чтобы она не попала в предмет
                        content_cell = content_cell.replace(current_group, "")

                    if not current_group:
                        continue # Если группу еще не нашли, пропускаем строку

                    # --- 2. Номер пары ---
                    # Очищаем от лишних символов, ищем цифры
                    para_nums = re.findall(r'\b[1-7]\b', para_cell)
                    
                    # Если номеров пар нет в ячейке пары, иногда они в начале первой ячейки
                    if not para_nums:
                         para_nums = re.findall(r'^\s*([1-7])\b', content_cell)

                    if not para_nums:
                        continue

                    # --- 3. Поиск Преподавателя ---
                    teachers = teacher_regex.findall(content_cell)
                    
                    # Удаляем найденных преподавателей из текста предмета
                    subject_text = content_cell
                    for teacher in teachers:
                        subject_text = subject_text.replace(teacher, "")

                    # --- 4. Очистка Предмета ---
                    # Удаляем "нет", мусор, лишние символы
                    subject_text = re.sub(r'\bнет\b', '', subject_text, flags=re.IGNORECASE)
                    subject_text = re.sub(r'^\s*\d+\s*', '', subject_text) # удаляем цифры в начале (если попал номер пары)
                    subject_text = clean_text(subject_text)

                    # Капитализация
                    subject_text = capitalize_subject(subject_text)

                    # Если после очистки предмет пустой или слишком короткий (и это не "нет"), пропускаем
                    if len(subject_text) < 2:
                        continue

                    # --- 5. Обработка Аудитории ---
                    room_text = clean_text(room_cell)
                    
                    # --- 6. Формирование подгрупп (Логика разделения) ---
                    # Если учителей 2 и аудиторий 2 (через /), пытаемся сопоставить
                    final_teacher_str = ""
                    final_room_str = room_text

                    if len(teachers) == 2 and '/' in room_text:
                        # Пример: Teacher1/Teacher2 и Room1/Room2
                        final_teacher_str = f"{teachers[0]} / {teachers[1]}"
                    elif len(teachers) > 0:
                        final_teacher_str = ", ".join(teachers)
                    else:
                        final_teacher_str = "" # Учителя нет (например, классный час)

                    # --- Сохранение (для каждого номера пары, если сдвоенные) ---
                    for para in para_nums:
                        para_int = int(para)
                        
                        lesson_entry = {
                            "group": current_group,
                            "date": current_date,
                            "day_of_week": day_of_week,
                            "para_num": para_int,
                            "time": time_map.get(para_int, ""),
                            "subject": subject_text,
                            "teacher": final_teacher_str,
                            "room": final_room_str
                        }
                        
                        schedule_data.append(lesson_entry)

    print(f"✅ Распознано {len(schedule_data)} занятий")
    return schedule_data

def save_to_json(data, filename='schedule.json'):
    print(f"💾 Сохраняю в {filename}...")
    
    # Сортируем для красоты: сначала по группе, потом по номеру пары
    data.sort(key=lambda x: (x['group'], x['para_num']))

    groups = sorted(list(set(item['group'] for item in data)))

    output = {
        'last_updated': datetime.now().isoformat(),
        'total_lessons': len(data),
        'groups_count': len(groups),
        'groups': groups,
        'schedule': data
    }

    with open(filename, 'w', encoding='utf-8') as f:
        json.dump(output, f, ensure_ascii=False, indent=2)

    print(f"✅ Успешно сохранено!")

def main():
    try:
        print("🚀 Запуск умного парсера расписания (v2.0)")
        print("=" * 50)

        pdf_content = download_pdf(PDF_URL)
        if not pdf_content:
            return

        schedule = parse_schedule(pdf_content)
        
        if not schedule:
            print("⚠️ Внимание: список занятий пуст. Возможно, структура PDF изменилась.")
        else:
            save_to_json(schedule)

        print("=" * 50)

    except Exception as e:
        print(f"❌ КРИТИЧЕСКАЯ ОШИБКА: {e}")
        import traceback
        traceback.print_exc()

if __name__ == "__main__":
    main()
