# Silent text-to-video worker for RunPod Hub.
#
# Weights are not baked into the image. entrypoint.sh downloads them before ComfyUI
# starts, into MODEL_DIR (default /runpod-volume/models). The base image's
# extra_model_paths.yaml reads that directory.
#
# Custom nodes cannot be loaded from a volume, so the interpolation node and its
# checkpoint are baked here. The base image runs `python -u /handler.py` from
# /start.sh, so the handler copied onto / replaces the stock one.
FROM runpod/worker-comfyui:5.10.0-base

# curl is not in the base image. The downloader needs it.
RUN apt-get update && apt-get install -y --no-install-recommends curl ca-certificates \
    && rm -rf /var/lib/apt/lists/*

# runpod 1.7.11 through 1.10.0 corrupt per-worker job tracking on network-volume
# endpoints. runpod>=1.10.1 requires boto3>=1.43.40, so boto3 is left unpinned.
# No --system: the base image keeps its runtime in /opt/venv, which is first on PATH.
RUN uv pip install boto3 'runpod>=1.10.1'

# Pinned to the commit in custom_nodes.txt. A registry install would float.
ARG RIFE_SHA=26545cc2dd95bc3d27f056016300673bdeee78f5
RUN git clone https://github.com/Fannovel16/ComfyUI-Frame-Interpolation.git \
        /comfyui/custom_nodes/ComfyUI-Frame-Interpolation \
    && git -C /comfyui/custom_nodes/ComfyUI-Frame-Interpolation checkout ${RIFE_SHA} \
    && uv pip install -r /comfyui/custom_nodes/ComfyUI-Frame-Interpolation/requirements-no-cupy.txt

RUN mkdir -p /comfyui/custom_nodes/ComfyUI-Frame-Interpolation/ckpts/rife \
    && python -c "import urllib.request; urllib.request.urlretrieve('https://github.com/Fannovel16/ComfyUI-Frame-Interpolation/releases/download/models/rife49.pth', '/comfyui/custom_nodes/ComfyUI-Frame-Interpolation/ckpts/rife/rife49.pth')"

COPY handler.py wan_job.py wan_graph.py wan_comfy.py wan_mp4.py wan_delivery.py /
COPY workflows/wan22_t2v.json /workflows/wan22_t2v.json
COPY download_models.sh models.yaml models.optional.yaml /opt/hub/
COPY entrypoint.sh /hub-entrypoint.sh
RUN chmod +x /hub-entrypoint.sh /opt/hub/download_models.sh

ENV COMFY_WORKFLOW=/workflows/wan22_t2v.json \
    MODEL_DIR=/runpod-volume/models \
    COMFY_RIFE=1

CMD ["/hub-entrypoint.sh"]
