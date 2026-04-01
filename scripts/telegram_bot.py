#!/usr/bin/env python3
"""Telegram bot that classifies messages and writes them to Notion."""

import asyncio
import base64
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

SYSTEM_PROMPT = f"""\
You are a message classifier. Classify the user's message into one of two categories:

1. **reminder**: A task or event with a deadline (e.g., "周五之前提交报告", "下周三开会").
   - Extract the task content and deadline.
   - Convert all dates to YYYY-MM-DD format.

2. **note**: A piece of information worth recording (e.g., paper titles, game names, book recommendations).
   - Extract the content and assign a category: 论文, 游戏, 书籍, 电影, 音乐, 美食, 链接, 想法, 其他.

Today's date is {date.today().isoformat()}. Use it to resolve relative dates like "下周三", "后天", "月底".
Extract meaningful tags when possible (at most 3 tags). Prioritize location names as tags.

You MUST respond with ONLY a JSON object in the following format, no other text:
{{"type": "reminder" or "note", "content": "...", "deadline": "YYYY-MM-DD" or null, "category": "..." or null, "tags": ["..."]}}\
"""


def classify_message(client: Anthropic, text: str = None, image_data: bytes = None, image_type: str = "image/jpeg") -> dict:
    """Call Kimi API to classify a message. Supports text, image, or both."""
    content = []
    if image_data:
        content.append({
            "type": "image",
            "source": {
                "type": "base64",
                "media_type": image_type,
                "data": base64.b64encode(image_data).decode(),
            },
        })
    if text:
        content.append({"type": "text", "text": text})
    if not content:
        raise ValueError("No text or image provided")

    response = client.messages.create(
        model="kimi-for-coding",
        max_tokens=256,
        system=SYSTEM_PROMPT,
        messages=[{"role": "user", "content": content}],
    )
    raw = response.content[0].text.strip()
    if raw.startswith("```"):
        raw = raw.split("\n", 1)[1].rsplit("```", 1)[0].strip()
    return json.loads(raw)


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


CATEGORY_EMOJI = {
    "论文": "📄", "游戏": "🎮", "书籍": "📚", "电影": "🎬",
    "音乐": "🎵", "美食": "🍜", "链接": "🔗", "想法": "💡", "其他": "📝",
}


def format_reply(classification: dict, notion_result: dict) -> str:
    """Format the bot's reply message."""
    if classification["type"] == "reminder":
        lines = ["📋 *事项提醒*", f"内容: {classification['content']}"]
        if classification["deadline"]:
            lines.append(f"截止: {classification['deadline']}")
    else:
        emoji = CATEGORY_EMOJI.get(classification.get("category", ""), "📝")
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
        """Handle incoming text and photo messages."""
        if not self._is_allowed(update.effective_user.id):
            await update.message.reply_text("无权限使用此 Bot。")
            return

        await update.message.chat.send_action("typing")

        text = update.message.text or update.message.caption
        image_data = None

        if update.message.photo:
            photo = update.message.photo[-1]  # largest size
            file = await photo.get_file()
            image_data = await file.download_as_bytearray()

        try:
            classification = await asyncio.to_thread(
                classify_message, self.anthropic, text, image_data
            )
            notion_result = await asyncio.to_thread(write_to_notion, classification)
            reply = format_reply(classification, notion_result)
            await update.message.reply_text(reply, parse_mode="Markdown")
        except Exception as e:
            logger.error(f"Error processing message: {e}", exc_info=True)
            await update.message.reply_text(f"处理失败: {e}")


def main():
    load_env()
    token = os.environ.get("TELEGRAM_BOT_TOKEN")
    if not token:
        print("Error: TELEGRAM_BOT_TOKEN not set. See .env.example.", file=sys.stderr)
        sys.exit(1)

    bot = NotionBot()
    app = ApplicationBuilder().token(token).build()
    app.add_handler(CommandHandler("start", bot.start))
    app.add_handler(MessageHandler(
        (filters.TEXT | filters.PHOTO) & ~filters.COMMAND, bot.handle_message
    ))

    logger.info("Bot started. Polling for messages...")
    app.run_polling()


if __name__ == "__main__":
    main()
