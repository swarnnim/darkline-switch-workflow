# Darkline Producer — a Switch workflow for a daily AI horror channel

**Flip the Switch Hackathon (WeMakeDevs × Switch AI) — Track 02: Best Personal or Creative Workflow**

A one-line story idea dropped into a team chat becomes a production-ready
horror short — with a human approving every step that matters.

## The workflow

**DARKLINE THRESHOLD** publishes a 60-second AI horror short every day.
Coming up with each day's short used to be a solo scramble. Now it is a
team workflow that runs inside **Switch**, in the team's Mattermost
workspace:

1. **Seed.** A person posts a one-line premise in the room:
   *"a lift that stops on a floor that does not exist. 60 seconds, diabolical tone."*
2. **Draft.** The **Darkline Producer** agent (an OpenCode agent connected
   through Switch) replies with a full draft: a title, a ~1,000-character
   narration script written for a deep male voice, a thumbnail brief
   (≤ 4 words), and three visual beats.
3. **Human gate 1 — approval.** Nothing proceeds until a person approves
   the draft or requests edits. The agent revises and re-asks.
4. **Production checklist.** On approval the agent locks the script and
   returns the exact checklist the channel's pipeline runs: 6 × 10s
   vertical clips from the beats, Kokoro VOICE_01 narration, bold
   captions with red keyword emphasis, royalty-free SFX, music added
   post-upload from the YouTube Studio Audio Library rotation, and a
   Canva thumbnail built from the brief.
5. **Human gate 2 — "ship it".** Only on the person's confirmation does
   the agent queue the short into the DARKLINE production pipeline and
   summarise what was queued.

Two real runs — one in a Switch room, one in the Mattermost channel —
are transcribed in [`demo/demo-transcripts.md`](demo/demo-transcripts.md).

## Why Switch is central

Remove Switch and this project stops working:

- The agent is a **managed agent**: it is defined in Switch, placed on a
  machine through Switch's agent-management plane, and started, stopped
  and supervised by the **headless Switch agent controller** enrolled
  against this server.
- The conversation happens in **rooms bridged by Switch** into the
  team's Mattermost workspace — the agent joins the channel as a
  first-class member (`@darkline`), is addressed by mention, and its
  session lifecycle ("starting a session", "worked for 27s") is run by
  Switch, not by a bot script.
- The human gates are enforced by the agent's Switch instructions and
  the room workflow, not by a separate app: seed → draft → approval →
  checklist → ship-it is one continuous room conversation.

## Architecture

```
Mattermost 11.9 (team chat)  ──bridge──  switch-core 0.31.0 (rooms, agents, API :8000)
                                                │
                          agent controller (headless, enrolled machine "hatch-vm")
                                                │
                                     OpenCode 1.19 agent host
                                                │
                            model shim (:8399, OpenAI-compatible) ──► OpenRouter free models ($0)
```

- **switch-core** runs self-hosted with PostgreSQL 16, seeded by
  upstream's own `setup.py` (Mattermost team, bridge registration,
  account linking). Feature flags: `agent_management`, `group_chats`,
  `agent_chats`, `follow_the_conversation`, `service_connections`.
- **Agent** — definition in [`agent/agent-definition.json`](agent/agent-definition.json);
  the provider is OpenCode with the config in
  [`agent/opencode.json`](agent/opencode.json).
- **$0 model layer** — OpenCode talks to a tiny local shim
  ([`shim/model_shim.py`](shim/model_shim.py)) that exposes an
  OpenAI-compatible API and forwards to **free-tier OpenRouter models
  only** (discovered live from the catalog at startup; tool-capable
  models only). No paid API key is used anywhere; the credential is
  attached through the platform's sanctioned surrogate-credential
  helper and is never written to disk by this project.
- **Controller** — `switch-agent-controller` (headless) enrolled with a
  one-time enrollment code minted in the Switch management API;
  providers probed on the machine (OpenCode 1.19.5).

## Running it

Standard route (any normal machine): use upstream's standalone
`docker compose` deployment of Switch 0.31.0, enable the
`agent_management` feature flag, install the agent controller from the
`switch-agent-controller-v*` GitHub release, enroll it, create the
agent from `agent/agent-definition.json`, start the shim, and invite
the agent to a room.

This build was produced inside a restricted sandbox where containers
cannot create network interfaces at all (the kernel blocks the netlink
ioctls a container runtime needs — verified with Docker + crun and a
bare `ip link` in a fresh namespace). The stack therefore runs
**host-natively**, the same topology upstream's own local-dev flow uses
for switch-core: PostgreSQL and Mattermost as host processes,
switch-core via `uv run`, `setup.py` run directly. The scripts in
[`stack/`](stack/) are exactly what runs this deployment, including the
host-networking compose override kept for reference. Environment notes
that cost real debugging time — an extra seccomp filter on the systemd
tree blocks the `keyctl` syscall every container init needs, and a
bracketed-IPv6 `NO_PROXY` entry crashes strict URL parsers — are
written up in the scripts' comments.

## Files

- `agent/` — the Switch agent definition and its OpenCode config
- `shim/` — the $0 OpenAI-compatible model shim (stdlib Python)
- `stack/` — the runner scripts for core, setup and the controller
- `tools/` — a registry image puller used to fetch images where the
  Docker daemon's own downloads were blocked by the egress proxy
- `demo/` — the workflow design and the two verified run transcripts

## Honest limits

- Free-tier models vary in speed and availability; the shim fails over
  across the live free roster per request.
- The DARKLINE render pipeline itself (Veo clips, TTS, ffmpeg) runs as
  the channel's separate existing job after "ship it" — this project is
  the creative front-end that feeds it, which is the part that used to
  be the daily bottleneck.

Built solo for the Flip the Switch hackathon, November 2026. MIT licensed.
