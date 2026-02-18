from beeagent_module.domain.models import Alert, ShelfSignal, StockRow


# Правило A: stock_on_hand > 0 И seen_on_shelf == false → OOS алерт
def detect_rule_a(
    stock_rows: list[StockRow],
    shelf_signals: list[ShelfSignal],
    sku_id: str,
    store_id: str,
    date: str,
) -> list[Alert]:

    alerts = []

    # найти запись о запасах для этой даты/магазина/sku
    stock_record = next(
        (
            s
            for s in stock_rows
            if s.date == date and s.store_id == store_id and s.sku_id == sku_id
        ),
        None,
    )

    # найти сигнал полки для этой даты/магазина/sku
    shelf_record = next(
        (
            s
            for s in shelf_signals
            if s.date == date and s.store_id == store_id and s.sku_id == sku_id
        ),
        None,
    )

    # применить правило A: stock_on_hand > 0 И seen_on_shelf == false
    if (
        stock_record
        and shelf_record
        and stock_record.stock_on_hand > 0
        and not shelf_record.seen_on_shelf
    ):
        alert = Alert(
            store_id=store_id,
            sku_id=sku_id,
            rule_id="RULE_A",
            severity="high",
            details=f"Stock on hand {stock_record.stock_on_hand} but not visible on shelf (date: {date})",
        )
        alerts.append(alert)

    return alerts
