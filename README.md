# Wan 2.2 text to video

A RunPod serverless worker that turns a prompt into a silent mp4. It runs ComfyUI with the Wan 2.2 text-to-video weights, a four-step Lightning LoRA pair, and optional frame interpolation. It does not generate audio.

Weights download on first start into `MODEL_DIR` (default `/runpod-volume/models`). They are not baked into the image. The default set is the six files in `models.yaml`, 38.03 GB as declared there. A 48 GB or larger GPU is required. 24 GB cards are not in the listing.

https://runpod.io?ref=d7ed2jfg

Referral link: we get RunPod credit if you sign up.

Licenses, including the CC-BY-NC exclusion, are in [LICENSES.md](LICENSES.md).

## Request

`POST /run` on the endpoint:

```json
{
  "input": {
    "prompt": "A slow handheld push-in across a sunlit kitchen table, steam rising from a cup of coffee.",
    "width": 480,
    "height": 832,
    "duration_seconds": 5,
    "seed": 1
  }
}
```

`prompt` is required. `negative_prompt` is optional; omit it to keep the workflow default. `seed` is optional; omit it for a new seed each job.

`width` and `height` must be one of `480x832`, `832x480`, `720x1280`, `1280x720`. The default is `480x832`. `720x1280` is tight on a 48 GB card.

`duration_seconds` is a whole number from 1 to `MAX_DURATION_SECONDS` (default 5). The model samples at 16 fps with a frame count of `duration * 16 + 1` (81 frames at 5 seconds). Interpolation doubles that to 32 fps and emits `(n - 1) * 2 + 1` frames, so a 5 second request is about 5.03 seconds of video.

## Response

Without S3, the mp4 comes back inline. `generation_seconds` is measured around the ComfyUI run. The number below is the field, not a benchmark:

```json
{
  "content_type": "video/mp4",
  "video_base64": "<base64-encoded mp4>",
  "width": 480,
  "height": 832,
  "fps": 32,
  "seed": 1,
  "duration_seconds": 5,
  "generation_seconds": 0
}
```

With all four of `S3_ENDPOINT_URL`, `S3_BUCKET_NAME`, `S3_ACCESS_KEY_ID`, and `S3_SECRET_ACCESS_KEY` set, the worker also uploads `{job_id}.mp4` and adds `video_url`. A partial set is an error. `S3_PUBLIC_URL` is an optional base for that URL. There is no default bucket.

```json
{
  "content_type": "video/mp4",
  "video_url": "https://cdn.example.com/abc123.mp4",
  "video_base64": "<base64-encoded mp4>",
  "width": 480,
  "height": 832,
  "fps": 32,
  "seed": 1,
  "duration_seconds": 5,
  "generation_seconds": 0
}
```

Set `RETURN_BASE64=0` to drop the inline bytes when S3 is configured. The worker refuses that setting when S3 is not configured.

`fps` is 16 when `COMFY_RIFE` is off.

## Environment

| Variable | Default | Purpose |
| --- | --- | --- |
| `COMFY_RIFE` | `1` | `1` interpolates to 32 fps. `0` encodes the 16 fps sample. |
| `MODEL_DIR` | `/runpod-volume/models` | Weight directory. Mount a network volume here so a cold start does not download 38 GB again. |
| `SKIP_MODEL_DOWNLOAD` | `0` | `1` skips the download. Use only when the files are already in `MODEL_DIR`. |
| `DOWNLOAD_OPTIONAL_LORAS` | `0` | `1` also fetches the v2.0 and 250928 pairs in `models.optional.yaml`. |
| `COMFY_LORA_HIGH` / `COMFY_LORA_LOW` | v1.1 filenames | Both halves of one pair. Do not mix releases. |
| `HF_TOKEN` | empty | Optional. The default files are public. |
| `RETURN_BASE64` | `1` | Include `video_base64`. |
| `S3_ENDPOINT_URL`, `S3_BUCKET_NAME`, `S3_ACCESS_KEY_ID`, `S3_SECRET_ACCESS_KEY` | empty | All four, or none. |
| `S3_PUBLIC_URL` | empty | Base for `video_url`. |
| `S3_REGION` | `us-east-1` | Passed to the S3 client. |
| `MAX_DURATION_SECONDS` | `5` | Upper bound on `duration_seconds`. |
| `COMFY_TIMEOUT_SECONDS` | `1500` | How long one ComfyUI prompt may run. |
| `COMFY_WORKFLOW` | `/workflows/wan22_t2v.json` | Graph path inside the image. |

