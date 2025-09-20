__copyright__ = "Copyright (c) 2024-2025 Alex Laird"
__license__ = "MIT"

from typing import Optional


class Selector:
    """
    Can be used to extend the definition of a CSS selector, allowing for programmatic inspection
    of the selections results before determining if selector matches.
    """

    def __init__(self,
                 css_selector: str,
                 text: Optional[str] = None) -> None:
        #: The CSS selector.
        self.css_selector: str = css_selector
        #: The text within the tag that must match.
        self.text: Optional[str] = text


class AmazonInSelectors:
    """
    Custom selectors for Amazon India (amazon.in) with updated CSS selectors that match
    the current HTML structure.
    """

    ##########################################################################
    # CSS selectors for Pages
    ##########################################################################

    BAD_INDEX_SELECTOR = "html.a-tablet"

    ##########################################################################
    # CSS selectors for AuthForms
    ##########################################################################

    SIGN_IN_FORM_SELECTOR = "form[name='signIn']"
    CLAIM_FORM_SELECTOR = "form[name='signIn'].auth-validate-form"
    INTENT_FORM_SELECTOR = "form#intent-confirmation-form"
    INTENT_MESSAGE_SELECTOR = "div#intent-confirmation-container"
    MFA_DEVICE_SELECT_FORM_SELECTOR = "form#auth-select-device-form"
    MFA_DEVICE_SELECT_INPUT_SELECTOR = "input[name='otpDeviceContext']"
    MFA_DEVICE_SELECT_INPUT_SELECTOR_VALUE = "value"
    MFA_FORM_SELECTOR = "form#auth-mfa-form"
    CAPTCHA_1_FORM_SELECTOR = "form.cvf-widget-form-captcha"
    CAPTCHA_2_FORM_SELECTOR = ["form:has(input[id^='captchacharacters'])", "form[action$='validateCaptcha']"]
    CAPTCHA_OTP_FORM_SELECTOR = "form#verification-code-form"
    DEFAULT_ERROR_TAG_SELECTOR = "div#auth-error-message-box"
    CAPTCHA_1_ERROR_SELECTOR = "div.cvf-widget-alert"
    CAPTCHA_2_ERROR_SELECTOR = "div.a-alert-info"

    ##########################################################################
    # CSS selectors for pagination
    ##########################################################################

    NEXT_PAGE_LINK_SELECTOR = "ul.a-pagination li.a-last a"

    ##########################################################################
    # Updated CSS selectors for Amazon India Order Entities and Fields
    ##########################################################################

    # Updated order history selectors for Amazon India
    ORDER_HISTORY_ENTITY_SELECTOR = [
        "div.a-box-group",  # Main container for orders
        "div[data-order-id]",  # If they use data attributes
        "div.order-card",  # Fallback
        "div.order",  # Fallback
        ".a-box-group .a-box",  # Individual order boxes
        ".order-info",  # Order info containers
    ]
    
    ORDER_HISTORY_COUNT_SELECTOR = [
        ".js-yo-container span.num-orders",
        ".order-count",
        "span:contains('orders')",
        ".a-size-base:contains('order')"
    ]
    
    ORDER_DETAILS_ENTITY_SELECTOR = [
        "div#orderDetails",
        "div#ordersContainer",
        ".order-details-container"
    ]
    
    ITEM_ENTITY_SELECTOR = [
        ".item-box",  # From the HTML we saw
        ".a-fixed-left-grid.item-box",
        "[data-component='purchasedItems'] .a-fixed-left-grid",
        "div:has(> div.yohtmlc-item)",
        ".yohtmlc-item"
    ]
    
    SHIPMENT_ENTITY_SELECTOR = [
        "div.delivery-box",  # From our analysis
        ".a-box.delivery-box",
        "[data-component='orderCard'] [data-component='shipments'] .a-box",
        "div.shipment"
    ]

    # Selectors for orders to skip (same as original)
    ORDER_SKIP_ITEMS = [
        ".brand-info-box .brand-logo img",
        "a.yohtmlc-order-details-link[href^='/wholefoodsmarket']",
        Selector("div.yohtmlc-shipment-status-primaryText", "Purchased at Amazon")
    ]
    
    ORDER_SKIP_TOTALS = [
        Selector("div.yohtmlc-shipment-status-primaryText", "Cancelled"),
        Selector("span.delivery-box__primary-text", "Cancelled")
    ]

    #####################################
    # Updated Item field selectors
    #####################################

    FIELD_ITEM_IMG_LINK_SELECTOR = "a img"
    FIELD_ITEM_QUANTITY_SELECTOR = [
        ".od-item-view-qty",
        "span.item-view-qty", 
        "span.product-image__qty",
        ".quantity"
    ]
    FIELD_ITEM_TITLE_SELECTOR = [
        ".yohtmlc-product-title",  # From the HTML we saw
        ".yohtmlc-product-title a",
        "[data-component='itemTitle']",
        ".yohtmlc-item a"
    ]
    FIELD_ITEM_LINK_SELECTOR = [
        ".yohtmlc-product-title a",  # From the HTML
        "[data-component='itemTitle'] a",
        ".yohtmlc-item a",
        "a:has(> .yohtmlc-product-title)"
    ]
    FIELD_ITEM_TAG_ITERATOR_SELECTOR = [".yohtmlc-item div"]
    FIELD_ITEM_PRICE_SELECTOR = [
        "[data-component='unitPrice'] .a-text-price :not(.a-offscreen)",
        ".yohtmlc-item .a-color-price",
        ".a-price .a-offscreen"
    ]
    FIELD_ITEM_SELLER_SELECTOR = ["[data-component='orderedMerchant']"] + FIELD_ITEM_TAG_ITERATOR_SELECTOR
    FIELD_ITEM_RETURN_SELECTOR = ["[data-component='itemReturnEligibility']"] + FIELD_ITEM_TAG_ITERATOR_SELECTOR

    #####################################
    # Updated Order field selectors for Amazon India
    #####################################

    FIELD_ORDER_DETAILS_LINK_SELECTOR = [
        "a.yohtmlc-order-details-link",
        ".order-details-link",
        "a[href*='order-details']"
    ]
    
    FIELD_ORDER_NUMBER_SELECTOR = [
        ".yohtmlc-order-id span[dir='ltr']",  # Common in Amazon India
        ".yohtmlc-order-id bdi[dir='ltr']",
        "[data-component='orderId']",
        "[data-component='briefOrderInfo'] div.a-column",
        ".order-date-invoice-item bdi[dir='ltr']",
        "bdi[dir='ltr']",
        "span[dir='ltr']"
    ]
    
    FIELD_ORDER_GRAND_TOTAL_SELECTOR = [
        "div.yohtmlc-order-total span.value",  # Updated for India
        ".order-total .value",
        "div.order-header div.a-column.a-span2",
        "div.order-header div.a-col-left .a-span9",
        ".a-span.a-size-base.a-color-secondary"  # Price spans
    ]
    
    FIELD_ORDER_PLACED_DATE_SELECTOR = [
        "[data-component='orderDate']",
        "span.order-date-invoice-item",
        "[data-component='briefOrderInfo'] div.a-column",
        "div.a-span3",
        "div.a-span12",
        ".order-placed-date"
    ]
    
    FIELD_ORDER_PAYMENT_METHOD_SELECTOR = "img.pmts-payment-credit-card-instrument-logo"
    FIELD_ORDER_PAYMENT_METHOD_LAST_4_SELECTOR = "span:has(img.pmts-payment-credit-card-instrument-logo):last-child"
    FIELD_ORDER_SUBTOTALS_TAG_ITERATOR_SELECTOR = [
        "[data-component='orderSubtotals'] div.a-row",
        "div#od-subtotals div.a-row"
    ]
    FIELD_ORDER_SUBTOTALS_TAG_POPOVER_PRELOAD_SELECTOR = ".a-popover-preload"
    FIELD_ORDER_SUBTOTALS_INNER_TAG_SELECTOR = "div.a-span-last"
    FIELD_ORDER_ADDRESS_SELECTOR = [
        "div.displayAddressDiv",
        "[data-component='shippingAddress']"
    ]
    FIELD_ORDER_ADDRESS_FALLBACK_1_SELECTOR = "div.recipient span.a-declarative"
    FIELD_ORDER_ADDRESS_FALLBACK_2_SELECTOR = "script[id^='shipToData']"
    FIELD_ORDER_GIFT_CARD_INSTANCE_SELECTOR = ".gift-card-instance"

    #####################################
    # Updated Shipment field selectors
    #####################################

    FIELD_SHIPMENT_TRACKING_LINK_SELECTOR = [
        "span.track-package-button a",
        "a[href*='ship-track?itemId=']"
    ]
    FIELD_SHIPMENT_DELIVERY_STATUS_SELECTOR = [
        "span.delivery-box__primary-text",  # Updated for India
        "div.js-shipment-info-container div.a-row",
        ".yohtmlc-shipment-status-primaryText",
        ".od-status-message"
    ]

    #####################################
    # Recipient field selectors (same as original)
    #####################################

    FIELD_RECIPIENT_NAME_SELECTOR = [
        "li.displayAddressFullName",
        "div:nth-child(1)",
        "li:nth-child(1)"
    ]
    FIELD_RECIPIENT_ADDRESS1_SELECTOR = "li.displayAddressAddressLine1"
    FIELD_RECIPIENT_ADDRESS2_SELECTOR = "li.displayAddressAddressLine2"
    FIELD_RECIPIENT_ADDRESS_CITY_STATE_POSTAL_SELECTOR = "li.displayAddressCityStateOrRegionPostalCode"
    FIELD_RECIPIENT_ADDRESS_COUNTRY_SELECTOR = "li.displayAddressCountryName"
    FIELD_RECIPIENT_ADDRESS_FALLBACK_SELECTOR = [
        "div:nth-child(2)",
        "li:nth-child(2)"
    ]

    #####################################
    # Seller field selectors (same as original)
    #####################################

    FIELD_SELLER_NAME_SELECTOR = ["a", "span"]
    FIELD_SELLER_LINK_SELECTOR = "a"

    #####################################
    # Transaction field selectors (same as original)
    #####################################

    TRANSACTION_HISTORY_FORM_SELECTOR = "form:has(input[name='ppw-widgetState'])"
    TRANSACTION_HISTORY_CONTAINER_SELECTOR = ".pmts-portal-component"
    TRANSACTION_DATE_CONTAINERS_SELECTOR = "div.apx-transaction-date-container"
    TRANSACTIONS_CONTAINER_SELECTOR = "div"
    TRANSACTIONS_SELECTOR = "div.apx-transactions-line-item-component-container:has(*)"

    TRANSACTIONS_NEXT_PAGE_INPUT_SELECTOR = [
        "input[type='submit'][name^='ppw-widgetEvent:DefaultNextPageNavigationEvent']"]
    TRANSACTIONS_NEXT_PAGE_INPUT_STATE_SELECTOR = "input[name='ppw-widgetState']"
    TRANSACTIONS_NEXT_PAGE_INPUT_IE_SELECTOR = "input[name='ie']"

    FIELD_TRANSACTION_COMPLETED_DATE_SELECTOR = "span"
    FIELD_TRANSACTION_PAYMENT_METHOD_SELECTOR = [
        "div.apx-transactions-line-item-component-container > div:nth-child(1) span.a-size-base"]
    FIELD_TRANSACTION_GRAND_TOTAL_SELECTOR = [
        "div.apx-transactions-line-item-component-container > div:nth-child(1) span.a-size-base-plus"]
    FIELD_TRANSACTION_ORDER_NUMBER_SELECTOR = [
        "div.apx-transactions-line-item-component-container div .a-span12"]
    FIELD_TRANSACTION_ORDER_LINK_SELECTOR = [
        "div.apx-transactions-line-item-component-container a.a-link-normal"]
    FIELD_TRANSACTION_SELLER_NAME_SELECTOR = [
        "div.apx-transactions-line-item-component-container :has(a.a-link-normal) + div"]