
import json, urllib.request, urllib.error
keys = json.load(open("E:/GoldstrategyEngine/tmp_probe_keys.json", encoding="utf-8"))
for name, k in keys.items():
    req = urllib.request.Request(
        "https://apihub.agnes-ai.com/v1/chat/completions",
        data=json.dumps({"model":"agnes-3.0-flash","messages":[{"role":"user","content":"ping"}],"max_tokens":4}).encode(),
        headers={"Authorization":f"Bearer {k}","Content-Type":"application/json"})
    try:
        r = urllib.request.urlopen(req, timeout=30)
        body = r.read().decode()
        m = json.loads(body).get("choices",[{}])[0].get("message",{}).get("content","")[:20]
        print(f"{name}: OK 200 -> {m!r}")
    except urllib.error.HTTPError as e:
        print(f"{name}: HTTP {e.code} {e.read()[:120]!r}")
    except Exception as e:
        print(f"{name}: ERR {str(e)[:80]}")
