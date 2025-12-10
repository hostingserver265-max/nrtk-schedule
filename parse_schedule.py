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

def parse_schedule(pdf_content):
    schedule = []
    
    # Глобальные переменные для хранения контекста между страницами
    last_known_date = "Не определена"
    last_known_day = "Не определен"

    # Регулярка для группы (1РЭУС-25-1, 2ССА-24-1 и т.д.)
    group_regex = re.compile(r'\b\d{0,1}[А-ЯA-Z]{2,6}-\d{2,3}-\d{1,2}[а-яА-Яa-zA-Z]?к?с?\b')

    with pdfplumber.open(io.BytesIO(pdf_content)) as pdf:
        print(f"📄 Страниц в PDF: {len(pdf.pages)}")

        for page_num, page in enumerate(pdf.pages):
            text_page = page.extract_text() or ""
            
            # 1. Пытаемся найти дату на странице
            date_match = re.search(r'(понедельник|вторник|среда|четверг|пятница|суббота).*?(\d{1,2}\s+[а-я]+)', text_page, re.IGNORECASE | re.DOTALL)
            
            if date_match:
                last_known_day = date_match.group(1).lower()
                last_known_date = date_match.group(2)
                print(f"📅 Стр {page_num + 1}: Найдена новая дата -> {last_known_day}, {last_known_date}")
            else:
                print(f"⬇️ Стр {page_num + 1}: Продолжение даты -> {last_known_day}, {last_known_date}")

            # Пропускаем страницы без даты, если это самое начало и дата еще не найдена (например, титульник)
            if last_known_date == "Не определена" and page_num == 0:
                continue

            # 2. Извлекаем таблицу
            tables = page.extract_tables(table_settings={"vertical_strategy": "lines", "horizontal_strategy": "lines", "snap_tolerance": 3})
            
            current_group = None
            
            for table in tables:
                for row in table:
                    # Очищаем ячейки
                    row = [clean_text(cell) for cell in row]
                    
                    # Фильтруем пустые элементы в списке (['', 'Text', ''] -> ['Text']) для анализа
                    row_content = [x for x in row if x]
                    if not row_content:
                        continue

                    full_row_text = " ".join(row)

                    # --- АНАЛИЗ СТРОКИ ---

                    # A. Это строка заголовка группы?
                    # Условия: Найдена группа, и в строке НЕТ номера пары (цифры 1-7)
                    group_match = group_regex.search(full_row_text)
                    
                    has_para_number = False
                    para_index = -1
                    
                    # Ищем "Якорь" - номер пары (одинокая цифра от 1 до 8)
                    for idx, cell in enumerate(row):
                        if re.fullmatch(r'[1-8]', cell):
                            has_para_number = True
                            para_index = idx
                            break

                    if group_match and not has_para_number:
                        current_group = group_match.group(0)
                        continue # Это заголовок группы, идем дальше

                    if not current_group:
                        continue

                    # B. Это строка с занятием?
                    if has_para_number and para_index != -1:
                        para_num = int(row[para_index])
                        
                        # --- ЛОГИКА ОПРЕДЕЛЕНИЯ КОЛОНОК ОТНОСИТЕЛЬНО ПАРЫ ---
                        
                        # 1. Аудитория (всегда справа от пары)
                        room_text = ""
                        if para_index + 1 < len(row):
                            room_text = row[para_index + 1]

                        # 2. Предмет (обычно сразу слева от пары)
                        subject_text = ""
                        if para_index > 0:
                            subject_text = row[para_index - 1]
                        
                        # 3. Преподаватель (самый левый непустой элемент или левее предмета)
                        teacher_text = ""
                        # Ищем всё, что левее предмета
                        left_part = row[:para_index-1] 
                        # Если предмет оказался пустым, берем всё левее пары
                        if not subject_text:
                            left_part = row[:para_index]
                        
                        # Собираем учителя из оставшихся левых колонок
                        # Обычно учитель в row[0], а row[0] может быть пустым из-за кривого парсинга
                        relevant_left = [x for x in left_part if x]
                        if relevant_left:
                            teacher_text = relevant_left[0]
                            # Если "левых" элементов больше одного, возможно предмет разбился на части
                            # или преподаватель разбит. Но обычно структура: [Teacher, Subject, Para...]
                            # Если предмет пуст, а в left_part 2 элемента, то второй - это предмет
                            if not subject_text and len(relevant_left) > 1:
                                teacher_text = relevant_left[0]
                                subject_text = relevant_left[1]
                        
                        # --- ДОПОЛНИТЕЛЬНЫЕ ПРОВЕРКИ ---
                        
                        # Если предмет пустой, но есть учитель - возможно они склеились или это Классный час
                        # Но если и предмет и учитель пустые - это мусор
                        if not subject_text and not teacher_text:
                            continue
                        
                        # Фильтр ключевых слов заголовков
                        if "Преподаватель" in teacher_text or "Дисциплина" in subject_text:
                            continue
                            
                        # Фильтр "нет пар"
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

    return schedule

def save_json(data):
    # Сортировка: Дата -> Группа -> Пара
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
