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

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/139.0 Safari/537.36"
    )
}

REQUEST_TIMEOUT = 45

# Пауза между запросами к Flibusta
REQUEST_DELAY = 0.4

# Telegram разрешает около 4096 символов.
# Оставляем запас.
TELEGRAM_LIMIT = 3800


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
# HTTP
# ============================================================

session = requests.Session()
session.headers.update(HEADERS)


def get_page(url):
    print(f"Загружаем страницу: {url}")

    response = session.get(
        url,
        timeout=REQUEST_TIMEOUT
    )

    print("HTTP:", response.status_code)
    print("Получено символов:", len(response.text))

    response.raise_for_status()

    time.sleep(REQUEST_DELAY)

    return BeautifulSoup(
        response.text,
        "html.parser"
    )


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

        if name:
            if name.lower() not in {
                "флибуста",
                "книжное братство"
            }:
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
# ССЫЛКИ НА КНИГИ
# ============================================================

def is_book_link(link):
    href = link.get("href", "")

    return bool(
        re.search(
            r"/b/\d+(?:[/?#]|$)",
            href
        )
    )


def normalize_url(href):
    if href.startswith("http://"):
        return href

    if href.startswith("https://"):
        return href

    if href.startswith("//"):
        return "https:" + href

    if href.startswith("/"):
        return "https://flibusta.is" + href

    return "https://flibusta.is/" + href


# ============================================================
# БЛОК "ВПЕЧАТЛЕНИЯ"
# ============================================================

def find_impressions_boundary(soup):

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
            "strong"
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
# КНИГИ СО СТРАНИЦЫ АВТОРА
# ============================================================

def get_candidate_books(soup):

    candidates = []

    author_h1 = soup.find("h1")
    impressions = find_impressions_boundary(soup)

    started = author_h1 is None

    for element in soup.find_all(
        [
            "a",
            "h1",
            "h2",
            "h3",
            "h4",
            "h5",
            "h6",
            "div",
            "section",
            "aside",
            "strong"
        ]
    ):

        # Не заходим в блок впечатлений.
        if (
            impressions is not None
            and element is impressions
        ):
            break

        if not started:

            if element is author_h1:
                started = True

            continue

        if element.name != "a":
            continue

        if not is_book_link(element):
            continue

        title = element.get_text(
            " ",
            strip=True
        )

        href = element.get("href", "")

        if not title or not href:
            continue

        # Технические ссылки
        bad_titles = {
            "читать",
            "скачать",
            "fb2",
            "epub",
            "mobi",
            "rtf",
            "mail"
        }

        if title.lower() in bad_titles:
            continue

        if title.startswith("("):
            continue

        book_url = normalize_url(href)

        candidates.append({
            "title": title,
            "url": book_url
        })

    # Убираем дубликаты по URL
    result = []
    seen_urls = set()

    for item in candidates:

        if item["url"] in seen_urls:
            continue

        seen_urls.add(item["url"])
        result.append(item)

    return result


# ============================================================
# НОРМАЛИЗАЦИЯ ИМЁН
# ============================================================

def normalize_name(name):
    name = name.lower()

    name = name.replace(
        "ё",
        "е"
    )

    name = re.sub(
        r"\s+",
        " ",
        name
    )

    name = re.sub(
        r"[.,;:!?\"'«»()]+",
        " ",
        name
    )

    return name.strip()


def names_match(book_author, current_author):

    a = normalize_name(book_author)
    b = normalize_name(current_author)

    if not a or not b:
        return False

    # Полное совпадение
    if a == b:
        return True

    # Один вариант содержит другой
    if a in b or b in a:
        return True

    # Сравнение по отдельным словам
    a_words = set(a.split())
    b_words = set(b.split())

    if len(a_words) >= 2 and len(b_words) >= 2:
        common = a_words & b_words

        if len(common) >= 2:
            return True

    return False


# ============================================================
# АВТОРЫ НА СТРАНИЦЕ КНИГИ
# ============================================================

