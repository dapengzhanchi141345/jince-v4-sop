#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""gen_ca.py -- generate a self-signed CA and per-host forged leaf certs.

Stdlib + openssl only (no paid libs). This makes the CA; the MITM / 443
servers sign leaf certs on the fly against it. Usage:

    python gen_ca.py [CA_CRT] [CA_KEY] [DAYS]

Defaults: ca.crt / ca.key in the CWD, 3650 days.

NOTE: only import this CA into the target machine's trust store to test your
own EA. Importing a CA into the SYSTEM root store is a trust escalation --
only do it on a machine you own/control and revert when done.
"""
import os
import subprocess
import sys


def run(cmd, **kw):
    r = subprocess.run(cmd, capture_output=True, **kw)
    if r.returncode != 0:
        sys.stderr.write("openssl failed: %s\n" % r.stderr.decode())
        sys.exit(1)


def main():
    ca_crt = sys.argv[1] if len(sys.argv) > 1 else "ca.crt"
    ca_key = sys.argv[2] if len(sys.argv) > 2 else "ca.key"
    days = sys.argv[3] if len(sys.argv) > 3 else "3650"
    if os.path.exists(ca_crt) and os.path.exists(ca_key):
        print("CA already exists: %s / %s (reusing)" % (ca_crt, ca_key))
        return
    # self-signed CA, 10-year lifetime
    run(["openssl", "req", "-x509", "-newkey", "rsa:2048", "-nodes",
         "-keyout", ca_key, "-out", ca_crt, "-days", days,
         "-subj", "/O=LocalMITM/CN=Local MITM Root CA"])
    print("CA generated: %s (key: %s)" % (ca_crt, ca_key))


if __name__ == "__main__":
    main()
