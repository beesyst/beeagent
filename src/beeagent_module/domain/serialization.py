from dataclasses import asdict, is_dataclass
from typing import Any


def model_to_dict(value: Any) -> Any:
    if is_dataclass(value) and not isinstance(value, type):
        return asdict(value)

    if isinstance(value, list):
        return [model_to_dict(item) for item in value]

    if isinstance(value, dict):
        return {key: model_to_dict(item) for key, item in value.items()}

    return value
