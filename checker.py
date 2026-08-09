import os
import json
import re
import time

import requests
from bs4 import BeautifulSoup


# ------------------------------------------------------------
# НАСТРОЙКИ
# ------------------------------------------------------------

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


# ------------------------------------------------------------
# JSON
# ------------------------------------------------------------

def load_json(filename, default):
    try:
        with open(filename, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception as e:
        print(f"Ошибка чтения {filename}: {e}")
        return default


def save_json(filename, data):
    with open(filename, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)


# ------------------------------------------------------------
# FLIBUSTA
# ------------------------------------------------------------

def get_page(url):
    """
    Загружает именно страницу конкретного автора.
    ВАЖНО: URL передаётся непосредственно requests.get(),
    поэтому список книг не может случайно взяться от другого автора.
    """
    response = requests.get(
        url,
        headers=HEADERS,
        timeout=REQUEST_TIMEOUT
    )
    response.raise_for_status()

    return BeautifulSoup(response.text, "html.parser")


def get_author_name(soup):
    h1 = soup.find("h1")

    if h1:
        name = h1.get_text(" ", strip=True)
        if name and name.lower() not in {"флибуста", "книжное братство"}:
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
                name = name.split(separator, 1)[0].strip()

        if name:
            return name

    return "Неизвестный автор"


def is_book_link(link):
    """
    Книга на Flibusta имеет ссылку вида /b/12345.
    Ссылки на жанры, авторов, серии и т.п. сюда не попадут.
    """
    href = link.get("href", "")

    return bool(
        re.search(r"/b/\d+(?:[/?#]|$)", href)
    )


def find_impressions_boundary(soup):
    """
    На странице автора есть боковой блок
    «Впечатления о книгах».

    В нём тоже встречаются ссылки /b/ на книги других авторов.
    Поэтому после этого заголовка ссылки больше НЕ рассматриваем.
    """

    for element in soup.find_all(
        ["h1", "h2", "h3", "h4", "h5", "h6",
         "div", "section", "aside", "strong"]
    ):
        text = element.get_text(" ", strip=True).lower()

        if "впечатления о книгах" in text:
            return element

    return None


def get_author_books(soup):
    """
    Возвращает только книги из основного списка данного автора.

    Главный принцип:
    1. начинаем после H1 с именем автора;
    2. берём только ссылки /b/ID;
    3. прекращаем сбор перед блоком «Впечатления о книгах»;
    4. не используем поиск по всей странице после этого блока.
    """

    books = []

    author_h1 = soup.find("h1")
    impressions = find_impressions_boundary(soup)

    started = author_h1 is None

    for element in soup.find_all(["a", "h1", "h2", "h3", "h4", "h5", "h6",
                                  "div", "section", "aside", "strong"]):

        # Дошли до блока с отзывами/впечатлениями —
        # дальше книги не принадлежат основному списку автора.
        if impressions is not None and element is impressions:
            break

        if not started:
            if element is author_h1:
                started = True
            continue

        if element.name != "a":
            continue

        if not is_book_link(element):
            continue

        title = element.get_text(" ", strip=True)

        if not title:
            continue

        # Убираем технические ссылки, если вдруг встретятся.
        bad_titles = {
            "читать",
            "скачать",
            "fb2",
            "epub",
            "mobi",
            "rtf",
            "mail",
        }

        if title.lower() in bad_titles:
            continue

        if title.startswith("("):
            continue

        # Один и тот же title может встречаться несколько раз
        # в разных представлениях книги.
        if title not in books:
            books.append(title)

    return books


def get_author_books_from_url(author_url):
    """
    ВАЖНО:
    Эта функция получает URL конкретного автора и сама загружает
    его страницу. Никаких общих/заранее загруженных soup здесь нет.
    """

    soup = get_page(author_url)

    author_name = get_author_name(soup)
    books = get_author_books(soup)

    return author_name, books


# ------------------------------------------------------------
# TELEGRAM
# ------------------------------------------------------------

def send_message(text):
    if not TOKEN:
        print("ОШИБКА: TELEGRAM_TOKEN не найден")
        return False

    url = f"https://api.telegram.org/bot{TOKEN}/sendMessage"

    try:
        response = requests.post(
            url,
            data={
                "chat_id": CHAT_ID,
                "text": text,
            },
            timeout=30,
        )

        print("Telegram:", response.text)

        return response.ok

    except Exception as e:
        print("Ошибка Telegram:", e)
        return False


def make_message(author_name, books):
    return (
        "📚 Новые книги на Флибусте:\n\n"
        f"👤 Автор: {author_name}\n\n"
        + "\n".join(f"• {book}" for book in books)
    )


# ------------------------------------------------------------
# ПРОВЕРКА
# ------------------------------------------------------------

def main():
    print("Старт проверки")

    authors = load_json(AUTHORS_FILE, [])
    seen = load_json(SEEN_FILE, {})

    print("Авторов:", len(authors))

    for author_url in authors:

        print()
        print("Проверяем:", author_url)

        try:
            author_name, books = get_author_books_from_url(author_url)

            print("Автор:", author_name)
            print("Найдено книг:", len(books))
            print("Первые книги:", books[:5])

            # Если страница вдруг вернула 0 книг,
            # НЕ перезаписываем старую базу пустым списком.
            # Это защищает от временной ошибки сайта.
            if not books:
                print(
                    "Книги не найдены — старый список "
                    "не изменяем."
                )
                continue

            old_books = seen.get(author_url)

            # Первый запуск конкретного автора:
            # просто запоминаем текущий список.
            if old_books is None:
                print(
                    "Первичная загрузка автора — "
                    "уведомление не отправляем."
                )

                seen[author_url] = books
                continue

            new_books = [
                book
                for book in books
                if book not in old_books
            ]

            print("Старых книг:", len(old_books))
            print("Новых книг:", len(new_books))

            if new_books:
                message = make_message(
                    author_name,
                    new_books
                )
                send_message(message)

            seen[author_url] = books

        except requests.exceptions.Timeout:
            print(
                "Ошибка: Flibusta не ответила "
                f"за {REQUEST_TIMEOUT} секунд."
            )

        except requests.exceptions.RequestException as e:
            print("Ошибка соединения:", e)

        except Exception as e:
            print("Ошибка при проверке:", e)

        # Небольшая пауза между авторами,
        # чтобы не делать пять запросов одновременно.
        time.sleep(1)

    save_json(SEEN_FILE, seen)

    print()
    print("Проверка завершена")


if __name__ == "__main__":
    main()
