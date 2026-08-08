import os
import json
import requests

from flibusta import get_author_books, get_author_name


TOKEN = os.getenv("TELEGRAM_TOKEN")
USER_ID = 194667223

AUTHORS_FILE = "authors.json"
SEEN_FILE = "seen.json"


def load_json(filename, default):
    try:
        with open(filename, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception as e:
        print(f"Ошибка чтения {filename}:", e)
        return default


def save_json(filename, data):
    with open(filename, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)


def send_message(text):
    if not TOKEN:
        print("ОШИБКА: TELEGRAM_TOKEN не найден")
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

        try:
            books = get_author_books(author_url)
        except Exception as e:
            print("Ошибка при проверке:", e)
            continue

        print("Найдено книг:", len(books))
        print("Первые книги:", books[:5])

        old_books = seen.get(author_url)

        # Первая проверка автора:
        # запоминаем существующие книги,
        # но уведомление не отправляем.
        if old_books is None:
            print("Первичная загрузка автора — уведомление не отправляем.")
            seen[author_url] = books
            continue

        new_books = [
            book for book in books
            if book not in old_books
        ]

        print("Старых книг:", len(old_books))
        print("Новых книг:", len(new_books))

        if new_books:

            try:
                author_name = get_author_name(author_url)
            except Exception as e:
                print("Не удалось получить имя автора:", e)
                author_name = "Неизвестный автор"

            message_lines = [
                "📚 Новые книги на Флибусте:",
                "",
                f"👤 Автор: {author_name}",
                ""
            ]

            for book in new_books:
                message_lines.append(f"• {book}")

            message = "\n".join(message_lines)

            send_message(message)

        seen[author_url] = books

    save_json(SEEN_FILE, seen)

    print("Проверка завершена")


if __name__ == "__main__":
    main()
