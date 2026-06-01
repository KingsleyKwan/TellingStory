#!/usr/bin/env python3
"""
sleyStory - Interactive Storytelling Bot (繁體中文長篇版)
Follows the interactive-story-generator skill rules.
"""

import asyncio
import os
import sqlite3
import sys
from datetime import datetime
from pathlib import Path

from dotenv import load_dotenv
from telegram import Update
from telegram.ext import Application, CommandHandler, MessageHandler, filters, ContextTypes

from openai import OpenAI

load_dotenv()

TELEGRAM_TOKEN = os.getenv("TELEGRAM_TOKEN")
LM_STUDIO_URL = os.getenv("LM_STUDIO_URL", "http://192.168.1.96:1234/v1")
MODEL_NAME = os.getenv("STORY_MODEL", "gemma-4-E4B")

client = OpenAI(base_url=LM_STUDIO_URL, api_key="lm-studio")

BASE_DIR = Path(__file__).parent
DB_PATH = BASE_DIR / "stories.db"

# ====================== DATABASE ======================
def init_db():
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute('''CREATE TABLE IF NOT EXISTS stories (
        story_id INTEGER PRIMARY KEY AUTOINCREMENT,
        user_id INTEGER,
        title TEXT,
        story_bible TEXT,
        current_chapter INTEGER DEFAULT 1,
        created_at TEXT
    )''')
    c.execute('''CREATE TABLE IF NOT EXISTS chapters (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        story_id INTEGER,
        chapter_num INTEGER,
        content TEXT,
        choice_made TEXT,
        created_at TEXT
    )''')
    c.execute('''CREATE TABLE IF NOT EXISTS memories (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        story_id INTEGER,
        memory_type TEXT,
        key TEXT,
        value TEXT,
        updated_at TEXT
    )''')
    conn.commit()
    conn.close()

init_db()

# ====================== STORY GENERATION (with Story Bible) ======================
def load_story_context(story_id: int) -> dict:
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()

    c.execute("SELECT story_bible, current_chapter FROM stories WHERE story_id = ?", (story_id,))
    row = c.fetchone()
    story_bible = row[0] if row else "{}"
    current_chapter = row[1] if row else 1

    c.execute("""SELECT chapter_num, content, choice_made 
                 FROM chapters WHERE story_id = ? 
                 ORDER BY chapter_num DESC LIMIT 4""", (story_id,))
    recent = c.fetchall()
    conn.close()

    return {
        "story_bible": story_bible,
        "current_chapter": current_chapter,
        "recent_chapters": recent[::-1]
    }


def generate_chapter(story_id: int, user_choice: str = None, initial_prompt: str = "", is_first: bool = False) -> tuple:
    ctx = load_story_context(story_id)
    chapter_num = ctx["current_chapter"] + (0 if is_first else 1)

    system_prompt = (
        "你是專業的繁體中文長篇互動故事生成器，嚴格遵守 interactive-story-generator 規則。"
        "你必須維持故事的原始風格、角色性格、世界觀與氛圍，直到第20章都不改變。"
        "每次產生 800-1800 字的詳細章節，包含大量對話、關係發展、真實後果。"
        "⚠️ 每章結尾「必須」包含 A/B/C/D/E/I 選項，否則用戶無法繼續。絕對不要省略選項部分！"
    )

    if is_first:
        user_msg = f"""用戶想要的故事主題與風格：{initial_prompt or '未指定'}

請先生成**第 1 章**（繁體中文，800-1800字），格式如下：

**第 1 章：【章節標題】**

[沉浸式繁體中文敘事...]

**你接下來要怎麼做？**
A) [選項A — 簡短誘人描述]
B) [選項B — 會帶來不同走向]
C) [選項C]
D) [選項D]
E) [選項E — 可選]
I) [生成本篇圖像] （為本章最重要場面生成AI圖像）

⚠️ 每章結尾「必須」包含以上選項格式，絕對不要省略！

然後在章節結束後，輸出一個 JSON Story Bible（用 ```json 包起來），包含：
{{
  "core_style": "故事的核心風格與氛圍描述（例如：輕鬆日常、溫暖幽默、專注小細節）",
  "main_characters": {{"角色名": "背景與性格"}},
  "world_rules": "世界觀與重要設定",
  "tone_rules": "絕對不能出現的元素或必須保持的元素"
}}

（內部記憶更新 — 不顯示給用戶）"""
    else:
        history = "\n\n".join([f"第 {ch[0]} 章選擇：{ch[2]}" for ch in ctx["recent_chapters"]])
        user_msg = f"""目前 Story Bible：
{ctx['story_bible']}

這是故事的第 {chapter_num} 章。
用戶選擇：{user_choice}

之前章節選擇記錄：
{history}

請嚴格維持 Story Bible 中定義的風格，生成第 {chapter_num} 章（繁體中文），並在章節後更新 Story Bible（JSON）。

⚠️ 重要：每章結尾「必須」包含以下格式的選項，否則用戶無法繼續：

**你接下來要怎麼做？**
A) [選項A — 簡短誘人描述]
B) [選項B — 會帶來不同走向]
C) [選項C]
D) [選項D]
E) [選項E — 可選]
I) [生成本篇圖像] （為本章最重要場面生成AI圖像）

絕對不要省略選項部分！格式必須完全符合技能文件規定。"""

    try:
        response = client.chat.completions.create(
            model=MODEL_NAME,
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_msg}
            ],
            temperature=0.82,
            max_tokens=3000
        )
        full_output = response.choices[0].message.content.strip()

        # Split chapter content and possible bible update
        chapter_content = full_output
        new_bible = None

        if "```json" in full_output:
            parts = full_output.split("```json")
            chapter_content = parts[0].strip()
            try:
                import json, re
                json_str = re.search(r'\{.*\}', parts[1], re.DOTALL).group(0)
                new_bible = json_str
            except:
                pass

        # Save chapter
        conn = sqlite3.connect(DB_PATH)
        c = conn.cursor()
        c.execute("""INSERT INTO chapters (story_id, chapter_num, content, choice_made, created_at)
                     VALUES (?, ?, ?, ?, ?)""",
                  (story_id, chapter_num, chapter_content, user_choice or "初始章", datetime.now().isoformat()))
        c.execute("UPDATE stories SET current_chapter = ? WHERE story_id = ?", (chapter_num, story_id))

        # Update Story Bible if we got one
        if new_bible:
            c.execute("UPDATE stories SET story_bible = ? WHERE story_id = ?", (new_bible, story_id))

        conn.commit()
        conn.close()

        return chapter_content, chapter_num
    except Exception as e:
        return f"生成故事時發生錯誤：{e}", chapter_num

