import base64
import json
import os
import shutil
import subprocess
import sys
import types
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

import handler  # noqa: E402
import wan_delivery  # noqa: E402
import wan_graph  # noqa: E402
import wan_job  # noqa: E402
import wan_mp4  # noqa: E402

BASH = shutil.which("bash")

BOX_HEADER = 8
# Split so this file does not itself contain the private strings it scans for.
FORBIDDEN = (
    "public." + "sis" + "if.ai",
    "sis" + "if.ai",
    "tmnojr" + "vn2mm4xa",
    "w1fcdy" + "t788",
    "ghcr.io/" + "vtemian",
)
S3_ENV = ("S3_ENDPOINT_URL", "S3_BUCKET_NAME", "S3_ACCESS_KEY_ID", "S3_SECRET_ACCESS_KEY", "S3_PUBLIC_URL")


def _box(box_type: bytes, payload: bytes) -> bytes:
    return (BOX_HEADER + len(payload)).to_bytes(4, "big") + box_type + payload


def _hdlr_payload(handler_type: bytes) -> bytes:
    return b"\x00\x00\x00\x00" + b"\x00\x00\x00\x00" + handler_type + (b"\x00" * 12) + b"\x00"


def _trak(handler_type: bytes) -> bytes:
    return _box(b"trak", _box(b"mdia", _box(b"hdlr", _hdlr_payload(handler_type))))


def _mp4(*handler_types: bytes) -> bytes:
    tracks = b"".join(_trak(handler_type) for handler_type in handler_types)
    ftyp = _box(b"ftyp", b"isom" + (1).to_bytes(4, "big") + b"isom")
    return ftyp + _box(b"moov", tracks)


SILENT_MP4 = _mp4(b"vide")
SOUND_MP4 = _mp4(b"vide", b"soun")


def _clear_s3(monkeypatch):
    for key in S3_ENV:
        monkeypatch.delenv(key, raising=False)


def _run_bash(*args: str, **kwargs: object) -> subprocess.CompletedProcess[str]:
    if BASH is None:
        raise RuntimeError("bash is not installed")
    return subprocess.run([BASH, *args], check=False, **kwargs)  # noqa: S603


def test_package_has_no_private_endpoints():
    files = [path for path in ROOT.rglob("*") if path.is_file() and "__pycache__" not in path.parts]
    offenders = [
        f"{path.relative_to(ROOT)}: {needle}"
        for path in files
        for needle in FORBIDDEN
        if needle in path.read_text(encoding="utf-8", errors="replace").lower()
    ]
    assert offenders == []


def test_readme_carries_the_referral_link_and_the_publishing_docs():
    readme = (ROOT / "README.md").read_text(encoding="utf-8")
    assert "https://runpod.io?ref=d7ed2jfg" in readme
    assert "Referral link: we get RunPod credit if you sign up." in readme
    assert "https://docs.runpod.io/hub/publishing-guide" in readme
    assert "https://docs.runpod.io/hub/revenue-sharing" in readme
    assert "https://console.runpod.io/hub" in readme


def test_licenses_record_the_noncommercial_audio_exclusion():
    text = (ROOT / "LICENSES.md").read_text(encoding="utf-8")
    assert "CC-BY-NC" in text
    assert "MMAudio" in text
    assert "AGPL-3.0" in text


def test_default_weights_are_the_six_commercial_files(tmp_path):
    env = {**os.environ, "DRY_RUN": "1"}
    result = _run_bash(
        str(ROOT / "download_models.sh"),
        str(tmp_path),
        capture_output=True,
        text=True,
        env=env,
    )
    assert result.returncode == 0
    assert result.stdout.count("would get") == 6
    assert "38.03" in result.stdout
    lowered = result.stdout.lower()
    found = [name for name in ("mmaudio", "bigvgan", "ace-step", "ace_step") if name in lowered]
    assert found == []


