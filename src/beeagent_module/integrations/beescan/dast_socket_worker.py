import array
import json
import signal
import socket
import sys


def main():
    config = json.loads(sys.argv[1])
    signal.alarm(config["seconds"])
    family = socket.AF_INET6 if ":" in config["connected_ip"] else socket.AF_INET
    with socket.socket(socket.AF_UNIX, socket.SOCK_STREAM) as listener:
        listener.bind("/broker/open.sock")
        listener.listen(8)
        listener.settimeout(config["seconds"])
        print("ready", flush=True)
        for _ in range(config["requests"]):
            connection, _address = listener.accept()
            with connection, socket.socket(family, socket.SOCK_STREAM) as upstream:
                upstream.settimeout(2)
                try:
                    upstream.connect((config["connected_ip"], config["port"]))
                    connection.sendmsg(
                        [b"1"],
                        [
                            (
                                socket.SOL_SOCKET,
                                socket.SCM_RIGHTS,
                                array.array("i", [upstream.fileno()]),
                            )
                        ],
                    )
                except OSError:
                    connection.sendall(b"0")


if __name__ == "__main__":
    main()