`hub.json` exposes the same knobs to the Hub deploy form. `.runpod/tests.json` is the build-time check: one 1-second 480x832 clip on an L40S, with a 60 minute timeout so the weight download can finish.

## Local checks

These do not download weights and do not need a GPU. Run them from this directory, which is the repository root once the folder is published on its own:

```bash
python3 -m pytest tests -q
docker build .
```

## Publishing

Do not submit the parent repository to the Hub. The Hub reads `handler.py`, `Dockerfile`, and `README.md` from the repository root (or from `.runpod/`), and it reads `hub.json` and `tests.json` from `.runpod/`. This folder is prepared so that it can be the root of its own repository. Publishing, and the GitHub release that publishing requires, are left to the account owner.

Docs used, retrieved 11 October 2026:

- https://docs.runpod.io/hub/publishing-guide (page last modified 20 July 2026)
- https://docs.runpod.io/hub/overview (page last modified 20 July 2026)
- https://docs.runpod.io/hub/revenue-sharing (page last modified 20 July 2026)
- https://docs.runpod.io/references/gpu-types (page last modified 18 August 2026)

Steps, from those pages:

1. Create a new public GitHub repository and put the contents of this directory at its root, including `.runpod/hub.json` and `.runpod/tests.json`.
2. Push the default branch.
3. Create a GitHub release. The Hub indexes releases, not commits.
4. Open https://console.runpod.io/hub (the docs also link https://www.console.runpod.io/hub). Under **Add your repo**, click **Get Started**, and enter that new repository's URL.
5. The console then asks for `hub.json`, `tests.json`, `handler.py`, `Dockerfile`, and `README.md`. They are already in this directory.
6. The listing stays **Pending** while RunPod builds and runs `.runpod/tests.json`. A test passes when the endpoint returns HTTP 200. After the test, RunPod reviews the repo manually before it appears in the Hub.
7. Link the GitHub profile on the RunPod account. Revenue sharing requires that link, an approved listing, and a maintained release.
8. Later updates are a new GitHub release. The docs say the listing is indexed and built after a release, usually within an hour.

Revenue, from the revenue-sharing page: users who deploy the listing generate compute hours. The share resets every month. Below 100 hours it is 0%. It is 1% at 100-999 hours, 3% at 1,000-4,999, 5% at 5,000-9,999, and 7% at 10,000 or more. Their example is 2,500 hours earning $75 of RunPod credits. Credits land in the RunPod balance during the first week of the next month.

The optional Hub badge in the publishing guide can be added after the listing exists. This README does not include one.

## Before you publish

- The build-time test downloads the weights and renders a clip. The docs do not say who pays for that GPU. Watch the account during the first build.
- `hub.json` has no network-volume field. `containerDiskInGb` is 100 so a deploy can hold the image and the weights without a volume. Attach a volume at `/runpod-volume` on any endpoint you keep warm, or every cold start downloads about 38 GB again. People who deploy the listing have to do that themselves.
- The base image is AGPL-3.0 and ComfyUI inside it is GPL-3.0. Read [LICENSES.md](LICENSES.md) before the listing is public.
- Do not add MMAudio weights. The downloader refuses a manifest that names them.
- Do not point this listing at an existing production endpoint, and do not change one to use this image, until you mean to.
