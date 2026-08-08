import requests
from bs4 import BeautifulSoup


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

    for link in soup.find_all("a", href=True):
        text = link.get_text(" ", strip=True)
        href = link.get("href", "")

        # Берём только ссылки на книги
        if "/b/" not in href:
            continue

        # Убираем служебные ссылки
        if text.lower() in {
            "читать",
            "fb2",
            "epub",
            "mobi",
            "скачать",
            "скачать rtf",
            "rtf"
        }:
            continue

        if text and text not in books:
            books.append(text)

    return books
