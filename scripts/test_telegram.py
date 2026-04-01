#!/usr/bin/env python3
"""Test Telegram bot connectivity - listen for messages and print them."""

import os
import sys
import json
from urllib.request import Request, urlopen

sys.path.insert(0, os.path.dirname(__file__))
from notion_writer import load_env

load_env()

TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN")
if not TOKEN:
    print("FAIL  TELEGRAM_BOT_TOKEN not set")
    sys.exit(1)

API = f"https://api.telegram.org/bot{TOKEN}"


def call(method, params=None):
    url = f"{API}/{method}"
    if params:
        data = json.dumps(params).encode()
        req = Request(url, data=data, method="POST")
        req.add_header("Content-Type", "application/json")
    else:
        req = Request(url)
    with urlopen(req) as resp:
        return json.loads(resp.read())


# 1. Test bot info
print("=" * 50)
print("1. Bot 信息")
print("=" * 50)
me = call("getMe")
if me["ok"]:
    bot = me["result"]
    print(f"OK    Bot: @{bot['username']} ({bot['first_name']})")
else:
    print(f"FAIL  {me}")
    sys.exit(1)

# 2. Listen for messages
print()
print("=" * 50)
print("2. 等待消息中... (给 bot 发条消息, Ctrl+C 退出)")
print("=" * 50)

offset = None
try:
    while True:
        params = {"timeout": 30}
        if offset:
            params["offset"] = offset
        updates = call("getUpdates", params)
        for u in updates.get("result", []):
            offset = u["update_id"] + 1
            msg = u.get("message", {})
            user = msg.get("from", {})
            text = msg.get("text", "")
            print(f"  [{user.get('id')}] {user.get('first_name', '')}: {text}")
except KeyboardInterrupt:
    print("\n已退出")
