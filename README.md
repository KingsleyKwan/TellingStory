# sleyStory

**Interactive Storytelling Bot** — 繁體中文長篇互動故事生成器

Implements the interactive-story-generator skill with persistent memory.

## Key Fixes Applied (2026-06-01)
- Story context loading (last 3 chapters)
- Chapter persistence + correct numbering
- User can provide initial story prompt via `/newstory 故事描述`
- Prevents immediate memory loss and repetition

## Usage
- `/newstory 我要講香港現代懸疑故事，主角是記者`
- Then reply with A / B / C / D / E / I to continue

See skill docs for full rules.

## Hybrid AI Architecture (v3+)

- **Main Story Generation**: xAI Grok (`grok-3-latest`) — creative, detailed Traditional Chinese narrative
- **Guardrail (Consistency Check)**: Local LM Studio (`gemma-4-E4B`) — validates character consistency before sending to user
- **Image Generation (I option)**:
  - `IMAGE_MODE=groq` → Grok Imagine (placeholder)
  - `IMAGE_MODE=comfyui` → Local ComfyUI

### Environment Variables
Copy `.env.example` to `.env` and fill in your keys.

### New Commands
- `/image_mode groq` or `/image_mode comfyui`
- `/test_guardrail` — test the local consistency checker

All data (characters, relationships, memories) is stored in `stories.db`.
