"""Authenticated Zepto MCP client used by the assistant and its smoke check."""

from __future__ import annotations

import json
import os
import tempfile
import uuid
import webbrowser
from contextlib import AsyncExitStack
from pathlib import Path
from urllib.parse import parse_qs, urlparse

import httpx2
from mcp import ClientSession
from mcp.client.auth import AuthorizationCodeResult, OAuthClientProvider, TokenStorage
from mcp.client.streamable_http import streamable_http_client
from mcp.shared.auth import (
    OAuthClientInformationFull,
    OAuthClientMetadata,
    OAuthToken,
)


MCP_URL = "https://mcp.zepto.co.in/mcp"
# Zepto-issued public OAuth client identifier. Keep registration secrets out of source.
ZEPTO_CLIENT_ID = "4b8e449eb4e377b0ee2d63186fa99ded"
REDIRECT_URI = "http://localhost/callback"


def _data_dir() -> Path:
    if os.name == "nt":
        base = Path(os.environ.get("LOCALAPPDATA", Path.home() / "AppData" / "Local"))
    else:
        base = Path(os.environ.get("XDG_DATA_HOME", Path.home() / ".local" / "share"))
    return base / "voice_assistant"


def _token_path() -> Path:
    return _data_dir() / "zepto_mcp_tokens.bin"


def _protect(data: bytes) -> bytes:
    if os.name == "nt":
        try:
            import win32crypt
        except ImportError as exc:
            raise RuntimeError("Install pywin32 to securely store Zepto tokens on Windows") from exc
        return win32crypt.CryptProtectData(data, "Zepto MCP OAuth tokens", None, None, None, 0)
    return data


def _unprotect(data: bytes) -> bytes:
    if os.name == "nt":
        import win32crypt

        return win32crypt.CryptUnprotectData(data, None, None, None, 0)[1]
    return data


class ZeptoTokenStorage(TokenStorage):
    """Persist refreshed MCP tokens outside the project directory."""

    def __init__(self) -> None:
        self.path = _token_path()
        self.tokens = self._load()
        self.client_info = OAuthClientInformationFull(
            client_id=ZEPTO_CLIENT_ID,
            client_name="Sofi",
            redirect_uris=[REDIRECT_URI],
            grant_types=["authorization_code", "refresh_token"],
            response_types=["code"],
            token_endpoint_auth_method="none",
            application_type="native",
        )

    def _load(self) -> OAuthToken | None:
        if not self.path.exists():
            return None
        try:
            return OAuthToken.model_validate(json.loads(_unprotect(self.path.read_bytes())))
        except Exception as exc:
            print(f"Saved Zepto token could not be loaded ({type(exc).__name__}); sign in again.")
            return None

    async def get_tokens(self) -> OAuthToken | None:
        return self.tokens

    async def set_tokens(self, tokens: OAuthToken) -> None:
        self.path.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
        if os.name != "nt":
            self.path.parent.chmod(0o700)
        raw = _protect(tokens.model_dump_json().encode("utf-8"))
        fd, temp_path = tempfile.mkstemp(prefix="zepto-mcp-", suffix=".tmp", dir=self.path.parent)
        try:
            with os.fdopen(fd, "wb") as file:
                file.write(raw)
                file.flush()
                os.fsync(file.fileno())
            os.replace(temp_path, self.path)
            if os.name != "nt":
                self.path.chmod(0o600)
            self.tokens = tokens
        finally:
            if os.path.exists(temp_path):
                os.unlink(temp_path)

    async def get_client_info(self) -> OAuthClientInformationFull | None:
        return self.client_info

    async def set_client_info(self, client_info: OAuthClientInformationFull) -> None:
        self.client_info = client_info


async def _open_browser(url: str) -> None:
    print("Opening Zepto authorization page:")
    print(url)
    webbrowser.open(url)


async def _wait_for_callback() -> AuthorizationCodeResult:
    print(f"After Zepto sign-in, paste the callback URL for {REDIRECT_URI}.")
    callback_url = input("Callback URL: ").strip()
    params = parse_qs(urlparse(callback_url).query)
    if "error" in params:
        raise RuntimeError(
            f"Zepto authorization failed: {params['error'][0]} "
            f"{params.get('error_description', [''])[0]}"
        )
    if "code" not in params:
        raise RuntimeError("The callback URL did not contain an authorization code")
    return AuthorizationCodeResult(
        code=params["code"][0],
        state=params.get("state", [None])[0],
        iss=params.get("iss", [None])[0],
    )


class ZeptoMCPClient:
    """Long-lived MCP connection; keep it open to preserve the MCP session."""

    def __init__(self) -> None:
        self._stack: AsyncExitStack | None = None
        self._session: ClientSession | None = None
        self._device_id = self._load_device_id()

    @property
    def device_id(self) -> str:
        return self._device_id

    @staticmethod
    def _load_device_id() -> str:
        path = _data_dir() / "zepto_mcp_device_id"
        try:
            return path.read_text(encoding="utf-8").strip()
        except OSError:
            device_id = str(uuid.uuid4())
            path.parent.mkdir(parents=True, exist_ok=True)
            if os.name != "nt":
                path.parent.chmod(0o700)
            path.write_text(device_id, encoding="utf-8")
            if os.name != "nt":
                path.chmod(0o600)
            return device_id

    async def connect(self) -> None:
        if self._session is not None:
            return
        stack = AsyncExitStack()
        try:
            metadata = OAuthClientMetadata(
                client_name="Sofi",
                redirect_uris=[REDIRECT_URI],
                grant_types=["authorization_code", "refresh_token"],
                response_types=["code"],
                token_endpoint_auth_method="none",
                application_type="native",
            )
            oauth = OAuthClientProvider(
                server_url=MCP_URL,
                client_metadata=metadata,
                storage=ZeptoTokenStorage(),
                redirect_handler=_open_browser,
                callback_handler=_wait_for_callback,
            )
            http_client = await stack.enter_async_context(httpx2.AsyncClient(auth=oauth))
            read_stream, write_stream = await stack.enter_async_context(
                streamable_http_client(MCP_URL, http_client=http_client)
            )
            session = await stack.enter_async_context(ClientSession(read_stream, write_stream))
            await session.initialize()
            self._stack = stack
            self._session = session
        except Exception:
            await stack.aclose()
            raise

    async def list_tools(self) -> list[dict]:
        await self.connect()
        result = await self._session.list_tools()
        return [tool.model_dump(mode="json") for tool in result.tools]

    async def call_tool(self, name: str, arguments: dict | None = None) -> dict:
        await self.connect()
        result = await self._session.call_tool(name, arguments=arguments or {})
        return result.model_dump(mode="json", by_alias=True)

    async def close(self) -> None:
        if self._stack is not None:
            await self._stack.aclose()
        self._stack = None
        self._session = None


def format_result(result: dict) -> str:
    """Return readable JSON for Strands while preserving structured MCP data."""
    return json.dumps(result, ensure_ascii=False, indent=2, default=str)
