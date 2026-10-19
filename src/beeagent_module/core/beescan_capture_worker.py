import json
import re
import socket
import ssl
import sys
from typing import TYPE_CHECKING
from urllib.parse import urlsplit


def normalized_headers(values, *, https):
    nosniff = values.get("x-content-type-options")
    hsts = values.get("strict-transport-security")
    result = {
        "nosniff": "absent"
        if nosniff is None
        else "nosniff"
        if nosniff.lower() == "nosniff"
        else "other",
        "hsts": "absent" if hsts is None else "other",
        "hsts_max_age": None,
        "https": https,
        "complete": True,
    }
    if hsts is not None:
        seen = set()
        for directive in hsts.split(";"):
            directive = directive.strip()
            if not directive:
                continue
            match = re.fullmatch(
                r'([A-Za-z][A-Za-z0-9-]*)(?:\s*=\s*([A-Za-z0-9-]+|"[A-Za-z0-9-]*"))?',
                directive,
            )
            if match is None:
                raise ValueError
            name, value = match.groups()
            name = name.lower()
            if name in seen:
                raise ValueError
            seen.add(name)
            if name == "max-age":
                if value is None:
                    raise ValueError
                value = value.strip('"')
                if not value.isascii() or not value.isdecimal() or len(value) > 19:
                    raise ValueError
                age = int(value)
                if age > 2**63 - 1:
                    raise ValueError
                result.update(hsts="max_age", hsts_max_age=age)
    return result


def capture(config):
    exposure = config.get("git_exposure", False)
    if type(exposure) is not bool or (exposure and config.get("http_signals", False)):
        raise ValueError
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
            path = "/.git/HEAD" if exposure else "/"
            request = f"GET {path} HTTP/1.1\r\nHost: {origin.netloc}\r\nConnection: close\r\nAccept: */*\r\nUser-Agent: BeeAgent-BS2\r\n\r\n"
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
            headers = {}
            signals = config.get("http_signals", False)
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
                    or exposure
                    and name in {"content-type", "content-encoding"}
                    or signals
                    and name in {"x-content-type-options", "strict-transport-security"}
                ) and name in seen:
                    raise ValueError
                seen.add(name)
                if exposure and name in {
                    "content-length",
                    "transfer-encoding",
                    "content-encoding",
                    "content-type",
                }:
                    headers[name] = value.strip()
                if signals and name in {
                    "x-content-type-options",
                    "strict-transport-security",
                }:
                    if len(value) > 1024:
                        raise ValueError
                    headers[name] = value.strip()
                if name == "x-beescan-marker" and not exposure:
                    marker = value.strip()
                    if marker not in {"present", "absent"}:
                        raise ValueError
            result = {
                "origin": config["origin"],
                "connected_ip": config["connected_ip"],
                "port": config["port"],
                "method": "GET",
                "request_count": 1,
                "status_code": status,
                "marker_header": marker,
                "complete": True,
            }
            if exposure:
                if TYPE_CHECKING:
                    from beescan.domain import git_head_signature
                else:
                    import git_head_signature

                if "transfer-encoding" in headers or "content-encoding" in headers:
                    raise ValueError
                length = headers.get("content-length")
                if length is None:
                    raise ValueError
                if (
                    re.fullmatch(r"[0-9]{1,4}", length) is None
                    or int(length) > git_head_signature.MAX_HEAD_BYTES
                ):
                    raise ValueError
                length = int(length)
                body = bytearray()
                while True:
                    chunk = stream.recv(
                        git_head_signature.MAX_HEAD_BYTES + 1 - len(body)
                    )
                    if not chunk:
                        break
                    body.extend(chunk)
                    if len(body) > git_head_signature.MAX_HEAD_BYTES:
                        raise ValueError
                if len(body) != length:
                    raise ValueError
                signature = git_head_signature.git_head_signature(bytes(body))
                media = headers.get("content-type", "").split(";", 1)[0].strip().lower()
                if status != 200 or media in {"text/html", "application/xhtml+xml"}:
                    signature = None
                del body
                result.pop("marker_header")
                result.update(path="/.git/HEAD", signature=signature)
            if signals:
                result["header_facts"] = normalized_headers(
                    headers, https=origin.scheme == "https"
                )
            return 0, result
        finally:
            stream.close()


if __name__ == "__main__":
    try:
        sys.path.insert(0, "/")
        code, result = capture(json.loads(sys.argv[1]))
        if result is not None:
            print(json.dumps(result))
    except TimeoutError:
        code = 4
    except OSError, ValueError, KeyError, TypeError, UnicodeError:
        code = 5
    sys.exit(code)
