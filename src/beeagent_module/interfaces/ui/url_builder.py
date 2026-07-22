from __future__ import annotations

from urllib.parse import quote, urlencode


def _filter_qs_val(value: str | None) -> str | None:
    if value is not None and value.strip():
        return value.strip()
    return None


def _add_sort_pair(
    params: dict[str, str], sort: str | None, order: str | None
) -> None:
    """Add a complete non-default sort pair, never a partial pair."""
    if sort is None and order is None:
        return
    effective_sort = sort or "received_at"
    effective_order = order or "desc"
    if effective_sort == "received_at" and effective_order == "desc":
        return
    params["sort"] = effective_sort
    params["order"] = effective_order


def build_rop_url(
    *,
    tab: str = "overview",
    period: str | None = None,
    run_id: str | None = None,
    lang: str | None = None,
    page: int | None = None,
    page_size: int | None = None,
    sort: str | None = None,
    order: str | None = None,
    filter_params: dict[str, str] | None = None,
    extra: dict[str, str] | None = None,
) -> str:
    params: dict[str, str] = {}

    params["tab"] = tab

    if run_id is not None:
        rv = _filter_qs_val(run_id)
        if rv is not None:
            params["run_id"] = rv
    if period is not None:
        pv = _filter_qs_val(period)
        if pv is not None:
            params["period"] = pv
    if lang is not None:
        lv = _filter_qs_val(lang)
        if lv is not None and lv != "en":
            params["lang"] = lv
    if page is not None and page > 1:
        params["page"] = str(page)
    if page_size is not None and page_size != 25:
        params["page_size"] = str(page_size)
    _add_sort_pair(params, sort, order)

    if filter_params:
        for key, value in filter_params.items():
            fv = _filter_qs_val(value)
            if fv is not None:
                params[key] = fv

    if extra:
        for key, value in extra.items():
            ev = _filter_qs_val(value)
            if ev is not None:
                params[key] = ev

    if not params:
        return "/rop"

    return "/rop?" + urlencode(params, doseq=True)


def build_rop_event_url(
    event_id: str,
    run_id: str,
    *,
    period: str | None = None,
    lang: str | None = None,
    page: int | None = None,
    page_size: int | None = None,
    sort: str | None = None,
    order: str | None = None,
    filter_params: dict[str, str] | None = None,
) -> str:
    params: dict[str, str] = {"run_id": run_id}
    if period is not None:
        pv = _filter_qs_val(period)
        if pv is not None:
            params["period"] = pv
    if lang is not None and lang != "en":
        params["lang"] = lang
    if page is not None and page > 1:
        params["page"] = str(page)
    if page_size is not None and page_size != 25:
        params["page_size"] = str(page_size)
    _add_sort_pair(params, sort, order)
    for extra_params in (filter_params or {},):
        for key, value in extra_params.items():
            normalized = _filter_qs_val(value)
            if normalized is not None:
                params[key] = normalized
    return f"/rop/events/{quote(event_id, safe='')}?{urlencode(params, doseq=True)}"


def build_reset_url(
    tab: str = "queue",
    period: str | None = None,
    lang: str | None = None,
) -> str:
    return build_rop_url(tab=tab, period=period, lang=lang)
