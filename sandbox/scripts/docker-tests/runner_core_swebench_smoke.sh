#!/usr/bin/env bash
set -euo pipefail

IMAGE=${IMAGE:-runner-core}
CONFIG=${CONFIG:-scripts/swe-bench/swebench_smoke_astropy.yaml}

log() { printf '==> %s\n' "$*"; }
note() { printf '%s\n' "$*" >&2; }

if [[ ! -f "$CONFIG" ]]; then
  echo "Config not found at $CONFIG" >&2
  exit 1
fi

INSTANCES=$(python3 - <<'PY'
import json, os, sys, pathlib

cfg_path = pathlib.Path(os.environ["CONFIG"])
raw = []
for line in cfg_path.read_text().splitlines():
    line = line.strip()
    if not line or line.startswith("#"):
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
if want_id:
    instances = [inst for inst in instances if inst.get("id") == want_id]
    if not instances:
        sys.exit(f"Instance {want_id} not found in config.")

for inst in instances:
    required = ("id", "repo_url", "commit", "test_command")
    missing = [k for k in required if not str(inst.get(k, "")).strip()]
    if missing:
        sys.exit(f"Instance {inst.get('id','?')} missing fields: {', '.join(missing)}")
    print(json.dumps(inst))
PY
)

if [[ -z "$INSTANCES" ]]; then
  echo "No instances to run" >&2
  exit 1
fi

success=0

