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
