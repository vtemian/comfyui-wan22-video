"""RunPod serverless entrypoint for silent text-to-video.

Raises on failure so RunPod reports the job FAILED. Heavy clients (boto3, runpod)
are imported inside the functions that need them.
"""

from __future__ import annotations

import logging
import re
import time
import uuid

import wan_comfy
import wan_delivery
import wan_graph
import wan_job
import wan_mp4

logger = logging.getLogger(__name__)

_KEY_CHARS = re.compile(r"[^A-Za-z0-9_-]")
_JOB_ID_LENGTH = 80


def handler(job: dict[str, object]) -> dict[str, object]:
    spec = wan_job.build_spec(_job_input(job))
    wan_delivery.ensure_delivery()
    encoded, generation_seconds = render_clip(spec)
    wan_mp4.require_no_audio_stream(encoded)
    return wan_delivery.build_response(spec, encoded, generation_seconds, _job_id(job))


def render_clip(spec: wan_job.JobSpec) -> tuple[bytes, float]:
    logger.info("Generating %sx%s, seed %s, rife %s", spec.width, spec.height, spec.seed, spec.rife)
    wan_comfy.await_server()
    started = time.perf_counter()
    prompt_id = wan_comfy.submit(wan_graph.build_graph(spec))
    encoded = wan_comfy.fetch_output(wan_comfy.await_result(prompt_id))
    return encoded, round(time.perf_counter() - started, 2)


def _job_input(job: dict[str, object]) -> dict[str, object]:
    raw = job.get("input")
    if isinstance(raw, dict):
        return {str(key): value for key, value in raw.items()}
    raise ValueError("Job input must be an object")


def _job_id(job: dict[str, object]) -> str:
    raw = job.get("id")
    if not isinstance(raw, str):
        return str(uuid.uuid4())
    cleaned = _KEY_CHARS.sub("", raw.strip())[:_JOB_ID_LENGTH]
    if cleaned:
        return cleaned
    return str(uuid.uuid4())


def main() -> None:
    import runpod.serverless

    logging.basicConfig(level=logging.INFO)
    runpod.serverless.start({"handler": handler})


if __name__ == "__main__":
    main()