while IFS= read -r INST_JSON; do
  [[ -z "$INST_JSON" ]] && continue
  export INSTANCE_JSON="$INST_JSON"

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
  FAIL_TO_PASS=$(python3 - <<'PY'
import json, os
data = json.loads(os.environ["INSTANCE_JSON"])
val = data.get("FAIL_TO_PASS") or []
if isinstance(val, str):
    try:
        import json as _json
        val = _json.loads(val)
    except Exception:
        val = [val]
if not isinstance(val, (list, tuple)):
    val = [str(val)]
print(" ".join(val))
PY
)
  PASS_TO_PASS=$(python3 - <<'PY'
import json, os
data = json.loads(os.environ["INSTANCE_JSON"])
val = data.get("PASS_TO_PASS") or []
if isinstance(val, str):
    try:
        import json as _json
        val = _json.loads(val)
    except Exception:
        val = [val]
if not isinstance(val, (list, tuple)):
    val = [str(val)]
print(" ".join(val))
PY
)
  EXPECTED_FAIL=$(python3 - <<'PY'
import json, os
data = json.loads(os.environ["INSTANCE_JSON"])
print(str(bool(data.get("expected_fail", True))).lower())
PY
)
  SETUP_COMMANDS=$(python3 - <<'PY'
import json, os
data = json.loads(os.environ["INSTANCE_JSON"])
for cmd in data.get("setup_commands", []):
    print(cmd)
PY
)
  SETUP_COMMIT=$(python3 - <<'PY'
import json, os
data = json.loads(os.environ["INSTANCE_JSON"])
print(data.get("environment_setup_commit") or data.get("commit"))
PY
)
  VERSION=$(python3 - <<'PY'
import json, os
data = json.loads(os.environ["INSTANCE_JSON"])
print(data.get("version") or "")
PY
)
  PACKAGE_NAME=$(python3 - <<'PY'
import json, os
url = json.loads(os.environ["INSTANCE_JSON"]).get("repo_url", "")
name = url.rstrip("/").split("/")[-1].replace(".git", "") if url else ""
print(name)
PY
)
  TEST_PATCH=$(python3 - <<'PY'
import json, os
data = json.loads(os.environ["INSTANCE_JSON"])
print(data.get("test_patch") or "")
PY
)

  CONTAINER="runner-core-swebench-${INSTANCE_ID//[^a-zA-Z0-9]/-}"
  note "---- Running $INSTANCE_ID ----"
  docker rm -f "$CONTAINER" >/dev/null 2>&1 || true

  docker run -d --name "$CONTAINER" "$IMAGE" >/dev/null
  docker exec "$CONTAINER" rm -rf /workspace/repo
  docker exec "$CONTAINER" git clone "$REPO_URL" /workspace/repo >/dev/null
  docker exec "$CONTAINER" bash -lc "cd /workspace/repo && git checkout $SETUP_COMMIT" >/dev/null
  if [[ -n "$TEST_PATCH" ]]; then
    docker exec "$CONTAINER" env INSTANCE_JSON="$INSTANCE_JSON" bash -lc $'cd /workspace/repo && python - <<\"PY\"\nimport json, os, pathlib, subprocess, sys\npatch = json.loads(os.environ[\"INSTANCE_JSON\"]).get(\"test_patch\") or \"\"\nif not patch.strip():\n    sys.exit()\npath = pathlib.Path(\"/tmp/test_patch.diff\")\npath.write_text(patch)\nres = subprocess.run([\"git\", \"apply\", str(path)])\nsys.exit(res.returncode)\nPY' || { note "Applying test_patch failed for $INSTANCE_ID"; docker rm -f "$CONTAINER" >/dev/null; continue; }
  fi
  docker exec "$CONTAINER" bash -lc $'cd /workspace/repo && python - <<\"PY\"\nfrom pathlib import Path\nrepl = {\n    \"from collections import MutableMapping\": \"from collections.abc import MutableMapping\",\n    \"from collections import Mapping\": \"from collections.abc import Mapping\",\n    \"collections.MutableMapping\": \"collections.abc.MutableMapping\",\n    \"collections.Mapping\": \"collections.abc.Mapping\",\n}\nfor p in Path(\".\").rglob(\"*.py\"):\n    txt = p.read_text()\n    new = txt\n    for old, new_val in repl.items():\n        new = new.replace(old, new_val)\n    if new != txt:\n        p.write_text(new)\nPY'

  if [[ -n "$SETUP_COMMANDS" ]]; then
    while IFS= read -r cmd; do
      [[ -z "$cmd" ]] && continue
      docker exec "$CONTAINER" bash -lc "cd /workspace/repo && $cmd" || { note "Setup failed for $INSTANCE_ID"; docker rm -f "$CONTAINER" >/dev/null; continue 2; }
    done <<< "$SETUP_COMMANDS"
  fi

  if [[ -n "$VERSION" && -n "$PACKAGE_NAME" ]]; then
    docker exec "$CONTAINER" bash -lc "python -m pip install ${PACKAGE_NAME}==${VERSION} || true" || true
  fi

  docker exec "$CONTAINER" bash -lc "cd /workspace/repo && git checkout $COMMIT" >/dev/null
  docker exec "$CONTAINER" bash -lc "cd /workspace/repo && python -m pip install --no-deps -e ." || { note "Editable install failed for $INSTANCE_ID"; docker rm -f "$CONTAINER" >/dev/null; continue; }

  set +e
  docker exec "$CONTAINER" bash -lc "cd /workspace/repo && $TEST_COMMAND"
  status=$?
  set -e
  if [[ "$EXPECTED_FAIL" == "true" && $status -eq 0 ]]; then
    note "Baseline unexpectedly passed for $INSTANCE_ID"
    docker rm -f "$CONTAINER" >/dev/null
    continue
  fi
  if [[ "$EXPECTED_FAIL" == "false" && $status -ne 0 ]]; then
    note "Baseline failed but expected pass for $INSTANCE_ID"
    docker rm -f "$CONTAINER" >/dev/null
    continue
  fi

  if [[ -n "$FAIL_TO_PASS" ]]; then
    set +e
    docker exec "$CONTAINER" env INSTANCE_JSON="$INSTANCE_JSON" bash -lc $'cd /workspace/repo && PYTHONWARNINGS=ignore::UserWarning python - <<\"PY\"\nimport json, os, subprocess\ninst = json.loads(os.environ[\"INSTANCE_JSON\"])\nargs = inst.get(\"FAIL_TO_PASS\") or []\nif isinstance(args, str):\n    try:\n        import json as _json\n        args = _json.loads(args)\n    except Exception:\n        args = args.split()\ncode = subprocess.run([\"python\", \"-m\", \"pytest\", \"-q\", *args]).returncode\nraise SystemExit(code)\nPY'
    ft_status=$?
    set -e
    if [[ $ft_status -eq 0 ]]; then
      note "FAIL_TO_PASS unexpectedly passed for $INSTANCE_ID"
      docker rm -f "$CONTAINER" >/dev/null
      continue
    fi
  fi

  docker rm -f "$CONTAINER" >/dev/null
  log "Instance $INSTANCE_ID completed"
  success=1
  break
done <<< "$INSTANCES"

if [[ $success -eq 0 ]]; then
  echo "No instance completed successfully" >&2
  exit 1
fi

log "SWE-bench-lite smoke test completed"
