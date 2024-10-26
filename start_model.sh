#!/bin/bash

port=$1
input=$2

# Path to a model
path="/tmp/local/models/$input"

# Get the version
version="${input##*/}"

image=rkrikbaev/ml:0.0.2

# Combain name of container, replace all / on _
name="${input%/*}"
name="${name//\//_}"

# Final name
fullname="${name}_${version}"

echo "Modified input: $name"
echo "Last segment: $version"
echo "Container name: $fullname"

# Start docker container
docker run -itd --name "$fullname" -p $port:8000 -v "$path:/workspace/server/model" -v "/tmp/src:/workspace/server" $image python3 -m uvicorn server:app --host 0.0.0.0 --port 8000