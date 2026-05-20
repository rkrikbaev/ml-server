# Краткий обзор перемещения

## forecast

| Папка        | Файл          | Функция / Класс        | Импортирован в \_\_init__.py |
| ------------ | ------------- | -----------------------| ---------------------------- |
| **forecast** | date.py       | get_full_days_mask     | ✅                           |
|              |               | get_weekday            | ✅                           |
|              |               |                        |                              |
|              | enums.py      | Threshold              | ✅                           |
|              |               |                        |                              |
|              | evaluation.py | count_input_health     | ✅                           |
|              |               | evaluate_input_health  | ✅                           |
|              |               |                        |                              |
|              | inference.py  | predict_default        | ✅                           |
|              |               | predict                | ✅                           |
|              |               |                        |                              |
|              | model.py      | SbreModel              | 📛                           |
|              |               | init_model             | ✅                           |

### date.py

Лежат функции для работы с датами

1. get_full_days_mask
2. get_weekday

---

### enums.py

Лежат функции для работы с enum-ами

1. Threshold (class)

---

### evaluation.py

Лежат функции для оценки здоровья входных рядов

1. count_input_health
2. evaluate_input_health

---

### inference.py

Лежат функции для расчёта модели предоставленными данными

1. predict_default
2. predict

---

### model.py

Лежат функции для работы с моделью

1. SbreModel (empty class)
2. init_model

## send

| Папка    | Файл        | Функция / Класс        | Импортирован в \_\_init__.py |
| ---------| ----------- | ---------------------- | ---------------------------- |
| **send** | archives.py | get_data_from_arvhives | ✅                           |
|          |             | send_ndc_url           | 📛                           |
|          |             | extract_data           | 📛                           |
|          |             |                        |                              |
|          | rz.py       | get_data_from_rz       | ✅                           |
|          |             | send_rz_url            | 📛                           |
|          |             | convert_rz_format      | 📛                           |
|          |             | require_rz_data        | 📛                           |

### archives.py

Лежат функции для работы с архивами из NDC

1. get_data_from_arvhives (main)
2. send_ndc_url (assistant for the main)
3. extract_data (assistant for the main)

---

### rz.py

Лежат функции для работы с графиком ремонтов

1. get_data_from_rz (main)
2. send_rz_url (assistant for the main)
3. convert_rz_format (assistant for the main)
4. require_rz_data (assistant for the main)

## utils

| Папка      | Файл          | Функция / Класс                    | Импортирован в \_\_init__.py |
| ---------- | ------------- | ---------------------------------- | ---------------------------- |
| **utils**  | other.py      | nan_helper                         | 📛                           |
|            |               | interpolate_nan_1d                 | ✅                           |
|            |               | get_last_past_index                | ✅                           |
|            |               |                                    |                              |
|            | schema.py     | get_fields                         | ✅                           |
|            |               |                                    |                              |
|            | timestamps.py | generate_timestamp                 | ✅                           |
|            |               | timestamps_to_timezoned_timestamps | ✅                           |
|            |               | get_pred_timestamps                | ✅                           |

### other.py

Лежат функции для работы с другими вспомогательными функциями

1. nan_helper
2. interpolate_nan_1d
3. get_last_past_index

---

### schema.py

Лежат функции вспомогательные для работы со схемой данных

1. get_fields

---

### timestamps.py

Лежат функции вспомогательные для работы с timestamp-ами

1. generate_timestamp
2. timestamps_to_timezoned_timestamps
3. get_pred_timestamps
