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

- Сделать систему **подключаемой к реальным данным и “пилотируемой”**, и одновременно заложить **универсальность по каналам управления** (Telegram/Slack/Discord/WhatsApp).
- Один и тот же бизнес-сценарий (“case”) должен работать через любой UI-канал.
- Графы не знают UI и не знают источник данных: они вызывают `case` + `adapter`.
- UI-канал = тонкий слой (transport), который вызывает `cases/*` и показывает результат.
- KISS: минимум абстракций, максимум ясности.

### Итерация 5 — Cases layer v0 + Data Adapter v0 (mock → later 1C)
**Статус: ГОТОВО**

Цель: отвязать UI от деталей storage и графа. UI вызывает `cases/*`, граф читает данные только через `adapter`.

Сделать:
1. Cases layer (новое):
- создать `src/beeagent_module/cases/`
- `cases/oos.py`:
  - `run_oos_case(...)` → запускает OOS workflow и возвращает `run_id + report_text`
  - `approve_last_run_case(...)` → approve/reject по last_run
  - `get_last_report_case(...)` → вернуть текст отчёта для `/last`
- UI (telegram) НЕ читает `storage/runs/*` напрямую — только вызывает case-функции.
2. Data Adapter v0:
- интерфейс `DataAdapter` (Protocol/ABC — выбрать проще)
- методы (минимум для текущего OOS):
  - `get_catalog(...)` (stores + skus)
  - `get_stock(...)`
  - `get_shelf_signal(...)`
  - `get_sales(...)` (можно вернуть пусто, но метод должен быть)
  - `get_planogram(...)` / `get_photosignal(...)` — заглушки возвращают пусто
- `MockAdapter`:
  - читает `storage/mock/<dataset_id>/dataset.json`
  - отдаёт доменные объекты
3. Graph uses adapter:
- узел `load_data` больше не читает dataset.json напрямую
- узел `load_data` вызывает `adapter.*` и кладёт в state stores/skus/sales/stock/shelf_signals
4. Настройки:
- `data.adapter: "mock"`
- `data.mock.dataset_id: "<dataset_id>"` (опционально)
- если dataset_id не задан: как сейчас — генерим dataset на `/run_oos`

Артефакты:
- `storage/runs/<run_id>/run.json`:
  - `"adapter": "mock"`
  - `"trigger": "manual"` (задаём уже сейчас)

DoD:
- Telegram-бот работает как раньше, но не читает storage напрямую
- граф работает как раньше, но получает данные через adapter
- один ключ `data.adapter` выбирает адаптер (пока только mock)
- `pytest -q` проходит

### Итерация 6 — Scheduler v0 + Approval gate “обязателен”
**Статус: ГОТОВО**

Цель: автозапуск без ручного `/run_oos`, но никаких “готовых задач” без approve.

Сделать:
1. Scheduler (KISS):
- простой periodic loop: каждые N секунд
- без cron/apscheduler на этом этапе
2. Политика approval:
- после scheduled-run задачи всегда остаются `draft`
- бот отправляет сообщение: “New run ready → Approve/Reject”
3. Настройки:
- `scheduler.enabled: bool`
- `scheduler.interval: int`
- `scheduler.start_run: bool` (опционально)

Артефакты:
- `storage/runs/<run_id>/run.json`:
  - `"trigger": "scheduled"` / `"trigger": "manual"`

DoD:
- при scheduler.enabled бот создаёт run по интервалу
- без approve задачи остаются draft
- approve/reject работает для последнего run
- `pytest -q` проходит

### Итерация 7 — Mini-observability v0 (timing шагов)
**Статус: ГОТОВО**

Цель: видеть длительность каждого node и сохранить trace.

Сделать:
- фиксировать `duration_ms` для каждого node (внутри node или тонким wrapper, без монстров)
- лог: одна строка на node: `step=load_data duration_ms=...`
- артефакт: `storage/runs/<run_id>/steps.json` (или trace.json)

DoD:
- после run появляется `steps.json`
- `pytest -q` проходит

### Итерация 8 — 2-й агент v0 + multi-channel UI readiness
**Статус: ГОТОВО**

Цель: показать расширяемость платформы:
- новый агент = новый `cases/*` + `agents/*` + кнопка/команда в UI
- и подготовить “каркас” для второго UI-канала (без реализации интеграции в прод)

Сделать:
1. Второй агент (пример): `Promo Calendar` или `Price Check`:
- `agents/promo/graph.py` + `cases/promo.py`
- Telegram:
  - команда `/run_promo`
  - кнопка “Run Promo Scan”
- persist артефактов аналогично OOS, в `run.json` добавить `"agent": "promo"`
2. UI readiness (без интеграции):
- создать `ui/README.md` или секцию в README:
  - правила: UI-канал вызывает только `cases/*`
  - список будущих каналов: slack/discord/whatsapp
- (опционально) создать пустой модуль-заготовку:
  - `ui/slack_stub.py` (без зависимостей), только комментарии и будущие точки входа

DoD:
- второй агент запускается end-to-end через Telegram
- артефакты создаются по тому же стандарту
- в доке зафиксирован контракт: UI → cases → agents/adapter/storage
- `pytest -q` проходит

### Итерация 9 — Quiz Agent v0 (Pharmacy demo) + WOW UX (Telegram)
**Статус: ГОТОВО**

Цель: сделать “вау-демо” для маркетологов и пилота:
пользователь задаёт запрос → агент проводит квиз (вопросы/варианты) → собирает ответы → считает результат → выдаёт рекомендации + сохраняет артефакты.

Сделать:
1. Новый кейс + агент:
- `cases/quiz.py`:
  - `start_quiz_case(...)` — старт сессии (создать session_id, первый вопрос)
  - `answer_quiz_case(...)` — принять ответ, вернуть следующий вопрос или финальный результат
  - `get_last_quiz_result_case(...)` — вернуть последний результат квиза (для `/last_quiz`)