def test_optional_loras_are_not_in_the_default_download(tmp_path):
    env = {**os.environ, "DRY_RUN": "1", "MANIFEST": str(ROOT / "models.optional.yaml")}
    result = _run_bash(
        str(ROOT / "download_models.sh"),
        str(tmp_path),
        capture_output=True,
        text=True,
        env=env,
    )
    assert result.returncode == 0
    assert result.stdout.count("would get") == 4
    assert "v2.0" in result.stdout
    assert "250928" in result.stdout


def test_manifest_that_names_mmaudio_is_refused(tmp_path):
    manifest = tmp_path / "models.yaml"
    manifest.write_text("url: https://example.com/mmaudio.safetensors\n", encoding="utf-8")
    env = {**os.environ, "MANIFEST": str(manifest)}
    result = _run_bash(
        str(ROOT / "download_models.sh"),
        str(tmp_path),
        capture_output=True,
        text=True,
        env=env,
    )
    assert result.returncode == 1
    assert "audio model" in result.stderr


def test_shell_scripts_parse():
    for name in ("download_models.sh", "entrypoint.sh"):
        result = _run_bash("-n", str(ROOT / name))
        assert result.returncode == 0


def test_workflow_is_silent_and_has_a_generic_filename():
    raw = (ROOT / "workflows" / "wan22_t2v.json").read_text(encoding="utf-8")
    assert "sisif" not in raw.lower()
    graph = json.loads(raw)
    classes = " ".join(node["class_type"] for node in graph.values())
    assert "AceStep" not in classes
    assert "MMAudio" not in classes
    assert "Audio" not in classes
    assert graph["90"]["inputs"]["filename_prefix"] == "video"


def test_prompt_size_and_seed_land_on_the_graph(monkeypatch):
    monkeypatch.setenv("COMFY_RIFE", "1")
    spec = wan_job.build_spec(
        {
            "prompt": "  unique kettle whistle  ",
            "negative_prompt": "blur",
            "width": 832,
            "height": 480,
            "duration_seconds": 1,
            "seed": 7,
        }
    )
    graph = wan_graph.build_graph(spec)
    assert wan_graph.node_inputs(graph, wan_graph.TITLE_PROMPT)["text"] == "unique kettle whistle"
    assert wan_graph.node_inputs(graph, wan_graph.TITLE_NEGATIVE)["text"] == "blur"
    assert wan_graph.node_inputs(graph, wan_graph.TITLE_LATENT)["length"] == 17
    assert wan_graph.node_inputs(graph, wan_graph.TITLE_LATENT)["width"] == 832
    for title in wan_graph.SAMPLER_TITLES:
        assert wan_graph.node_inputs(graph, title)["noise_seed"] == 7
    assert wan_graph.node_inputs(graph, wan_graph.TITLE_ASSEMBLE)["fps"] == 32
    high = wan_graph.node_inputs(graph, "Lightning LoRA high noise")["lora_name"]
    assert high == wan_job.DEFAULT_LORA_HIGH


def test_interpolation_can_be_bypassed(monkeypatch):
    monkeypatch.setenv("COMFY_RIFE", "0")
    spec = wan_job.build_spec({"prompt": "a cup", "seed": 1})
    graph = wan_graph.build_graph(spec)
    decode = wan_graph.node_key(graph, wan_graph.TITLE_DECODE)
    assert wan_graph.node_inputs(graph, wan_graph.TITLE_SAVE_RESIZE)["image"] == [decode, 0]
    assert wan_graph.node_inputs(graph, wan_graph.TITLE_ASSEMBLE)["fps"] == wan_job.SAMPLE_FPS


def test_audio_nodes_are_removed_before_submit():
    graph = wan_graph.load_workflow(wan_graph.workflow_path())
    save = wan_graph.node_key(graph, wan_graph.TITLE_SAVE)
    graph["999"] = {"class_type": "MMAudioSampler", "_meta": {"title": "Foley"}, "inputs": {}}
    wan_graph.node_inputs(graph, wan_graph.TITLE_SAVE)["audio"] = ["999", 0]
    wan_graph.drop_audio_nodes(graph)
    assert "999" not in graph
    assert "audio" not in graph[save]["inputs"]


