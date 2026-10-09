"""Idempotent Garage bootstrap through the admin API v2 (stdlib only).

Steps (safe to re-run):
  1. Wait for the admin API.
  2. Assign a layout role to the single node and apply the layout (only if missing).
  3. Import the access keys stored in the Kubernetes Secret (only if missing).
  4. Create the buckets (only if missing) and grant read/write/owner to their key.

Environment:
  GARAGE_ADMIN_URL, GARAGE_ADMIN_TOKEN, GARAGE_ZONE, GARAGE_CAPACITY_BYTES
  BUCKETS: comma-separated "bucket:KEY_ENV_PREFIX" pairs, e.g.
           "clear-helper-docs:APP,langfuse:LANGFUSE" -> reads APP_ACCESS_KEY_ID,
           APP_SECRET_ACCESS_KEY, LANGFUSE_ACCESS_KEY_ID, ...
"""

from __future__ import annotations

import json
import os
import re
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from typing import Any

ADMIN_URL = os.environ["GARAGE_ADMIN_URL"].rstrip("/")
TOKEN = os.environ["GARAGE_ADMIN_TOKEN"]
ZONE = os.environ.get("GARAGE_ZONE", "dc1")
CAPACITY = int(os.environ["GARAGE_CAPACITY_BYTES"])

KEY_ID_RE = re.compile(r"^GK[0-9a-f]{24}$")
SECRET_RE = re.compile(r"^[0-9a-f]{64}$")


class ApiError(Exception):
    def __init__(self, status: int, body: str) -> None:
        super().__init__(f"HTTP {status}: {body}")
        self.status = status


def call(method: str, path: str, body: dict[str, Any] | None = None,
         query: dict[str, str] | None = None) -> Any:
    url = f"{ADMIN_URL}{path}"
    if query:
        url += "?" + urllib.parse.urlencode(query)
    data = json.dumps(body).encode() if body is not None else None
    req = urllib.request.Request(url, data=data, method=method)  # noqa: S310
    req.add_header("Authorization", f"Bearer {TOKEN}")
    if data is not None:
        req.add_header("Content-Type", "application/json")
    try:
        with urllib.request.urlopen(req, timeout=15) as resp:  # noqa: S310
            raw = resp.read().decode()
            return json.loads(raw) if raw else None
    except urllib.error.HTTPError as exc:
        raise ApiError(exc.code, exc.read().decode(errors="replace")) from exc


def log(msg: str) -> None:
    print(f"[garage-bootstrap] {msg}", flush=True)


def wait_for_api(timeout: int = 600) -> dict[str, Any]:
    deadline = time.monotonic() + timeout
    while True:
        try:
            return call("GET", "/v2/GetClusterStatus")
        except (ApiError, urllib.error.URLError, OSError) as exc:
            if time.monotonic() > deadline:
                raise
            log(f"admin API not ready yet ({exc}); retrying in 5s")
            time.sleep(5)


def ensure_layout(status: dict[str, Any]) -> None:
    nodes = status.get("nodes") or []
    if not nodes:
        raise RuntimeError("no Garage node reported by GetClusterStatus")
    node_id = nodes[0]["id"]
    layout = call("GET", "/v2/GetClusterLayout")
    if any(role.get("id") == node_id for role in layout.get("roles") or []):
        log(f"layout already contains node {node_id[:16]} (version {layout['version']})")
        return
    log(f"assigning node {node_id[:16]} zone={ZONE} capacity={CAPACITY}")
    call("POST", "/v2/UpdateClusterLayout", {
        "roles": [{"id": node_id, "zone": ZONE, "capacity": CAPACITY, "tags": []}],
    })
    new_version = int(layout["version"]) + 1
    call("POST", "/v2/ApplyClusterLayout", {"version": new_version})
    log(f"layout applied (version {new_version})")


def ensure_key(prefix: str, name: str) -> str:
    key_id = os.environ[f"{prefix}_ACCESS_KEY_ID"].strip()
    secret = os.environ[f"{prefix}_SECRET_ACCESS_KEY"].strip()
    if not KEY_ID_RE.match(key_id) or not SECRET_RE.match(secret):
        raise RuntimeError(
            f"{prefix}: access key must match GK + 24 hex chars and secret 64 hex chars"
        )
    try:
        call("GET", "/v2/GetKeyInfo", query={"id": key_id})
        log(f"key {name} ({key_id}) already exists")
    except ApiError as exc:
        if exc.status not in (400, 404):
            raise
        call("POST", "/v2/ImportKey",
             {"accessKeyId": key_id, "secretAccessKey": secret, "name": name})
        log(f"key {name} ({key_id}) imported")
    return key_id


def ensure_bucket(bucket: str, key_id: str) -> None:
    try:
        info = call("GET", "/v2/GetBucketInfo", query={"globalAlias": bucket})
        log(f"bucket {bucket} already exists")
    except ApiError as exc:
        if exc.status not in (400, 404):
            raise
        info = call("POST", "/v2/CreateBucket", {"globalAlias": bucket})
        log(f"bucket {bucket} created")
    call("POST", "/v2/AllowBucketKey", {
        "bucketId": info["id"],
        "accessKeyId": key_id,
        "permissions": {"read": True, "write": True, "owner": True},
    })
    log(f"key {key_id} granted read/write/owner on {bucket}")


def main() -> int:
    status = wait_for_api()
    ensure_layout(status)
    for pair in filter(None, (p.strip() for p in os.environ.get("BUCKETS", "").split(","))):
        bucket, prefix = pair.split(":", 1)
        key_id = ensure_key(prefix, f"{bucket}-key")
        ensure_bucket(bucket, key_id)
    log("done")
    return 0


if __name__ == "__main__":
    sys.exit(main())
