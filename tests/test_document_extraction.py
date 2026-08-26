from __future__ import annotations

import io
import logging
import os
import subprocess
import tempfile
import zipfile
from pathlib import Path

import pytest
from PIL import ImageFont

os.environ.setdefault("HF_HUB_OFFLINE", "1")
os.environ.setdefault("TRANSFORMERS_OFFLINE", "1")
os.environ.setdefault("HF_DATASETS_OFFLINE", "1")

from beeagent_module.core.attachment_store import persist_run_attachments
from beeagent_module.core.docling_reader import (
    _FORMAT_SUFFIXES,
    _build_ocr_options,
    convert_blob_item,
)
from beeagent_module.core.document_extraction import (
    _WORKER_OFFLINE_ENV,
    DOCLING_ENGINE,
    DocumentExtractionResult,
    _worker_environment,
    extract_attachment_documents,
)
from beeagent_module.core.document_extraction_worker import _apply_offline_env


def _logger() -> logging.Logger:
    logger = logging.getLogger("test_document_extraction")
    logger.addHandler(logging.NullHandler())
    logger.propagate = False
    return logger


def _extraction_settings(**overrides: object) -> dict:
    settings = {
        "engine": "docling",
        "chars_max": 2000,
        "pages_max": 20,
        "timeout_seconds": 60,
        "ocr_enabled": True,
    }
    settings.update(overrides)
    return settings


def _stored_event(tmp_path: Path, run_id: str, attachments: list[dict]) -> dict:
    event = {
        "event_id": "evt-1",
        "event_instance_id": "event-000001",
        "_raw_attachments": attachments,
    }
    manifest = persist_run_attachments(
        storage_dir=tmp_path,
        run_id=run_id,
        events=[event],
        attachment_settings={
            "enabled": True,
            "chars_max": 500,
            "size_max": 1048576,
            "types": ["text/plain"],
            "storage": {
                "enabled": True,
                "file_max": 10485760,
                "message_max": 20971520,
                "files_message_max": 20,
            },
        },
        logger=_logger(),
    )
    return manifest


def _raw_attachment(content: bytes, content_type: str = "text/plain") -> dict:
    return {
        "filename": "blob.bin",
        "content_type": content_type,
        "size": len(content),
        "payload": content,
        "storage_status": "stored",
        "reason_code": None,
    }


def _docx_bytes(text: str) -> bytes:
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as archive:
        archive.writestr(
            "[Content_Types].xml",
            '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
            '<Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types">'
            '<Default Extension="rels" ContentType="application/vnd.openxmlformats-package.relationships+xml"/>'
            '<Default Extension="xml" ContentType="application/xml"/>'
            '<Override PartName="/word/document.xml" '
            'ContentType="application/vnd.openxmlformats-officedocument.wordprocessingml.document.main+xml"/>'
            "</Types>",
        )
        archive.writestr(
            "_rels/.rels",
            '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
            '<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">'
            '<Relationship Id="rId1" '
            'Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/officeDocument" '
            'Target="word/document.xml"/></Relationships>',
        )
        archive.writestr(
            "word/document.xml",
            '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
            '<w:document xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main">'
            f"<w:body><w:p><w:r><w:t>{text}</w:t></w:r></w:p></w:body></w:document>",
        )
    return buf.getvalue()


