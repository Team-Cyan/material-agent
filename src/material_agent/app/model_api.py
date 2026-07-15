from __future__ import annotations

import hmac
import json
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import parse_qs, urlsplit

from .model_catalog_service import ModelCatalogService


class ModelApiServer(ThreadingHTTPServer):
    def __init__(self, address, service: ModelCatalogService, token: str | None):
        super().__init__(address, ModelApiHandler)
        self.model_service = service
        self.api_token = token


class ModelApiHandler(BaseHTTPRequestHandler):
    server: ModelApiServer

    def do_GET(self) -> None:  # noqa: N802
        if not self._authorized():
            return
        path = urlsplit(self.path).path
        if path == "/health":
            self._json(HTTPStatus.OK, {"status": "ok"})
            return
        if path == "/v1/models":
            self._json(HTTPStatus.OK, {"models": self.server.model_service.list_models()})
            return
        if path == "/v1/model-selections":
            self._json(
                HTTPStatus.OK,
                {"selections": self.server.model_service.selections()},
            )
            return
        self._json(HTTPStatus.NOT_FOUND, {"error": "not_found"})

    def do_POST(self) -> None:  # noqa: N802
        if not self._authorized():
            return
        parts = self._model_action_parts()
        if parts is None:
            self._json(HTTPStatus.NOT_FOUND, {"error": "not_found"})
            return
        model_id, action = parts
        try:
            if action == "install":
                result = self.server.model_service.install(model_id)
            elif action == "select":
                result = self.server.model_service.select(model_id)
            else:
                self._json(HTTPStatus.NOT_FOUND, {"error": "not_found"})
                return
        except (OSError, ValueError) as error:
            self._json(HTTPStatus.BAD_REQUEST, {"error": str(error)})
            return
        self._json(HTTPStatus.OK, result)

    def do_DELETE(self) -> None:  # noqa: N802
        if not self._authorized():
            return
        path = urlsplit(self.path)
        parts = path.path.strip("/").split("/")
        if len(parts) != 3 or parts[:2] != ["v1", "models"]:
            self._json(HTTPStatus.NOT_FOUND, {"error": "not_found"})
            return
        force = parse_qs(path.query).get("force", ["false"])[0].lower() in {
            "1",
            "true",
            "yes",
        }
        try:
            result = self.server.model_service.delete(parts[2], force=force)
        except (OSError, ValueError) as error:
            self._json(HTTPStatus.BAD_REQUEST, {"error": str(error)})
            return
        self._json(HTTPStatus.OK, result)

    def log_message(self, format: str, *args) -> None:
        return

    def _authorized(self) -> bool:
        token = self.server.api_token
        if not token:
            return True
        header = self.headers.get("Authorization", "")
        expected = f"Bearer {token}"
        if hmac.compare_digest(header, expected):
            return True
        self._json(
            HTTPStatus.UNAUTHORIZED,
            {"error": "unauthorized"},
            extra_headers={"WWW-Authenticate": "Bearer"},
        )
        return False

    def _model_action_parts(self) -> tuple[str, str] | None:
        parts = urlsplit(self.path).path.strip("/").split("/")
        if len(parts) != 4 or parts[:2] != ["v1", "models"]:
            return None
        return parts[2], parts[3]

    def _json(
        self,
        status: HTTPStatus,
        payload: dict,
        *,
        extra_headers: dict[str, str] | None = None,
    ) -> None:
        body = (json.dumps(payload, ensure_ascii=False) + "\n").encode("utf-8")
        self.send_response(status.value)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        for key, value in (extra_headers or {}).items():
            self.send_header(key, value)
        self.end_headers()
        self.wfile.write(body)


def serve_model_api(
    service: ModelCatalogService,
    *,
    host: str,
    port: int,
    token: str | None,
) -> None:
    if host not in {"127.0.0.1", "::1", "localhost"} and not token:
        raise ValueError("a bearer token is required when model API listens beyond localhost")
    server = ModelApiServer((host, port), service, token)
    try:
        server.serve_forever()
    finally:
        server.server_close()
