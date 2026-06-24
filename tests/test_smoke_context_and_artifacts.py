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


def test_smoke_context_and_artifact_together() -> None:
    with TemporaryDirectory() as tmp_dir:
        storage_dir = Path(tmp_dir)
        run_id = generate_run_id()
        session_id = generate_session_id()
        context = RuntimeContext(
            run_id=run_id,
            session_id=session_id,
            case_type="lead_classification",
            module_id="beeagent-rop",
            authority=AuthorityLevel.DRAFT_ONLY,
            payload={"email": "test@example.com", "category": "sales"},
        )

        logger = logging.getLogger("module-execution")
        api = ArtifactAPI(context=context, storage_dir=storage_dir, logger=logger)

        api.write_json(
            "classification.json",
            {
                "email": context.payload.get("email"),
                "predicted_category": "sales",
                "confidence": 0.95,
            },
        )

        api.write_json(
            "metadata.json",
            {
                "run_id": context.run_id,
                "session_id": context.session_id,
                "module_id": context.module_id,
                "case_type": context.case_type,
                "authority": context.authority.value,
            },
        )

        api.write_text(
            "report.txt",
            f"""
        Module: {context.module_id}
        Run: {context.run_id}
        Case: {context.case_type}
        Authority: {context.authority.value}
        """.strip(),
        )

        artifact_dir = api.artifact_dir()
        assert artifact_dir.exists()

        assert artifact_dir.name == f"module-{context.module_id}"
        assert artifact_dir.parent.name == run_id
        assert artifact_dir.parent.parent.name == "runs"

        classification = cast(dict[str, Any], api.read_json("classification.json"))
        assert classification["predicted_category"] == "sales"

        metadata = cast(dict[str, Any], api.read_json("metadata.json"))
        assert metadata["run_id"] == run_id
        assert metadata["session_id"] == session_id
        assert metadata["authority"] == "draft_only"

        report = api.read_text("report.txt")
        assert context.module_id in report
        assert run_id in report


def test_smoke_multiple_modules_same_run() -> None:
    with TemporaryDirectory() as tmp_dir:
        storage_dir = Path(tmp_dir)

        run_id = generate_run_id()
        session_id = generate_session_id()

        ctx1 = RuntimeContext(
            run_id=run_id,
            session_id=session_id,
            case_type="lead_classification",
            module_id="beeagent-rop",
            authority=AuthorityLevel.DRAFT_ONLY,
            payload={"email": "test@example.com"},
        )

        ctx2 = RuntimeContext(
            run_id=run_id,
            session_id=session_id,
            case_type="document_analysis",
            module_id="beescan",
            authority=AuthorityLevel.READ_ONLY,
            payload={"doc_id": "123"},
        )

        logger = logging.getLogger("modules")
        api1 = ArtifactAPI(context=ctx1, storage_dir=storage_dir, logger=logger)
        api2 = ArtifactAPI(context=ctx2, storage_dir=storage_dir, logger=logger)

        api1.write_json("result.json", {"classification": "sales"})
        api2.write_json("result.json", {"scan_result": "clean"})

        result1 = api1.read_json("result.json")
        result2 = api2.read_json("result.json")

        assert result1 == {"classification": "sales"}
        assert result2 == {"scan_result": "clean"}

        run_dir = storage_dir / "runs" / run_id
        assert (run_dir / "module-beeagent-rop").exists()
        assert (run_dir / "module-beescan").exists()


def test_smoke_context_authority_levels() -> None:
    with TemporaryDirectory() as tmp_dir:
        storage_dir = Path(tmp_dir)
        logger = logging.getLogger("test")

        for authority in [
            AuthorityLevel.READ_ONLY,
            AuthorityLevel.DRAFT_ONLY,
            AuthorityLevel.EXECUTION_CAPABLE,
        ]:
            ctx = RuntimeContext(
                run_id=generate_run_id(),
                session_id=generate_session_id(),
                case_type="test",
                module_id=f"module-{authority.value}",
                authority=authority,
            )

            api = ArtifactAPI(context=ctx, storage_dir=storage_dir, logger=logger)

            api.write_json(
                "authority_test.json",
                {
                    "authority": authority.value,
                },
            )

            data = cast(dict[str, Any], api.read_json("authority_test.json"))
            assert data["authority"] == authority.value


def test_smoke_artifact_api_logging() -> None:
    with TemporaryDirectory() as tmp_dir:
        storage_dir = Path(tmp_dir)

        class CaptureHandler(logging.Handler):
            def __init__(self):
                super().__init__()
                self.records = []

            def emit(self, record):
                self.records.append(record)

        logger = logging.getLogger("test-capture")
        handler = CaptureHandler()
        logger.addHandler(handler)
        logger.setLevel(logging.INFO)

        ctx = RuntimeContext(
            run_id="run-test123",
            session_id="session-test456",
            case_type="test",
            module_id="test-module",
            authority=AuthorityLevel.READ_ONLY,
        )

        api = ArtifactAPI(context=ctx, storage_dir=storage_dir, logger=logger)

        api.write_json("test.json", {"data": "value"})
        api.read_json("test.json")

        assert len(handler.records) >= 1

        write_logs = [r for r in handler.records if "written" in r.getMessage()]
        assert len(write_logs) > 0

        log_msg = write_logs[0].getMessage()
        assert "module_id" in log_msg
        assert "test-module" in log_msg
        assert "run-test123" in log_msg
        assert "test.json" in log_msg


def test_smoke_full_artifact_workflow() -> None:
    with TemporaryDirectory() as tmp_dir:
        storage_dir = Path(tmp_dir)
        logger = logging.getLogger("workflow-test")

        run_id = generate_run_id(prefix="workflow")
        session_id = generate_session_id(prefix="user-session")

        context = RuntimeContext(
            run_id=run_id,
            session_id=session_id,
            case_type="lead_qualification",
            module_id="lead-scorer",
            authority=AuthorityLevel.DRAFT_ONLY,
            payload={
                "lead_id": "L12345",
                "email": "user@example.com",
                "company": "TechCorp",
            },
        )

        api = ArtifactAPI(context=context, storage_dir=storage_dir, logger=logger)

        leads_data = [
            {"id": "L12345", "score": 85, "tier": "hot"},
            {"id": "L12346", "score": 62, "tier": "warm"},
        ]

        api.write_json("leads.json", leads_data)
        api.write_json(
            "summary.json",
            {
                "total_processed": len(leads_data),
                "high_quality": 1,
                "processed_at": "2024-04-22T10:30:00Z",
            },
        )

        report_text = "\n".join(
            [
                "Lead Scoring Report",
                f"Run ID: {context.run_id}",
                f"Module: {context.module_id}",
                f"Authority: {context.authority.value}",
                f"Leads Processed: {len(leads_data)}",
            ]
        )
        api.write_text("report.md", report_text)

        artifacts = api.list_artifacts()
        assert len(artifacts) == 3

        leads = api.read_json("leads.json")
        summary = cast(dict[str, Any], api.read_json("summary.json"))
        report = api.read_text("report.md")

        assert len(leads) == len(leads_data)
        assert summary["total_processed"] == 2
        assert context.run_id in report

        expected_path = storage_dir / "runs" / run_id / "module-lead-scorer"
        assert api.artifact_dir() == expected_path
        assert all(artifact.parent == expected_path for artifact in artifacts)
