import os
import json
import requests

from flibusta import get_author_books


TOKEN = os.getenv("TELEGRAM_TOKEN")
USER_ID = 194667223

AUTHORS_FILE = "authors.json"
SEEN_FILE = "seen.json"


def load_json(filename, default):
    try:
        with open(filename, "r", encoding="utf-8") as f:
            return json.load(f)
    except:
        return default


def save_json(filename, data):
    with open(filename, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)


def send_message(text):
    url = f"https://api.telegram.org/bot{TOKEN}/sendMessage"

    requests.post(
        url,
        data={
            "chat_id": USER_ID,
            "text": text
        }
    )


def main():

    authors = load_json(AUTHORS_FILE, [])
    seen = load_json(SEEN_FILE, {})

    updated = False

    for author_url in authors:

        books = get_author_books(author_url)
        print("Проверяем:", author_url)

print("Найдено книг:", len(books))

print(books[:5])

        old_books = seen.get(author_url, [])

        new_books = [
            b for b in books
            if b not in old_books
        ]

        if new_books:
            send_message(
                "📚 Новые книги на Флибусте:\n\n"
                + "\n".join(
                    "• " + b for b in new_books
                )
            )

        if books != old_books:
            seen[author_url] = books
            updated = True

    if updated:
        save_json(SEEN_FILE, seen)


if __name__ == "__main__":
    main()
