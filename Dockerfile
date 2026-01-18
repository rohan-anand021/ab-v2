FROM python:3.11-slim

ENV DEBIAN_FRONTEND=noninteractive \
    PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1 \
    LANG=C.UTF-8 \
    LC_ALL=C.UTF-8

RUN apt-get update && apt-get install -y --no-install-recommends \
    git \
    ca-certificates \
    curl \
    ripgrep \
    patch \
    jq \
    openssh-client \
    tini \
    procps \
    less \
    build-essential \
    pkg-config \
    libffi-dev \
    libssl-dev \
    && curl -LsSf https://astral.sh/uv/install.sh | env UV_INSTALL_DIR=/usr/local/bin sh \
    && uv --version \
    && uv venv /opt/venv \
    && rm -rf /var/lib/apt/lists/*

ARG USER=agent
ARG UID=1000
ARG GID=1000

RUN groupadd --gid "${GID}" "${USER}" \
    && useradd --uid "${UID}" --gid "${GID}" -m "${USER}" \
    && mkdir -p /workspace /artifacts \
    && chown -R "${USER}:${USER}" /workspace /artifacts /opt/venv

ENV VIRTUAL_ENV=/opt/venv \
    PATH="/opt/venv/bin:${PATH}"

WORKDIR /workspace
USER ${USER}

ENTRYPOINT ["tini", "--"]
CMD ["sleep", "infinity"]
