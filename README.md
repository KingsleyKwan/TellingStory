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
