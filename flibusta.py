import requests
from bs4 import BeautifulSoup
from urllib.parse import urljoin


def get_page(url):
    headers = {
        "User-Agent": "Mozilla/5.0"
    }

    response = requests.get(
        url,
        headers=headers,
        timeout=30
    )

    response.raise_for_status()

    return BeautifulSoup(response.text, "html.parser")


def get_author_name(author_url):
    soup = get_page(author_url)

    # Ищем имя автора среди заголовков
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

    # Запасной вариант — название страницы
    page_title = soup.find("title")

    if page_title:

        name = page_title.get_text(" ", strip=True)

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


def get_author_books(author_url):
    soup = get_page(author_url)

    author_name = get_author_name(author_url)

    print("Автор:", author_name)

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
        "rtf"
    }

    # Получаем ссылки на книги
    for element in soup.find_all("a", href=True):

        text = element.get_text(" ", strip=True)
        href = element.get("href", "")

        if not text:
            continue

        # Убираем служебные ссылки
        if text.lower() in bad_names:
            continue

        if text.startswith("("):
            continue

        # Нам нужны только страницы книг
        if "/b/" not in href:
            continue

        # Не добавляем дубликаты
        if text not in books:
            books.append(text)

    print("Найдено книг:", len(books))

    return books
