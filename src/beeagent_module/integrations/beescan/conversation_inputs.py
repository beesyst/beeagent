import json
import struct
import zlib
from pathlib import PurePath
from urllib.parse import urlsplit, urlunsplit

from beeagent_module.integrations.beescan.probe import _unique_object


def validate_attachment(item, redact):
    name, media, content = (
        item.get("filename"),
        item.get("content_type"),
        item.get("content"),
    )
    if (
        type(name) is not str
        or not 1 <= len(name) <= 128
        or PurePath(name).name != name
        or name in {".", ".."}
        or "\\" in name
        or any(ord(c) < 32 for c in name)
        or type(content) is not bytes
        or not 1 <= len(content) <= 2 * 1024 * 1024
    ):
        raise ValueError("invalid_attachment")
    extension = PurePath(name).suffix.lower()
    allowed = {
        ".txt": {"text/plain"},
        ".md": {"text/plain", "text/markdown"},
        ".json": {"application/json"},
        ".har": {"application/json", "application/octet-stream"},
        ".png": {"image/png"},
        ".jpg": {"image/jpeg"},
        ".jpeg": {"image/jpeg"},
    }
    if extension not in allowed or media not in allowed[extension]:
        raise ValueError("unsupported_attachment")
    if extension in {".json", ".har"}:
        try:
            data = json.loads(
                content,
                object_pairs_hook=_unique_object,
                parse_constant=lambda _: (_ for _ in ()).throw(ValueError()),
            )
            stack = [(data, 0)]
            count = 0
            while stack:
                value, depth = stack.pop()
                count += 1
                if depth > 16 or count > 20000:
                    raise ValueError("attachment_structure_limit")
                if isinstance(value, dict):
                    stack.extend((v, depth + 1) for v in value.values())
                elif isinstance(value, list):
                    stack.extend((v, depth + 1) for v in value)
            if extension == ".har":
                if type(data) is not dict or type(data.get("log")) is not dict:
                    raise ValueError("invalid_har")
                entries = data["log"].get("entries")
                if type(entries) is not list or len(entries) > 256:
                    raise ValueError("invalid_har")
                sanitized = []
                for entry in entries:
                    request, response = entry["request"], entry["response"]
                    method, url, status = (
                        request["method"],
                        request["url"],
                        response["status"],
                    )
                    if (
                        type(url) is not str
                        or len(url) > 4096
                        or method
                        not in {
                            "GET",
                            "HEAD",
                            "POST",
                            "PUT",
                            "PATCH",
                            "DELETE",
                            "OPTIONS",
                        }
                        or type(status) is not int
                        or not 0 <= status <= 599
                    ):
                        raise ValueError("invalid_har_entry")
                    parsed = urlsplit(url)
                    if (
                        parsed.scheme not in {"http", "https"}
                        or not parsed.hostname
                        or parsed.username
                        or parsed.password
                    ):
                        raise ValueError("invalid_har_url")
                    sanitized.append(
                        {
                            "method": method,
                            "origin": urlunsplit(
                                (parsed.scheme, parsed.netloc, "", "", "")
                            ),
                            "status": status,
                        }
                    )
                data = {"source": "untrusted_upload", "entries": sanitized}
            else:
                from beeui_module.artifacts.redaction import redact_value

                data = redact_value(data)

            def sanitize(value):
                if isinstance(value, dict):
                    normalized = {
                        redact(key): sanitize(item) for key, item in value.items()
                    }
                    if len(normalized) != len(value):
                        raise ValueError("redacted_attachment_key_collision")
                    return normalized
                if isinstance(value, list):
                    return [sanitize(item) for item in value]
                return redact(value) if isinstance(value, str) else value

            content = json.dumps(
                sanitize(data), ensure_ascii=True, allow_nan=False
            ).encode()
        except ValueError, TypeError, KeyError, UnicodeError, RecursionError:
            raise ValueError("invalid_structured_attachment") from None
    elif extension in {".txt", ".md"}:
        value = content.decode("utf-8")
        if any(ord(c) < 32 and c not in "\n\r\t" for c in value):
            raise ValueError("invalid_text_attachment")
        content = redact(value).encode()
    elif extension == ".png":
        if not content.startswith(b"\x89PNG\r\n\x1a\n"):
            raise ValueError("invalid_png")
        position, kinds, compressed = 8, [], bytearray()
        width = height = channels = 0
        while position < len(content):
            if position + 12 > len(content):
                raise ValueError("invalid_png")
            length = int.from_bytes(content[position : position + 4])
            kind = content[position + 4 : position + 8]
            if (
                any(not (65 <= value <= 90 or 97 <= value <= 122) for value in kind)
                or kind[2] & 32
                or not kind[0] & 32
                and kind not in {b"IHDR", b"PLTE", b"IDAT", b"IEND"}
                or kind == b"IDAT"
                and b"IDAT" in kinds
                and kinds[-1] != b"IDAT"
            ):
                raise ValueError("invalid_png")
            end = position + 12 + length
            if end > len(content) or zlib.crc32(
                content[position + 4 : end - 4]
            ) != int.from_bytes(content[end - 4 : end]):
                raise ValueError("invalid_png")
            data = content[position + 8 : end - 4]
            if not kinds:
                if kind != b"IHDR" or length != 13:
                    raise ValueError("invalid_png")
                width, height = struct.unpack(">II", data[:8])
                channels = {0: 1, 2: 3, 4: 2, 6: 4}.get(data[9], 0)
                if (
                    not 1 <= width <= 4096
                    or not 1 <= height <= 4096
                    or data[8] != 8
                    or data[9] not in {0, 2, 4, 6}
                    or data[10:] != b"\0\0\0"
                ):
                    raise ValueError("unsupported_png")
            if kind == b"PLTE" and (
                b"PLTE" in kinds
                or b"IDAT" in kinds
                or not 3 <= length <= 768
                or length % 3
            ):
                raise ValueError("invalid_png")
            if kind == b"IDAT":
                compressed.extend(data)
            if kind == b"IEND" and (length or end != len(content)):
                raise ValueError("invalid_png")
            kinds.append(kind)
            position = end
        if (
            kinds.count(b"IHDR") != 1
            or not kinds
            or kinds[-1] != b"IEND"
            or not compressed
        ):
            raise ValueError("invalid_png")
        decoder = zlib.decompressobj()
        try:
            raw = decoder.decompress(compressed, 64 * 1024 * 1024 + 1)
        except zlib.error:
            raise ValueError("invalid_png") from None
        row_bytes = 1 + width * channels
        if (
            len(raw) != height * row_bytes
            or any(raw[index] > 4 for index in range(0, len(raw), row_bytes))
            or len(raw) > 64 * 1024 * 1024
            or not decoder.eof
            or decoder.unused_data
        ):
            raise ValueError("invalid_png")
    else:
        if not content.startswith(b"\xff\xd8\xff"):
            raise ValueError("invalid_jpeg")
        position, frame, scanned, ended = 2, False, False, False
        tables = set()
        while position < len(content):
            if content[position] != 255:
                raise ValueError("invalid_jpeg")
            while position < len(content) and content[position] == 255:
                position += 1
            if position >= len(content):
                raise ValueError("invalid_jpeg")
            marker = content[position]
            position += 1
            if marker == 217:
                ended = position == len(content)
                break
            if (
                marker in {0, 216}
                or 208 <= marker <= 215
                or position + 2 > len(content)
            ):
                raise ValueError("invalid_jpeg")
            length = int.from_bytes(content[position : position + 2])
            end = position + length
            if length < 2 or end > len(content):
                raise ValueError("invalid_jpeg")
            if marker in {192, 193, 194}:
                if frame or length < 8 or content[position + 2] != 8:
                    raise ValueError("invalid_jpeg")
                height, width = struct.unpack(
                    ">HH", content[position + 3 : position + 7]
                )
                channels = content[position + 7]
                if (
                    channels not in {1, 3}
                    or length != 8 + 3 * channels
                    or not 1 <= width <= 4096
                    or not 1 <= height <= 4096
                ):
                    raise ValueError("invalid_jpeg")
                frame = True
            if marker in {196, 219}:
                if length <= 2:
                    raise ValueError("invalid_jpeg")
                tables.add(marker)
            position = end
            if marker == 218:
                if not frame or length < 6 or tables != {196, 219}:
                    raise ValueError("invalid_jpeg")
                channels = content[end - length + 2]
                if not 1 <= channels <= 3 or length != 6 + 2 * channels:
                    raise ValueError("invalid_jpeg")
                scanned = True
                scan_start = position
                while position < len(content):
                    found = content.find(b"\xff", position)
                    if found < 0 or found + 1 >= len(content):
                        raise ValueError("invalid_jpeg")
                    if content[found + 1] == 0 or 208 <= content[found + 1] <= 215:
                        position = found + 2
                    else:
                        position = found
                        break
                if position <= scan_start:
                    raise ValueError("invalid_jpeg")
        if not frame or not scanned or not ended:
            raise ValueError("invalid_jpeg")
    if not 1 <= len(content) <= 2 * 1024 * 1024:
        raise ValueError("normalized_attachment_limit")
    return {
        "filename": "observation" + extension,
        "content_type": media,
        "payload": content,
        "size": len(content),
        "storage_status": "stored",
    }
