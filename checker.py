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
    """
    Не используем soup.find("h1"),
    потому что на некоторых страницах первым H1
    может оказаться элемент сайта.

    На странице автора Flibusta название автора
    присутствует в <title>.
    """

    title = soup.find("title")

    if title:
        text = title.get_text(" ", strip=True)

        # Например:
        # Ник Перумов | Флибуста

        for separator in (
            "| Флибуста",
            "— Флибуста",
            "- Флибуста",
        ):
            if separator in text:
                text = text.split(separator, 1)[0].strip()

        if text:
            return text

    # Запасной вариант:
    for h in soup.find_all("h1"):
        text = h.get_text(" ", strip=True)

        if text and text.lower() not in {
            "флибуста",
            "книжное братство"
        }:
            return text

    return "Неизвестный автор"


# ============================================================
# ПОИСК ОСНОВНОГО СПИСКА КНИГ
# ============================================================

def is_book_href(href):
    """
    Настоящая ссылка на книгу имеет вид:

        /b/123456

    Но ссылки "читать", "fb2", "epub", "mobi"
    тоже могут вести в /b/....

    Поэтому одной проверки href недостаточно.
    """

    if not href:
        return False

    return bool(
        re.search(
            r"/b/\d+(?:[/?#]|$)",
            href
        )
    )


def looks_like_format_link(text):
    """
    Отбрасываем ссылки форматов и служебные ссылки.
    """

    text = text.strip().lower()

    bad = {
        "(читать)",
        "читать",
        "(fb2)",
        "fb2",
        "(epub)",
        "epub",
        "(mobi)",
        "mobi",
        "(rtf)",
        "rtf",
        "(txt)",
        "txt",
        "(pdf)",
        "pdf",
        "mail",
        "(mail)",
        "скачать",
    }

    return text in bad


def get_real_book_links(soup):
    """
    На странице Flibusta структура примерно такая:

        [название книги] [читать] [fb2] [epub] [mobi]

    Все эти ссылки могут вести на одну книгу.

    Нас интересует только ссылка с НАЗВАНИЕМ книги.

    Отличаем её от служебных ссылок по тексту.
    """

    books = []
    seen_urls = set()

    for a in soup.find_all("a", href=True):

        href = a.get("href", "")
        text = a.get_text(" ", strip=True)

        if not is_book_href(href):
            continue

        if not text:
            continue

        if looks_like_format_link(text):
            continue

        # Ссылки "читать" и форматы уже отсеяны.
        #
        # Дополнительная защита от ссылок,
        # содержащих только скобки.

        if text.startswith("(") and text.endswith(")"):
            continue

        # Нормализуем URL
        clean_url = href.split("#", 1)[0]

        # Если одна и та же книга уже встретилась —
        # не добавляем её второй раз.
        if clean_url in seen_urls:
            continue

        seen_urls.add(clean_url)

        books.append({
            "title": text,
            "url": clean_url
        })

    return books


def remove_impressions_section(soup, books):
    """
    Боковой блок:

        Впечатления о книгах

    содержит ссылки на книги совершенно других авторов.

    Ищем этот блок и запоминаем ссылки на книги,
    которые находятся внутри него.
    """

    impression_urls = set()

    # Ищем текст именно заголовка.
    for tag in soup.find_all(
        ["h1", "h2", "h3", "h4", "h5", "h6",
         "div", "section", "aside", "strong", "span"]
    ):

        text = re.sub(
            r"\s+",
            " ",
            tag.get_text(" ", strip=True)
        ).strip().lower()

        if text != "впечатления о книгах":
            continue

        # Поднимаемся по DOM.
        parent = tag.parent

        for _ in range(6):

            if parent is None:
                break

            links = parent.find_all("a", href=True)

            found = False

            for a in links:

                href = a.get("href", "")

                if is_book_href(href):

                    impression_urls.add(
                        href.split("#", 1)[0]
                    )

                    found = True

            if found:
                break

            parent = parent.parent

    result = []

    for book in books:

        if book["url"] not in impression_urls:
            result.append(book)

    return result


def get_author_books(soup):
    """
    Получаем книги автора.

    Важно:
    - не берём ссылки "читать";
    - не берём fb2/epub/mobi;
    - не берём книги из блока впечатлений;
    - сохраняем URL книги, а не только название.
    """

    books = get_real_book_links(soup)

    print(
        "Книг до удаления блока впечатлений:",
        len(books)
    )

    books = remove_impressions_section(
        soup,
        books
    )

    print(
        "Книг после удаления блока впечатлений:",
        len(books)
    )

    # Финальная защита от дублей
    result = []
    seen = set()

    for book in books:

        if book["url"] in seen:
            continue

        seen.add(book["url"])
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


def make_message(author_name, books):

    lines = [
        "📚 Новые книги на Флибусте:",
        "",
        f"👤 Автор: {author_name}",
        ""
    ]

    for book in books:
        lines.append(
            f"• {book['title']}"
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
                [
                    book["title"]
                    for book in books[:10]
                ]
            )

            # ------------------------------------------------
            # Защита от неправильной страницы
            # ------------------------------------------------

            if not books:

                print(
                    "Книги не найдены."
                )

                print(
                    "Старый список НЕ изменяем."
                )

                continue

            # Сохраняем URL
            current_urls = [
                book["url"]
                for book in books
            ]

            # ------------------------------------------------
            # Первый запуск
            # ------------------------------------------------

            old_urls = seen.get(
                author_url
            )

            if old_urls is None:

                print(
                    "Первичная загрузка автора — "
                    "уведомление не отправляем."
                )

                seen[author_url] = current_urls

                continue

            # ------------------------------------------------
            # Новые книги
            # ------------------------------------------------

            new_urls = [
                url
                for url in current_urls
                if url not in old_urls
            ]

            print(
                "Старых книг:",
                len(old_urls)
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

                # Telegram ограничивает сообщение
                # примерно 4096 символами.
                #
                # Если книг много — отправляем
                # несколькими сообщениями.

                MAX_LENGTH = 3500

                if len(message) <= MAX_LENGTH:

                    send_message(message)

                else:

                    print(
                        "Сообщение слишком большое — "
                        "разбиваем на части."
                    )

                    header = (
                        "📚 Новые книги на Флибусте:\n\n"
                        f"👤 Автор: {author_name}\n\n"
                    )

                    chunk = header

                    for book in new_books:

                        line = (
                            f"• {book['title']}\n"
                        )

                        if (
                            len(chunk) +
                            len(line)
                        ) > MAX_LENGTH:

                            send_message(chunk)

                            time.sleep(1)

                            chunk = (
                                f"📚 Продолжение — "
                                f"{author_name}:\n\n"
                            )

                        chunk += line

                    if chunk.strip():

                        send_message(chunk)

            # ------------------------------------------------
            # Обновляем базу
            # ------------------------------------------------

            seen[author_url] = current_urls

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

        time.sleep(2)

    save_json(
        SEEN_FILE,
        seen
    )

    print()
    print("================================")
    print("ПРОВЕРКА ЗАВЕРШЕНА")
    print("================================")


if __name__ == "__main__":
    main()
