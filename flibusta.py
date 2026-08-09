import os
import json
import requests
from bs4 import BeautifulSoup


AUTHORS_FILE = "authors.json"
SEEN_FILE = "seen_books.json"

TELEGRAM_TOKEN = os.environ.get("TELEGRAM_TOKEN")
CHAT_ID = "194667223"

HEADERS = {
    "User-Agent": "Mozilla/5.0"
}


def load_authors():
    with open(AUTHORS_FILE, "r", encoding="utf-8") as f:
        return json.load(f)


def load_seen():
    if not os.path.exists(SEEN_FILE):
        return {}

    try:
        with open(SEEN_FILE, "r", encoding="utf-8") as f:
            data = json.load(f)

            if isinstance(data, dict):
                return data

            return {}

    except Exception as e:
        print(f"Ошибка чтения {SEEN_FILE}: {e}")
        return {}


def save_seen(seen):
    with open(SEEN_FILE, "w", encoding="utf-8") as f:
        json.dump(
            seen,
            f,
            ensure_ascii=False,
            indent=2
        )


def get_page(author_url):
    response = requests.get(
        author_url,
        headers=HEADERS,
        timeout=30
    )

    response.raise_for_status()

    return BeautifulSoup(
        response.text,
        "html.parser"
    )


def get_author_name(soup):
    for element in soup.find_all("h1"):

        name = element.get_text(
            " ",
            strip=True
        )

        if not name:
            continue

        if name.lower() in {
            "флибуста",
            "книжное братство"
        }:
            continue

        return name

    title = soup.find("title")

    if title:

        name = title.get_text(
            " ",
            strip=True
        )

        for separator in [
            " | Флибуста",
            " — Флибуста",
            " - Флибуста"
        ]:

            if separator in name:
                name = name.split(
                    separator
                )[0].strip()

        if (
            name
            and
            name.lower() != "флибуста"
        ):
            return name

    return "Неизвестный автор"


def get_author_books(soup):
    """
    Получает книги именно из списка автора.

    ВАЖНО:

    Не используем soup.find_all("a", href=True)
    по всей странице.

    На странице Flibusta есть дополнительные блоки,
    например «Впечатления о книгах», где тоже имеются
    ссылки /b/.

    Поэтому сначала определяем основной список книг
    автора и исключаем боковые блоки.
    """

    books = []

    bad_names = {
        "(читать)",
        "(fb2)",
        "(epub)",
        "(mobi)",
        "(rtf)",
        "читать",
        "fb2",
        "epub",
        "mobi",
        "rtf",
        "скачать",
        "mail"
    }

    # -------------------------------------------------
    # Ищем основной контейнер со списком книг.
    #
    # На разных страницах Flibusta структура немного
    # отличается, поэтому пробуем несколько вариантов.
    # -------------------------------------------------

    main_container = None

    # Сначала пытаемся найти основной <main>.
    main = soup.find("main")

    if main is not None:
        main_container = main

    # Если <main> нет — пробуем article.
    if main_container is None:

        article = soup.find("article")

        if article is not None:
            main_container = article

    # Если ничего не нашли — ищем body.
    if main_container is None:

        body = soup.find("body")

        if body is not None:
            main_container = body

    if main_container is None:
        return books

    # -------------------------------------------------
    # Находим блок «Впечатления о книгах».
    # -------------------------------------------------

    impressions = None

    for element in main_container.find_all(
        ["h1", "h2", "h3", "h4", "h5", "div", "section", "aside"]
    ):

        text = element.get_text(
            " ",
            strip=True
        ).lower()

        if "впечатления о книгах" in text:

            impressions = element
            break

    # -------------------------------------------------
    # Находим ссылки на книги.
    # -------------------------------------------------

    for link in main_container.find_all(
        "a",
        href=True
    ):

        href = link.get("href", "")

        text = link.get_text(
            " ",
            strip=True
        )

        # Нам нужны только книги.
        if "/b/" not in href:
            continue

        if not text:
            continue

        if text.lower() in bad_names:
            continue

        if text.startswith("("):
            continue

        # -------------------------------------------------
        # Проверяем, не находится ли ссылка внутри блока
        # «Впечатления о книгах».
        # -------------------------------------------------

        inside_impressions = False

        if impressions is not None:

            for parent in link.parents:

                if parent is impressions:

                    inside_impressions = True
                    break

        if inside_impressions:
            continue

        # -------------------------------------------------
        # Исключаем ссылки из боковых блоков.
        # -------------------------------------------------

        bad_parent = False

        for parent in link.parents:

            if parent.name not in {
                "aside",
                "footer"
            }:
                continue

            parent_text = parent.get_text(
                " ",
                strip=True
            ).lower()

            if (
                "впечатления" in parent_text
                or
                "последние комментарии" in parent_text
                or
                "рекомендации" in parent_text
                or
                "популярные книги" in parent_text
            ):

                bad_parent = True
                break

        if bad_parent:
            continue

        # -------------------------------------------------
        # Убираем дубликаты.
        # -------------------------------------------------

        if text not in books:
            books.append(text)

    return books


