import json
import logging
import os
import shutil
import ssl
import subprocess
import sys
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

import pytest
import test_beescan_egress_lab as network_lab
import yaml

from beeagent_module.integrations.beescan import investigation as host
from beeagent_module.integrations.beescan import local_cli
from beeagent_module.integrations.beescan.case_state import load_case
from tests.settings_support import read_test_settings

approved = network_lab.approved
managed_lab = network_lab.managed_lab


@pytest.fixture
def adaptive_lab(managed_lab, monkeypatch):
    _, root, _, sessions, probe = managed_lab
    requests = []
    scenario = {"root": "both", "patched": False}

    class Handler(BaseHTTPRequestHandler):
        def do_GET(self):
            requests.append(self.path)
            if self.path == "/":
                body = "<!-- diagnostic /operations/health.txt -->"
                if scenario["root"] == "both":
                    body += (
                        '<a href="'
                        + scenario.get("resource", "/archive/entry?record=912")
                        + '">Entry</a>'
                    )
            elif self.path == "/operations/health.txt":
                body = (
                    "No disclosure"
                    if scenario["patched"]
                    else "APP_TOKEN=adaptive-lab-private-canary"
                )
            else:
                body = "Ordinary record"
            raw = body.encode()
            self.send_response(200)
            self.send_header(
                "Content-Type", "text/plain" if self.path != "/" else "text/html"
            )
            self.send_header("Content-Length", str(len(raw)))
            self.end_headers()
            self.wfile.write(raw)

        def log_message(self, format, *args):
            pass

    server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    if probe.origin.startswith("https:"):
        context = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
        context.load_cert_chain(root / "cert.pem", root / "key.pem")
        server.socket = context.wrap_socket(server.socket, server_side=True)
    thread = threading.Thread(target=server.serve_forever)
    thread.start()
    config = read_test_settings()
    config["beescan"]["investigation"].update(
        trusted_local_enabled=True, local_lab_enabled=True
    )
    config["beescan"]["investigation"]["adaptive"].update(
        enabled=True, max_steps=2, max_requests=6
    )
    monkeypatch.setenv("OPENROUTER_API_KEY", "laboratory-no-ai-provider-call")
    monkeypatch.setattr(
        host,
        "call_structured_ai",
        lambda **kwargs: '{"objective":"supported_disclosures"}',
    )
    origin = probe.origin.rsplit(":", 1)[0] + ":" + str(server.server_port)
    try:
        yield config, root, requests, sessions, scenario, origin
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=2)


@pytest.mark.parametrize("mode", ["vulnerable", "patched", "different_discovery"])
def test_real_adaptive_http_https(adaptive_lab, mode):
    config, root, requests, sessions, scenario, origin = adaptive_lab
    scenario["patched"] = mode == "patched"
    scenario["root"] = "debug" if mode == "different_discovery" else "both"
    operator = local_cli._LocalOperator(local_cli._identity(), local_cli._SEAL)
    result = host.execute_investigation(
        task=host.InvestigationTask(origin, "Investigate disclosures field=APP_TOKEN"),
        local_operator=operator,
        settings=config,
        reload_settings=lambda: config,
        storage_dir=root / "storage",
        logger=logging.getLogger("managed-lab"),
        adaptive=True,
    )
    assert result["status"] == ("NO_MATCH" if mode == "patched" else "MATCH"), result
    assert (
        result["request_count"]
        == len(requests)
        == (3 if mode == "different_discovery" else 6)
    )
    state, _ = load_case(root / "storage", result["case_id"])
    assert state["terminal"] and not state["pending"]
    assert state["metrics"]["ai_calls"] == 1
    assert all(
        session.closed
        and session.helper.poll() is not None
        and session.supervisor.poll() is not None
        for session in sessions
    )
    for path in (root / "storage").rglob("*.json"):
        assert "adaptive-lab-private-canary" not in path.read_text()


