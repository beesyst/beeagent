import json
import logging
import ssl
import threading
from dataclasses import asdict, replace
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

import pytest
import test_beescan_egress_lab as network_lab

from beeagent_module.integrations.beescan import egress
from beeagent_module.integrations.beescan import investigation as host
from tests.settings_support import read_test_settings
from tests.test_beescan_debug_disclosure import NATURAL_TASK

approved = network_lab.approved
managed_lab = network_lab.managed_lab
CANARY = "bounded-lab-canary-344-562"


@pytest.mark.parametrize(
    "mode,expected",
    [
        ("vulnerable", "MATCH"),
        ("patched", "NO_MATCH"),
        ("ambiguous", "INCONCLUSIVE"),
        ("truncated", "ERROR"),
        ("cleanup", "ERROR"),
        ("terminal", "MATCH"),
    ],
)
def test_real_debug_managed_egress(managed_lab, monkeypatch, mode, expected):
    _, root, _, sessions, probe = managed_lab
    if mode == "terminal" and probe.origin.startswith("https:"):
        pytest.skip(
            "Controlling-terminal launcher uses the HTTP lab; HTTPS capture is covered independently"
        )
    requests, ai_calls = [], []

    class Handler(BaseHTTPRequestHandler):
        def do_GET(self):
            requests.append((self.command, self.path))
            if self.path == "/":
                body = "<!-- <a href=/cgi-bin/phpinfo.php>Debug</a> -->"
                if mode == "ambiguous":
                    body += "<!-- debug /other/config -->"
            elif self.path == "/cgi-bin/phpinfo.php":
                body = (
                    "<table><tr><td>SECRET_KEY</td><td>" + CANARY + "</td></tr></table>"
                )
                if mode == "patched":
                    body = "<p>Diagnostic output disabled</p>"
            else:
                raise AssertionError("Unexpected request")
            raw = body.encode()
            self.send_response(200)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.send_header(
                "Content-Length",
                str(len(raw) + (1 if mode == "truncated" and self.path != "/" else 0)),
            )
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
    transport = replace(
        probe,
        origin=probe.origin.rsplit(":", 1)[0] + ":" + str(server.server_port),
        time_budget_seconds=30,
    )
    policy = host.InvestigationPolicy(
        transport, True, True, True, "GET", "numeric_invalid_v1", 3
    )
    approval = asdict(policy)
    for key in ("valid_from", "expires_at"):
        approval["transport"][key] = approval["transport"][key].isoformat()
    config = read_test_settings()
    config["beescan"]["investigation"].update(
        enabled=True, approval=approval, local_lab_enabled=True
    )
    for item in config["modules"]["registry"]:
        item["enabled"] = item["id"] == "beescan"
    task = root / "debug-task.json"
    task.write_text(json.dumps({"target": transport.origin, "task": NATURAL_TASK}))
    task.chmod(0o600)

    def ai(**kwargs):
        ai_calls.append(kwargs)
        return '{"intent":"debug_page_secret_disclosure"}'

    monkeypatch.setattr(host, "call_structured_ai", ai)
    monkeypatch.setenv("OPENROUTER_API_KEY", "laboratory-private-key")
    if mode == "cleanup":
        original_close = egress.ManagedEgress.close

        def close(self):
            original_close(self)
            raise RuntimeError("cleanup_unverified")

        monkeypatch.setattr(egress.ManagedEgress, "close", close)
    try:
        if mode == "terminal":
            monkeypatch.setenv("BEEAGENT_BS10_LAB_TARGET", transport.origin)
            result = _terminal_cli(config, root, Path(__file__).resolve().parents[1])
            assert (
                result["status"] == "MATCH"
                and result["request_count"] == len(requests) == 2
            )
            return
        result = host.execute_investigation(
            task_path=task,
            settings=config,
            reload_settings=lambda: config,
            storage_dir=root / "storage",
            logger=logging.getLogger("managed-lab"),
        )
        assert result["status"] == expected, result
        assert (
            result["request_count"]
            == len(requests)
            == (1 if mode == "ambiguous" else 2)
        )
        assert result["request_count_exact"]
        if mode != "ambiguous":
            assert requests == [("GET", "/"), ("GET", "/cgi-bin/phpinfo.php")]
        assert result["integration_status"] == "LABORATORY_ONLY"
        assert len(ai_calls) == 1
        assert CANARY not in str(ai_calls)
        assert egress._active.get() is None
        assert sessions and all(
            session.closed
            and session.helper.poll() is not None
            and session.supervisor.poll() is not None
            for session in sessions
        )
        for path in (root / "storage/runs").glob("*/module-beescan/*"):
            assert CANARY not in path.read_text()
            if path.name == "source.json":
                record = json.loads(path.read_text())
                assert (
                    record["projection"] == "debug-redacted-v1"
                    and "capture" not in record
                )
        parent = root / "storage/runs" / result["run_id"] / "module-beescan"
        assert json.loads((parent / "investigation_status.json").read_text()) == result
        if mode != "cleanup":
            assert json.loads((parent / "egress_lifecycle.json").read_text())[
                "cleanup_verified"
            ]
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=2)


