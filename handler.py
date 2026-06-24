import os
import sys

# Worker deps live in an isolated folder so they do not collide with InvokeAI's
# own packages. Add it to this process only. The invokeai-web subprocess does
# not inherit it and keeps using the /opt/venv environment.
sys.path.insert(0, os.environ.get("HANDLER_DEPS", "/opt/handler-deps"))

import base64
import subprocess
import time

import requests
import runpod

INVOKEAI_HOST = os.environ.get("INVOKEAI_HOST", "127.0.0.1")
INVOKEAI_PORT = int(os.environ.get("INVOKEAI_PORT", "9090"))
BASE = f"http://{INVOKEAI_HOST}:{INVOKEAI_PORT}"
QUEUE_ID = os.environ.get("INVOKEAI_QUEUE_ID", "default")

BOOT_TIMEOUT = int(os.environ.get("INVOKEAI_BOOT_TIMEOUT", "600"))
JOB_TIMEOUT = int(os.environ.get("INVOKEAI_JOB_TIMEOUT", "600"))
POLL_INTERVAL = float(os.environ.get("INVOKEAI_POLL_INTERVAL", "1.0"))

_server = None


def _server_up():
    try:
        return requests.get(f"{BASE}/api/v1/app/version", timeout=5).status_code == 200
    except requests.RequestException:
        return False


def start_invokeai():
    """Boot invokeai-web once per worker and block until the API answers."""
    global _server
    if _server_up():
        return
    if _server is None:
        _server = subprocess.Popen(
            ["invokeai-web", "--host", INVOKEAI_HOST, "--port", str(INVOKEAI_PORT)]
        )
    deadline = time.time() + BOOT_TIMEOUT
    while time.time() < deadline:
        if _server_up():
            return
        if _server.poll() is not None:
            raise RuntimeError("invokeai-web exited during startup")
        time.sleep(2)
    raise RuntimeError(f"invokeai-web not ready within {BOOT_TIMEOUT}s")


def version():
    r = requests.get(f"{BASE}/api/v1/app/version", timeout=10)
    r.raise_for_status()
    return r.json().get("version")


def collect_image_names(session):
    names = []
    for out in (session or {}).get("results", {}).values():
        if isinstance(out, dict):
            img = out.get("image")
            if isinstance(img, dict) and img.get("image_name"):
                names.append(img["image_name"])
    return names


def fetch_image_b64(image_name):
    r = requests.get(f"{BASE}/api/v1/images/i/{image_name}/full", timeout=60)
    r.raise_for_status()
    return base64.b64encode(r.content).decode("utf-8")


def run_batch(batch):
    enq = requests.post(
        f"{BASE}/api/v1/queue/{QUEUE_ID}/enqueue_batch",
        json={"batch": batch},
        timeout=30,
    )
    if enq.status_code not in (200, 201):
        return {"error": "enqueue failed", "status_code": enq.status_code, "detail": enq.text[:1000]}

    item_ids = enq.json().get("item_ids", [])
    if not item_ids:
        return {"error": "no queue items enqueued", "detail": enq.json()}

    image_names = []
    deadline = time.time() + JOB_TIMEOUT
    for item_id in item_ids:
        while True:
            if time.time() > deadline:
                return {"error": "timeout waiting for generation", "item_ids": item_ids}
            item = requests.get(f"{BASE}/api/v1/queue/{QUEUE_ID}/i/{item_id}", timeout=15)
            item.raise_for_status()
            body = item.json()
            status = body.get("status")
            if status == "completed":
                image_names.extend(collect_image_names(body.get("session")))
                break
            if status in ("failed", "canceled"):
                return {
                    "error": f"generation {status}",
                    "item_id": item_id,
                    "error_type": body.get("error_type"),
                    "error_message": body.get("error_message"),
                }
            time.sleep(POLL_INTERVAL)

    return {
        "status": "completed",
        "item_ids": item_ids,
        "image_names": image_names,
        "images": [fetch_image_b64(n) for n in image_names],
    }


def handler(job):
    data = job.get("input") or {}
    start_invokeai()

    batch = data.get("batch")
    graph = data.get("graph")

    if not batch and not graph:
        return {
            "ok": True,
            "invokeai_version": version(),
            "note": "Send 'graph' or a full 'batch' to generate. Models must be installed under INVOKEAI_ROOT.",
        }

    if not batch:
        batch = {"graph": graph, "runs": 1}

    return run_batch(batch)


runpod.serverless.start({"handler": handler})
