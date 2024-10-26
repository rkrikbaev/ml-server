#!/bin/bash

port=$1
input=$2

# Path to a model
path="$PWD/local/models/$input"

# Get the version
version="${input##*/}"

# Combain name of container, replace all / on _
name="${input%/*}"
name="${name//\//_}"

# Final name
fullname="${name}_${version}"

echo "Modified input: $name"
echo "Last segment: $version"
echo "Container name: $fullname"

# Start docker container
docker run -itd --name "$fullname" -p $port:8000 -v "$path:/workspace/server/model" -v "/DATASET/project/ml-services/git/ml-server/src:/workspace/server" 10.210.2.103:8082/fpcloud/ml:latest python3 -m uvicorn server:app --host 0.0.0.0 --port 8000