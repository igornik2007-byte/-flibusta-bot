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

    for element in soup.find_all("a", href=True):

        text = element.get_text(" ", strip=True)
        href = element.get("href", "")

        if not text:
            continue

        if text.lower() in bad_names:
            continue

        if "/b/" not in href:
            continue

        if text.startswith("("):
            continue

        if text not in books:
            books.append(text)

    return books


def get_author_name(author_url):
    """
    Получает имя автора со страницы автора.
    """

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

    # Сначала пытаемся найти заголовок страницы
    title = soup.find("h1")

    if title:
        name = title.get_text(" ", strip=True)
        if name:
            return name

    # Запасной вариант — title страницы
    page_title = soup.find("title")

    if page_title:
        name = page_title.get_text(" ", strip=True)

        # Убираем возможное название сайта
        for suffix in [
            " — Флибуста",
            " - Флибуста",
            " | Флибуста"
        ]:
            if suffix in name:
                name = name.split(suffix)[0].strip()

        if name:
            return name

    return "Неизвестный автор"
