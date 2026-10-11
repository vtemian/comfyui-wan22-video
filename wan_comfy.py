"""Drive a local ComfyUI over HTTP. Stdlib only, so unit tests import this without torch."""

from __future__ import annotations

import json
import os
import time
import urllib.error
import urllib.parse
import urllib.request
import uuid
from pathlib import Path

from wan_job import require_int

POLL_INTERVAL_SECONDS = 1
SERVER_WAIT_INTERVAL_SECONDS = 2
DEFAULT_HOST = "127.0.0.1:8188"
DEFAULT_TIMEOUT_SECONDS = "1500"
DEFAULT_REQUEST_TIMEOUT_SECONDS = "120"
DEFAULT_SERVER_WAIT_ATTEMPTS = "180"
DEFAULT_OUTPUT_DIR = "/comfyui/output"


def await_server() -> None:
    """Block until ComfyUI answers.

    The base image backgrounds ComfyUI and execs the handler immediately, so the first
    job on a cold worker races a process that is still importing torch.
    """
    if _server_answered():
        return
    attempts = server_wait_attempts()
    raise RuntimeError(f"ComfyUI at {comfy_host()} did not answer after {attempts} attempts")


def submit(graph: dict[str, object]) -> str:
    payload = json.dumps({"prompt": graph, "client_id": str(uuid.uuid4())}).encode("utf-8")
    body = _post_json("/prompt", payload)
    prompt_id = body.get("prompt_id")
    if not isinstance(prompt_id, str) or not prompt_id:
        raise RuntimeError("ComfyUI did not return a prompt_id")
    return prompt_id


def await_result(prompt_id: str) -> dict[str, object]:
    deadline = time.monotonic() + timeout_seconds()
    entry = _poll_until(prompt_id, deadline)
    if entry is None:
        raise TimeoutError(f"ComfyUI did not finish {prompt_id} within {timeout_seconds()}s")
    return _finished_entry(entry, prompt_id)


def fetch_output(entry: dict[str, object]) -> bytes:
    """Bytes of the file SaveVideo wrote.

    SaveVideo reports through PreviewVideo, so the file lands under `images`.
    Entries typed "temp" are previews ComfyUI deletes.
    """
    saved = _saved_images(entry)
    if not saved:
        raise RuntimeError("ComfyUI reported no saved output")
    encoded = _download(saved[0])
    _discard(saved[0])
    return encoded


def comfy_host() -> str:
    return os.environ.get("COMFY_HOST", DEFAULT_HOST)


def timeout_seconds() -> int:
    return require_int(os.environ.get("COMFY_TIMEOUT_SECONDS", DEFAULT_TIMEOUT_SECONDS), "COMFY_TIMEOUT_SECONDS")


def request_timeout_seconds() -> int:
    raw = os.environ.get("COMFY_REQUEST_TIMEOUT_SECONDS", DEFAULT_REQUEST_TIMEOUT_SECONDS)
    return require_int(raw, "COMFY_REQUEST_TIMEOUT_SECONDS")


def server_wait_attempts() -> int:
    raw = os.environ.get("COMFY_SERVER_WAIT_ATTEMPTS", DEFAULT_SERVER_WAIT_ATTEMPTS)
    return require_int(raw, "COMFY_SERVER_WAIT_ATTEMPTS")


def _server_answered() -> bool:
    answered = False
    attempt = 0
    while not answered and attempt < server_wait_attempts():
        answered = _probe_or_wait(attempt)
        attempt += 1
    return answered


def _probe_or_wait(attempt: int) -> bool:
    if _probe_server():
        return True
    if attempt < server_wait_attempts() - 1:
        time.sleep(SERVER_WAIT_INTERVAL_SECONDS)
    return False


def _probe_server() -> bool:
    try:
        _get_json("/system_stats", timeout=SERVER_WAIT_INTERVAL_SECONDS)
    except (urllib.error.URLError, OSError, ValueError):
        return False
    return True


