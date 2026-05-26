#!/usr/bin/env python3
"""
Update style preferences for a story (fine-tuning the bot).
Usage: python update_style.py <story_id> <key> <value>
Example: python update_style.py 5 tone "more suspenseful and dialogue-heavy"
Or: python update_style.py 5 focus "internal monologues and emotional consequences"
"""
import sqlite3
import sys
import json

DB_PATH = "/home/workdir/artifacts/story_memories.db"

def update_style(story_id, key, value):
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    
    cursor.execute('SELECT style_preferences FROM stories WHERE id = ?', (story_id,))
    row = cursor.fetchone()
    if not row:
        print(f"Story {story_id} not found.")
        return
    
    prefs = json.loads(row[0]) if row[0] else {"user_adjustments": []}
    
    if key == "user_adjustments":
        prefs.setdefault("user_adjustments", []).append(value)
    else:
        prefs[key] = value
    
    cursor.execute('''
        UPDATE stories SET style_preferences = ? WHERE id = ?
    ''', (json.dumps(prefs), story_id))
    
    conn.commit()
    conn.close()
    print(f"Style updated for story {story_id}: {key} = {value}")
    print(f"Current preferences: {prefs}")

if __name__ == "__main__":
    if len(sys.argv) < 4:
        print("Usage: python update_style.py <story_id> <key> <value>")
        sys.exit(1)
    story_id = int(sys.argv[1])
    key = sys.argv[2]
    value = " ".join(sys.argv[3:])  # allow spaces in value
    update_style(story_id, key, value)