"""Job validation for the public text-to-video worker.

Sampling sizes are the four Wan 2.2 T2V A14B publishes. Other stride-16 sizes still
decode and still look wrong, so they are rejected here rather than sent to the model.
"""

from __future__ import annotations

import os
import random
from dataclasses import dataclass

SAMPLE_FPS = 16
DEFAULT_WIDTH = 480
DEFAULT_HEIGHT = 832
DEFAULT_DURATION = 5
DEFAULT_MAX_DURATION = 5
MIN_DURATION_SECONDS = 1
MAX_PROMPT_CHARS = 4000
SEED_MODULUS = 2**32
DEFAULT_LORA_HIGH = "wan2.2_t2v_lightx2v_4steps_lora_v1.1_high_noise.safetensors"
DEFAULT_LORA_LOW = "wan2.2_t2v_lightx2v_4steps_lora_v1.1_low_noise.safetensors"

# wan/configs SUPPORTED_SIZES for t2v-A14B. 704-tall sizes belong to the 5B model.
SUPPORTED_SIZES = frozenset({(480, 832), (832, 480), (720, 1280), (1280, 720)})
_TRUE_VALUES = frozenset({"1", "true", "yes"})


@dataclass(frozen=True)
class JobSpec:
    prompt: str
    negative: str | None
    width: int
    height: int
    frames: int
    seed: int
    duration_seconds: int
    lora_high: str
    lora_low: str
    rife: bool


def env_flag(name: str, default: str) -> bool:
    return os.environ.get(name, default).strip().lower() in _TRUE_VALUES


def build_spec(job_input: dict[str, object]) -> JobSpec:
    width, height = require_size(job_input)
    duration = require_duration(job_input.get("duration_seconds", DEFAULT_DURATION))
    return JobSpec(
        prompt=require_prompt(job_input),
        negative=resolve_negative(job_input),
        width=width,
        height=height,
        frames=frame_count(duration),
        seed=resolve_seed(job_input.get("seed")),
        duration_seconds=duration,
        lora_high=_lora_name("COMFY_LORA_HIGH", DEFAULT_LORA_HIGH),
        lora_low=_lora_name("COMFY_LORA_LOW", DEFAULT_LORA_LOW),
        rife=env_flag("COMFY_RIFE", "1"),
    )


def frame_count(duration_seconds: int) -> int:
    """Wan samples duration*16+1 frames.

    The VAE requires a frame count that is 1 mod 4. 16fps keeps that for every whole second.
    """
    return duration_seconds * SAMPLE_FPS + 1


def require_prompt(job_input: dict[str, object]) -> str:
    prompt = _prompt_text(job_input.get("prompt"))
    if len(prompt) > MAX_PROMPT_CHARS:
        raise ValueError("prompt is too long")
    return prompt


def resolve_negative(job_input: dict[str, object]) -> str | None:
    """None leaves the workflow's own negative prompt in place."""
    if "negative_prompt" not in job_input:
        return None
    negative = job_input["negative_prompt"]
    if not isinstance(negative, str):
        raise TypeError("negative_prompt must be a string")
    return negative


def require_size(job_input: dict[str, object]) -> tuple[int, int]:
    width = require_int(job_input.get("width", DEFAULT_WIDTH), "width")
    height = require_int(job_input.get("height", DEFAULT_HEIGHT), "height")
    if (width, height) in SUPPORTED_SIZES:
        return width, height
    choices = ", ".join(f"{pair[0]}x{pair[1]}" for pair in sorted(SUPPORTED_SIZES))
    raise ValueError(f"Unsupported size {width}x{height}. Supported: {choices}")


def require_duration(value: object) -> int:
    duration = require_int(value, "duration_seconds")
    limit = max_duration_seconds()
    if duration < MIN_DURATION_SECONDS or duration > limit:
        raise ValueError(f"duration_seconds must be {MIN_DURATION_SECONDS}..{limit}")
    return duration


def max_duration_seconds() -> int:
    raw = os.environ.get("MAX_DURATION_SECONDS", str(DEFAULT_MAX_DURATION))
    return require_int(raw, "MAX_DURATION_SECONDS")


def resolve_seed(value: object) -> int:
    if value is None:
        return random.randint(0, SEED_MODULUS - 1)
    seed = require_int(value, "seed")
    if seed < 0 or seed >= SEED_MODULUS:
        raise ValueError("seed must fit in an unsigned 32-bit integer")
    return seed


def require_int(value: object, name: str) -> int:
    if isinstance(value, bool) or not isinstance(value, (int, str)):
        raise TypeError(f"{name} must be an integer")
    return _parse_int(value, name)


def _parse_int(value: int | str, name: str) -> int:
    try:
        return int(value)
    except ValueError as error:
        raise ValueError(f"{name} must be an integer") from error


def _prompt_text(raw: object) -> str:
    if not isinstance(raw, str):
        raise TypeError("Missing required 'prompt' input")
    prompt = raw.strip()
    if not prompt:
        raise ValueError("Missing required 'prompt' input")
    return prompt


def _lora_name(env_name: str, default: str) -> str:
    value = os.environ.get(env_name, "").strip()
    if value:
        return value
    return default
