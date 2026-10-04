# Zepto MCP + Python Setup Guide

This guide explains how to connect a Python application such as **Sofi** to the official Zepto MCP server using the Python MCP SDK and Zepto OAuth.

## 1. Overview

The working architecture is:

```text
Python application
       │
       ▼
MCP Python SDK
       │
       ▼
OAuth / PKCE
       │
       ▼
Zepto OAuth
       │
       ▼
Zepto MCP
https://mcp.zepto.co.in/mcp
       │
       ▼
Zepto tools
```

Zepto MCP endpoint:

```text
https://mcp.zepto.co.in/mcp
```

OAuth server:

```text
https://auth.zepto.co.in
```

---

# 2. Important: Why `mcp-remote` Didn't Work

The first test was:

```powershell
npx -y mcp-remote https://mcp.zepto.co.in/mcp
```

The MCP connection itself worked, but OAuth failed:

```text
POST /register
HTTP 403
```

Zepto's OAuth server rejected the dynamically generated OAuth client.

We therefore manually registered an OAuth client and made the Python MCP SDK reuse that existing client.

Do **not** rely on automatic dynamic client registration for this setup.

---

# 3. Requirements

## Windows

Recommended:

* Windows 10/11
* Python 3.11+
* PowerShell
* Node.js/npm (only needed for the optional `mcp-remote` test)

## Python packages

Inside your Python virtual environment:

```powershell
pip install mcp httpx2
```

Activate the environment first:

```powershell
.\.venv\Scripts\Activate.ps1
```

Use your project's existing virtual environment if you already have one.

---

# 4. Create a Zepto OAuth Client

Zepto OAuth registration endpoint:

```text
https://auth.zepto.co.in/register
```

The simplest working native-client registration uses:

```text
Redirect URI:
http://localhost/callback
```

PowerShell:

```powershell
$body = @{
    client_name = "Sofi"
    redirect_uris = @(
        "http://localhost/callback"
    )
    grant_types = @(
        "authorization_code",
        "refresh_token"
    )
    response_types = @(
        "code"
    )
    token_endpoint_auth_method = "none"
    application_type = "native"
} | ConvertTo-Json

try {
    Invoke-RestMethod `
        -Uri "https://auth.zepto.co.in/register" `
        -Method POST `
        -ContentType "application/json" `
        -Body $body `
        -ErrorAction Stop
}
catch {
    $response = $_.Exception.Response

    Write-Host "HTTP Status:" $response.StatusCode
    Write-Host "Headers:"
    $response.Headers

    Write-Host ""
    Write-Host "Body:"

    $reader = New-Object System.IO.StreamReader(
        $response.GetResponseStream()
    )

    $reader.ReadToEnd()
}
```

A successful response will contain a value similar to:

```text
client_id : xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx
```

Save the `client_id`.

## Security

The response may also contain:

```text
registration_access_token
```

Do **not** put this token into your application.

Do not commit it to Git.

It is not required for normal OAuth authentication.

If a registration access token has been exposed publicly, treat it as compromised and replace/revoke the registration if Zepto provides a mechanism to do so.

---

# 5. Configure the Client ID

In the Python application, set:

```python
ZEPTO_CLIENT_ID = "YOUR_CLIENT_ID"
```

Do not commit production credentials to Git.

For a real application, use an environment variable instead:

```powershell
$env:ZEPTO_CLIENT_ID = "YOUR_CLIENT_ID"
```

Then:

```python
import os

ZEPTO_CLIENT_ID = os.environ["ZEPTO_CLIENT_ID"]
```

---

# 6. Important Redirect URI

The redirect URI must exactly match the URI registered with Zepto.

This setup uses:

```text
http://localhost/callback
```

Therefore the Python application must use exactly:

```python
REDIRECT_URI = "http://localhost/callback"
```

Do not change it to:

```text
http://127.0.0.1/callback
```

or:

```text
http://localhost:43069/callback
```

unless that URI has also been registered with Zepto.

---

# 7. Python OAuth Storage

The important part of this integration is preventing the MCP SDK from dynamically registering another OAuth client.

Create a storage implementation:

```python
class ZeptoTokenStorage(TokenStorage):

    def __init__(self):
        self.tokens = None

        self.client_info = OAuthClientInformationFull(
            client_id=ZEPTO_CLIENT_ID,
            client_name="Sofi",
            redirect_uris=[REDIRECT_URI],
            grant_types=[
                "authorization_code",
                "refresh_token",
            ],
            response_types=["code"],
            token_endpoint_auth_method="none",
            application_type="native",
        )

    async def get_tokens(self):
        return self.tokens

    async def set_tokens(self, tokens):
        self.tokens = tokens

    async def get_client_info(self):
        return self.client_info

    async def set_client_info(self, client_info):
        self.client_info = client_info
