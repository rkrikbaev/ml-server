# Схемы и Валидации

> Все дискриминаторы запускаются из функций под названиям `*_discriminator`. Название под звёздочкой (`*`) соответствует названию самой схемы и API.

-  Схема API [predict](./PREDICT.md) использует тип данных **PredictSchema** с дискриминатором [**TAG_PREDICT_CREATE**](../CONFIG.md#tag) из [`PredictCreateSchema`](./PREDICT.md#создание-predictcreateschema) и [**TAG_PREDICT_UPDATE**](../CONFIG.md#tag) из [`PredictUpdateSchema`](./PREDICT.md#обновление-predictupdateschema)
