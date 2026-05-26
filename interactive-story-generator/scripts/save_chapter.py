#!/usr/bin/env python3
"""
Save a new chapter and update long-term memory for a story.
Usage: python save_chapter.py <story_id> <chapter_num> "<chapter_title>" "<full_content>" "<choice_made>" '<memory_summary_json>'
Where memory_summary_json is a JSON string like:
{"summary": "Protagonist met ally and discovered clue.", "key_events": ["met ally", "found map"], "character_states": {"protagonist": "curious and determined"}, "plot_tension": 7, "user_feedback": []}
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
    
    conn.commit()
    conn.close()
    print(f"Chapter {chapter_num} saved for story {story_id}. Memory updated.")

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