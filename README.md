# AI Message Classifier → Notion

A Claude Code skill that classifies your messages and stores them in Notion databases.

## Categories

| Type | Description | Example |
|------|-------------|---------|
| **Reminder** | Tasks with deadlines | "周五之前交报告" |
| **Note** | Life snippets worth recording | "推荐论文 Attention Is All You Need" |

## Setup

### 1. Create Notion Integration

1. Go to [Notion Integrations](https://www.notion.so/my-integrations)
2. Create a new integration, copy the token

### 2. Create Notion Databases

Create two databases in Notion:

**Reminders Database** with properties:
- `Name` (title)
- `Deadline` (date)
- `Status` (select: Pending, Done)
- `Tags` (multi_select)

**Notes Database** with properties:
- `Name` (title)
- `Date` (date)
- `Category` (select)
- `Tags` (multi_select)

Then share both databases with your integration (click "..." → "Connections" → add your integration).

### 3. Configure Environment

```bash
cp .env.example .env
# Edit .env with your token and database IDs
```

## Usage

In Claude Code:

```
/note 周五之前要交机器学习的作业
/note 看到一篇不错的论文 Attention Is All You Need
/note 朋友推荐了一个游戏叫塞尔达传说
```

Claude will automatically classify the message, extract structured data, and write it to the appropriate Notion database.
