#!/usr/bin/env python3
"""Telegram bot that classifies messages and writes them to Notion."""

import asyncio
import json
import logging
import os
import sys
from datetime import date

from anthropic import Anthropic
from telegram import Update
from telegram.ext import (
    ApplicationBuilder,
    CommandHandler,
    ContextTypes,
    MessageHandler,
    filters,
)

# Add parent directory to path so we can import notion_writer
sys.path.insert(0, os.path.dirname(__file__))
from notion_writer import add_note, add_reminder, get_config, load_env

logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    level=logging.INFO,
)
logger = logging.getLogger(__name__)

# Load .env once at startup
load_env()

CLASSIFICATION_SCHEMA = {
    "type": "json_schema",
    "schema": {
        "type": "object",
        "properties": {
            "type": {
                "type": "string",
                "enum": ["reminder", "note"],
                "description": "reminder: task/event with deadline; note: information worth recording",
            },
            "content": {
                "type": "string",
                "description": "The core content extracted from the message",
            },
            "deadline": {
                "type": ["string", "null"],
                "description": "Deadline in YYYY-MM-DD format, null if not a reminder or no deadline mentioned",
            },
            "category": {
                "type": ["string", "null"],
                "description": "Category for notes: \u8bba\u6587/\u6e38\u620f/\u4e66\u7c4d/\u7535\u5f71/\u97f3\u4e50/\u7f8e\u98df/\u94fe\u63a5/\u60f3\u6cd5/\u5176\u4ed6, null for reminders",
            },
            "tags": {
                "type": "array",
                "items": {"type": "string"},
                "description": "Relevant tags extracted from the message",
            },
        },
        "required": ["type", "content", "deadline", "category", "tags"],
        "additionalProperties": false,
    },
}

SYSTEM_PROMPT = f"""\
You are a message classifier. Classify the user's message into one of two categories:

1. **reminder**: A task or event with a deadline (e.g., "\u5468\u4e94\u4e4b\u524d\u63d0\u4ea4\u62a5\u544a", "\u4e0b\u5468\u4e09\u5f00\u4f1a").
   - Extract the task content and deadline.
   - Convert all dates to YYYY-MM-DD format.

2. **note**: A piece of information worth recording (e.g., paper titles, game names, book recommendations).
   - Extract the content and assign a category: \u8bba\u6587, \u6e38\u620f, \u4e66\u7c4d, \u7535\u5f71, \u97f3\u4e50, \u7f8e\u98df, \u94fe\u63a5, \u60f3\u6cd5, \u5176\u4ed6.

Today's date is {date.today().isoformat()}. Use it to resolve relative dates like "\u4e0b\u5468\u4e09", "\u540e\u5929", "\u6708\u5e95".
Extract meaningful tags when possible.\
"""


def classify_message(client: Anthropic, text: str) -> dict:
    """Call Claude API to classify a message. Runs in a thread (blocking)."""
    response = client.messages.create(
        model="claude-sonnet-4-20250514",
        max_tokens=256,
        system=SYSTEM_PROMPT,
        messages=[{"role": "user", "content": text}],
        output_config={"format": CLASSIFICATION_SCHEMA},
    )
    return json.loads(response.content[0].text)


def write_to_notion(classification: dict) -> dict:
    """Write classified message to Notion. Runs in a thread (blocking)."""
    token, reminders_db, notes_db = get_config()

    if classification["type"] == "reminder":
        return add_reminder(
            token,
            reminders_db,
            classification["content"],
            classification["deadline"],
            classification["tags"] or None,
        )
    else:
        return add_note(
            token,
            notes_db,
            classification["content"],
            classification["category"],
            classification["tags"] or None,
        )


