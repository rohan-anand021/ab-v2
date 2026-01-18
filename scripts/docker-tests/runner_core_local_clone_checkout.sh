#!/usr/bin/env bash
set -euo pipefail

IMAGE=${IMAGE:-runner-core}
CONTAINER=${CONTAINER:-runner-core-clone-$$}
TMP_ROOT=$(mktemp -d)
REPO_SRC="$TMP_ROOT/repo"
BARE_REPO="$TMP_ROOT/repo.git"

log() { printf '==> %s\n' "$*"; }
fail() { printf 'FAIL: %s\n' "$*" >&2; exit 1; }

cleanup() {
  docker rm -f "$CONTAINER" >/dev/null 2>&1 || true
  rm -rf "$TMP_ROOT"
}
trap cleanup EXIT

log "Creating local test repo"
mkdir -p "$REPO_SRC"
pushd "$REPO_SRC" >/dev/null
git init -q
git config user.email "runner@example.com"
git config user.name "Runner Core"

cat > app.py <<'PY'
def add(a, b):
    return a + b
PY

cat > test_app.py <<'PY'
from app import add

def test_add():
    assert add(1, 1) == 3  # intentionally wrong
PY

git add app.py test_app.py
git commit -q -m "failing test commit"
FAIL_SHA=$(git rev-parse HEAD)

cat > test_app.py <<'PY'
from app import add

def test_add():
    assert add(1, 1) == 2
PY

git add test_app.py
git commit -q -m "fix test"
PASS_SHA=$(git rev-parse HEAD)
popd >/dev/null

log "Creating bare clone"
git clone --bare -q "$REPO_SRC" "$BARE_REPO"

log "Starting container $CONTAINER from image $IMAGE"
docker run -d --name "$CONTAINER" "$IMAGE" >/dev/null

log "Copying bare repo into container"
docker cp "$BARE_REPO" "$CONTAINER":/tmp/repo.git
log "Fixing ownership on bare repo for git safety checks"
docker exec --user root "$CONTAINER" chown -R agent:agent /tmp/repo.git

log "Installing minimal pytest shim inside container (no network)"
docker exec "$CONTAINER" bash -lc '
cat > /opt/venv/bin/pytest <<'"'"'PY'"'"'
#!/usr/bin/env python3
import glob
import os
import importlib.util
import sys
import traceback

sys.path.insert(0, os.getcwd())

paths = sorted(glob.glob("test_*.py") + glob.glob("*_test.py"))
failures = 0
for path in paths:
    spec = importlib.util.spec_from_file_location(path.replace("/", "_"), path)
    mod = importlib.util.module_from_spec(spec)
    try:
        spec.loader.exec_module(mod)
    except Exception:
        failures += 1
        traceback.print_exc()
        continue
    for name in dir(mod):
        if name.startswith("test_"):
            obj = getattr(mod, name)
            if callable(obj):
                try:
                    obj()
                except Exception:
                    failures += 1
                    traceback.print_exc()
if failures:
    sys.exit(1)
PY
chmod +x /opt/venv/bin/pytest
'
PYTEST=/opt/venv/bin/pytest

log "Cloning repo inside container"
docker exec "$CONTAINER" git clone /tmp/repo.git /workspace/repo >/dev/null

log "Checkout failing commit ($FAIL_SHA) and ensure pytest fails"
set +e
docker exec "$CONTAINER" bash -lc "cd /workspace/repo && git checkout $FAIL_SHA && $PYTEST -q"
fail_status=$?
set -e
if [[ $fail_status -eq 0 ]]; then
  fail "pytest unexpectedly passed on failing commit"
fi

log "Checkout passing commit ($PASS_SHA) and ensure pytest passes"
docker exec "$CONTAINER" bash -lc "cd /workspace/repo && git checkout $PASS_SHA && $PYTEST -q" >/dev/null

log "Stopping container cleanly"
docker stop "$CONTAINER" >/dev/null

log "Local clone/checkout test passed"
