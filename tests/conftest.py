from __future__ import annotations

import os


os.environ["BITRIX_WRITEBACK_WEBHOOK_URL"] = (
    "https://portal.test/rest/1/writetoken/"
)
os.environ["BITRIX_WEBHOOK_URL"] = "https://portal.test/rest/1/readonlytoken/"
