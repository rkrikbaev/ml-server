# Base CUDA devel image
FROM ubuntu:22.04

# Set working directory
WORKDIR /workspace/server

# Install required packages including Python and pip
RUN apt update && \
    apt-get -y install git unzip wget tmux curl python3.10 python3-pip python3-dev build-essential telnet netcat-traditional && \
    apt-get clean && rm -rf /var/lib/apt/lists/*

# Upgrade pip
RUN python3.10 -m pip install --upgrade pip

# Copy requirements and install
COPY requirements.txt .
RUN pip install -r requirements.txt 

# Add repo folder to PYTHONPATH
ENV PYTHONPATH="/workspace/server:${PYTHONPATH}"

EXPOSE 8000

# Copy files
COPY . .