import ctypes
import json
import os
import signal
import subprocess
import sys
from pathlib import Path


def main():
    parent = int(sys.argv[1])
    libc = ctypes.CDLL(None, use_errno=True)
    if sys.argv[2] == "exec":
        if libc.prctl(1, signal.SIGKILL, 0, 0, 0) != 0 or os.getppid() != parent:
            raise SystemExit(1)
        signal.alarm(int(sys.argv[4]))
        os.execv(sys.argv[3], ["pasta", *sys.argv[5:]])

    def terminate(_signum, _frame):
        raise SystemExit(1)

    signal.signal(signal.SIGTERM, terminate)
    signal.signal(signal.SIGALRM, terminate)
    try:
        if os.getppid() != parent:
            raise SystemExit(1)
        supervise()
    finally:
        signal.signal(signal.SIGTERM, signal.SIG_IGN)
        signal.signal(signal.SIGALRM, signal.SIG_IGN)
        directory = Path(__file__).parent
        for name in ("pasta", "worker.py"):
            (directory / name).unlink(missing_ok=True)
        try:
            directory.rmdir()
        except FileNotFoundError:
            pass


def supervise():
    address, port, seconds = sys.argv[3:]
    signal.alarm(int(seconds))
    family = "ip6" if ":" in address else "ip"
    setting = "disable_ipv6" if family == "ip" else "accept_dad"
    for interface in ("all", "default"):
        with open(f"/proc/sys/net/ipv6/conf/{interface}/{setting}", "w") as stream:
            stream.write("1" if family == "ip" else "0")
    rules = (
        "table inet beescan {\nchain output {\n"
        "type filter hook output priority -150; policy drop;\n"
        f"{family} daddr {address} tcp dport {int(port)} accept\n"
        "ct state established tcp flags & (syn | ack) != syn accept\n}\n}\n"
    )
    subprocess.run(
        ["/usr/sbin/nft", "-f", "-"],
        input=rules.encode("ascii"),
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        check=True,
        timeout=3,
    )
    print(json.dumps({"pid": os.getpid()}), flush=True)
    sys.stdin.buffer.read(1)


if __name__ == "__main__":
    main()
