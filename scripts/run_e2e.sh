#!/bin/bash
set -e

# Setup environment variables for E2E sandbox execution
export CLOUD_PROVIDER="mock"
export DASHSCOPE_API_KEY="mock-key"
export MODELSTUDIO_WORKSPACE_ID="mock-workspace"

echo "🧪 Running SentinelOps E2E Test Suite (Tiers 1-4)..."
.venv/bin/pytest tests/e2e --tb=short -v

echo "🎉 All E2E test cases passed!"
