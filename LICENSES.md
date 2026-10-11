# License audit

Audited 11 October 2026 against the ComfyUI worker this directory was prepared from:

- `rp-handler/Dockerfile.comfyui`
- `rp-handler/handler_comfyui.py`
- `rp-handler/comfyui/workflows/wan22_product_t2v.json`
- `rp-handler/comfyui/models.yaml`
- `rp-handler/comfyui/custom_nodes.txt`

That image does not bake the diffusion weights. It bakes one custom node and one interpolation checkpoint, and `models.yaml` is what a volume download fetches. This directory keeps that split. The default download is the six files in `models.yaml` (38.03 GB as declared there). `models.optional.yaml` is off unless `DOWNLOAD_OPTIONAL_LORAS=1`.

Nothing in this directory downloads MMAudio, BigVGAN, or ACE-Step. The graph strips any node whose class contains `MMAudio`, `AceStep`, or `VAEDecodeAudio` before it is submitted.

This is a source audit of the licenses those projects publish. It is not a legal opinion.

## Shipped

| Piece | Where it comes from | License | Notes |
| --- | --- | --- | --- |
| Base image `runpod/worker-comfyui:5.10.0-base` | [runpod-workers/worker-comfyui](https://github.com/runpod-workers/worker-comfyui/blob/main/LICENSE) | AGPL-3.0 | The worker repository license is the GNU Affero General Public License v3. The image also contains ComfyUI. |
| ComfyUI 0.34.0, inside that base image | [Comfy-Org/ComfyUI v0.34.0](https://github.com/Comfy-Org/ComfyUI/blob/v0.34.0/LICENSE) | GPL-3.0 | Confirmed from the tag's `LICENSE` file. |
| ComfyUI-Frame-Interpolation `26545cc2dd95bc3d27f056016300673bdeee78f5` | [LICENSE at that commit](https://github.com/Fannovel16/ComfyUI-Frame-Interpolation/blob/26545cc2dd95bc3d27f056016300673bdeee78f5/LICENSE) | MIT | The only custom node the Dockerfile clones. |
| `rife49.pth` | [Frame-Interpolation release asset](https://github.com/Fannovel16/ComfyUI-Frame-Interpolation/releases/download/models/rife49.pth) | MIT, with a provenance gap | The node pack is MIT. [Practical-RIFE](https://github.com/hzwer/Practical-RIFE/blob/main/LICENSE) is MIT, and its README says the trained-model links listed there are under that same MIT license. This image downloads the node pack's `rife49.pth`, and that file was not byte-compared to a Practical-RIFE release. |
| `wan2.2_t2v_high_noise_14B_fp8_scaled` and `wan2.2_t2v_low_noise_14B_fp8_scaled` | [Comfy-Org/Wan_2.2_ComfyUI_Repackaged](https://huggingface.co/Comfy-Org/Wan_2.2_ComfyUI_Repackaged) | Apache-2.0 | The Hub model record's license field is `apache-2.0`. Upstream [Wan-Video/Wan2.2 LICENSE.txt](https://github.com/Wan-Video/Wan2.2/blob/main/LICENSE.txt) is Apache-2.0. The official Hugging Face model page returned HTTP 401 without a token; the files this template fetches are the public Comfy-Org copies, which answer without a token. |
| `umt5_xxl_fp8_e4m3fn_scaled` | Same Comfy-Org repository | Apache-2.0 | The fp8 file is in the Apache-2.0 repackage. The upstream text encoder [google/umt5-xxl](https://huggingface.co/google/umt5-xxl) is Apache-2.0. |
| `wan_2.1_vae` | Same Comfy-Org repository | Apache-2.0 | Upstream [Wan-Video/Wan2.1 LICENSE.txt](https://github.com/Wan-Video/Wan2.1/blob/main/LICENSE.txt) is Apache-2.0. A14B uses this VAE. |
| Lightning LoRA v1.1, both halves | Same Comfy-Org repository, and [lightx2v/Wan2.2-Lightning](https://huggingface.co/lightx2v/Wan2.2-Lightning) | Apache-2.0 | The lightx2v model card says the models in that repository are Apache-2.0. v1.1 is the pair the graph loads by default. |
| Lightning LoRA v2.0 and 250928, both halves | [lightx2v/Wan2.2-Lightning](https://huggingface.co/lightx2v/Wan2.2-Lightning) | Apache-2.0 | Same repository and license as v1.1. Optional download only. The 250928 high-noise file is rank 128. Do not mix halves across pairs. |

The handler modules in this directory (`handler.py`, `wan_job.py`, `wan_graph.py`, `wan_comfy.py`, `wan_mp4.py`, `wan_delivery.py`) are Apache-2.0, Copyright 2026 vtemian. [LICENSE](LICENSE) is the unmodified Apache License, Version 2.0. The container as a whole is not Apache-2.0, because it runs the AGPL-3.0 worker image and GPL-3.0 ComfyUI.

Publishing the image gives other people a network service that includes those programs. AGPL-3.0 has a source-offer duty for network use. The practical way to meet it is to publish this directory as its own public repository and to keep the upstream links above. Confirm that with counsel before the listing goes public if the AGPL base image is not acceptable. Rebuilding ComfyUI from the GPL sources, without the worker-comfyui image, would be a different template and was not done here.

## Not shipped

| Piece | Why it is not in the image | License |
| --- | --- | --- |
| MMAudio checkpoints | Not in `rp-handler/comfyui/models.yaml` and not cloned by `Dockerfile.comfyui`. An earlier plan downloaded them. They stay out. | Code in [hkchengrex/MMAudio](https://github.com/hkchengrex/MMAudio/blob/main/LICENSE) is MIT. The README states the checkpoints are [CC-BY-NC 4.0](https://creativecommons.org/licenses/by-nc/4.0/). Non-commercial. Do not add them to a Hub template. |
| BigVGAN vocoder | MMAudio's runtime dependency in that earlier plan. Not downloaded now. | [NVIDIA/BigVGAN](https://github.com/NVIDIA/BigVGAN/blob/main/LICENSE) code is MIT. The checkpoint was not re-audited because this image does not fetch it. |
| ACE-Step | `models.yaml` does not download it. The product workflow has no music nodes. `handler_comfyui.py` still knows how to drop `AceStep` nodes if a graph contains them. | [ACE-Step v1](https://huggingface.co/ACE-Step/ACE-Step-v1-3.5B) is Apache-2.0. [Ace-Step1.5](https://huggingface.co/ACE-Step/Ace-Step1.5) is MIT. Commercial terms are not the reason it is omitted. The template is silent video. |
| Other interpolation checkpoints the node pack can fetch (FILM and the rest) | The Dockerfile downloads only `rife49.pth`. | Not audited. Do not point the graph at another checkpoint without reading that file's license. |

`download_models.sh` refuses a manifest that names `mmaudio`, `bigvgan`, or `ace-step`.
