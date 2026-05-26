#!/usr/bin/env python3
"""
List all stories with progress info.
Usage: python list_stories.py
"""
import sqlite3
import json

DB_PATH = "/home/workdir/artifacts/story_memories.db"

def list_stories():
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    
    cursor.execute('''
        SELECT s.id, s.title, s.background, s.current_chapter, s.last_updated, 
               COUNT(c.id) as chapter_count
        FROM stories s
        LEFT JOIN chapters c ON s.id = c.story_id
        GROUP BY s.id
        ORDER BY s.last_updated DESC
    ''')
    
    rows = cursor.fetchall()
    conn.close()
    
    if not rows:
        print("No stories found. Start a new one!")
        return
    
    print("=== Your Story Library ===")
    for row in rows:
        story_id, title, bg, curr_ch, last_up, ch_count = row
        print(f"ID: {story_id} | '{title}' ({bg})")
        print(f"   Chapters: {curr_ch} | Last updated: {last_up}")
        print()
    
    return rows

if __name__ == "__main__":
    list_stories()