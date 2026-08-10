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

# Telegram позволяет около 4096 символов.
# Оставляем запас.
TELEGRAM_LIMIT = 3500

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/139.0 Safari/537.36"
    ),
    "Accept": (
        "text/html,application/xhtml+xml,"
        "application/xml;q=0.9,image/avif,image/webp,"
        "*/*;q=0.8"
    ),
    "Accept-Language": "ru-RU,ru;q=0.9,en-US;q=0.8,en;q=0.7",
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
        print(f"{filename} не найден — используем пустую базу.")
        return default

    except Exception as e:
        print(f"Ошибка чтения {filename}: {e}")
        return default


def save_json(filename, data):
    try:
        with open(filename, "w", encoding="utf-8") as f:
            json.dump(
                data,
                f,
                ensure_ascii=False,
                indent=2
            )

    except Exception as e:
        print(f"Ошибка сохранения {filename}: {e}")


# ============================================================
# FLIBUSTA — ЗАГРУЗКА СТРАНИЦЫ
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


# ============================================================
# ИМЯ АВТОРА
# ============================================================

def get_author_name(soup):
    """
    На странице автора имя обычно находится в h1.

    Если h1 содержит «Флибуста», пытаемся определить имя
    через title.
    """

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
                "книжное братство",
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

        if (
            name
            and name.lower() not in {
                "флибуста",
                "книжное братство",
            }
        ):
            return name

    return "Неизвестный автор"


# ============================================================
# ПРОВЕРКА ССЫЛКИ НА КНИГУ
# ============================================================

def get_book_id(href):
    """
    Настоящая книга Flibusta имеет ссылку вида:

        /b/123456

    Возвращаем ID книги.
    """

    if not href:
        return None

    match = re.search(
        r"(?:^|/)b/(\d+)(?:[/?#]|$)",
        href
    )

    if not match:
        return None

    return match.group(1)


# ============================================================
# ОЧИСТКА НАЗВАНИЯ
# ============================================================

def clean_book_title(title):
    if not title:
        return None

    title = re.sub(
        r"\s+",
        " ",
        title
    ).strip()

    if not title:
        return None

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

    normalized = title.lower().strip(
        " ()[]"
    )

    if normalized in technical:
        return None

    # Убираем технические варианты:
    # (читать)
    # (fb2)
    # (epub)
    # и т.д.
    if re.fullmatch(
        r"\((?:читать|скачать|fb2|epub|mobi|rtf|txt|pdf|mail)\)",
        title,
        flags=re.IGNORECASE
    ):
        return None

    return title


# ============================================================
# ГРАНИЦА «ВПЕЧАТЛЕНИЯ О КНИГАХ»
# ============================================================

def find_impressions_boundary(soup):
    """
    Ищем заголовок/элемент с текстом
    «Впечатления о книгах».

    ВАЖНО:
    Мы НЕ проверяем link.parents.

    Причина:
    на некоторых страницах Flibusta блок может оказаться
    большим контейнером, внутри которого находится
    основной список книг.
    """

    # Сначала ищем заголовки.
    for tag in [
        "h1",
        "h2",
        "h3",
        "h4",
        "h5",
        "h6",
        "strong",
    ]:

        for element in soup.find_all(tag):

            text = element.get_text(
                " ",
                strip=True
            ).lower()

            if "впечатления о книгах" in text:
                return element

    return None


# ============================================================
# КНИГИ АВТОРА
# ============================================================

