
# PRD: **SentinelOps** — Confidence-Driven Autonomous SRE Remediation Agent

**Version:** 1.0 · **Owner:** [You] · **Handoff target:** Claude Code (build end-to-end)
**Track:** Qwen Hackathon — Track 4 (Autopilot Agent)
**One-line:** A multi-cloud, memory-augmented SRE agent that autonomously triages and remediates Kubernetes incidents, where every action carries a Bayesian confidence score that **provably improves over time** — auto-executing only when earned, escalating to a human otherwise.

---

## 0. How to read this document (instructions for Claude Code)

This PRD is **self-contained**. You do not need any prior conversation context. Build in the phases in §12 (Build Roadmap). Everything the reasoning agents do goes through **Qwen via Alibaba Cloud Model Studio's OpenAI-compatible endpoint** (§7). All destructive actions go through a **parameterized playbook registry** (§6) — the LLM never emits raw shell/kubectl. Confidence math is fully specified in §5 with verified numbers. Multi-cloud connectors are in §8 with verified auth recipes per provider.

---

## 1. Problem statement & wedge

SRE/DevOps teams drown in repetitive, well-understood incidents (CrashLoopBackOff, stuck rollouts, latency spikes). Existing tools (K8sGPT, HolmesGPT) **diagnose** but stay read-only. Commercial agentic pipelines (e.g., Komodor Klaudia) exist but are **locked SaaS** and keep a hard human gate on every fix.

**The gap nobody ships:** a system where the **confidence score itself is the visible, memory-driven center** — a number earned per fix-pattern from real outcomes, **open and local**, that a judge can watch *climb during a live demo* until the agent stops asking permission. That is the differentiator.

---

## 2. Winning factors (why this wins the track)
Now let me deliver the complete, self-contained PRD. I've verified the two critical technical facts it depends on: the **Qwen Model Studio OpenAI-compatible endpoint** (one-line swap from OpenRouter) and the **multi-cloud Kubernetes auth patterns** (GKE via OAuth token, AKS via Azure AD app, EKS via STS presigned URL). Here it is — hand this file directly to Claude Code.

---

# PRD: SentinelOps — Multi-Cloud Autonomous SRE Remediation Agent

**Version 1.0 · Track 4 (Autopilot Agent) · Qwen Hackathon**
**Document type:** Self-contained build spec for Claude Code (no prior conversation context assumed)

---

## 0. TL;DR for the implementer

You are building **SentinelOps**: an agent that ingests infrastructure alerts, diagnoses root cause, consults a memory of past incidents, proposes a remediation from a *fixed playbook registry* (never free-text shell), gates risky actions behind a human approval step, executes, verifies the real metric recovered, and writes the outcome back to memory so its **confidence per fix-pattern provably rises over time**.

- **AI backend:** Qwen via Alibaba Cloud Model Studio's **OpenAI-compatible endpoint**. Use the `openai` Python SDK with a swapped `base_url` + `api_key`. Model: `qwen-plus` (reasoning), `qwen-max` (arbitration).
- **Targets (connectors):** AWS EKS, Azure AKS, GCP GKE, Alibaba ACK — all normalized behind one `ClusterConnector` interface.
- **Storage:** SQLite (incidents, fix records) + NetworkX (incident similarity graph).
- **UI / HITL:** Telegram bot approval cards.
- **The proof:** a scripted replay of N seeded incidents showing confidence climbing, auto-resolve rate rising, and a single-agent baseline losing on false-fix rate and time-to-resolution.

Build in the phase order in §11. Do not skip the test harness (§10) — it *is* the demo.

---

## 1. Problem statement

SRE/DevOps teams drown in alerts. Existing agentic tools (K8sGPT, HolmesGPT) diagnose but stay **read-only**; commercial pipelines (Komodor Klaudia) do multi-agent remediation but are **locked SaaS** and keep an opaque human gate. **No open, local system closes the loop into confidence-driven unattended remediation with a visible, learned trust score.** That gap is the wedge.

## 2. Goals & non-goals

**Goals**
- End-to-end: signal → triage → memory → plan → arbitrate → gate → execute → verify → learn.
- A confidence score that is *earned* per (action, symptom) pair from real outcomes and *decays* with age.
- Multi-cloud connectors with production auth patterns.
- Safety: dry-run first, blast-radius limits, namespace denylist, rate limiting, safe-default fallback.

**Non-goals**
- Not building a general-purpose LLM shell executor. Actions are a closed set.
- Not remediating on "Qwen Cloud" — that is the LLM brain, *not* an infra target.
- Not handling network ingress to clusters (assume connectivity exists).