```

The critical function is:

```python
async def get_client_info(self):
    return self.client_info
```

This tells the MCP SDK:

> Use this already registered Zepto OAuth client.

Instead of:

```text
/register
```

which previously resulted in:

```text
403 Forbidden
```

---

# 8. Complete Test Client

Create:

```text
scripts/test_zepto_mcp.py
```

Use:

```python
import asyncio
import webbrowser
from urllib.parse import parse_qs, urlparse

import httpx2

from mcp import ClientSession
from mcp.client.auth import (
    AuthorizationCodeResult,
    OAuthClientProvider,
    TokenStorage,
)
from mcp.client.streamable_http import streamable_http_client
from mcp.shared.auth import (
    OAuthClientInformationFull,
    OAuthClientMetadata,
    OAuthToken,
)


MCP_URL = "https://mcp.zepto.co.in/mcp"

ZEPTO_CLIENT_ID = "YOUR_CLIENT_ID"

REDIRECT_URI = "http://localhost/callback"


class ZeptoTokenStorage(TokenStorage):

    def __init__(self):
        self.tokens: OAuthToken | None = None

        self.client_info = OAuthClientInformationFull(
            client_id=ZEPTO_CLIENT_ID,
            client_name="Sofi",
            redirect_uris=[REDIRECT_URI],
            grant_types=[
                "authorization_code",
                "refresh_token",
            ],
            response_types=["code"],
            token_endpoint_auth_method="none",
            application_type="native",
        )

    async def get_tokens(self):
        return self.tokens

    async def set_tokens(self, tokens):
        self.tokens = tokens

    async def get_client_info(self):
        print("Using pre-registered Zepto OAuth client")
        return self.client_info

    async def set_client_info(self, client_info):
        self.client_info = client_info


async def open_browser(authorization_url: str):

    print()
    print("Opening Zepto authorization page...")
    print()
    print(authorization_url)
    print()

    webbrowser.open(authorization_url)


async def wait_for_callback():

    print()
    print("Waiting for OAuth callback...")
    print(f"Expected callback: {REDIRECT_URI}")
    print()

    callback_url = input(
        "Paste the callback URL: "
    ).strip()

    parsed = urlparse(callback_url)

    params = parse_qs(parsed.query)

    if "error" in params:
        raise RuntimeError(
            f"OAuth authorization failed: "
            f"{params['error'][0]} "
            f"{params.get('error_description', [''])[0]}"
        )

    return AuthorizationCodeResult(
        code=params["code"][0],
        state=params.get("state", [None])[0],
        iss=params.get("iss", [None])[0],
    )


async def main():

    metadata = OAuthClientMetadata(
        client_name="Sofi",
        redirect_uris=[REDIRECT_URI],
        grant_types=[
            "authorization_code",
            "refresh_token",
        ],
        response_types=["code"],
        token_endpoint_auth_method="none",
        application_type="native",
    )

    storage = ZeptoTokenStorage()

    oauth = OAuthClientProvider(
        server_url=MCP_URL,
        client_metadata=metadata,
        storage=storage,
        redirect_handler=open_browser,
        callback_handler=wait_for_callback,
    )

    async with httpx2.AsyncClient(
        auth=oauth
    ) as http_client:

        async with streamable_http_client(
            MCP_URL,
            http_client=http_client,
        ) as (read, write):

            async with ClientSession(
                read,
                write
            ) as session:

                print("Initializing MCP session...")

                await session.initialize()

                print()
                print("Connected to Zepto MCP!")
                print()

                result = await session.list_tools()

                print("Available tools:")

                for tool in result.tools:
                    print(
                        f"  - {tool.name}"
                    )

                print()

                print(
                    f"Total tools: "
                    f"{len(result.tools)}"
                )


if __name__ == "__main__":
    asyncio.run(main())
```

Replace:

```python
YOUR_CLIENT_ID
```

with the `client_id` returned by Zepto.

---

# 9. Run the Test

From the project directory:

```powershell
python .\scripts\test_zepto_mcp.py
```

The first time, the program should open the Zepto OAuth authorization page.

After authentication, the MCP session should initialize.

Expected result:

```text
Using pre-registered Zepto OAuth client

Opening Zepto authorization page...

Initializing MCP session...

