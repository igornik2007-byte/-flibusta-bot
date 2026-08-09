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
        json.dump(data, f, ensure_ascii=False, indent=2)


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

    response.raise_for_status()

    print("HTTP:", response.status_code)
    print("Получено символов:", len(response.text))

    return BeautifulSoup(response.text, "html.parser")


def get_author_name(soup):
    # Сначала пытаемся найти H1
    h1 = soup.find("h1")

    if h1:
        name = h1.get_text(" ", strip=True)

        if name:
            return name

    # Если H1 нет — пробуем title
    title = soup.find("title")

    if title:
        name = title.get_text(" ", strip=True)

        # Убираем хвосты Flibusta
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


def is_book_url(href):
    """
    Книга на Flibusta имеет URL примерно:

    /b/123456

    Важный момент:
    ссылки на авторов /a/
    сюда не попадут.
    """

    if not href:
        return False

    return bool(
        re.search(r"(?:^|/)b/\d+(?:[/?#]|$)", href)
    )


def clean_book_title(title):
    """
    Чистим название книги от лишних пробелов.
    """

    title = re.sub(r"\s+", " ", title)
    return title.strip()


def find_main_book_container(soup):
    """
    Пытаемся найти основной контейнер со списком книг автора.

    На Flibusta рядом с книгами может находиться боковой блок
    «Впечатления о книгах».

    Мы НЕ используем всю страницу целиком.
    """

    # --------------------------------------------------------
    # Вариант 1.
    # Ищем элемент, содержащий много ссылок /b/
    # --------------------------------------------------------

    candidates = []

    for tag in soup.find_all(["div", "section", "main", "article", "table"]):

        book_links = []

        for a in tag.find_all("a", href=True):
            if is_book_url(a.get("href")):
                book_links.append(a)

        if len(book_links) >= 2:
            candidates.append((len(book_links), tag))

    if candidates:
        # Берём наиболее подходящий контейнер.
        candidates.sort(key=lambda x: x[0], reverse=True)

        best = candidates[0][1]

        return best

    return None


def get_books_from_container(container):
    """
    Извлекает только ссылки /b/ из переданного контейнера.
    """

    books = []
    seen_urls = set()

    for a in container.find_all("a", href=True):

        href = a.get("href", "")

        if not is_book_url(href):
            continue

        # Нормализуем URL
        href_clean = href.split("#", 1)[0]

        if href_clean in seen_urls:
            continue

        seen_urls.add(href_clean)

        title = clean_book_title(
            a.get_text(" ", strip=True)
        )

        if not title:
            continue

        # Технические ссылки
        bad_titles = {
            "читать",
            "скачать",
            "mail",
            "fb2",
            "epub",
            "mobi",
            "rtf",
            "txt",
            "pdf",
        }

        if title.lower() in bad_titles:
            continue

        books.append({
            "title": title,
            "url": href_clean
        })

    return books


def remove_impressions_books(soup, books):
    """
    Дополнительная защита.

    Если ссылка на книгу находится внутри блока
    «Впечатления о книгах», она удаляется.
    """

    impression_links = set()

    # Ищем текстовый элемент с заголовком
    for tag in soup.find_all(
        ["h1", "h2", "h3", "h4", "h5", "h6",
         "div", "section", "aside", "strong", "span"]
    ):

        text = tag.get_text(" ", strip=True).lower()

        if text == "впечатления о книгах":

            # Идём вверх по дереву и ищем разумный контейнер.
            parent = tag.parent

            for _ in range(5):

                if parent is None:
                    break

                links = parent.find_all("a", href=True)

                book_links = [
                    a for a in links
                    if is_book_url(a.get("href", ""))
                ]

                if book_links:
                    for a in book_links:
                        impression_links.add(
                            a.get("href", "").split("#", 1)[0]
                        )

                    break

                parent = parent.parent

    result = []

    for book in books:

        if book["url"] not in impression_links:
            result.append(book)

    return result


def get_author_books(soup):
    """
    Главная функция поиска книг автора.

    Важная логика:

    1. Ищем контейнер основного списка.
    2. Берём только /b/ID.
    3. Удаляем ссылки из «Впечатления о книгах».
    4. Удаляем дубликаты.
    """

    container = find_main_book_container(soup)

    if container is None:
        print("Не удалось найти контейнер книг.")

        return []

    books = get_books_from_container(container)

    books = remove_impressions_books(
        soup,
        books
    )

    # Убираем дубликаты по URL
    result = []
    urls = set()

    for book in books:

        if book["url"] in urls:
            continue

        urls.add(book["url"])
        result.append(book)

    return result


def get_author_books_from_url(author_url):

    soup = get_page(author_url)

    author_name = get_author_name(soup)

    books = get_author_books(soup)

    return author_name, books


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

    text = (
        "📚 Новые книги на Флибусте:\n\n"
        f"👤 Автор: {author_name}\n\n"
    )

    for book in books:
        text += f"• {book['title']}\n"

    return text


# ============================================================
# ПРОВЕРКА АВТОРОВ
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

    print("Авторов:", len(authors))

    for author_url in authors:

        print()
        print("--------------------------------")
        print("Проверяем:", author_url)
        print("--------------------------------")

        try:

            author_name, books = get_author_books_from_url(
                author_url
            )

            print("Автор:", author_name)

            print(
                "Найдено книг:",
                len(books)
            )

            print(
                "Первые книги:",
                [
                    book["title"]
                    for book in books[:10]
                ]
            )

            # ------------------------------------------------
            # Если книг не нашли
            # ------------------------------------------------

            if not books:

                print(
                    "Книги не найдены."
                )

                print(
                    "Старый список НЕ изменяем."
                )

                continue

            # Сохраняем только URL книг
            current_books = [
                book["url"]
                for book in books
            ]

            # ------------------------------------------------
            # Первый запуск
            # ------------------------------------------------

            old_books = seen.get(author_url)

            if old_books is None:

                print(
                    "Первичная загрузка автора."
                )

                print(
                    "Уведомление НЕ отправляем."
                )

                seen[author_url] = current_books

                continue

            # ------------------------------------------------
            # Ищем новые книги
            # ------------------------------------------------

            new_urls = [
                url
                for url in current_books
                if url not in old_books
            ]

            print(
                "Старых книг:",
                len(old_books)
            )

            print(
                "Новых книг:",
                len(new_urls)
            )

            if new_urls:

                new_books = [
                    book
                    for book in books
                    if book["url"] in new_urls
                ]

                message = make_message(
                    author_name,
                    new_books
                )

                send_message(message)

            # ------------------------------------------------
            # Обновляем базу
            # ------------------------------------------------

            seen[author_url] = current_books

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
# START
# ============================================================

if __name__ == "__main__":
    main()
