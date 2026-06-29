---
name: ad-learnings
description: Give Claude eyes & ears on a short-form video ad, then produce creative learnings. Use when the user shares an ad video (local file path or TikTok/Reels/YouTube/Meta URL) and wants a teardown, advice on how to enhance future content, or an incrementality test design for a content/series format. Triggers on "analyze this ad", "watch this video", "teardown", "what can we learn from this creative", "how do I test this format", "incrementality test".
---

# ad-learnings

Eyes + ears come from the `2Sense` MCP server (works in Claude Code AND the Desktop
app). You, the orchestrator, do the thinking.

## Step 1 — Perceive (eyes + ears)

Call the MCP tool **`mcp__2Sense__analyze_ad`** with `source` = the path or URL the
user gave (optionally `language: "fr"`/`"en"` to force transcription language).

It returns one text block (timestamp legend + transcript) followed by the **contact-sheet
images** — each grid cell is a frame with its timestamp burned in top-left. Look at the
images (eyes) and read the transcript (ears).

- If the `2Sense` MCP isn't connected, tell the user to reconnect MCP / restart, or run
  the CLI fallback yourself: `/Users/stephanedeprez/ads-learnings-1000/bin/ee prep "<src>"`.
- CLI-only optimization for batch/long jobs: instead of the MCP images landing in your
  context, run `ee prep` then spawn the **ad-eyes** sub-agent (`subagent_type: "ad-eyes"`)
  on the sheets dir + manifest; it returns a compact JSON timeline. Use this when
  analyzing many videos at once.

## Step 2 — Load brand context before judging

Perception is raw; good advice needs the brand's frame:
- **Which brand?** If unclear, ask. Load canon with the `novexlab` or `hautessence`
  skills, or `qmd query "..."` / the `obsidian` MCP. Don't invent positioning, audience,
  or offer — look it up.
- Pull audience, core values, awareness stages, UMP/UMS, and existing creative frameworks
  (pain points, concepts, format shows) relevant to this ad.

## Step 3 — Teardown

Ground every claim in a timestamp (from the burned-in frame times + transcript segments):
1. **Hook (0–3s)** — what's shown/said, the device, does it earn the next 3s? Quote it.
2. **Retention & pacing** — cut rhythm, energy, dead spots.
3. **Message & awareness stage** — claim/desire channeled; fit to the audience's
   awareness level for this brand.
4. **Clarity** — legible without sound? (captions burned in? on-screen text?)
5. **Brand & product** — first appearance vs. attention peak.
6. **CTA** — present? clear? well-timed?

## Step 4 — Two deliverables

**A) Enhance future content.** Concrete, prioritized changes for the *next* assets in
this style (not a rewrite of this one). Tie each to a lever (hook variant, new pain
point/angle, pacing, proof, CTA); propose specific new hook lines / scene swaps. Reuse
the brand's own frameworks (e.g. the direct-response creative suite), not generic tips.

**B) Incrementality test for the format/series.** Design a test of whether this *format*
drives **incremental** outcomes, not just attributed ones:
- Hypothesis ("This <format> lifts <metric> incrementally vs. <control>").
- Method fit for a bootstrapped DTC brand: Meta/TikTok **conversion-lift / ghost-holdout**,
  **geo holdout / matched-market**, or a clean **format-level A/B** (same offer + spend,
  format the only variable).
- Define: unit of randomization, control (PSA/holdout or alt format), primary metric +
  guardrails, minimum runtime/budget for a readable result, and the decision rule that
  greenlights scaling the format.
- Flag confounds (creative fatigue, audience overlap, attribution windows).

## Output
Lead with the single highest-leverage insight in one sentence. Then teardown, then the
two deliverables. Prose first; a short table only for the test design or change list.
Specific and brand-grounded — no generic ad clichés.

## Notes
- Series learning: run `analyze_ad` on several videos and compare for patterns (recurring
  hooks, pacing, what the winners share).
- Ad from a library MCP (Meta Ad Library / Foreplay-style)? Download the video, then pass
  the local file path to `analyze_ad`.
