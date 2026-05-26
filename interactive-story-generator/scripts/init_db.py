#!/usr/bin/env python3
"""
Initialize the story memories database if it doesn't exist.
Creates tables: stories, chapters, memories.
DB location: /home/workdir/artifacts/story_memories.db
"""
import sqlite3
import os
from datetime import datetime

DB_PATH = "/home/workdir/artifacts/story_memories.db"

def init_db():
    os.makedirs(os.path.dirname(DB_PATH), exist_ok=True)
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    
    # Stories table (v2 - with Story Bible)
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS stories (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            title TEXT NOT NULL,
            background TEXT NOT NULL,
            created_at TEXT DEFAULT CURRENT_TIMESTAMP,
            last_updated TEXT DEFAULT CURRENT_TIMESTAMP,
            current_chapter INTEGER DEFAULT 0,
            style_preferences TEXT DEFAULT '{}',
            story_bible TEXT DEFAULT '{}'   -- Categorized Story Bible (locations, characters, relationships, active plots)
        )
    ''')
    
    # Chapters table
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS chapters (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            story_id INTEGER NOT NULL,
            chapter_num INTEGER NOT NULL,
            title TEXT,
            content TEXT NOT NULL,
            choice_made TEXT,
            timestamp TEXT DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (story_id) REFERENCES stories (id) ON DELETE CASCADE
        )
    ''')
    
    # Memories table (v2 - categorized long-term memory)
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS memories (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            story_id INTEGER NOT NULL,
            chapter_num INTEGER NOT NULL,
            summary TEXT NOT NULL,
            key_events TEXT,
            character_states TEXT,
            plot_tension INTEGER DEFAULT 5,
            user_feedback TEXT,
            story_bible_snapshot TEXT DEFAULT '{}',  -- Full categorized bible at this point
            categorized_events TEXT,                 -- JSON array of detailed events {event_id, overview, full_details, related_characters, location, consequences}
            locations_state TEXT,                    -- Current state of all locations
            relationships_map TEXT,                  -- Character relationship graph
            timestamp TEXT DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (story_id) REFERENCES stories (id) ON DELETE CASCADE
        )
    ''')
    
    conn.commit()
    conn.close()
    print(f"Database initialized successfully at {DB_PATH}")
    return DB_PATH

if __name__ == "__main__":
    init_db()