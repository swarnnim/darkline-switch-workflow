# Flip the Switch — Track 02 demo workflow

Status: BUILT AND VERIFIED 2026-11-04. The workflow below ran end-to-end
twice — once in a Switch room, once in the Mattermost channel — with a
self-hosted Switch 0.31.0 stack and the Darkline Producer agent
(OpenCode provider) connected through the headless agent controller.
Full transcripts: demo-transcripts.md in this folder.

## The workflow (human + agent, Switch central)
1. Human posts a DARKLINE horror-short seed in the team chat, e.g.:
   "Seed: a lift that stops on a floor that does not exist. 60s, diabolical tone."
2. Agent replies in-chat with:
   - a ~55–60s narration script draft (one paragraph, speakable),
   - a thumbnail brief (≤4 words, bold, designed — not a frame-grab),
   - 3 visual beats (one line each).
3. Human approves or edits in-chat (approval is a chat message, not a form).
4. Agent returns a production checklist:
   - [ ] script locked (final text pasted back)
   - [ ] 6×10s clip plan matches the 3 beats
   - [ ] narration voice + captions + SFX noted
   - [ ] music added post-upload via YouTube Studio Audio Library rotation
   - [ ] thumbnail brief handed to Canva step
5. Human confirms "ship it" — only then is the short a candidate for the
   normal DARKLINE pipeline (separate job, separate approval).

## Why this fits Track 02
- Real task, not a toy: it is the actual first step of a DARKLINE short.
- Switch is central: seed, draft, approval, and checklist all live in the
  team chat; the agent never works outside the chat thread.
- >=1 agent + >=1 person complete the task together, in order, with the
  human's approval gating the output.

## How the run was produced
- Self-hosted switch-core 0.31.0 + PostgreSQL 16 + Mattermost 11.9,
  seeded with upstream's setup.py (see the repo README for why the
  stack runs host-natively in this build environment).
- Agent "darkline" created through the Switch management API and
  placed on the headless switch-agent-controller; model served by the
  $0 OpenRouter shim (free-tier models only).