def _terminal_cli(config, root, repository):
    import fcntl
    import os
    import pty
    import select
    import shutil
    import subprocess
    import sys
    import termios
    import time

    import yaml

    project = root / "debug-cli"
    (root / "beescan").symlink_to(
        repository.parent / "beescan", target_is_directory=True
    )
    (project / "config").mkdir(parents=True, mode=0o700)
    for name in ("start.py", "prompts.yml"):
        shutil.copyfile(repository / "config" / name, project / "config" / name)
    shutil.copyfile(repository / "pyproject.toml", project / "pyproject.toml")
    shutil.copyfile(repository / "uv.lock", project / "uv.lock")
    (project / "config/settings.yml").write_text(yaml.safe_dump(config))
    for name in (".env", ".env.example"):
        (project / name).touch(mode=0o600)
    hooks = project / "hooks"
    hooks.mkdir()
    (hooks / "lab_hooks.py").write_text(
        "import os,json\nfrom pathlib import Path\n"
        "from beeagent_module.core import paths\n"
        "from beeagent_module.integrations.beescan import egress,investigation as host,detection_runner\n"
        "paths.ROOT_DIR=Path(os.environ['BEEAGENT_BS10_LAB_ROOT'])\n"
        "egress.executable_path=lambda:paths.ROOT_DIR.parent/'providers/pasta'\n"
        "original=egress.ManagedEgress._spawn\n"
        "def spawn(self,command,**kwargs):\n"
        " if 'exec' in command:command=[*command,'--map-host-loopback','192.0.2.1']\n"
        " return original(self,command,**kwargs)\n"
        "egress.ManagedEgress._spawn=spawn\n"
        "host.call_structured_ai=lambda **kwargs:json.dumps({'intent':'debug_page_secret_disclosure'})\n"
    )
    config["beescan"]["investigation"].update(
        trusted_local_enabled=True, enabled=False, approval=None
    )
    (project / "config/settings.yml").write_text(yaml.safe_dump(config))
    target = os.environ["BEEAGENT_BS10_LAB_TARGET"]
    entrypoint = project / "config/start.py"
    code = (
        "import sys,runpy;sys.path.insert(0,sys.argv[1]);import lab_hooks;"
        "sys.argv=sys.argv[2:];runpy.run_path(sys.argv[0],run_name='__main__')"
    )
    master, slave = pty.openpty()
    command = [
        sys.executable,
        "-c",
        code,
        str(hooks),
        str(entrypoint),
        "beescan",
        "investigate",
        "--target",
        target,
        "--task",
        NATURAL_TASK,
    ]
    process = subprocess.Popen(
        command,
        cwd=repository,
        env={**os.environ, "BEEAGENT_BS10_LAB_ROOT": str(project)},
        stdin=slave,
        stdout=slave,
        stderr=slave,
        start_new_session=True,
        preexec_fn=lambda: fcntl.ioctl(0, termios.TIOCSCTTY, 0),
    )
    os.close(slave)
    output = bytearray()
    deadline = time.monotonic() + 120
    try:
        while time.monotonic() < deadline:
            if select.select([master], [], [], 1)[0]:
                try:
                    chunk = os.read(master, 4096)
                except OSError:
                    break
                if not chunk:
                    break
                output.extend(chunk)
                assert len(output) <= 131072
            elif process.poll() is not None:
                break
        assert process.wait(timeout=5) == 0
        lines = output.decode().splitlines()
        assert CANARY in lines
        result = json.loads(lines[-1])
        assert CANARY not in json.dumps(result)
        for path in (project / "storage/runs").glob("*/module-beescan/*"):
            assert CANARY not in path.read_text()
        lifecycle = (
            project
            / "storage/runs"
            / result["run_id"]
            / "module-beescan/egress_lifecycle.json"
        )
        assert json.loads(lifecycle.read_text())["cleanup_verified"]
        return result
    finally:
        if process.poll() is None:
            process.kill()
            process.wait(timeout=5)
        os.close(master)
