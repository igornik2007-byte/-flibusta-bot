import os
import json
import re
import time

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
        json.dump(
            data,
            f,
            ensure_ascii=False,
            indent=2
        )


# ============================================================
# ЗАГРУЗКА FLIBUSTA
# ============================================================

def get_page(url):

    last_error = None

    for attempt in range(1, MAX_RETRIES + 1):

        print(
            f"Загружаем страницу "
            f"(попытка {attempt}/{MAX_RETRIES}): {url}"
        )

        try:

            response = requests.get(
                url,
                headers=HEADERS,
                timeout=REQUEST_TIMEOUT
            )

            print("HTTP:", response.status_code)

            print(
                "Получено символов:",
                len(response.text)
            )

            response.raise_for_status()

            return BeautifulSoup(
                response.text,
                "html.parser"
            )

        except requests.exceptions.RequestException as e:

            last_error = e

            print("Ошибка:", e)

            if attempt < MAX_RETRIES:

                print(
                    "Повторяем через 3 секунды..."
                )

                time.sleep(3)

    raise last_error


# ============================================================
# ИМЯ АВТОРА
# ============================================================

def get_author_name(soup):

    h1 = soup.find("h1")

    if h1:

        text = h1.get_text(
            " ",
            strip=True
        )

        if text:

            if text.lower() not in (
                "флибуста",
                "книжное братство"
            ):

                return text

    title = soup.find("title")

    if title:

        text = title.get_text(
            " ",
            strip=True
        )

        for separator in (
            " | Флибуста",
            " — Флибуста",
            " - Флибуста",
        ):

            if separator in text:

                text = text.split(
                    separator,
                    1
                )[0].strip()

        if text:
            return text

    return "Неизвестный автор"


# ============================================================
# ID КНИГИ
# ============================================================

def get_book_id(href):

    if not href:
        return None

    match = re.search(
        r"/b/(\d+)",
        href
    )

    if match:
        return match.group(1)

    return None


# ============================================================
# НАЗВАНИЕ КНИГИ
# ============================================================

def clean_book_title(text):

    if not text:
        return ""

    text = re.sub(
        r"\s+",
        " ",
        text.strip()
    )

    bad_titles = {
        "читать",
        "скачать",
        "fb2",
        "epub",
        "mobi",
        "rtf",
        "txt",
        "pdf",
        "mail",
    }

    check = text.lower().strip()

    if check in bad_titles:
        return ""

    if check.strip("() ") in bad_titles:
        return ""

    if re.fullmatch(
        r"\((?:читать|скачать|fb2|epub|mobi|rtf|txt|pdf|mail)\)",
        check
    ):
        return ""

    return text


# ============================================================
# ПРОВЕРКА: ПОХОЖА ЛИ ССЫЛКА НА НАСТОЯЩУЮ КНИГУ
# ============================================================

def is_real_book_link(link):

    href = link.get("href", "")

    if not get_book_id(href):
        return False

    title = clean_book_title(
        link.get_text(
            " ",
            strip=True
        )
    )

    if len(title) < 2:
        return False

    # Ссылки "читать", "скачать", fb2 и т.п.
    # нам не нужны.
    if title.lower() in {
        "читать",
        "скачать",
        "fb2",
        "epub",
        "mobi",
        "rtf",
        "txt",
        "pdf",
    }:
        return False

    return True


# ============================================================
# ПОИСК ОСНОВНОГО БЛОКА КНИГ
# ============================================================

