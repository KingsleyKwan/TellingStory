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
    
    # v3 - Character consistency tables
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS characters (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            story_id INTEGER NOT NULL,
            name TEXT NOT NULL,
            short_term_goal TEXT,
            mid_term_goal TEXT,
            long_term_goal TEXT,
            personality TEXT,
            mbti TEXT,
            appearance TEXT,
            abilities TEXT,           -- JSON array 格式，例如 ["超強記憶力", "精通格鬥"]
            traits TEXT,
            items TEXT,               -- JSON array 格式
            background TEXT,
            current_state TEXT,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (story_id) REFERENCES stories(id) ON DELETE CASCADE,
            UNIQUE(story_id, name)
        )
    ''')

    cursor.execute('''
        CREATE TABLE IF NOT EXISTS character_relationships (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            story_id INTEGER NOT NULL,
            character_a TEXT NOT NULL,
            character_b TEXT NOT NULL,
            relationship_type TEXT,           -- 父親、情侶、敵人、盟友、暗戀、師徒、競爭對手...
            trust_level INTEGER DEFAULT 50,   -- 0-100
            affection_level INTEGER DEFAULT 0,
            tension_level INTEGER DEFAULT 0,
            relationship_summary TEXT,
            history_summary TEXT,
            last_interaction_chapter INTEGER,
            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (story_id) REFERENCES stories(id) ON DELETE CASCADE,
            UNIQUE(story_id, character_a, character_b)
        )
    ''')

    conn.commit()
    conn.close()
    print(f"Database initialized successfully at {DB_PATH}")
    return DB_PATH

if __name__ == "__main__":
    init_db()