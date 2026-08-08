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
        text = link.get_text(strip=True)
        href = link["href"]

        if text and "/b/" in href:
            if text not in books:
                books.append(text)

    return books
