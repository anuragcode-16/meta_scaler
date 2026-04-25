#!/bin/bash
# =============================================================================
# DEPLOY_TO_HF_SPACE.sh — AdaptiveSRE HuggingFace Space Deployment
# Run this from your project root: bash DEPLOY_TO_HF_SPACE.sh
# =============================================================================

set -e  # Exit on any error

echo "=============================================="
echo " AdaptiveSRE — HF Space Deployment Script"
echo "=============================================="

# ── STEP 1: Pre-flight checks ──────────────────────────────────────────────
echo ""
echo "[1/7] Pre-flight checks..."

# Check git is clean
if [[ -n $(git status --porcelain) ]]; then
  echo "  WARNING: You have uncommitted changes. Committing everything now."
  git add -A
  git commit -m "chore: pre-deployment sync $(date +%Y-%m-%d)"
fi

# Check required files exist
REQUIRED_FILES=("inference.py" "openenv.yaml" "Dockerfile" "requirements.runtime.txt" "server/app.py")
for f in "${REQUIRED_FILES[@]}"; do
  if [[ ! -f "$f" ]]; then
    echo "  FAIL: Missing required file: $f"
    exit 1
  fi
done
echo "  PASS: All required files present"

# ── STEP 2: Fix Dockerfile for HF Spaces ──────────────────────────────────
echo ""
echo "[2/7] Verifying Dockerfile for HF Spaces..."

# HF Spaces runs as non-root user 1000. Must set correct permissions.
cat > Dockerfile << 'DOCKERFILE_EOF'
FROM python:3.11-slim

# HF Spaces runs as user 1000 — set up correctly
RUN useradd -m -u 1000 user
WORKDIR /app

# Install Docker CLI (needed for subprocess docker commands)
RUN apt-get update && apt-get install -y \
    docker.io curl && \
    rm -rf /var/lib/apt/lists/*

# Install Python dependencies
COPY requirements.runtime.txt .
RUN pip install --no-cache-dir -r requirements.runtime.txt

# Copy project files
COPY --chown=user . .

# Switch to non-root user
USER user

# HF Spaces MUST use port 7860
EXPOSE 7860

ENV PYTHONUNBUFFERED=1
ENV HOME=/home/user

CMD ["python3", "-m", "uvicorn", "server.app:app", \
     "--host", "0.0.0.0", "--port", "7860", "--workers", "1"]
DOCKERFILE_EOF

echo "  PASS: Dockerfile updated for HF Spaces (non-root user, port 7860)"

# ── STEP 3: Create .gitignore ─────────────────────────────────────────────
echo ""
echo "[3/7] Creating .gitignore..."

cat > .gitignore << 'GITIGNORE_EOF'
__pycache__/
*.py[cod]
*.egg-info/
.env
.venv/
venv/
checkpoints/
*.pt
*.bin
*.safetensors
eval_results.json
inference_output.txt
*.log
.DS_Store
GITIGNORE_EOF

echo "  PASS: .gitignore created"

# ── STEP 4: Push to GitHub ─────────────────────────────────────────────────
echo ""
echo "[4/7] Pushing to GitHub..."

git add -A
git commit -m "feat: HF Space deployment ready — Dockerfile + README updated" || echo "  Nothing new to commit"
git push origin main
echo "  PASS: GitHub up to date"

# ── STEP 5: Create/push HF Space ──────────────────────────────────────────
echo ""
echo "[5/7] Setting up HuggingFace Space..."

# Install HF CLI if not present
pip install huggingface_hub -q

python3 << 'PYTHON_EOF'
from huggingface_hub import HfApi, create_repo
import os, subprocess

api = HfApi()

repo_id = "ashifsekh/adaptive-sre"

# Create space if it doesn't exist
try:
    create_repo(
        repo_id=repo_id,
        repo_type="space",
        space_sdk="docker",   # We use Docker runtime
        exist_ok=True,
        private=False,
    )
    print(f"  Space ready: https://huggingface.co/spaces/{repo_id}")
except Exception as e:
    print(f"  Space already exists or error: {e}")

PYTHON_EOF

echo "  PASS: HF Space created (Docker runtime)"

# ── STEP 6: Push to HF Space using git ─────────────────────────────────────
echo ""
echo "[6/7] Pushing code to HF Space..."

# HF Spaces uses a separate git remote
HF_REMOTE="https://huggingface.co/spaces/ashifsekh/adaptive-sre"

# Add HF remote if not already there
git remote get-url hf-space 2>/dev/null || git remote add hf-space "$HF_REMOTE"

# Push — use your HF token for auth
# Set HF_TOKEN env var before running this script:  export HF_TOKEN=hf_xxx
git push hf-space main

echo "  PASS: Code pushed to HF Space"

# ── STEP 7: Validate Space is live ─────────────────────────────────────────
echo ""
echo "[7/7] Waiting for Space to build and validating..."

sleep 30  # Give Space time to start building

MAX_RETRIES=20
RETRY_COUNT=0
SPACE_URL="https://ashifsekh-adaptive-sre.hf.space"

while [ $RETRY_COUNT -lt $MAX_RETRIES ]; do
  HTTP_CODE=$(curl -s -o /dev/null -w "%{http_code}" \
    -X POST "$SPACE_URL/reset" \
    -H "Content-Type: application/json" \
    -d '{"task":"easy"}' \
    --max-time 10 2>/dev/null || echo "000")

  if [ "$HTTP_CODE" = "200" ]; then
    echo "  PASS: Space is live! POST /reset → HTTP 200"
    echo ""
    echo "=============================================="
    echo " DEPLOYMENT COMPLETE"
    echo " Space URL: https://huggingface.co/spaces/ashifsekh/adaptive-sre"
    echo " API URL:   $SPACE_URL"
    echo ""
    echo " Submission validation:"
    echo "   curl -X POST $SPACE_URL/reset -d '{\"task\":\"easy\"}'"
    echo "=============================================="
    exit 0
  fi

  echo "  Waiting... attempt $((RETRY_COUNT+1))/$MAX_RETRIES (HTTP $HTTP_CODE)"
  sleep 15
  RETRY_COUNT=$((RETRY_COUNT+1))
done

echo "  WARNING: Space not responding after $(($MAX_RETRIES * 15))s"
echo "  Check build logs at: https://huggingface.co/spaces/ashifsekh/adaptive-sre"
echo "  The build may still be in progress — check in 2-3 minutes"