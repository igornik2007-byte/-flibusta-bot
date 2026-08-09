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


def book_belongs_to_author(book_url, author_name):
    try:
        soup = get_page(book_url)

        author_lower = author_name.lower().strip()

        page_text = soup.get_text(" ", strip=True).lower()

        if author_lower in page_text:
            return True

        return False

    except Exception as e:
        print("Ошибка проверки книги:", e)
        return False


def get_author_books(author_url):
    soup = get_page(author_url)

    author_name = get_author_name(author_url)

    print("Автор:", author_name)

    books = []
    checked_urls = set()

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

    book_links = []

    for element in soup.find_all("a", href=True):

        text = element.get_text(" ", strip=True)
        href = element.get("href", "")

        if not text:
            continue

        if text.lower() in bad_names:
            continue

        if text.startswith("("):
            continue

        if "/b/" not in href:
            continue

        book_url = urljoin(author_url, href)

        if book_url in checked_urls:
            continue

        checked_urls.add(book_url)

        book_links.append(
            (text, book_url)
        )

    print("Найдено ссылок на книги:", len(book_links))

    for book_name, book_url in book_links:

        if book_belongs_to_author(
            book_url,
            author_name
        ):

            if book_name not in books:
                books.append(book_name)

    return books