def _xlsx_bytes() -> bytes:
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as archive:
        archive.writestr(
            "[Content_Types].xml",
            '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
            '<Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types">'
            '<Default Extension="rels" ContentType="application/vnd.openxmlformats-package.relationships+xml"/>'
            '<Default Extension="xml" ContentType="application/xml"/>'
            '<Override PartName="/xl/workbook.xml" '
            'ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet.main+xml"/>'
            '<Override PartName="/xl/worksheets/sheet1.xml" '
            'ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.worksheet+xml"/>'
            "</Types>",
        )
        archive.writestr(
            "_rels/.rels",
            '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
            '<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">'
            '<Relationship Id="rId1" '
            'Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/officeDocument" '
            'Target="xl/workbook.xml"/></Relationships>',
        )
        archive.writestr(
            "xl/workbook.xml",
            '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
            '<workbook xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main" '
            'xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships">'
            '<sheets><sheet name="Sheet1" sheetId="1" r:id="rId1"/></sheets></workbook>',
        )
        archive.writestr(
            "xl/_rels/workbook.xml.rels",
            '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
            '<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">'
            '<Relationship Id="rId1" '
            'Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/worksheet" '
            'Target="worksheets/sheet1.xml"/></Relationships>',
        )
        archive.writestr(
            "xl/worksheets/sheet1.xml",
            '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
            '<worksheet xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main">'
            "<sheetData>"
            '<row r="1"><c r="A1" t="inlineStr"><is><t>item</t></is></c>'
            '<c r="B1" t="inlineStr"><is><t>qty</t></is></c></row>'
            '<row r="2"><c r="A2" t="inlineStr"><is><t>ER70S-6</t></is></c>'
            '<c r="B2"><v>100</v></c></row>'
            "</sheetData></worksheet>",
        )
    return buf.getvalue()


def _text_pdf_bytes(text: str) -> bytes:
    content = f"({text}) Tj"
    return (
        "%PDF-1.4\n"
        "1 0 obj\n<< /Type /Catalog /Pages 2 0 R >>\nendobj\n"
        "2 0 obj\n<< /Type /Pages /Kids [3 0 R] /Count 1 >>\nendobj\n"
        "3 0 obj\n<< /Type /Page /Parent 2 0 R /MediaBox [0 0 612 792] "
        "/Contents 4 0 R /Resources << /Font << /F1 5 0 R >> >> >>\nendobj\n"
        f"4 0 obj\n<< /Length {len(content)} >>\nstream\n"
        f"BT /F1 24 Tf 72 720 Td {content} ET\nendstream\nendobj\n"
        "5 0 obj\n<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>\nendobj\n"
        "trailer\n<< /Root 1 0 R >>\n%%EOF\n"
    ).encode()


def _text_image_bytes(image_format: str, text: str) -> bytes:
    from PIL import Image, ImageDraw

    image = Image.new("RGB", (1600, 400), "white")
    draw = ImageDraw.Draw(image)
    draw.text((40, 150), text, fill="black")
    buf = io.BytesIO()
    image.save(buf, image_format)
    return buf.getvalue()


def _scanned_pdf_bytes(text: str) -> bytes:
    from PIL import Image, ImageDraw

    image = Image.new("RGB", (1600, 400), "white")
    draw = ImageDraw.Draw(image)
    draw.text((40, 150), text, fill="black")
    buf = io.BytesIO()
    image.save(buf, "PDF", resolution=200)
    return buf.getvalue()


def _read_blob(
    tmp_path: Path, run_id: str, attachment_id: str
) -> dict[str, object] | None:
    from beeagent_module.core.attachment_store import resolve_attachment_blob_path

    path = resolve_attachment_blob_path(tmp_path, run_id, attachment_id)
    if path is None:
        return None
    return {"blob_path": str(path)}


def _layout_model_available() -> bool:
    cache = (
        Path(os.path.expanduser("~"))
        / ".cache"
        / "huggingface"
        / "hub"
        / "models--docling-project--docling-layout-heron"
    )
    return cache.is_dir()


needs_layout_model = pytest.mark.skipif(
    not _layout_model_available(),
    reason="docling layout model is not prepared locally",
)


def _cyrillic_assets_available() -> bool:
    from beeagent_module.core.docling_reader import (
        _RAPIDOCR_ASSETS_DIR,
        _RAPIDOCR_DET_MODEL,
        _RAPIDOCR_REC_KEYS,
        _RAPIDOCR_REC_MODEL,
    )

    return all(
        (_RAPIDOCR_ASSETS_DIR / name).is_file()
        for name in (_RAPIDOCR_DET_MODEL, _RAPIDOCR_REC_MODEL, _RAPIDOCR_REC_KEYS)
    )


needs_cyrillic_assets = pytest.mark.skipif(
    not _cyrillic_assets_available(),
    reason="rapidocr cyrillic assets are not prepared locally",
)


