# FLUX.1 Serverless (diffusers)

Text to image generation with FLUX.1 on Runpod Serverless. This is a plain `diffusers` worker. No ComfyUI, no InvokeAI, no web UI. You send JSON, you get a base64 PNG back, and the endpoint scales to zero so billing stops between requests.

[![Runpod](https://api.runpod.io/badge/NathanWhite-hub/runpod-flux-serverless)](https://console.runpod.io/hub/NathanWhite-hub/runpod-flux-serverless)


## Why diffusers and not InvokeAI

InvokeAI is a full application: a server, a job queue, a model database, and a canvas frontend. None of that maps onto a serverless request and response worker, which is why it is absent from the Hub. The generation core inside InvokeAI is `diffusers`, so this worker calls `diffusers` directly. The payload stays small and readable instead of a full node graph.

## Files

```
.
├── handler.py            # serverless handler: loads FLUX, runs generation, returns PNGs
├── requirements.txt      # python deps (torch comes from the base image)
├── Dockerfile            # CUDA + pytorch base, installs deps, runs the handler
├── .gitignore
└── .runpod/
    ├── hub.json          # Hub listing + deploy config (GPU pools, env, presets)
    └── tests.json        # Hub validator test (uses ungated schnell, no token needed)
```

## API

### Request

```json
{
  "input": {
    "prompt": "a red fox in a snowy pine forest, golden hour",
    "width": 1024,
    "height": 1024,
    "num_inference_steps": 28,
    "guidance_scale": 3.5,
    "num_images": 1,
    "max_sequence_length": 512,
    "seed": 12345
  }
}
```

`prompt` is the only required field. Everything else falls back to defaults. Omit `seed` for a random one, which is returned in the response so you can reproduce a result.

| Field | Default | Notes |
|-------|---------|-------|
| `prompt` | required | text prompt |
| `width` | 1024 | image width |
| `height` | 1024 | image height |
| `num_inference_steps` | `DEFAULT_STEPS` env | 28 to 50 for dev, 4 for schnell |
| `guidance_scale` | `DEFAULT_GUIDANCE` env | around 3.5 for dev, 0 for schnell |
| `num_images` | 1 | images per request |
| `max_sequence_length` | 512 | T5 prompt token budget |
| `seed` | random | integer for reproducible output |

### Response

```json
{
  "images": ["<base64 PNG>"],
  "parameters": {
    "model": "black-forest-labs/FLUX.1-dev",
    "seed": 12345,
    "num_inference_steps": 28,
    "guidance_scale": 3.5,
    "width": 1024,
    "height": 1024,
    "quantized": true
  },
  "seconds": 7.4
}
```

Decode an image with `base64 -d` or in code:

```python
import base64
with open("out.png", "wb") as f:
    f.write(base64.b64decode(resp["output"]["images"][0]))
```

## Environment variables

| Key | Default | Purpose |
|-----|---------|---------|
| `MODEL_ID` | `black-forest-labs/FLUX.1-dev` | any FLUX repo on Hugging Face |
| `HUGGING_FACE_HUB_TOKEN` | empty | required for gated models like FLUX.1-dev |
| `QUANTIZE` | `false` | qfloat8 on transformer + T5, fits dev on 24GB |
| `DEFAULT_STEPS` | `28` | step fallback when a request omits it |
| `DEFAULT_GUIDANCE` | `3.5` | guidance fallback when a request omits it |

## Model gating

FLUX.1-dev is gated. Accept the license at https://huggingface.co/black-forest-labs/FLUX.1-dev, create a read token at https://huggingface.co/settings/tokens, and set it as `HUGGING_FACE_HUB_TOKEN` on the endpoint. FLUX.1-schnell is Apache 2.0 and needs no token, which is why the Hub validator test runs schnell.

## VRAM

| Mode | Approx VRAM | GPU |
|------|-------------|-----|
| dev, `QUANTIZE=true` | ~17 to 20 GB | 24GB card (4090, L4, A5000) |
| dev, full bf16 + cpu offload | fits 24GB, faster on 48GB | A6000, L40S, A100 |
| schnell, full bf16 | ~24 GB | 24GB card |

The quantized path loads straight onto the GPU. The full path enables `enable_model_cpu_offload`, which trades speed for a smaller VRAM footprint.

## Network volume

The Dockerfile sets `HF_HOME=/runpod-volume/huggingface`. Attach a network volume to the endpoint so the FLUX weights download once and persist. Without a volume, every cold worker pulls the full model again, which adds minutes to the first request and burns disk.

## Deploy through the Hub

1. Create an empty repo on GitHub and push this folder (commands below).
2. Cut a GitHub Release. The Hub indexes releases, not commits.
3. In the Runpod console open the Hub, click Get Started under Add your repo, paste the repo URL, and follow the prompts.
4. After the build and validator pass and the listing is approved, click Deploy, pick a preset, and supply your Hugging Face token for dev.

## Deploy without the Hub

Build the image, push it to a registry, then create a Serverless endpoint pointing at it.

```bash
docker build -t YOUR_DOCKERHUB_USER/flux-serverless:1.0.0 .
docker push YOUR_DOCKERHUB_USER/flux-serverless:1.0.0
```

In the Runpod console create a Serverless endpoint, set the container image, attach a network volume, and set the env vars from the table above.

## Local sanity check

The full pipeline needs a CUDA GPU and the model download, so local runs require a capable machine. Handler logic and imports check with:

```bash
pip install runpod
python -c "import handler"
```

## License

Code here is MIT. The FLUX.1-dev weights carry the Black Forest Labs non commercial license. Review it before any commercial use.
