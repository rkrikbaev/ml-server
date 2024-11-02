run:
	docker run -it --name ml --restart always -p 8010:8000 fpcloud/ml:0.0.1 python3 -m uvicorn server:app --host 0.0.0.0 --port 8000

build:
	docker build -t fpcloud/ml:0.0.1 .