def _cyrillic_font() -> ImageFont.FreeTypeFont | None:
    for path in (
        "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
        "/usr/share/fonts/truetype/liberation/LiberationSans-Regular.ttf",
        "/usr/share/fonts/truetype/freefont/FreeSans.ttf",
    ):
        if os.path.exists(path):
            return ImageFont.truetype(path, 44)
    return None


needs_cyrillic_font = pytest.mark.skipif(
    _cyrillic_font() is None,
    reason="no Cyrillic-capable truetype font is available",
)


def _cyrillic_image_bytes() -> bytes:
    from PIL import Image, ImageDraw

    image = Image.new("RGB", (2200, 560), "white")
    draw = ImageDraw.Draw(image)
    font = _cyrillic_font()
    draw.text((40, 60), "Запрос коммерческого предложения", fill="black", font=font)
    draw.text((40, 320), "Сварочная проволока", fill="black", font=font)
    buf = io.BytesIO()
    image.save(buf, "PNG")
    return buf.getvalue()


def _encrypted_pdf_bytes() -> bytes:
    import hashlib
    import struct

    def rc4(key: bytes, data: bytes) -> bytes:
        state = list(range(256))
        j = 0
        for i in range(256):
            j = (j + state[i] + key[i % len(key)]) & 0xFF
            state[i], state[j] = state[j], state[i]
        i = j = 0
        out = bytearray()
        for byte in data:
            i = (i + 1) & 0xFF
            j = (j + state[i]) & 0xFF
            state[i], state[j] = state[j], state[i]
            out.append(byte ^ state[(state[i] + state[j]) & 0xFF])
        return bytes(out)

    def pad_password(password: str) -> bytes:
        padding = (
            b"\x28\xbf\x4e\x5e\x4e\x75\x8a\x41\x64\x00\x4e\x56\xff\xfa\x01\x08"
            b"\x2e\x2e\x00\xb6\xd0\x68\x3e\x80\x2f\x0c\xa9\xfe\x64\x53\x69\x7a"
        )
        return (password.encode("latin-1") + padding)[:32]

    user_password = "secret"
    owner_password = "owner"
    permissions = 0xFFFFF0C0
    file_id = b"\x00\x01\x02\x03\x04\x05\x06\x07\x08\x09\x0a\x0b\x0c\x0d\x0e\x0f"
    key = hashlib.md5()
    key.update(pad_password(user_password))
    key.update(pad_password(owner_password))
    key.update(struct.pack("<I", permissions))
    key.update(file_id)
    encryption_key = key.digest()[:5]
    u_value = rc4(encryption_key, pad_password(""))
    content = b"BT /F1 24 Tf 72 720 Td (Secret encrypted text) Tj ET"
    object_key = hashlib.md5(encryption_key + struct.pack("<HH", 4, 0)).digest()[:10]
    encrypted_content = rc4(object_key, content)
    length = len(encrypted_content)
    return (
        b"%PDF-1.4\n"
        b"1 0 obj\n<< /Type /Catalog /Pages 2 0 R >>\nendobj\n"
        b"2 0 obj\n<< /Type /Pages /Kids [3 0 R] /Count 1 >>\nendobj\n"
        b"3 0 obj\n<< /Type /Page /Parent 2 0 R /MediaBox [0 0 612 792] "
        b"/Contents 4 0 R /Resources << /Font << /F1 5 0 R >> >> >>\nendobj\n"
        b"4 0 obj\n<< /Length "
        + str(length).encode()
        + b" >>\nstream\n"
        + encrypted_content
        + b"\nendstream\nendobj\n"
        b"5 0 obj\n<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>\nendobj\n"
        b"trailer\n<< /Root 1 0 R /Encrypt 6 0 R "
        b"/ID [<000102030405060708090a0b0c0d0e0f><000102030405060708090a0b0c0d0e0f>] >>\n"
        b"6 0 obj\n<< /Filter /Standard /V 1 /R 2 /O <"
        + owner_password.encode().hex().encode()
        + b"> /U <"
        + u_value.hex().encode()
        + b"> /P "
        + str(permissions).encode()
        + b" >>\nendobj\n"
        b"%%EOF\n"
    )