def test_fresh_process_cli_inspect_resume(adaptive_lab):
    config, root, requests, _, _, origin = adaptive_lab
    if origin.startswith("https:"):
        pytest.skip(
            "Fresh process uses HTTP; real TLS is exercised by the adaptive laboratory above"
        )
    repository = Path(__file__).resolve().parents[1]
    project = root / "adaptive-cli"
    (root / "beescan").symlink_to(
        repository.parent / "beescan", target_is_directory=True
    )
    (project / "config").mkdir(parents=True, mode=0o700)
    for name in ("start.py", "prompts.yml"):
        shutil.copyfile(repository / "config" / name, project / "config" / name)
    for name in ("pyproject.toml", "uv.lock"):
        shutil.copyfile(repository / name, project / name)
    for name in (".env", ".env.example"):
        (project / name).touch(mode=0o600)
    config["beescan"]["investigation"]["adaptive"]["max_steps"] = 1
    (project / "config/settings.yml").write_text(yaml.safe_dump(config))
    hooks = project / "hooks"
    hooks.mkdir()
    (hooks / "lab_hooks.py").write_text(
        "import os,json\nfrom pathlib import Path\n"
        "from beeagent_module.core import paths\n"
        "from beeagent_module.integrations.beescan import egress,investigation as host\n"
        "paths.ROOT_DIR=Path(os.environ['BEEAGENT_ADAPTIVE_LAB_ROOT'])\n"
        "egress.executable_path=lambda:paths.ROOT_DIR.parent/'providers/pasta'\n"
        "original=egress.ManagedEgress._spawn\n"
        "def spawn(self,command,**kwargs):\n"
        " if 'exec' in command:command=[*command,'--map-host-loopback','192.0.2.1']\n"
        " return original(self,command,**kwargs)\n"
        "egress.ManagedEgress._spawn=spawn\n"
        "host.call_structured_ai=lambda **kwargs:json.dumps({'objective':'supported_disclosures'})\n"
    )
    code = "import sys,runpy;sys.path.insert(0,sys.argv[1]);import lab_hooks;sys.argv=sys.argv[2:];runpy.run_path(sys.argv[0],run_name='__main__')"

    def cli(arguments):
        process = subprocess.run(
            [
                sys.executable,
                "-c",
                code,
                str(hooks),
                str(project / "config/start.py"),
                "beescan",
                "investigate",
                *arguments,
            ],
            cwd=repository,
            env={
                **os.environ,
                "BEEAGENT_ADAPTIVE_LAB_ROOT": str(project),
                "OPENAI_API_KEY": "laboratory-no-ai-call",
            },
            capture_output=True,
            text=True,
            timeout=90,
            check=False,
        )
        assert "adaptive-lab-private-canary" not in process.stdout + process.stderr
        return process.returncode, json.loads(process.stdout.splitlines()[-1])

    first_code, first = cli(
        [
            "--adaptive",
            "--target",
            origin,
            "--task",
            "Investigate disclosures field=APP_TOKEN",
        ]
    )
    assert first_code == 5 and first["request_count"] == 4, first
    inspect_code, inspected = cli(["--inspect", first["case_id"]])
    assert inspect_code == 0 and len(inspected["outcomes"]) == 1
    second_code, second = cli(
        [
            "--resume",
            first["case_id"],
            "--task",
            "Continue supported disclosures field=APP_TOKEN",
        ]
    )
    assert second_code == 0 and second["status"] == "MATCH", second
    assert second["request_count"] == 3 and len(requests) == 7
    state, _ = load_case(project / "storage", first["case_id"])
    assert len(state["segments"]) == 2 and state["metrics"]["request_count"] == 7
    assert all(
        "adaptive-lab-private-canary" not in path.read_text()
        for path in (project / "storage").rglob("*.json")
    )


def test_real_resume_changed_resource_stops(adaptive_lab):
    config, root, requests, _, scenario, origin = adaptive_lab
    config["beescan"]["investigation"]["adaptive"]["max_steps"] = 1
    operator = local_cli._LocalOperator(local_cli._identity(), local_cli._SEAL)

    def run(resume=None):
        return host.execute_investigation(
            task=host.InvestigationTask(
                origin, "Investigate disclosures field=APP_TOKEN"
            ),
            local_operator=operator,
            settings=config,
            reload_settings=lambda: config,
            storage_dir=root / "storage",
            logger=logging.getLogger("managed-lab"),
            adaptive=True,
            resume_case_id=resume,
        )

    first = run()
    assert first["request_count"] == 4
    scenario["resource"] = "/different/item?entry=93"
    second = run(first["case_id"])
    assert second["status"] == "INCONCLUSIVE", second
    assert second["reason"] == "evidence_not_equivalent"
    assert second["request_count"] == 1 and len(requests) == 5
    state, _ = load_case(root / "storage", first["case_id"])
    assert state["metrics"]["request_count"] == 5
    assert len(state["outcomes"]) == 1
