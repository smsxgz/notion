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
                "description": "Category for notes: 论文/游戏/书籍/电影/音乐/美食/链接/想法/其他, null for reminders",
            },
            "tags": {
                "type": "array",
                "items": {"type": "string"},
                "description": "Relevant tags extracted from the message",
            },
        },
        "required": ["type", "content", "deadline", "category", "tags"],
        "additionalProperties": False,
    },
}

SYSTEM_PROMPT = f"""\
You are a message classifier. Classify the user's message into one of two categories:

1. **reminder**: A task or event with a deadline (e.g., "周五之前提交报告", "下周三开会").
   - Extract the task content and deadline.
   - Convert all dates to YYYY-MM-DD format.

2. **note**: A piece of information worth recording (e.g., paper titles, game names, book recommendations).
   - Extract the content and assign a category: 论文, 游戏, 书籍, 电影, 音乐, 美食, 链接, 想法, 其他.

Today's date is {date.today().isoformat()}. Use it to resolve relative dates like "下周三", "后天", "月底".
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
        lines = [f"📋 *事项提醒*", f"内容: {classification['content']}"]
        if classification["deadline"]:
            lines.append(f"截止: {classification['deadline']}")
    else:
        emoji = {
            "论文": "📄", "游戏": "🎮", "书籍": "📚", "电影": "🎬",
            "音乐": "🎵", "美食": "🍜", "链接": "🔗", "想法": "💡", "其他": "📝",
        }.get(classification.get("category", ""), "📝")
        lines = [
            f"{emoji} *{classification.get('category', '记录')}*",
            f"内容: {classification['content']}",
        ]

    if classification.get("tags"):
        lines.append(f"标签: {', '.join(classification['tags'])}")

    url = notion_result.get("url", "")
    if url:
        lines.append(f"[Notion 链接]({url})")

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
            "👋 发给我任何消息，我会自动分类并存入 Notion！\n\n"
            "支持两种类型：\n"
            "• *事项提醒* — 带 deadline 的任务（如：周五之前交报告）\n"
            "• *日常记录* — 论文、游戏、书籍等（如：推荐论文 xxx）\n\n"
            "直接发消息即可，无需任何命令。",
            parse_mode="Markdown",
        )

    async def handle_message(
        self, update: Update, context: ContextTypes.DEFAULT_TYPE
    ) -> None:
        """Handle incoming text messages."""
        if not self._is_allowed(update.effective_user.id):
            await update.message.reply_text("⛔ 无权限使用此 Bot。")
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
            await update.message.reply_text(f"❌ 处理失败: {e}")


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
