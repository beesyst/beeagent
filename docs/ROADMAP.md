# ROADMAP — BeeAgent (AI Merchandising Agent, итерации разработки)

## Принцип
Делаем маленькие итерации. Каждая итерация:
- запускается `start.sh`
- пишет логи в `logs/`
- оставляет артефакты в `storage/`
- не ломает структуру пакета `beeagent_module`
- соблюдает KISS (минимум абстракций, максимум ясности)

## Цель pre-MVP (для ближайшего созвона)
Показать end-to-end демо:
Telegram → запуск агента (OOS Detector) → отчёт → approve/reject задач → артефакты в storage.
Данные: мок (без 1С), LLM через API.

---

## Этап 1 — Pre-MVP (итерации 0–4)

### Итерация 0 — Каркас и запуск (skeleton)
**Статус: ГОТОВО**

Цель: репозиторий готов к разработке и демо.

Сделать:
- `start.sh` → запускает `python3 config/start.py`
- `config/start.py` → загрузка env + settings + запуск одного режима (telegram)
- `src/beeagent_module/` → создать пакет со структурами папок (см. ARCHITECTURE)
- `beeagent_module/core/log.py` → логирование (stdout + logs/app.log)
- `beeagent_module/core/paths.py` → пути к logs/ и storage/
- `beeagent_module/core/settings.py` → загрузка settings.yml + fail-fast валидация
- `storage/` и `logs/` создаются автоматически

DoD:
- `bash start.sh` работает
- создаются `logs/app.log` и `storage/.keep` (или папки runs/tasks/artifacts)
- `pytest -q` проходит (smoke test)

### Итерация 1 — Telegram bot v0 (UX скелет)
**Статус: ГОТОВО**

Цель: Telegram бот отвечает и показывает меню.

Сделать:
- команды: `/start`, `/help`, `/run_oos`, `/last`
- inline-кнопки: "Run OOS Scan", "Show Report"
- allowlist (один chat_id в config) — KISS security

Артефакты:
- `storage/telemetry/telegram_updates.jsonl` (optional, 1 строка на событие)

DoD:
- бот запускается и отвечает
- меню и кнопки работают
- не падает при неизвестной команде

### Итерация 2 — Mock data v0 + доменная модель
**Статус: ГОТОВО**

Цель: воспроизводимый мок данных для демо.

Сделать:
- `domain/` модели: Store, SKU, SalesRow, StockRow, ShelfSignal, Alert, Task, RunMeta
- генератор моков:
  - 3 stores
  - 1 category ("Vitamins" или "Cosmetics")
  - 10–30 SKU с маржой/ценой
  - 4–12 недель daily sales + daily stock
  - shelf_signal (boolean) + несколько forced anomalies
- конфиг параметров мок-датасета в `config/settings.yml` (без хардкода, fail-fast):
  - `mock.seed`
  - `mock.weeks`
  - `mock.stores`
  - `mock.skus`
  - `mock.category`

Артефакты:
- `storage/mock/<dataset_id>/dataset.json` (или набор csv/json)

DoD:
- генерация даёт одинаковый результат при одинаковом seed
- мок можно загрузить одной функцией `load_mock_dataset(...)`
- при `/run_oos` создаётся `storage/mock/<dataset_id>/dataset.json` (параметры берутся из settings.yml)

### Итерация 3 — LangGraph workflow v0 (OOS detector, dry-run)
**Статус: ГОТОВО**

Цель: end-to-end запуск через LangGraph и отчёт в Telegram.

Graph nodes (KISS):
1) collect_input
2) load_data (mock)
3) detect_oos (rules)
4) draft_tasks
5) render_report (telegram-friendly markdown)
6) persist_run

Правила OOS (простые):
- Rule A: stock_on_hand > 0 AND seen_on_shelf == false → alert
- Rule B (optional): sales_drop >= X% AND seen_on_shelf == false → alert

Артефакты:
- `storage/runs/<run_id>/run.json`
- `storage/runs/<run_id>/alerts.json`
- `storage/runs/<run_id>/tasks_draft.json`

DoD:
- `/run_oos` создаёт run_id, пишет артефакты, возвращает отчёт в Telegram
- если данных нет — понятное сообщение + empty report

### Итерация 4 — Approval v0 + export (HTML или XLSX)
**Статус: ГОТОВО**

Цель: enterprise-вкус: approval before action + красивый артефакт.

Сделать:
- кнопки: "Approve Tasks" / "Reject"
- статус задач: draft/approved/rejected + reason
- экспорт отчёта:
  - минимум: `report.md` и `report.html`
  - опционально: `report.xlsx` (если успеем)

Артефакты:
- `storage/runs/<run_id>/tasks_approved.json` (или tasks.json со статусами)
- `storage/artifacts/<run_id>/report.html` (+ md/xlsx)

DoD:
- approve/reject сохраняются и видны в `/last`
- без approve задачи не считаются "готовыми"

---

## Этап 2 — Pilot-ready (итерации 5–8)

### Итерация 5 — Data adapter interface (mock → later 1C)
Цель: не переписывать граф при подключении 1С.

Сделать:
- интерфейс `DataAdapter` (get_sales/get_stock/get_catalog/get_planogram/get_photosignal)
- `MockAdapter` реализует интерфейс
- граф использует только adapter

DoD:
- один переключатель в settings.yml меняет адаптер (mock)

### Итерация 6 — Scheduler + approval gate
Цель: автозапуск по расписанию + обязательный approval.

### Итерация 7 — Мини-observability v0
Цель: базовая трассировка шагов графа (лог + run step timing).

### Итерация 8 — Добавить 2-й агент (например "Promo calendar")
Цель: показать расширяемость каркаса: новый agent = новый graph module.

---

## Этап 3 — Enterprise hardening (после подтверждения проекта)
- multi-tenancy (tenants, namespaces, ACL)
- RBAC/SSO (Keycloak)
- real data integrations (1C/BI)
- полноценная observability/evals (Langfuse/Phoenix/LangSmith)
- безопасные политики (OWASP LLM Top 10 как чеклист)
