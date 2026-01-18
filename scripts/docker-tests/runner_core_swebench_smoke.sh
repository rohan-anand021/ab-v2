#!/usr/bin/env bash
set -euo pipefail

IMAGE=${IMAGE:-runner-core}
CONTAINER=${CONTAINER:-runner-core-swebench-$$}
CONFIG=${CONFIG:-scripts/docker-tests/swebench_smoke.yaml}
export CONFIG

log() { printf '==> %s\n' "$*"; }
fail() { printf 'FAIL: %s\n' "$*" >&2; exit 1; }

cleanup() {
  docker rm -f "$CONTAINER" >/dev/null 2>&1 || true
}
trap cleanup EXIT

if [[ ! -f "$CONFIG" ]]; then
  fail "Config not found at $CONFIG. Add swebench_smoke.yaml first."
fi

INSTANCE_JSON=$(python3 - <<'PY'
import json, os, sys, pathlib

cfg_path = pathlib.Path(os.environ["CONFIG"])
raw = []
for line in cfg_path.read_text().splitlines():
    if line.strip().startswith("#"):
        continue
    if not line.strip():
        continue
    raw.append(line)
text = "\n".join(raw)
try:
    cfg = json.loads(text)
except json.JSONDecodeError as exc:
    sys.exit(f"Could not parse {cfg_path}: {exc}")

instances = cfg.get("instances") or []
if not instances:
    sys.exit("No instances defined in config.")

want_id = os.environ.get("INSTANCE_ID")
selected = None
if want_id:
    for inst in instances:
        if inst.get("id") == want_id:
            selected = inst
            break
    if selected is None:
        sys.exit(f"Instance {want_id} not found in config.")
else:
    selected = instances[0]

required = ("id", "repo_url", "commit", "test_command")
missing = [k for k in required if not str(selected.get(k, "")).strip()]
if missing:
    sys.exit(f"Instance {selected.get('id','?')} missing fields: {', '.join(missing)}")

print(json.dumps(selected))
PY
) || fail "$INSTANCE_JSON"
export INSTANCE_JSON

INSTANCE_ID=$(python3 - <<'PY'
import json, os
data = json.loads(os.environ["INSTANCE_JSON"])
print(data["id"])
PY
)
REPO_URL=$(python3 - <<'PY'
import json, os
data = json.loads(os.environ["INSTANCE_JSON"])
print(data["repo_url"])
PY
)
COMMIT=$(python3 - <<'PY'
import json, os
data = json.loads(os.environ["INSTANCE_JSON"])
print(data["commit"])
PY
)
TEST_COMMAND=$(python3 - <<'PY'
import json, os
data = json.loads(os.environ["INSTANCE_JSON"])
print(data["test_command"])
PY
)
if [[ "$COMMIT" == FILL_ME_* || "$TEST_COMMAND" == FILL_ME_* ]]; then
  fail "Update $CONFIG with real commit/test_command for $INSTANCE_ID (see notes in the file)."
fi
SETUP_COMMANDS=$(python3 - <<'PY'
import json, os
data = json.loads(os.environ["INSTANCE_JSON"])
for cmd in data.get("setup_commands", []):
    print(cmd)
PY
)

log "Using instance $INSTANCE_ID"
log "Starting container $CONTAINER from image $IMAGE"
docker run -d --name "$CONTAINER" "$IMAGE" >/dev/null

log "Cloning repo $REPO_URL"
docker exec "$CONTAINER" rm -rf /workspace/repo
docker exec "$CONTAINER" git clone "$REPO_URL" /workspace/repo >/dev/null

log "Checking out commit $COMMIT"
docker exec "$CONTAINER" bash -lc "cd /workspace/repo && git checkout $COMMIT" >/dev/null

# Apply simple py3 compat rewrites for older repos (collections.* -> collections.abc.*)
log "Applying python compat rewrites (collections.* -> collections.abc.*)"
docker exec "$CONTAINER" bash -lc $'cd /workspace/repo && python - <<\"PY\"\nfrom pathlib import Path\nrepl = {\n    \"from collections import MutableMapping\": \"from collections.abc import MutableMapping\",\n    \"from collections import Mapping\": \"from collections.abc import Mapping\",\n    \"collections.MutableMapping\": \"collections.abc.MutableMapping\",\n    \"collections.Mapping\": \"collections.abc.Mapping\",\n}\nfor p in Path(\".\").rglob(\"*.py\"):\n    txt = p.read_text()\n    new = txt\n    for old, new_val in repl.items():\n        new = new.replace(old, new_val)\n    if new != txt:\n        p.write_text(new)\nPY'

if [[ -n "$SETUP_COMMANDS" ]]; then
  log "Running setup commands"
  while IFS= read -r cmd; do
    [[ -z "$cmd" ]] && continue
    docker exec "$CONTAINER" bash -lc "cd /workspace/repo && $cmd"
  done <<< "$SETUP_COMMANDS"
fi

log "Running baseline test command (expected to fail): $TEST_COMMAND"
set +e
docker exec "$CONTAINER" bash -lc "cd /workspace/repo && $TEST_COMMAND"
status=$?
set -e
if [[ $status -eq 0 ]]; then
  fail "Baseline tests unexpectedly passed (exit 0)"
else
  log "Baseline tests failed as expected (exit $status)"
fi

log "Stopping container cleanly"
docker stop "$CONTAINER" >/dev/null

log "SWE-bench-lite smoke test completed"
