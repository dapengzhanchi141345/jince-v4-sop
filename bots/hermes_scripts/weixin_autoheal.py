# -*- coding: utf-8 -*-
"""weixin session auto-heal: acknowledge any 'unknown' (crash-lost) admissions on the
weixin session so its FIFO cannot stay paused forever after a gateway restart.
No-op when nothing is unknown. Run by cron every 15 min."""
import glob, json, os, re, sqlite3, subprocess, time

HERMES = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DB = os.path.join(HERMES, "state.db")
CLI = os.path.join(HERMES, "bin", "hermes.exe")
LOG = os.path.join(HERMES, "logs", "weixin_autoheal.log")

def main():
    sessions = set()
    # 1) lease rows marked platform=weixin
    try:
        db = sqlite3.connect(f"file:{DB}?mode=ro", uri=True, timeout=5)
        rows = db.execute("SELECT DISTINCT conversation_id FROM session_turn_leases WHERE holder LIKE '%platform=weixin%'").fetchall()
        db.close()
        sessions.update(r[0] for r in rows)
    except Exception as e:
        print(f"lease read failed: {e}")
    # 2) fallback: recent agent.log 'paused: unknown_execution' session ids
    for logf in glob.glob(os.path.join(HERMES, "logs", "agent.log*")):
        try:
            with open(logf, "r", encoding="utf-8", errors="replace") as f:
                tail = f.readlines()[-400:]
        except Exception:
            continue
        for line in tail:
            m = re.search(r"Session (\d{8}_\d{6}_[0-9a-f]+) paused: unknown_execution", line)
            if m:
                sessions.add(m.group(1))
    acted = []
    for sid in sorted(sessions):
        try:
            r = subprocess.run([CLI, "sessions", "discard", sid, "--yes"],
                               capture_output=True, text=True, timeout=90)
            out = (r.stdout or "").strip().splitlines()
            acted.append(f"{sid} -> {out[0] if out else f'exit={r.returncode}'}")
        except Exception as e:
            acted.append(f"{sid} -> error {e}")
    stamp = time.strftime("%Y-%m-%d %H:%M:%S")
    with open(LOG, "a", encoding="utf-8") as f:
        for a in acted:
            f.write(f"[{stamp}] {a}\n")
        if not acted:
            f.write(f"[{stamp}] no weixin session candidates; nothing to do\n")
    print("\n".join(acted) or "nothing to do")

if __name__ == "__main__":
    main()
