# Local Model Bundle

This directory is intentionally part of the Docker build context.

To build an offline image with Chronos trajectory forecasting ready on Ubuntu/OEL,
place the model files under:

```text
docker/icu-models/chronos/
  config.json
  model.safetensors
```

Then build:

```bash
docker build -f backend/Dockerfile \
  --build-arg INCLUDE_LOCAL_MODELS=true \
  -t icu-alert-system:chronos .
```

At runtime the image sets `ICU_MODELS_DIR=/opt/icu-models`, so the backend reads
Chronos from `/opt/icu-models/chronos` without downloading anything.

Do not commit large model weights to Git. Keep them in the local build context
or publish the image to your private registry.
