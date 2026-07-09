# SentinelOps Setup Guide

This guide covers how to set up SentinelOps end-to-end, including connecting to multiple DevOps tools (AWS, GCP, Azure, and Local Kubernetes) and configuring the AI engine.

## Prerequisites
- Python 3.11+
- `uv` (Fast Python package installer)
- Node.js (for the frontend dashboard)
- Qwen/Dashtone API Key

## 1. Local Prod-Like Simulation (Recommended for Demo)
We provide a local simulation using `kind` (Kubernetes in Docker). This allows you to test SentinelOps against real crashing pods without needing cloud credentials.

1. Ensure Docker is running.
2. Run the environment setup script:
   ```bash
   ./scripts/setup_local_prod.sh
   ```
   This spins up a local Kubernetes cluster named `sentinelops-demo` and deploys a "bad-app" pod configured to memory leak and crash.

## 2. Cloud Provider Connections

SentinelOps supports multi-cloud execution via the Playbook Registry.

### AWS EKS Setup
1. Export your AWS credentials:
   ```bash
   export AWS_ACCESS_KEY_ID="your_key"
   export AWS_SECRET_ACCESS_KEY="your_secret"
   export AWS_DEFAULT_REGION="us-east-1"
   ```
2. Update `kubeconfig` to point to EKS:
   ```bash
   aws eks update-kubeconfig --region us-east-1 --name your-cluster-name
   ```
3. Set `SENTINELOPS_CLOUD_PROVIDER=aws` in `.env`.

### GCP GKE Setup
1. Authenticate with gcloud:
   ```bash
   gcloud auth application-default login
   ```
2. Get cluster credentials:
   ```bash
   gcloud container clusters get-credentials your-cluster-name --region your-region
   ```
3. Set `SENTINELOPS_CLOUD_PROVIDER=gcp` in `.env`.

### Azure AKS Setup
1. Authenticate with Azure CLI:
   ```bash
   az login
   ```
2. Get cluster credentials:
   ```bash
   az aks get-credentials --resource-group your-resource-group --name your-cluster-name
   ```
3. Set `SENTINELOPS_CLOUD_PROVIDER=azure` in `.env`.

## 3. The "Self-Learning" Harness
For enterprise deployments, you do not want to wait weeks for the AI to learn confidence patterns. You can ingest past historical success data from PagerDuty/Jira.

1. Export historical incidents to `data/historical_incidents.csv`.
2. Run the ingestor:
   ```bash
   python scripts/ingest_historical_data.py
   ```
3. The AI's Bayesian graph will instantly pre-load high confidence scores for known issues.

## 4. Starting the Application
1. **Backend API:**
   ```bash
   python -m uvicorn src.sentinelops.api.server:app --reload
   ```
2. **Frontend Dashboard:**
   ```bash
   cd frontend
   npm run dev
   ```
3. Open `http://localhost:5173` to view the Live Incident Feed and Confidence Dashboard.
