#!/usr/bin/env bash
# Post-create lifecycle hook. Brings up Oracle, then runs the three
# pre-build steps the workshop notebook depends on:
#   1. bootstrap.py     — AGENT user + vector memory pool
#   2. onnx_setup.py    — download + load ALL_MINILM_L12_V2 ONNX model
#   3. seed_supplychain — HF dataset → OracleVS + AsyncOracleStore
#
# Idempotent. Safe to re-run.
set -euo pipefail

WORKSHOP_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$WORKSHOP_ROOT"

LOG_DIR="$WORKSHOP_ROOT/.devcontainer/logs"
mkdir -p "$LOG_DIR"

# ── 1. Bring up Oracle Free ───────────────────────────────────────────────
echo "▶ Starting Oracle Free container …"
docker compose -f .devcontainer/docker-compose.yml up -d

echo "▶ Waiting for Oracle to become healthy (this can take 3-5 minutes on first boot) …"
ATTEMPTS=0
while [ "$ATTEMPTS" -lt 80 ]; do
  STATUS=$(docker inspect -f '{{.State.Health.Status}}' oracle-free 2>/dev/null || echo "starting")
  if [ "$STATUS" = "healthy" ]; then
    echo "✅ Oracle is healthy."
    break
  fi
  ATTEMPTS=$((ATTEMPTS + 1))
  sleep 15
  echo "   … still waiting ($STATUS, attempt $ATTEMPTS/80)"
done

if [ "$STATUS" != "healthy" ]; then
  echo "❌ Oracle never became healthy. Check 'docker logs oracle-free'." >&2
  exit 1
fi

# ── 2. Bootstrap (AGENT user + vector pool) ───────────────────────────────
echo "▶ Running bootstrap.py …"
python app/scripts/bootstrap.py 2>&1 | tee "$LOG_DIR/bootstrap.log"

# bootstrap may have set vector_memory_size in SPFILE; bounce so it takes effect.
if grep -q "scope=spfile" "$LOG_DIR/bootstrap.log"; then
  echo "▶ Restarting Oracle so vector_memory_size takes effect …"
  docker compose -f .devcontainer/docker-compose.yml restart oracle-free
  sleep 30
  for _ in $(seq 1 40); do
    if [ "$(docker inspect -f '{{.State.Health.Status}}' oracle-free)" = "healthy" ]; then
      break
    fi
    sleep 10
  done
fi

# ── 3. Load the ONNX embedder model ───────────────────────────────────────
echo "▶ Running onnx_setup.py …"
python app/scripts/onnx_setup.py 2>&1 | tee "$LOG_DIR/onnx_setup.log"

# ── 4. Seed Hugging Face data → OracleVS + AsyncOracleStore ───────────────
echo "▶ Running seed_supplychain.py …"
python app/scripts/seed_supplychain.py 2>&1 | tee "$LOG_DIR/seed.log"

echo
echo "✅ Runtime setup complete. The workshop notebook can be opened now."
echo "   Notebook:   workshop/notebook_student.ipynb"
echo "   App (next): http://localhost:3000  (once start_app.sh has the backend + frontend ready)"
