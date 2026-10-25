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

## Checking that a note arrived

`send` reporting `sent to <claude-name> as <name>` only means the socket accepted the note, and an empty reply on the socket is normal; a bad token looks the same. The proof is on Claude's side, in two places.

**The session registry.** `~/.claude/sessions/<pid>.json` (the same file `claude agents --json` reads) moves `status` to `busy` and bumps `updatedAt` when the note is taken.

**The transcript.** It is

```text
~/.claude/projects/<cwd, slashes turned into dashes>/<sessionId>.jsonl
```

so a session started in `/data/python/SDR` writes to the directory `-data-python-SDR`. A delivery appends a `queue-operation` record of `enqueue`, then a `user` record with `origin.kind` `peer`, `turnOrigin` `peer` and `promptSource` `system`. The text of the second one starts `Another Claude session sent a message:`. If the status moved but those two records are missing, the note did not arrive as a peer message.

Both were checked on 2026-10-04 against an idle session, which took the note at once.

## Not tried

**A note to a session that is in the middle of a turn.** The `enqueue` record suggests it is held and taken at the session's next tool round, but this program has not been run against a busy session to see. Notes between Claude sessions over the same socket did reach a busy session that way on 2026-10-04, at its next tool round; that shows the receiving side queues, and is not a test of `send`.

## Requirements

- Linux, same user for Grok and Claude Code
- Claude Code with its session socket under `$XDG_RUNTIME_DIR/cc-socks/`
- Python 3
