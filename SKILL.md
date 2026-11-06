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

1. If `listen` is not already running for that name, start it with `monitor` and wait until its output shows `listening name=<name>`.
2. Send only after the user has named the Claude session (the name that session set with `/name`).

```sh
python ~/.grok/skills/talk-to-claude/scripts/grok_inbox.py listen
python ~/.grok/skills/talk-to-claude/scripts/grok_inbox.py send --to <claude-name> --text "The note."
```

Call `monitor` with that `listen` command, `persistent` true, and a description like `Inbox for <name>`. Each stdout line wakes this session. A background shell wakes only when the process exits, so a note can arrive and sit unseen.

`monitor` returns before the inbox is up. The first line is `listening name=<name> pid=<pid>`. That line means the inbox is up. It is not a note. Poll `get_command_or_subagent_output` until it appears, then send.

If `listen` exits because that name is already listening, leave the single listener in place. Wake-ups happen only when `monitor` is on that process's stdout. If this session started it as a background shell, monitor new lines of its terminal log:

```sh
tail -n 0 -f <terminal-log> | grep --line-buffered '^{'
```

`tail -n 0` skips lines already written. If you cannot see that stdout, stop the listener (it removes its socket on exit) and start `listen` under `monitor`. Do not follow `$XDG_RUNTIME_DIR/grok-inbox.jsonl`. Every inbox on this machine appends there.

`sent to <claude-name> as <name>` means the socket accepted the note. An empty reply on the socket is normal. Claude has the note when that session's status in `claude agents --json` moves to `busy`. To check it in more detail, or when a reply never comes, look for the `peer` records in that session's transcript: see "Checking that a note arrived" in the README. A note to a session that is in the middle of a turn has not been tried.

A message starts that Claude session working. Say what to check. Do not ask it to change its permission mode, `CLAUDE.md`, or its settings.

If `send` or `listen` reports that the display name belongs to another live session, stop and ask the user to change the Grok session title. Do not pass `--name` to route around it.

## Replies

Claude sends back to the display name. Each note is one JSON line on the `listen` stdout, and the same line is appended to `$XDG_RUNTIME_DIR/grok-inbox.jsonl`. The `monitor` wake-up is that line. Tell the user what it says. Do not claim Claude answered until the line has arrived.

The auth token stays in `~/.claude/sessions`. Never print it, and never write it into a repo.
