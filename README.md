# HireGuard: a secure AI HR platform

SUP'COM "Secure AI HR System" hackathon · team Diga Diga · all data is fictional.

> **The AI reads, code decides, humans approve.**
> Whatever reads stranger text (CVs, emails, questions) cannot act; whatever can act never reads stranger text.

HireGuard does an HR team's daily paperwork with two modules on one trust core:

- **Recruit (HireGuard):** CV screening with evidence for every point, inbox triage and template replies,
  interview slots, follow-ups, and a fast-track to the offer (offer-fit check, talent pool, offer letters).
- **Team (HR Nexus):** the employee Answer Desk, self-service documents, a team skills map, HR process metrics
  and a handbook knowledge-gap radar. Aggregates only, never individual scores.

Nothing is sent, booked, released or committed without a human approval; the executor refuses anything else (403).

```mermaid
flowchart TB
  subgraph IN["Untrusted input"]
    direction LR
    CV["CV PDFs"]
    MAIL["Candidate emails"]
    Q["Employee questions"]
  end

  subgraph READ["AI reads, cannot act"]
    direction LR
    SAN["Sanitizer<br/>hidden text removed and reported"]
    DET["Detector<br/>injection flags, signal only"]
    GATE["Email gate<br/>SPF, DKIM, DMARC"]
    LLM["Local LLM, Qwen3-8B<br/>typed JSON, no tools"]
    VAL["Validator<br/>claims need visible evidence"]
  end

  subgraph REC["Recruit module · HireGuard"]
    direction LR
    SCO["Rubric scorer<br/>proposed scores + evidence"]
    TRU["Stability badge<br/>fairness audit"]
    FAST["Fast-track<br/>offer fit, follow-ups,<br/>talent pool, offer letters"]
    INB["Inbox digest<br/>template replies"]
  end

  subgraph TEAM["Team module · HR Nexus"]
    direction LR
    SK["Skills map<br/>holder counts only"]
    PM["HR process metrics<br/>per stage, no people"]
    KG["Knowledge-gap radar<br/>cells under 5 hidden"]
    AD["Answer Desk<br/>documents"]
  end

  subgraph ACT["Humans approve, code acts"]
    direction LR
    APR["Approval queue<br/>risk, canaries, attention guard,<br/>2nd approver for offers"]
    EXE["Executor<br/>403 unless approved"]
    AUD[("Audit log<br/>hash-chained, anchored")]
  end

  HR(["Recruiter · HR manager"])
  EMP(["Employee"])
  OUT["Sent emails, bookings,<br/>released documents"]

  CV --> SAN --> LLM
  SAN --> DET
  MAIL --> GATE -->|"language, intent,<br/>urgency only"| LLM
  LLM --> VAL --> SCO
  SCO --> TRU
  SCO --> FAST
  GATE --> INB
  Q --> AD
  EMP --> AD

  SK -.->|"proposed rubric<br/>counts only"| SCO
  AD -.->|"section + week only"| KG

  FAST --> APR
  INB --> APR
  AD --> APR
  HR -->|"approve or reject"| APR
  APR --> EXE --> OUT
  APR --> AUD
  EXE --> AUD
  AUD -.->|"stage timestamps"| PM

  classDef ai fill:#fde68a,stroke:#b45309,color:#1f2937
  classDef code fill:#dbeafe,stroke:#1d4ed8,color:#1f2937
  classDef human fill:#dcfce7,stroke:#15803d,color:#1f2937
  classDef risky fill:#fee2e2,stroke:#b91c1c,color:#1f2937
  class LLM ai
  class SAN,DET,GATE,VAL,SCO,TRU,FAST,INB,SK,PM,KG,AD,EXE,AUD,OUT code
  class APR,HR,EMP human
  class CV,MAIL,Q risky
```

## Results (fictional CVs and emails, 95% Clopper-Pearson intervals)

| What | HireGuard | Standard AI screener, same model |
|---|---|---|
| 40 hidden-text attacks that moved the output (Qwen3-8B) | **3/40** (7.5%); 1 helped the attacker, by 1.4 points | **13/40** (32.5%) |
| Same 40 attacks, paired | 11 moved only the standard screener, 1 only HireGuard: exact McNemar **p = 0.006** | |
| Email routing (100 emails, 15 spoofed) | right lane 100/100, spoofed emails given no candidate data 15/15 | |
| Code path only (no model): attacks / twin CVs | 0/40 / 0/89 | |
| Skill extraction (200 CVs, Qwen3-8B) | F1 **0.944** (precision 0.999, recall 0.894); Arabic 0.80 | |
| **Known limit:** twin CVs whose score changed through the model | **17/89** with identity masking (26/90 before): town, school, gender 0; CV language 13/20, gap 4/9 | |

Details, every run and its mode: [hireguard/docs/evaluation.md](hireguard/docs/evaluation.md) and Security Center → Evaluation.

## Run it (Windows)

```powershell
cd hireguard
copy .env.example .env
.\run.ps1 -Setup -Seed     # first time: venv, npm install, fictional demo data (passwords printed once)
.\run.ps1                  # API on :8000 (docs at /api/docs), UI on http://localhost:5173
ollama pull qwen3:8b       # the local model; without it the demo runs on labelled fixtures and says so
```

## What is where

| Path | Contents |
|---|---|
| [`hireguard/`](hireguard/README.md) | The product: FastAPI backend, React frontend, evaluation harness, fictional data, Odoo connector, Modal deployment |
| [`research/`](research/README.md) | HR Nexus feasibility research: the experiments that decided what the Team module does, and what we refuse to build |
| [`persons/`](persons/README.md) | Who owns what, and what is left to do |

Key documents: [architecture, data boundaries and risk register](hireguard/docs/architecture.md) ·
[pitch](hireguard/docs/pitch.md) · [demo script](hireguard/docs/demo_script.md) ·
[threat model](hireguard/docs/threat_model.md) · [pipeline](hireguard/docs/pipeline.md) ·
[API contract](hireguard/contracts/API.md) · [authentication](hireguard/docs/security_auth.md) ·
[pentest report](hireguard/docs/pentest_report.md).

## Team

| Person | Role |
|---|---|
| Ahmed | System design, architecture, integration and release gates |
| Hedhili | AI model setup, evaluation and adversarial testing |
| Rayen | Backend APIs, data contracts, authorization, Odoo connector |
| Yasmina | Frontend, user workflows, browser security, demo |
