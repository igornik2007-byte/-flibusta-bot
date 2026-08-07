import requests
from bs4 import BeautifulSoup


def get_author_books(url):
    try:
        headers = {
            "User-Agent": "Mozilla/5.0"
        }

        response = requests.get(
            url,
            headers=headers,
            timeout=20
        )

        response.raise_for_status()

        soup = BeautifulSoup(
            response.text,
            "html.parser"
        )

        books = []

        for link in soup.find_all("a"):
            href = link.get("href", "")

            if "/b/" in href:
                title = link.text.strip()

                if title:
                    books.append(title)

        return list(set(books))

    except Exception as e:
        print("Ошибка проверки:", e)
        return []
