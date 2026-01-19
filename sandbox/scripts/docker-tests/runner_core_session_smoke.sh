#!/usr/bin/env bash
set -euo pipefail

IMAGE=${IMAGE:-runner-core}
CONTAINER=${CONTAINER:-runner-core-smoke-$$}

log() { printf '==> %s\n' "$*"; }
fail() { printf 'FAIL: %s\n' "$*" >&2; exit 1; }

assert_eq() {
  local got=$1 expected=$2 msg=$3
  if [[ "$got" != "$expected" ]]; then
    fail "$msg (got: $got, expected: $expected)"
  fi
}

assert_contains() {
  local haystack=$1 needle=$2 msg=$3
  if [[ "$haystack" != *"$needle"* ]]; then
    fail "$msg (missing: $needle)"
  fi
}

cleanup() {
  docker rm -f "$CONTAINER" >/dev/null 2>&1 || true
}
trap cleanup EXIT

log "Starting container $CONTAINER from image $IMAGE"
docker run -d --name "$CONTAINER" "$IMAGE" >/dev/null

log "Verifying container is running"
docker ps --filter "name=$CONTAINER" --filter "status=running" --format '{{.Names}}' | grep -qx "$CONTAINER" || fail "container is not running"

log "Exec works repeatedly"
docker exec "$CONTAINER" true
docker exec "$CONTAINER" true

log "Stdout/stderr capture"
output=$(docker exec "$CONTAINER" bash -lc 'echo out; echo err >&2' 2>&1)
assert_contains "$output" "out" "stdout missing"
assert_contains "$output" "err" "stderr missing"

log "Exit code propagation"
set +e
docker exec "$CONTAINER" bash -lc 'exit 7'
status=$?
set -e
assert_eq "$status" 7 "docker exec exit code mismatch"

log "Default cwd is /workspace"
cwd=$(docker exec "$CONTAINER" pwd)
assert_eq "$cwd" "/workspace" "unexpected cwd"

log "Env overlay works"
foo=$(docker exec -e FOO=bar "$CONTAINER" bash -lc 'echo -n "$FOO"')
assert_eq "$foo" "bar" "env override failed"

log "Core tools available"
docker exec "$CONTAINER" rg --version >/dev/null
docker exec "$CONTAINER" git --version >/dev/null
docker exec "$CONTAINER" patch --version >/dev/null
docker exec "$CONTAINER" uv --version >/dev/null

log "Patch application"
docker exec "$CONTAINER" bash -lc '
  printf "hello\n" > /workspace/hello.txt
  cat > /workspace/hello.patch <<'"'"'PATCH'"'"'
--- a/hello.txt
+++ b/hello.txt
@@ -1 +1 @@
-hello
+hello world
PATCH
  patch -p1 -d /workspace < /workspace/hello.patch
'
patched=$(docker exec "$CONTAINER" cat /workspace/hello.txt)
assert_eq "$patched" "hello world" "patch did not apply"

log "Timeout kills long-running exec"
set +e
docker exec "$CONTAINER" bash -lc '
python - <<'"'"'PY'"'"'
import subprocess, sys
p = subprocess.Popen(["sleep", "5"])
try:
    p.wait(timeout=1)
except subprocess.TimeoutExpired:
    p.kill()
    p.wait()
    sys.exit(124)
sys.exit(p.returncode)
PY
'
to_status=$?
set -e
assert_eq "$to_status" 124 "timeout enforcement failed"
docker exec "$CONTAINER" pgrep -f "sleep 5" >/dev/null 2>&1 && fail "sleep process still running after timeout"

log "Stopping container cleanly"
docker stop "$CONTAINER" >/dev/null

log "All checks passed"
