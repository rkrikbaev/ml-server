# syntax=docker/dockerfile:1

FROM ubuntu:22.04

WORKDIR /workspace/server

ENV DEBIAN_FRONTEND=noninteractive
ENV VIRTUAL_ENV=/opt/venv
ENV PATH="${VIRTUAL_ENV}/bin:${PATH}"

RUN apt-get update && \
    apt-get install -y --no-install-recommends \
        software-properties-common \
        openssh-client \
        gnupg \
        git \
        unzip \
        wget \
        tmux \
        curl \
        build-essential \
        telnet \
        netcat-traditional \
        net-tools && \
    add-apt-repository -y ppa:deadsnakes/ppa && \
    apt-get update && \
    apt-get install -y --no-install-recommends \
        python3.13 \
        python3.13-venv \
        python3.13-dev && \
    python3.13 -m venv ${VIRTUAL_ENV} && \
    apt-get clean && \
    rm -rf /var/lib/apt/lists/*

COPY requirements.txt .

RUN pip install --upgrade pip setuptools wheel
# NOTE: SSH-dependent build steps commented out. To enable, configure SSH key forwarding during docker build.
# RUN --mount=type=ssh mkdir -p -m 0700 ~/.ssh && ssh-keyscan 10.210.2.101 >> ~/.ssh/known_hosts
# RUN --mount=type=ssh git clone -b package git@10.210.2.101:mikhail.kotyushev/oik-new.git /tmp/package
# RUN python3.13 -m pip install /tmp/package
# RUN rm -rf /tmp/package
RUN pip install -r requirements.txt
