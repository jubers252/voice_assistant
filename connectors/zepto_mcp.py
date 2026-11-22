"""Authenticated Zepto MCP client used by the assistant and its smoke check."""

from __future__ import annotations

import asyncio
import json
import os
import sys
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
REDIRECT_URI = "http://localhost/callback"
PROJECT_DIR = Path(__file__).resolve().parents[1]
TOKEN_PATH = PROJECT_DIR / "zepto_token"
CLIENT_CONFIG_PATH = PROJECT_DIR / "zepto_client.json"
DEVICE_ID_PATH = PROJECT_DIR / ".local" / "zepto" / "zepto_mcp_device_id"


def _write_private_file(path: Path, data: bytes, *, private_parent: bool = True) -> None:
    path.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
    if private_parent and os.name != "nt":
        path.parent.chmod(0o700)
    path.write_bytes(data)
    if os.name != "nt":
        path.chmod(0o600)


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

    def __init__(
        self,
        token_path: Path | None = None,
        client_info_path: Path | None = None,
    ) -> None:
        self.path = token_path or TOKEN_PATH
        self.client_info_path = client_info_path or CLIENT_CONFIG_PATH
        self.tokens = self._load()
        self.client_info = self._load_client_info()

    def _load_client_info(self) -> OAuthClientInformationFull | None:
        try:
            data = json.loads(self.client_info_path.read_text(encoding="utf-8-sig"))
            if not isinstance(data, dict):
                return None
            data.pop("registration_access_token", None)
            data.pop("registration_client_uri", None)
            if not data.get("redirect_uris") or REDIRECT_URI not in data["redirect_uris"]:
                return None
            if data.get("token_endpoint_auth_method") != "none":
                return None
            return OAuthClientInformationFull.model_validate(data)
        except (OSError, ValueError):
            return None

    def _load(self) -> OAuthToken | None:
        if not self.path.exists():
            return None
        try:
            token_data = _unprotect(self.path.read_bytes())
            return OAuthToken.model_validate(json.loads(token_data))
        except Exception as exc:
            print(f"Saved Zepto token could not be loaded ({type(exc).__name__}); sign in again.")
            return None

    async def get_tokens(self) -> OAuthToken | None:
        return self.tokens

    async def set_tokens(self, tokens: OAuthToken) -> None:
        data = _protect(tokens.model_dump_json().encode("utf-8"))
        _write_private_file(self.path, data)
        self.tokens = tokens

    async def get_client_info(self) -> OAuthClientInformationFull | None:
        return self.client_info

    async def set_client_info(self, client_info: OAuthClientInformationFull) -> None:
        self.client_info = client_info
        data = client_info.model_dump(mode="json")
        data.pop("registration_access_token", None)
        data.pop("registration_client_uri", None)
        _write_private_file(
            self.client_info_path,
            (json.dumps(data, ensure_ascii=False, indent=2) + "\n").encode("utf-8"),
            private_parent=False,
        )


async def _open_browser(url: str) -> None:
    print("Opening Zepto authorization page:")
    print(url)
    webbrowser.open(url)


async def _wait_for_callback() -> AuthorizationCodeResult:
    print(f"After Zepto sign-in, paste the callback URL for {REDIRECT_URI}.")
    try:
        callback_url = await asyncio.to_thread(input, "Callback URL: ")
    except EOFError as exc:
        raise RuntimeError(
            "Zepto sign-in requires an interactive terminal. Run this command in a terminal "
            "and paste the callback URL after authorization."
        ) from exc
    callback_url = callback_url.strip()
    query = parse_qs(urlparse(callback_url).query or callback_url)
    if "error" in query:
        raise RuntimeError(
            f"Zepto authorization failed: {query['error'][0]} "
            f"{query.get('error_description', [''])[0]}"
        )
    if "code" not in query:
        raise RuntimeError("The callback URL did not contain an authorization code")
    return AuthorizationCodeResult(
        code=query["code"][0],
        state=query.get("state", [None])[0],
        iss=query.get("iss", [None])[0],
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
        try:
            return DEVICE_ID_PATH.read_text(encoding="utf-8").strip()
        except OSError:
            device_id = str(uuid.uuid4())
            _write_private_file(DEVICE_ID_PATH, device_id.encode("utf-8"))
            return device_id

    async def connect(self) -> None:
        if self._session is not None:
            return
        stack = AsyncExitStack()
        try:
            oauth = OAuthClientProvider(
                server_url=MCP_URL,
                client_metadata=OAuthClientMetadata(
                    client_name="Sofi",
                    redirect_uris=[REDIRECT_URI],
                    grant_types=["authorization_code", "refresh_token"],
                    response_types=["code"],
                    token_endpoint_auth_method="none",
                    application_type="native",
                ),
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


async def _test_token_storage() -> None:
    """Check token serialization in a temporary directory; does not contact Zepto."""
    token = OAuthToken(
        access_token="test-access-token",
        token_type="Bearer",
        expires_in=3600,
        scope="test",
        refresh_token="test-refresh-token",
    )
    with tempfile.TemporaryDirectory(prefix="zepto-token-test-") as temp_dir:
        token_path = Path(temp_dir) / "tokens.bin"
        client_info_path = Path(temp_dir) / "client.json"
        storage = ZeptoTokenStorage(token_path, client_info_path)
        await storage.set_tokens(token)

        client_info = OAuthClientInformationFull(
            client_id="test-client",
            client_name="Sofi",
            redirect_uris=[REDIRECT_URI],
            token_endpoint_auth_method="none",
        )
        await storage.set_client_info(client_info)

        reloaded = ZeptoTokenStorage(token_path, client_info_path)
        saved = await reloaded.get_tokens()
        if saved is None or saved.access_token != token.access_token:
            raise AssertionError("Saved access token did not load")
        if saved.refresh_token != token.refresh_token:
            raise AssertionError("Saved refresh token did not load")
        saved_client_info = await reloaded.get_client_info()
        if saved_client_info is None or saved_client_info.client_id != client_info.client_id:
            raise AssertionError("Saved OAuth client info did not load")
        print("Token and OAuth client storage round-trip passed.")


if __name__ == "__main__" and "--test-token-storage" in sys.argv:
    asyncio.run(_test_token_storage())
