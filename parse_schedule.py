import pdfplumber
import requests
import json
import io
import re

# URL вашего PDF
PDF_URL = "https://cloud.nntc.nnov.ru/index.php/s/fYpXD39YccFB5gM/download/%D1%81%D0%B0%D0%B9%D1%82%20zameny2022-2023dist.pdf"

def download_pdf(url):
    print("📥 Скачиваю PDF...")
    try:
        response = requests.get(url, timeout=30)
        response.raise_for_status()
        return response.content
    except Exception as e:
        print(f"❌ Ошибка скачивания: {e}")
        return None

def clean_text(text):
    if not text: return ""
    return str(text).replace('\n', ' ').strip()

def fill_merged_cells(schedule):
    """
    Заполняет пустые ячейки (предмет, кабинет), если это продолжение
    предыдущей пары (объединенные ячейки в PDF).
    """
    if not schedule:
        return []

    # Сначала сортируем, чтобы пары шли по порядку
    schedule.sort(key=lambda x: (x['date'], x['group'], x['para']))

    count_fixed = 0
    for i in range(1, len(schedule)):
        prev = schedule[i-1]
        curr = schedule[i]

        # Проверяем, относится ли строка к той же группе и дате
        if curr['group'] == prev['group'] and curr['date'] == prev['date']:
            
            # Если предмет пустой, копируем его из предыдущей пары
            if not curr['subject']:
                curr['subject'] = prev['subject']
                
                # Если учитель тоже пустой (или такой же), копируем
                if not curr['teacher']:
                    curr['teacher'] = prev['teacher']
                
                # Если кабинет пустой, копируем
                if not curr['room']:
                    curr['room'] = prev['room']
                
                count_fixed += 1

    print(f"🔧 Исправлено (заполнено) объединенных ячеек: {count_fixed}")
    return schedule

def parse_schedule(pdf_content):
    schedule = []
    
    last_known_date = "Не определена"
    last_known_day = "Не определен"

    # Регулярка для группы
    group_regex = re.compile(r'\b\d{0,1}[А-ЯA-Z]{2,6}-\d{2,3}-\d{1,2}[а-яА-Яa-zA-Z]?к?с?\b')

    with pdfplumber.open(io.BytesIO(pdf_content)) as pdf:
        print(f"📄 Страниц в PDF: {len(pdf.pages)}")

        for page_num, page in enumerate(pdf.pages):
            text_page = page.extract_text() or ""
            
            # Поиск даты
            date_match = re.search(r'(понедельник|вторник|среда|четверг|пятница|суббота).*?(\d{1,2}\s+[а-я]+)', text_page, re.IGNORECASE | re.DOTALL)
            
            if date_match:
                last_known_day = date_match.group(1).lower()
                last_known_date = date_match.group(2)
            
            if last_known_date == "Не определена" and page_num == 0:
                continue

            tables = page.extract_tables(table_settings={"vertical_strategy": "lines", "horizontal_strategy": "lines", "snap_tolerance": 3})
            
            current_group = None
            
            for table in tables:
                for row in table:
                    row = [clean_text(cell) for cell in row]
                    
                    # Пропуск пустых строк
                    if not any(row):
                        continue

                    full_row_text = " ".join(row)
                    
                    # --- ПОИСК ГРУППЫ ---
                    group_match = group_regex.search(full_row_text)
                    
                    # Ищем цифру пары (1-8)
                    para_index = -1
                    has_para_number = False
                    for idx, cell in enumerate(row):
                        if re.fullmatch(r'[1-8]', cell):
                            has_para_number = True
                            para_index = idx
                            break

                    # Если есть название группы и нет номера пары -> это заголовок группы
                    if group_match and not has_para_number:
                        current_group = group_match.group(0)
                        continue

                    if not current_group:
                        continue

                    # --- ПОИСК ЗАНЯТИЯ ---
                    if has_para_number and para_index != -1:
                        para_num = int(row[para_index])
                        
                        # 1. Аудитория (справа от пары)
                        room_text = ""
                        if para_index + 1 < len(row):
                            room_text = row[para_index + 1]

                        # 2. Предмет (слева от пары)
                        subject_text = ""
                        if para_index > 0:
                            subject_text = row[para_index - 1]
                        
                        # 3. Преподаватель (левее предмета или самый левый)
                        teacher_text = ""
                        left_part = row[:para_index-1] 
                        if not subject_text:
                            left_part = row[:para_index]
                        
                        relevant_left = [x for x in left_part if x] # Берем только непустые
                        
                        if relevant_left:
                            teacher_text = relevant_left[0]
                            # Если слева было 2 значения (например: [Препод, Предмет]), а мы думали предмет пуст
                            if not subject_text and len(relevant_left) > 1:
                                teacher_text = relevant_left[0]
                                subject_text = relevant_left[1]

                        # Фильтрация
                        if not subject_text and not teacher_text and not room_text:
                            continue
                        if "Преподаватель" in teacher_text or "Дисциплина" in subject_text:
                            continue
                        if "нет" in teacher_text.lower() or "нет" in subject_text.lower():
                            continue

                        schedule.append({
                            "group": current_group,
                            "date": last_known_date,
                            "day": last_known_day,
                            "para": para_num,
                            "subject": subject_text,
                            "teacher": teacher_text,
                            "room": room_text
                        })

    # ЗАПУСК ФУНКЦИИ ЗАПОЛНЕНИЯ ПРОПУСКОВ
    schedule = fill_merged_cells(schedule)
    return schedule

def save_json(data):
    # Финальная сортировка
    data.sort(key=lambda x: (x['date'], x['group'], x['para']))
    
    with open('schedule.json', 'w', encoding='utf-8') as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
    print(f"\n💾 Сохранено {len(data)} занятий в schedule.json")

# Запуск
content = download_pdf(PDF_URL)
if content:
    data = parse_schedule(content)
    if len(data) > 0:
        save_json(data)
    else:
        print("⚠️ Занятия не найдены!")
