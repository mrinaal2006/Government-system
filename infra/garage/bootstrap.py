"""Idempotent Garage bootstrap: cluster layout, application key and private bucket.

Runs once per `docker compose up` (service storage-init). Uses only the standard
library and Garage's admin API v2. The application key receives read/write on the
bucket only; the bucket has no website or public access configured.
"""

import json
import os
import sys
import time
import urllib.error
import urllib.request

ADMIN = os.environ.get("GARAGE_ADMIN_URL", "http://storage:3903")
TOKEN = os.environ["GARAGE_ADMIN_TOKEN"]
KEY_ID = os.environ["STORAGE_ACCESS_KEY"]
SECRET = os.environ["STORAGE_SECRET_KEY"]
BUCKET = os.environ.get("STORAGE_BUCKET", "dgimews-files")


def call(endpoint, body=None, query=""):
    req = urllib.request.Request(
        f"{ADMIN}/v2/{endpoint}{query}",
        data=json.dumps(body).encode() if body is not None else None,
        headers={"Authorization": f"Bearer {TOKEN}", "Content-Type": "application/json"},
        method="POST" if body is not None else "GET",
    )
    with urllib.request.urlopen(req, timeout=10) as resp:
        raw = resp.read()
        return json.loads(raw) if raw else None


def wait():
    for _ in range(60):
        try:
            return call("GetClusterStatus")
        except (urllib.error.URLError, ConnectionError, TimeoutError):
            time.sleep(1)
    sys.exit("Garage admin API did not become available")


status = wait()
node = status["nodes"][0]
if not node.get("role"):
    call("UpdateClusterLayout", {"roles": [{"id": node["id"], "zone": "dc1", "capacity": 100 * 1024**3, "tags": []}]})
    layout = call("GetClusterLayout")
    call("ApplyClusterLayout", {"version": layout["version"] + 1})
    print("layout applied")

try:
    call("GetKeyInfo", query=f"?id={KEY_ID}")
except urllib.error.HTTPError:
    call("ImportKey", {"accessKeyId": KEY_ID, "secretAccessKey": SECRET, "name": "dgimews-app"})
    print("application key imported")

try:
    bucket = call("GetBucketInfo", query=f"?globalAlias={BUCKET}")
except urllib.error.HTTPError:
    bucket = call("CreateBucket", {"globalAlias": BUCKET})
    print("bucket created")

call("AllowBucketKey", {"bucketId": bucket["id"], "accessKeyId": KEY_ID,
                        "permissions": {"read": True, "write": True, "owner": False}})
print("storage ready")
