#!/usr/bin/env python3
"""
Create a new story record in the database.
Usage: python create_story.py "Story Title" "Real World - Modern Hong Kong" "Initial setup prompt here (optional)"
Returns: the new story_id
"""
import sqlite3
import sys
import json
from datetime import datetime

DB_PATH = "/home/workdir/artifacts/story_memories.db"

def create_story(title, background, initial_prompt=""):
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    
    cursor.execute('''
        INSERT INTO stories (title, background, style_preferences)
        VALUES (?, ?, ?)
    ''', (title, background, json.dumps({"tone": "engaging", "focus": "character development", "user_adjustments": []})))
    
    story_id = cursor.lastrowid
    conn.commit()
    conn.close()
    
    print(f"New story created: ID={story_id}, Title='{title}', Background='{background}'")
    if initial_prompt:
        print(f"Initial prompt: {initial_prompt}")
    return story_id

if __name__ == "__main__":
    if len(sys.argv) < 3:
        print("Usage: python create_story.py <title> <background> [initial_prompt]")
        sys.exit(1)
    
    title = sys.argv[1]
    background = sys.argv[2]
    initial_prompt = sys.argv[3] if len(sys.argv) > 3 else ""
    create_story(title, background, initial_prompt)