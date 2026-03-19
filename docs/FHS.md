# Filesystem Hierarchy Standard

```fhs
ml-server/
⤷ docker/
   ⤷ .dockerignore
   ⤷ Dockerfile
   ⤷ docker-compose.yaml
⤷ docs/**
⤷ fp/**
⤷ lib/**
⤷ local/**
⤷ src/
   ⤷ api/
      ⤷ broker/
         ⤷ tasks/
            ⤷ __init__.py
            ⤷ predict.py
         ⤷ __init__.py
         ⤷ broker.py
      ⤷ data/
         ⤷ __init__.py
         ⤷ predict.py
      ⤷ forecast/
         ⤷ __init__.py
         ⤷ date.py
         ⤷ enums.py
         ⤷ evaluation.py
         ⤷ inference.py
         ⤷ model.py
      ⤷ send/
         ⤷ __init__.py
         ⤷ archives.py
         ⤷ rz.py
      ⤷ utils/
         ⤷ __init__.py
         ⤷ other.py
         ⤷ schema.py
         ⤷ timestamps.py
      ⤷ __init__.py
      ⤷ config.py
      ⤷ message.py
      ⤷ server.py
```

## Краткий обзор

- [`docker`](SETUP.md) папке лежат файлы для сборки и запуска контейнера
- `docs` папке лежат документы, включая это руководство
- `fp` папке лежат файлы модуля прогнозирования к SCADA
- `lib` папке лежат библиотека, в том числе и обучение моделей (репозиторий)
- `local` папке лежат обученные модели
- `src` папке лежат исходный код проекта ML сервера
  - [`api`](./API/MAIN.md) внутри `src` папке лежат файлы API сервера
    - [`data`](.//API/schema/MAIN.md) внутри `api` папке лежат схема данных
    - `forecast` внутри `api` папке лежат файлы прогнозирования
    - `send` внутри `api` папке лежат файлы отправки и взятия данных из других серверов
    - `utils` внутри `api` папке лежат вспомогательные файлы
    - `broker` внутри `api` папке лежат файлы брокера
      - `tasks` внутри `broker` папке лежат файлы задач брокера
