__copyright__ = "Copyright (c) 2024-2025 Alex Laird"
__license__ = "MIT"

import os
from urllib.parse import urlencode


class AmazonInConstants:
    """
    Custom constants class for Amazon India (amazon.in) domain.
    """

    ##########################################################################
    # General URL - Modified for Amazon India
    ##########################################################################

    BASE_URL = "https://www.amazon.in"

    ##########################################################################
    # URLs for AmazonSession
    ##########################################################################

    SIGN_IN_URL = f"{BASE_URL}/ap/signin"
    SIGN_IN_QUERY_PARAMS = {"openid.pape.max_auth_age": "0",
                            "openid.return_to": f"{BASE_URL}/?ref_=nav_custrec_signin",
                            "openid.identity": "http://specs.openid.net/auth/2.0/identifier_select",
                            "openid.assoc_handle": "inflex",  # Changed from usflex to inflex for India
                            "openid.mode": "checkid_setup",
                            "openid.claimed_id": "http://specs.openid.net/auth/2.0/identifier_select",
                            "openid.ns": "http://specs.openid.net/auth/2.0"}
    SIGN_IN_CLAIM_URL = f"{BASE_URL}/ax/claim"
    SIGN_OUT_URL = f"{BASE_URL}/gp/flex/sign-out.html"

    ##########################################################################
    # URLs for Orders
    ##########################################################################

    ORDER_HISTORY_URL = f"{BASE_URL}/your-orders/orders"
    ORDER_DETAILS_URL = f"{BASE_URL}/gp/your-account/order-details"
    HISTORY_FILTER_QUERY_PARAM = "timeFilter"

    ##########################################################################
    # URLs for Transactions
    ##########################################################################

    TRANSACTION_HISTORY_ROUTE = "/cpe/yourpayments/transactions"
    TRANSACTION_HISTORY_URL = f"{BASE_URL}{TRANSACTION_HISTORY_ROUTE}"

    ##########################################################################
    # Headers
    ##########################################################################

    BASE_HEADERS = {
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,image/apng,*/*;q=0.8,"
                  "application/signed-exchange;v=b3;q=0.7",
        "Accept-Encoding": "gzip, deflate, br, zstd",
        "Accept-Language": "en-IN,en;q=0.9,hi;q=0.8",  # Modified for India
        "Cache-Control": "max-age=0",
        "Device-Memory": "8",
        "Downlink": "10",
        "Dpr": "1",  # Reduced from 2 to 1
        "Ect": "4g",
        "Origin": BASE_URL,
        "Host": "www.amazon.in",  # Explicit host for India
        "Priority": "u=0, i",
        "Referer": f"{SIGN_IN_URL}?{urlencode(SIGN_IN_QUERY_PARAMS)}",
        "Rtt": "50",  # Increased RTT for India
        "Sec-Ch-Device-Memory": "8",
        "Sec-Ch-Dpr": "1",
        "Sec-Ch-Ua": '"Google Chrome";v="119", "Chromium";v="119", "Not?A_Brand";v="24"',  # Updated Chrome version
        "Sec-Ch-Ua-Mobile": "?0",
        "Sec-Ch-Ua-Platform": '"Windows"',  # Quoted for Windows
        "Sec-Ch-Ua-Platform-Version": '"10.0.0"',  # Windows 10
        "Sec-Ch-Viewport-Width": "1366",  # Common Indian screen width
        "Sec-Fetch-Dest": "document",
        "Sec-Fetch-Mode": "navigate",
        "Sec-Fetch-Site": "none",
        "Sec-Fetch-User": "?1",
        "Upgrade-Insecure-Requests": "1",
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) "
                      "Chrome/119.0.0.0 Safari/537.36",  # Reduced version to appear less bot-like
        "Viewport-Width": "1366"
    }

    ##########################################################################
    # Authentication
    ##########################################################################

    COOKIES_SET_WHEN_AUTHENTICATED = ["x-main"]
    JS_ROBOT_TEXT_REGEX = r"[.\s\S]*verify that you're not a robot[.\s\S]*Enable JavaScript[.\s\S]*"

    ##########################################################################
    # Currency - Modified for Indian Rupee
    ##########################################################################

    CURRENCY_SYMBOL = "₹"

    def format_currency(self,
                        amount: float) -> str:
        formatted_amt = "{currency_symbol}{amount:,.2f}".format(currency_symbol=self.CURRENCY_SYMBOL,
                                                                amount=abs(amount))
        if round(amount, 2) < 0:
            return f"-{formatted_amt}"
        return formatted_amt