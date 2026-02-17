# DEV_GUIDE — запуск, логи, режимы (BeeAgent)

## 1) Требования
- Python 3.12+
- uv (менеджер окружений/зависимостей)
- Telegram Bot Token (для запуска UI в Telegram)
- (опционально) OpenAI API key — если включим LLM-объяснения

## 2) Установка (dev)
1) Установить uv (один раз в системе)
2) В корне проекта:
   - `uv sync`

Запуск выполняй через `uv run`, активация venv не нужна.

## 3) Настройка
- Скопировать `.env.example` → `.env`
- Заполнить ключи:
  - `TELEGRAM_BOT_TOKEN=...`
  - (опционально) `OPENAI_API_KEY=...`
- Проверить `config/settings.yml` (пороги, allowlist, режимы)

## 4) Запуск
- `bash start.sh`

`start.sh` делает:
- `uv sync`
- `uv run python3 config/start.py`

## 5) Режимы
В BeeAgent режимы такие:

- **manual-run** (через Telegram): запуск по команде `/run_oos` или кнопке
- **scheduled-run** (позже): запуск по расписанию (но с approval gate)
- **dry-run** (по умолчанию для pre-MVP): ничего не меняет в системах клиента, только:
  - считает алерты
  - формирует задачи как `draft`
  - генерирует отчёт

> Важно: любые “действия” (создание задач как “готовых”) — только после approve.

## 6) Логи
- stdout
- `logs/app.log`

Формат: время + уровень + сообщение.
Секреты в логах запрещены.

## 7) Артефакты в storage/
Минимальный набор для pre-MVP:

- `storage/mock/<dataset_id>/...` — мок-датасеты (генерация/фикстуры)
- `storage/runs/<run_id>/run.json` — мета-инфо о запуске
- `storage/runs/<run_id>/alerts.json` — найденные отклонения / OOS
- `storage/runs/<run_id>/tasks.json` — задачи (draft/approved/rejected)
- `storage/artifacts/<run_id>/report.md` — текстовый отчёт (Telegram-friendly)
- `storage/artifacts/<run_id>/report.html` — “красивый” отчёт (для демонстрации)
- (опционально) `storage/artifacts/<run_id>/report.xlsx` — Excel отчёт

## 8) Правило безопасности (must-have)
Даже если агент “уверен”, система может/должна отказаться от действий:
- нет approval
- пользователь не в allowlist
- данные пустые/сомнительные (например, нет stock или нет shelf_signal)
- превышены лимиты/ограничения, заданные в правилах (позже)

## 9) Copilot / AI prompt template (BeeAgent)
Нужно внести изменения в проект BeeAgent (НЕ только в текущий файл).

**Контекст**
- Проект: BeeAgent (Python 3.12+, uv)
- Цель: pre-MVP demo (Telegram → LangGraph → mock data → report → approval)
- Архитектура: маленькие итерации, артефакты в `storage/`, логи в `logs/app.log`
- Источник правды: `config/settings.yml` (никаких “скрытых” дефолтов для обязательных ключей)
- Интеграции: сейчас только mock adapter (реальная 1C будет позже)

**Правила**
- Сначала прочитай (open/read) все перечисленные файлы и только потом предлагай правки.
- Если в процессе понял, что нужен ещё файл — добавь его в список “Файлы” и тоже прочитай.
- Правки делай только в рамках текущей задачи/итерации. Не рефактори “просто так”.
- Источник правды: `config/settings.yml`. Обязательные ключи не имеют дефолтов в коде. Если ключа нет — fail fast с понятной ошибкой на старте.
- После правок обнови/добавь валидацию в `core/settings.py` для новых обязательных ключей.
- Добавляй короткие русские комментарии в коде перед каждой функцией в формате `# Русский комментарий`, а логи и всё остальное должно быть на английском.
- После проделанной работы сделай короткий чеклист для отчёта.

**Ограничения**
- KISS: минимальные изменения, без лишней абстракции
- PEP 8: имена, длина строк, структура

**Формат ответа**
- Ответ строго в формате: Что прочитал → План → Было → Стало → Почему
- Без diff, без лишних рассуждений
- Если нужна новая функция/класс: укажи точное место вставки (до/после блока)
- Для новых артефактов в storage: покажи пример 1 объекта (json) или 1 строки (jsonl)

**Задача**
<опиши задачу одной фразой>

**Файлы**
- README.ru.md (если есть)
- docs/SPEC.md
- docs/ROADMAP.md
- config/start.py
- config/settings.yml
- src/beeagent_module/core/settings.py
- src/beeagent_module/core/paths.py
- src/beeagent_module/core/log.py
- src/beeagent_module/ui/telegram_bot.py
- src/beeagent_module/agents/oos/graph.py
- src/beeagent_module/agents/oos/rules.py
- src/beeagent_module/adapters/mock.py
- src/beeagent_module/storage/fs.py
(добавь другие, если нужно)

**Ожидаемый результат**
- `bash start.sh` работает
- `/run_oos` в Telegram отдаёт отчёт
- создаются артефакты в `storage/`
- `pytest -q` проходит
