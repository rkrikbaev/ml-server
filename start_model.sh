#!/bin/bash

port=$1
model=$2

root="$(pwd)"
echo "Root: $root"

# Get the version
version="${model##*/}"

image=ml:0.0.9

# Combain name of container, replace all / on _
name="${model%/*}"
name="${name//\//_}"
name="${name//@/_}"

# Final name
fullname="${name}_${version}"

echo "Model name: $name"
echo "Last segment: $version"
echo "Container name: $fullname"

# Start docker container
docker run \
    --cpus 8 \
    -m 1024m \
    -itd \
    --name "$fullname" \
    -e MAX_CONCURRENT_REQUESTS=8 \
    -e LOGLEVEL=WARNING \
    -p $port:8000 \
    -v "/$root/local/$model:/workspace/models" \
    -v "/$root/src:/workspace/server" \
    -v "/$root/lib:/workspace/lib" \
    $image \
    python3 -m uvicorn server:app --host 0.0.0.0 --port 8000
