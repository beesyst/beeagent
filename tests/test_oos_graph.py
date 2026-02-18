import json
from pathlib import Path
from tempfile import TemporaryDirectory

from beeagent_module.agents.oos.graph import build_oos_graph, run_oos_workflow
from beeagent_module.agents.oos.rules import detect_rule_a
from beeagent_module.domain.models import ShelfSignal, StockRow
from beeagent_module.mock.dataset import generate_mock_dataset, save_mock_dataset


# Тест правил OOS и выполнения LangGraph-скрипта с mock-данными
class TestOOSRules:
    # Тест правила A: stock_on_hand > 0 AND seen_on_shelf == false → alert
    def test_rule_a_triggers_on_stock_and_no_shelf(self):
        stock_rows = [
            StockRow(
                date="2025-01-01",
                store_id="STORE-001",
                sku_id="SKU-0001",
                stock_on_hand=5,
            )
        ]
        shelf_signals = [
            ShelfSignal(
                date="2025-01-01",
                store_id="STORE-001",
                sku_id="SKU-0001",
                seen_on_shelf=False,
            )
        ]

        alerts = detect_rule_a(
            stock_rows=stock_rows,
            shelf_signals=shelf_signals,
            sku_id="SKU-0001",
            store_id="STORE-001",
            date="2025-01-01",
        )

        assert len(alerts) == 1
        assert alerts[0].store_id == "STORE-001"
        assert alerts[0].sku_id == "SKU-0001"
        assert alerts[0].rule_id == "RULE_A"
        assert alerts[0].severity == "high"

    # Правило A не срабатывает, если stock_on_hand <= 0 или seen_on_shelf == true
    def test_rule_a_no_alert_when_stock_zero(self):
        stock_rows = [
            StockRow(
                date="2025-01-01",
                store_id="STORE-001",
                sku_id="SKU-0001",
                stock_on_hand=0,
            )
        ]
        shelf_signals = [
            ShelfSignal(
                date="2025-01-01",
                store_id="STORE-001",
                sku_id="SKU-0001",
                seen_on_shelf=False,
            )
        ]

        alerts = detect_rule_a(
            stock_rows=stock_rows,
            shelf_signals=shelf_signals,
            sku_id="SKU-0001",
            store_id="STORE-001",
            date="2025-01-01",
        )

        assert len(alerts) == 0

    # Правило A не срабатывает, если товар виден на полке (seen_on_shelf == true), даже при наличии stock_on_hand > 0
    def test_rule_a_no_alert_when_shelf_visible(self):
        stock_rows = [
            StockRow(
                date="2025-01-01",
                store_id="STORE-001",
                sku_id="SKU-0001",
                stock_on_hand=5,
            )
        ]
        shelf_signals = [
            ShelfSignal(
                date="2025-01-01",
                store_id="STORE-001",
                sku_id="SKU-0001",
                seen_on_shelf=True,
            )
        ]

        alerts = detect_rule_a(
            stock_rows=stock_rows,
            shelf_signals=shelf_signals,
            sku_id="SKU-0001",
            store_id="STORE-001",
            date="2025-01-01",
        )

        assert len(alerts) == 0