## 3. Architecture — the complete flow

Full pipeline (A→I). Click any stage to see its contract, inputs/outputs, and safety rules.
I've verified the two critical facts your PRD depends on, and both check out. Here's the self-contained PRD for Claude Code.

**Two things I confirmed via search (so the PRD is accurate, not guessed):**
- **Qwen backend:** Alibaba Cloud Model Studio exposes an **OpenAI-compatible endpoint** — literally a one-line swap of `base_url` + `api_key` + `model` from your OpenRouter setup. It also supports **function/tool calling** (needed for the agents) via `qwen-plus`/`qwen-max`. Base URL pattern: `https://{WorkspaceId}.<region>.maas.aliyuncs.com/compatible-mode/v1`.
- **Multi-cloud K8s connectors:** GKE (google SDK OAuth token), AKS (Azure AD app + `AKS_RESOURCE_ID` magic token), and EKS (STS pre-signed URL token) each have a distinct, verified auth recipe — plus the official `kubernetes` Python client's `watch.Watch()` for event ingestion. These are the exact patterns the connector layer standardizes.

---

# PRD — SentinelOps: A Memory-Driven, Multi-Cloud SRE Remediation Agent

## 0. Handoff Note to Claude Code
You are building this end-to-end with **no access to prior conversation**. This document is complete and self-contained. Build in the phase order in §11. Use **Qwen via Alibaba Cloud Model Studio's OpenAI-compatible API** for all reasoning. Never generate free-text shell/kubectl — all actions come from a typed playbook registry.

## 1. Product Summary
SentinelOps is an autonomous **DevOps/SRE incident-remediation agent**. It ingests alerts from any major cloud, diagnoses root cause, consults a memory of past incidents, proposes a parameterized fix with a **calibrated confidence score**, gates risky actions behind a human approval step, executes with a dry-run first, verifies the *actual symptom metric*, and writes the outcome back to memory so confidence-per-pattern **provably rises over time**.

**The wedge:** an open, local, watchable **confidence score earned per fix-pattern from real outcomes** — the one thing no OSS SRE agent (K8sGPT, HolmesGPT) or commercial tool (Komodor Klaudia) currently ships as an unattended, memory-driven closed loop.

## 2. Goals & Non-Goals

| Goals | Non-Goals |
|---|---|
| End-to-end incident→remediation→verification loop | Full APM/observability platform (we consume signals, not replace Datadog) |
| Confidence that measurably improves with experience | Arbitrary LLM-generated shell execution |
| Multi-cloud connectors (AWS/Azure/GCP/Alibaba) | Managing IAM provisioning for the client |
| Human-in-the-loop at gated decision points | Zero-human autonomy on day one |
| Qwen as the reasoning backend | Fine-tuning a custom model |

## 3. Target Scenarios (build playbooks for these 6)
1. **CrashLoopBackOff** (OOMKilled, bad config, failing probe, image pull error)
2. **Stuck rollout** (bad readiness probe, quota exceeded)
3. **Latency/error-rate spike** (ambiguous: last deploy vs downstream dep vs resource starvation)
4. **PVC stuck Pending** (storage class / zone mismatch)
5. **HPA not scaling** (missing metrics-server, wrong target metric)
6. **Flapping/noisy alert** — *correct action = suppress, not fix* (the ambiguity showcase)

## 4. Architecture Overview
```
                    ┌─────────────────────────────────────────────┐
                    │            CONNECTOR LAYER (§8)              │
   Cloud Monitoring │  CloudConnector (ABC)                        │
   webhooks ───────►│   ├── AWSConnector    (EKS via STS token)    │
   K8s Watch API ──►│   ├── AzureConnector  (AKS via AAD token)    │
                    │   ├── GCPConnector    (GKE via OAuth token)  │
                    │   └── AlibabaConnector(ACK via RAM token)    │
                    └───────────────────┬─────────────────────────┘
                                        │ normalized IncidentSignal
        ┌───────────────────────────────▼────────────────────────────┐
        │                    AGENT PIPELINE                           │
        │  A Ingest → B Triage → C Investigate → D Plan → E Arbitrate │
        │      → F Human Gate → G Execute → H Verify → I Memory-write  │
        └───────────────────────────────┬────────────────────────────┘
                                         │
        ┌────────────────────────────────▼───────────────────────────┐
        │  STATE: SQLite (incidents, fix_records) + NetworkX (graph)  │
        │  LLM:   Qwen (Model Studio OpenAI-compatible) (§7)          │
        │  UI:    Telegram approval cards + FastAPI webhook receiver   │
        │  JOBS:  APScheduler (memory decay, timeout fallbacks)        │
        └─────────────────────────────────────────────────────────────┘
```

