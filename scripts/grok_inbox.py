"""Talk to a live Claude Code session from this project.

`listen` registers this Grok session under its display name and accepts
replies. `send` delivers a note to a Claude session by the name it set
with /name. The display name is `generated_title` in this session's
summary.json, and only when `title_is_manual` is true.

Claude checks that the process on the socket is the pid in the session
file, with the same /proc start time, so a recycled pid is refused.
The auth token stays in ~/.claude/sessions and is never printed.
listen removes the socket, the key, and the pid file when it exits.
"""
import argparse
import hashlib
import json
import os
import signal
import socket
import sys
import time
import uuid
from pathlib import Path

REG = Path.home() / ".claude" / "sessions"
SOCK_DIR = Path(os.environ.get("XDG_RUNTIME_DIR", f"/run/user/{os.getuid()}")) / "cc-socks"
LOG = Path(os.environ.get("XDG_RUNTIME_DIR", f"/run/user/{os.getuid()}")) / "grok-inbox.jsonl"


def parse_proc_start(stat: str) -> str:
    # Field 22 of /proc/pid/stat. The comm field is in parentheses and
    # can contain spaces, so count from the last ")".
    end = stat.rfind(")")
    fields = stat[end + 2 :].split() if end >= 0 else []
    if len(fields) < 20:
        raise SystemExit("could not read process start time")
    return fields[19]


def proc_start(pid: int) -> str:
    return parse_proc_start(Path(f"/proc/{pid}/stat").read_text())


def pid_domain() -> str:
    # Same shape Claude writes: linux:<machine-id>:<pid namespace>.
    machine = Path("/etc/machine-id").read_text().strip()
    ns = os.readlink("/proc/self/ns/pid")
    return f"linux:{machine}:{ns}"


def alive(pid) -> bool:
    try:
        os.kill(int(pid), 0)
    except (OSError, TypeError, ValueError):
        return False
    return True


def session_summary():
    sid = os.environ.get("GROK_SESSION_ID")
    root = Path.home() / ".grok" / "sessions"
    if not sid or not root.is_dir():
        return None
    matches = [p for p in root.glob(f"*/{sid}/summary.json") if p.is_file()]
    if len(matches) != 1:
        return None
    return json.loads(matches[0].read_text())


def validate_display_name(name):
    # The registry name and from-name must be the same string. Reject
    # characters that would break the attribute instead of escaping them.
    cleaned = name.strip()
    if not cleaned:
        raise SystemExit("no display name set. Set the session title, or pass --name.")
    if any(c in '"&<>' or ord(c) < 32 for c in cleaned):
        raise SystemExit(
            'display name cannot contain ", &, <, >, or control characters'
        )
    return cleaned


def name_from_summary(summary, explicit):
    if explicit:
        return validate_display_name(explicit)
    title = (summary or {}).get("generated_title")
    if (summary or {}).get("title_is_manual") and isinstance(title, str) and title.strip():
        return validate_display_name(title)
    return None


def session_name(explicit):
    if explicit:
        return name_from_summary(None, explicit)
    return name_from_summary(session_summary(), None)


def claude_metas():
    if not REG.is_dir():
        return []
    found = []
    for path in REG.glob("*.json"):
        stem = path.name[:-5]
        if not stem.isdigit():
            continue
        try:
            meta = json.loads(path.read_text())
        except (OSError, json.JSONDecodeError):
            continue
        if isinstance(meta, dict):
            found.append(meta)
    return found


def live_named(name):
    return [m for m in claude_metas() if m.get("name") == name and alive(m.get("pid"))]


def require_one(name, hits, what, missing=None):
    if not hits:
        raise SystemExit(missing or f"no live {what} named {name}")
    if len(hits) > 1:
        listed = ", ".join(f"{m.get('pid')} ({m.get('version')})" for m in hits)
        raise SystemExit(f"more than one live {what} named {name}: {listed}")
    return hits[0]


def require_grok_inbox(meta, name):
    if meta.get("version") == "grok":
        return meta
    raise SystemExit(
        f"{name} is pid {meta.get('pid')} version {meta.get('version')}, "
        "not a grok inbox. That title is already a live session. "
        "Set a different session title and run listen under that name."
    )


def write_private(path, text):
    data = text.encode()
    fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
    try:
        while data:
            wrote = os.write(fd, data)
            if wrote <= 0:
                raise SystemExit(f"could not write {path}")
            data = data[wrote:]
    finally:
        os.close(fd)


def load_key(meta):
    pid = meta["pid"]
    for path in REG.glob(f"{pid}.*.key"):
        try:
            key = json.loads(path.read_text())
        except (OSError, json.JSONDecodeError):
            continue
        if key.get("procStart") == meta.get("procStart"):
            return key
    raise SystemExit(f"no auth key for pid {pid} with this process start time")


def note(name, text, sock):
    body = text.strip("\n")
    first = f"{name} here."
    if not body.startswith(first):
        body = f"{first}\n\n{body}" if body else first
    return (
        f'<cross-session-message from="uds:{sock}" from-name="{name}" '
        f'from-mode="prompting">\n{body}\n</cross-session-message>\n'
    )


def deliver(meta, content):
    key = load_key(meta)
    frames = [
        {"type": "auth", "token": key["peerToken"]},
        {"type": "user", "message": {"role": "user", "content": content}},
    ]
    payload = "".join(json.dumps(f, separators=(",", ":")) + "\n" for f in frames).encode()
    conn = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
    conn.settimeout(5)
    try:
        conn.connect(meta["messagingSocketPath"])
        conn.sendall(payload)
        conn.shutdown(socket.SHUT_WR)
        try:
            conn.recv(4096)
        except socket.timeout:
            pass
    finally:
        conn.close()


