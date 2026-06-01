## Cursor Cloud specific instructions

This is an MCP skill project consisting of Python CLI scripts for an interactive story generator. There is no web server, API, or frontend—scripts are invoked directly via the command line.

### Project structure

- `interactive-story-generator/SKILL.md` — full skill specification
- `interactive-story-generator/scripts/` — 6 Python scripts (see README and SKILL.md for details)

### Prerequisites

- **Python 3.x** (standard library only; no `pip install` or `requirements.txt` needed)
- The database directory `/home/workdir/artifacts/` must exist and be writable. Create it before first run:
  ```
  sudo mkdir -p /home/workdir/artifacts && sudo chmod 777 /home/workdir
  ```

### Running the scripts

All scripts are in `interactive-story-generator/scripts/`. Standard workflow:

1. `python3 interactive-story-generator/scripts/init_db.py` — initialise SQLite DB (idempotent, safe to re-run)
2. `python3 interactive-story-generator/scripts/create_story.py "<title>" "<background>"` — create a story
3. `python3 interactive-story-generator/scripts/save_chapter.py <story_id> <chapter_num> "<title>" "<content>" "<choice>" '<memory_json>'` — save chapter + memory
4. `python3 interactive-story-generator/scripts/load_context.py <story_id>` — load context for AI continuation
5. `python3 interactive-story-generator/scripts/list_stories.py` — list all stories
6. `python3 interactive-story-generator/scripts/update_style.py <story_id> <key> "<value>"` — update style prefs

### Gotchas

- The DB path is **hardcoded** to `/home/workdir/artifacts/story_memories.db` across all scripts. If you need a different path, every script must be updated.
- There are **no automated tests, linting, or build steps** configured in this repository.
- `init_db.py` uses `CREATE TABLE IF NOT EXISTS`, so it is safe to run multiple times without data loss.
