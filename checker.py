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
RETRIES = 3

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/139.0 Safari/537.36"
    ),
    "Accept": (
        "text/html,application/xhtml+xml,"
        "application/xml;q=0.9,image/avif,image/webp,*/*;q=0.8"
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
# FLIBUSTA
# ============================================================

def get_page(url):
    """
    Загружает страницу автора.

    При временных ошибках 502/503/504
    делает несколько повторных попыток.
    """

    last_error = None

    for attempt in range(1, RETRIES + 1):

        try:
            print(
                f"Загружаем страницу "
                f"(попытка {attempt}/{RETRIES}): {url}"
            )

            response = requests.get(
                url,
                headers=HEADERS,
                timeout=REQUEST_TIMEOUT
            )

            print("HTTP:", response.status_code)

            response.raise_for_status()

            print(
                "Получено символов:",
                len(response.text)
            )

            return BeautifulSoup(
                response.text,
                "html.parser"
            )

        except requests.exceptions.RequestException as e:

            last_error = e

            print("Ошибка:", e)

            if attempt < RETRIES:
                print("Повтор через 5 секунд...")
                time.sleep(5)

    raise last_error


# ============================================================
# АВТОР
# ============================================================

def get_author_name(soup):

    h1 = soup.find("h1")

    if h1:
        name = h1.get_text(
            " ",
            strip=True
        )

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
        name = title.get_text(
            " ",
            strip=True
        )

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

        if name:
            return name

    return "Неизвестный автор"


# ============================================================
# КНИГИ
# ============================================================

BOOK_RE = re.compile(
    r"(?:^|/)b/(\d+)(?:[/?#]|$)"
)


BAD_TITLES = {
    "читать",
    "скачать",
    "fb2",
    "epub",
    "mobi",
    "rtf",
    "txt",
    "pdf",
    "mail",
    "открыть",
}


def is_book_link(href):
    if not href:
        return False

    return bool(
        BOOK_RE.search(href)
    )


def clean_book_title(title):
    """
    Приводит название книги к нормальному виду.
    """

    title = title.strip()

    # Убираем лишние пробелы
    title = re.sub(
        r"\s+",
        " ",
        title
    )

    # Убираем технические варианты
    title_lower = title.lower()

    if title_lower in BAD_TITLES:
        return None

    # Варианты вроде "(читать)"
    if (
        title.startswith("(")
        and title.endswith(")")
    ):
        return None

    return title


def find_impressions_boundary(soup):
    """
    Ищем блок «Впечатления о книгах».

    Всё, что находится после него,
    не считаем книгами автора.
    """

    # Сначала ищем элементы с точным/частичным текстом.
    for tag in soup.find_all(
        [
            "h1",
            "h2",
            "h3",
            "h4",
            "h5",
            "h6",
            "strong",
            "div",
            "section",
            "aside",
        ]
    ):

        text = tag.get_text(
            " ",
            strip=True
        ).lower()

        if "впечатления о книгах" in text:
            return tag

    return None


def get_author_books(soup):
    """
    Извлекает книги автора.

    Основной критерий книги:
        ссылка /b/12345

    При этом:
    - исключаем технические ссылки;
    - удаляем дубли;
    - не берём книги из блока
      «Впечатления о книгах».
    """

    author_h1 = soup.find("h1")
    boundary = find_impressions_boundary(soup)

    books = []
    seen_titles = set()

    # --------------------------------------------------------
    # Определяем порядковые позиции элементов.
    #
    # Это надёжнее, чем пытаться сравнивать сами Tag-объекты.
    # --------------------------------------------------------

    all_elements = soup.find_all(True)

    h1_position = -1
    boundary_position = len(all_elements)

    if author_h1 is not None:

        for i, element in enumerate(all_elements):

            if element is author_h1:
                h1_position = i
                break

    if boundary is not None:

        for i, element in enumerate(all_elements):

            if element is boundary:
                boundary_position = i
                break

    # --------------------------------------------------------
    # Если H1 не найден, начинаем с начала страницы.
    # --------------------------------------------------------

    for i, element in enumerate(all_elements):

        # До имени автора не идём.
        if i <= h1_position:
            continue

        # После блока впечатлений не идём.
        if i >= boundary_position:
            break

        if element.name != "a":
            continue

        href = element.get(
            "href",
            ""
        )

        if not is_book_link(href):
            continue

        title = element.get_text(
            " ",
            strip=True
        )

        title = clean_book_title(title)

        if not title:
            continue

        # ----------------------------------------------------
        # Иногда одна книга имеет несколько одинаковых ссылок.
        # ----------------------------------------------------

        if title in seen_titles:
            continue

        seen_titles.add(title)
        books.append(title)

    return books


def get_author_books_from_url(author_url):

    soup = get_page(author_url)

    author_name = get_author_name(soup)

    books = get_author_books(soup)

    print(
        "Кандидатов книг:",
        len(books)
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


def send_long_message(text):
    """
    Telegram разрешает примерно 4096 символов
    в одном сообщении.

    Поэтому длинный список книг
    разбиваем на несколько сообщений.
    """

    MAX_LENGTH = 3800

    if len(text) <= MAX_LENGTH:
        return send_message(text)

    parts = []
    current = ""

    for line in text.splitlines(True):

        if len(current) + len(line) > MAX_LENGTH:

            if current:
                parts.append(current)

            current = line

        else:
            current += line

    if current:
        parts.append(current)

    success = True

    for part in parts:

        if not send_message(part):
            success = False

        time.sleep(1)

    return success


def make_message(
    author_name,
    new_books
):

    lines = [
        "📚 Новые книги на Флибусте:",
        "",
        f"👤 Автор: {author_name}",
        "",
    ]

    for book in new_books:
        lines.append(
            f"• {book}"
        )

    return "\n".join(lines)


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

        print(
            "Найдено книг:",
            len(books)
        )

        print(
            "Первые книги:",
            books[:10]
        )

        # ----------------------------------------------------
        # Защита от ситуации,
        # когда сайт отдал кривую страницу.
        # ----------------------------------------------------

        if not books:

            print(
                "Книги не найдены — "
                "старый список не изменяем."
            )

            return

        old_books = seen.get(
            author_url
        )

        # ----------------------------------------------------
        # Первый запуск автора.
        # ----------------------------------------------------

        if old_books is None:

            print(
                "Первичная загрузка автора — "
                "уведомление не отправляем."
            )

            seen[author_url] = books

            return

        # ----------------------------------------------------
        # Ищем только новые названия.
        # ----------------------------------------------------

        new_books = [
            book
            for book in books
            if book not in old_books
        ]

        print(
            "Старых книг:",
            len(old_books)
        )

        print(
            "Новых книг:",
            len(new_books)
        )

        # ----------------------------------------------------
        # ВАЖНО:
        # если новых книг нет — Telegram не трогаем.
        # ----------------------------------------------------

        if not new_books:

            print(
                "Новых книг нет."
            )

            # Обновляем базу на случай изменения
            # порядка книг.
            seen[author_url] = books

            return

        print(
            "Отправляем новые книги:"
        )

        for book in new_books:
            print(
                "  +",
                book
            )

        message = make_message(
            author_name,
            new_books
        )

        send_long_message(message)

        # ----------------------------------------------------
        # После успешной проверки сохраняем
        # полный актуальный список.
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
            type(e).__name__,
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

        # Небольшая пауза между авторами.
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
