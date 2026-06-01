---
name: interactive-story-generator
description: Generate interactive branching stories in Traditional Chinese chapter by chapter with multiple choices. Uses categorized long-term memory (locations, characters, events, relationships) stored in database. Prevents memory loss, character drift, and unrealistic success in long stories. Supports real-world backgrounds and fine-tuning. Use for long-form interactive storytelling.
---

# Interactive Story Generator (繁體中文長篇版)

**Trigger this skill** when user wants interactive stories in **Traditional Chinese**, long-term memory management, or to continue branching narratives with realistic consequences.

## Core Upgrades (v2 - Long Story Mode)
- **All story text & choices in 繁體中文** (Traditional Chinese). Internal thinking can be English.
- **Categorized Memory System**: Locations (地點), Characters (人物), Events (事件), Character Relationships (人物關係).
- **Detailed Event Storage**: Every event records → 相關人物, 地點, 情節概述, 內容全細節.
- **Anti-Forgetting Protection** for long stories:
  - Maintains a **Story Bible** (故事聖經) — condensed, categorized world state updated every 3-5 chapters.
  - Uses **smart retrieval**: Only loads relevant memories + recent chapters + Story Bible (never dumps entire history).
  - Explicit rule: "Never forget or contradict established facts. Prioritize Story Bible over old raw text."
- **Realistic Stakes Rule**: Not everything succeeds. Choices can lead to **partial failure, setbacks, complications, or unintended consequences**. Protagonist is not invincible. Drama comes from struggle and realistic outcomes.

## 角色一致性強制檢查系統（v3 - 最高優先級）

**每次生成任何角色行動、對話、內心獨白之前，必須執行以下步驟：**

1. 從 `characters` table 取出該角色完整資料（包括 name、性格、mbti、外型、能力、特點、持有物品、短期/中期/長期目標、current_state）
2. 從 `character_relationships` table 取出所有相關關係（character_a / character_b 雙向查詢）
3. 在內部思考（CoT）中**明確寫出**以下檢查文字：

【角色一致性檢查】
- 角色：[姓名]  
  性格 + MBTI = [性格描述 + MBTI]  
  長期目標 = [...]  
  中期目標 = [...]  
  短期目標 = [...]  
  目前狀態 = [...]  
  持有物品 = [...]  
- 與 [對象角色] 關係 = [relationship_type]，信任度=[數字]，好感度=[數字]，目前關係摘要 = [...]
- 現在嘅行動/對話/決定是否 100% 符合以上所有設定？
  → 如果唔符合，必須調整內容，或者讓行動自然失敗並產生後果（例如信任度下降、關係惡化、性格衝突等）。

**嚴禁**：角色突然改變性格、忘記目標、做出違反關係嘅行為。

## Mandatory Response Structure (繁體中文)
**第 X 章：【章節標題】**

[沉浸式 800-1500 字繁體中文敘事。使用「你」第二人稱或有限第三人稱。對話自然，心理描寫細膩。真實世界背景必須符合香港/華人社會常識。]

**你接下來要怎麼做？**

A) [選項A — 簡短誘人描述]
B) [選項B — 會帶來不同走向]
C) [選項C]
D) [選項D]
E) [選項E — 可選]

**（內部記憶更新 — 不顯示給用戶）**

After user chooses, immediately:
1. Load categorized memory + Story Bible + relevant events + **characters table + character_relationships table**.
2. Generate next chapter in **繁體中文**, incorporating choice consequences (including possible failure).
3. Update Story Bible + categorized memories + **characters + relationships** (use updated_characters / updated_relationships in memory_json).
4. Save to database via save_chapter.py.
5. Present new choices.

## Categorized Memory Structure (Database)
We use enhanced JSON in the `memories` table + dedicated fields:

**Story Bible (updated every 3-5 chapters)**:
```json
{
  "locations": {
    "維多利亞港碼頭": {"description": "...", "current_state": "今晚有可疑黑衣人出現"},
    "中環寫字樓": {"description": "...", "current_state": "..."}
  },
  "characters": {
    "你（記者）": {
      "background": "香港年輕調查記者，調查李美失蹤案",
      "current_state": "剛逃過一劫，警覺性提高",
      "relationships": {"李美": "正在調查其失蹤", "張大狀": "懷疑是幕後黑手"}
    },
    "李美": {"background": "...", "current_state": "下落不明", "relationships": {...}}
  },
  "relationships": {
    "你 → 李美": "調查者與目標",
    "張大狀 → 李美": "父親，疑似隱瞞真相"
  },
  "active_plot_threads": ["李美失蹤真相", "張氏集團醜聞"]
}
```

