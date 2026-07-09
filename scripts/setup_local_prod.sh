#!/bin/bash
set -e

echo "============================================================"
echo "🚀 SentinelOps: Local Prod Environment Setup"
echo "============================================================"

# Check if kind is installed
if ! command -v kind &> /dev/null; then
    echo "❌ Error: 'kind' is not installed. Please install it (e.g. brew install kind)"
    exit 1
fi

# Check if kubectl is installed
if ! command -v kubectl &> /dev/null; then
    echo "❌ Error: 'kubectl' is not installed. Please install it (e.g. brew install kubectl)"
    exit 1
fi

CLUSTER_NAME="sentinelops-demo"

# Create cluster if it doesn't exist
if ! kind get clusters | grep -q "^${CLUSTER_NAME}$"; then
    echo "📦 Creating kind cluster '${CLUSTER_NAME}'..."
    kind create cluster --name ${CLUSTER_NAME}
else
    echo "✅ Cluster '${CLUSTER_NAME}' already exists."
fi

# Deploy the bad app
echo "🚀 Deploying 'bad-app' (memory leaking pod)..."
kubectl apply -f k8s/bad-app.yaml --context kind-${CLUSTER_NAME}

echo "⏳ Waiting for deployment to rollout..."
kubectl rollout status deployment/bad-app --context kind-${CLUSTER_NAME} || true

echo "✅ Environment ready!"
echo "Run 'kubectl get pods --context kind-${CLUSTER_NAME}' to see the pods."
echo "============================================================"
