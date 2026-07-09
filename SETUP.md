# Setup Guide

This document outlines how to correctly set up, configure, and launch the SentinelOps project on your local machine.

## Prerequisites

1. **Python 3.11+**: Ensure you have Python installed. The project manages dependencies using `uv` or `pip`.
2. **Node.js 18+**: Required for the Vite + React frontend.
3. **SQLite**: Required for the memory database (usually bundled with Python).

## 1. Clone & Configure Environment

Clone the repository and enter the root directory:
```bash
cd SentinelOps
```

Create an `.env` file by copying the example template:
```bash
cp .env.example .env
```
Inside `.env`, you **must** configure your API keys (e.g., `GEMINI_API_KEY`) for the agents to operate correctly. You can mock cloud credentials (`CLOUD_PROVIDER="mock"`) to test the system without real Kubernetes clusters.

## 2. Install Backend Dependencies

It is highly recommended to use a virtual environment:
```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt # Or use your package manager (e.g., uv sync)
```

## 3. Launching the Application

We have bundled a unified start script that will launch both the FastAPI backend and the React frontend concurrently.

```bash
# Make the script executable
chmod +x scripts/start.sh

# Start the system
./scripts/start.sh
```

### Accessing the System
- **React Dashboard:** [http://localhost:5173](http://localhost:5173)
- **FastAPI Swagger Docs:** [http://localhost:8000/docs](http://localhost:8000/docs)

## 4. Ingesting Historical Data (Optional)

To solve the "cold start" problem (so the agent trusts autonomous fixes immediately), you can upload the provided sample historical data to prime the Bayesian memory:

```bash
curl -X POST "http://localhost:8000/api/ingest" \
  -H "X-API-Key: sentinelops-hackathon-2026" \
  -F "file=@data/historical_fixes.csv"
```
