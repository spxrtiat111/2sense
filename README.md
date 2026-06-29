# ads-learnings — eyes & ears for Claude

Give Claude the ability to **see and hear short-form video ads**, so it can give grounded
advice on (a) enhancing future content and (b) designing incrementality tests for a
content/series format.

Claude is the **brain**. The pipeline only does **perception**, delivered as one MCP tool:

```
analyze_ad(source)                                   ← MCP tool (CLI + Desktop app)
   │  ingest   → yt-dlp (URLs) → local mp4
   │  ffmpeg   → frames @ 3fps → Pillow contact sheets (labeled) + manifest   (EYES)
   │  ffmpeg   → mono wav → Groq whisper-large-v3 → transcript + segments      (EARS)
   │  numpy    → audio energy/rhythm: tempo, energy curve, onsets, dynamics    (EARS+)
   │  YAMNet   → audio-event tags: music/speech/instruments/genre/SFX          (EARS+)
   ▼
returns: [ text (timestamp legend + transcript), sheet image, sheet image, … ]
   ▼
Claude sees the sheets + reads the transcript → teardown + 2 deliverables
```

No model runs on your Mac — locally it's just `ffmpeg` (bundled), `yt-dlp`, and Pillow,
managed by `uv`. The only hosted call is Whisper on Groq.

## Where it's wired

The `2Sense` MCP server exposes four tools, available in **both** surfaces:
- **`analyze_ad(source, language="auto")`** — full eyes + ears: contact-sheet images,
  transcript, audio energy/rhythm profile, AND YAMNet audio-event tags.
- **`transcribe(path, language="auto")`** — speech transcript only (Groq Whisper).
- **`audio_profile(path)`** — music/energy signals (free numpy): tempo, energy curve, onsets.
- **`audio_events(path)`** — YAMNet tags (free, local): music/speech/instruments/genre/SFX
  + a coarse timeline. No mood (happy/sad) — YAMNet covers events, not affect.

| Surface | How | Tool namespace |
|---|---|---|
| Claude Code (CLI + Code apps, any dir) | user-scope MCP in `~/.claude.json` | `mcp__2Sense__analyze_ad` |
| Claude Desktop app | `claude_desktop_config.json` | `analyze_ad` |
| This repo (portable) | project `.mcp.json` | — |

Claude Code also gets the **`ad-learnings` skill** + **`ad-eyes` sub-agent** (symlinked into
`~/.claude/`) for the guided teardown workflow. The Desktop app uses the MCP tool directly.

## Setup

```bash
# 1. Free Groq key: https://console.groq.com/keys → paste into .env (GROQ_API_KEY=)
cp .env.example .env
# 2. Verify:
bin/ee doc --ping
```
Then **restart Claude Code and the Desktop app** so the MCP server (and the global
skill/agent) load.

> Notes: the project pins **Python 3.12** (TensorFlow/YAMNet requirement). The first
> `audio_events` / `analyze_ad` call downloads the ~15 MB YAMNet model once (then cached).
> Disable the audio layers in `config.toml` (`[audio] profile`, `yamnet`) if you want
> speech-only ears.

## Use

- **Claude Code or Desktop:** *"analyze this ad: <path or URL>"* → Claude calls
  `analyze_ad`, sees the sheets, reads the transcript, and produces the analysis.
- **CLI prep only (no LLM):** `bin/ee prep "<path-or-url>"` → `data/out/<slug>/`.

Output per video: `frames/`, `sheets/`, `manifest.json`, `audio.wav`, `prep.json`
(+ `ears.json` when transcribed).

## Config
Edit `config.toml`: `fps`, `max_frames`, sheet grid (`cols`/`rows`), Whisper `model`,
`language`.

## Pieces
- `src/eyesears/` — prep CLI (`ee`) + 2Sense MCP (`ee-ears`: `analyze_ad`, `transcribe`, `audio_profile`)
- `src/eyesears/audio_features.py` — free numpy music/energy analysis
- `src/eyesears/yamnet.py` — free YAMNet audio-event tagging (TensorFlow, lazy-loaded)
- `.claude/agents/ad-eyes.md` — vision sub-agent (Claude Code batch optimization)
- `.claude/skills/ad-learnings/` — orchestration skill
- `.mcp.json` / `~/.claude.json` / `claude_desktop_config.json` — MCP registrations