def send_telegram(author_name, new_books):

    if not TELEGRAM_TOKEN:

        print(
            "Ошибка: TELEGRAM_TOKEN не найден"
        )

        return False

    if not new_books:
        return True

    message = (
        "📚 Новые книги на Флибусте:\n\n"
        f"👤 Автор: {author_name}\n\n"
    )

    for book in new_books:

        message += f"• {book}\n"

    url = (
        "https://api.telegram.org/bot"
        f"{TELEGRAM_TOKEN}/sendMessage"
    )

    data = {
        "chat_id": CHAT_ID,
        "text": message
    }

    try:

        response = requests.post(
            url,
            data=data,
            timeout=30
        )

        print(
            "Telegram:",
            response.text
        )

        return response.ok

    except Exception as e:

        print(
            f"Ошибка Telegram: {e}"
        )

        return False


def check_author(
    author_url,
    seen
):

    print(
        f"Проверяем: {author_url}"
    )

    try:

        soup = get_page(
            author_url
        )

        author_name = get_author_name(
            soup
        )

        print(
            f"Автор: {author_name}"
        )

        books = get_author_books(
            soup
        )

        print(
            f"Найдено книг: {len(books)}"
        )

        if books:

            print(
                "Первые книги:",
                books[:5]
            )

        # -------------------------------------------------
        # Если автор уже был в базе, сравниваем старый
        # список с новым.
        # -------------------------------------------------

        if author_url in seen:

            old_books = seen.get(
                author_url,
                []
            )

            print(
                f"Старых книг: {len(old_books)}"
            )

            new_books = [
                book
                for book in books
                if book not in old_books
            ]

            print(
                f"Новых книг: {len(new_books)}"
            )

            if new_books:

                send_telegram(
                    author_name,
                    new_books
                )

        else:

            # -------------------------------------------------
            # Первый запуск автора.
            #
            # Сохраняем текущий список.
            # Ничего в Telegram не отправляем.
            # -------------------------------------------------

            print(
                "Первичная загрузка автора — "
                "уведомление не отправляем."
            )

        # -------------------------------------------------
        # В любом случае сохраняем актуальный список.
        # -------------------------------------------------

        seen[author_url] = books

    except requests.exceptions.Timeout:

        print(
            "Ошибка: сайт Flibusta не ответил "
            "за 30 секунд."
        )

    except requests.exceptions.RequestException as e:

        print(
            f"Ошибка соединения: {e}"
        )

    except Exception as e:

        print(
            f"Ошибка при проверке: {e}"
        )


def main():

    print(
        "Старт проверки"
    )

    authors = load_authors()

    print(
        f"Авторов: {len(authors)}"
    )

    seen = load_seen()

    for author_url in authors:

        check_author(
            author_url,
            seen
        )

    save_seen(
        seen
    )

    print(
        "Проверка завершена"
    )


if __name__ == "__main__":
    main()
