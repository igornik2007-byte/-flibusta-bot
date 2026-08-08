import requests
from bs4 import BeautifulSoup
from urllib.parse import urljoin


def get_author_books(author_url):
    headers = {
        "User-Agent": "Mozilla/5.0"
    }

    response = requests.get(
        author_url,
        headers=headers,
        timeout=30
    )

    response.raise_for_status()

    soup = BeautifulSoup(response.text, "html.parser")

    books = []

    # Ищем ссылки на страницы книг
    for link in soup.find_all("a", href=True):

        href = link.get("href", "")
        text = link.get_text(" ", strip=True)

        # Нас интересуют только ссылки на книги
        if not href.startswith("/b/"):
            continue

        if not text:
            continue

        # Отбрасываем служебные ссылки
        bad_names = {
            "читать",
            "fb2",
            "epub",
            "mobi",
            "rtf",
            "скачать",
            "скачать rtf"
        }

        if text.lower() in bad_names:
            continue

        # Убираем дубликаты
        if text not in books:
            books.append(text)

    return books
