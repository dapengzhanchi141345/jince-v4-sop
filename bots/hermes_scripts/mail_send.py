#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""邮件发送器（0 LLM）：用 mail_config.json 的 SMTP 配置发一封邮件。
用法: python mail_send.py --to 收件人 --subject 主题 --body 正文
安全铁律：
  1) 只认 mail_config.json 的 SMTP 配置，没配置/没 enabled 直接拒绝（exit 2）；
  2) 每次发送写 audit.jsonl 留痕（收件人/主题/时间）；
  3) 对外发邮件属审查闸 external_send 类——agent 调用本脚本前必须先过
     E:/AgentCommons/shared/action_review/gate.py check external_send（李彦明确认后才执行）。
"""
import argparse
import json
import os
import smtplib
import sys
import time
from email.mime.text import MIMEText
from email.header import Header
from email.utils import formataddr

HERE = os.path.dirname(os.path.abspath(__file__))
CFG = os.path.join(HERE, "mail_config.json")
AUDIT = os.path.join(HERE, "mail_send_audit.jsonl")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--to", required=True)
    ap.add_argument("--subject", required=True)
    ap.add_argument("--body", required=True)
    args = ap.parse_args()

    try:
        with open(CFG, encoding="utf-8") as f:
            cfg = json.load(f)
    except Exception as e:
        print(f"REJECTED: 邮件配置读不出: {e}")
        sys.exit(2)
    if not (cfg.get("enabled") and cfg.get("smtp_host") and cfg.get("user") and cfg.get("auth_code")):
        print("REJECTED: SMTP 未配置/未启用，需李彦明供邮箱授权码后填 mail_config.json")
        sys.exit(2)

    msg = MIMEText(args.body, "plain", "utf-8")
    msg["From"] = formataddr((str(Header("李彦明", "utf-8")), cfg["user"]))
    msg["To"] = args.to
    msg["Subject"] = Header(args.subject, "utf-8")
    try:
        with smtplib.SMTP_SSL(cfg["smtp_host"], int(cfg.get("smtp_port", 465))) as s:
            s.login(cfg["user"], cfg["auth_code"])
            s.sendmail(cfg["user"], [args.to], msg.as_string())
    except Exception as e:
        print(f"SEND_FAILED: {type(e).__name__}: {str(e)[:120]}")
        sys.exit(1)
    with open(AUDIT, "a", encoding="utf-8") as f:
        f.write(json.dumps({"ts": time.strftime("%Y-%m-%d %H:%M:%S"), "to": args.to,
                            "subject": args.subject[:80], "body_len": len(args.body)},
                           ensure_ascii=False) + "\n")
    print(f"SENT: 已发到 {args.to}（{args.subject[:40]}）")


if __name__ == "__main__":
    main()