def test_rejects_unsupported_size_and_long_duration():
    with pytest.raises(ValueError, match="Unsupported size"):
        wan_job.build_spec({"prompt": "hello", "width": 512, "height": 512})
    with pytest.raises(ValueError, match="duration_seconds"):
        wan_job.build_spec({"prompt": "hello", "duration_seconds": 6})
    with pytest.raises(ValueError, match="prompt"):
        wan_job.build_spec({"prompt": "   "})


def test_silent_clip_is_accepted_and_a_sound_track_is_not():
    wan_mp4.require_no_audio_stream(SILENT_MP4)
    with pytest.raises(ValueError, match="audio"):
        wan_mp4.require_no_audio_stream(SOUND_MP4)


def test_handler_returns_base64_when_s3_is_unset(monkeypatch):
    _clear_s3(monkeypatch)
    monkeypatch.setattr(handler, "render_clip", lambda spec: (SILENT_MP4, 1.25))
    result = handler.handler(
        {
            "id": "abc",
            "input": {
                "prompt": "A cup of coffee.",
                "seed": 1,
                "width": 832,
                "height": 480,
                "duration_seconds": 1,
            },
        }
    )
    assert base64.b64decode(result["video_base64"]) == SILENT_MP4
    assert result["width"] == 832
    assert result["height"] == 480
    assert result["fps"] == 32
    assert result["seed"] == 1
    assert result["generation_seconds"] == 1.25
    assert "video_url" not in result


def test_partial_s3_fails_before_render(monkeypatch):
    _clear_s3(monkeypatch)
    monkeypatch.setenv("S3_BUCKET_NAME", "renders")

    def fail_if_called(spec):
        raise AssertionError(spec)

    monkeypatch.setattr(handler, "render_clip", fail_if_called)
    with pytest.raises(ValueError, match="Incomplete S3"):
        handler.handler({"input": {"prompt": "A cup.", "seed": 1}})


def test_s3_upload_uses_only_the_configured_bucket(monkeypatch):
    _clear_s3(monkeypatch)
    monkeypatch.setenv("S3_ENDPOINT_URL", "https://s3.example.com")
    monkeypatch.setenv("S3_BUCKET_NAME", "renders")
    monkeypatch.setenv("S3_ACCESS_KEY_ID", "key")
    monkeypatch.setenv("S3_SECRET_ACCESS_KEY", "secret")
    monkeypatch.setenv("S3_PUBLIC_URL", "https://cdn.example.com")
    monkeypatch.setenv("RETURN_BASE64", "0")
    uploaded = {}

    class FakeClient:
        def upload_fileobj(self, fileobj, bucket, key, **kwargs):
            extra = kwargs["ExtraArgs"]
            uploaded["bucket"] = bucket
            uploaded["key"] = key
            uploaded["body"] = fileobj.read()
            uploaded["content_type"] = extra["ContentType"]

    monkeypatch.setitem(sys.modules, "boto3", types.SimpleNamespace(client=lambda *args, **kwargs: FakeClient()))
    monkeypatch.setattr(handler, "render_clip", lambda spec: (SILENT_MP4, 2))
    result = handler.handler({"id": "job/1", "input": {"prompt": "A cup.", "seed": 3, "duration_seconds": 1}})
    assert result["video_url"] == "https://cdn.example.com/job1.mp4"
    assert "video_base64" not in result
    assert uploaded["bucket"] == "renders"
    assert uploaded["key"] == "job1.mp4"
    assert uploaded["body"] == SILENT_MP4
    assert uploaded["content_type"] == "video/mp4"


def test_sound_track_fails_the_job(monkeypatch):
    _clear_s3(monkeypatch)
    monkeypatch.setattr(handler, "render_clip", lambda spec: (SOUND_MP4, 1))
    with pytest.raises(ValueError, match="audio"):
        handler.handler({"input": {"prompt": "A cup.", "seed": 1}})


def test_job_input_must_be_an_object():
    with pytest.raises(ValueError, match="object"):
        handler.handler({"input": "nope"})


def test_empty_s3_settings_mean_inline_only(monkeypatch):
    _clear_s3(monkeypatch)
    assert wan_delivery.s3_settings() is None
