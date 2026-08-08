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

    # На странице книги находятся в строках/блоках,
    # где присутствует номер книги и ссылка с названием.
    for element in soup.find_all("a", href=True):

        text = element.get_text(" ", strip=True)
        href = element.get("href", "")

        if not text:
            continue

        # Служебные ссылки пропускаем
        if text.lower() in bad_names:
            continue

        # Ищем именно ссылки на книгу.
        # Ссылки на форматы/чтение имеют другие адреса.
        if "/b/" not in href:
            continue

        # У служебных ссылок могут быть дополнительные параметры.
        # Название книги обычно не начинается со скобок.
        if text.startswith("("):
            continue

        if text not in books:
            books.append(text)

    return books
