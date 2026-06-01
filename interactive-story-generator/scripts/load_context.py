#!/usr/bin/env python3
"""
Load full context for continuing a story: last chapters, memory summary, style prefs.
Usage: python load_context.py <story_id> [num_last_chapters=3]
Outputs JSON to stdout for easy parsing by AI.
"""
import sqlite3
import sys
import json

DB_PATH = "/home/workdir/artifacts/story_memories.db"

def load_context(story_id, num_last=3):
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    
    # Get story info
    cursor.execute('SELECT title, background, current_chapter, style_preferences FROM stories WHERE id = ?', (story_id,))
    story_row = cursor.fetchone()
    if not story_row:
        print(json.dumps({"error": "Story not found"}))
        return
    
    title, background, current_chapter, style_prefs = story_row
    style = json.loads(style_prefs) if style_prefs else {}
    
    # Get last N chapters
    cursor.execute('''
        SELECT chapter_num, title, content, choice_made, timestamp 
        FROM chapters 
        WHERE story_id = ? 
        ORDER BY chapter_num DESC 
        LIMIT ?
    ''', (story_id, num_last))
    chapters = cursor.fetchall()
    
    # Get latest memory
    cursor.execute('''
        SELECT summary, key_events, character_states, plot_tension, user_feedback, chapter_num
        FROM memories 
        WHERE story_id = ? 
        ORDER BY chapter_num DESC 
        LIMIT 1
    ''', (story_id,))
    mem_row = cursor.fetchone()
    
    memory = {}
    if mem_row:
        memory = {
            "summary": mem_row[0],
            "key_events": json.loads(mem_row[1]) if mem_row[1] else [],
            "character_states": json.loads(mem_row[2]) if mem_row[2] else {},
            "plot_tension": mem_row[3],
            "user_feedback": json.loads(mem_row[4]) if mem_row[4] else [],
            "last_chapter_num": mem_row[5]
        }
    
    # v3 - Load characters
    cursor.execute('''
        SELECT name, short_term_goal, mid_term_goal, long_term_goal, personality, mbti,
               appearance, abilities, traits, items, background, current_state
        FROM characters WHERE story_id = ?
    ''', (story_id,))
    char_rows = cursor.fetchall()
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

    # v3 - Load relationships
    cursor.execute('''
        SELECT character_a, character_b, relationship_type, trust_level, affection_level,
               tension_level, relationship_summary, history_summary, last_interaction_chapter
        FROM character_relationships WHERE story_id = ?
    ''', (story_id,))
    rel_rows = cursor.fetchall()
    relationships = [
        {
            "character_a": r[0],
            "character_b": r[1],
            "relationship_type": r[2],
            "trust_level": r[3],
            "affection_level": r[4],
            "tension_level": r[5],
            "relationship_summary": r[6],
            "history_summary": r[7],
            "last_interaction_chapter": r[8]
        } for r in rel_rows
    ]

    context = {
        "story_id": story_id,
        "title": title,
        "background": background,
        "current_chapter": current_chapter,
        "style_preferences": style,
        "last_chapters": [
            {
                "num": ch[0],
                "title": ch[1],
                "content": ch[2][:500] + "..." if len(ch[2]) > 500 else ch[2],
                "choice_made": ch[3]
            } for ch in reversed(chapters)
        ],
        "memory": memory,
        "characters": characters,
        "relationships": relationships
    }
    
    conn.close()
    print(json.dumps(context, indent=2))
    return context

if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Usage: python load_context.py <story_id> [num_last_chapters]")
        sys.exit(1)
    story_id = int(sys.argv[1])
    num_last = int(sys.argv[2]) if len(sys.argv) > 2 else 3
    load_context(story_id, num_last)