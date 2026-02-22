import re


# Универсальные нормализаторы текста (без доменной логики и без i18n)
def normalize_bullets(text: str, bullet: str = "• ") -> str:
    lines = [ln.rstrip() for ln in text.splitlines() if ln.strip()]
    if not lines:
        return ""

    bullet_char = bullet.strip()

    normalized: list[str] = []
    for ln in lines:
        m = re.match(r"^(\s*)([•\-\*])\s+(.*)$", ln)
        if m:
            indent, _, rest = m.groups()
            normalized.append(f"{indent}{bullet_char} {rest.strip()}")
            continue

        indent = ln[: len(ln) - len(ln.lstrip())]
        normalized.append(f"{indent}{bullet_char} {ln.strip()}")

    return "\n".join(normalized)