## 5. Tech Stack
- **Language:** Python 3.11
- **LLM:** Qwen via Alibaba Cloud Model Studio, OpenAI-compatible endpoint (`openai` SDK)
- **K8s:** `kubernetes` (official Python client) — `watch.Watch()`, `CoreV1Api`, `AppsV1Api`, `AutoscalingV1Api`
- **Cloud SDKs:** `boto3` (AWS), `azure-identity`+`azure-mgmt-containerservice` (Azure), `google-cloud-container`+`google-auth` (GCP), `alibabacloud_cs20151215` (Alibaba ACK)
- **Storage:** SQLite (`sqlite3`/SQLModel) + NetworkX (in-memory graph, persisted to SQLite)
- **API/Webhook:** FastAPI + Uvicorn
- **Scheduler:** APScheduler
- **UI:** Telegram Bot API (`python-telegram-bot`)
- **Testing:** pytest, pytest-asyncio, `kind`/`minikube` for integration
- **Config:** pydantic-settings + `.env`

## 6. Repository Structure
```
sentinelops/
├── README.md
├── pyproject.toml
├── .env.example
├── docker-compose.yml            # app + local sqlite volume + kind bootstrap script
├── config/
│   └── settings.py               # pydantic Settings (thresholds, regions, workspace id)
├── src/sentinelops/
│   ├── main.py                   # FastAPI app + startup wiring
│   ├── models/
│   │   ├── signal.py             # IncidentSignal schema
│   │   ├── incident.py           # Incident, Hypothesis, Plan
│   │   └── fix_record.py         # FixRecord (Beta-Binomial state)
│   ├── connectors/
│   │   ├── base.py               # CloudConnector ABC
│   │   ├── aws.py  azure.py  gcp.py  alibaba.py
│   │   └── factory.py            # get_connector(provider)
│   ├── llm/
│   │   └── qwen_client.py        # OpenAI-compatible wrapper + tool-calling helper
│   ├── agents/
│   │   ├── triage.py  investigation.py  planning.py
│   │   ├── arbitration.py  execution.py  verification.py
│   ├── memory/
│   │   ├── graph.py              # NetworkX fingerprint graph
│   │   ├── store.py              # SQLite CRUD
│   │   └── confidence.py         # §9 formula (CORE MODULE)
│   ├── playbooks/
│   │   └── registry.py           # typed, parameterized actions + denylist
│   ├── gate/
│   │   └── telegram_gate.py      # approval cards + timeout fallback
│   ├── orchestrator.py           # A→I pipeline driver
│   └── jobs/
│       └── scheduler.py          # decay job, timeout job
├── tests/
│   ├── unit/  integration/  fixtures/seeded_incidents.json
└── scripts/
    ├── seed_incidents.py         # replay N incidents for the demo
    └── baseline_single_agent.py  # single-LLM baseline for comparison
```

## 7. Qwen LLM Backend (verified spec)
```python
# src/sentinelops/llm/qwen_client.py
from openai import OpenAI
from config.settings import settings

client = OpenAI(
    api_key=settings.DASHSCOPE_API_KEY,
    # Region-specific. Singapore example; swap region + WorkspaceId per deployment.
    base_url=f"https://{settings.MODELSTUDIO_WORKSPACE_ID}.ap-southeast-1.maas.aliyuncs.com/compatible-mode/v1",
)

MODELS = {"triage": "qwen-plus", "arbitration": "qwen-max", "cheap": "qwen-turbo"}

def reason(model_key, messages, tools=None):
    # NOTE (verified): tools cannot be combined with stream=True on Model Studio.
    return client.chat.completions.create(
        model=MODELS[model_key], messages=messages, tools=tools, temperature=0.2,
    )
```
- Every agent that must return structured output uses **tool/function calling** with a strict JSON Schema (Model Studio supports `tools` on `qwen-turbo/plus/max`).
- One-line swap from OpenRouter: only `base_url`, `api_key`, `model` change.

## 8. Connector Layer (production-ready, multi-cloud)
Common contract — all connectors return an authenticated `kubernetes.client.ApiClient`, so the agent pipeline is **cloud-agnostic**.

