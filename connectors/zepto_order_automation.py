import asyncio
import time
import json
import os
import logging
import re
from playwright.async_api import async_playwright
from bs4 import BeautifulSoup
from zepto_simple_login_async import ZeptoLoginAsync

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler('zepto_playwright.log', encoding='utf-8'),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger(__name__)


class ZeptoScraper(ZeptoLoginAsync):
    def __init__(self, phone_number, headless=False, output_dir='output'):
        # Initialize parent class (login functionality)
        super().__init__(phone_number, headless)
        
        # Additional scraper-specific attributes
        self.output_dir = output_dir
        self.session_file = "zepto_playwright_session.json"
        
        # Create output directory
        if not os.path.exists(output_dir):
            os.makedirs(output_dir)

    # Class-level regexes and selectors for DOM-based extraction and parsing
    PRICE_REGEX = re.compile(r"₹\s?[\d,]+(?:\.\d+)?")
    BARE_NUM_REGEX = re.compile(r"^[\d,]+(?:\.\d+)?$")

    # Common selectors to try for product cards, name and price inside cards
    CARD_SELECTORS = [
        "[data-testid='product-card']",
        ".product-card",
        ".search-item",
        "div[data-testid*='product']",
        ".grid-card"
    ]

    NAME_SELECTORS = [
        "[data-testid='product-name']",
        ".product-title",
        "h3",
        "h2",
        ".title"
    ]

    PRICE_SELECTORS = [
        "[data-testid='product-price']",
        ".price",
        ".mrp",
        ".product-price",
        ".amount"
    ]

    async def validate_session_and_login(self):
        """Validate if session is active and perform login if needed"""
        logger.info("Validating login session...")
        
        try:
            # Check if user is logged in
            if await self.is_logged_in():
                logger.info("Session is valid - user is logged in")
                return True
            else:
                logger.warning("Session expired or not logged in - attempting login")
                
                # Attempt login
                login_success = await self.perform_login()
                
                if login_success:
                    logger.info("Login successful - session restored")
                    # Handle any popups after login
                    await self.handle_popups()
                    return True
                else:
                    logger.error("Login failed - cannot proceed")
                    return False
                    
        except Exception as e:
            logger.error(f"Session validation failed: {e}")
            return False
    
    async def setup_browser(self):
        """Setup browser using parent class functionality"""
        logger.info("Setting up browser with inherited functionality")
        
        # Use parent class browser setup
        if await self.start_browser():
            # Navigate to Zepto URL with longer timeout
            logger.info(f"Navigating to Zepto: {self.base_url}")
            await self.page.goto(self.base_url, wait_until='domcontentloaded', timeout=30000)
            
            # Wait for network to be idle with longer timeout (Firefox may need more time)
            try:
                await self.page.wait_for_load_state('networkidle', timeout=15000)
            except Exception as e:
                logger.warning(f"Network idle timeout (this is normal for Firefox): {e}")
            
            # Additional wait for dynamic content
            await self.page.wait_for_timeout(3000)
            
            # Validate login session
            if not await self.validate_session_and_login():
                logger.error("Login validation failed - cannot proceed")
                return None
            
            # Additional wait after login validation
            await self.page.wait_for_timeout(2000)
            
            # Take debug screenshot if in headless mode
            if self.headless:
                try:
                    await self.page.screenshot(path=os.path.join(self.output_dir, 'debug_initial_load.png'), full_page=True)
                    logger.info("Saved initial page screenshot for debugging")
                except Exception as e:
                    logger.debug(f"Failed to save debug screenshot: {e}")
            
            logger.info("Browser setup completed successfully")
            return self.page
        else:
            logger.error("Browser setup failed")
            return None
        

    async def select_current_location(self):
        """
        Select current location for delivery on Zepto website.
        
        This method handles the location selection workflow:
        1. Clicks "Select Location" button if present
        2. Clicks "Use My Current Location" in the modal
        3. Handles location permission "Enable" button
        4. Waits for location detection and modal closure
        
        Returns:
            bool: True if location selection successful, False otherwise
        """
        logger.info("Starting location selection process")
        
        try:
            await self.page.wait_for_timeout(2000)
            
            # Check current page content for debugging
            page_text = await self.page.evaluate("() => document.body.innerText")
            logger.info(f"Current page content preview: {page_text[:200]}...")
            
            # Try to click "Select Location" button
            location_button_selectors = [
                "button[aria-label='Select Location']",
                "button[aria-haspopup='dialog']",
                "button:has-text('Select Location')",
                ".WCHS8[data-testid='user-address']",
                "text=Select Location"
            ]
            
            location_button_clicked = await self._click_element(location_button_selectors, "Select Location button")
            if location_button_clicked:
                await self.page.wait_for_timeout(2000)
            
            # Click "Use My Current Location"
            current_location_selectors = [
                "text=Use My Current Location",
                "span:has-text('Use My Current Location')",
                "div:has-text('Use My Current Location')",
                "[data-testid*='current-location']"
            ]
            
            current_location_clicked = await self._click_element(current_location_selectors, "Use Current Location")
            if not current_location_clicked:
                logger.warning("Could not find 'Use My Current Location' option")
                return False
                
            await self.page.wait_for_timeout(1500)
            
            # Handle location permission "Enable" button
            enable_selectors = [
                "button:has-text('Enable')",
                "button:has-text('Allow')",
                "button:has-text('Grant Permission')",
                "text=Enable",
                "[data-testid*='enable']"
            ]
            
            enable_clicked = await self._click_element(enable_selectors, "Enable location")
            if enable_clicked:
                await self.page.wait_for_timeout(2000)
            else:
                logger.info("No enable button found - location may already be enabled")
            
            # Wait for location processing - longer timeout
            logger.info("Waiting for location detection to complete")
            await self.page.wait_for_timeout(3000)
            
            # Force close modal by looking for close/dismiss buttons
            modal_close_selectors = [
                "button[aria-label='Close']",
                "button:has-text('✕')",
                "button:has-text('×')",
                "[data-testid*='close']",
                "[data-testid*='dismiss']"
            ]
            
            for selector in modal_close_selectors:
                try:
                    close_btn = await self.page.wait_for_selector(selector, timeout=2000)
                    if close_btn and await close_btn.is_visible():
                        # Check if it's within a modal
                        is_in_modal = await close_btn.evaluate("""
                            (el) => {
                                let parent = el.parentElement;
                                while (parent) {
                                    const text = parent.innerText || '';
                                    if (text.includes('location') || text.includes('Location')) {
                                        return true;
                                    }
                                    parent = parent.parentElement;
                                }
                                return false;
                            }
                        """)
                        
                        if is_in_modal:
                            await close_btn.click()
                            logger.info(f"Closed location modal using: {selector}")
                            await self.page.wait_for_timeout(1000)
                            break
                except:
                    continue
            
            # Press Escape key as fallback to close modal
            try:
                await self.page.keyboard.press('Escape')
                await self.page.wait_for_timeout(500)
                logger.info("Pressed Escape to close any remaining modal")
            except:
                pass
            
            # Verify location modal is closed
            await self._verify_modal_closed()
            
            logger.info("Location selection completed successfully")
            return True
                
        except Exception as e:
            logger.error(f"Failed to select location: {e}")
            return False
        
    async def select_delivery_address(self):
        """
        Select delivery address from saved addresses if address selection is required.
        
        This method:
        1. Checks if address selection is needed on the page
        2. Attempts to select the first available saved address
        3. Falls back to clicking address cards if buttons not found
        
        Returns:
            bool: True if address selected or not required, False if selection failed
        """
        logger.info("Starting delivery address selection")
        
        try:
            await self.page.wait_for_timeout(1000)
            
            # Check if address selection is required
            page_text = await self.page.evaluate("() => document.body.innerText.toLowerCase()")
            address_keywords = ['select address', 'delivery address', 'choose address', 'saved address']
            
            if not any(keyword in page_text for keyword in address_keywords):
                logger.info("Address already selected or not required")
                return True
                
            logger.info("Address selection required - looking for saved addresses")
            
            # Primary address selection selectors
            address_selectors = [
                "[data-testid='address-item']",
                "button:has-text('Deliver here')",
                "button:has-text('Select')",
                "[data-testid*='address-select']"
            ]
            
            # Try to select address using primary selectors
            if await self._select_address_with_selectors(address_selectors):
                logger.info("Address selected successfully")
                return True
            
            # Fallback: Try clicking address cards directly
        except Exception as e:
            logger.error(f"Failed to select delivery address: {e}")
            return False
    
    async def _click_element(self, selectors, element_name):
        """
        Helper method to click an element using multiple selectors.
        
        Args:
            selectors (list): List of CSS selectors to try
            element_name (str): Name of element for logging
            
        Returns:
            bool: True if element was clicked, False otherwise
        """
        for selector in selectors:
            try:
                element = await self.page.wait_for_selector(selector, timeout=2000)
                if element and await element.is_visible():
                    await element.scroll_into_view_if_needed()
                    await element.click()
                    logger.info(f"Clicked {element_name} using selector: {selector}")
                    return True
            except Exception as e:
                logger.debug(f"Selector {selector} failed for {element_name}: {e}")
                continue
        
        logger.info(f"No {element_name} found with provided selectors")
        return False
    
    async def _verify_modal_closed(self):
        """
        Helper method to verify location modal is closed.
        """
        try:
            modal = await self.page.wait_for_selector("[data-testid='address-modal']", timeout=1000)
            if modal and await modal.is_visible():
                logger.warning("Location modal still open - may need manual intervention")
            else:
                logger.info("Location modal closed successfully")
        except:
            logger.info("Location modal not found - selection completed")
    
    async def _select_address_with_selectors(self, selectors):
        """
        Helper method to select address using provided selectors.
        
        Args:
            selectors (list): List of CSS selectors to try
            
        Returns:
            bool: True if address was selected, False otherwise
        """
        for selector in selectors:
            try:
                elements = await self.page.query_selector_all(selector)
                for element in elements:
                    if await element.is_visible():
                        await element.scroll_into_view_if_needed()
                        await element.click()
                        logger.info(f"Selected address using selector: {selector}")
                        await self.page.wait_for_timeout(1000)
                        return True
            except Exception as e:
                logger.debug(f"Address selector {selector} failed: {e}")
                continue
        
        return False
    
    async def search_products(self, search_term):
        """Search for products using the given term (Playwright version)"""
        logger.info(f"Searching for products: {search_term}")
        
        # Check if still logged in before searching
        if not await self.is_logged_in():
            logger.error("Not logged in - cannot search products")
            return False
        
        try:
            # Handle any popups that might be blocking the search
            # await self.handle_popups()
            
            # Wait for page to be fully interactive
            await self.page.wait_for_load_state('networkidle', timeout=2000)
            await self.page.wait_for_timeout(2000)
            
            # Click search button/icon
            search_button_selectors = [
                "a[data-testid='search-bar-icon']",
                "button:has-text('Search')",
                "[data-testid*='search']",
                "input[placeholder*='Search']",  # Sometimes input is directly visible
                "[aria-label*='Search' i]"
            ]
            search_button = None
            for selector in search_button_selectors:
                try:
                    element = await self.page.wait_for_selector(selector, timeout=2000, state='visible')
                    if element and await element.is_visible():
                        search_button = element
                        logger.info(f"Found search element using: {selector}")
                        break
                except:
                    continue
            
            if not search_button:
                logger.error("Search button not found")
                # Take debug screenshot
                if self.headless:
                    await self.page.screenshot(path=os.path.join(self.output_dir, 'debug_search_not_found.png'))
                return False
            
            # Click if it's a button, otherwise it's already the input
            if await search_button.get_attribute('role') != 'textbox':
                await search_button.click()
                await self.page.wait_for_timeout(1500)
            
            # Enter search term
            search_input_selectors = [
                "input[placeholder*='Search for']",
                "input[type='search']",
                "input[role='searchbox']",
                "input[aria-label*='Search' i]"
            ]
            
            search_input = None
            for selector in search_input_selectors:
                try:
                    search_input = await self.page.wait_for_selector(selector, timeout=2000, state='visible')
                    if search_input:
                        break
                except:
                    continue
            
            if not search_input:
                logger.error("Search input not found")
                return False
            
            await search_input.fill("")
            await search_input.type(search_term, delay=50)
            await search_input.press('Enter')
            
            logger.info("Waiting for search results to load")
            # Wait for network activity to settle
            await self.page.wait_for_load_state('networkidle', timeout=2000)
            await self.page.wait_for_timeout(1000)
            
            # Take screenshot of search results
            if self.headless:
                await self.page.screenshot(path=os.path.join(self.output_dir, 'debug_search_results.png'))
                logger.info("Saved search results screenshot")
            
            return True
            
        except Exception as e:
            logger.error(f"Search failed: {e}")
            if self.headless:
                try:
                    await self.page.screenshot(path=os.path.join(self.output_dir, 'debug_search_error.png'))
                except:
                    pass
            return False
        

    async def search_and_extract_products(self, product_name, max_products=5):
        """Search for products and extract product information from results.
        
        This method combines searching and extraction for convenience.
        
        Args:
            product_name: Product name to search for
            max_products: Maximum number of products to extract (default 5)
            
        Returns:
            list: List of product dicts with name, price, quantity, etc.
        """
        logger.info(f"Searching and extracting up to {max_products} products for: {product_name}")

        # First search for the product
        search_success = await self.search_products(product_name)
        if not search_success:
            logger.error(f"Search failed for: {product_name}")
            return []

        # First attempt: DOM-based extraction (more reliable)
        try:
            dom_products = await self.extract_products_dom(max_products)
            if dom_products:
                logger.info(f"DOM-based extraction found {len(dom_products)} products")
                return dom_products
        except Exception as e:
            logger.debug(f"DOM extraction failed: {e}")

        # Fallback: original text-based parsing
        try:
            # Wait for search results to fully load
            await self.page.wait_for_timeout(3000)

            # Get page text content
            page_text = await self.page.evaluate("() => document.body.innerText")

            if "Showing results for" not in page_text and "results" not in page_text.lower():
                logger.warning("No clear search results indication found")

            # Parse products from text
            lines = [line.strip() for line in page_text.split('\n') if line.strip()]
            products = []

            logger.info("Parsing product information from page text...")

            # Look for both ADD buttons and quantity controls (+ buttons)
            action_buttons = ["ADD", "+", "-"]  # Include quantity control buttons

            for i, line in enumerate(lines):
                if len(products) >= max_products:
                    break

                if line in action_buttons:
                    try:
                        product_info = self._extract_single_product(lines, i, button_type=line)
                        if product_info:
                            products.append(product_info)
                            logger.info(f"Extracted product {len(products)}: {product_info['name']} - {product_info['price']} [{line} button]")
                    except Exception as e:
                        logger.debug(f"Failed to extract product at position {i}: {e}")

            logger.info(f"Successfully extracted {len(products)} products (text fallback)")
            return products

        except Exception as e:
            logger.error(f"Product extraction failed: {e}")
            return []

    async def extract_products_dom(self, max_products=5):
        """DOM-first extraction: finds product anchors and extracts name/price/quantity."""
        logger.info("Running DOM-first extraction")
        products = []

        try:
            # Wait for products to be loaded
            await self.page.wait_for_timeout(2000)
            
            # Try multiple selectors for product containers
            product_selectors = [
                "a[href*='/pn/']",
                "a[href*='/product/']",
                "div[data-testid='product-card']",
                "article",
                ".product-card"
            ]
            
            anchors = []
            for selector in product_selectors:
                try:
                    elements = await self.page.query_selector_all(selector)
                    if elements and len(elements) > 0:
                        anchors = elements
                        logger.info(f"Found {len(anchors)} elements using selector: {selector}")
                        break
                except Exception as e:
                    logger.debug(f"Selector {selector} failed: {e}")
                    continue
            
            if not anchors:
                logger.warning("No product anchors found with any selector")
                # Save page HTML for debugging
                if self.headless:
                    html_content = await self.page.content()
                    html_path = os.path.join(self.output_dir, 'debug_products_page.html')
                    with open(html_path, 'w', encoding='utf-8') as f:
                        f.write(html_content)
                    logger.info(f"Saved page HTML to: {html_path}")
                return []
                
        except Exception as e:
            logger.debug(f"Product anchor selector failed: {e}")
            return []

        for anchor in anchors[:max_products * 2]:  # get extras in case some fail
            if len(products) >= max_products:
                break

            try:
                inner_text = (await anchor.inner_text()).strip()
                
                # Skip non-product anchors
                if '₹' not in inner_text and 'ADD' not in inner_text:
                    continue

                # Extract using data-slot-id selectors (most reliable)
                name = await self._extract_text(anchor, "[data-slot-id='ProductName']")
                price_text = await self._extract_text(anchor, "[data-slot-id='EdlpPrice']")
                quantity = await self._extract_text(anchor, "[data-slot-id='PackSize']")
                
                # Parse price with regex
                price = None
                if price_text:
                    match = self.PRICE_REGEX.search(price_text)
                    if match:
                        price = match.group(0).replace(' ', '')

                # Fallback for name if not found
                if not name:
                    parts = [p.strip() for p in inner_text.split('\n') if p.strip()]
                    name = next((p for p in parts if len(p) > 10 and not p.startswith('₹')), None)

                if name:
                    products.append({
                        'name': name,
                        'price': price or 'Price not found',
                        'quantity': quantity or 'N/A',
                        'button_type': 'DOM',
                        'href': await anchor.get_attribute('href')
                    })

            except Exception as e:
                logger.debug(f"Failed to parse product anchor: {e}")
                continue

        logger.info(f"DOM extraction found {len(products)} products")
        return products

    async def _extract_text(self, element, selector):
        """Helper to safely extract text from a child element."""
        try:
            child = await element.query_selector(selector)
            if child:
                return (await child.inner_text()).strip()
        except:
            pass
        return None
    
    def _extract_single_product(self, lines, start_idx, button_type="ADD"):
        """Extract a single product from text lines starting at button (helper method)"""
        try:
            # use compiled class-level regexes to avoid re-compiling on each call
            price_regex = self.PRICE_REGEX
            bare_num_regex = self.BARE_NUM_REGEX

            product_name = None
            price = None
            search_range = range(max(0, start_idx - 6), min(len(lines), start_idx + 18))
            excluded_prefixes = ('₹', '(', 'SAVE', 'Premium', 'ADD', '+', '-')

            for i in search_range:
                text = lines[i].strip()

                # price detection (first match wins)
                if not price:
                    m = price_regex.search(text)
                    if m:
                        price = m.group(0).replace(' ', '')
                    elif text == '₹' and i + 1 < len(lines):
                        nxt = lines[i + 1].strip()
                        if bare_num_regex.match(nxt.replace('₹', '')):
                            price = f"₹{nxt}"
                    elif bare_num_regex.match(text.replace('₹', '')):
                        for ck in range(max(0, i - 2), min(len(lines), i + 3)):
                            if '₹' in lines[ck]:
                                price = f"₹{text}"
                                break

                # product name heuristics
                if product_name is None:
                    cand = text
                    if (len(cand) > 10 and re.search(r'[A-Za-z]', cand) and
                        not cand.startswith(excluded_prefixes) and
                        not bare_num_regex.match(cand.replace('(', '').replace(')', '').replace(',', '')) and
                        'pack' not in cand.lower()[:10] and
                        'offer' not in cand.lower()[:10] and
                        cand not in ["ADD", "+", "-", "₹"]):

                        product_name = cand

                if product_name and price:
                    break

            if product_name:
                return {
                    'name': product_name,
                    'price': price or 'Price not found',
                    'button_type': button_type
                }

            return None

        except Exception as e:
            logger.debug(f"Error extracting single product: {e}")
            return None
    

    async def add_product_to_cart(self, product_name=None, quantity=1, product_index=None):
        """Add a product to cart with specified quantity.
        
        Args:
            product_name: Product name to search for (if product_index not provided)
            quantity: Quantity to add (default 1)
            product_index: Direct index of product in search results (0-based)
        """
        logger.info(f"Adding to cart: {product_name or f'product at index {product_index}'} (quantity: {quantity})")
        
        # Check if still logged in before adding to cart
        if not await self.is_logged_in():
            logger.error("Not logged in - cannot add to cart")
            return False
        
        try:
            await self.page.wait_for_timeout(2000)
            if isinstance(product_index, int):
                logger.info(f"Using product index: {product_index}")    
                product_index = product_index -1
            # Get all product anchors
            anchors = await self.page.query_selector_all("a[href*='/pn/']")
            logger.info(f"Found {len(anchors)} product anchors")
            
            # If product_index provided, use it directly
            if product_index is not None:
                if product_index < 0 or product_index >= len(anchors):
                    logger.error(f"Invalid product index: {product_index} (total: {len(anchors)})")
                    return False
                
                target_anchors = [anchors[product_index]]
                logger.info(f"Using product at index {product_index}")
            else:
                # Search by name
                if not product_name:
                    logger.error("Either product_name or product_index must be provided")
                    return False
                
                keywords = [w.lower() for w in product_name.split() if len(w) > 2]
                target_anchors = anchors
            
            for anchor in target_anchors:
                try:
                    text = (await anchor.inner_text()).lower()
                    
                    # Skip name matching if using index
                    if product_index is None:
                        # Check if product name matches
                        if not all(kw in text for kw in keywords):
                            continue
                    
                    logger.info(f"Found matching product")
                    
                    # Try to find ADD button first
                    add_btn = await anchor.query_selector("button:has-text('ADD')")
                    
                    if add_btn:
                        # Product not in cart yet - click ADD
                        await add_btn.scroll_into_view_if_needed()
                        await self.page.wait_for_timeout(500)
                        await add_btn.click()
                        await self.page.wait_for_timeout(1500)
                        logger.info("Clicked ADD button")
                        
                        # If quantity > 1, need to increase
                        if quantity > 1:
                            for _ in range(quantity - 1):
                                plus_btn = await anchor.query_selector("button[aria-label='Increase quantity']")
                                if plus_btn:
                                    await plus_btn.click()
                                    await self.page.wait_for_timeout(500)
                    else:
                        # Product already in cart - find increase button
                        logger.info("Product already in cart, updating quantity")
                        plus_btn = await anchor.query_selector("button[aria-label='Increase quantity']")
                        
                        if plus_btn:
                            for _ in range(quantity):
                                await plus_btn.click()
                                await self.page.wait_for_timeout(500)
                        else:
                            logger.warning("Neither ADD nor increase button found")
                            continue
                    
                    logger.info(f"Successfully added '{product_name}' (quantity: {quantity})")
                    await self.page.wait_for_timeout(1000)
                    return True
                    
                except Exception as e:
                    logger.debug(f"Error processing anchor: {e}")
                    continue
            
            logger.warning(f"Product not found: {product_name}")
            return False
            
        except Exception as e:
            logger.error(f"Failed to add to cart: {e}")
            return False

    async def goto_cart(self):
        """Navigate to cart page by clicking the cart button."""
        logger.info("Navigating to cart")
        
        try:
            # Wait for page to be ready
            await self.page.wait_for_load_state('domcontentloaded')
            await self.page.wait_for_timeout(2000)
            
            # Find and click cart button
            cart_selectors = [
                "button[data-testid='cart-btn']",
                "button[aria-label='Cart']",
                "a:has-text('Cart')",
                "button:has-text('Cart')",
                "[data-testid*='cart']",
                "a[href*='/cart']",
                "svg[aria-label='cart']"
            ]
            
            for selector in cart_selectors:
                try:
                    cart_btn = await self.page.wait_for_selector(selector, timeout=3000, state='visible')
                    if cart_btn and await cart_btn.is_visible():
                        await cart_btn.scroll_into_view_if_needed()
                        await self.page.wait_for_timeout(500)
                        await cart_btn.click()
                        await self.page.wait_for_load_state('networkidle', timeout=2000)
                        await self.page.wait_for_timeout(2000)
                        logger.info(f"Navigated to cart using: {selector}")
                        
                        # Take screenshot in headless mode
                        if self.headless:
                            await self.page.screenshot(path=os.path.join(self.output_dir, 'debug_cart_page.png'))
                        
                        return True
                except Exception as e:
                    logger.debug(f"Cart selector {selector} failed: {e}")
                    continue
            
            logger.warning("Cart button not found")
            # Take debug screenshot
            if self.headless:
                await self.page.screenshot(path=os.path.join(self.output_dir, 'debug_cart_not_found.png'))
            return False
            
        except Exception as e:
            logger.error(f"Failed to navigate to cart: {e}")
            return False

    async def goto_account(self):
        """Navigate to account page by clicking the profile button."""
        logger.info("Navigating to account/profile page")
        
        try:
            # Wait for page to be ready
            await self.page.wait_for_load_state('domcontentloaded')
            await self.page.wait_for_timeout(2000)
            
            # Find and click profile button
            profile_selectors = [
                "a[aria-label='profile']",
                "a[href='/account']",
                "[data-testid='my-account']",
                "a:has([data-testid='my-account'])",
                "span:has-text('profile')",
                ".qO5yx a[href='/account']"
            ]
            
            for selector in profile_selectors:
                try:
                    profile_btn = await self.page.wait_for_selector(selector, timeout=3000, state='visible')
                    if profile_btn and await profile_btn.is_visible():
                        await profile_btn.scroll_into_view_if_needed()
                        await self.page.wait_for_timeout(500)
                        await profile_btn.click()
                        await self.page.wait_for_load_state('networkidle', timeout=2000)
                        await self.page.wait_for_timeout(2000)
                        logger.info(f"Navigated to account using: {selector}")
                        
                        # Take screenshot in headless mode
                        if self.headless:
                            await self.page.screenshot(path=os.path.join(self.output_dir, 'debug_account_page.png'))
                        
                        return True
                except Exception as e:
                    logger.debug(f"Profile selector {selector} failed: {e}")
                    continue
            
            logger.warning("Profile button not found")
            # Take debug screenshot
            if self.headless:
                await self.page.screenshot(path=os.path.join(self.output_dir, 'debug_profile_not_found.png'))
            return False
            
        except Exception as e:
            logger.error(f"Failed to navigate to account: {e}")
            return False

    async def get_order_history(self, max_orders=3):
        """Get order history from account page.
        
        Args:
            max_orders (int): Maximum number of orders to extract (default 3)
            
        Returns:
            list: List of order dictionaries with status, date, amount, etc.
        """
        logger.info(f"Getting order history (max {max_orders} orders)")
        
        try:
            # First navigate to account page
            if not await self.goto_account():
                logger.error("Failed to navigate to account page")
                return []
            
            await self.page.wait_for_timeout(3000)
            
            # Find order containers - each order is in an <a> tag with href="/order/"
            order_links = await self.page.query_selector_all('a[href*="/order/"]')
            
            if not order_links:
                logger.info("No orders found on account page")
                return []
            
            orders = []
            
            for i, order_link in enumerate(order_links[:max_orders]):
                try:
                    # Extract order status
                    status_element = await order_link.query_selector('p.mr-1\\.5.text-heading6')
                    status = "Unknown"
                    if status_element:
                        status_text = await status_element.text_content()
                        if status_text:
                            status = status_text.strip()
                    
                    # Extract order date/time
                    date_element = await order_link.query_selector('p.mt-1.text-body2')
                    date = "Unknown"
                    if date_element:
                        date_text = await date_element.text_content()
                        if date_text:
                            date = date_text.strip().replace('Placed at ', '')
                    
                    # Extract order amount
                    amount_element = await order_link.query_selector('p.mr-1\\.5.text-heading5')
                    amount = "Unknown"
                    if amount_element:
                        amount_text = await amount_element.text_content()
                        if amount_text:
                            amount = amount_text.strip()
                    
                    # Extract order ID from href
                    href = await order_link.get_attribute('href')
                    order_id = "Unknown"
                    if href:
                        # Extract order ID from URL like "/order/019adf78-27d9-7572-a04a-efc2b01a99ae"
                        parts = href.split('/')
                        if len(parts) >= 3:
                            order_id = parts[2].split('?')[0]  # Remove query parameters
                    
                    # Count product images to get item count
                    product_images = await order_link.query_selector_all('img[alt=""][width="46"][height="46"]')
                    item_count = len(product_images)
                    
                    order_info = {
                        'order_number': i + 1,
                        'order_id': order_id,
                        'status': status,
                        'date': date,
                        'amount': amount,
                        'item_count': item_count,
                        'url': href or 'N/A'
                    }
                    
                    orders.append(order_info)
                    logger.info(f"Extracted order {i+1}: {status} - {amount} - {date}")
                    
                except Exception as e:
                    logger.debug(f"Failed to extract order {i+1}: {e}")
                    continue
            
            logger.info(f"Successfully extracted {len(orders)} orders")
            
            # Take screenshot of orders page
            if self.headless:
                await self.page.screenshot(path=os.path.join(self.output_dir, 'debug_orders_page.png'))
            
            return orders
            
        except Exception as e:
            logger.error(f"Failed to get order history: {e}")
            return []

    async def goto_order_details(self, order_index=0):
        """Navigate to specific order details page by clicking on order at given index.
        
        Args:
            order_index (int): Index of order to click (0-based, default 0 for first order)
            
        Returns:
            dict: Order details information or None if failed
        """
        logger.info(f"Navigating to order details for order index {order_index}")
        
        try:
            # First navigate to account page if not already there
            current_url = self.page.url
            if '/account' not in current_url:
                if not await self.goto_account():
                    logger.error("Failed to navigate to account page")
                    return None
            
            await self.page.wait_for_timeout(2000)
            
            # Find order links
            order_links = await self.page.query_selector_all('a[href*="/order/"]')
            
            if not order_links:
                logger.error("No orders found on account page")
                return None
            
            if order_index >= len(order_links):
                logger.error(f"Order index {order_index} out of range (found {len(order_links)} orders)")
                return None
            
            # Click on the specified order
            target_order = order_links[order_index]
            await target_order.scroll_into_view_if_needed()
            await target_order.click()
            
            # Wait for order details page to load with better error handling
            try:
                await self.page.wait_for_load_state('networkidle', timeout=10000)
            except Exception as e:
                logger.warning(f"Network idle timeout: {e}")
                # Continue anyway, page might still be usable
            
            # Additional wait and verify we're on order details page
            await self.page.wait_for_timeout(3000)
            
            # Verify we're on the correct page
            current_url = self.page.url
            if '/order/' not in current_url:
                logger.error(f"Navigation failed - not on order page: {current_url}")
                return None
            
            logger.info(f"Successfully navigated to order details for index {order_index}")
            
            # Extract order details from the details page
            order_details = await self._extract_order_details_from_page()
            
            # Take screenshot of order details page
            if self.headless:
                await self.page.screenshot(path=os.path.join(self.output_dir, f'order_details_{order_index}.png'))
                logger.info(f"Saved order details screenshot for index {order_index}")
            
            return order_details
            
        except Exception as e:
            logger.error(f"Failed to navigate to order details: {e}")
            return None

    async def _extract_order_details_from_page(self):
        """Extract order details using known HTML structure."""
        logger.info("Extracting order details from order page")
        
        try:
            # Wait for page to be stable and fully loaded
            await self.page.wait_for_load_state('domcontentloaded')
            await self.page.wait_for_timeout(3000)  # Give page time to stabilize
            
            order_details = {}
            
            # Extract order ID from URL
            try:
                current_url = self.page.url
                if '/order/' in current_url:
                    order_details['order_id'] = current_url.split('/order/')[1].split('?')[0]
            except Exception as e:
                logger.debug(f"Failed to extract order ID: {e}")
            
            # Extract ETA information from known structure
            try:
                eta_container = await self.page.query_selector('#eta-timer-content')
                if eta_container:
                    # Extract time from span.text-heading1
                    time_element = await eta_container.query_selector('span.text-heading1')
                    if time_element:
                        time_text = await time_element.text_content()
                        if time_text:
                            order_details['arriving_in'] = time_text.strip()
                    
                    # Extract messages from specific span classes
                    eta_label = await eta_container.query_selector('span.text-body1')
                    if eta_label:
                        order_details['eta_label'] = (await eta_label.text_content()).strip()
                    
                    status_msg = await eta_container.query_selector('span.text-heading4')
                    if status_msg:
                        order_details['order_status_message'] = (await status_msg.text_content()).strip()
                    
                    delay_msg = await eta_container.query_selector('span.text-body4')
                    if delay_msg:
                        order_details['delay_message'] = (await delay_msg.text_content()).strip()
            except Exception as e:
                logger.debug(f"ETA extraction failed: {e}")
            
            # Extract basic order info with simple selectors
            try:
                # Order status from h1/h2
                for selector in ['h1', 'h2']:
                    element = await self.page.query_selector(selector)
                    if element:
                        text = await element.text_content()
                        if text and any(word in text.lower() for word in ['delivered', 'cancelled', 'on the way', 'placed']):
                            order_details['status'] = text.strip()
                            break
                
                # Total amount from first price element
                price_elements = await self.page.query_selector_all('span:has-text("₹")')
                for element in price_elements:
                    amount_text = await element.text_content()
                    if amount_text and '₹' in amount_text:
                        price_match = self.PRICE_REGEX.search(amount_text)
                        if price_match:
                            order_details['total_amount'] = price_match.group(0)
                            break
                
                # Order date from page text
                page_text = await self.page.evaluate("() => document.body.innerText")
                import re
                date_pattern = r'(\d{1,2}\s+(Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec)\s+\d{4})'
                date_match = re.search(date_pattern, page_text)
                if date_match:
                    order_details['order_date'] = date_match.group(0)
                
            except Exception as e:
                logger.debug(f"Basic info extraction failed: {e}")
            
            logger.info(f"Extracted order details: {len(order_details)} fields")
            return order_details
            
        except Exception as e:
            logger.error(f"Failed to extract order details: {e}")
            return {}

    async def clear_cart(self):
        """Clear all items from cart."""
        logger.info("Clearing cart")
        try:
            # First navigate to cart
            if not await self.goto_cart():
                logger.error("Failed to navigate to cart")
                return False
            is_high_demand = await self.check_high_demand_flag()
            if is_high_demand:
                logger.warning("High demand - try again later")
                return "High demand - try again late"
            
            await self.page.wait_for_timeout(2000)
            
            # Find all remove/minus buttons
            remove_selectors = [
                "button[aria-label='Remove']",
                "button[data-testid*='minus-btn']",
                "button:has-text('Remove')"
            ]
            
            removed_count = 0
            
            # Keep removing until no more items
            while True:
                remove_btn = None
                
                for selector in remove_selectors:
                    try:
                        remove_btn = await self.page.wait_for_selector(selector, timeout=2000)
                        if remove_btn and await remove_btn.is_visible():
                            break
                    except:
                        continue
                
                if not remove_btn:
                    logger.info(f"Cart cleared - removed {removed_count} items")
                    break
                
                # Click remove button
                await remove_btn.scroll_into_view_if_needed()
                await remove_btn.click()
                await self.page.wait_for_timeout(1000)
                removed_count += 1
                
                logger.debug(f"Removed item {removed_count}")
            
            # After clearing cart, click back button to return to main page
            await self.page.wait_for_timeout(1500)
            
            back_selectors = [
                "button.cpG2SV",  # class from HTML
                "button:has(svg[viewBox='0 0 24 24'])",  # SVG back arrow
                "button[aria-label='Back']",
                "button[aria-label='Go back']"
            ]
            
            for selector in back_selectors:
                try:
                    back_btn = await self.page.wait_for_selector(selector, timeout=2000)
                    if back_btn and await back_btn.is_visible():
                        await back_btn.click()
                        await self.page.wait_for_timeout(2000)
                        logger.info("Returned to main page after clearing cart")
                        break
                except:
                    continue
            
            return True
            
        except Exception as e:
            logger.error(f"Failed to clear cart: {e}")
            return False

    async def get_cart_info(self):
        """Get detailed information about all products currently in cart."""
        logger.info("Getting cart information")
        
        try:
         
            cart_items = []
            
            # Find all product containers in cart (using class from HTML)
            product_containers = await self.page.query_selector_all("div.__6RuoF")
            
            if not product_containers:
                logger.info("Cart is empty")
                return {"items": [], "total_items": 0, "total_price": None}
            
            for container in product_containers:
                try:
                    # Extract product name
                    name = await self._extract_text(container, "p.ngKou")
                    
                    # Extract quantity/pack size
                    quantity_text = await self._extract_text(container, "p.__4SHbK")
                    
                    # Extract current quantity in cart
                    cart_qty = await self._extract_text(container, "p[data-testid*='cart-qty']")
                    
                    # Extract price
                    price_text = await self._extract_text(container, "p.cTJX6L")
                    price = None
                    if price_text:
                        match = self.PRICE_REGEX.search(price_text)
                        if match:
                            price = match.group(0).replace(' ', '')
                    
                    if name:
                        cart_items.append({
                            'name': name,
                            'pack_size': quantity_text or 'N/A',
                            'quantity': cart_qty or '1',
                            'price': price or 'Price not found'
                        })
                
                except Exception as e:
                    logger.debug(f"Failed to parse cart item: {e}")
                    continue
            
            # Try to get total price if available
            total_price = None
            try:
                total_elem = await self.page.query_selector("p:has-text('Total'), span:has-text('Total')")
                if total_elem:
                    total_text = await total_elem.evaluate("el => el.parentElement.innerText")
                    match = self.PRICE_REGEX.search(total_text)
                    if match:
                        total_price = match.group(0).replace(' ', '')
            except:
                pass
            
            result = {
                'items': cart_items,
                'total_items': len(cart_items),
                'total_price': total_price
            }
            
            logger.info(f"Cart contains {len(cart_items)} items")
            return result
            
        except Exception as e:
            logger.error(f"Failed to get cart info: {e}")
            return None
    
    async def check_high_demand_flag(self):
        """Check if 'High demand right now' notification is displayed.
        
        Returns:
            bool: True if high demand flag is present, False otherwise
        """
        try:
            # Check for high demand text
            element = await self.page.query_selector("text=High demand right now")
            if element and await element.is_visible():
                logger.warning("High demand flag detected")
                return True
            
            logger.info("No high demand flag - service available")
            return False
            
        except Exception as e:
            logger.debug(f"Error checking high demand flag: {e}")
            return False
        
    async def get_order_details(self, ensure_cart=False):
        """Compact order summary extractor.

        Returns a small dict with: item_total, handling_fee, delivery_fee, to_pay,
        products (list of dicts), total_items. Uses `get_cart_info()` for products.

        This version prefers the non-strikethrough value in each summary row
        (e.g. picks the visible price, not the crossed-out original price).
        """
        logger.info("Getting order details (compact)")
        try:
            if not ensure_cart:
                await self.goto_cart()

            await self.page.wait_for_timeout(500)

            # Reliable product list and (maybe) total from cart parser
            cart = await self.get_cart_info() or {'items': [], 'total_price': None, 'total_items': 0}

            # Locate bill summary container if present to avoid picking wrong rows
            bill = None
            try:
                bill = await self.page.query_selector("div:has-text('Bill summary')")
                if not bill:
                    bill = await self.page.query_selector("div:has-text('Bill Summary')")
            except Exception:
                bill = None

            # Find summary rows inside bill (or globally as fallback)
            if bill:
                rows = await bill.query_selector_all("div.flex.justify-between")
            else:
                rows = await self.page.query_selector_all("div.flex.justify-between")

            summary = {}
            for r in rows:
                try:
                    # label is usually the left button/span
                    left_btn = await r.query_selector("button")
                    if left_btn:
                        label = (await left_btn.inner_text()).strip()
                    else:
                        # fallback to first span or first line
                        spans = await r.query_selector_all("span")
                        if spans:
                            label = (await spans[0].inner_text()).strip()
                        else:
                            label = (await r.inner_text()).split('\n')[0].strip()

                    # right side values: prefer spans that are NOT strikethrough
                    right_spans = await r.query_selector_all("div span")
                    value = None
                    for s in right_spans:
                        try:
                            cls = (await s.get_attribute('class') or '').lower()
                            txt = (await s.inner_text()).strip()
                            if not txt:
                                continue
                            if 'strikethrough' not in cls:
                                # pick the first visible non-strikethrough value
                                value = txt
                        except Exception:
                            continue

                    # if none picked, fallback to last non-empty span text
                    if not value and right_spans:
                        for s in reversed(right_spans):
                            try:
                                txt = (await s.inner_text()).strip()
                                if txt:
                                    value = txt
                                    break
                            except:
                                continue

                    if value:
                        summary[label.lower()] = value
                except Exception:
                    continue

            def _find_label(key):
                for k, v in summary.items():
                    if key in k:
                        return v
                return None

            # Prefer cart total, else try to use summary's item total
            item_total = cart.get('total_price') or _find_label('item total')
            handling_fee = _find_label('handling fee')
            delivery_fee = _find_label('delivery fee') or _find_label('delivery')
            to_pay = _find_label('to pay') or _find_label('pay') or item_total

            # Attempt to take a screenshot of the order summary for debugging/audit
            try:
                if not os.path.exists(self.output_dir):
                    os.makedirs(self.output_dir, exist_ok=True)
                filename = f"order_details_{int(time.time())}.png"
                filepath = os.path.join(self.output_dir, filename)
                await self.page.screenshot(path=filepath, full_page=True)
                logger.info(f"Saved order details screenshot: {filepath}")
            except Exception as e:
                logger.debug(f"Failed to save order details screenshot: {e}")

            return {
                'item_total': item_total,
                'handling_fee': handling_fee,
                'delivery_fee': delivery_fee,
                'to_pay': to_pay,
                'products': cart.get('items', []),
                'total_items': cart.get('total_items', 0)
            }
        except Exception as e:
            logger.debug(f"get_order_details error: {e}")
            return None

    async def go_to_payment(self, ensure_cart=True):
        """Click the 'Click to Pay' / proceed-to-pay button and wait for payment screen.

        Args:
            ensure_cart (bool): If True (default) navigate to the cart page first.

        Returns:
            dict: { 'status': 'payment_page'|'not_found'|'error', 'url': current_url }
        """
        logger.info("Attempting to go to payment")
        
        # Check if still logged in before proceeding to payment
        if not await self.is_logged_in():
            logger.error("Not logged in - cannot proceed to payment")
            return {'status': 'error', 'error': 'Not logged in'}
        
        try:
            if not ensure_cart:
                await self.goto_cart()
              

            await self.page.wait_for_timeout(700)

            # Common selectors for the pay/proceed button
            pay_selectors = [
                "button:has-text('Click to Pay')",
                "button:has-text('Proceed to pay')",
                "button.bg-skin-primary",
                "div:has(button:has-text('Click to Pay')) button",
            ]

            clicked = False
            for sel in pay_selectors:
                try:
                    btn = await self.page.wait_for_selector(sel, timeout=1500)
                    if btn and await btn.is_visible():
                        await btn.scroll_into_view_if_needed()
                        await btn.click()
                        clicked = True
                        await self.page.wait_for_timeout(1500)
                        logger.info(f"Clicked pay button using selector: {sel}")
                        break
                except Exception:
                    continue

            if not clicked:
                logger.warning("Pay button not found")
                return {'status': 'not_found', 'url': self.page.url}

            # Wait a bit and check for payment method indicators
            await self.page.wait_for_timeout(1000)
            indicators = [
                "text=UPI",
                "text=Netbanking",
                "text=Debit Card",
                "text=Credit Card",
                "text=Pay",
                "button:has-text('Place Order')",
            ]

            for ind in indicators:
                try:
                    el = await self.page.wait_for_selector(ind, timeout=2000)
                    if el:
                        logger.info("Payment page appears to be loaded")
                        return {'status': 'payment_page', 'url': self.page.url}
                except Exception:
                    continue

            # If no explicit indicators found, return current URL anyway
            return {'status': 'payment_page', 'url': self.page.url}

        except Exception as e:
            logger.error(f"go_to_payment failed: {e}")
            return {'status': 'error', 'error': str(e)}

    async def list_payment_methods(self, ensure_payment=False, max_methods=20, idle_seconds=0):
        """Return a list of visible payment method names on the payment page.

        Args:
            ensure_payment (bool): If True, navigate to payment first via `go_to_payment()`.
            max_methods (int): Limit number of returned methods.
            idle_seconds (int): If >0, keep the browser open for this many seconds after listing.

        Returns:
            list[str]: list of unique method texts (shortened).
        """
        logger.info("Listing payment methods")
        try:
            if ensure_payment:
                await self.go_to_payment()

            await self.page.wait_for_timeout(600)

            # Broad selector strategy: look for tab items, nav buttons and visible labels
            selectors = [
                "[role='tab']",
                "[testid^='nvb_']",
                "nav [role='tab']",
                "div[role='tab']",
                "div.textView",
                "article",
                "button",
                "label",
                "li",
            ]

            candidates = []
            for sel in selectors:
                try:
                    els = await self.page.query_selector_all(sel)
                    for e in els:
                        candidates.append(e)
                except Exception:
                    continue

            methods = []
            seen = set()
            for el in candidates:
                if len(methods) >= max_methods:
                    break
                try:
                    txt = (await el.inner_text()).strip()
                    txt_norm = ' '.join(txt.split())
                    if not txt_norm or len(txt_norm) < 2:
                        continue
                    # Skip strings that are just prices or UI noise
                    if self.PRICE_REGEX.search(txt_norm):
                        continue
                    low = txt_norm.lower()
                    if low in seen:
                        continue
                    # Heuristic: avoid long paragraphs, pick short labels (<= 40 chars)
                    if len(txt_norm) > 60:
                        continue
                    seen.add(low)
                    methods.append(txt_norm)
                except Exception:
                    continue

            logger.info(f"Found {len(methods)} payment methods")

            if idle_seconds and idle_seconds > 0:
                logger.info(f"Keeping browser open for {idle_seconds} seconds as requested")
                try:
                    await asyncio.sleep(idle_seconds)
                except Exception:
                    pass

            return methods
        except Exception as e:
            logger.debug(f"list_payment_methods error: {e}")
            return []

    async def select_payment_method(self, method_name, ensure_payment=False):
        """Attempt to select a payment method by name (partial match).

        Args:
            method_name (str): substring to match against visible method texts (case-insensitive).
            ensure_payment (bool): If True, navigate to payment first.

        Returns:
            bool: True if clicked a matching method, False otherwise.
        """
        # Simplified: only support Cash On Delivery (COD) / Pay On Delivery selection.
        logger.info(f"Selecting payment method (COD only): {method_name}")
        try:
            page = self.page

            if ensure_payment:
                await self.go_to_payment()

            await page.wait_for_timeout(500)

            # Common selectors for COD / Pay On Delivery
            cod_selectors = [
                "text=Pay On Delivery",
               
            ]

            # also try common abbreviations
            cod_selectors += ["text=Pay On Delivery", "text=Cash On Delivery"]

            for sel in cod_selectors:
                try:
                    el = await page.query_selector(sel)
                    if el and await el.is_visible():
                        try:
                            await el.scroll_into_view_if_needed()
                        except Exception:
                            pass
                        try:
                            await el.click()
                        except Exception:
                            try:
                                await el.evaluate("e => e.dispatchEvent(new MouseEvent('click', {bubbles:true, cancelable:true, view: window}))")
                            except Exception:
                                pass

                        await page.wait_for_timeout(800)
                        logger.info(f"Selected COD using selector: {sel}")
                    
                        return True
                except Exception:
                    continue

            logger.warning("COD payment method not found")
            return False
        except Exception as e:
            logger.error(f"select_payment_method (COD) failed: {e}")
            return False

    async def _click_proceed_if_present(self, page):
        """Click a 'Proceed to Pay' / 'Proceed' button if present on the current page/frame.

        Uses a set of robust selectors (including testid and aria-label) and tolerates absence.
        """
        try:
            proceed_selectors = [
                "[testid='btn_pay']",
                "button[testid='btn_pay']",
                "[testid^='btn_pay']",
                "button[aria-label*='Proceed to Pay']",
                "button:has-text('Proceed to Pay')",
                "button:has-text('Proceed to pay')",
                "button:has-text('Proceed')",
                "div[role='button'][testid='btn_pay']",
            ]

            for sel in proceed_selectors:
                try:
                    btn = await page.wait_for_selector(sel, timeout=2000)
                    if btn and await btn.is_visible():
                        await btn.scroll_into_view_if_needed()
                        await btn.click()
                        await page.wait_for_timeout(3000)
                        logger.info(f"Clicked proceed button using selector: {sel}")
                        return True
                except Exception:
                    continue

            logger.debug("No proceed/pay button found after selecting payment method")
            return False
        except Exception as e:
            logger.debug(f"_click_proceed_if_present error: {e}")
            return False

    async def click_proceed_final(self, ensure_payment=False):
        """Public wrapper to click the final 'Proceed' / 'Proceed to Pay' button.

        This function is intended to be called after the user explicitly confirms
        they want to proceed. It will optionally navigate to the payment screen
        first (when `ensure_payment=True`), then attempt to click the proceed
        button using the internal helper. Returns a dict with status and URL.
        """
        logger.info("Final proceed requested by user")
        try:
            if ensure_payment:
                await self.go_to_payment()

            await self.page.wait_for_timeout(300)

            clicked = await self._click_proceed_if_present(self.page)
            if clicked:
                logger.info("Proceed button clicked (final)")
                return {'status': 'clicked', 'url': self.page.url}
            else:
                logger.warning("Proceed button not found (final)")
                return {'status': 'not_found', 'url': self.page.url}

        except Exception as e:
            logger.error(f"click_proceed_final failed: {e}")
            return {'status': 'error', 'error': str(e)}

    
    def check_cod_availability(self, payment_methods):

        """Check if Cash On Delivery (COD) is available in the list of payment methods.

        Args:
            payment_methods (list[str]): List of payment method names.  """
        if not payment_methods:
            return False   
        
        cod_keywords = 'COD is currently unavailable'
        for method in payment_methods:
            if cod_keywords.lower() == method.lower():
                logger.info("Cash On Delivery (COD) is not available")
                return False

        logger.info("Cash On Delivery (COD) is available")
        return True
    
    async def checkout(self, ensure_cart=True):
        """Combined checkout function for agent usage.
        
        This method:
        1. Navigates to payment page
        2. Lists available payment methods
        3. Checks COD availability
        4. selects COD if available
        
        Args:
            ensure_cart (bool): If True, navigate to cart first (default True)
            
        Returns:
            dict: {
                'status': 'success'|'cod_unavailable'|'error',
                'payment_url': str,
                'payment_methods': list[str],
                'cod_available': bool,
                'error': str (only if status='error')
            }
        """
        logger.info("Starting checkout process")
        
        try:
            # Step 1: Navigate to payment page
            payment_result = await self.go_to_payment(ensure_cart=ensure_cart)
            
            if payment_result.get('status') == 'error':
                return {
                    'status': 'error',
                    'error': payment_result.get('error', 'Failed to navigate to payment'),
                    'payment_url': None,
                    'payment_methods': [],
                    'cod_available': False
                }
            
            payment_url = payment_result.get('url')
            
            # Step 2: List payment methods
            methods = await self.list_payment_methods()
            
            # Step 3: Check COD availability
            cod_available = self.check_cod_availability(methods)
            if cod_available:
                logger.info("Proceeding with Cash On Delivery (COD) option")    
                select_method = await self.select_payment_method("Pay On Delivery")  
                if select_method:
                    logger.info("COD method selected successfully")
                # await self.click_proceed_final()
            else:
                logger.info("COD not available — please add more items upto minimum order value 100rs.")
            result = {
                'status': 'success' if cod_available else 'cod_unavailable',
                'payment_url': payment_url,
                'payment_methods': methods,
                'cod_available': cod_available
            }
            
            logger.info(f"Checkout completed - COD available: {cod_available}")
            return result
            
        except Exception as e:
            logger.error(f"Checkout failed: {e}")
            return {
                'status': 'error',
                'error': str(e),
                'payment_url': None,
                'payment_methods': [],
                'cod_available': False
            }
    
    # UPI/QR helpers removed — operating in COD-only mode to keep the payment flow simple.



    
    # Example usage
    async def main(self):   
      
        await self.setup_browser()
      
        # location_selected = await self.select_current_location()
        # if location_selected:
        #     logger.info("Location selected successfully")
        # else:
        #     logger.error("Failed to select location")
        
        # address_selected = await self.select_delivery_address()
        # if address_selected:
        #     logger.info("Address selected successfully")
        # else:
        #     logger.error("Failed to select address")


        # await self.goto_cart()
        # is_high_demand = await self.check_high_demand_flag()
        # if is_high_demand:
        #     print("High demand - try again later")
        #     return 0
        # await self.clear_cart()

        # # Example: Find nearest product match from search results
        # await self.search_products("toast")
        # products_list = await self.extract_products(max_products=5)
        
      
        # await self.add_product_to_cart(product_name="brown toast", quantity=2, product_index=0)
        
   
      
        # cart_info = await self.get_order_details()
        # print(f"Cart Info: {cart_info}")
        # payment_url = await self.go_to_payment()
        # print(f"Payment URL: {payment_url}")
        # methods = await self.list_payment_methods()
        # print(f"Payment Methods: {methods}")
        # check_cod_status= self.check_cod_availability(methods)
  
        # if check_cod_status:
        #     logger.info("Proceeding with Cash On Delivery (COD) option")    
        #     select_method = await self.select_payment_method("Pay On Delivery")  
        #     if select_method:
        #         logger.info("COD method selected successfully")
        #         # await self.click_proceed_final()
        # else:
        #     logger.info("COD not available — please add more items upto minimum order value 100rs.")
        await self.goto_account()
        result = await self. get_order_history()
        order_details = await self.goto_order_details(1)
     
        print(f"Order History: {order_details}")
        await self.cleanup()
        
if __name__ == "__main__":
    phone_number = "9028129764"
    scraper = ZeptoScraper(phone_number, headless=False)
    
    asyncio.run(scraper.main())