Connected to Zepto MCP!
```

Then the available tools should be listed.

---

# 10. Expected Zepto Tools

The current successful connection exposed 23 tools:

```text
zepto_shop
search_products
search_multiple_products
get_product_details
get_location_serviceability
select_store
list_saved_addresses
select_saved_address
add_saved_address
update_drop_zone
get_user_details
update_user_name
view_cart
update_cart
get_payment_methods
create_order
create_online_payment_order
create_wallet_order
create_upi_reserve_pay_order
check_payment_status
get_order_detail
list_order_history
get_past_order_items
```

This confirms that the MCP connection is working, not merely OAuth authentication.

---

# 11. Testing a Tool

Once connected, you can call an MCP tool with:

```python
result = await session.call_tool(
    "search_products",
    {
        # tool arguments go here
    }
)
```

The exact arguments should be obtained from the tool definition rather than guessed.

You can inspect the schemas with:

```python
result = await session.list_tools()

for tool in result.tools:

    print(tool.name)
    print(tool.description)
    print(tool.inputSchema)
    print()
```

---

# 12. Sofi Integration Architecture

Once the standalone test works, don't put all the OAuth/MCP code inside Sofi's main agent loop.

A cleaner architecture is:

```text
                    Sofi
                     │
                     ▼
              Agent / Planner
                     │
                     ▼
              Tool Manager
                     │
          ┌──────────┴──────────┐
          │                     │
       Local Tools          Zepto MCP
                                │
                                ▼
                         OAuth Provider
                                │
                                ▼
                         Zepto MCP Server
```

Ideally create something like:

```text
sofi/
├── agent/
├── tools/
├── integrations/
│   └── zepto/
│       ├── client.py
│       ├── auth.py
│       └── tools.py
└── main.py
```

Then the rest of Sofi doesn't need to know the OAuth implementation details.

---

# 13. Security Recommendation

Zepto exposes tools that can perform real-world actions.

There is an important difference between:

### Read operations

Examples:

```text
search_products
get_product_details
view_cart
get_order_detail
list_order_history
get_past_order_items
```

These are relatively safe for an autonomous assistant.

### State-changing operations

Examples:

```text
update_cart
add_saved_address
update_drop_zone
select_saved_address
```

These should generally require additional validation.

### Financial / order operations

Especially:

```text
create_order
create_online_payment_order
create_wallet_order
create_upi_reserve_pay_order
```

These should **never be freely executed by an LLM without a confirmation layer**.

Recommended flow:

```text
User:
"Order milk."

        ↓

Sofi searches products

        ↓

Sofi shows:
Milk
₹XX
Quantity: 1

        ↓

Sofi asks:
"Should I place the order?"

        ↓

User confirms

        ↓

Sofi executes order/payment tool
```

Do not let an LLM independently decide to spend money.

---

# 14. Troubleshooting

## `403 Forbidden` from `/register`

If you see:

```text
POST /register
403
```

the MCP client is attempting dynamic OAuth registration.

Make sure your Python `TokenStorage` returns the existing client:

```python
async def get_client_info(self):
    return self.client_info
```

---

## Redirect URI mismatch

If OAuth complains about the redirect URI, verify that these are identical:

Zepto registration:

```text
http://localhost/callback
```

Python:

```python
REDIRECT_URI = "http://localhost/callback"
```

Even changing `localhost` to `127.0.0.1` can matter.

---

## `mcp-remote` doesn't support static client options

Our installed version was:

```text
mcp-remote 0.14.3
```

Its CLI showed:

```text
Usage: mcp-remote <https://server-url> [callback-port] [--debug]
```

Therefore this option should not be used with that CLI:

```text
--static-oauth-client-info
```

For this integration, use the Python MCP SDK directly.

---

# 15. Git Security

Add credentials/configuration files to `.gitignore`.

For example:

```gitignore
.env
*.token
zepto_client.json
```

Prefer environment variables:

```powershell
$env:ZEPTO_CLIENT_ID = "..."
```

and:

```python
import os

ZEPTO_CLIENT_ID = os.environ["ZEPTO_CLIENT_ID"]
```

Never commit:

```text
registration_access_token
access_token
refresh_token
client_secret
```

to Git.

---

# 16. Final Working Configuration

The setup that worked was:

```text
MCP:
https://mcp.zepto.co.in/mcp

OAuth:
https://auth.zepto.co.in

OAuth flow:
Authorization Code + PKCE

Client:
Pre-registered native OAuth client

Redirect:
http://localhost/callback

Python:
MCP Python SDK

Transport:
Streamable HTTP

Result:
23 Zepto MCP tools available
```

The key fix was:

```text
Dynamic OAuth registration
          ↓
        403 ❌

Pre-register Zepto OAuth client
          ↓
Use existing client in Python OAuthClientProvider
          ↓
       OAuth ✅
          ↓
       MCP ✅
          ↓
     23 tools ✅
```
