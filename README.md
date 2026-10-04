# talk-to-claude

A Grok skill that sends a note to a live [Claude Code](https://code.claude.com) session and takes the reply on an inbox registered under this Grok session's display name.

Claude does not load this skill. It answers with its own `SendMessage`, to the display name, while `listen` is running.

Checked on 2026-10-04 against Claude Code 2.1.289 on Linux. The session that first received a note reported 2.1.287.

## Install

Grok loads user skills from `~/.grok/skills/<name>/`. Point that name at this repo:

```sh
mkdir -p ~/.grok/skills
ln -s "$(pwd)" ~/.grok/skills/talk-to-claude
```

The slash command is `/talk-to-claude`. Grok also invokes the skill when you ask it to message a Claude session.

## Use

Set the Grok session title first. That title is the name Claude will answer. The program reads `generated_title` from the session summary and uses it only when `title_is_manual` is true. It will not invent a name. The display name cannot contain `"`, `&`, `<`, `>`, or control characters. `listen` removes its socket, key, and pid file when it exits.

```sh
python ~/.grok/skills/talk-to-claude/scripts/grok_inbox.py name
python ~/.grok/skills/talk-to-claude/scripts/grok_inbox.py listen
python ~/.grok/skills/talk-to-claude/scripts/grok_inbox.py send --to <claude-name> --text "The note."
```

`<claude-name>` is the name set with `/name` inside the Claude session. `listen` has to be running before `send`. One `listen` per name. Replies are JSON lines on the listener's stdout and in `$XDG_RUNTIME_DIR/grok-inbox.jsonl`.

`claude agents --json` lists the inbox under the display name while `listen` is running.

## What it sends

Two JSON lines on the Claude session's Unix socket, then a half-close:

```text
{"type":"auth","token":"<peerToken>"}
{"type":"user","message":{"role":"user","content":"<cross-session-message ...>..."}}
```

The note Claude sees starts with `<display-name> here.` and carries `from-name` set to that same name. Claude replies by sending to the name, or by copying the `from` address into `SendMessage`.

The auth key is `~/.claude/sessions/<pid>.<sha256 of the socket path>.key`, mode `600`. The token is 32 hex characters. It is never printed. The registry version is `grok`. Claude also checks that the process on the socket is that pid, with the same `/proc` start time.

## Requirements

- Linux, same user for Grok and Claude Code
- Claude Code with its session socket under `$XDG_RUNTIME_DIR/cc-socks/`
- Python 3
