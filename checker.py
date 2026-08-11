import os
import json
import re
import time
from urllib.parse import urljoin

import requests
from bs4 import BeautifulSoup


# ============================================================
# НАСТРОЙКИ
# ============================================================

TOKEN = os.getenv("TELEGRAM_TOKEN")
CHAT_ID = "194667223"

AUTHORS_FILE = "authors.json"
SEEN_FILE = "seen.json"

REQUEST_TIMEOUT = 45
MAX_RETRIES = 3

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/139.0 Safari/537.36"
    ),
    "Accept": (
        "text/html,application/xhtml+xml,application/xml;"
        "q=0.9,image/avif,image/webp,*/*;q=0.8"
    ),
    "Accept-Language": "ru-RU,ru;q=0.9,en;q=0.8",
    "Connection": "keep-alive",
}


# ============================================================
# JSON
# ============================================================

def load_json(filename, default):
    try:
        with open(filename, "r", encoding="utf-8") as f:
            return json.load(f)
    except FileNotFoundError:
        return default
    except Exception as e:
        print(f"Ошибка чтения {filename}: {e}")
        return default


def save_json(filename, data):
    with open(filename, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)


# ============================================================
# ЗАГРУЗКА СТРАНИЦЫ FLIBUSTA
# ============================================================

def get_page(url):
    last_error = None

    for attempt in range(1, MAX_RETRIES + 1):
        print(f"Загружаем страницу (попытка {attempt}/{MAX_RETRIES}): {url}")
        try:
            response = requests.get(
                url,
                headers=HEADERS,
                timeout=REQUEST_TIMEOUT
            )

            # Корректная обработка кириллицы
            response.encoding = response.apparent_encoding or "utf-8"

            print("HTTP:", response.status_code)
            print("Получено символов:", len(response.text))

            response.raise_for_status()

            return BeautifulSoup(response.text, "html.parser")

        except requests.exceptions.RequestException as e:
            last_error = e
            print("Ошибка:", e)
            if attempt < MAX_RETRIES:
                print("Повторяем через 3 секунды...")
                time.sleep(3)

    raise last_error


# ============================================================
# ИМЯ АВТОРА
# ============================================================

def get_author_name(soup):
    h1 = soup.find("h1")
    if h1:
        text = h1.get_text(" ", strip=True)
        if text and text.lower() not in ("флибуста", "книжное братство"):
            return text

    title = soup.find("title")
    if title:
        text = title.get_text(" ", strip=True)
        for separator in (" | Флибуста", " — Флибуста", " - Флибуста"):
            if separator in text:
                text = text.split(separator, 1)[0].strip()
        if text:
            return text

    return "Неизвестный автор"


# ============================================================
# ИДЕНТИФИКАЦИЯ КНИГИ
# ============================================================

def get_book_id(href):
    if not href:
        return None

    # Ищем точное совпадение /b/12345 (без /read, /fb2, /epub и т.д.)
    match = re.search(r"^/b/(\d+)/?$", href.strip())
    if match:
        return match.group(1)

    return None


def clean_book_title(text):
    if not text:
        return ""

    text = re.sub(r"\s+", " ", text.strip())

    bad_titles = {
        "читать", "скачать", "fb2", "epub", "mobi", 
        "rtf", "txt", "pdf", "mail", "пожаловаться"
    }

    check = text.lower().strip()

    if check in bad_titles or check.strip("() ") in bad_titles:
        return ""

    if re.fullmatch(r"\((?:читать|скачать|fb2|epub|mobi|rtf|txt|pdf|mail)\)", check):
        return ""

    return text


# ============================================================
# ВЫДЕЛЕНИЕ ОСНОВНОЙ ОБЛАСТИ СТРАНИЦЫ (ИСКЛЮЧЕНИЕ СИДЕБАРОВ)
# ============================================================

def isolate_author_content(soup):
    """
    Возвращает только центральную область страницы автора,
    удаляя сайдбары, футеры и блоки отзывов/комментариев.
    """
    # Ищем главный контейнер
    main_content = soup.find("div", id="main") or soup.find("div", id="content")
    if not main_content:
        main_content = soup.body or soup

    # Удаляем сайдбары и мусорные блоки, если они присутствуют
    for selector in ["#sidebar-left", "#sidebar-right", "#footer", "#header"]:
        for el in main_content.select(selector):
            el.decompose()

    # Удаляем секции комментариев и impressions, если они идут ниже
    for heading in main_content.find_all(["h2", "h3"]):
        heading_text = heading.get_text(strip=True).lower()
        if any(bad in heading_text for bad in ["впечатления", "рецензии", "комментарии", "обсуждение"]):
            # Удаляем сам заголовок и все следующие за ним элементы
            for sibling in list(heading.find_next_siblings()):
                sibling.decompose()
            heading.decompose()
            break

    return main_content


# ============================================================
# СБОР КНИГ СО СТРАНИЦЫ
# ============================================================

def parse_books_from_soup(soup):
    content_area = isolate_author_content(soup)
    
    books = []
    seen_ids = set()

    for link in content_area.find_all("a", href=True):
        href = link.get("href", "")
        book_id = get_book_id(href)

        if not book_id or book_id in seen_ids:
            continue

        title = clean_book_title(link.get_text(" ", strip=True))
        if not title or len(title) < 2:
            continue

        seen_ids.add(book_id)
        books.append({
            "id": str(book_id),
            "title": title
        })

    return books


# ============================================================
# СБОР КНИГ С УЧЕТОМ ПАГИНАЦИИ
# ============================================================