def find_books_container(soup):

    # --------------------------------------------------------
    # ВАЖНО:
    #
    # Мы НЕ ищем книги по всей странице.
    #
    # Сначала пытаемся найти участок страницы,
    # начинающийся около строки "Сортировать по".
    #
    # Именно там находится список книг автора.
    # --------------------------------------------------------

    sort_text = soup.find(
        string=lambda text:
        text and "Сортировать по" in text
    )

    if sort_text:

        # Поднимаемся вверх по DOM и ищем контейнер,
        # внутри которого находится список книг.
        current = sort_text.parent

        for _ in range(8):

            if current is None:
                break

            links = current.find_all(
                "a",
                href=True
            )

            book_count = 0

            for link in links:

                if get_book_id(
                    link.get("href", "")
                ):

                    title = clean_book_title(
                        link.get_text(
                            " ",
                            strip=True
                        )
                    )

                    if len(title) >= 2:
                        book_count += 1

            if book_count >= 3:

                print(
                    "Найден основной блок книг:",
                    current.name,
                    current.get("class", [])
                )

                return current

            current = current.parent

    return None


# ============================================================
# ПОИСК КНИГ АВТОРА
# ============================================================

def get_author_books(soup):

    container = find_books_container(
        soup
    )

    if container is None:

        print(
            "ОШИБКА: основной блок книг автора "
            "не найден."
        )

        return None

    candidate_links = []

    for link in container.find_all(
        "a",
        href=True
    ):

        if not is_real_book_link(link):
            continue

        candidate_links.append(link)

    print(
        "Кандидатов ссылок на книги:",
        len(candidate_links)
    )

    books = []
    seen_ids = set()

    for link in candidate_links:

        book_id = get_book_id(
            link.get("href", "")
        )

        if not book_id:
            continue

        if book_id in seen_ids:
            continue

        title = clean_book_title(
            link.get_text(
                " ",
                strip=True
            )
        )

        if not title:
            continue

        seen_ids.add(book_id)

        books.append({
            "id": str(book_id),
            "title": title
        })

    print(
        "Уникальных книг:",
        len(books)
    )

    return books


# ============================================================
# АВТОР
# ============================================================

def get_author_books_from_url(
    author_url
):

    soup = get_page(
        author_url
    )

    author_name = get_author_name(
        soup
    )

    books = get_author_books(
        soup
    )

    return author_name, books


# ============================================================
# TELEGRAM
# ============================================================

def send_message(text):

    if not TOKEN:

        print(
            "ОШИБКА: TELEGRAM_TOKEN не найден"
        )

        return False

    url = (
        "https://api.telegram.org/"
        f"bot{TOKEN}/sendMessage"
    )

    try:

        response = requests.post(
            url,
            data={
                "chat_id": CHAT_ID,
                "text": text,
            },
            timeout=30,
        )

        print(
            "Telegram:",
            response.text
        )

        return response.ok

    except Exception as e:

        print(
            "Ошибка Telegram:",
            e
        )

        return False


# ============================================================
# TELEGRAM-СООБЩЕНИЕ
# ============================================================

def make_message(
    author_name,
    new_books
):

    text = (
        "📚 Новые книги на Флибусте:\n\n"
        f"👤 Автор: {author_name}\n\n"
    )

    for book in new_books:

        text += (
            f"• {book['title']}\n"
        )

    return text


# ============================================================
# ПРОВЕРКА ОДНОГО АВТОРА
# ============================================================

