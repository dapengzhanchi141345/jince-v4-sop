
import json, time, os, hashlib
base = r"E:\GoldstrategyEngine\data"
batch = {
  "id": "rd_verify_batch_exness_study_20261005",
  "ts": int(time.time()),
  "source": "https://my.exndomain.com/pa/analytics/analystViews (Exness analyst views, public views only)",
  "pipeline": "social funnel: view -> testable hypothesis -> same-denom A/B -> five-test -> footnote-only unless 5/5",
  "items": [
    {
      "id": "V18",
      "status": "BLOCKED",
      "hypothesis": "Exness analyst views directional calls have positive expectancy after 0.25R slippage on T1 universe, same-denom vs current regime routing baseline (V15 B-arm, 37 events PF 0.33)",
      "unlock_order": [
        "extnet up (curl api.ipify returns IP) OR user saves page content to E:/workbuddy/内容中心/收件箱/exness_analyst_views/",
        "extract testable directional calls from content (account-side data REJECTED, public views only)",
        "same-denom A/B vs V15 baseline T1-16; z-test only after R backfill (gate 2); wf3 same-sign",
        "polish.json -> five-test + risk-officer a/b/c recheck (full-event-set recompute, 0.25R slippage, footnote-only)",
        "default: dashboard footnote only; live requires 5/5 + risk-officer dual-gate"
      ],
      "account_data_rule": "zero account-side data (positions/equity/deals of that account) - reject door V19",
      "exp_R_note": "R-based z-test pending R backfill (gate 2); until then report amount-PF only, no significance wording"
    },
    {
      "id": "V19",
      "status": "REJECT",
      "hypothesis": "account-side data ingestion gate - negative iron rule: any hold/account data from the Exness personal account is REJECTED from learning pipeline, audit-only",
      "reason": "L4 boundary per risk-officer: account data never enters gates; mirrors social_inbox dead-end isolation"
    }
  ],
  "caveats": [
    "extnet down as of 10-05 (DoH sidecar only unblocks github.com); V18 BLOCKED until extnet up OR inbox content lands",
    "sample base reuses V15 B-arm (37 events, PF 0.33, includes old teaching batch - control denominator, not live edge)"
  ]
}
out = os.path.join(base, "rd_verify_batch_exness_study_20261005.json")
json.dump(batch, open(out, "w", encoding="utf-8"), ensure_ascii=False, indent=1)
md5 = hashlib.md5(open(out, "rb").read()).hexdigest()[:8]
sz = os.path.getsize(out)
# verify back
b2 = json.load(open(out, encoding="utf-8"))
print("WROTE", out, sz, "bytes, md5", md5)
print("items:", [(i["id"], i["status"]) for i in b2["items"]])