# ====================== HANDLERS ======================
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "📖 歡迎來到 sleyStory！\n\n"
        "我可以為你生成繁體中文長篇互動故事。\n\n"
        "指令：\n"
        "• /newstory + 描述 → 建立新故事\n"
        "• /mystories → 查看你所有的故事\n"
        "• /loadstory <ID> → 載入指定故事繼續玩\n\n"
        "例如：/newstory 我要講香港現代懸疑故事"
    )

async def new_story(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    prompt = update.message.text.replace("/newstory", "").strip() if update.message.text else ""

    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute("INSERT INTO stories (user_id, title, story_bible, created_at) VALUES (?, ?, ?, ?)",
              (user_id, "未命名故事", prompt, datetime.now().isoformat()))
    story_id = c.lastrowid
    conn.commit()
    conn.close()

    context.user_data["current_story_id"] = story_id
    context.user_data["initial_prompt"] = prompt

    chapter1, _ = generate_chapter(story_id, initial_prompt=prompt, is_first=True)

    await update.message.reply_text(
        f"✅ 新故事已建立！Story ID: `{story_id}`\n"
        f"以後可以用 `/loadstory {story_id}` 繼續這個故事。\n\n"
        f"{chapter1}"
    )


async def list_my_stories(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute("""SELECT story_id, title, current_chapter, created_at 
                 FROM stories WHERE user_id = ? ORDER BY story_id DESC""", (user_id,))
    rows = c.fetchall()
    conn.close()

    if not rows:
        await update.message.reply_text("你目前沒有任何故事。請用 /newstory 開始一個新故事！")
        return

    msg = "📚 你的故事列表：\n\n"
    for row in rows:
        sid, title, ch, created = row
        msg += f"• ID `{sid}` — {title}（第 {ch} 章）\n  建立於 {created[:10]}\n"
    msg += "\n使用 `/loadstory <ID>` 繼續某個故事。"
    await update.message.reply_text(msg)


async def load_story(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    args = context.args
    if not args:
        await update.message.reply_text("請輸入 Story ID，例如：`/loadstory 5`")
        return

    try:
        story_id = int(args[0])
    except ValueError:
        await update.message.reply_text("Story ID 必須是數字，例如：`/loadstory 5`")
        return

    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute("SELECT story_id FROM stories WHERE story_id = ? AND user_id = ?", (story_id, user_id))
    row = c.fetchone()
    conn.close()

    if not row:
        await update.message.reply_text(f"找不到 Story ID `{story_id}`，或這不是你的故事。")
        return

    context.user_data["current_story_id"] = story_id
    await update.message.reply_text(
        f"✅ 已載入 Story ID `{story_id}`！\n"
        f"現在可以直接輸入 A / B / C / D / E / I 繼續故事。"
    )


async def handle_choice(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = update.message.text.strip()
    story_id = context.user_data.get("current_story_id")

    if not story_id:
        await update.message.reply_text("請先用 /newstory 開始一個新故事。")
        return

    chapter_text, ch_num = generate_chapter(story_id, user_choice=text)
    await update.message.reply_text(f"（第 {ch_num} 章）\n\n{chapter_text}")

def main():
    app = Application.builder().token(TELEGRAM_TOKEN).build()
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("newstory", new_story))
    app.add_handler(CommandHandler("mystories", list_my_stories))
    app.add_handler(CommandHandler("loadstory", load_story))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_choice))

    print("📖 sleyStory bot is running...")
    app.run_polling()

if __name__ == "__main__":
    if sys.platform == "darwin":
        # Fix for Python 3.12+ on macOS: ensure an event loop exists
        asyncio.set_event_loop(asyncio.new_event_loop())
    main()