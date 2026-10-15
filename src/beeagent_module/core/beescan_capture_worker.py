import json
import re
import socket
import ssl
import sys
from urllib.parse import urlsplit


def capture(config):
    origin = urlsplit(config["origin"])
    family = socket.AF_INET6 if ":" in config["connected_ip"] else socket.AF_INET
    with socket.socket(family, socket.SOCK_STREAM) as connection:
        connection.settimeout(config["seconds"])
        connection.connect((config["connected_ip"], config["port"]))
        if origin.scheme == "https":
            stream = ssl.create_default_context().wrap_socket(
                connection, server_hostname=origin.hostname
            )
        else:
            stream = connection
        try:
            request = f"GET / HTTP/1.1\r\nHost: {origin.netloc}\r\nConnection: close\r\nAccept: */*\r\nUser-Agent: BeeAgent-BS2\r\n\r\n"
            stream.sendall(request.encode("ascii"))
            header = bytearray()
            while not header.endswith(b"\r\n\r\n"):
                chunk = stream.recv(1)
                if not chunk or len(header) >= 8192:
                    raise ValueError
                header.extend(chunk)
            lines = header.decode("ascii").split("\r\n")
            match = re.fullmatch(r"HTTP/1\.[01] ([2-5][0-9]{2}) [\x20-\x7e]*", lines[0])
            if match is None:
                raise ValueError
            status = int(match[1])
            if 300 <= status <= 399:
                return 3, None
            marker = None
            seen = set()
            for line in lines[1:-2]:
                name, separator, value = line.partition(":")
                if (
                    not separator
                    or re.fullmatch(r"[A-Za-z0-9!#$%&'*+.^_`|~-]+", name) is None
                    or any(ord(c) < 32 or ord(c) > 126 for c in value)
                ):
                    raise ValueError
                name = name.lower()
                if (
                    name in {"x-beescan-marker", "content-length", "transfer-encoding"}
                    and name in seen
                ):
                    raise ValueError
                seen.add(name)
                if name == "x-beescan-marker":
                    marker = value.strip()
                    if marker not in {"present", "absent"}:
                        raise ValueError
            return 0, {
                "origin": config["origin"],
                "connected_ip": config["connected_ip"],
                "port": config["port"],
                "method": "GET",
                "request_count": 1,
                "status_code": status,
                "marker_header": marker,
                "complete": True,
            }
        finally:
            stream.close()


if __name__ == "__main__":
    try:
        code, result = capture(json.loads(sys.argv[1]))
        if result is not None:
            print(json.dumps(result))
    except TimeoutError:
        code = 4
    except OSError, ValueError, KeyError, TypeError, UnicodeError:
        code = 5
    sys.exit(code)