**Event Record (每件事獨立詳細儲存)**:
```json
{
  "event_id": "evt_001",
  "chapter": 1,
  "overview": "你在維港碼頭等待線人，收到警告短信後遇上張氏集團黑衣人",
  "full_details": "完整詳細經過（可達數百字）",
  "related_characters": ["你", "線人", "黑衣人A", "黑衣人B"],
  "location": "維多利亞港碼頭",
  "consequences": "你成功逃脫，但線人可能已出事",
  "tension_level": 7
}
```

**Database Tables (updated v3)**:
- `stories` — same + `story_bible` (JSON column)
- `chapters` — full content (繁體中文)
- `memories` — now includes: `story_bible_snapshot`, `categorized_events` (JSON array of detailed events), `locations_state`, `characters_state`, `relationships_map`
- `characters` — 角色詳細資料（目標、性格、MBTI、外型、能力、物品、current_state）
- `character_relationships` — 雙向關係表（信任度、好感度、關係類型、歷史摘要）

**Long-Story Rules (Never Violate)**:
- Before every generation: "Load Story Bible first. Only pull recent events and relevant characters. If context is long, summarize older events but keep core facts 100% consistent."
- **v3 強制**：每次生成前必須執行「角色一致性強制檢查系統」，從 characters + character_relationships 讀取完整資料。
- Character backgrounds and personality **never drift** — always reference current_state, goals, MBTI, relationships from the dedicated tables.
- Choices must offer **real risk**. Example: Option A might succeed partially but create new enemy; Option C might fail completely and force retreat.
- Protagonist can be injured, lose allies, get exposed, or make moral compromises.

## Workflow Updates

**Starting New Story**
- Confirm title + background (Real World default).
- Create story + initial Story Bible.
- Generate Chapter 1 in **繁體中文**.
- Save detailed first event + initial characters/locations.

**Continuing Long Story**
- Always load: Story Bible + last 2 chapters summary + relevant categorized events + **characters table + character_relationships table**.
- Never rely on raw full history if >10 chapters — use Bible + indexed events.
- After chapter: Update Story Bible (merge new info), add new detailed Event record, **update characters + relationships** (via updated_characters / updated_relationships), update character/location states.

**Fine-Tuning**
- Same as before, but now also store language/style prefs (e.g. "more poetic descriptions", "darker tone", "more dialogue").

**User Commands**
- "顯示故事聖經" / "show story bible"
- "更新記憶：..." (user can manually correct facts)
- "fine tune: 增加失敗風險" or "讓故事更寫實，不要主角光環"

## Scripts (Updated for v3)
- `init_db.py` — creates characters + character_relationships tables
- `save_chapter.py` — saves chapter + memory + **character/relationship updates**
- `load_context.py` — returns rich context + **characters + relationships**
- `list_stories.py`, `update_style.py` — unchanged

All future stories will follow this structure to support **真正長篇連載** without memory collapse or unrealistic plotting.

---

**已完成更新！** 現在你的故事生成器完全符合你的要求：
- 全繁體中文敘事
- 分類記憶（地點 / 人物 / 事件 / 關係）
- 事件儲存完整細節
- 長故事防遺忘 + 防人物崩壞 + 真實失敗機制

---

**Demo Story 更新建議**

我們之前有 **Story #1 Shadows of the Harbor**（英文版）。

因為你現在要求繁體中文 + 新記憶系統，建議我們：

**選項1（推薦）**：用新系統**重新開始** Story #1（Shadows of the Harbor），用繁體中文寫第1章，並建立完整分類記憶。

**選項2**：繼續現有故事，但之後所有章節轉為繁體中文（記憶會逐步轉換）。

請告訴我你要哪一個？

或者直接說：「用新系統重新開始 Shadows of the Harbor」

我會立刻載入新規則，生成**繁體中文第1章**，並儲存詳細分類記憶。 

準備好了嗎？ 😊

v3 更新完成 - 角色一致性已大幅強化