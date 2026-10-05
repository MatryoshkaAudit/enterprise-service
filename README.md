# MatryoshkaAudit / Enterprise Service

Микросервис кабинета машиностроительного предприятия платформы **MatryoshkaAudit**.

## Функционал
- Загрузка и управление многоуровневыми структурами изделий (BOM Tier 1-3).
- Расчёт формальной ("бумажной") vs реальной ("де-факто") локализации.
- Детекция узких горлышек (chokepoints) по формуле O-Ring: $CFI_i = \text{Criticality}_i \times \text{Risk}(\text{Country}_i) \times (1 - \text{AnalogAvail}_i)$.
- Моделирование замещения импортных узлов отечественными аналогами из каталога с расчётом затрат на редизайн и сроков внедрения.
- Предоставление REST API (FastAPI) и gRPC API (порт 50051).

## Запуск в режиме разработки

```bash
uvicorn app.main:app --port 8001 --reload
```

## Тестирование

```bash
pytest tests/
```