def get_author_books(soup):
    """
    Получаем список книг автора.

    Используем ссылки /b/ID.

    Важный момент:
    мы НЕ используем link.parents для исключения блока
    «Впечатления о книгах».

    Это было причиной появления 0 книг.

    Вместо этого сначала пытаемся найти основной контейнер
    списка книг. Если определить его невозможно —
    используем все уникальные ссылки /b/ на странице,
    что для страницы автора Flibusta является безопаснее,
    чем удалить весь список.
    """

    books = []
    seen_ids = set()

    impressions = find_impressions_boundary(soup)

    # --------------------------------------------------------
    # ВАРИАНТ 1.
    # Ищем контейнер, в котором находится имя автора,
    # и собираем книги из этого контейнера.
    # --------------------------------------------------------

    author_h1 = soup.find("h1")

    candidate_containers = []

    if author_h1:

        # Поднимаемся по родителям, но НЕ слишком высоко.
        parent = author_h1.parent

        for _ in range(6):

            if parent is None:
                break

            candidate_containers.append(parent)

            parent = parent.parent

    # --------------------------------------------------------
    # Сначала пробуем контейнеры от маленького к большому.
    # --------------------------------------------------------

    for container in candidate_containers:

        links = container.find_all("a")

        temp_books = []
        temp_ids = set()

        for link in links:

            href = link.get(
                "href",
                ""
            )

            book_id = get_book_id(href)

            if not book_id:
                continue

            title = clean_book_title(
                link.get_text(
                    " ",
                    strip=True
                )
            )

            if not title:
                continue

            if book_id in temp_ids:
                continue

            temp_ids.add(book_id)
            temp_books.append(title)

        # Нам нужен контейнер, где действительно есть
        # разумное количество книг.
        if len(temp_books) >= 2:

            books = temp_books
            seen_ids = temp_ids

            break

    # --------------------------------------------------------
    # ВАРИАНТ 2.
    # Если контейнер найти не удалось — собираем ссылки
    # со страницы напрямую.
    # --------------------------------------------------------

    if not books:

        for link in soup.find_all("a"):

            href = link.get(
                "href",
                ""
            )

            book_id = get_book_id(href)

            if not book_id:
                continue

            title = clean_book_title(
                link.get_text(
                    " ",
                    strip=True
                )
            )

            if not title:
                continue

            if book_id in seen_ids:
                continue

            seen_ids.add(book_id)
            books.append(title)

    # --------------------------------------------------------
    # Последняя защита от технических ссылок.
    # --------------------------------------------------------

    cleaned = []

    for title in books:

        title = clean_book_title(title)

        if not title:
            continue

        cleaned.append(title)

    return cleaned


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
            "ОШИБКА: TELEGRAM_TOKEN не найден."
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

    if len(text) <= TELEGRAM_LIMIT:

        return send_message(
            text
        )

    print(
        "Сообщение длинное — "
        "разбиваем на части."
    )

    lines = text.split("\n")

    parts = []
    current = ""

    for line in lines:

        candidate = (
            current
            + ("\n" if current else "")
            + line
        )

        if len(candidate) > TELEGRAM_LIMIT:

            if current:
                parts.append(
                    current
                )

            current = line

        else:

            current = candidate

    if current:
        parts.append(
            current
        )

    print(
        "Количество частей:",
        len(parts)
    )

    success = True

    for index, part in enumerate(
        parts,
        start=1
    ):

        print(
            f"Отправляем часть "
            f"{index}/{len(parts)}"
        )

        if not send_message(
            part
        ):
            success = False

        time.sleep(1)

    return success


# ============================================================
# TELEGRAM-СООБЩЕНИЕ
# ============================================================

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

    return "\n".join(
        lines
    )


# ============================================================
# ОСНОВНАЯ ПРОВЕРКА
# ============================================================

def main():

    print(
        "================================"
    )
    print(
        "СТАРТ ПРОВЕРКИ"
    )
    print(
        "================================"
    )

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
        print(
            "--------------------------------"
        )
        print(
            "Проверяем:",
            author_url
        )
        print(
            "--------------------------------"
        )

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
            # ЕСЛИ КНИГ НЕТ
            # ------------------------------------------------

            if not books:

                print(
                    "Книги не найдены — "
                    "старый список не изменяем."
                )

                continue

            # ------------------------------------------------
            # СТАРЫЙ СПИСОК
            # ------------------------------------------------

            old_books = seen.get(
                author_url
            )

            # ------------------------------------------------
            # ПЕРВАЯ ЗАГРУЗКА
            # ------------------------------------------------

            if old_books is None:

                print(
                    "Первичная загрузка автора — "
                    "уведомление не отправляем."
                )

                seen[author_url] = books

                continue

            # ------------------------------------------------
            # СРАВНЕНИЕ
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
            # НОВЫЕ КНИГИ
            # ------------------------------------------------

            if new_books:

                print(
                    "Найдены новые книги:"
                )

                for book in new_books:
                    print(
                        " +",
                        book
                    )

                message = make_message(
                    author_name,
                    new_books
                )

                send_long_message(
                    message
                )

            else:

                print(
                    "Новых книг нет."
                )

            # ------------------------------------------------
            # ОБНОВЛЯЕМ БАЗУ
            # ------------------------------------------------

            seen[author_url] = books

        except requests.exceptions.Timeout:

            print(
                "ОШИБКА: Flibusta не ответила "
                f"за {REQUEST_TIMEOUT} секунд."
            )

            # Старую базу НЕ трогаем.

        except requests.exceptions.RequestException as e:

            print(
                "ОШИБКА соединения:",
                e
            )

            # Старую базу НЕ трогаем.

        except Exception as e:

            print(
                "ОШИБКА:",
                repr(e)
            )

            # Старую базу НЕ трогаем.

        # Небольшая пауза между авторами.
        time.sleep(1)

    # ========================================================
    # СОХРАНЕНИЕ
    # ========================================================

    save_json(
        SEEN_FILE,
        seen
    )

    print()
    print(
        "================================"
    )
    print(
        "ПРОВЕРКА ЗАВЕРШЕНА"
    )
    print(
        "================================"
    )


# ============================================================
# ЗАПУСК
# ============================================================

if __name__ == "__main__":
    main()
