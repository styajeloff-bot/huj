FROM ghcr.io/astral-sh/uv:python3.12-bookworm-slim

# Runtime deps:
# * curl — healthchecks / ad-hoc debugging
# * git / openssh-client — install private GitLab git+ssh dependencies
# * fonts-dejavu-core — Cyrillic font for reportlab (PD-denial PDF)
# * weasyprint system libs — Cairo / Pango / GDK-Pixbuf for headless
#   Markdown → PDF conversion of the СОПД template.
RUN apt-get update \
 && apt-get install -y --no-install-recommends \
        curl \
        git \
        openssh-client \
        fonts-dejavu-core \
        libcairo2 \
        libpango-1.0-0 \
        libpangocairo-1.0-0 \
        libgdk-pixbuf2.0-0 \
        libffi-dev \
        shared-mime-info \
 && rm -rf /var/lib/apt/lists/*

RUN groupadd --system --gid 999 nonroot \
 && useradd --system --gid 999 --uid 999 --create-home nonroot \
 && mkdir -p /home/nonroot/.cache/dconf /home/nonroot/.config /home/nonroot/.local/share \
 && chown -R nonroot:nonroot /home/nonroot

WORKDIR /app

ENV UV_COMPILE_BYTECODE=1

ENV UV_LINK_MODE=copy

ENV UV_NO_DEV=1

ENV UV_TOOL_BIN_DIR=/usr/local/bin

ENV HOME=/home/nonroot

ENV XDG_CACHE_HOME=/home/nonroot/.cache

ENV XDG_CONFIG_HOME=/home/nonroot/.config

ENV XDG_DATA_HOME=/home/nonroot/.local/share

COPY pyproject.toml uv.lock ./

# Path is relative to the Docker build context (./backend in docker-compose.dev.yml).
ARG SDK_SSH_KEY=id_ed25519

RUN mkdir -p /root/.ssh \
 && chmod 700 /root/.ssh

COPY ${SDK_SSH_KEY} /root/.ssh/id_ed25519

RUN touch /root/.ssh/known_hosts \
 && ssh-keyscan -t rsa gitlab.carcraft.ru >> /root/.ssh/known_hosts \
 && chmod 644 /root/.ssh/known_hosts \
 && chmod 600 /root/.ssh/id_ed25519

RUN --mount=type=cache,target=/root/.cache/uv \
    uv sync --locked --no-install-project

COPY --chown=nonroot:nonroot . /app

RUN --mount=type=cache,target=/root/.cache/uv \
    uv sync --locked

RUN chown -R nonroot:nonroot /home/nonroot

ENV PATH="/app/.venv/bin:$PATH"


USER nonroot


EXPOSE 8000
ENTRYPOINT ["python", "-m", "infrastructure.container_entrypoint"]
CMD ["uv", "run", "uvicorn", "main:app", "--host", "0.0.0.0", "--port", "3002", "--proxy-headers", "--forwarded-allow-ips", "*"]
