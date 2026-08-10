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

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/139.0 Safari/537.36"
    )
}

TELEGRAM_LIMIT = 4000


# ============================================================
# JSON
# ============================================================

def load_json(filename, default):
    try:
        with open(filename, "r", encoding="utf-8") as f:
            return json.load(f)
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
# FLIBUSTA
# ============================================================

def get_page(url):
    print("Загружаем страницу:", url)

    response = requests.get(
        url,
        headers=HEADERS,
        timeout=REQUEST_TIMEOUT
    )

    print("HTTP:", response.status_code)
    print("Получено символов:", len(response.text))

    response.raise_for_status()

    return BeautifulSoup(
        response.text,
        "html.parser"
    )


def get_author_name(soup):
    """
    Определяем имя автора.

    На нормальной странице автора Flibusta имя находится
    в заголовке h1.
    """

    h1 = soup.find("h1")

    if h1:
        name = h1.get_text(" ", strip=True)

        if (
            name
            and name.lower() not in {
                "флибуста",
                "книжное братство"
            }
        ):
            return name

    title = soup.find("title")

    if title:
        name = title.get_text(" ", strip=True)

        for separator in (
            " | Флибуста",
            " — Флибуста",
            " - Флибуста",
        ):
            if separator in name:
                name = name.split(
                    separator,
                    1
                )[0].strip()

        if (
            name
            and name.lower() not in {
                "флибуста",
                "книжное братство"
            }
        ):
            return name

    return "Неизвестный автор"


# ============================================================
# ПОИСК ГРАНИЦЫ ОСНОВНОГО СПИСКА
# ============================================================

def find_impressions_element(soup):
    """
    Ищем блок «Впечатления о книгах».

    После него ссылки /b/ могут относиться уже
    к книгам других авторов.
    """

    for element in soup.find_all(
        [
            "h1",
            "h2",
            "h3",
            "h4",
            "h5",
            "h6",
            "div",
            "section",
            "aside",
            "strong",
            "p"
        ]
    ):
        text = element.get_text(
            " ",
            strip=True
        ).lower()

        if "впечатления о книгах" in text:
            return element

    return None


# ============================================================
# КНИГИ
# ============================================================

def is_book_link(link):
    """
    Настоящая книга Flibusta имеет URL:

        /b/123456

    """

    href = link.get("href", "")

    return bool(
        re.search(
            r"(?:^|/)b/\d+(?:[/?#]|$)",
            href
        )
    )


def clean_book_title(title):
    """
    Очищаем название книги от технического текста.
    """

    title = title.strip()

    # Убираем переводы строк и лишние пробелы
    title = re.sub(
        r"\s+",
        " ",
        title
    ).strip()

    # Технические ссылки
    technical = {
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

    # Если ссылка состоит только из технического текста
    normalized = title.lower()

    normalized = normalized.strip(
        " ()[]"
    )

    if normalized in technical:
        return None

    # Например:
    # "(читать)"
    # "(fb2)"
    # "(epub)"
    if re.fullmatch(
        r"\((?:читать|скачать|fb2|epub|mobi|rtf|txt|pdf|mail)\)",
        title,
        flags=re.IGNORECASE
    ):
        return None

    # Если название вообще состоит из скобок
    if title.startswith("(") and title.endswith(")"):
        return None

    return title


def get_author_books(soup):
    """
    Собираем книги автора.

    Не привязываемся к конкретному расположению H1.
    Сначала находим основной контейнер страницы,
    затем собираем ссылки /b/ID.

    Блок «Впечатления о книгах» отсекается.
    """

    impressions = find_impressions_element(soup)

    books = []
    book_ids = set()

    # Сначала находим все ссылки на книги
    for link in soup.find_all("a"):

        # Если ссылка находится внутри блока впечатлений,
        # пропускаем её.
        if impressions is not None:
            try:
                if impressions in link.parents:
                    continue
            except Exception:
                pass

        if not is_book_link(link):
            continue

        href = link.get("href", "")

        match = re.search(
            r"/b/(\d+)",
            href
        )

        if not match:
            continue

        book_id = match.group(1)

        title = link.get_text(
            " ",
            strip=True
        )

        title = clean_book_title(title)

        if not title:
            continue

        # Одна книга может иметь несколько технических
        # ссылок. Учитываем ID книги.
        if book_id in book_ids:
            continue

        book_ids.add(book_id)

        books.append(title)

    return books


def get_author_books_from_url(author_url):
    """
    Загружаем страницу конкретного автора.
    """

    soup = get_page(author_url)

    author_name = get_author_name(soup)

    books = get_author_books(soup)

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
        f"https://api.telegram.org/"
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


def send_long_message(text):
    """
    Telegram не принимает слишком длинные сообщения.
    Поэтому разбиваем сообщение примерно по 3500 символов.
    """

    if len(text) <= TELEGRAM_LIMIT:
        return send_message(text)

    parts = []

    current = ""

    for line in text.split("\n"):

        if len(current) + len(line) + 1 > 3500:

            if current:
                parts.append(
                    current
                )

            current = line

        else:

            if current:
                current += "\n"

            current += line

    if current:
        parts.append(current)

    print(
        "Сообщение слишком длинное."
    )

    print(
        "Отправляем частей:",
        len(parts)
    )

    success = True

    for part in parts:

        if not send_message(part):
            success = False

        time.sleep(1)

    return success


def make_message(
    author_name,
    books
):
    lines = [
        "📚 Новые книги на Флибусте:",
        "",
        f"👤 Автор: {author_name}",
        "",
    ]

    for book in books:
        lines.append(
            f"• {book}"
        )

    return "\n".join(lines)


# ============================================================
# ПРОВЕРКА
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

            print(
                "Найдено книг:",
                len(books)
            )

            print(
                "Первые книги:",
                books[:10]
            )

            # ------------------------------------------------
            # Защита от ошибочного ответа сайта
            # ------------------------------------------------

            if not books:

                print(
                    "Книги не найдены — "
                    "старый список не изменяем."
                )

                continue

            # ------------------------------------------------
            # Первый запуск автора
            # ------------------------------------------------

            old_books = seen.get(
                author_url
            )

            if old_books is None:

                print(
                    "Первичная загрузка автора — "
                    "уведомление не отправляем."
                )

                seen[author_url] = books

                continue

            # ------------------------------------------------
            # Ищем новые книги
            # ------------------------------------------------

            old_set = set(
                old_books
            )

            new_books = [
                book
                for book in books
                if book not in old_set
            ]

            print(
                "Старых книг:",
                len(old_books)
            )

            print(
                "Новых книг:",
                len(new_books)
            )

            # ------------------------------------------------
            # Отправляем уведомление
            # ------------------------------------------------

            if new_books:

                message = make_message(
                    author_name,
                    new_books
                )

                send_long_message(
                    message
                )

            # ------------------------------------------------
            # Обновляем базу
            # ------------------------------------------------

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
                repr(e)
            )

        time.sleep(1)

    # ========================================================
    # Сохраняем базу
    # ========================================================

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
