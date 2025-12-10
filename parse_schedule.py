import pdfplumber
import requests
import json
import io
import re

# URL PDF
PDF_URL = "https://cloud.nntc.nnov.ru/index.php/s/fYpXD39YccFB5gM/download/%D1%81%D0%B0%D0%B9%D1%82%20zameny2022-2023dist.pdf"

def download_pdf(url):
    print("📥 Скачиваю PDF...")
    try:
        response = requests.get(url, timeout=30)
        response.raise_for_status()
        return response.content
    except Exception as e:
        print(f"❌ Ошибка: {e}")
        return None

def clean_text(text):
    if not text: return ""
    return str(text).replace('\n', ' ').strip()

def parse_schedule_flexible(pdf_content):
    schedule = []
    
    # Регулярка для группы: (цифра)(Буквы)-(цифры)-(цифра)(буквы)
    # Пример: 1РЭУС-25-1, 2ССА-24-1, ЗИСИП-23-1
    group_regex = re.compile(r'\b\d{0,1}[А-ЯA-Z]{2,6}-\d{2,3}-\d{1,2}[а-яА-Яa-zA-Z]?к?с?\b')

    with pdfplumber.open(io.BytesIO(pdf_content)) as pdf:
        print(f"📄 Страниц в PDF: {len(pdf.pages)}")

        for page_num, page in enumerate(pdf.pages):
            # Поиск даты на странице
            text_page = page.extract_text() or ""
            date_match = re.search(r'(понедельник|вторник|среда|четверг|пятница|суббота).*?(\d{1,2}\s+[а-я]+)', text_page, re.IGNORECASE | re.DOTALL)
            
            current_date = "Не определена"
            day_of_week = "Не определен"
            if date_match:
                day_of_week = date_match.group(1).lower()
                current_date = date_match.group(2)
            
            print(f"\n--- Стр {page_num + 1} | Дата: {current_date} ({day_of_week}) ---")

            # Извлекаем таблицу. Используем 'lines', так как сетка видна четко
            tables = page.extract_tables(table_settings={"vertical_strategy": "lines", "horizontal_strategy": "lines"})
            
            current_group = None
            
            for table_idx, table in enumerate(tables):
                for row_idx, row in enumerate(table):
                    # Очищаем строку
                    row = [clean_text(cell) for cell in row]
                    row_text = " ".join(row)

                    # --- ОТЛАДКА: Показываем первые 3 строки каждой таблицы, чтобы понять структуру ---
                    if row_idx < 3:
                        print(f"DEBUG ROW [{row_idx}]: {row}")

                    # 1. Поиск Группы (если строка содержит код группы и НЕ содержит номера пары)
                    found_group = group_regex.search(row_text)
                    
                    # Проверяем, есть ли в этой строке номер пары (одинокая цифра 1-8)
                    has_para_num = False
                    para_index = -1
                    for idx, cell in enumerate(row):
                        if re.fullmatch(r'[1-8]', cell): # Если ячейка состоит ТОЛЬКО из цифры
                            has_para_num = True
                            para_index = idx
                            break
                    
                    # Если нашли группу и это не строка с парой -> обновляем текущую группу
                    if found_group and not has_para_num:
                        current_group = found_group.group(0)
                        # print(f"  👉 Найдена группа: {current_group}")
                        continue

                    # Если группы нет, пропускаем
                    if not current_group:
                        continue

                    # 2. Поиск Занятия (должен быть номер пары)
                    if has_para_num and para_index != -1:
                        para_num = int(row[para_index])
                        
                        # ЛОГИКА ОТНОСИТЕЛЬНЫХ КОЛОНОК
                        # Препод обычно слева в начале (col 0)
                        # Предмет где-то между Преподом и Парой
                        # Аудитория справа от Пары
                        
                        teacher_text = row[0]
                        
                        # Предмет берем из колонки перед парой. 
                        # Если пара в col 2, предмет в col 1. Если пара в col 1, предмет тоже в col 0 (смешан).
                        subject_text = ""
                        if para_index > 0:
                            subject_text = row[para_index - 1]
                        
                        # Если предмет пустой, возможно он в той же колонке, что и препод (col 0)
                        if not subject_text and para_index > 0:
                            subject_text = row[0]

                        # Аудитория - следующая колонка после пары
                        room_text = ""
                        if para_index + 1 < len(row):
                            room_text = row[para_index + 1]

                        # Фильтрация мусора
                        if "Преподаватель" in teacher_text or "Дисциплина" in subject_text:
                            continue
                        if "нет" in teacher_text.lower() or "нет" in subject_text.lower():
                            continue

                        # Сборка
                        schedule.append({
                            "group": current_group,
                            "date": current_date,
                            "day": day_of_week,
                            "para": para_num,
                            "subject": subject_text,
                            "teacher": teacher_text,
                            "room": room_text
                        })

    return schedule

def save_json(data):
    with open('schedule.json', 'w', encoding='utf-8') as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
    print(f"\n💾 Сохранено {len(data)} занятий в schedule.json")

# Запуск
content = download_pdf(PDF_URL)
if content:
    data = parse_schedule_flexible(content)
    if len(data) > 0:
        save_json(data)
    else:
        print("\n⚠️ ОШИБКА: Занятия не найдены. Посмотрите на DEBUG ROW выше, чтобы понять, как выглядит таблица для скрипта.")