- `agents/quiz/graph.py` (LangGraph):
  - nodes: collect_input → load_quiz_spec → ask_question → record_answer → compute_result → persist_run
  - граф НЕ знает про Telegram, отдаёт “screen” (текст + варианты) как данные
2. Quiz spec (контент) без хардкода:
- хранить спецификацию квиза в `config/quiz/pharmacy_quiz.json`
- минимальный формат:
  - title
  - questions[]: {id, text, options[], correct_option_id?, score_map?}
  - result_rules[]: границы score → рекомендация
3. Сессии (state) для чата:
- хранить состояние квиза по `chat_id` (или session_id) в `storage/sessions/<chat_id>.json`
- state: agent="quiz", quiz_id, current_question_idx, answers[], score_so_far, run_id
4. Telegram UX:
- команда `/quiz_pharmacy` — старт квиза
- inline-кнопки вариантов ответа (callback_data содержит question_id + option_id)
- команда `/last_quiz` — показать последний результат квиза
- allowlist обязателен (как везде)
5. Артефакты (единый стандарт run):
- `storage/runs/<run_id>/run.json`:
  - `"agent": "quiz"`
  - `"quiz_id": "pharmacy"`
  - `"trigger": "manual" | "scheduled"`
- `storage/runs/<run_id>/quiz_answers.json` — ответы пользователя
- `storage/runs/<run_id>/quiz_result.json` — score + итоговая рекомендация
- `storage/artifacts/<run_id>/report.md` и `report.html` — человекочитаемый итог
- `storage/runs/<run_id>/steps.json` — timing шагов (как общий стандарт observability)
6. Настройки (если нужны новые ключи — обязательно через settings.yml + fail-fast):
- `quiz.enabled: bool`
- `quiz.default_id: "pharmacy"`
- `quiz.storage_dir: "storage/quiz"` (или вычислять от storage, но путь контролируемый)

DoD:
- `bash start.sh` работает
- `/quiz_pharmacy` запускает квиз и показывает первый вопрос с кнопками вариантов
- ответы кнопками проходят весь квиз до финального результата (score + рекомендация)
- `/last_quiz` показывает последний результат
- создаются артефакты run + session в `storage/`
- `pytest -q` проходит

### Итерация 10 — Explainable Recommendations v0 (OOS → Action) + LLM summary + WOW demo
**Статус: TODO**

Цель: показать клиенту “реального AI-агента” под ТЗ на минимальном объёме:
Telegram → запуск OOS → объяснимые рекомендации “что делать” → approve/reject → артефакты + trace.

Сделать:

1. Recommendation Engine v0 (rules + метрики)
* на базе результатов OOS (alerts/tasks) и мок-данных посчитать **рекомендации** в формате:
  * action: `restock_shelf` / `increase_order` / `reduce_order` / `rotate_sku`
  * reason (кратко)
  * metrics (2–3 числа): напр. `stock_on_hand`, `units_7d`, `days_of_cover`
  * expected_effect (heuristic): напр. “снизим потери продаж”, “уменьшим заморозку”
  * confidence: `high|medium|low` по простому правилу
* рекомендации **детерминированные** (без LLM в расчётах)
2. LLM summary (API) — только для текста
* LLM получает structured JSON (рекомендации + метрики) и возвращает:
  * 5–10 строк “операционного” текста без ML-терминов
  * **не меняет цифры**, только формулирует
* если LLM выключен/нет ключа — fallback на шаблонный текст (rules-only)
3. LangGraph trace (обязателен)
* OOS workflow должен явно включать шаги:
  * `collect_input` → `load_data` → `detect_oos` → `draft_tasks`
  * `build_recommendations` → `llm_explain` (optional) → `render_report` → `persist_run`
* в логах: `step=<name> duration_ms=<...>`
* в `storage/runs/<run_id>/steps.json` — тайминги шагов
4. Артефакты run (единый стандарт)
* `storage/runs/<run_id>/run.json` (agent=oos, trigger=manual/scheduled, counts)
* `storage/runs/<run_id>/alerts.json`
* `storage/runs/<run_id>/tasks*.json`
* `storage/runs/<run_id>/recommendations.json`
* `storage/artifacts/<run_id>/report.md` + `report.html`
* approve/reject сохраняет статус задач как сейчас
5. Telegram UX (не меняем сильно)
* `/run_oos` и кнопка “Run OOS Scan” возвращают **report с рекомендациями**
* `/last` показывает последний report (с рекомендациями)
* approve/reject работают как раньше
Настройки (fail-fast, без хардкода):
* `llm.enabled: bool`
* `llm.provider: "openai"` (пока один)
* `llm.model: "gpt-4o-mini"` (пример)
* `llm.api_key_env: "OPENAI_API_KEY"`
* `recommendations.enabled: bool`
* `recommendations.items_max: int` (например 10)

DoD:
* `bash start.sh` работает
* `/run_oos` → отчёт + 5–10 строк рекомендаций (action/reason/metrics/effect/confidence)
* approve/reject работает
* создаются: `recommendations.json`, `report.md/html`, `steps.json`
* логи содержат `step=... duration_ms=...` для рекомендаций
* `pytest -q` проходит (добавить тест на recommendations + fallback LLM off)

## Этап 3 — Enterprise hardening (после подтверждения проекта)
- multi-tenancy (tenants, namespaces, ACL)
- RBAC/SSO (Keycloak)
- real data integrations (1C/BI)
- полноценная observability/evals (Langfuse/Phoenix/LangSmith)
- безопасные политики (OWASP LLM Top 10 как чеклист)
