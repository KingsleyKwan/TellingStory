# sleyStory — Project Summary

**Last Updated:** 2026-06-03

---

## Project Aim

**sleyStory** is an AI-powered **interactive long-form storytelling system** that generates branching narratives in **Traditional Chinese (繁體中文)**.

### Core Goals
- Support **very long stories** (dozens of chapters) without memory collapse or character drift.
- Maintain **strong character consistency** (personality, goals, relationships).
- Deliver **realistic consequences** — protagonist is not invincible; choices can lead to partial failure or setbacks.
- Provide **immersive, dialogue-heavy** storytelling with rich sensory and emotional detail.
- Allow users to generate AI images for key scenes via the "I" option.

The system is designed so that future AI agents (when context window is full) can read this file to quickly understand the project's mission and current state.

---

## Completed Features

### 1. Telegram Bot Interface
- `/newstory`, `/loadstory`, `/mystories`, `/image_mode`
- Choice-driven interaction (A/B/C/D/E + I for image)
- Persistent per-user story sessions

### 2. Hybrid Story Generation
- **Main model**: Grok (xAI) — creative narrative generation
- **Guardrail**: Local LM Studio model — enforces character consistency and rule compliance
- Automatic retry + correction when guardrail detects violations

### 3. Long-Term Memory System (v3)
- **Story Bible** — condensed world state (locations, characters, active plot threads)
- **Categorized Memories**:
  - Locations
  - Characters (with `long_term_goal`, `mid_term_goal`, `short_term_goal`)
  - Events (detailed)
  - Character Relationships (`trust_level`, `affection_level`, `tension_level`)
- Database tables: `stories`, `chapters`, `memories`, `characters`, `character_relationships`

### 4. Strict Output Format
- Clean story text for user
- Hidden `---\nDATA\n\`\`\`json` block for machine state sync
- Automatic parsing and database update after every chapter

### 5. Image Generation Support
- "I) 生成本篇圖像" option at end of every chapter
- `IMAGE_MODE` switch (`groq` = text prompt only, `comfyui` = local generation)
- ComfyUI integration code exists (`generate_with_comfyui`) but currently uses a minimal hardcoded workflow

### 6. Anti-Drift & Realism Rules (enforced via SKILL.md + guardrail)
- Never contradict established facts
- Characters act according to their stored goals and personality
- Choices can result in failure, complications, or unintended consequences
- Relationships evolve naturally over chapters

### 7. User-Driven Story Correction (`/bug`)
- Users can report inconsistencies with `/bug <description>` (supports targeting specific chapters, e.g. `/bug 63 ...`)
- System uses Grok to verify if the reported conflict is real based on previous chapters + Story Bible + character states.
- If confirmed, the system **re-generates the target chapter** with the correction applied and replaces it in the database.
- Bug reports are stored in the `memories` table for audit trail.

### 8. Hybrid Generation with Automatic Fallback
- Primary generator: Grok (online) — keeps creative quality high.
- Automatic fallback: When Grok refuses (safety filter, "I won't generate", etc.), the system **automatically switches to the local LM Studio model** to generate that chapter.
- Local fallback uses a relaxed system prompt that encourages generation of mature/dark content as long as all characters are adults (18+).
- Guardrail retries also respect the model used for the original generation (Grok retries with Grok, local retries with local).
- This ensures the story can continue even when the online model hits content policy limits.

### 9. Performance Optimizations (v4)
- **45-second TTL memory cache** for `load_story_context` — eliminates repeated database reads for Story Bible, characters, and relationships.
- Reduced number of recent chapters loaded from 4 → 2 (still sufficient for context).
- **Separate lightweight guardrail model** via `GUARDRAIL_MODEL` env var — guardrail checks now run on a smaller/faster model while fallback generation uses the stronger local model.
- Cache is automatically invalidated after new chapters are saved or `/bug` corrections are applied.
- These changes significantly reduce latency without affecting story quality or any existing features.

---

## Current Configuration (as of 2026-06-03)

| Setting          | Value                          | Notes |
|------------------|--------------------------------|-------|
| `IMAGE_MODE`     | `groq`                         | Returns text prompt only |
| `GROK_MODEL`     | `grok-4.3`                     | Main creative model |
| `LM_STUDIO_MODEL`| `gemma-4-E4B`                  | Local guardrail |
| ComfyUI          | Partially implemented          | Hardcoded workflow needs improvement |

---

## Known Limitations / TODOs

- ComfyUI image generation is not reliable (hardcoded node IDs, empty prompt bug when choosing "I")
- No automatic workflow loading from ComfyUI
- Story Bible is only partially synced in the current JSON parsing logic
- No web UI or story export feature yet
- Need a robust way for future agents to load this summary when context is full

---

## Recommended Next Steps

1. Improve ComfyUI integration (load saved workflow JSON or make it configurable)
2. Add a proper image prompt generation step **before** calling image generation (currently passes empty content on "I")
3. Create an `AGENTS.md` or update this file whenever major features are added
4. Consider publishing the TellingStory repository as the canonical home for this project

---

**Purpose of this file**:  
When the agent's context window is full, the next agent should read `PROJECT_SUMMARY.md` first to understand what has already been built and what the mission is.