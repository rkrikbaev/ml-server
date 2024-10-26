docker run -it --name ml0 --restart always -p 8000 -m 1024m \
-v .\Downloads\kegoc_services\ml\server:/server fpcloud/ml:0.0.1 python3 -m uvicorn server:app --host 0.0.0.0 --port 8000

# start with bash
docker run -itd --rm --name model1 -p 18200:8000 \
-v "/DATASET/project/ml-services/ml-consumption/local/models/$MODEL_PATH/1.0:/workspace/server/model" \
-v "/DATASET/project/ml-services/git/ml-server/src:/workspace/server" 10.210.2.103:8083/ml:0.0.1 /bin/bash