import secrets
from datetime import UTC, datetime, timedelta


class AccessApplication:
    def __init__(self, mode="vulnerable", relationship="horizontal"):
        self.mode = mode
        self.tokens = [secrets.token_urlsafe(32), secrets.token_urlsafe(32)]
        self.accounts = [
            {
                "id": "account-a",
                "role": "admin" if relationship == "vertical" else "user",
            },
            {"id": "account-b", "role": "user"},
        ]
        self.objects = [
            {"id": "object-a", "private": secrets.token_hex(16)},
            {"id": "object-b", "private": secrets.token_hex(16)},
        ]
        self.requests = []

    def get(self, path, credential):
        path = path.split("?", 1)[0]
        index = self.tokens.index(credential) if credential in self.tokens else None
        self.requests.append((path, index))
        if path == "/whoami":
            if self.mode == "redirect":
                return 302, {}
            if index is None or self.mode == "expired":
                return 401, {}
            return 200, self.accounts[0 if self.mode == "substituted" else index]
        if path not in {"/records/a", "/records/b"}:
            return 404, {}
        selected = 0 if path.endswith("/a") else 1
        if self.mode == "denial_disclosure" and index == 1 and selected == 0:
            return 403, self.objects[selected]
        if self.mode == "anonymous_disclosure" and index is None:
            return 401, self.objects[selected]
        if index is None and self.mode != "public":
            return 401, {}
        if index != selected and self.mode == "fixed":
            return 403, {}
        if index != selected and self.mode == "ambiguous":
            return 200, {"message": "Welcome"}
        if self.mode == "missing_private":
            return 200, {"id": self.objects[selected]["id"]}
        return 200, self.objects[selected]


def make_test_profile(origin, relationship="horizontal", public=False):
    now = datetime.now(UTC)
    return {
        "profile_id": "controlled-access",
        "origin": origin,
        "operator_ids": ["alice"],
        "authorization_reference": "controlled-fixture-owner-authorization",
        "valid_from": (now - timedelta(minutes=1)).isoformat(),
        "expires_at": (now + timedelta(minutes=10)).isoformat(),
        "principals": [
            {
                "principal_id": name,
                "role": "admin"
                if index == 0 and relationship == "vertical"
                else "user",
                "credential_env": "BEEAGENT_ACCESS_" + name.upper(),
                "account_id": "account-" + name,
                "identity_path": "/whoami",
                "identity_field": "id",
                "role_field": "role",
                "baseline_path": "/records/" + name,
                "object_field": "id",
                "object_id": "object-" + name,
            }
            for index, name in enumerate(("a", "b"))
        ],
        "resource": {
            "resource_id": "approved-object",
            "path": "/records/a",
            "owner_id": "a",
            "object_field": "id",
            "object_id": "object-a",
            "private_fields": ["private"],
            "expected_access": [True, public],
            "public": public,
        },
        "relationship": relationship,
        "request_budget": 8,
        "seconds": 30,
        "read_only": True,
        "local_lab": True,
    }


class AutonomousApplication(AccessApplication):
    def __init__(self, mode="vulnerable", relationship="horizontal", alternate=False):
        super().__init__(mode, relationship)
        self.alternate = alternate
        self.resources = []
        for group in range(2 if mode == "multiple" else 1):
            for index in range(2):
                identifier = secrets.token_hex(8)
                path = f"/observed-{group}/{index}-{identifier}"
                payload = {
                    "id": identifier,
                    "owner_id": self.accounts[index]["id"],
                    "private": secrets.token_hex(16),
                    "href": path,
                    "type": "resource-" + str(group),
                    "visibility": "public"
                    if mode == "public"
                    else "unknown"
                    if mode == "ambiguous"
                    else "private",
                }
                if alternate:
                    payload = {
                        "uuid": identifier,
                        "owner": {"id": self.accounts[index]["id"]},
                        "location": {
                            "latitude": secrets.randbelow(1000),
                            "longitude": secrets.randbelow(1000),
                        },
                        "href": path,
                        "type": "vehicle",
                        "visibility": payload["visibility"],
                    }
                if mode == "no_owner":
                    payload.pop("owner_id", None)
                    payload.pop("owner", None)
                self.resources.append((path, index, group, payload))

    def get(self, path, credential):
        index = self.tokens.index(credential) if credential in self.tokens else None
        self.requests.append((path, index))
        if path == "/" and self.mode in {"html", "login"}:
            return (
                200,
                '<a href="/surface">application</a>'
                if self.mode == "html"
                else '<form method="post" action="/login">Login</form>',
            )
        if path == "/" or path == "/surface" and self.mode == "html":
            if index is None or self.mode == "expired":
                return 401, {}
            identity = self.accounts[0 if self.mode == "substituted" else index]
            items = [p for _, owner, _, p in self.resources if owner == index]
            if self.mode == "no_owner":
                items = [
                    {
                        key: value
                        for key, value in p.items()
                        if key not in {"owner", "owner_id"}
                    }
                    for p in items
                ]
            return 200, {
                "data": {"user": identity, "items": items}
            } if self.alternate else {"identity": identity, "resources": items}
        selected = next((entry for entry in self.resources if entry[0] == path), None)
        if selected is None:
            return 404, {}
        _, owner, group, payload = selected
        if index is None and self.mode != "public":
            return 401, {}
        if index != owner and (
            self.mode == "fixed" or self.mode == "multiple" and group == 0
        ):
            return 403, {}
        if index != owner and self.mode == "ambiguous":
            return 200, {"message": "Welcome"}
        return 200, payload


def autonomous_profile(origin, relationship="horizontal", expectation="owned_private"):
    profile = make_test_profile(origin, relationship)
    profile.pop("resource")
    profile.pop("relationship")
    profile.update(
        discovery=True,
        expectation=expectation,
        discovery_budget=4,
        request_budget=20,
        seconds=60,
    )
    profile["principals"] = [
        {
            key: p[key]
            for key in ("principal_id", "account_id", "role", "credential_env")
        }
        for p in profile["principals"]
    ]
    return profile
