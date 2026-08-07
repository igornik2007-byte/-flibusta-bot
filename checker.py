import os
import requests


TOKEN = os.getenv("TELEGRAM_TOKEN")
USER_ID = 194667223


def send_message(text):
    url = f"https://api.telegram.org/bot{TOKEN}/sendMessage"

    response = requests.post(
        url,
        data={
            "chat_id": USER_ID,
            "text": text
        }
    )

    print(response.text)


def main():
    print("Старт")

    send_message("Тест Flibusta bot ✅")


if __name__ == "__main__":
    main()