class TestResultContract:
    def test_result_has_product_neutral_fields(self) -> None:
        result = DocumentExtractionResult(
            attachment_id="att-1",
            status="ok",
            reason_code="docling_extraction_completed",
            engine=DOCLING_ENGINE,
            text="bounded text",
            text_length=12,
            is_truncated=False,
            content_type="text/plain",
            ocr_used=False,
            page_count=None,
        )
        assert result.engine == "docling"
        assert result.status == "ok"
        assert result.text_length == 12
        assert result.page_count is None


class TestWorkerFailureHandling:
    def test_worker_timeout_degrades_all(self, tmp_path: Path, monkeypatch) -> None:
        manifest = _stored_event(tmp_path, "run-1", [_raw_attachment(b"hello world")])
        monkeypatch.setattr(
            "beeagent_module.core.document_extraction.subprocess.run",
            lambda *a, **k: (_ for _ in ()).throw(
                subprocess.TimeoutExpired(cmd="worker", timeout=1)
            ),
        )
        results = extract_attachment_documents(
            storage_dir=tmp_path,
            run_id="run-1",
            attachment_items=[
                {
                    "attachment_id": manifest["items"][0]["attachment_id"],
                    "content_type": "text/plain",
                }
            ],
            extraction_settings=_extraction_settings(),
            logger=_logger(),
        )
        result = results[manifest["items"][0]["attachment_id"]]
        assert result.status == "failed"
        assert result.reason_code == "docling_worker_timeout"

    def test_worker_spawn_failure_degrades_all(
        self, tmp_path: Path, monkeypatch
    ) -> None:
        manifest = _stored_event(tmp_path, "run-1", [_raw_attachment(b"hello world")])
        monkeypatch.setattr(
            "beeagent_module.core.document_extraction.subprocess.run",
            lambda *a, **k: (_ for _ in ()).throw(OSError("spawn failed")),
        )
        results = extract_attachment_documents(
            storage_dir=tmp_path,
            run_id="run-1",
            attachment_items=[
                {
                    "attachment_id": manifest["items"][0]["attachment_id"],
                    "content_type": "text/plain",
                }
            ],
            extraction_settings=_extraction_settings(),
            logger=_logger(),
        )
        result = results[manifest["items"][0]["attachment_id"]]
        assert result.status == "failed"
        assert result.reason_code == "docling_worker_spawn_failed"

    def test_worker_nonzero_exit_degrades_all(
        self, tmp_path: Path, monkeypatch
    ) -> None:
        manifest = _stored_event(tmp_path, "run-1", [_raw_attachment(b"hello world")])
        monkeypatch.setattr(
            "beeagent_module.core.document_extraction.subprocess.run",
            lambda *a, **k: subprocess.CompletedProcess(
                args=[], returncode=1, stdout="", stderr="boom"
            ),
        )
        results = extract_attachment_documents(
            storage_dir=tmp_path,
            run_id="run-1",
            attachment_items=[
                {
                    "attachment_id": manifest["items"][0]["attachment_id"],
                    "content_type": "text/plain",
                }
            ],
            extraction_settings=_extraction_settings(),
            logger=_logger(),
        )
        result = results[manifest["items"][0]["attachment_id"]]
        assert result.status == "failed"
        assert result.reason_code == "docling_worker_no_result"

    def test_missing_blob_fails_without_worker(
        self, tmp_path: Path, monkeypatch
    ) -> None:
        calls: list[str] = []
        monkeypatch.setattr(
            "beeagent_module.core.document_extraction.subprocess.run",
            lambda *a, **k: (
                calls.append("run")
                or subprocess.CompletedProcess(
                    args=[], returncode=0, stdout="", stderr=""
                )
            ),
        )
        results = extract_attachment_documents(
            storage_dir=tmp_path,
            run_id="run-missing",
            attachment_items=[
                {"attachment_id": "evt-1-att-0", "content_type": "text/plain"}
            ],
            extraction_settings=_extraction_settings(),
            logger=_logger(),
        )
        assert calls == []
        assert results["evt-1-att-0"].reason_code == "attachment_blob_unavailable"


