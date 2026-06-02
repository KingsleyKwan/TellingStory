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

    # v3 - Character consistency tables
    c.execute('''
        CREATE TABLE IF NOT EXISTS characters (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            story_id INTEGER NOT NULL,
            name TEXT NOT NULL,
            short_term_goal TEXT,
            mid_term_goal TEXT,
            long_term_goal TEXT,
            personality TEXT,
            mbti TEXT,
            appearance TEXT,
            abilities TEXT,
            traits TEXT,
            items TEXT,
            background TEXT,
            current_state TEXT,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            UNIQUE(story_id, name)
        )
    ''')

    c.execute('''
        CREATE TABLE IF NOT EXISTS character_relationships (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            story_id INTEGER NOT NULL,
            character_a TEXT NOT NULL,
            character_b TEXT NOT NULL,
            relationship_type TEXT,
            trust_level INTEGER DEFAULT 50,
            affection_level INTEGER DEFAULT 0,
            tension_level INTEGER DEFAULT 0,
            relationship_summary TEXT,
            history_summary TEXT,
            last_interaction_chapter INTEGER,
            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            UNIQUE(story_id, character_a, character_b)
        )
    ''')

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

    # v3 - Load characters (gracefully handle if table is empty)
    try:
        c.execute("""
            SELECT name, short_term_goal, mid_term_goal, long_term_goal,
                   personality, mbti, appearance, abilities, traits, items,
                   background, current_state
            FROM characters WHERE story_id = ?
        """, (story_id,))
        char_rows = c.fetchall()
        characters = {}
        for r in char_rows:
            characters[r[0]] = {
                "short_term_goal": r[1], "mid_term_goal": r[2], "long_term_goal": r[3],
                "personality": r[4], "mbti": r[5], "appearance": r[6],
                "abilities": json.loads(r[7]) if r[7] else [],
                "traits": r[8], "items": json.loads(r[9]) if r[9] else [],
                "background": r[10], "current_state": r[11]
            }
    except:
        characters = {}

    # v3 - Load relationships
    try:
        c.execute("""
            SELECT character_a, character_b, relationship_type, trust_level,
                   affection_level, tension_level, relationship_summary
            FROM character_relationships WHERE story_id = ?
        """, (story_id,))
        rel_rows = c.fetchall()
        relationships = [
            {
                "character_a": r[0], "character_b": r[1], "relationship_type": r[2],
                "trust_level": r[3], "affection_level": r[4], "tension_level": r[5],
                "relationship_summary": r[6]
            } for r in rel_rows
        ]
    except:
        relationships = {}

    conn.close()

    return {
        "story_bible": story_bible,
        "current_chapter": current_chapter,
        "recent_chapters": recent[::-1],
        "characters": characters,
        "relationships": relationships
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

GROK_SYSTEM_PROMPT = """【最高優先級規則 - 角色一致性 + 用戶選擇強制遵循 + 輸出格式】
你係 sleyStory 嘅故事生成器。生成任何內容前必須嚴格遵守以下規則：

1. 所有角色必須 100% 符合 database 所儲存嘅角色資料。
2. 所有角色之間嘅互動必須符合 character_relationships 表嘅關係設定。
3. 【最重要】你必須嚴格根據用戶本次選擇的行動來發展劇情，絕對不能偏離或忽略用戶的選擇。

【嚴格輸出格式要求】
你必須把輸出分成「給用戶看的故事」和「給程式用的隱藏資料」兩部分，格式如下：

**第 X 章：【章節標題】**

[沉浸式自然敘事 + 對話，絕對不要出現任何技術性詞彙。故事要像真正的輕小說一樣自然流暢。]

**你接下來要怎麼做？**
A) ...
B) ...
I) ...

---
DATA
```json
{...}
```

⚠️ 故事本文絕對不要提到任何資料庫欄位或技術詞彙！
⚠️ 每章結尾「必須」包含 A/B/C/D/E/I 選項。
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
請生成第 1 章（繁體中文），嚴格遵守角色一致性規則。
輸出格式必須嚴格按照 system prompt 的要求：故事本文（乾淨自然） + ---DATA + JSON。
絕對不要在故事本文中出現任何技術性詞彙。"""
    else:
        user_msg = f"""目前 Story Bible：
{ctx['story_bible']}

這是故事的第 {chapter_num} 章。
【用戶本次選擇】：{user_choice}

之前章節選擇記錄：
{history}
{char_context}
{rel_context}

請嚴格遵守角色一致性規則，並**必須以用戶本次選擇為核心**來發展劇情。
輸出格式必須嚴格按照 system prompt 的要求：故事本文（乾淨自然） + ---DATA + JSON。
絕對不要在故事本文中出現任何技術性詞彙。"""

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

        # ====================== NEW SEPARATED OUTPUT PARSING ======================
        chapter_content = full_output
        parsed_json = None

        # Split story and hidden data using the new delimiter
        if "---\nDATA" in full_output:
            story_part, data_part = full_output.split("---\nDATA", 1)
            chapter_content = story_part.strip()

            # Extract JSON from the DATA section
            if "```json" in data_part:
                try:
                    json_str = re.search(r'\{.*\}', data_part.split("```json")[1], re.DOTALL).group(0)
                    parsed_json = json.loads(json_str)
                except Exception as e:
                    logger.warning(f"Failed to parse hidden DATA JSON: {e}")
        else:
            # Fallback: old format (try to extract any JSON)
            if "```json" in full_output:
                try:
                    parts = full_output.split("```json")
                    chapter_content = parts[0].strip()
                    json_str = re.search(r'\{.*\}', parts[1], re.DOTALL).group(0)
                    parsed_json = json.loads(json_str)
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

        # ====================== v3 AUTO-SYNC: characters + relationships + memories ======================
        if parsed_json:
            try:
                # Try multiple possible JSON structures
                char_data = None
                rel_data = None

                # Format 1: updated_characters + updated_relationships (ideal)
                if "updated_characters" in parsed_json:
                    char_data = parsed_json["updated_characters"]
                if "updated_relationships" in parsed_json:
                    rel_data = parsed_json["updated_relationships"]

                # Format 2: characters + relationships
                if not char_data and "characters" in parsed_json:
                    char_data = parsed_json["characters"]
                if not rel_data and "relationships" in parsed_json:
                    rel_data = parsed_json["relationships"]

                # Format 3: Story Bible → protagonist + relationships (current observed format)
                if not char_data and "Story Bible" in parsed_json:
                    sb = parsed_json["Story Bible"]
                    if "protagonist" in sb:
                        char_data = {sb["protagonist"]["name"]: sb["protagonist"]}
                    if "relationships" in sb:
                        rel_data = sb["relationships"]

                # Format 4: main_characters
                if not char_data and "main_characters" in parsed_json:
                    char_data = parsed_json["main_characters"]

                # Insert / Update characters
                if char_data and isinstance(char_data, dict):
                    for name, info in char_data.items():
                        if not isinstance(info, dict):
                            continue
                        c.execute('''
                            INSERT INTO characters (story_id, name, short_term_goal, mid_term_goal, long_term_goal,
                                                    personality, mbti, appearance, abilities, traits, items,
                                                    background, current_state)
                            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                            ON CONFLICT(story_id, name) DO UPDATE SET
                                short_term_goal = excluded.short_term_goal,
                                mid_term_goal = excluded.mid_term_goal,
                                long_term_goal = excluded.long_term_goal,
                                personality = excluded.personality,
                                mbti = excluded.mbti,
                                appearance = excluded.appearance,
                                abilities = excluded.abilities,
                                traits = excluded.traits,
                                items = excluded.items,
                                background = excluded.background,
                                current_state = excluded.current_state,
                                updated_at = CURRENT_TIMESTAMP
                        ''', (
                            story_id, name,
                            info.get("short_term_goal") or info.get("short_term_goal"),
                            info.get("mid_term_goal"),
                            info.get("long_term_goal"),
                            info.get("personality"),
                            info.get("mbti"),
                            info.get("appearance"),
                            json.dumps(info.get("abilities", [])) if info.get("abilities") else None,
                            info.get("traits"),
                            json.dumps(info.get("items", [])) if info.get("items") else None,
                            info.get("background"),
                            info.get("current_state")
                        ))
                    logger.info(f"Synced {len(char_data)} characters for story {story_id}")

                # Insert / Update relationships
                if rel_data:
                    if isinstance(rel_data, dict):
                        # Convert dict format {"小櫻": {"type":.., "trust":..}} to list
                        rel_list = []
                        for char_b, rel_info in rel_data.items():
                            if isinstance(rel_info, dict):
                                rel_list.append({
                                    "character_a": char_data.get("name", "sley") if char_data else "sley",
                                    "character_b": char_b,
                                    "relationship_type": rel_info.get("type") or rel_info.get("relationship_type"),
                                    "trust_level": rel_info.get("trust"),
                                    "affection_level": rel_info.get("affection"),
                                    "tension_level": rel_info.get("tension")
                                })
                        rel_data = rel_list

                    if isinstance(rel_data, list):
                        for rel in rel_data:
                            if not isinstance(rel, dict):
                                continue
                            c.execute('''
                                INSERT INTO character_relationships (story_id, character_a, character_b,
                                                                     relationship_type, trust_level, affection_level,
                                                                     tension_level, relationship_summary, last_interaction_chapter)
                                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                                ON CONFLICT(story_id, character_a, character_b) DO UPDATE SET
                                    relationship_type = excluded.relationship_type,
                                    trust_level = excluded.trust_level,
                                    affection_level = excluded.affection_level,
                                    tension_level = excluded.tension_level,
                                    relationship_summary = excluded.relationship_summary,
                                    last_interaction_chapter = excluded.last_interaction_chapter,
                                    updated_at = CURRENT_TIMESTAMP
                            ''', (
                                story_id,
                                rel.get("character_a") or rel.get("from"),
                                rel.get("character_b") or rel.get("to"),
                                rel.get("relationship_type") or rel.get("type"),
                                rel.get("trust_level") or rel.get("trust"),
                                rel.get("affection_level") or rel.get("affection"),
                                rel.get("tension_level") or rel.get("tension"),
                                rel.get("relationship_summary"),
                                chapter_num
                            ))
                        logger.info(f"Synced {len(rel_data)} relationships for story {story_id}")

                # Insert memory record (simple event summary)
                c.execute('''
                    INSERT INTO memories (story_id, memory_type, key, value, updated_at)
                    VALUES (?, ?, ?, ?, ?)
                ''', (
                    story_id,
                    "chapter_event",
                    f"chapter_{chapter_num}",
                    json.dumps({
                        "chapter": chapter_num,
                        "choice": user_choice,
                        "summary": chapter_content[:300] + "..."
                    }, ensure_ascii=False),
                    datetime.now().isoformat()
                ))

            except Exception as e:
                logger.warning(f"Failed to sync v3 tables from Story Bible: {e}")

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