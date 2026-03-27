# AI Message Classifier → Notion

Classify messages into **reminders** (with deadlines) or **notes** (daily life records), and store them in Notion databases. Two entry points:

- **Telegram Bot** — Send messages from your phone, auto-classified via Claude API
- **Claude Code Skill** — Use `/note` in Claude Code for quick classification

## Setup

### 1. Notion

1. Go to [Notion Integrations](https://www.notion.so/my-integrations), create an integration, copy the token
2. Create two databases:

   **Reminders**: `Name` (title), `Deadline` (date), `Status` (select: Pending/Done), `Tags` (multi_select)

   **Notes**: `Name` (title), `Date` (date), `Category` (select), `Tags` (multi_select)

3. Share both databases with your integration ("..." → "Connections")

### 2. Telegram Bot

1. Message [@BotFather](https://t.me/BotFather) on Telegram → `/newbot` → copy the token
2. (Optional) Message [@userinfobot](https://t.me/userinfobot) to get your user ID for access control

### 3. Claude API

1. Get an API key from [Anthropic Console](https://console.anthropic.com/)

### 4. Configure

```bash
cp .env.example .env
# Fill in: TELEGRAM_BOT_TOKEN, ANTHROPIC_API_KEY, NOTION_TOKEN, database IDs
```

### 5. Install & Run

```bash
pip install -r requirements.txt
python3 scripts/telegram_bot.py
```

## Usage

### Telegram

Send any message to your bot:

- `周五之前要交机器学习的作业` → 📋 Reminder with deadline
- `看到一篇论文 Attention Is All You Need` → 📄 Note (论文)
- `朋友推荐了塞尔达传说` → 🎮 Note (游戏)

The bot replies with the classification result and a Notion link.

### Claude Code

```
/note 周五之前要交机器学习的作业
```