class TestWorkerEnvironment:
    _SENTINEL_SECRETS = (
        "OPENAI_API_KEY",
        "DEEPSEEK_API_KEY",
        "ANTHROPIC_API_KEY",
        "ROP_MAILBOX_USERNAME",
        "ROP_MAILBOX_PASSWORD",
        "BITRIX_WEBHOOK_URL",
        "BITRIX_WRITEBACK_WEBHOOK_URL",
        "BEEAGENT_WEB_ADMIN_TOKEN",
        "BEEAGENT_WEB_ROP_TOKEN",
        "BEEAGENT_WEB_OPERATOR_TOKEN",
        "BEEAGENT_WEB_SESSION_SECRET",
    )

    def test_sanitized_environment_strips_secrets(self, monkeypatch) -> None:
        for key in self._SENTINEL_SECRETS:
            monkeypatch.setenv(key, "sentinel-secret-value")

        env = _worker_environment()

        for key in self._SENTINEL_SECRETS:
            assert key not in env, f"secret {key} leaked into worker environment"
        for key, value in _WORKER_OFFLINE_ENV.items():
            assert env.get(key) == value

    def test_sanitized_environment_forces_offline(self, monkeypatch) -> None:
        monkeypatch.setenv("HF_HUB_OFFLINE", "0")
        monkeypatch.setenv("TRANSFORMERS_OFFLINE", "0")
        monkeypatch.setenv("HF_DATASETS_OFFLINE", "0")

        env = _worker_environment()

        assert env.get("HF_HUB_OFFLINE") == "1"
        assert env.get("TRANSFORMERS_OFFLINE") == "1"
        assert env.get("HF_DATASETS_OFFLINE") == "1"

    def test_worker_apply_offline_env_is_unconditional(self, monkeypatch) -> None:
        monkeypatch.setenv("HF_HUB_OFFLINE", "0")
        monkeypatch.setenv("TRANSFORMERS_OFFLINE", "0")
        monkeypatch.setenv("HF_DATASETS_OFFLINE", "0")

        _apply_offline_env()

        assert os.environ.get("HF_HUB_OFFLINE") == "1"
        assert os.environ.get("TRANSFORMERS_OFFLINE") == "1"
        assert os.environ.get("HF_DATASETS_OFFLINE") == "1"

    def test_worker_subprocess_receives_sanitized_env(
        self, tmp_path: Path, monkeypatch
    ) -> None:
        for key in self._SENTINEL_SECRETS:
            monkeypatch.setenv(key, "sentinel-secret-value")
        monkeypatch.setenv("HF_HUB_OFFLINE", "0")

        captured: dict[str, object] = {}
        monkeypatch.setattr(
            "beeagent_module.core.document_extraction.subprocess.run",
            lambda *a, **k: (
                captured.update(k)
                or subprocess.CompletedProcess(
                    args=[], returncode=0, stdout="", stderr=""
                )
            ),
        )
        manifest = _stored_event(tmp_path, "run-1", [_raw_attachment(b"hello")])
        extract_attachment_documents(
            storage_dir=tmp_path,
            run_id="run-1",
            attachment_items=[
                {
                    "attachment_id": manifest["items"][0]["attachment_id"],
                    "content_type": "text/plain",
                }
            ],
            extraction_settings=_extraction_settings(),
            logger=_logger(),
        )

        worker_env = captured["env"]
        assert isinstance(worker_env, dict)
        for key in self._SENTINEL_SECRETS:
            assert key not in worker_env, (
                f"secret {key} leaked into worker subprocess environment"
            )
        assert worker_env.get("HF_HUB_OFFLINE") == "1"
        assert worker_env.get("TRANSFORMERS_OFFLINE") == "1"
        assert worker_env.get("HF_DATASETS_OFFLINE") == "1"