def check_author(
    author_url,
    seen
):

    print()
    print("--------------------------------")
    print(
        "Проверяем:",
        author_url
    )
    print("--------------------------------")

    try:

        author_name, books = (
            get_author_books_from_url(
                author_url
            )
        )

        print(
            "Автор:",
            author_name
        )

        # ----------------------------------------------------
        # КРИТИЧЕСКАЯ ЗАЩИТА
        #
        # None означает:
        # "мы не смогли найти блок книг".
        #
        # В этом случае НЕ трогаем seen.json.
        # ----------------------------------------------------

        if books is None:

            print(
                "Список книг не удалось определить."
            )

            print(
                "Старый список НЕ изменяем."
            )

            return

        print(
            "Найдено книг:",
            len(books)
        )

        print(
            "Первые книги:",
            [
                b["title"]
                for b in books[:10]
            ]
        )

        # ----------------------------------------------------
        # Если список подозрительно маленький,
        # не обновляем базу.
        #
        # Это защита от неполной страницы.
        # ----------------------------------------------------

        if len(books) < 3:

            print(
                "Слишком мало книг найдено."
            )

            print(
                "Старый список НЕ изменяем."
            )

            return

        # ----------------------------------------------------
        # Первый запуск автора
        # ----------------------------------------------------

        old_books = seen.get(
            author_url
        )

        if old_books is None:

            print(
                "Первичная загрузка автора — "
                "уведомление не отправляем."
            )

            seen[author_url] = books

            return

        # ----------------------------------------------------
        # Старый формат seen.json
        # ----------------------------------------------------

        old_ids = set()
        old_titles = set()

        for item in old_books:

            if isinstance(
                item,
                dict
            ):

                book_id = item.get(
                    "id"
                )

                if book_id:
                    old_ids.add(
                        str(book_id)
                    )

                title = item.get(
                    "title"
                )

                if title:
                    old_titles.add(
                        title
                    )

            elif isinstance(
                item,
                str
            ):

                old_titles.add(
                    item
                )

        # ----------------------------------------------------
        # НОВЫЕ КНИГИ
        # ----------------------------------------------------

        new_books = []

        for book in books:

            book_id = str(
                book["id"]
            )

            title = book["title"]

            if book_id in old_ids:
                continue

            if title in old_titles:
                continue

            new_books.append(
                book
            )

        print(
            "Старых книг:",
            len(old_books)
        )

        print(
            "Новых книг:",
            len(new_books)
        )

        # ----------------------------------------------------
        # НОВЫЕ КНИГИ
        # ----------------------------------------------------

        if new_books:

            print(
                "Новые книги:"
            )

            for book in new_books:

                print(
                    " +",
                    book["title"],
                    f"(ID {book['id']})"
                )

            message = make_message(
                author_name,
                new_books
            )

            MAX_MESSAGE_LENGTH = 3500

            if len(message) <= MAX_MESSAGE_LENGTH:

                send_message(
                    message
                )

            else:

                current = (
                    "📚 Новые книги на "
                    "Флибусте:\n\n"
                    f"👤 Автор: "
                    f"{author_name}\n\n"
                )

                for book in new_books:

                    line = (
                        f"• {book['title']}\n"
                    )

                    if (
                        len(current)
                        + len(line)
                        > MAX_MESSAGE_LENGTH
                    ):

                        send_message(
                            current
                        )

                        time.sleep(1)

                        current = (
                            "📚 Продолжение:\n\n"
                            f"👤 Автор: "
                            f"{author_name}\n\n"
                        )

                    current += line

                if current.strip():

                    send_message(
                        current
                    )

        else:

            print(
                "Новых книг нет."
            )

        # ----------------------------------------------------
        # Обновляем seen только после успешного
        # определения нормального списка книг.
        # ----------------------------------------------------

        seen[author_url] = books

    except requests.exceptions.Timeout:

        print(
            "ОШИБКА: Flibusta не ответила "
            f"за {REQUEST_TIMEOUT} секунд."
        )

    except requests.exceptions.RequestException as e:

        print(
            "ОШИБКА соединения:",
            e
        )

    except Exception as e:

        print(
            "ОШИБКА:",
            e
        )


# ============================================================
# MAIN
# ============================================================

def main():

    print("================================")
    print("СТАРТ ПРОВЕРКИ")
    print("================================")

    authors = load_json(
        AUTHORS_FILE,
        []
    )

    seen = load_json(
        SEEN_FILE,
        {}
    )

    print(
        "Авторов:",
        len(authors)
    )

    for author_url in authors:

        check_author(
            author_url,
            seen
        )

        time.sleep(2)

    save_json(
        SEEN_FILE,
        seen
    )

    print()
    print("================================")
    print("ПРОВЕРКА ЗАВЕРШЕНА")
    print("================================")


# ============================================================
# START
# ============================================================

if __name__ == "__main__":
    main()
