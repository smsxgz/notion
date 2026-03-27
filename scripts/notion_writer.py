#!/usr/bin/env python3
"""Write classified messages to Notion databases."""

import argparse
import json
import os
import sys
from datetime import date
from urllib.request import Request, urlopen
from urllib.error import HTTPError


def load_env():
    """Load .env file into environment variables."""
    env_file = os.path.join(os.path.dirname(os.path.dirname(__file__)), ".env")
    if os.path.exists(env_file):
        with open(env_file) as f:
            for line in f:
                line = line.strip()
                if line and not line.startswith("#") and "=" in line:
                    key, value = line.split("=", 1)
                    os.environ.setdefault(key.strip(), value.strip())


def get_config():
    """Load Notion config from environment or .env file."""
    load_env()

    token = os.environ.get("NOTION_TOKEN")
    reminders_db = os.environ.get("NOTION_REMINDERS_DB")
    notes_db = os.environ.get("NOTION_NOTES_DB")

    if not token:
        raise ValueError("NOTION_TOKEN not set. See .env.example for setup.")

    return token, reminders_db, notes_db


def notion_api(token, endpoint, payload):
    """Make a Notion API request."""
    url = f"https://api.notion.com/v1/{endpoint}"
    data = json.dumps(payload).encode()
    req = Request(url, data=data, method="POST")
    req.add_header("Authorization", f"Bearer {token}")
    req.add_header("Content-Type", "application/json")
    req.add_header("Notion-Version", "2022-06-28")

    try:
        with urlopen(req) as resp:
            return json.loads(resp.read())
    except HTTPError as e:
        body = e.read().decode()
        raise RuntimeError(f"Notion API error ({e.code}): {body}")


def add_reminder(token, db_id, content, deadline, tags=None):
    """Add a reminder to the Notion reminders database."""
    if not db_id:
        raise ValueError("NOTION_REMINDERS_DB not set.")

    properties = {
        "Name": {"title": [{"text": {"content": content}}]},
        "Status": {"select": {"name": "Pending"}},
    }

    if deadline:
        properties["Deadline"] = {"date": {"start": deadline}}

    if tags:
        properties["Tags"] = {"multi_select": [{"name": t} for t in tags]}

    payload = {"parent": {"database_id": db_id}, "properties": properties}
    result = notion_api(token, "pages", payload)
    url = result.get("url", "")
    print(f"Reminder added: {content}")
    if deadline:
        print(f"  Deadline: {deadline}")
    print(f"  Notion URL: {url}")
    return {"content": content, "deadline": deadline, "tags": tags, "url": url}


def add_note(token, db_id, content, category=None, tags=None):
    """Add a note to the Notion notes database."""
    if not db_id:
        raise ValueError("NOTION_NOTES_DB not set.")

    properties = {
        "Name": {"title": [{"text": {"content": content}}]},
        "Date": {"date": {"start": date.today().isoformat()}},
    }

    if category:
        properties["Category"] = {"select": {"name": category}}

    if tags:
        properties["Tags"] = {"multi_select": [{"name": t} for t in tags]}

    payload = {"parent": {"database_id": db_id}, "properties": properties}
    result = notion_api(token, "pages", payload)
    url = result.get("url", "")
    print(f"Note added: {content}")
    if category:
        print(f"  Category: {category}")
    print(f"  Notion URL: {url}")
    return {"content": content, "category": category, "tags": tags, "url": url}


def main():
    parser = argparse.ArgumentParser(description="Write to Notion databases")
    parser.add_argument("type", choices=["reminder", "note"], help="Message type")
    parser.add_argument("--content", required=True, help="Message content")
    parser.add_argument("--deadline", help="Deadline in YYYY-MM-DD format (reminders only)")
    parser.add_argument("--category", help="Category label (notes only)")
    parser.add_argument("--tags", help="Comma-separated tags")

    args = parser.parse_args()
    token, reminders_db, notes_db = get_config()
    tags = [t.strip() for t in args.tags.split(",")] if args.tags else None

    if args.type == "reminder":
        add_reminder(token, reminders_db, args.content, args.deadline, tags)
    else:
        add_note(token, notes_db, args.content, args.category, tags)


if __name__ == "__main__":
    main()
