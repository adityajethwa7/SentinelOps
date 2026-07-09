# SentinelOps

> A mathematically sound approach to autonomous DevSecOps remediation using Bayesian inference. 

SentinelOps bridges the gap between static runbooks and unpredictable LLMs by placing an autonomous reasoning agent inside a strict mathematical harness. It safely transitions from "Human-in-the-Loop" to "Autonomous" by actively scoring its own track record over time.

## 🚀 The Hackathon "Winning Stroke"
For the Qwen Hackathon, we've extended the backend proof-of-concept into a fully functional product featuring:
- **Historical Data Harness (Self-Learning)**: Solves the enterprise "cold start" problem. Instantly ingest past PagerDuty/Jira resolutions via CSV to bootstrap the AI's confidence to "Day-1 Trust" without waiting for live failures.
- **Real-Time React Dashboard**: A stunning Vite/React dashboard to monitor live incidents, track the live Bayesian confidence curves, and manage Human-in-the-Loop approval gates.
- **Local Prod Simulation**: A fully reproducible `kind` Kubernetes environment that proves the agent acts on real infrastructure outside of mock scripts.
- **Multi-Cloud Ready**: Pluggable playbook constraints and connectors designed to run commands against AWS EKS, GCP GKE, and Azure AKS transparently.

## 🏗 Architecture
- **Orchestrator**: Multi-agent pipeline (`Triage` → `Investigation` → `Planning` → `Arbitration`).
- **Memory Graph (SQLite)**: Stateful tracking of clusters (Resources × Symptoms) linked to `FixRecords`.
- **Bayesian Update Engine**: Updates Alpha/Beta parameters continuously on execution success/failure.
- **Arbitration Gate**: Calculates `Confidence Threshold` vs `Blast Radius` dynamically.
- **React Dashboard (Vite)**: Connects via FastAPI to visualize the real-time pipeline.

## 📚 Quickstart & Setup Guide
To spin up the real environment, ingest historical data, and start the UI, please refer to the extensive setup documentation:
👉 **[View the Setup Guide](docs/SETUP_GUIDE.md)** 👈
