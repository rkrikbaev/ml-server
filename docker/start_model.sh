#!/bin/bash


# input="/KAZ/UZHNIY/JAMBYL/220/L2129/P/1.0"
input=$1

path="$PWD/local/models/$input"

# Отделяем последний сегмент
version="${input##*/}"

# Заменяем все / на _ в оставшейся части строки
name="${input%/*}"
name="${name//\//_}"

# Результат
echo "Modified input: $name"
echo "Last segment: $version"

docker run -itd --name $name:$version -p $port:8000 -v $path:/workspace/server/model" -v "/DATASET/project/ml-services/git/ml-server/src:/workspace/server" 10.210.2.103:8082/fpcloud/ml:latest python3 -m uvicorn server:app --host 0.0.0.0 --port 8000