class TestFormatSuffixMapping:
    def test_allowlisted_types_have_controlled_suffixes(self) -> None:
        for content_type in (
            "text/plain",
            "text/csv",
            "application/pdf",
            "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
            "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            "image/jpeg",
            "image/png",
        ):
            suffix = _FORMAT_SUFFIXES.get(content_type)
            assert suffix and suffix.startswith(".")
        assert "text/plain" in _FORMAT_SUFFIXES

    def test_suffixes_are_derived_from_content_type_only(self) -> None:
        assert _FORMAT_SUFFIXES["application/pdf"] == ".pdf"
        assert _FORMAT_SUFFIXES["image/png"] == ".png"


class TestOcrBackend:
    def test_explicit_backend_is_rapidocr_onnxruntime(self) -> None:
        options = _build_ocr_options(True)
        assert options is not None
        assert options.kind == "rapidocr"
        assert options.backend == "onnxruntime"

    def test_disabled_ocr_has_no_options(self) -> None:
        assert _build_ocr_options(False) is None

    def test_cyrillic_assets_are_pinned_when_ready(self) -> None:
        options = _build_ocr_options(True)
        assert options is not None
        if _cyrillic_assets_available():
            assert options.lang == ["cyrillic"]
            assert options.rec_model_path is not None
            assert options.rec_keys_path is not None

    def test_missing_cyrillic_assets_are_refused(self, monkeypatch) -> None:
        from beeagent_module.core import docling_reader

        monkeypatch.setattr(docling_reader, "_cyrillic_assets_ready", lambda: False)
        with pytest.raises(FileNotFoundError):
            _build_ocr_options(True)

    def test_missing_cyrillic_assets_degrades_extraction(
        self, tmp_path: Path, monkeypatch
    ) -> None:
        from beeagent_module.core import docling_reader

        monkeypatch.setattr(docling_reader, "_cyrillic_assets_ready", lambda: False)
        with tempfile.TemporaryDirectory() as td:
            target = Path(td) / "blob.bin"
            target.write_bytes(_text_image_bytes("PNG", "RFQ welding wire ER70S-6"))
            result = convert_blob_item(
                {
                    "index": 0,
                    "attachment_id": "att-missing-assets",
                    "blob_path": str(target),
                    "content_type": "image/png",
                    "chars_max": 2000,
                    "pages_max": 20,
                    "ocr_enabled": True,
                }
            )
        assert result["status"] == "failed"
        assert result["reason_code"] == "docling_assets_missing"
        assert result["text"] == ""


