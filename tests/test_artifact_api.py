import json
import logging
from pathlib import Path
from tempfile import TemporaryDirectory
from typing import Any, cast

from beeagent_module.core.artifact_api import ArtifactAPI
from beeagent_module.core.module_contract import AuthorityLevel
from beeagent_module.core.runtime_context import (
    RuntimeContext,
    generate_run_id,
    generate_session_id,
)


# Тесты для ArtifactAPI: проверка создания, валидации, записи и чтения артефактов, а также изоляции путей
def _create_test_context(
    run_id: str | None = None,
    module_id: str = "test-module",
) -> RuntimeContext:
    return RuntimeContext(
        run_id=run_id or generate_run_id(),
        session_id=generate_session_id(),
        case_type="test_case",
        module_id=module_id,
        authority=AuthorityLevel.READ_ONLY,
    )


# Helper to create a test ArtifactAPI with a logger
def _create_test_api(context: RuntimeContext, storage_dir: Path) -> ArtifactAPI:
    logger = logging.getLogger("test")
    return ArtifactAPI(context=context, storage_dir=storage_dir, logger=logger)


# Тест: проверка, что ArtifactAPI создается с правильным контекстом и директорией
def test_artifact_api_creation() -> None:
    with TemporaryDirectory() as tmp_dir:
        storage_dir = Path(tmp_dir)
        ctx = _create_test_context()
        api = _create_test_api(ctx, storage_dir)

        assert api.artifact_dir().exists()
        assert api.artifact_dir().parent == storage_dir / "runs" / ctx.run_id


# Тест: проверка, что ArtifactAPI rejects invalid context
def test_artifact_api_invalid_context() -> None:
    with TemporaryDirectory() as tmp_dir:
        storage_dir = Path(tmp_dir)
        logger = logging.getLogger("test")

        try:
            ArtifactAPI(
                context=cast(Any, "invalid"),
                storage_dir=storage_dir,
                logger=logger,
            )
            assert False, "Should reject non-RuntimeContext"
        except ValueError as e:
            assert "context" in str(e)


# Тест: проверка, что ArtifactAPI rejects invalid storage_dir
def test_artifact_api_invalid_storage_dir() -> None:
    ctx = _create_test_context()
    logger = logging.getLogger("test")

    try:
        ArtifactAPI(context=ctx, storage_dir=cast(Any, "invalid"), logger=logger)
        assert False, "Should reject non-Path storage_dir"
    except ValueError as e:
        assert "storage_dir" in str(e)


# Тест: проверка, что ArtifactAPI rejects invalid filename with slashes
def test_write_json_artifact() -> None:
    with TemporaryDirectory() as tmp_dir:
        storage_dir = Path(tmp_dir)
        ctx = _create_test_context()
        api = _create_test_api(ctx, storage_dir)

        data = {"key": "value", "number": 42}
        path = api.write_json("test.json", data)

        assert path.exists()
        assert path.name == "test.json"
        assert path.parent == api.artifact_dir()

        content = json.loads(path.read_text(encoding="utf-8"))
        assert content == data


# Тест: проверка, что ArtifactAPI rejects invalid filename with slashes
def test_write_text_artifact() -> None:
    with TemporaryDirectory() as tmp_dir:
        storage_dir = Path(tmp_dir)
        ctx = _create_test_context()
        api = _create_test_api(ctx, storage_dir)

        content = "This is a test report."
        path = api.write_text("report.txt", content)

        assert path.exists()
        assert path.read_text(encoding="utf-8") == content


# Тест: проверка, что ArtifactAPI rejects invalid filename with slashes
def test_read_json_artifact() -> None:
    with TemporaryDirectory() as tmp_dir:
        storage_dir = Path(tmp_dir)
        ctx = _create_test_context()
        api = _create_test_api(ctx, storage_dir)

        original_data = {"test": "data", "list": [1, 2, 3]}
        api.write_json("data.json", original_data)

        read_data = api.read_json("data.json")
        assert read_data == original_data


# Тест: проверка, что ArtifactAPI rejects invalid filename with slashes
def test_read_text_artifact() -> None:
    with TemporaryDirectory() as tmp_dir:
        storage_dir = Path(tmp_dir)
        ctx = _create_test_context()
        api = _create_test_api(ctx, storage_dir)

        original_content = "This is test content\nwith multiple lines."
        api.write_text("content.txt", original_content)

        read_content = api.read_text("content.txt")
        assert read_content == original_content


# Тест: проверка, что ArtifactAPI rejects invalid filename with slashes
def test_read_nonexistent_artifact() -> None:
    with TemporaryDirectory() as tmp_dir:
        storage_dir = Path(tmp_dir)
        ctx = _create_test_context()
        api = _create_test_api(ctx, storage_dir)

        try:
            api.read_json("nonexistent.json")
            assert False, "Should raise ValueError for nonexistent file"
        except ValueError as e:
            assert "not found" in str(e).lower()


# Тест: проверка, что ArtifactAPI rejects invalid filename with slashes
def test_invalid_filename_with_slash() -> None:
    with TemporaryDirectory() as tmp_dir:
        storage_dir = Path(tmp_dir)
        ctx = _create_test_context()
        api = _create_test_api(ctx, storage_dir)

        try:
            api.write_json("subdir/file.json", {"data": "value"})
            assert False, "Should reject filename with slash"
        except ValueError as e:
            assert "filename" in str(e).lower()


