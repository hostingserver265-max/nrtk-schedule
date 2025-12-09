import pdfplumber
import requests
import json
import io
import re
from datetime import datetime

# URL твоего PDF с расписанием
PDF_URL = "https://cloud.nntc.nnov.ru/index.php/s/fYpXD39YccFB5gM/download/%D1%81%D0%B0%D0%B9%D1%82%20zameny2022-2023dist.pdf"

def download_pdf(url):
    """Скачивает PDF с сайта"""
    print("📥 Скачиваю PDF с сайта колледжа...")
    response = requests.get(url, timeout=30)
    response.raise_for_status()
    print(f"✅ PDF скачан ({len(response.content)} байт)")
    return response.content

def parse_schedule(pdf_content):
    """Парсит PDF и извлекает расписание"""
    print("🔍 Парсю расписание...")
    schedule_data = []

    with pdfplumber.open(io.BytesIO(pdf_content)) as pdf:
        print(f"📄 Всего страниц: {len(pdf.pages)}")

        for page_num, page in enumerate(pdf.pages, 1):
            text = page.extract_text()

            if not text:
                continue

            lines = text.split('\n')
            current_group = None
            current_date = None
            current_day_of_week = None

            for line in lines:
                line = line.strip()

                if not line:
                    continue

                # Ищем дату (например: "среда 10 декабря")
                date_match = re.search(
                    r'(понедельник|вторник|среда|четверг|пятница|суббота)\s+(\d+)\s+(января|февраля|марта|апреля|мая|июня|июля|августа|сентября|октября|ноября|декабря)',
                    line,
                    re.IGNORECASE
                )
                if date_match:
                    current_day_of_week = date_match.group(1).lower()
                    day = date_match.group(2)
                    month = date_match.group(3)
                    current_date = f"{day} {month}"
                    print(f"  📅 Найдена дата: {current_day_of_week}, {current_date}")
                    continue

                # Ищем группу (формат: 1РЭУС-25-1, 2ССА-24-1 и т.д.)
                group_match = re.match(r'^(\d[А-Я]{2,5}-\d{2}-\d{1,2}[а-яукс]?)$', line)
                if group_match:
                    current_group = group_match.group(1)
                    continue

                # Парсим занятие
                if current_group and current_date:
                    # Ищем номер пары (1-7)
                    para_match = re.search(r'\b([1-7])\b', line)
                    if not para_match:
                        continue

                    para_num = int(para_match.group(1))

                    # Пропускаем строки с "нет"
                    if re.search(r'^\s*нет\s*$', line, re.IGNORECASE):
                        continue

                    # Извлекаем преподавателя (Фамилия И.О.)
                    teacher_match = re.search(r'([А-Я][а-я]+(?:-[А-Я][а-я]+)?\s+[А-Я]\.[А-Я]\.)', line)
                    teacher = teacher_match.group(1) if teacher_match else ""

                    # Извлекаем аудиторию
                    room_match = re.search(
                        r'(\d{3}(?:\(с/з\))?|Ук\s+\d{3}|ук\s+км|с/з|актовый зал|2\s+площадка[^\d]*\d+)',
                        line,
                        re.IGNORECASE
                    )
                    room = room_match.group(1).strip() if room_match else ""

                    # Извлекаем название предмета/дисциплины
                    subject = line
                    if teacher:
                        subject = subject.replace(teacher, '')
                    if room:
                        subject = subject.replace(room, '')

                    # Убираем номер пары и лишние пробелы
                    subject = re.sub(r'\b[1-7]\b', '', subject)
                    subject = ' '.join(subject.split()).strip()

                    # Пропускаем если предмет слишком короткий
                    if len(subject) < 3:
                        continue

                    # Пропускаем служебные записи
                    if re.match(r'^(нет|ПП|УП)\s*\d*$', subject, re.IGNORECASE):
                        continue

                    # Определяем время пары
                    time_map = {
                        1: "08:10-09:40",
                        2: "09:50-11:20",
                        3: "11:30-13:00",
                        4: "13:30-15:00",
                        5: "15:10-16:40",
                        6: "16:50-18:20",
                        7: "18:30-20:00"
                    }

                    schedule_data.append({
                        'group': current_group,
                        'date': current_date,
                        'day_of_week': current_day_of_week,
                        'para_num': para_num,
                        'time': time_map.get(para_num, ""),
                        'subject': subject,
                        'teacher': teacher,
                        'room': room
                    })

    print(f"✅ Распознано {len(schedule_data)} занятий")
    return schedule_data

def save_to_json(data, filename='schedule.json'):
    """Сохраняет данные в JSON"""
    print(f"💾 Сохраняю в {filename}...")

    # Получаем уникальные группы
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

    print(f"✅ Файл сохранён!")
    print(f"📊 Статистика:")
    print(f"   • Всего занятий: {len(data)}")
    print(f"   • Групп: {len(groups)}")
    print(f"   • Группы: {', '.join(groups[:5])}{'...' if len(groups) > 5 else ''}")

def main():
    """Главная функция"""
    try:
        print("🚀 Запуск парсера расписания НРТК")
        print("=" * 50)

        # Скачиваем PDF
        pdf_content = download_pdf(PDF_URL)

        # Парсим расписание
        schedule = parse_schedule(pdf_content)

        if not schedule:
            print("❌ ОШИБКА: Не удалось распарсить расписание!")
            exit(1)

        # Сохраняем в JSON
        save_to_json(schedule)

        print("=" * 50)
        print("✅ ГОТОВО! Расписание успешно обновлено")

    except Exception as e:
        print(f"❌ КРИТИЧЕСКАЯ ОШИБКА: {e}")
        import traceback
        traceback.print_exc()
        exit(1)

if __name__ == "__main__":
    main()
