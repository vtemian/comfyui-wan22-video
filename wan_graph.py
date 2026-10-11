"""Load the silent text-to-video graph and apply one job to it.

Nodes are addressed by _meta.title. A graph edit that only renames an id used to
leave jobs running on the file's stale defaults.
"""

from __future__ import annotations

import copy
import json
import os
from pathlib import Path
from typing import cast

from wan_job import SAMPLE_FPS, JobSpec

TITLE_PROMPT = "Prompt"
TITLE_NEGATIVE = "Negative prompt"
TITLE_LATENT = "Latent"
TITLE_SAVE_RESIZE = "Save resize"
TITLE_DECODE = "Decode"
TITLE_ASSEMBLE = "Assemble"
TITLE_SAVE = "Save"
SAMPLER_TITLES = ("Sampler high noise", "Sampler low noise")
LORA_TITLES = ("Lightning LoRA high noise", "Lightning LoRA low noise")
FILENAME_PREFIX = "video"
MUSIC_TITLE_PREFIX = "Music"
AUDIO_CLASS_MARKS = ("AceStep", "MMAudio", "VAEDecodeAudio")

_WORKFLOW_CACHE: dict[str, dict[str, object]] = {}


def workflow_path() -> str:
    override = os.environ.get("COMFY_WORKFLOW", "").strip()
    if override:
        return override
    return str(Path(__file__).with_name("workflows") / "wan22_t2v.json")


def build_graph(spec: JobSpec) -> dict[str, object]:
    graph = load_workflow(workflow_path())
    drop_audio_nodes(graph)
    apply_prompt(graph, spec)
    apply_size(graph, spec)
    apply_seed(graph, spec)
    apply_loras(graph, spec)
    apply_filename(graph)
    if spec.rife:
        return graph
    bypass_interpolation(graph)
    return graph


def load_workflow(path: str) -> dict[str, object]:
    cached = _WORKFLOW_CACHE.get(path)
    if cached is None:
        cached = _read_workflow(path)
        _WORKFLOW_CACHE[path] = cached
    return copy.deepcopy(cached)


def drop_audio_nodes(graph: dict[str, object]) -> dict[str, object]:
    """Remove audio branches before submit.

    MMAudio weights are CC-BY-NC and are not downloaded. A graph that still names
    an audio node would otherwise fetch or load them inside a public template.
    """
    removable = [node_id for node_id, node in graph.items() if is_audio_node(node)]
    for node_id in removable:
        del graph[node_id]
    for node in graph.values():
        _pop_audio_input(node)
    return graph


def is_audio_node(node: object) -> bool:
    if not isinstance(node, dict):
        return False
    if _title_of(node).startswith(MUSIC_TITLE_PREFIX):
        return True
    class_type = str(node.get("class_type", ""))
    return any(mark in class_type for mark in AUDIO_CLASS_MARKS)


def apply_prompt(graph: dict[str, object], spec: JobSpec) -> None:
    node_inputs(graph, TITLE_PROMPT)["text"] = spec.prompt
    if spec.negative is None:
        return
    node_inputs(graph, TITLE_NEGATIVE)["text"] = spec.negative


def apply_size(graph: dict[str, object], spec: JobSpec) -> None:
    latent = node_inputs(graph, TITLE_LATENT)
    latent["width"] = spec.width
    latent["height"] = spec.height
    latent["length"] = spec.frames
    resize = node_inputs(graph, TITLE_SAVE_RESIZE)
    resize["width"] = spec.width
    resize["height"] = spec.height


def apply_seed(graph: dict[str, object], spec: JobSpec) -> None:
    # Both experts denoise one trajectory. A second seed would restart the noise mid-schedule.
    for title in SAMPLER_TITLES:
        node_inputs(graph, title)["noise_seed"] = spec.seed


def apply_loras(graph: dict[str, object], spec: JobSpec) -> None:
    names = (spec.lora_high, spec.lora_low)
    for title, name in zip(LORA_TITLES, names, strict=True):
        node_inputs(graph, title)["lora_name"] = name


def apply_filename(graph: dict[str, object]) -> None:
    node_inputs(graph, TITLE_SAVE)["filename_prefix"] = FILENAME_PREFIX


def bypass_interpolation(graph: dict[str, object]) -> None:
    """Take interpolation off the video path and encode at the sample rate.

    The resize stays in the path. Pointing the assembler at the decoder would
    also skip the resize.
    """
    resize = node_inputs(graph, TITLE_SAVE_RESIZE)
    resize["image"] = [node_key(graph, TITLE_DECODE), 0]
    node_inputs(graph, TITLE_ASSEMBLE)["fps"] = SAMPLE_FPS


def node_inputs(graph: dict[str, object], title: str) -> dict[str, object]:
    inputs = find_node(graph, title).get("inputs")
    if isinstance(inputs, dict):
        return cast("dict[str, object]", inputs)
    raise KeyError(title)


def find_node(graph: dict[str, object], title: str) -> dict[str, object]:
    matches = [node for node in graph.values() if _is_titled(node, title)]
    if not matches:
        raise KeyError(title)
    node = matches[0]
    if isinstance(node, dict):
        return node
    raise KeyError(title)


def node_key(graph: dict[str, object], title: str) -> str:
    matches = [key for key, node in graph.items() if _is_titled(node, title)]
    if not matches:
        raise KeyError(title)
    return str(matches[0])


def _read_workflow(path: str) -> dict[str, object]:
    loaded = json.loads(Path(path).read_text(encoding="utf-8"))
    if not isinstance(loaded, dict):
        raise TypeError("Workflow must be a JSON object")
    return {str(key): value for key, value in loaded.items()}


def _pop_audio_input(node: object) -> None:
    if not isinstance(node, dict):
        return
    inputs = node.get("inputs")
    if not isinstance(inputs, dict):
        return
    inputs.pop("audio", None)


def _is_titled(node: object, title: str) -> bool:
    return isinstance(node, dict) and _title_of(node) == title


def _title_of(node: dict[str, object]) -> str:
    meta = node.get("_meta")
    if not isinstance(meta, dict):
        return ""
    title = meta.get("title")
    if isinstance(title, str):
        return title
    return ""
