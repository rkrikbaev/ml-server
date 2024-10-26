#!/bin/bash

port=$1
model=$2

root="$(pwd)"
echo "Root: $root"

# For tetsing
root=/tmp

# Get the version
version="${model##*/}"

image=rkrikbaev/ml:0.0.2

# Combain name of container, replace all / on _
name="${model%/*}"
name="${name//\//_}"

# Final name
fullname="${name}_${version}"

echo "Model name: $name"
echo "Last segment: $version"
echo "Container name: $fullname"

# Start docker container
docker run -itd --name "$fullname" -p $port:8000 -v "/$root/local/models/$model:/workspace/model" -v "/$root/src:/workspace/server" $image python3 -m uvicorn server:app --host 0.0.0.0 --port 8000