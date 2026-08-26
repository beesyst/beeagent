from __future__ import annotations

import os
import tempfile
from pathlib import Path
from typing import Any

from docling.datamodel.base_models import InputFormat
from docling.datamodel.pipeline_options import PdfPipelineOptions, RapidOcrOptions
from docling.document_converter import (
    DocumentConverter,
    ImageFormatOption,
    PdfFormatOption,
)

_DOCLING_ENGINE = "docling"
_TEXT_CONTENT_TYPES = frozenset({"text/plain", "text/csv"})
_PDF_CONTENT_TYPES = frozenset({"application/pdf"})
_DOCX_CONTENT_TYPES = frozenset(
    {"application/vnd.openxmlformats-officedocument.wordprocessingml.document"}
)
_XLSX_CONTENT_TYPES = frozenset(
    {
        "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    }
)
_IMAGE_CONTENT_TYPES = frozenset({"image/jpeg", "image/png"})
_FORMAT_SUFFIXES = {
    "text/plain": ".txt",
    "text/csv": ".csv",
    "application/pdf": ".pdf",
    "application/vnd.openxmlformats-officedocument.wordprocessingml.document": ".docx",
    "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet": ".xlsx",
    "image/jpeg": ".jpg",
    "image/png": ".png",
}

_RAPIDOCR_ENGINE_BACKEND = "onnxruntime"
_RAPIDOCR_CYRILLIC_LANG = "cyrillic"
_RAPIDOCR_ASSETS_DIR = (
    Path(os.path.expanduser("~")) / ".cache" / "beeagent" / "rapidocr"
)
_RAPIDOCR_DET_MODEL = "ch_PP-OCRv5_det_mobile.onnx"
_RAPIDOCR_REC_MODEL = "cyrillic_PP-OCRv5_rec_mobile.onnx"
_RAPIDOCR_REC_KEYS = "ppocrv5_cyrillic_dict.txt"
_RAPIDOCR_CLS_MODEL = "ch_ppocr_mobile_v2.0_cls_mobile.onnx"
_RAPIDOCR_MODEL_BASE_URL = (
    "https://www.modelscope.cn/models/RapidAI/RapidOCR/resolve/v3.9.2/"
)
_RAPIDOCR_ASSET_URLS = {
    _RAPIDOCR_DET_MODEL: _RAPIDOCR_MODEL_BASE_URL
    + "onnx/PP-OCRv5/det/ch_PP-OCRv5_det_mobile.onnx",
    _RAPIDOCR_REC_MODEL: _RAPIDOCR_MODEL_BASE_URL
    + "onnx/PP-OCRv5/rec/cyrillic_PP-OCRv5_rec_mobile.onnx",
    _RAPIDOCR_REC_KEYS: _RAPIDOCR_MODEL_BASE_URL
    + "paddle/PP-OCRv5/rec/cyrillic_PP-OCRv5_rec_mobile/ppocrv5_cyrillic_dict.txt",
}

_converters: dict[str, DocumentConverter] = {}


def _text_converter() -> DocumentConverter:
    if "text" not in _converters:
        _converters["text"] = DocumentConverter(
            allowed_formats=[
                InputFormat.MD,
                InputFormat.CSV,
                InputFormat.DOCX,
                InputFormat.XLSX,
            ]
        )
    return _converters["text"]


def _rapidocr_models_dir() -> Path | None:
    try:
        import rapidocr
    except ImportError:
        return None
    models_dir = Path(rapidocr.__file__).resolve().parent / "models"
    return models_dir if models_dir.is_dir() else None


def _cyrillic_assets_ready() -> bool:
    return all(
        (_RAPIDOCR_ASSETS_DIR / name).is_file()
        for name in (_RAPIDOCR_DET_MODEL, _RAPIDOCR_REC_MODEL, _RAPIDOCR_REC_KEYS)
    )


def _build_ocr_options(ocr_enabled: bool) -> RapidOcrOptions | None:
    if not ocr_enabled:
        return None
    models_dir = _rapidocr_models_dir()
    if (
        not _cyrillic_assets_ready()
        or models_dir is None
        or not (models_dir / _RAPIDOCR_CLS_MODEL).is_file()
    ):
        raise FileNotFoundError("RapidOCR Cyrillic assets are not prepared")
    return RapidOcrOptions(
        backend=_RAPIDOCR_ENGINE_BACKEND,
        lang=[_RAPIDOCR_CYRILLIC_LANG],
        det_model_path=str(_RAPIDOCR_ASSETS_DIR / _RAPIDOCR_DET_MODEL),
        cls_model_path=str(models_dir / _RAPIDOCR_CLS_MODEL),
        rec_model_path=str(_RAPIDOCR_ASSETS_DIR / _RAPIDOCR_REC_MODEL),
        rec_keys_path=str(_RAPIDOCR_ASSETS_DIR / _RAPIDOCR_REC_KEYS),
    )


def prepare_rapidocr_assets() -> None:
    import urllib.request

    _RAPIDOCR_ASSETS_DIR.mkdir(parents=True, exist_ok=True)
    for filename, url in _RAPIDOCR_ASSET_URLS.items():
        destination = _RAPIDOCR_ASSETS_DIR / filename
        if destination.is_file() and destination.stat().st_size > 0:
            continue
        with urllib.request.urlopen(url, timeout=60) as response:
            payload = response.read()
        temporary = destination.with_name(destination.name + ".tmp")
        temporary.write_bytes(payload)
        temporary.replace(destination)


def _pipeline_converter(ocr_enabled: bool) -> DocumentConverter:
    key = f"pipeline:{ocr_enabled}"
    if key not in _converters:
        opts = PdfPipelineOptions()
        opts.force_backend_text = True
        opts.do_ocr = ocr_enabled
        opts.do_table_structure = False
        opts.do_picture_classification = False
        opts.do_picture_description = False
        opts.do_chart_extraction = False
        opts.do_code_enrichment = False
        opts.do_formula_enrichment = False
        ocr_options = _build_ocr_options(ocr_enabled)
        if ocr_options is not None:
            opts.ocr_options = ocr_options
        _converters[key] = DocumentConverter(
            format_options={
                InputFormat.PDF: PdfFormatOption(pipeline_options=opts),
                InputFormat.IMAGE: ImageFormatOption(pipeline_options=opts),
            }
        )
    return _converters[key]


def _bounded_text(value: str, max_length: int) -> tuple[str, bool]:
    text = " ".join(
        value.replace("\t", " ").replace("\n", " ").replace("\r", " ").split()
    )
    if max_length > 0 and len(text) > max_length:
        return text[:max_length], True
    return text, False


def _ocr_used(conversion_result: Any) -> bool:
    confidence = getattr(conversion_result, "confidence", None)
    pages = getattr(confidence, "pages", None)
    if not pages:
        return False
    for page_confidence in pages.values():
        score = getattr(page_confidence, "ocr_score", None)
        if isinstance(score, float) and not _is_nan(score) and score > 0:
            return True
    return False


def _is_nan(value: float) -> bool:
    return value != value


def _page_count(conversion_result: Any) -> int | None:
    document = getattr(conversion_result, "document", None)
    pages = getattr(document, "pages", None)
    if not pages:
        return None
    return len(pages)


def _convert_item(
    blob_path: Path,
    content_type: str,
    chars_max: int,
    pages_max: int,
    ocr_enabled: bool,
) -> dict[str, Any]:
    if content_type in _TEXT_CONTENT_TYPES:
        converter = _text_converter()
    elif content_type in _PDF_CONTENT_TYPES or content_type in _IMAGE_CONTENT_TYPES:
        converter = _pipeline_converter(ocr_enabled)
    elif content_type in _DOCX_CONTENT_TYPES or content_type in _XLSX_CONTENT_TYPES:
        converter = _text_converter()
    else:
        return {
            "status": "unsupported",
            "reason_code": "unsupported_content_type",
            "engine": "none",
            "text": "",
            "text_length": 0,
            "is_truncated": False,
            "content_type": content_type,
            "ocr_used": False,
            "page_count": None,
        }

    suffix = _FORMAT_SUFFIXES.get(content_type, "")
    source_path = _controlled_source_path(blob_path, suffix)
    try:
        conversion_result = converter.convert(
            source_path,
            raises_on_error=True,
            max_num_pages=pages_max,
        )
    finally:
        if source_path != blob_path:
            _unlink(source_path)
    document = conversion_result.document
    full_text = document.export_to_markdown() if document is not None else ""
    bounded, is_truncated = _bounded_text(full_text, chars_max)
    return {
        "status": "ok",
        "reason_code": "docling_extraction_completed",
        "engine": _DOCLING_ENGINE,
        "text": bounded,
        "text_length": len(bounded),
        "is_truncated": is_truncated,
        "content_type": content_type,
        "ocr_used": _ocr_used(conversion_result),
        "page_count": _page_count(conversion_result),
    }


def _controlled_source_path(blob_path: Path, suffix: str) -> Path:
    if not suffix:
        return blob_path
    fd, temporary = tempfile.mkstemp(prefix="docling_", suffix=suffix)
    try:
        with os.fdopen(fd, "wb") as handle:
            handle.write(blob_path.read_bytes())
    except Exception:
        os.close(fd)
        _unlink(Path(temporary))
        raise
    return Path(temporary)


def _unlink(path: Path) -> None:
    try:
        path.unlink(missing_ok=True)
    except OSError:
        pass


def convert_blob_item(item: dict[str, Any]) -> dict[str, Any]:
    attachment_id = str(item.get("attachment_id") or "")
    content_type = str(item.get("content_type") or "").strip().lower()
    blob_path = Path(str(item.get("blob_path") or ""))
    chars_max = int(item.get("chars_max") or 0)
    pages_max = int(item.get("pages_max") or 0)
    ocr_enabled = bool(item.get("ocr_enabled"))
    base = {
        "attachment_id": attachment_id,
        "content_type": content_type,
        "engine": _DOCLING_ENGINE,
        "text": "",
        "text_length": 0,
        "is_truncated": False,
        "ocr_used": False,
        "page_count": None,
    }
    if not blob_path.is_file():
        base.update({"status": "failed", "reason_code": "attachment_blob_unavailable"})
        return base
    try:
        result = _convert_item(
            blob_path=blob_path,
            content_type=content_type,
            chars_max=chars_max,
            pages_max=pages_max,
            ocr_enabled=ocr_enabled,
        )
    except Exception as exc:
        base.update(
            {
                "status": "failed",
                "reason_code": _classify_failure(exc),
            }
        )
        return base
    result["attachment_id"] = attachment_id
    return result


def _classify_failure(exc: Exception) -> str:
    name = type(exc).__name__
    message = str(exc)
    if name == "LocalEntryNotFoundError":
        return "docling_model_assets_missing"
    if name == "FileNotFoundError":
        return "docling_assets_missing"
    if name == "ImportError" or name == "ModuleNotFoundError":
        return "docling_dependency_missing"
    if "timeout" in message.lower() or "timed out" in message.lower():
        return "docling_timeout"
    if name in ("ValueError", "TypeError"):
        return "docling_conversion_failed"
    return "docling_extraction_failed"
