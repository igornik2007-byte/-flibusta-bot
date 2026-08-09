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
            return json.load(f)
    except Exception:
        return {}


def save_seen(seen):
    with open(SEEN_FILE, "w", encoding="utf-8") as f:
        json.dump(seen, f, ensure_ascii=False, indent=2)


def get_page(author_url):
    response = requests.get(
        author_url,
        headers=HEADERS,
        timeout=30
    )

    response.raise_for_status()

    return BeautifulSoup(response.text, "html.parser")


def get_author_name(soup):
    for element in soup.find_all("h1"):
        name = element.get_text(" ", strip=True)

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
        name = title.get_text(" ", strip=True)

        for separator in [
            " | Флибуста",
            " — Флибуста",
            " - Флибуста"
        ]:
            if separator in name:
                name = name.split(separator)[0].strip()

        if name and name.lower() != "флибуста":
            return name

    return "Неизвестный автор"


def get_author_books(soup):
    """
    Получаем книги именно из списка книг автора.

    Важный момент:
    раньше мы делали soup.find_all("a", href=True)
    по всей странице.

    Из-за этого в список попадали книги из блока
    «Впечатления о книгах».

    Здесь сначала ищем основной контейнер страницы автора
    и исключаем боковые/дополнительные блоки.
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
    # 1. Сначала ищем ссылки на книги, которые находятся
    #    непосредственно в элементах списка/таблицы автора.
    # -------------------------------------------------

    candidates = []

    # Частый вариант структуры Flibusta:
    # книги находятся внутри li / tr / div,
    # а не в боковых блоках.
    for container in soup.find_all(["li", "tr", "div"]):

        links = container.find_all(
            "a",
            href=True,
            recursive=True
        )

        book_links = []

        for link in links:
            href = link.get("href", "")

            if "/b/" in href:
                book_links.append(link)

        # Нас интересуют небольшие контейнеры,
        # содержащие ссылку на книгу.
        if len(book_links) == 1:

            link = book_links[0]

            text = link.get_text(" ", strip=True)

            if not text:
                continue

            if text.lower() in bad_names:
                continue

            if text.startswith("("):
                continue

            candidates.append(link)

    # -------------------------------------------------
    # 2. Если нашли подходящие элементы — используем их.
    # -------------------------------------------------

    if candidates:

        for element in candidates:

            text = element.get_text(" ", strip=True)

            href = element.get("href", "")

            if not text:
                continue

            if "/b/" not in href:
                continue

            if text.lower() in bad_names:
                continue

            if text.startswith("("):
                continue

            if text not in books:
                books.append(text)

    # -------------------------------------------------
    # 3. Запасной вариант.
    #
    # Если структура страницы изменилась и предыдущий
    # способ ничего не нашёл, берём только ссылки,
    # которые находятся до блока «Впечатления о книгах».
    # -------------------------------------------------

    if not books:

        for element in soup.find_all(["h2", "h3"]):

            title = element.get_text(" ", strip=True).lower()

            if "впечатления о книгах" in title:
                break

        else:

            # Последний безопасный вариант:
            # собираем ссылки на книги, но исключаем
            # элементы, находящиеся внутри блоков,
            # явно связанных с впечатлениями/комментариями.

            for link in soup.find_all("a", href=True):

                href = link.get("href", "")
                text = link.get_text(" ", strip=True)

                if "/b/" not in href:
                    continue

                if not text:
                    continue

                if text.lower() in bad_names:
                    continue

                if text.startswith("("):
                    continue

                # Проверяем родителей ссылки.
                ignored = False

                for parent in link.parents:

                    if parent.name not in [
                        "div",
                        "section",
                        "article",
                        "aside",
                        "td",
                        "li"
                    ]:
                        continue

                    parent_text = parent.get_text(
                        " ",
                        strip=True
                    ).lower()

                    if (
                        "впечатления о книгах" in parent_text
                        or
                        "впечатления" in parent_text
                    ):
                        ignored = True
                        break

                if ignored:
                    continue

                if text not in books:
                    books.append(text)

    return books


def send_telegram(author_name, new_books):
    if not TELEGRAM_TOKEN:
        print("Ошибка: TELEGRAM_TOKEN не найден")
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
        f"https://api.telegram.org/bot"
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

        print("Telegram:", response.text)

        return response.ok

    except Exception as e:
        print("Ошибка Telegram:", e)
        return False


def check_author(author_url, seen):
    print(f"Проверяем: {author_url}")

    try:
        soup = get_page(author_url)

        author_name = get_author_name(soup)

        print(f"Автор: {author_name}")

        books = get_author_books(soup)

        print(f"Найдено книг: {len(books)}")

        if books:
            print("Первые книги:", books[:5])

        # -------------------------------------------------
        # Первый запуск автора.
        #
        # Сохраняем текущий список, но НЕ отправляем
        # уведомление обо всех старых книгах.
        # -------------------------------------------------

        if author_url not in seen:

            seen[author_url] = books

            print(
                "Первичная загрузка автора — "
                "уведомление не отправляем."
            )

            return

        old_books = seen.get(author_url, [])

        print(f"Старых книг: {len(old_books)}")

        new_books = [
            book for book in books
            if book not in old_books
        ]

        print(f"Новых книг: {len(new_books)}")

        if new_books:
            send_telegram(
                author_name,
                new_books
            )

        # Сохраняем актуальный список.
        seen[author_url] = books

    except Exception as e:

        print(
            f"Ошибка при проверке: {e}"
        )


def main():

    print("Старт проверки")

    authors = load_authors()

    print(f"Авторов: {len(authors)}")

    seen = load_seen()

    for author_url in authors:

        check_author(
            author_url,
            seen
        )

    save_seen(seen)

    print("Проверка завершена")


if __name__ == "__main__":
    main()