def cmd_name(args):
    name = session_name(args.name)
    if not name:
        raise SystemExit("no display name set. Set the session title, or pass --name.")
    print(name)


def cmd_send(args):
    name = session_name(args.name)
    if not name:
        raise SystemExit("no display name set. Set the session title, or pass --name.")
    mine = require_grok_inbox(
        require_one(
            name,
            live_named(name),
            "inbox",
            missing=f"no live inbox named {name}. Run listen first.",
        ),
        name,
    )
    text = Path(args.file).read_text() if args.file else args.text
    if not text or not text.strip():
        raise SystemExit("the note is empty")
    target = require_one(args.to, live_named(args.to), "Claude session")
    deliver(target, note(name, text, mine["messagingSocketPath"]))
    print(f"sent to {args.to} as {name}")


def cmd_listen(args):
    name = session_name(args.name)
    if not name:
        raise SystemExit("no display name set. Set the session title, or pass --name.")
    others = live_named(name)
    if len(others) == 1:
        other = others[0]
        raise SystemExit(
            f"{name} is already listening as pid {other.get('pid')} "
            f"version {other.get('version')}"
        )
    if others:
        listed = ", ".join(f"{m.get('pid')} ({m.get('version')})" for m in others)
        raise SystemExit(f"more than one live inbox is named {name}: {listed}")

    pid = os.getpid()
    SOCK_DIR.mkdir(mode=0o700, exist_ok=True)
    sock_path = SOCK_DIR / f"{pid}.sock"
    digest = hashlib.sha256(str(sock_path).encode()).hexdigest()
    key_path = REG / f"{pid}.{digest}.key"
    meta_path = REG / f"{pid}.json"
    created = []

    def remove_created():
        for path in created:
            try:
                path.unlink()
            except FileNotFoundError:
                pass

    def stop(*_args):
        raise SystemExit(0)

    signal.signal(signal.SIGTERM, stop)
    signal.signal(signal.SIGINT, stop)

    server = None
    try:
        if sock_path.exists():
            sock_path.unlink()
        created.append(sock_path)
        server = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        server.bind(str(sock_path))
        os.chmod(sock_path, 0o600)
        server.listen(8)

        token = os.urandom(16).hex()
        start = proc_start(pid)
        now = int(time.time() * 1000)
        # peerFeatures is omitted on purpose. This listener does not
        # implement notify_idle or artifact_yield.
        meta = {
            "pid": pid,
            "sessionId": str(uuid.uuid4()),
            "cwd": str(Path.cwd()),
            "startedAt": now,
            "procStart": start,
            "version": "grok",
            "peerProtocol": 1,
            "kind": "interactive",
            "entrypoint": "cli",
            "pidDomain": pid_domain(),
            "messagingSocketPath": str(sock_path),
            "name": name,
            "nameSource": "user",
            "nameSince": now,
            "updatedAt": now,
            "status": "idle",
            "statusUpdatedAt": now,
        }
        key = {"peerToken": token, "procStart": start, "pidDomain": meta["pidDomain"]}
        REG.mkdir(mode=0o700, exist_ok=True)
        created.append(key_path)
        write_private(key_path, json.dumps(key))
        created.append(meta_path)
        meta_path.write_text(json.dumps(meta))
        print(f"listening name={name} pid={pid}", flush=True)

        while True:
            conn, _ = server.accept()
            conn.settimeout(8)
            buf = b""
            authed = False
            try:
                while True:
                    try:
                        chunk = conn.recv(65536)
                    except socket.timeout:
                        break
                    if not chunk:
                        break
                    buf += chunk
                    while b"\n" in buf:
                        line, buf = buf.split(b"\n", 1)
                        if not line.strip():
                            continue
                        try:
                            obj = json.loads(line)
                        except json.JSONDecodeError:
                            continue
                        if not authed:
                            authed = obj.get("type") == "auth" and obj.get("token") == token
                            continue
                        redacted = {k: v for k, v in obj.items() if "token" not in k.lower()}
                        record = json.dumps({"at": time.time(), "message": redacted})
                        print(record, flush=True)
                        with LOG.open("a") as fh:
                            fh.write(record + "\n")
            finally:
                conn.close()
    finally:
        if server is not None:
            server.close()
        remove_created()


def main():
    parser = argparse.ArgumentParser(description="Talk to a live Claude Code session.")
    sub = parser.add_subparsers(dest="cmd", required=True)

    def add_name(cmd):
        cmd.add_argument("--name", help="display name. Default: this session's title, if you set one.")

    show = sub.add_parser("name", help="print the display name this session would use")
    add_name(show)
    show.set_defaults(func=cmd_name)

    listen = sub.add_parser("listen", help="register the inbox and accept replies")
    add_name(listen)
    listen.set_defaults(func=cmd_listen)

    send = sub.add_parser("send", help="send a note to a Claude session by its /name")
    add_name(send)
    send.add_argument("--to", required=True, help="Claude session name")
    group = send.add_mutually_exclusive_group(required=True)
    group.add_argument("--text")
    group.add_argument("--file")
    send.set_defaults(func=cmd_send)

    args = parser.parse_args()
    args.func(args)


if __name__ == "__main__":
    try:
        main()
    except BrokenPipeError:
        sys.exit(0)
