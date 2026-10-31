# Audit log anchoring

Owner: P3. Code: `backend/app/workflow/audit.py` (hash chain), `backend/app/workflow/anchor.py` (anchoring).

## What we claim (exactly)

> The audit log is **tamper-evident against anyone with application credentials**.
> **History older than the last anchor is pinned externally**, so rewriting it is detectable by anyone who holds the anchor.

We do **not** claim:

- that the log cannot be altered (someone with file access can; the point is that it shows),
- anything about events after the last anchor (the window is at most 30 minutes, `HG_ANCHOR_INTERVAL_MIN`),
- that an action was correct, only that the record of it was not changed afterwards,
- that `GET /api/audit/verify` alone defeats an attacker with file access: it checks the chain and the anchors **stored in the same database**. The external copies (git remote, OpenTimestamps proof) are what an attacker cannot also rewrite, so they must be compared when it matters (see "Check it yourself").

## How it works

1. Every audit entry stores `hash = SHA-256(prev_hash || canonical_json(entry))`. Editing or deleting a row breaks the chain from that row on.
2. `POST /api/audit/anchor` (admin) and a background loop every 30 minutes write `data/anchors/anchor-<seq>.json` = `{seq, head_hash, ts}`.
3. `audit.verify()` also checks that every stored anchor's `head_hash` still equals the chain's hash at that `seq`. So a **fully recomputed** chain (every hash rewritten to look consistent) or a **truncated** one fails at the anchored `seq`.
4. With `HG_ANCHOR_NETWORK=1` the anchor file is also stamped with OpenTimestamps and pushed to a public git repo.

The anchor files contain a sequence number, a hash and a timestamp. No personal data.

## Modes

| Mode | Set by | What happens | `status` |
|---|---|---|---|
| Offline (default, demo) | nothing | file written locally, **no network call at all** | `pending` |
| Network | `HG_ANCHOR_NETWORK=1` | `ots stamp` (if installed), then `git add/commit/push` (if `data/anchors` is its own repo) | `anchored` if the OTS stamp or the push worked, else `pending` |

`anchored` with method `file+ots` means the digest was submitted to the OpenTimestamps calendar servers. The Bitcoin attestation appears a few hours later (`ots upgrade`, below). Until then the proof is "pending" on their side.

The network step runs **before** the database write, so a slow `git push` never blocks approvals.

## Setup on Windows

```powershell
# 1. OpenTimestamps client (needs Python 3 and internet)
pip install opentimestamps-client
ots --help                      # check it is on PATH (open a new terminal if not)

# 2. A public repo for the anchors (fictional demo data only; the files hold a hash and a number)
#    Create an EMPTY public repo on GitHub first, then:
cd hireguard\data\anchors
git init
git remote add origin https://github.com/<you>/hireguard-anchors.git
git branch -M main
git commit --allow-empty -m "init"
git push -u origin main         # needs git credentials (e.g. `gh auth login`)

# 3. Run the backend with anchoring on
$env:HG_ANCHOR_NETWORK = "1"
.\run.ps1 -Seed
```

`data/anchors/` must be **its own repository**. If it is not, the code skips git entirely (it would otherwise act on the surrounding HireGuard repo). It is git-ignored in the main repo.

## Demo checklist (audit part)

1. Log in as an HR manager, open the Security Center: `GET /api/audit/verify` returns `{"ok": true, ...}`.
2. As admin: `POST /api/audit/anchor` returns `{"status": "pending"|"anchored", "file": "anchor-....json"}`.
3. `GET /api/audit/verify` again: `last_anchor` now shows that head hash.
4. (Optional live tamper) See `docs/demo_p3.md`, step 4.

## Check it yourself

```powershell
# Is the local chain intact, and does it match the anchors stored in the DB?
curl -b jar http://localhost:8000/api/audit/verify

# Does a local anchor match what was published? Compare with the public repo history:
git -C hireguard\data\anchors log --oneline
# After a few hours, finish the Bitcoin proof, then inspect it:
ots upgrade hireguard\data\anchors\anchor-00000042.json.ots
ots info    hireguard\data\anchors\anchor-00000042.json.ots
```

Full cryptographic verification of an `.ots` proof needs a Bitcoin node, or upload the `.ots` and the anchor file to the verifier on opentimestamps.org.

## Production

SQLite triggers (`audit_log_no_update`, `audit_log_no_delete`) stop the **application**, not someone with the database file. Production runs on Postgres with a role that cannot change history. Exact statements are in `docs/threat_model.md`, section "Audit log integrity".