def get_author_books_from_url(author_url):
    soup = get_page(author_url)
    author_name = get_author_name(soup)

    all_books = []
    seen_ids = set()

    # 1. Сбор с первой страницы
    first_page_books = parse_books_from_soup(soup)
    for b in first_page_books:
        if b["id"] not in seen_ids:
            seen_ids.add(b["id"])
            all_books.append(b)

    # 2. Проверка пагинации (?page=1, ?page=2...)
    pagination_urls = set()
    pager = soup.find("ul", class_="pager") or soup.find("div", class_="item-list")
    
    if pager:
        for a in pager.find_all("a", href=True):
            href = a.get("href", "")
            if "page=" in href:
                full_url = urljoin(author_url, href)
                pagination_urls.add(full_url)

    # Обходим найденные дополнительные страницы
    for page_url in sorted(pagination_urls):
        try:
            time.sleep(1.5)
            page_soup = get_page(page_url)
            page_books = parse_books_from_soup(page_soup)
            
            for b in page_books:
                if b["id"] not in seen_ids:
                    seen_ids.add(b["id"])
                    all_books.append(b)
        except Exception as e:
            print(f"Ошибка при обработке страницы пагинации {page_url}: {e}")

    return author_name, all_books


# ============================================================
# TELEGRAM
# ============================================================

def send_message(text):
    if not TOKEN:
        print("ОШИБКА: TELEGRAM_TOKEN не найден")
        return False

    url = f"https://api.telegram.org/bot{TOKEN}/sendMessage"

    try:
        response = requests.post(
            url,
            data={"chat_id": CHAT_ID, "text": text},
            timeout=30,
        )
        print("Telegram:", response.text)
        return response.ok
    except Exception as e:
        print("Ошибка Telegram:", e)
        return False


def make_message(author_name, new_books):
    text = f"📚 Новые книги на Флибусте:\n\n👤 Автор: {author_name}\n\n"
    for book in new_books:
        text += f"• {book['title']}\n"
    return text


# ============================================================
# ПРОВЕРКА ОДНОГО АВТОРА
# ============================================================

def check_author(author_url, seen):
    print("\n--------------------------------")
    print("Проверяем:", author_url)
    print("--------------------------------")

    try:
        author_name, books = get_author_books_from_url(author_url)

        print("Автор:", author_name)
        print("Найдено книг:", len(books))

        if not books:
            print("Книги не найдены. Старый список НЕ изменяем.")
            return

        if books:
            print("Первые книги:", [b["title"] for b in books[:5]])

        old_books = seen.get(author_url)

        # ----------------------------------------------------
        # Защита от неполной загрузки страницы
        # ----------------------------------------------------
        if old_books and len(books) < len(old_books) * 0.5:
            print(
                f"ВНИМАНИЕ: Найдено {len(books)} книг, хотя раньше было {len(old_books)}. "
                "Возможно, страница загрузилась не полностью. Базу не обновляем."
            )
            return

        # ----------------------------------------------------
        # Первый запуск для автора
        # ----------------------------------------------------
        if old_books is None:
            print("Первичная загрузка автора — сохраняем список без уведомлений.")
            seen[author_url] = books
            return

        # ----------------------------------------------------
        # Извлечение старых ID и заголовков
        # ----------------------------------------------------
        old_ids = set()
        old_titles = set()

        for item in old_books:
            if isinstance(item, dict):
                if item.get("id"):
                    old_ids.add(str(item["id"]))
                if item.get("title"):
                    old_titles.add(item["title"])
            elif isinstance(item, str):
                old_titles.add(item)

        # ----------------------------------------------------
        # Поиск новых книг
        # ----------------------------------------------------
        new_books = []
        for book in books:
            book_id = str(book["id"])
            title = book["title"]

            if book_id in old_ids or title in old_titles:
                continue

            new_books.append(book)

        print("Старых книг в базе:", len(old_books))
        print("Новых книг найдено:", len(new_books))

        # ----------------------------------------------------
        # Отправка уведомлений
        # ----------------------------------------------------
        if new_books:
            print("Отправка новых книг в Telegram:")
            for book in new_books:
                print(" +", book["title"], f"(ID {book['id']})")

            header = f"📚 Новые книги на Флибусте:\n\n👤 Автор: {author_name}\n\n"
            current = header
            MAX_MESSAGE_LENGTH = 3500

            for book in new_books:
                line = f"• {book['title']}\n"
                if len(current) + len(line) > MAX_MESSAGE_LENGTH:
                    if current != header:
                        send_message(current)
                        time.sleep(1)
                    current = f"📚 Продолжение:\n\n👤 Автор: {author_name}\n\n" + line
                else:
                    current += line

            if current.strip():
                send_message(current)

        else:
            print("Новых книг нет.")

        # Обновляем базу
        seen[author_url] = books

    except requests.exceptions.Timeout:
        print(f"ОШИБКА: Flibusta не ответила за {REQUEST_TIMEOUT} секунд.")
    except requests.exceptions.RequestException as e:
        print("ОШИБКА соединения:", e)
    except Exception as e:
        print("ОШИБКА обработки:", e)


# ============================================================
# MAIN
# ============================================================

def main():
    print("================================")
    print("СТАРТ ПРОВЕРКИ")
    print("================================")

    authors = load_json(AUTHORS_FILE, [])
    seen = load_json(SEEN_FILE, {})

    print("Авторов в списке:", len(authors))

    for author_url in authors:
        check_author(author_url, seen)
        time.sleep(2)

    save_json(SEEN_FILE, seen)

    print("\n================================")
    print("ПРОВЕРКА ЗАВЕРШЕНА")
    print("================================")


if __name__ == "__main__":
    main()
