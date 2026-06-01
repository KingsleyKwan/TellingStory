#!/usr/bin/env python3
"""
local_guardrail.py - Character consistency guardrail using local LM Studio.
Used to validate story content against stored character data and relationships.
"""

import sqlite3
import json
from pathlib import Path
from openai import OpenAI
import os
from dotenv import load_dotenv

load_dotenv()

DB_PATH = Path(__file__).parent / "stories.db"
LM_STUDIO_URL = os.getenv("LM_STUDIO_URL", "http://192.168.1.96:1234/v1")
LM_STUDIO_MODEL = os.getenv("LM_STUDIO_MODEL", "gemma-4-E4B")

local_client = OpenAI(base_url=LM_STUDIO_URL, api_key="lm-studio")


def load_characters_and_relationships(story_id: int) -> dict:
    """Load all characters and relationships for a story from the database."""
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()

    # Characters
    c.execute("""
        SELECT name, short_term_goal, mid_term_goal, long_term_goal,
               personality, mbti, appearance, abilities, traits, items,
               background, current_state
        FROM characters WHERE story_id = ?
    """, (story_id,))
    char_rows = c.fetchall()

    characters = {}
    for row in char_rows:
        characters[row[0]] = {
            "short_term_goal": row[1],
            "mid_term_goal": row[2],
            "long_term_goal": row[3],
            "personality": row[4],
            "mbti": row[5],
            "appearance": row[6],
            "abilities": json.loads(row[7]) if row[7] else [],
            "traits": row[8],
            "items": json.loads(row[9]) if row[9] else [],
            "background": row[10],
            "current_state": row[11]
        }

    # Relationships
    c.execute("""
        SELECT character_a, character_b, relationship_type, trust_level,
               affection_level, tension_level, relationship_summary
        FROM character_relationships WHERE story_id = ?
    """, (story_id,))
    rel_rows = c.fetchall()

    relationships = [
        {
            "character_a": r[0],
            "character_b": r[1],
            "relationship_type": r[2],
            "trust_level": r[3],
            "affection_level": r[4],
            "tension_level": r[5],
            "relationship_summary": r[6]
        } for r in rel_rows
    ]

    conn.close()
    return {"characters": characters, "relationships": relationships}


def check_story_consistency(story_text: str, story_id: int, relevant_characters: list = None) -> dict:
    """
    Use local LM Studio as a guardrail to check if the generated story
    violates any character consistency rules.
    Returns: {"is_valid": bool, "violations": [...], "suggestions": [...]}
    """
    data = load_characters_and_relationships(story_id)
    if not data["characters"]:
        return {"is_valid": True, "violations": [], "suggestions": []}

    # Build compact character summary for the check
    char_summary = []
    for name, info in data["characters"].items():
        if relevant_characters and name not in relevant_characters:
            continue
        char_summary.append(
            f"{name}: 性格={info['personality']}, MBTI={info['mbti']}, "
            f"長期目標={info['long_term_goal']}, 目前狀態={info['current_state']}"
        )

    rel_summary = [
        f"{r['character_a']} → {r['character_b']}: {r['relationship_type']} "
        f"(信任{r['trust_level']}, 好感{r['affection_level']})"
        for r in data["relationships"]
    ]

    system_prompt = (
        "你係嚴格嘅角色一致性守門員。只能輸出 JSON，格式如下：\n"
        '{"is_valid": true/false, "violations": ["..."], "suggestions": ["..."]}\n'
        "如果內容完全符合角色設定，is_valid = true。\n"
        "如果有任何違反（性格突變、目標遺忘、關係矛盾），列出 violations 並提供修改建議。"
    )

    user_msg = f"""請檢查以下故事內容是否違反角色設定：

【角色資料】
{chr(10).join(char_summary)}

【關係資料】
{chr(10).join(rel_summary)}

【故事內容】
{story_text[:3000]}...

請嚴格檢查並以 JSON 格式回覆。"""

    try:
        response = local_client.chat.completions.create(
            model=LM_STUDIO_MODEL,
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_msg}
            ],
            temperature=0.1,
            max_tokens=800
        )
        raw = response.choices[0].message.content.strip()
        # Try to extract JSON
        if "```json" in raw:
            raw = raw.split("```json")[1].split("```")[0].strip()
        result = json.loads(raw)
        return result
    except Exception as e:
        # If guardrail fails, default to allowing the content (fail open)
        return {"is_valid": True, "violations": [], "suggestions": [], "error": str(e)}