```python
# src/sentinelops/connectors/base.py
from abc import ABC, abstractmethod
from kubernetes import client

class CloudConnector(ABC):
    @abstractmethod
    def get_k8s_client(self) -> client.ApiClient: ...
    @abstractmethod
    def get_monitoring_events(self, since): ...   # normalized IncidentSignal list
    @abstractmethod
    def provider_name(self) -> str: ...
```

Verified auth recipe per provider (implement exactly these patterns):

| Provider | Auth pattern (verified) | Key detail |
|---|---|---|
| **GCP (GKE)** | `google.oauth2.service_account` → `ClusterManagerClient.get_cluster()` for endpoint → refresh OAuth token with `cloud-platform` scope → set as Bearer on `kubernetes.client.Configuration` | Cleanest; IAM-only |
| **Azure (AKS)** | AAD app (tenant/client/secret) → get mgmt token → `GET managedClusters/{name}` for FQDN → request token for magic resource ID `6dae42f8-4368-4678-94ff-3960e28e3630` → Bearer | Use Azure RBAC-for-K8s (authZ in Azure) |
| **AWS (EKS)** | `boto3` STS `generate_presigned_url` on `get_caller_identity` with `x-k8s-aws-id` header → base64url → `k8s-aws-v1.` prefix = token | authN via IAM, authZ via in-cluster RBAC (aws-auth configmap) |
| **Alibaba (ACK)** | RAM credentials → `alibabacloud_cs` `DescribeClusterUserKubeconfig` → parse kubeconfig token/cert | Mirrors GKE style |

Ingestion uses the official client's watch:
```python
from kubernetes import watch
w = watch.Watch()
for event in w.stream(core_v1.list_event_for_all_namespaces, _request_timeout=60):
    signal = normalize(event)   # -> IncidentSignal
```

> **Important scope clarification (verified):** "Qwen Cloud" / Alibaba Model Studio is an **AI platform, not an infra target** — it hosts the *brain*, not clusters to remediate. Connectors target real infra (AWS/Azure/GCP/Alibaba ECS/ACK); Qwen is the LLM backend only. Keep these two concerns separate in code.

## 9. Confidence-Scoring Module (the core differentiator)
```python
# src/sentinelops/memory/confidence.py
import math
from scipy.stats import beta

HALF_LIFE_DAYS = 90.0
PRIOR_A, PRIOR_B = 2.0, 2.0          # Beta(2,2): ~50/50 until proven
LOW_BLAST_BAR   = 0.35               # TUNABLE — calibrate by backtest
PROD_AUTO_BAR   = 0.55               # TUNABLE — calibrate by backtest

def _decayed_counts(outcomes):
    """outcomes: list of (success: bool, days_ago: float)."""
    a, b = PRIOR_A, PRIOR_B
    for success, days_ago in outcomes:
        w = math.exp(-math.log(2) / HALF_LIFE_DAYS * days_ago)
        if success: a += w
        else:       b += w
    return a, b

def action_confidence(p_diagnosis: float, outcomes) -> float:
    """Confidence = P(diagnosis right) x P(action fixes it | history).
    Second term = 10th-percentile (LCB) of decayed Beta posterior —
    thin evidence is punished automatically."""
    a, b = _decayed_counts(outcomes)
    p_fix_lcb = beta.ppf(0.10, a, b)     # lower confidence bound
    return p_diagnosis * p_fix_lcb
```
Behaviour to preserve (design intent):
- **Cold start** (no history): LCB ≈ 0.196 → correctly distrustful.
- **One win (1/1)** is *not* more trusted than 18/20 — the LCB fixes the naive `successes/attempts` bug.
- Recurrence of a validated pattern makes confidence climb until it crosses `LOW_BLAST_BAR`, at which point low-blast fixes auto-execute — **the demo moment**.
- `LOW_BLAST_BAR` / `PROD_AUTO_BAR` are **tunable constants**, calibrated by backtesting against the client's incident corpus for their tolerated false-auto-execute rate. Mark them clearly in config.

`FixRecord` is one row per `(action, symptom_cluster)` pair in SQLite; outcomes append-only.

## 10. Data Models (SQLite)
```
incidents(id, fingerprint, resource, namespace, symptom_tags_json,
          severity, raw_context_json, created_at, status)
hypotheses(id, incident_id, cause, p_diagnosis, evidence_json)
plans(id, incident_id, action, params_json, confidence, blast_radius,
      gate_decision, dry_run_diff)
fix_records(id, action, symptom_cluster, prior_a, prior_b)
fix_outcomes(id, fix_record_id, success, occurred_at)   -- for decay
graph_edges(src_fingerprint, dst_fix_record_id, weight)  -- NetworkX persist
```

