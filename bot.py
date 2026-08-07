import os
import json
from telegram import Update
from telegram.ext import (
    Application,
    CommandHandler,
    MessageHandler,
    ContextTypes,
    filters
)

USER_ID = 194667223
TOKEN = os.getenv("TELEGRAM_TOKEN")

AUTHORS_FILE = "authors.json"


def load_authors():
    try:
        with open(AUTHORS_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    except:
        return []


def save_authors(authors):
    with open(AUTHORS_FILE, "w", encoding="utf-8") as f:
        json.dump(authors, f, ensure_ascii=False, indent=2)


async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != USER_ID:
        return

    await update.message.reply_text(
        "Привет! 📚\n\n"
        "Я буду следить за новыми книгами авторов Флибусты.\n\n"
        "Отправь мне ссылку на страницу автора, чтобы добавить его."
    )


async def add_author(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != USER_ID:
        return

    text = update.message.text.strip()

    if "flibusta" not in text:
        return

    authors = load_authors()

    if text in authors:
        await update.message.reply_text(
            "⚠️ Этот автор уже отслеживается."
        )
        return

    authors.append(text)
    save_authors(authors)

    await update.message.reply_text(
        "✅ Автор добавлен!\n"
        f"Сейчас отслеживается: {len(authors)} авторов."
    )


async def list_authors(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != USER_ID:
        return

    authors = load_authors()

    if not authors:
        await update.message.reply_text(
            "Список авторов пока пуст."
        )
        return

    text = "📚 Отслеживаются:\n\n" + "\n".join(authors)

    await update.message.reply_text(text)


async def remove_author(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != USER_ID:
        return

    authors = load_authors()

    if not authors:
        await update.message.reply_text(
            "Список пуст."
        )
        return

    await update.message.reply_text(
        "Для удаления позже добавим кнопки выбора автора."
    )


def main():
    app = Application.builder().token(TOKEN).build()

    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("list", list_authors))
    app.add_handler(CommandHandler("remove", remove_author))

    app.add_handler(
        MessageHandler(filters.TEXT & ~filters.COMMAND, add_author)
    )

    print("Bot started")

    app.run_polling()


if __name__ == "__main__":
    main()