def _poll_until(prompt_id: str, deadline: float) -> dict[str, object] | None:
    found: dict[str, object] | None = None
    while found is None and time.monotonic() < deadline:
        found = _history_or_pause(prompt_id)
    return found


def _history_or_pause(prompt_id: str) -> dict[str, object] | None:
    found = _history_entry(prompt_id)
    if found is not None:
        return found
    time.sleep(POLL_INTERVAL_SECONDS)
    return None


def _history_entry(prompt_id: str) -> dict[str, object] | None:
    history = _get_json(f"/history/{prompt_id}")
    entry = history.get(prompt_id)
    if isinstance(entry, dict):
        return {str(key): value for key, value in entry.items()}
    return None


def _finished_entry(entry: dict[str, object], prompt_id: str) -> dict[str, object]:
    status = entry.get("status")
    if not isinstance(status, dict):
        return entry
    if status.get("status_str") != "error":
        return entry
    raise RuntimeError(f"ComfyUI failed {prompt_id}: {status.get('messages')}")


def _saved_images(entry: dict[str, object]) -> list[dict[str, object]]:
    outputs = entry.get("outputs")
    if not isinstance(outputs, dict):
        return []
    saved: list[dict[str, object]] = []
    for output in outputs.values():
        saved.extend(_output_images(output))
    return saved


def _output_images(output: object) -> list[dict[str, object]]:
    if not isinstance(output, dict):
        return []
    images = output.get("images")
    if not isinstance(images, list):
        return []
    return [item for item in images if _kept_image(item)]


def _kept_image(item: object) -> bool:
    return isinstance(item, dict) and item.get("type") != "temp"


def _download(item: dict[str, object]) -> bytes:
    query = urllib.parse.urlencode(
        {
            "filename": str(item.get("filename", "")),
            "subfolder": str(item.get("subfolder", "")),
            "type": str(item.get("type", "output")),
        }
    )
    request = urllib.request.Request(f"http://{comfy_host()}/view?{query}")
    return _read_bytes(request)


def _discard(item: dict[str, object]) -> None:
    """Delete SaveVideo's file so a warm worker does not fill its disk. Never fatal."""
    path = _output_path(item)
    if path is None:
        return
    path.unlink(missing_ok=True)


def _output_path(item: dict[str, object]) -> Path | None:
    filename = item.get("filename")
    if not isinstance(filename, str) or not filename:
        return None
    subfolder = item.get("subfolder")
    if not isinstance(subfolder, str):
        subfolder = ""
    root = Path(os.environ.get("COMFY_OUTPUT_DIR", DEFAULT_OUTPUT_DIR)).resolve()
    path = (root / subfolder / filename).resolve()
    if root not in path.parents:
        return None
    return path


def _post_json(path: str, payload: bytes) -> dict[str, object]:
    request = urllib.request.Request(
        f"http://{comfy_host()}{path}",
        data=payload,
        headers={"Content-Type": "application/json"},
    )
    try:
        return _read_json(request, timeout=request_timeout_seconds())
    except urllib.error.HTTPError as error:
        detail = error.read().decode("utf-8", errors="replace")
        raise RuntimeError(f"ComfyUI rejected the prompt: {detail}") from error


def _get_json(path: str, timeout: float | None = None) -> dict[str, object]:
    request = urllib.request.Request(f"http://{comfy_host()}{path}")
    return _read_json(request, timeout=request_timeout_seconds() if timeout is None else timeout)


def _read_json(request: urllib.request.Request, timeout: float) -> dict[str, object]:
    loaded = json.loads(_read_bytes(request, timeout))
    if not isinstance(loaded, dict):
        raise TypeError("ComfyUI returned a non-object JSON body")
    return {str(key): value for key, value in loaded.items()}


def _read_bytes(request: urllib.request.Request, timeout: float | None = None) -> bytes:
    if timeout is None:
        timeout = request_timeout_seconds()
    with urllib.request.urlopen(request, timeout=timeout) as response:  # noqa: S310
        return response.read()
