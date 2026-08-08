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
    except Exception:
        return default


def save_json(filename, data):
    with open(filename, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)


def send_message(text):
    if not TOKEN:
        print("Ошибка: TELEGRAM_TOKEN не найден")
        return

    url = f"https://api.telegram.org/bot{TOKEN}/sendMessage"

    response = requests.post(
        url,
        data={
            "chat_id": USER_ID,
            "text": text
        },
        timeout=30
    )

    print("Telegram:", response.text)


def main():
    print("Старт проверки")

    authors = load_json(AUTHORS_FILE, [])
    seen = load_json(SEEN_FILE, {})

    print("Авторов:", len(authors))

    for author_url in authors:
        print("Проверяем:", author_url)

        books = get_author_books(author_url)

        print("Найдено книг:", len(books))

        old_books = seen.get(author_url, [])

        new_books = [
            book for book in books
            if book not in old_books
        ]

        print("Новых книг:", len(new_books))

        if new_books:
            message = (
                "📚 Новые книги на Флибусте:\n\n"
                + "\n".join(
                    "• " + book for book in new_books
                )
            )

            send_message(message)

        seen[author_url] = books

    save_json(SEEN_FILE, seen)

    print("Проверка завершена")


if __name__ == "__main__":
    main()
