# Bot Mode group chats (hosted rooms)

Group chats on the bot interface (desktop / Bot Chat UI) are rows in the profile's `state.db` `hosted_rooms` table — they are NOT WeChat/Telegram platform groups. On hosts where WeChat runs through iLink private chat only, "pull the bot into the WeChat group" is a misconception; never instruct the user to invite the bot into a WeChat group — the group is a local Hermes entity and lives entirely in config/DB layer.

## Diagnosing "there are two groups" / duplicate names
1. Query rooms: sqlite3 on the profile's `state.db` → `hosted_rooms` (room_id, name, members_json, revision, updated_at).
2. One row in DB but two names in the UI = ONE room with two faces: the DB `name` and a stale gateway/UI cache (e.g. after a rename, old and new names sit side-by-side until the gateway restarts). It is not two groups and there is no ghost entry to clean up.
3. Before telling the user "bots need to be pulled into the group", read `members_json` — bot profiles are usually already members; the group and its members exist, only the display name is out of sync.
4. Cron delivery with `deliver: "bot-chat"` maps to the room by room_id, so renaming `name` does not break delivery; only the display name changes.

## Renaming a room (config-layer, zero user action besides a gateway restart)
1. `UPDATE hosted_rooms SET name='<new>', revision=revision+1, updated_at=<epoch float> WHERE room_id='<id>';` — before writing, read the existing row and match the `updated_at` column's format: on this host it is an **epoch float** (e.g. `1794480081.04`). Writing an ISO-8601 string corrupts gateway timestamp parsing — fix it back to epoch in the same session if caught.
2. Bumping `revision` marks the row as externally changed (observed pattern on this host); a running gateway keeps in-memory room state, so the new name only lands after a gateway restart, which also clears the UI's stale name cache. The user's restart path on this host: double-click `E:\workbuddy\国外模型\hermes\一键重启网关.bat` (or `hermes gateway restart` from an idle session; a live desktop session may refuse in-place restart).
3. This is a direct `state.db` write, not `config.yaml` — the "never hand-edit config.yaml" invariant does not apply, but back up the row's values before updating and verify with a re-read after commit.
