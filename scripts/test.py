#!/usr/bin/env python3
"""Test Kimi API classification and Notion writing."""

import json
import os
import sys
from datetime import date

# Add scripts dir to path
sys.path.insert(0, os.path.dirname(__file__))
from notion_writer import add_note, add_reminder, get_config, load_env

load_env()

# ── Kimi / Anthropic SDK ──────────────────────────────────────────────────────

try:
    from anthropic import Anthropic
except ImportError:
    print("FAIL  anthropic package not installed. Run: pip install anthropic")
    sys.exit(1)

SYSTEM_PROMPT = f"""\
You are a message classifier. Classify the user's message into one of two categories:
1. reminder: A task or event with a deadline.
2. note: A piece of information worth recording (paper, game, book, movie, etc.).

Today's date is {date.today().isoformat()}. Convert relative dates to YYYY-MM-DD.
For notes, assign a category: 论文, 游戏, 书籍, 电影, 音乐, 美食, 链接, 想法, 其他.
Extract meaningful tags when possible (at most 3 tags). Prioritize location names as tags.

You MUST respond with ONLY a JSON object in the following format, no other text:
{{"type": "reminder" or "note", "content": "...", "deadline": "YYYY-MM-DD" or null, "category": "..." or null, "tags": ["..."]}}\
"""

TEST_CASES = [
    "4月24日带队参加IOLC,在南京",
    "4月10日去武汉有一个千课万人的讲座(生成式AI工具在小学语文教学中的应用与实践)",
]


def classify(client: Anthropic, text: str) -> dict:
    response = client.messages.create(
        model="kimi-for-coding",
        max_tokens=256,
        system=SYSTEM_PROMPT,
        messages=[{"role": "user", "content": text}],
    )
    raw = response.content[0].text.strip()
    # Strip markdown code fences if present
    if raw.startswith("```"):
        raw = raw.split("\n", 1)[1].rsplit("```", 1)[0].strip()
    return json.loads(raw)


def run_tests():
    passed = 0
    failed = 0

    # ── 1. Kimi connectivity ──────────────────────────────────────────────────
    print("=" * 60)
    print("1. Kimi API 连通性测试")
    print("=" * 60)
    try:
        client = Anthropic(
            api_key=os.environ["ANTHROPIC_API_KEY"],
            base_url=os.environ.get("ANTHROPIC_BASE_URL"),
        )
        resp = client.messages.create(
            model="kimi-for-coding",
            max_tokens=32,
            messages=[{"role": "user", "content": "回复 OK"}],
        )
        print(f"OK    response: {resp.content[0].text.strip()}")
        passed += 1
    except Exception as e:
        print(f"FAIL  {e}")
        failed += 1

    # ── 2. Message classification ─────────────────────────────────────────────
    print()
    print("=" * 60)
    print("2. 消息分类测试 (JSON schema)")
    print("=" * 60)
    classifications = []
    for msg in TEST_CASES:
        try:
            result = classify(client, msg)
            print(f"OK    输入: {msg}")
            print(f"      分类: {json.dumps(result, ensure_ascii=False)}")
            classifications.append((msg, result))
            passed += 1
        except Exception as e:
            print(f"FAIL  输入: {msg}")
            print(f"      错误: {e}")
            classifications.append((msg, None))
            failed += 1

    # ── 3. Notion writing ─────────────────────────────────────────────────────
    print()
    print("=" * 60)
    print("3. Notion 写入测试")
    print("=" * 60)
    try:
        token, reminders_db, notes_db = get_config()
    except Exception as e:
        print(f"FAIL  加载 Notion 配置: {e}")
        failed += 1
        token = None

    if token:
        for msg, cls in classifications:
            if cls is None:
                continue
            try:
                if cls["type"] == "reminder":
                    result = add_reminder(token, reminders_db, cls["content"], cls["deadline"], cls["tags"] or None)
                else:
                    result = add_note(token, notes_db, cls["content"], cls["category"], cls["tags"] or None)
                print(f"OK    [{cls['type']}] {cls['content']}")
                print(f"      URL: {result.get('url', 'N/A')}")
                passed += 1
            except Exception as e:
                print(f"FAIL  [{cls['type']}] {msg}")
                print(f"      错误: {e}")
                failed += 1

    # ── Summary ───────────────────────────────────────────────────────────────
    print()
    print("=" * 60)
    print(f"结果: {passed} 通过, {failed} 失败")
    print("=" * 60)
    return failed == 0


if __name__ == "__main__":
    ok = run_tests()
    sys.exit(0 if ok else 1)
