#!/usr/bin/env python3
"""
sleyStory - Interactive Storytelling Bot (繁體中文長篇版)
Follows the interactive-story-generator skill rules.
"""

import asyncio
import json
import os
import re
import sqlite3
import sys
from datetime import datetime
from pathlib import Path

from dotenv import load_dotenv
from telegram import Update
from telegram.ext import Application, CommandHandler, MessageHandler, filters, ContextTypes

from openai import OpenAI
import logging

from local_guardrail import check_story_consistency

load_dotenv()

# Logging
logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")
logger = logging.getLogger(__name__)

TELEGRAM_TOKEN = os.getenv("TELEGRAM_TOKEN")

# xAI Grok (main story generation)
GROK_API_KEY = os.getenv("GROK_API_KEY")
GROK_MODEL = os.getenv("GROK_MODEL", "grok-3-latest")
grok_client = OpenAI(base_url="https://api.x.ai/v1", api_key=GROK_API_KEY) if GROK_API_KEY else None

# Local LM Studio (Guardrail)
LM_STUDIO_URL = os.getenv("LM_STUDIO_URL", "http://192.168.1.96:1234/v1")
LM_STUDIO_MODEL = os.getenv("LM_STUDIO_MODEL", "gemma-4-E4B")
local_client = OpenAI(base_url=LM_STUDIO_URL, api_key="lm-studio")

# Image mode
IMAGE_MODE = os.getenv("IMAGE_MODE", "groq").lower()  # groq or comfyui
COMFYUI_URL = os.getenv("COMFYUI_URL", "http://127.0.0.1:8188")

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


def parse_choices(chapter_text: str) -> dict:
    """Extract A/B/C/D/E/I choices from chapter text."""
    choices = {}
    pattern = r'^([A-EI])\)\s*(.+?)(?=\n[A-EI]\)|$)' 
    matches = re.findall(pattern, chapter_text, re.MULTILINE | re.DOTALL)
    for letter, desc in matches:
        choices[letter] = desc.strip()
    return choices


# ====================== HYBRID GENERATION (Grok + Local Guardrail) ======================

GROK_SYSTEM_PROMPT = """【最高優先級規則 - 角色一致性】
你係 sleyStory 嘅故事生成器。生成任何內容前必須嚴格遵守以下規則：

1. 所有角色必須 100% 符合 database 所儲存嘅：
   - 性格、MBTI、目標（短期/中期/長期）、能力、外型、持有物品、current_state
2. 所有角色之間嘅互動必須符合 character_relationships 表嘅：
   - relationship_type、trust_level、affection_level、歷史摘要
3. 如果你生成嘅內容違反以上任何一點，會被本地 Guardrail 拒絕並要求修改。

請用極致細膩嘅繁體中文描寫，並確保角色行動、對話、內心完全一致。
你必須維持故事的原始風格、角色性格、世界觀與氛圍，直到第20章都不改變。
每次產生 800-1800 字的詳細章節，包含大量對話、關係發展、真實後果。
⚠️ 每章結尾「必須」包含 A/B/C/D/E/I 選項，絕對不要省略！
⚠️ 絕對不要在章節開頭輸出任何 meta 說明，直接從章節標題開始。"""


