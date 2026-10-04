---
name: talk-to-claude
description: >
  Send a note to a live Claude Code session and take its reply on an inbox
  registered under this Grok session's display name. Introduce yourself as
  that name when the user has set one. Use when the user says talk to Claude,
  message a Claude agent, send a note to a named Claude session, or runs
  /talk-to-claude.
---

# Talk to Claude

This skill is for Grok only. Claude does not load it. Claude answers with its own `SendMessage` while the inbox below is running.

The program is `scripts/grok_inbox.py` next to this file. Installed, that path is `~/.grok/skills/talk-to-claude/scripts/grok_inbox.py`.

## Name

Run `name` before `listen` or `send`.

```sh
python ~/.grok/skills/talk-to-claude/scripts/grok_inbox.py name
```

The name is this session's `generated_title` when `title_is_manual` is true. If the command exits without a name, stop and ask the user to set the session title. Do not invent one, and do not pass `--name` unless the user just gave you that exact title.

Every note starts with `<name> here.` The program adds that line. The inbox is registered under that same name, which is the address Claude uses.

## Send

1. If `listen` is not already running for that name, start it in the background and wait until stdout shows `listening name=<name>`.
2. Send only after the user has named the Claude session (the name that session set with `/name`).

```sh
python ~/.grok/skills/talk-to-claude/scripts/grok_inbox.py listen
python ~/.grok/skills/talk-to-claude/scripts/grok_inbox.py send --to <claude-name> --text "The note."
```

`sent to <claude-name> as <name>` means the socket accepted the note. An empty reply on the socket is normal. Claude has the note when that session's status in `claude agents --json` moves to `busy`.

A message starts that Claude session working. Say what to check. Do not ask it to change its permission mode, `CLAUDE.md`, or its settings.

If `send` or `listen` reports that the display name belongs to another live session, stop and ask the user to change the Grok session title. Do not pass `--name` to route around it.

## Replies

Claude sends back to the display name. Those notes are JSON lines on the `listen` process stdout and in `$XDG_RUNTIME_DIR/grok-inbox.jsonl`. Read that log for a reply. Do not claim Claude answered until a line is there.

The auth token stays in `~/.claude/sessions`. Never print it, and never write it into a repo.
