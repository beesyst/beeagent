from __future__ import annotations

from pathlib import Path
from typing import Any

import yaml

_LABELS_EN: dict[str, str] = {
    "Dashboard": "Dashboard",
    "ROP Dashboard": "ROP Dashboard",
    "Run Overview": "Run Overview",
    "Connected Sources": "Connected Sources",
    "Loaded Items": "Loaded Items",
    "Classified Cases": "Classified Cases",
    "Need Review": "Need Review",
    "High-Priority Cases": "High-Priority Cases",
    "Recommendations": "Recommendations",
    "Evidence & Exports": "Evidence & Exports",
    "Source Health": "Source Health",
    "Processing Funnel": "Processing Funnel",
    "Classification Breakdown": "Classification Breakdown",
    "Operator Queue": "Operator Queue",
    "Attachment Processing": "Attachment Processing",
    "Modules": "Modules",
    "System Health": "System Health",
    "Quick Links": "Quick Links",
    "Technical details": "Technical details",
    "Open ROP Dashboard": "Open ROP Dashboard",
    "Open Latest Run": "Open Latest Run",
    "Open Modules": "Open Modules",
    "More runs": "More runs",
    "All runs": "All runs",
    "Total Runs": "Total Runs",
    "Loaded Modules": "Loaded Modules",
    "Latest Run Status": "Latest Run Status",
    "ROP Classified Cases": "ROP Classified Cases",
    "Needs Review": "Needs Review",
    "Degraded Sources": "Degraded Sources",
    "Latest Activity": "Latest Activity",
    "Modules Overview": "Modules Overview",
    "ROP Snapshot": "ROP Snapshot",
    "Latest run": "Latest run",
    "KPIs": "KPIs",
    "Summary": "Summary",
    "No latest run available.": "No latest run available.",
    "No KPI items available.": "No KPI items available.",
    "No summary data available.": "No summary data available.",
    "Adapter-backed product overview": "Adapter-backed product overview",
    "Review high-priority events": "Review high-priority events",
    "Review fallback classifications": "Review fallback classifications",
    "Check degraded sources": "Check degraded sources",
    "Investigate malformed source items": "Investigate malformed source items",
    "Classification produced no output": "Classification produced no output",
    "Review blocked/refused attachments": "Review blocked/refused attachments",
    "Open review TSV": "Open review TSV",
}
_LABELS_RU: dict[str, str] = {
    "Dashboard": "Дашборд",
    "ROP Dashboard": "ROP Дашборд",
    "Run Overview": "Обзор запуска",
    "Connected Sources": "Подключенные источники",
    "Loaded Items": "Загружено элементов",
    "Classified Cases": "Классифицировано",
    "Need Review": "Требуют проверки",
    "High-Priority Cases": "Высокий приоритет",
    "Recommendations": "Рекомендации",
    "Evidence & Exports": "Доказательства и экспорт",
    "Source Health": "Состояние источников",
    "Processing Funnel": "Воронка обработки",
    "Classification Breakdown": "Распределение классификаций",
    "Operator Queue": "Очередь оператора",
    "Attachment Processing": "Обработка вложений",
    "Modules": "Модули",
    "System Health": "Система",
    "Quick Links": "Быстрые ссылки",
    "Technical details": "Технические детали",
    "Open ROP Dashboard": "Открыть ROP дашборд",
    "Open Latest Run": "Открыть последний запуск",
    "Open Modules": "Модули",
    "More runs": "Ещё запуски",
    "All runs": "Все запуски",
    "Total Runs": "Всего запусков",
    "Loaded Modules": "Загружено модулей",
    "Latest Run Status": "Статус последнего запуска",
    "ROP Classified Cases": "ROP классификаций",
    "Needs Review": "Требуют проверки",
    "Degraded Sources": "Проблемные источники",
    "Latest Activity": "Последняя активность",
    "Modules Overview": "Обзор модулей",
    "ROP Snapshot": "ROP сводка",
    "Latest run": "Последний запуск",
    "KPIs": "KPI",
    "Summary": "Сводка",
    "No latest run available.": "Нет данных о последнем запуске.",
    "No KPI items available.": "Нет KPI данных.",
    "No summary data available.": "Нет сводных данных.",
    "Adapter-backed product overview": "Обзор продуктовой консоли",
    "Review high-priority events": "Проверьте события высокого приоритета",
    "Review fallback classifications": "Проверьте fallback-классификации",
    "Check degraded sources": "Проверьте проблемные источники",
    "Investigate malformed source items": "Проверьте поврежденные элементы",
    "Classification produced no output": "Классификация не дала результатов",
    "Review blocked/refused attachments": "Проверьте заблокированные вложения",
    "Open review TSV": "Открыть TSV для проверки",
}


# Загрузка конфигурации локализации из beeui.yml
def _load_beeui_config_locale(project_root: Path | None = None) -> dict[str, Any]:
    if project_root is None:
        project_root = Path(__file__).resolve().parent.parent.parent.parent.parent
    config_path = project_root / "config" / "beeui.yml"
    try:
        with config_path.open("r", encoding="utf-8") as f:
            data = yaml.safe_load(f)
        locale_cfg = (data or {}).get("app", {}).get("locale", {})
        return {
            "default": locale_cfg.get("default", "en"),
            "available": locale_cfg.get("available", ["en"]),
        }
    except FileNotFoundError, yaml.YAMLError, OSError:
        return {"default": "en", "available": ["en"]}


# Определение локали на основе параметра ?lang= и доступных локалей
def resolve_locale(lang_param: str | None, config: dict[str, Any] | None = None) -> str:
    if config is None:
        config = _load_beeui_config_locale()
    if lang_param and lang_param in config.get("available", ["en"]):
        return lang_param
    return config.get("default", "en")


# Получение конфигурации локали
def get_locale_config() -> dict[str, Any]:
    return _load_beeui_config_locale()


# Перевод меток на заданную локаль
def t(label: str, locale: str = "en") -> str:
    if locale == "ru":
        return _LABELS_RU.get(label, label)
    return _LABELS_EN.get(label, label)


# Возврат словаря всех переведенных меток для заданной локали
def translate_labels(locale: str) -> dict[str, str]:
    if locale == "ru":
        return dict(_LABELS_RU)
    return dict(_LABELS_EN)