def extract_book_authors(soup):

    authors = []

    # --------------------------------------------------------
    # Вариант 1.
    # Ищем ссылки на страницы авторов.
    # --------------------------------------------------------

    for link in soup.find_all("a"):

        href = link.get(
            "href",
            ""
        )

        text = link.get_text(
            " ",
            strip=True
        )

        if not text:
            continue

        # Авторские страницы Flibusta обычно имеют /a/ID
        if re.search(
            r"/a/\d+(?:[/?#]|$)",
            href
        ):
            if text not in authors:
                authors.append(text)

    # --------------------------------------------------------
    # Вариант 2.
    # Ищем текстовые элементы рядом с "Автор".
    # --------------------------------------------------------

    for element in soup.find_all(
        [
            "div",
            "span",
            "p",
            "td",
            "li",
            "dt",
            "dd"
        ]
    ):

        text = element.get_text(
            " ",
            strip=True
        )

        if not text:
            continue

        lower = text.lower()

        if (
            lower.startswith("автор:")
            or lower.startswith("авторы:")
        ):

            value = re.sub(
                r"^автор(?:ы)?\s*:\s*",
                "",
                text,
                flags=re.IGNORECASE
            ).strip()

            if value and value not in authors:
                authors.append(value)

    return authors


# ============================================================
# ПРОВЕРКА ПРИНАДЛЕЖНОСТИ КНИГИ АВТОРУ
# ============================================================

def book_belongs_to_author(book_url, author_name):

    try:

        soup = get_page(book_url)

        book_authors = extract_book_authors(
            soup
        )

        if not book_authors:

            print(
                "  ⚠ Авторы книги не определены:",
                book_url
            )

            return False

        print(
            "  Авторы книги:",
            book_authors
        )

        for book_author in book_authors:

            if names_match(
                book_author,
                author_name
            ):
                return True

        return False

    except requests.exceptions.RequestException as e:

        print(
            "  ⚠ Ошибка страницы книги:",
            e
        )

        # При ошибке НЕ считаем книгу принадлежащей автору.
        return False

    except Exception as e:

        print(
            "  ⚠ Ошибка разбора книги:",
            e
        )

        return False


# ============================================================
# ПОЛУЧЕНИЕ КНИГ КОНКРЕТНОГО АВТОРА
# ============================================================

def get_author_books_from_url(author_url):

    soup = get_page(
        author_url
    )

    author_name = get_author_name(
        soup
    )

    candidates = get_candidate_books(
        soup
    )

    print(
        "Кандидатов книг:",
        len(candidates)
    )

    books = []

    for index, book in enumerate(
        candidates,
        start=1
    ):

        print(
            f"Проверяем книгу "
            f"{index}/{len(candidates)}: "
            f"{book['title']}"
        )

        if book_belongs_to_author(
            book["url"],
            author_name
        ):

            books.append(
                book["title"]
            )

            print(
                "  ✓ Книга принадлежит автору"
            )

        else:

            print(
                "  ✗ Книга НЕ принадлежит автору"
            )

    # Убираем дубликаты названий,
    # сохраняя порядок.
    unique_books = []

    for title in books:

        if title not in unique_books:
            unique_books.append(title)

    return author_name, unique_books


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

        response = session.post(
            url,
            data={
                "chat_id": CHAT_ID,
                "text": text
            },
            timeout=30
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


def send_new_books(
    author_name,
    new_books
):

    if not new_books:
        return

    header = (
        "📚 Новые книги на Флибусте:\n\n"
        f"👤 Автор: {author_name}\n\n"
    )

    current = header

    for book in new_books:

        line = f"• {book}\n"

        # Если сообщение почти достигло лимита,
        # отправляем текущую часть.
        if (
            len(current) + len(line)
            > TELEGRAM_LIMIT
        ):

            send_message(
                current.rstrip()
            )

            current = (
                "📚 Новые книги "
                "на Флибусте:\n\n"
                f"👤 Автор: {author_name}\n\n"
            )

        current += line

    if current.strip():

        send_message(
            current.rstrip()
        )


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
            # Защита от неправильной страницы / ошибки
            # ------------------------------------------------

            if not books:

                print(
                    "Книги не найдены — "
                    "старый список не изменяем."
                )

                continue

            old_books = seen.get(
                author_url
            )

            # ------------------------------------------------
            # Первый запуск автора
            # ------------------------------------------------

            if old_books is None:

                print(
                    "Первичная загрузка автора — "
                    "уведомление не отправляем."
                )

                seen[author_url] = books

                continue

            # ------------------------------------------------
            # Новые книги
            # ------------------------------------------------

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

            if new_books:

                print(
                    "Новые книги:",
                    new_books
                )

                send_new_books(
                    author_name,
                    new_books
                )

            else:

                print(
                    "Новых книг нет."
                )

            # Обновляем базу только после
            # успешного получения нормального списка.
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

        # Пауза между авторами
        time.sleep(1)

    save_json(
        SEEN_FILE,
        seen
    )

    print()
    print("================================")
    print("ПРОВЕРКА ЗАВЕРШЕНА")
    print("================================")


# ============================================================
# ЗАПУСК
# ============================================================

if __name__ == "__main__":
    main()
