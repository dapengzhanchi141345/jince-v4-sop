
import json, urllib.request, urllib.error
keys = json.load(open("E:/GoldstrategyEngine/tmp_probe_keys.json", encoding="utf-8"))
for base in ("https://api.agnes-ai.cn/v1","https://apihub.agnes-ai.com/v1"):
    print(f"=== {base} ===")
    for name, k in keys.items():
        req = urllib.request.Request(
            base+"/chat/completions",
            data=json.dumps({"model":"agnes-3.0-flash","messages":[{"role":"user","content":"ping"}],"max_tokens":4}).encode(),
            headers={"Authorization":f"Bearer {k}","Content-Type":"application/json"})
        try:
            r = urllib.request.urlopen(req, timeout=25)
            print(f"  {name}: OK 200")
        except urllib.error.HTTPError as e:
            print(f"  {name}: HTTP {e.code} {e.read()[:80]!r}")
        except Exception as e:
            print(f"  {name}: ERR {str(e)[:60]}")
