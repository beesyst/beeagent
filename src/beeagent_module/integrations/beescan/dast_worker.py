import hashlib
import json
import select
import signal
import socket
import socketserver
import subprocess
import sys
import threading
import time
import urllib.error
import urllib.parse
import urllib.request


class Relay(socketserver.BaseRequestHandler):
    def handle(self):
        with socket.socket(socket.AF_UNIX, socket.SOCK_STREAM) as upstream:
            upstream.settimeout(2)
            upstream.connect("/gate.sock")
            pair = (self.request, upstream)
            while True:
                ready, _, _ = select.select(pair, [], [], 2)
                if not ready:
                    continue
                for source in ready:
                    data = source.recv(16384)
                    if not data:
                        return
                    destination = upstream if source is self.request else self.request
                    destination.sendall(data)


def main():
    config = json.loads(sys.argv[1])
    signal.alarm(config["seconds"])
    server = socketserver.ThreadingTCPServer(("127.0.0.1", 8091), Relay)
    server.daemon_threads = True
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    settings = {
        "api.disablekey": "true",
        "network.connection.httpProxy.enabled": "true",
        "network.connection.httpProxy.host": "127.0.0.1",
        "network.connection.httpProxy.port": "8091",
        "network.connection.httpProxy.authEnabled": "false",
        "network.connection.socksProxy.enabled": "false",
        "network.connection.timeoutInSecs": "2",
        "autoupdate.checkOnStart": "false",
        "autoupdate.downloadNewRelease": "false",
        "autoupdate.installAddonUpdates": "false",
        "ascan.threadPerHost": "1",
        "ascan.hostPerScan": "1",
    }
    command = [
        "/usr/lib/jvm/java-25-openjdk-amd64/bin/java",
        "-Xmx256m",
        "-XX:ReservedCodeCacheSize=64m",
        "-XX:CompressedClassSpaceSize=64m",
        "-XX:MaxDirectMemorySize=64m",
        "-Djava.awt.headless=true",
        "-Duser.home=/tmp",
        "-jar",
        "/zap/zap-2.17.0.jar",
        "-daemon",
        "-silent",
        "-host",
        "127.0.0.1",
        "-port",
        "8090",
        "-dir",
        "/tmp/zap-home",
    ]
    for key, value in settings.items():
        command.extend(["-config", f"{key}={value}"])
    child = subprocess.Popen(
        command, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL
    )
    opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))
    deadline = time.monotonic() + config["seconds"]

    def api(component, operation, name, **values):
        url = f"http://127.0.0.1:8090/JSON/{component}/{operation}/{name}/?"
        url += urllib.parse.urlencode(values)
        try:
            with opener.open(
                url, timeout=min(10, max(1, deadline - time.monotonic()))
            ) as response:
                data = response.read(2097153)
        except urllib.error.HTTPError as error:
            raise ValueError(f"zap_api_{component}_{name}_{error.code}") from None
        if len(data) > 2097152:
            raise ValueError("zap_api_limit")
        result = json.loads(data)
        if type(result) is not dict or "code" in result:
            raise ValueError("zap_api_rejected")
        return result

    try:
        while True:
            try:
                if api("core", "view", "version") != {"version": "2.17.0"}:
                    raise ValueError("zap_version")
                break
            except OSError:
                if child.poll() is not None or time.monotonic() >= deadline:
                    raise RuntimeError("zap_start_failed") from None
                time.sleep(0.1)
        policy = "beeagent-path-traversal-v1"
        api("pscan", "action", "disableAllScanners")
        api("ascan", "action", "addScanPolicy", scanPolicyName=policy)
        api("ascan", "action", "disableAllScanners", scanPolicyName=policy)
        api("ascan", "action", "enableScanners", ids="6", scanPolicyName=policy)
        api(
            "ascan",
            "action",
            "setScannerAttackStrength",
            id=6,
            attackStrength="LOW",
            scanPolicyName=policy,
        )
        api(
            "ascan",
            "action",
            "setScannerAlertThreshold",
            id=6,
            alertThreshold="MEDIUM",
            scanPolicyName=policy,
        )
        scanners = api("ascan", "view", "scanners", scanPolicyName=policy)["scanners"]
        enabled = [item for item in scanners if item["enabled"] == "true"]
        if len(enabled) != 1 or enabled[0]["id"] != "6":
            raise ValueError("zap_rule_policy")
        for entry in config["entries"]:
            url = config["origin"] + entry
            api("core", "action", "accessUrl", url=url, followRedirects="false")
            while url not in api("core", "view", "urls")["urls"]:
                if time.monotonic() >= deadline or child.poll() is not None:
                    raise TimeoutError("zap_site_incomplete")
                time.sleep(0.05)
            scan = api(
                "ascan",
                "action",
                "scan",
                url=url,
                recurse="false",
                inScopeOnly="false",
                scanPolicyName=policy,
            )["scan"]
            while api("ascan", "view", "status", scanId=scan)["status"] != "100":
                if time.monotonic() >= deadline or child.poll() is not None:
                    raise TimeoutError("zap_scan_incomplete")
                time.sleep(0.1)
        records = api(
            "core", "view", "alerts", baseurl=config["origin"], start=0, count=33
        )["alerts"]
        if len(records) > 32:
            raise ValueError("zap_alert_limit")
        alerts = []
        for record in records:
            if record["pluginId"] != "6":
                raise ValueError("zap_unapproved_rule")
            message = api("core", "view", "message", id=record["messageId"])["message"]
            target = message["requestHeader"].split("\r\n", 1)[0].split(" ")[1]
            target = target.removeprefix(config["origin"])
            alerts.append(
                {
                    "rule_id": "6",
                    "request_sha256": hashlib.sha256(
                        target.encode("ascii")
                    ).hexdigest(),
                    "response_sha256": hashlib.sha256(
                        message["responseBody"].encode("utf-8")
                    ).hexdigest(),
                }
            )
        print(
            json.dumps(
                {
                    "complete": True,
                    "rule_id": "6",
                    "alerts": alerts,
                    "entries": len(config["entries"]),
                }
            )
        )
    finally:
        child.terminate()
        try:
            child.wait(timeout=2)
        except subprocess.TimeoutExpired:
            child.kill()
            child.wait(timeout=2)
        server.shutdown()
        server.server_close()


if __name__ == "__main__":
    try:
        main()
    except (OSError, ValueError, RuntimeError, KeyError, TypeError) as error:
        reason = str(error)
        if (
            not reason.startswith("zap_")
            or len(reason) > 80
            or not all(c.isalnum() or c == "_" for c in reason)
        ):
            reason = "zap_worker_failed"
        print(json.dumps({"failure": reason}))
        sys.exit(1)