class TestRealExtraction:
    @pytest.mark.parametrize(
        "filename,content_type,payload,needle",
        [
            (
                "quote.txt",
                "text/plain",
                b"RFQ request for welding wire ER70S-6, 100 kg",
                "ER70S-6",
            ),
            (
                "prices.csv",
                "text/csv",
                b"item,quantity\nER70S-6,100\n",
                "ER70S-6",
            ),
            (
                "rfq.docx",
                "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
                _docx_bytes("RFQ for welding wire ER70S-6 100 kg"),
                "ER70S-6",
            ),
            (
                "prices.xlsx",
                "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                _xlsx_bytes(),
                "ER70S-6",
            ),
        ],
    )
    def test_common_formats_extract_locally(
        self,
        tmp_path: Path,
        filename: str,
        content_type: str,
        payload: bytes,
        needle: str,
    ) -> None:
        manifest = _stored_event(
            tmp_path,
            f"run-{filename.split('.')[0]}",
            [_raw_attachment(payload, content_type)],
        )
        attachment_id = manifest["items"][0]["attachment_id"]
        blob = _read_blob(tmp_path, f"run-{filename.split('.')[0]}", attachment_id)
        assert blob is not None
        with tempfile.TemporaryDirectory() as td:
            target = Path(td) / "blob.bin"
            target.write_bytes(Path(blob["blob_path"]).read_bytes())
            result = convert_blob_item(
                {
                    "index": 0,
                    "attachment_id": attachment_id,
                    "blob_path": str(target),
                    "content_type": content_type,
                    "chars_max": 2000,
                    "pages_max": 20,
                    "ocr_enabled": True,
                }
            )
        assert result["status"] == "ok"
        assert result["engine"] == "docling"
        assert result["reason_code"] == "docling_extraction_completed"
        assert needle in result["text"]
        assert result["is_truncated"] is False

    @needs_layout_model
    @pytest.mark.parametrize(
        "filename,content_type,payload,needle",
        [
            (
                "rfq.pdf",
                "application/pdf",
                _text_pdf_bytes("RFQ for welding wire ER70S-6"),
                "ER70S-6",
            ),
            (
                "rfq.jpg",
                "image/jpeg",
                _text_image_bytes("JPEG", "RFQ welding wire ER70S-6"),
                "ER70S-6",
            ),
            (
                "rfq.png",
                "image/png",
                _text_image_bytes("PNG", "RFQ welding wire ER70S-6"),
                "ER70S-6",
            ),
            (
                "scanned.pdf",
                "application/pdf",
                _scanned_pdf_bytes("RFQ welding wire ER70S-6"),
                "welding",
            ),
        ],
    )
    def test_pdf_and_image_ocr_extract_locally(
        self,
        tmp_path: Path,
        filename: str,
        content_type: str,
        payload: bytes,
        needle: str,
    ) -> None:
        manifest = _stored_event(
            tmp_path,
            f"run-{filename.split('.')[0]}",
            [_raw_attachment(payload, content_type)],
        )
        attachment_id = manifest["items"][0]["attachment_id"]
        blob = _read_blob(tmp_path, f"run-{filename.split('.')[0]}", attachment_id)
        assert blob is not None
        with tempfile.TemporaryDirectory() as td:
            target = Path(td) / "blob.bin"
            target.write_bytes(Path(blob["blob_path"]).read_bytes())
            result = convert_blob_item(
                {
                    "index": 0,
                    "attachment_id": attachment_id,
                    "blob_path": str(target),
                    "content_type": content_type,
                    "chars_max": 2000,
                    "pages_max": 20,
                    "ocr_enabled": True,
                }
            )
        assert result["status"] == "ok"
        assert result["engine"] == "docling"
        assert needle in result["text"]
        assert result["page_count"] == 1

    @needs_layout_model
    def test_image_ocr_reports_ocr_used(self, tmp_path: Path) -> None:
        payload = _text_image_bytes("PNG", "RFQ welding wire ER70S-6")
        with tempfile.TemporaryDirectory() as td:
            target = Path(td) / "blob.bin"
            target.write_bytes(payload)
            result = convert_blob_item(
                {
                    "index": 0,
                    "attachment_id": "att-ocr",
                    "blob_path": str(target),
                    "content_type": "image/png",
                    "chars_max": 2000,
                    "pages_max": 20,
                    "ocr_enabled": True,
                }
            )
        assert result["status"] == "ok"
        assert result["ocr_used"] is True

    @needs_layout_model
    @needs_cyrillic_assets
    @needs_cyrillic_font
    def test_cyrillic_russian_real_ocr_acceptance(self, tmp_path: Path) -> None:
        with tempfile.TemporaryDirectory() as td:
            target = Path(td) / "blob.bin"
            target.write_bytes(_cyrillic_image_bytes())
            result = convert_blob_item(
                {
                    "index": 0,
                    "attachment_id": "att-cyrillic",
                    "blob_path": str(target),
                    "content_type": "image/png",
                    "chars_max": 2000,
                    "pages_max": 20,
                    "ocr_enabled": True,
                }
            )
        assert result["status"] == "ok"
        assert result["engine"] == "docling"
        assert result["ocr_used"] is True
        assert "Запрос коммерческого предложения" in result["text"]
        assert "Сварочная проволока" in result["text"]

    def test_unsupported_content_type_degrades(self, tmp_path: Path) -> None:
        with tempfile.TemporaryDirectory() as td:
            target = Path(td) / "blob.bin"
            target.write_bytes(b"legacy doc bytes")
            result = convert_blob_item(
                {
                    "index": 0,
                    "attachment_id": "att-legacy",
                    "blob_path": str(target),
                    "content_type": "application/msword",
                    "chars_max": 2000,
                    "pages_max": 20,
                    "ocr_enabled": True,
                }
            )
        assert result["status"] == "unsupported"
        assert result["reason_code"] == "unsupported_content_type"

    @needs_layout_model
    def test_corrupt_pdf_degrades_without_crash(self, tmp_path: Path) -> None:
        with tempfile.TemporaryDirectory() as td:
            target = Path(td) / "blob.bin"
            target.write_bytes(b"%PDF-1.4 garbage not a real pdf")
            result = convert_blob_item(
                {
                    "index": 0,
                    "attachment_id": "att-corrupt",
                    "blob_path": str(target),
                    "content_type": "application/pdf",
                    "chars_max": 2000,
                    "pages_max": 20,
                    "ocr_enabled": True,
                }
            )
        assert result["status"] == "failed"
        assert result["text"] == ""

    @needs_layout_model
    def test_encrypted_pdf_degrades(self, tmp_path: Path) -> None:
        payload = _encrypted_pdf_bytes()
        with tempfile.TemporaryDirectory() as td:
            target = Path(td) / "blob.bin"
            target.write_bytes(payload)
            result = convert_blob_item(
                {
                    "index": 0,
                    "attachment_id": "att-encrypted",
                    "blob_path": str(target),
                    "content_type": "application/pdf",
                    "chars_max": 2000,
                    "pages_max": 20,
                    "ocr_enabled": True,
                }
            )
        assert result["status"] == "failed"
        assert result["text"] == ""
        assert isinstance(result["reason_code"], str)
        assert result["reason_code"]

    @needs_layout_model
    def test_encrypted_pdf_degrades_in_batch(self, tmp_path: Path) -> None:
        encrypted = _encrypted_pdf_bytes()
        manifest = _stored_event(
            tmp_path,
            "run-enc-batch",
            [
                _raw_attachment(b"RFQ for welding wire ER70S-6", "text/plain"),
                _raw_attachment(encrypted, "application/pdf"),
            ],
        )
        items = [
            {
                "attachment_id": item["attachment_id"],
                "content_type": item["content_type"],
            }
            for item in manifest["items"]
        ]
        results = extract_attachment_documents(
            storage_dir=tmp_path,
            run_id="run-enc-batch",
            attachment_items=items,
            extraction_settings=_extraction_settings(),
            logger=_logger(),
        )
        assert len(results) == 2
        valid = results[manifest["items"][0]["attachment_id"]]
        encrypted_result = results[manifest["items"][1]["attachment_id"]]
        assert valid.status == "ok"
        assert "ER70S-6" in valid.text
        assert encrypted_result.status == "failed"
        assert encrypted_result.text == ""
        assert isinstance(encrypted_result.reason_code, str)
        assert encrypted_result.reason_code


