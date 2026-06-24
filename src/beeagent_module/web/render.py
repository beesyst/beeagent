from __future__ import annotations

from jinja2 import Environment, PackageLoader, select_autoescape

_env = Environment(
    loader=PackageLoader("beeagent_module.web", "templates"),
    autoescape=select_autoescape(["html", "xml"]),
)


def render_template(template_name: str, **context: object) -> str:
    template = _env.get_template(template_name)
    return template.render(**context)