# Тест выполнения LangGraph-скрипта с mock-данными
class TestOOSGraph:
    # Чек, что граф компилируется и выполняется без ошибок
    def test_graph_builds(self):
        graph = build_oos_graph()
        assert graph is not None
        assert hasattr(graph, "invoke")

    # Чек, что весь workflow выполняется с mock-данными и возвращает ожидаемый результат
    def test_workflow_with_mock_dataset(self):
        with TemporaryDirectory() as tmp_dir:
            storage_dir = Path(tmp_dir)

            # генерация и сохранение mock-данных для OOS-сканирования
            dataset = generate_mock_dataset(
                seed=42,
                weeks=2,
                stores=2,
                skus=3,
                category="TestCategory",
            )
            dataset_id = dataset["meta"]["dataset_id"]
            save_mock_dataset(dataset, storage_dir)

            # выполнение workflow
            result = run_oos_workflow(
                dataset_id=dataset_id,
                storage_dir=storage_dir,
            )

            # чек структуры результата
            assert "run_id" in result
            assert "artifacts_dir" in result
            assert "report_text" in result
            assert "alerts_count" in result
            assert "tasks_count" in result

            # чек формата run_id
            assert result["run_id"].startswith("run-")

            # чек содержания отчета
            assert "📊 OOS Detection Report" in result["report_text"]
            assert result["run_id"] in result["report_text"]
            assert dataset_id in result["report_text"]

    # Чек: workflow создает все необходимые артефакты и сохраняет их в storage
    def test_workflow_creates_artifacts(self):
        with TemporaryDirectory() as tmp_dir:
            storage_dir = Path(tmp_dir)

            # генерация и сохранение mock-данных для OOS-сканирования
            dataset = generate_mock_dataset(
                seed=42,
                weeks=2,
                stores=2,
                skus=3,
                category="TestCategory",
            )
            dataset_id = dataset["meta"]["dataset_id"]
            save_mock_dataset(dataset, storage_dir)

            # выполнение workflow
            result = run_oos_workflow(
                dataset_id=dataset_id,
                storage_dir=storage_dir,
            )

            artifacts_dir = result["artifacts_dir"]
            assert artifacts_dir.exists()

            # чек наличия необходимых файлов
            run_json = artifacts_dir / "run.json"
            alerts_json = artifacts_dir / "alerts.json"
            tasks_json = artifacts_dir / "tasks_draft.json"

            assert run_json.exists()
            assert alerts_json.exists()
            assert tasks_json.exists()

            report_md = storage_dir / "artifacts" / result["run_id"] / "report.md"
            report_html = storage_dir / "artifacts" / result["run_id"] / "report.html"
            last_run_json = storage_dir / "reports" / "last_run.json"

            assert report_md.exists()
            assert report_html.exists()
            assert last_run_json.exists()

    # Чек: количество сгенерированных задач соответствует количеству обнаруженных алертов (1 задача на 1 алерт)
    def test_run_json_structure(self):
        with TemporaryDirectory() as tmp_dir:
            storage_dir = Path(tmp_dir)

            dataset = generate_mock_dataset(
                seed=42,
                weeks=1,
                stores=1,
                skus=2,
                category="TestCategory",
            )
            dataset_id = dataset["meta"]["dataset_id"]
            save_mock_dataset(dataset, storage_dir)

            result = run_oos_workflow(
                dataset_id=dataset_id,
                storage_dir=storage_dir,
            )

            run_json = result["artifacts_dir"] / "run.json"
            run_data = json.loads(run_json.read_text(encoding="utf-8"))

            assert "run_id" in run_data
            assert "created_at" in run_data
            assert "dataset_id" in run_data
            assert "seed" in run_data
            assert "alerts_count" in run_data
            assert "tasks_count" in run_data
            assert run_data["dataset_id"] == dataset_id

    # Чек: alerts.json содержит сериализованные объекты Alert
    def test_alerts_json_serialization(self):
        with TemporaryDirectory() as tmp_dir:
            storage_dir = Path(tmp_dir)

            dataset = generate_mock_dataset(
                seed=42,
                weeks=1,
                stores=2,
                skus=3,
                category="TestCategory",
            )
            dataset_id = dataset["meta"]["dataset_id"]
            save_mock_dataset(dataset, storage_dir)

            result = run_oos_workflow(
                dataset_id=dataset_id,
                storage_dir=storage_dir,
            )

            alerts_json = result["artifacts_dir"] / "alerts.json"
            alerts_data = json.loads(alerts_json.read_text(encoding="utf-8"))

            assert isinstance(alerts_data, list)
            for alert in alerts_data:
                assert "store_id" in alert
                assert "sku_id" in alert
                assert "rule_id" in alert
                assert "severity" in alert
                assert "details" in alert

    # Чек: tasks_draft.json содержит сериализованные объекты Task
    def test_tasks_json_serialization(self):
        with TemporaryDirectory() as tmp_dir:
            storage_dir = Path(tmp_dir)

            dataset = generate_mock_dataset(
                seed=42,
                weeks=1,
                stores=2,
                skus=3,
                category="TestCategory",
            )
            dataset_id = dataset["meta"]["dataset_id"]
            save_mock_dataset(dataset, storage_dir)

            result = run_oos_workflow(
                dataset_id=dataset_id,
                storage_dir=storage_dir,
            )

            tasks_json = result["artifacts_dir"] / "tasks_draft.json"
            tasks_data = json.loads(tasks_json.read_text(encoding="utf-8"))

            assert isinstance(tasks_data, list)
            for task in tasks_data:
                assert "task_id" in task
                assert "store_id" in task
                assert "sku_id" in task
                assert "action" in task
                assert "status" in task
                assert task["status"] == "draft"
                assert task["action"] == "restock_and_display"

    # Чек: количество сгенерированных задач соответствует количеству обнаруженных алертов (1 задача на 1 алерт)
    def test_alert_task_count_match(self):
        with TemporaryDirectory() as tmp_dir:
            storage_dir = Path(tmp_dir)

            dataset = generate_mock_dataset(
                seed=42,
                weeks=1,
                stores=2,
                skus=3,
                category="TestCategory",
            )
            dataset_id = dataset["meta"]["dataset_id"]
            save_mock_dataset(dataset, storage_dir)

            result = run_oos_workflow(
                dataset_id=dataset_id,
                storage_dir=storage_dir,
            )

            assert result["tasks_count"] == result["alerts_count"]

    # Чек: workflow produces deterministic results with same seed
    def test_workflow_deterministic_with_fixed_seed(self):
        with TemporaryDirectory() as tmp_dir:
            storage_dir = Path(tmp_dir)

            # первый run
            dataset1 = generate_mock_dataset(
                seed=99,
                weeks=1,
                stores=2,
                skus=3,
                category="TestCategory",
            )
            dataset_id1 = dataset1["meta"]["dataset_id"]
            save_mock_dataset(dataset1, storage_dir)

            result1 = run_oos_workflow(
                dataset_id=dataset_id1,
                storage_dir=storage_dir,
            )

            # второй run с тем же seed
            dataset2 = generate_mock_dataset(
                seed=99,
                weeks=1,
                stores=2,
                skus=3,
                category="TestCategory",
            )
            dataset_id2 = dataset2["meta"]["dataset_id"]
            # очистка предыдущих run-артефактов для чистоты эксперимента
            import shutil

            runs_dir = storage_dir / "runs"
            if runs_dir.exists():
                shutil.rmtree(runs_dir)

            save_mock_dataset(dataset2, storage_dir)

            result2 = run_oos_workflow(
                dataset_id=dataset_id2,
                storage_dir=storage_dir,
            )

            # чек: одинаковое количество алертов и задач (одинаковый dataset)
            assert result1["alerts_count"] == result2["alerts_count"]
            assert result1["tasks_count"] == result2["tasks_count"]