## 11. Build Phases (execute in order)
1. **Phase 0 — Scaffold:** repo, settings, `.env.example`, docker-compose with `kind` bootstrap, CI.
2. **Phase 1 — Storage + Confidence:** SQLite models, NetworkX graph, `confidence.py` **with unit tests locking the cold-start LCB ≈ 0.196 and the 1/1-vs-18/20 invariant**.
3. **Phase 2 — Playbook registry:** typed actions + param schemas + namespace denylist + dry-run support.
4. **Phase 3 — Qwen client + agents B/C/D** (tool-calling, structured JSON out).
5. **Phase 4 — Connectors:** implement GCP first (simplest), then AWS, Azure, Alibaba, behind the ABC + factory. Integration-test against `kind` using a mock connector.
6. **Phase 5 — Arbitration (E) + Telegram gate (F)** incl. timeout→safe-default job.
7. **Phase 6 — Execution (G) + Verification (H) + Memory write-back (I).**
8. **Phase 7 — Orchestrator** wires A→I; APScheduler runs decay + timeout jobs.
9. **Phase 8 — Demo harness:** `seed_incidents.py` (replays the 6 scenarios incl. flapping), `baseline_single_agent.py`.

## 12. Testing Strategy
- **Unit:** confidence math invariants; playbook param validation; denylist enforcement; normalizer schema.
- **Integration:** each connector against `kind`/`minikube`; full A→I on a seeded CrashLoopBackOff; flapping-alert case asserts action == `suppress_alert` (does nothing).
- **Simulation/eval:** replay N seeded incidents; assert confidence-per-pattern monotonically trends up and auto-resolve rate climbs.
- **Safety tests:** dry-run always precedes mutation; denylisted namespace raises; timeout on high-severity triggers safe default, never silence.

## 13. Success Metrics (for judges)
- Confidence-per-pattern **rising** over N simulated incidents (plot it live).
- Auto-resolve rate **climbing** as memory accumulates.
- **Single-agent baseline vs. pipeline** on identical seeded incidents: accuracy, **false-fix rate**, time-to-resolution.
- Flapping-alert case where the agent **correctly does nothing**.

## 14. Configuration (`.env.example`)
```
DASHSCOPE_API_KEY=
MODELSTUDIO_WORKSPACE_ID=
MODELSTUDIO_REGION=ap-southeast-1
CLOUD_PROVIDER=gcp            # gcp|aws|azure|alibaba
TELEGRAM_BOT_TOKEN=
TELEGRAM_CHAT_ID=
LOW_BLAST_BAR=0.35           # TUNABLE
PROD_AUTO_BAR=0.55           # TUNABLE
APPROVAL_TIMEOUT_MIN=10
DENYLIST_NAMESPACES=kube-system,kube-public
```

---

This is copy-paste ready for Claude Code. Two decisions I'd lock before you hand it off — want me to spec either one next?
I've laid out the winning factors and the full A→I flow above. Now, before I write the self-contained PRD for Claude Code, one decision drives the document's structure — **pick what we spec out in most depth** (the buttons above), and I'll build the complete PRD around it.

Here's the honest state of what I verified while researching this:

- **Qwen backend is confirmed and easy.** Alibaba Cloud Model Studio exposes an **OpenAI-compatible endpoint** (`base_url=https://{WorkspaceId}.ap-southeast-1.maas.aliyuncs.com/compatible-mode/v1`, key `DASHSCOPE_API_KEY`, models `qwen-plus`/`qwen-max`). It supports **function calling** — which your Triage/Investigation/Remediation agents need. It's a genuine one-line swap from OpenRouter. Note one real constraint: `tools` **cannot be combined with `stream=True`**, so agent reasoning calls must be non-streaming.

- **The multi-cloud connector layer is real and buildable.** The pattern is: use each cloud's **IAM to mint a short-lived token**, then hand it to the *same* `kubernetes` Python client. GKE → service-account OAuth token; AKS → Azure AD app + `AKS_RESOURCE_ID` magic token; EKS → STS pre-signed URL (`k8s-aws-v1.` token); Alibaba ACK → same shape via RAM. One unified `KubernetesConnector` interface, four auth adapters behind it. That's your production-connectors story, and it's the strongest Q&A defense.

- **One correction to fold in:** "Qwen Cloud" is the LLM brain (Model Studio), **not** an infra target. Connectors target AWS/Azure/GCP/Alibaba clusters; Qwen is the reasoning backend. The PRD keeps these cleanly separated.