class TestBatchWorkerIntegration:
    def test_txt_batch_extraction_via_worker(self, tmp_path: Path) -> None:
        manifest = _stored_event(
            tmp_path,
            "run-batch",
            [
                _raw_attachment(b"RFQ for welding wire ER70S-6", "text/plain"),
                _raw_attachment(b"RFQ for welding wire ER70S-6", "text/plain"),
            ],
        )
        items = [
            {
                "attachment_id": item["attachment_id"],
                "content_type": item["content_type"],
            }
            for item in manifest["items"]
        ]
        results = extract_attachment_documents(
            storage_dir=tmp_path,
            run_id="run-batch",
            attachment_items=items,
            extraction_settings=_extraction_settings(),
            logger=_logger(),
        )
        assert len(results) == 2
        for result in results.values():
            assert result.status == "ok"
            assert result.engine == "docling"
            assert "ER70S-6" in result.text

    def test_original_filename_never_controls_extraction(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            target = Path(td) / "totally-unrelated-name.bin"
            target.write_bytes(b"RFQ for welding wire ER70S-6")
            result = convert_blob_item(
                {
                    "index": 0,
                    "attachment_id": "att-noext",
                    "blob_path": str(target),
                    "content_type": "text/plain",
                    "chars_max": 2000,
                    "pages_max": 20,
                    "ocr_enabled": True,
                }
            )
        assert result["status"] == "ok"
        assert "ER70S-6" in result["text"]