# Тест: проверка, что ArtifactAPI rejects invalid filename with backslashes
def test_invalid_filename_with_backslash() -> None:
    with TemporaryDirectory() as tmp_dir:
        storage_dir = Path(tmp_dir)
        ctx = _create_test_context()
        api = _create_test_api(ctx, storage_dir)

        try:
            api.write_json("subdir\\file.json", {"data": "value"})
            assert False, "Should reject filename with backslash"
        except ValueError as e:
            assert "filename" in str(e).lower()


# Тест: проверка, что execute_module_case создает артефакт с результатом модуля
def test_invalid_empty_filename() -> None:
    with TemporaryDirectory() as tmp_dir:
        storage_dir = Path(tmp_dir)
        ctx = _create_test_context()
        api = _create_test_api(ctx, storage_dir)

        try:
            api.write_json("", {"data": "value"})
            assert False, "Should reject empty filename"
        except ValueError as e:
            assert "filename" in str(e).lower()


# Тест: проверка, что execute_module_case создает артефакт с результатом модуля
def test_artifact_path_isolation() -> None:
    with TemporaryDirectory() as tmp_dir:
        storage_dir = Path(tmp_dir)
        run_id = generate_run_id()

        ctx1 = RuntimeContext(
            run_id=run_id,
            session_id=generate_session_id(),
            case_type="test",
            module_id="module-1",
            authority=AuthorityLevel.READ_ONLY,
        )

        ctx2 = RuntimeContext(
            run_id=run_id,
            session_id=generate_session_id(),
            case_type="test",
            module_id="module-2",
            authority=AuthorityLevel.READ_ONLY,
        )

        api1 = _create_test_api(ctx1, storage_dir)
        api2 = _create_test_api(ctx2, storage_dir)

        api1.write_json("output.json", {"module": 1})
        api2.write_json("output.json", {"module": 2})

        data1 = api1.read_json("output.json")
        data2 = api2.read_json("output.json")

        assert data1 == {"module": 1}
        assert data2 == {"module": 2}


#
def test_artifact_dir_path_format() -> None:
    with TemporaryDirectory() as tmp_dir:
        storage_dir = Path(tmp_dir)
        run_id = "run-test123"

        ctx = RuntimeContext(
            run_id=run_id,
            session_id="session-test456",
            case_type="test",
            module_id="my-module",
            authority=AuthorityLevel.READ_ONLY,
        )

        api = _create_test_api(ctx, storage_dir)
        artifact_dir = api.artifact_dir()

        assert artifact_dir.name == "module-my-module"
        assert artifact_dir.parent.name == run_id
        assert artifact_dir.parent.parent.name == "runs"


# Тест: проверка, что ArtifactAPI.list_artifacts возвращает правильные файлы
def test_list_artifacts() -> None:
    with TemporaryDirectory() as tmp_dir:
        storage_dir = Path(tmp_dir)
        ctx = _create_test_context()
        api = _create_test_api(ctx, storage_dir)

        assert api.list_artifacts() == []

        api.write_json("first.json", {"data": 1})
        api.write_text("second.txt", "content")
        api.write_json("third.json", {"data": 2})

        artifacts = api.list_artifacts()
        assert len(artifacts) == 3
        assert artifacts[0].name == "first.json"
        assert artifacts[1].name == "second.txt"
        assert artifacts[2].name == "third.json"


# Тест: проверка, что ArtifactAPI.list_artifacts возвращает пустой список для несуществующей директории
def test_list_artifacts_empty_directory() -> None:
    with TemporaryDirectory() as tmp_dir:
        storage_dir = Path(tmp_dir)

        ctx = RuntimeContext(
            run_id="run-nonexistent",
            session_id=generate_session_id(),
            case_type="test",
            module_id="test",
            authority=AuthorityLevel.READ_ONLY,
        )

        logger = logging.getLogger("test")

        api = ArtifactAPI(ctx, storage_dir, logger)

        api.artifact_dir().rmdir()

        assert api.list_artifacts() == []


# Тест: проверка, что ArtifactAPI.write_json и write_text поддерживают unicode символы
def test_write_json_with_unicode() -> None:
    with TemporaryDirectory() as tmp_dir:
        storage_dir = Path(tmp_dir)
        ctx = _create_test_context()
        api = _create_test_api(ctx, storage_dir)

        data = {"text": "Привет мир 你好", "emoji": "🚀"}
        api.write_json("unicode.json", data)

        read_data = api.read_json("unicode.json")
        assert read_data == data


# Тест: проверка, что ArtifactAPI.write_json и write_text поддерживают unicode символы
def test_write_text_with_unicode() -> None:
    with TemporaryDirectory() as tmp_dir:
        storage_dir = Path(tmp_dir)
        ctx = _create_test_context()
        api = _create_test_api(ctx, storage_dir)

        content = "こんにちは\nمرحبا\n🌍"
        api.write_text("unicode.txt", content)

        read_content = api.read_text("unicode.txt")
        assert read_content == content
