#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""邮件采集器（0 LLM，确定性）：读 mail_config.json，IMAP 拉最近邮件出摘要。
未配置/连接失败 → 一行说明不崩。供晨报哨兵调用，也可单独跑。"""
import email as em
import imaplib
import json
import os
import socket
import time

HERE = os.path.dirname(os.path.abspath(__file__))
CFG = os.path.join(HERE, "mail_config.json")


def _decode(v):
    if not v:
        return ""
    if isinstance(v, str):
        return v
    try:
        return str(v)
    except Exception:
        return ""


def main():
    try:
        with open(CFG, encoding="utf-8") as f:
            cfg = json.load(f)
    except Exception as e:
        print(f"- 邮件连接器：配置文件读不出（{e}）")
        return
    if not (cfg.get("enabled") and cfg.get("imap_host") and cfg.get("user") and cfg.get("auth_code")):
        print("- 邮件连接器：未接入（待李彦明供邮箱地址+IMAP授权码，模板在 scripts/mail_config.json）")
        return
    limit = int(cfg.get("recent_limit", 5))
    try:
        socket.setdefaulttimeout(20)
        conn = imaplib.IMAP4_SSL(cfg.get("imap_host"), int(cfg.get("imap_port", 993)))
        conn.login(cfg["user"], cfg["auth_code"])
        conn.select(cfg.get("folder", "INBOX"), readonly=True)
        _, data = conn.search(None, "ALL")
        ids = (data[0].split() if data and data[0] else [])
        total = len(ids)
        unread = 0
        try:
            _, ud = conn.search(None, "UNSEEN")
            unread = len((ud[0].split() if ud and ud[0] else []))
        except Exception:
            pass
        lines = [f"- 邮件连接器：{cfg['user']} 未读 {unread} / 总 {total}"]
        for mid in ids[-limit:][::-1]:
            try:
                _, msgd = conn.fetch(mid, "(BODY.PEEK[HEADER.FIELDS (FROM SUBJECT DATE)])")
                raw = b"\r\n".join(x[1] for x in msgd if x and x[1])
                msg = em.message_from_bytes(raw)
                frm = _decode(msg.get("From"))[:40]
                subj = _decode(msg.get("Subject"))[:60]
                dt = _decode(msg.get("Date"))[:22]
                lines.append(f"  · [{dt}] {frm} | {subj}")
            except Exception:
                continue
        conn.logout()
        print("\n".join(lines))
    except Exception as e:
        print(f"- 邮件连接器：拉取失败（{type(e).__name__}: {str(e)[:80]}），下拍再试")


if __name__ == "__main__":
    main()