def format_reply(classification: dict, notion_result: dict) -> str:
    """Format the bot's reply message."""
    if classification["type"] == "reminder":
        lines = [f"\ud83d\udccb *\u4e8b\u9879\u63d0\u9192*", f"\u5185\u5bb9: {classification['content']}"]
        if classification["deadline"]:
            lines.append(f"\u622a\u6b62: {classification['deadline']}")
    else:
        emoji = {
            "\u8bba\u6587": "\ud83d\udcc4", "\u6e38\u620f": "\ud83c\udfae", "\u4e66\u7c4d": "\ud83d\udcda", "\u7535\u5f71": "\ud83c\udfac",
            "\u97f3\u4e50": "\ud83c\udfb5", "\u7f8e\u98df": "\ud83c\udf5c", "\u94fe\u63a5": "\ud83d\udd17", "\u60f3\u6cd5": "\ud83d\udca1", "\u5176\u4ed6": "\ud83d\udcdd",
        }.get(classification.get("category", ""), "\ud83d\udcdd")
        lines = [
            f"{emoji} *{classification.get('category', '\u8bb0\u5f55')}*",
            f"\u5185\u5bb9: {classification['content']}",
        ]

    if classification.get("tags"):
        lines.append(f"\u6807\u7b7e: {', '.join(classification['tags'])}")

    url = notion_result.get("url", "")
    if url:
        lines.append(f"[Notion \u94fe\u63a5]({url})")

    return "\n".join(lines)


class NotionBot:
    def __init__(self):
        self.anthropic = Anthropic()
        self.allowed_users = self._load_allowed_users()

    def _load_allowed_users(self) -> set | None:
        """Load allowed Telegram user IDs from env. None means allow all."""
        val = os.environ.get("TELEGRAM_ALLOWED_USERS", "").strip()
        if not val:
            return None
        return {int(uid.strip()) for uid in val.split(",") if uid.strip()}

    def _is_allowed(self, user_id: int) -> bool:
        if self.allowed_users is None:
            return True
        return user_id in self.allowed_users

    async def start(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        """Handle /start command."""
        await update.message.reply_text(
            "\ud83d\udc4b \u53d1\u7ed9\u6211\u4efb\u4f55\u6d88\u606f\uff0c\u6211\u4f1a\u81ea\u52a8\u5206\u7c7b\u5e76\u5b58\u5165 Notion\uff01\n\n"
            "\u652f\u6301\u4e24\u79cd\u7c7b\u578b\uff1a\n"
            "\u2022 *\u4e8b\u9879\u63d0\u9192* \u2014 \u5e26 deadline \u7684\u4efb\u52a1\uff08\u5982\uff1a\u5468\u4e94\u4e4b\u524d\u4ea4\u62a5\u544a\uff09\n"
            "\u2022 *\u65e5\u5e38\u8bb0\u5f55* \u2014 \u8bba\u6587\u3001\u6e38\u620f\u3001\u4e66\u7c4d\u7b49\uff08\u5982\uff1a\u63a8\u8350\u8bba\u6587 xxx\uff09\n\n"
            "\u76f4\u63a5\u53d1\u6d88\u606f\u5373\u53ef\uff0c\u65e0\u9700\u4efb\u4f55\u547d\u4ee4\u3002",
            parse_mode="Markdown",
        )

    async def handle_message(
        self, update: Update, context: ContextTypes.DEFAULT_TYPE
    ) -> None:
        """Handle incoming text messages."""
        if not self._is_allowed(update.effective_user.id):
            await update.message.reply_text("\u26d4 \u65e0\u6743\u9650\u4f7f\u7528\u6b64 Bot\u3002")
            return

        text = update.message.text
        await update.message.chat.send_action("typing")

        try:
            classification = await asyncio.to_thread(
                classify_message, self.anthropic, text
            )
            notion_result = await asyncio.to_thread(write_to_notion, classification)
            reply = format_reply(classification, notion_result)
            await update.message.reply_text(reply, parse_mode="Markdown")
        except Exception as e:
            logger.error(f"Error processing message: {e}", exc_info=True)
            await update.message.reply_text(f"\u274c \u5904\u7406\u5931\u8d25: {e}")


def main():
    load_env()
    token = os.environ.get("TELEGRAM_BOT_TOKEN")
    if not token:
        print("Error: TELEGRAM_BOT_TOKEN not set. See .env.example.", file=sys.stderr)
        sys.exit(1)

    bot = NotionBot()
    app = ApplicationBuilder().token(token).build()
    app.add_handler(CommandHandler("start", bot.start))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, bot.handle_message))

    logger.info("Bot started. Polling for messages...")
    app.run_polling()


if __name__ == "__main__":
    main()
