"""Return the mp4 inline, and upload it only when S3 env vars are complete.

No endpoint, bucket, or public URL is assumed. A partial S3 configuration is an error
so a job cannot look successful while the file never left the worker.
"""

from __future__ import annotations

import base64
import io
import os

from wan_job import JobSpec, env_flag

S3_KEYS = ("S3_ENDPOINT_URL", "S3_BUCKET_NAME", "S3_ACCESS_KEY_ID", "S3_SECRET_ACCESS_KEY")
VIDEO_CONTENT_TYPE = "video/mp4"
OUTPUT_FPS = 32
SAMPLE_FPS = 16


def ensure_delivery() -> None:
    # s3_settings raises on a partial configuration before any GPU work.
    settings = s3_settings()
    if env_flag("RETURN_BASE64", "1") or settings is not None:
        return
    raise ValueError("RETURN_BASE64 is off and S3 is not configured")


def build_response(spec: JobSpec, encoded: bytes, generation_seconds: float, job_id: str) -> dict[str, object]:
    body = _metadata(spec, generation_seconds)
    video_url = maybe_video_url(encoded, f"{job_id}.mp4")
    if video_url is not None:
        body["video_url"] = video_url
    if env_flag("RETURN_BASE64", "1"):
        body["video_base64"] = base64.b64encode(encoded).decode("ascii")
    return body


def maybe_video_url(encoded: bytes, key: str) -> str | None:
    settings = s3_settings()
    if settings is None:
        return None
    _upload(encoded, key, settings)
    return public_url(key, settings)


def s3_settings() -> dict[str, str] | None:
    values = {key: os.environ.get(key, "").strip() for key in S3_KEYS}
    present = [key for key, value in values.items() if value]
    if not present:
        return None
    if len(present) == len(S3_KEYS):
        return values
    missing = [key for key in S3_KEYS if not values[key]]
    raise ValueError(f"Incomplete S3 configuration, missing {', '.join(missing)}")


def public_url(key: str, settings: dict[str, str]) -> str:
    base = os.environ.get("S3_PUBLIC_URL", "").strip().rstrip("/")
    if base:
        return f"{base}/{key}"
    endpoint = settings["S3_ENDPOINT_URL"].rstrip("/")
    bucket = settings["S3_BUCKET_NAME"]
    return f"{endpoint}/{bucket}/{key}"


def _metadata(spec: JobSpec, generation_seconds: float) -> dict[str, object]:
    return {
        "content_type": VIDEO_CONTENT_TYPE,
        "width": spec.width,
        "height": spec.height,
        "fps": OUTPUT_FPS if spec.rife else SAMPLE_FPS,
        "seed": spec.seed,
        "duration_seconds": spec.duration_seconds,
        "generation_seconds": generation_seconds,
    }


def _upload(encoded: bytes, key: str, settings: dict[str, str]) -> None:
    # Imported here so unit tests can load the module with only pytest installed.
    import boto3

    client = boto3.client(
        "s3",
        aws_access_key_id=settings["S3_ACCESS_KEY_ID"],
        aws_secret_access_key=settings["S3_SECRET_ACCESS_KEY"],
        endpoint_url=settings["S3_ENDPOINT_URL"],
        region_name=os.environ.get("S3_REGION", "us-east-1"),
    )
    client.upload_fileobj(
        io.BytesIO(encoded),
        settings["S3_BUCKET_NAME"],
        key,
        ExtraArgs={"ContentType": VIDEO_CONTENT_TYPE},
    )
