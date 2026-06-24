FROM ghcr.io/invoke-ai/invokeai:latest

# Clear the base image entrypoint so our handler runs instead of invokeai-web.
ENTRYPOINT []

ENV PYTHONUNBUFFERED=1
ENV INVOKEAI_ROOT=/runpod-volume/invokeai
ENV INVOKEAI_HOST=127.0.0.1
ENV INVOKEAI_PORT=9090
ENV HANDLER_DEPS=/opt/handler-deps

# The InvokeAI venv ships without pip. Bootstrap pip with ensurepip, then install
# the worker deps into an isolated folder so they do not overwrite InvokeAI's own
# fastapi and pydantic. uv is a fallback in case ensurepip is unavailable.
RUN (python -m ensurepip --upgrade \
     && python -m pip install --no-cache-dir --target=/opt/handler-deps runpod requests) \
    || uv pip install --target /opt/handler-deps runpod requests

WORKDIR /workspace
COPY handler.py /workspace/handler.py

CMD ["python", "-u", "/workspace/handler.py"]
