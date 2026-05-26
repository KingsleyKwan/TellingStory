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
                "content": ch[2][:500] + "..." if len(ch[2]) > 500 else ch[2],  # truncated for context
                "choice_made": ch[3]
            } for ch in reversed(chapters)
        ],
        "memory": memory
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