def generate_chapter(story_id: int, user_choice: str = None, initial_prompt: str = "", is_first: bool = False) -> tuple:
    """
    Hybrid generation:
    1. Load context (characters, relationships, bible, recent chapters)
    2. Call Grok for creative generation
    3. Run local guardrail (up to 2 retries)
    4. Save everything
    """
    ctx = load_story_context(story_id)
    chapter_num = ctx["current_chapter"] + (0 if is_first else 1)

    # Build rich context for Grok
    char_context = ""
    if "characters" in ctx and ctx["characters"]:
        char_context = "\n【角色資料】\n" + "\n".join(
            [f"{name}: {json.dumps(data, ensure_ascii=False)}" for name, data in ctx.get("characters", {}).items()]
        )

    rel_context = ""
    if "relationships" in ctx and ctx["relationships"]:
        rel_context = "\n【關係資料】\n" + "\n".join(
            [f"{r['character_a']} → {r['character_b']}: {r['relationship_type']} "
             f"(信任{r['trust_level']}, 好感{r['affection_level']})" for r in ctx.get("relationships", [])]
        )

    history = "\n\n".join([f"第 {ch[0]} 章選擇：{ch[2]}" for ch in ctx["recent_chapters"]])

    if is_first:
        user_msg = f"""用戶想要的故事主題與風格：{initial_prompt or '未指定'}
請生成第 1 章（繁體中文），嚴格遵守角色一致性規則。格式必須包含章節標題 + 敘事 + A/B/C/D/E/I 選項 + ```json Story Bible。"""
    else:
        user_msg = f"""目前 Story Bible：
{ctx['story_bible']}

這是故事的第 {chapter_num} 章。
用戶選擇：{user_choice}

之前章節選擇記錄：
{history}
{char_context}
{rel_context}

請嚴格遵守角色一致性規則，生成第 {chapter_num} 章（繁體中文），並更新 Story Bible（JSON）。"""

    if not grok_client:
        return "錯誤：未設定 GROK_API_KEY，無法使用 Grok 生成故事。", chapter_num

    try:
        # Step 1: Generate with Grok
        response = grok_client.chat.completions.create(
            model=GROK_MODEL,
            messages=[
                {"role": "system", "content": GROK_SYSTEM_PROMPT},
                {"role": "user", "content": user_msg}
            ],
            temperature=0.85,
            max_tokens=3500
        )
        full_output = response.choices[0].message.content.strip()
        logger.info(f"Grok generated chapter {chapter_num} for story {story_id}")

        # Step 2: Guardrail check (up to 2 retries)
        for attempt in range(3):
            guard = check_story_consistency(full_output, story_id)
            if guard.get("is_valid", True):
                break
            logger.warning(f"Guardrail violation on attempt {attempt+1}: {guard.get('violations')}")
            if attempt == 2:
                break
            # Ask Grok to fix
            fix_msg = f"""以下內容被本地 Guardrail 發現違反角色一致性：
違規項目：{guard.get('violations')}
修改建議：{guard.get('suggestions')}

請根據建議重新生成修正版章節，保持原有風格與長度。"""
            response = grok_client.chat.completions.create(
                model=GROK_MODEL,
                messages=[
                    {"role": "system", "content": GROK_SYSTEM_PROMPT},
                    {"role": "user", "content": user_msg},
                    {"role": "assistant", "content": full_output},
                    {"role": "user", "content": fix_msg}
                ],
                temperature=0.7,
                max_tokens=3500
            )
            full_output = response.choices[0].message.content.strip()

        # Parse chapter + bible
        chapter_content = full_output
        new_bible = None
        if "```json" in full_output:
            parts = full_output.split("```json")
            chapter_content = parts[0].strip()
            try:
                json_str = re.search(r'\{.*\}', parts[1], re.DOTALL).group(0)
                new_bible = json_str
            except:
                pass

        # Save to DB
        conn = sqlite3.connect(DB_PATH)
        c = conn.cursor()
        c.execute("""INSERT INTO chapters (story_id, chapter_num, content, choice_made, created_at)
                     VALUES (?, ?, ?, ?, ?)""",
                  (story_id, chapter_num, chapter_content, user_choice or "初始章", datetime.now().isoformat()))
        c.execute("UPDATE stories SET current_chapter = ? WHERE story_id = ?", (chapter_num, story_id))
        if new_bible:
            c.execute("UPDATE stories SET story_bible = ? WHERE story_id = ?", (new_bible, story_id))
        conn.commit()
        conn.close()

        logger.info(f"Chapter {chapter_num} saved successfully for story {story_id}")
        return chapter_content, chapter_num

    except Exception as e:
        logger.error(f"Generation error: {e}")
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

    # Parse and store choices for future letter resolution
    context.user_data["last_choices"] = parse_choices(chapter1)

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
    context.user_data.pop("last_choices", None)  # reset choices when switching stories
    await update.message.reply_text(
        f"✅ 已載入 Story ID `{story_id}`！\n"
        f"現在可以直接輸入 A / B / C / D / E / I 繼續故事。"
    )


