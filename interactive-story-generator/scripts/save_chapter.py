#!/usr/bin/env python3
"""
Save a new chapter and update long-term memory + character/relationship state for a story.
Usage: python save_chapter.py <story_id> <chapter_num> "<chapter_title>" "<full_content>" "<choice_made>" '<memory_summary_json>'

memory_summary_json now supports optional v3 fields:
{
  "summary": "...",
  "key_events": [...],
  ...
  "updated_characters": {
    "角色名": {
      "short_term_goal": "...",
      "mid_term_goal": "...",
      "long_term_goal": "...",
      "current_state": "..."
    }
  },
  "updated_relationships": [
    {
      "character_a": "角色A",
      "character_b": "角色B",
      "trust_level": 75,
      "affection_level": 30,
      "relationship_summary": "..."
    }
  ]
}
"""
import sqlite3
import sys
import json
from datetime import datetime

DB_PATH = "/home/workdir/artifacts/story_memories.db"

def save_chapter(story_id, chapter_num, title, content, choice_made, memory_json_str):
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    
    # Insert chapter
    cursor.execute('''
        INSERT INTO chapters (story_id, chapter_num, title, content, choice_made)
        VALUES (?, ?, ?, ?, ?)
    ''', (story_id, chapter_num, title, content, choice_made))
    
    # Parse memory
    try:
        mem = json.loads(memory_json_str)
    except json.JSONDecodeError:
        mem = {"summary": memory_json_str, "key_events": [], "character_states": {}, "plot_tension": 5, "user_feedback": []}
    
    # Insert or update memory (latest per chapter)
    cursor.execute('''
        INSERT INTO memories (story_id, chapter_num, summary, key_events, character_states, plot_tension, user_feedback)
        VALUES (?, ?, ?, ?, ?, ?, ?)
    ''', (
        story_id,
        chapter_num,
        mem.get("summary", ""),
        json.dumps(mem.get("key_events", [])),
        json.dumps(mem.get("character_states", {})),
        mem.get("plot_tension", 5),
        json.dumps(mem.get("user_feedback", []))
    ))
    
    # Update story's current_chapter and last_updated
    cursor.execute('''
        UPDATE stories 
        SET current_chapter = ?, last_updated = CURRENT_TIMESTAMP
        WHERE id = ?
    ''', (chapter_num, story_id))

    # v3 - Handle character and relationship updates from memory_json
    updated_characters = mem.get("updated_characters", {})
    updated_relationships = mem.get("updated_relationships", [])

    for name, data in updated_characters.items():
        cursor.execute('''
            INSERT INTO characters (story_id, name, short_term_goal, mid_term_goal, long_term_goal,
                                    personality, mbti, appearance, abilities, traits, items, background, current_state)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(story_id, name) DO UPDATE SET
                short_term_goal = excluded.short_term_goal,
                mid_term_goal = excluded.mid_term_goal,
                long_term_goal = excluded.long_term_goal,
                current_state = excluded.current_state,
                updated_at = CURRENT_TIMESTAMP
        ''', (
            story_id, name,
            data.get("short_term_goal"), data.get("mid_term_goal"), data.get("long_term_goal"),
            data.get("personality"), data.get("mbti"), data.get("appearance"),
            json.dumps(data.get("abilities", [])) if data.get("abilities") else None,
            data.get("traits"),
            json.dumps(data.get("items", [])) if data.get("items") else None,
            data.get("background"),
            data.get("current_state")
        ))

    for rel in updated_relationships:
        cursor.execute('''
            INSERT INTO character_relationships (story_id, character_a, character_b, relationship_type,
                                                 trust_level, affection_level, tension_level,
                                                 relationship_summary, history_summary, last_interaction_chapter)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(story_id, character_a, character_b) DO UPDATE SET
                relationship_type = excluded.relationship_type,
                trust_level = excluded.trust_level,
                affection_level = excluded.affection_level,
                tension_level = excluded.tension_level,
                relationship_summary = excluded.relationship_summary,
                history_summary = excluded.history_summary,
                last_interaction_chapter = excluded.last_interaction_chapter,
                updated_at = CURRENT_TIMESTAMP
        ''', (
            story_id,
            rel.get("character_a"), rel.get("character_b"),
            rel.get("relationship_type"),
            rel.get("trust_level", 50),
            rel.get("affection_level", 0),
            rel.get("tension_level", 0),
            rel.get("relationship_summary"),
            rel.get("history_summary"),
            rel.get("last_interaction_chapter", chapter_num)
        ))

    conn.commit()
    conn.close()
    print(f"Chapter {chapter_num} saved for story {story_id}. Memory + character/relationship updates applied.")

if __name__ == "__main__":
    if len(sys.argv) < 7:
        print("Usage: python save_chapter.py <story_id> <chapter_num> <title> <content> <choice_made> <memory_json>")
        sys.exit(1)
    
    story_id = int(sys.argv[1])
    chapter_num = int(sys.argv[2])
    title = sys.argv[3]
    content = sys.argv[4]
    choice_made = sys.argv[5]
    memory_json = sys.argv[6]
    save_chapter(story_id, chapter_num, title, content, choice_made, memory_json)