# ====================== IMAGE GENERATION ======================

async def generate_image_for_chapter(chapter_content: str, story_id: int, chapter_num: int) -> str:
    """Generate an image for the chapter based on IMAGE_MODE."""
    prompt = f"電影感構圖，繁體中文故事場景：{chapter_content[:400]}... 高質素、細膩光影、角色表情豐富"

    if IMAGE_MODE == "comfyui":
        try:
            # Placeholder for real ComfyUI workflow trigger
            logger.info(f"[ComfyUI] Would generate image for story {story_id} chapter {chapter_num}")
            return f"[ComfyUI] 圖像已生成（開發中） - {chapter_num}.png"
        except Exception as e:
            logger.error(f"ComfyUI error: {e}")
            return None
    else:
        # Grok Imagine (currently not available via public API)
        logger.info(f"[Grok Imagine] Image generation requested but not yet available via API.")
        return None


async def set_image_mode(update: Update, context: ContextTypes.DEFAULT_TYPE):
    global IMAGE_MODE
    args = context.args
    if not args or args[0].lower() not in ["groq", "comfyui"]:
        await update.message.reply_text("請輸入 `/image_mode groq` 或 `/image_mode comfyui`")
        return
    IMAGE_MODE = args[0].lower()
    await update.message.reply_text(f"✅ 圖像生成模式已切換為：{IMAGE_MODE}")


async def test_guardrail(update: Update, context: ContextTypes.DEFAULT_TYPE):
    story_id = context.user_data.get("current_story_id")
    if not story_id:
        await update.message.reply_text("請先載入一個故事（/loadstory <ID>）")
        return
    sample = "Sley 突然變成冷酷殺手，忘記了他一直以來的熱血性格。"
    result = check_story_consistency(sample, story_id)
    await update.message.reply_text(f"Guardrail 測試結果：\n{json.dumps(result, ensure_ascii=False, indent=2)}")


async def handle_choice(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = update.message.text.strip()
    story_id = context.user_data.get("current_story_id")

    if not story_id:
        await update.message.reply_text("請先用 /newstory 開始一個新故事。")
        return

    # Resolve single-letter choice (A/B/C/D/E/I) to full choice text
    last_choices = context.user_data.get("last_choices", {})
    if text.upper() in last_choices:
        resolved_choice = f"{text.upper()}) {last_choices[text.upper()]}"
    else:
        resolved_choice = text

    chapter_text, ch_num = generate_chapter(story_id, user_choice=resolved_choice)

    # Parse and store new choices for next turn
    context.user_data["last_choices"] = parse_choices(chapter_text)

    # Handle "I" option for image generation
    if resolved_choice.upper().startswith("I)"):
        image_result = await generate_image_for_chapter(chapter_text, story_id, ch_num)
        if image_result:
            await update.message.reply_text(f"（第 {ch_num} 章）\n\n{chapter_text}\n\n🖼️ {image_result}")
        else:
            await update.message.reply_text(f"（第 {ch_num} 章）\n\n{chapter_text}\n\n（圖像生成暫時無法使用）")
    else:
        await update.message.reply_text(f"（第 {ch_num} 章）\n\n{chapter_text}")

def main():
    app = Application.builder().token(TELEGRAM_TOKEN).build()
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("newstory", new_story))
    app.add_handler(CommandHandler("mystories", list_my_stories))
    app.add_handler(CommandHandler("loadstory", load_story))
    app.add_handler(CommandHandler("image_mode", set_image_mode))
    app.add_handler(CommandHandler("test_guardrail", test_guardrail))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_choice))

    print("📖 sleyStory bot is running... (Hybrid Grok + Local Guardrail mode)")
    app.run_polling()

if __name__ == "__main__":
    if sys.platform == "darwin":
        # Fix for Python 3.12+ on macOS: ensure an event loop exists
        asyncio.set_event_loop(asyncio.new_event_loop())
    main()