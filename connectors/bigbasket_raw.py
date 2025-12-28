"""
BigBasket Order Automation - Simplified Version
Handles login with session persistence, product search, and checkout
"""

import time
import pickle
import os
from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.common.keys import Keys
from selenium.webdriver.edge.options import Options
from selenium.webdriver.edge.service import Service
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.common.action_chains import ActionChains
from selenium.common.exceptions import TimeoutException, NoSuchElementException

# Configuration
PHONE_NUMBER = "9028129764"  # Replace with your phone number
BIGBASKET_URL = "https://www.bigbasket.com"
SESSION_FILE = "output/bigbasket_session.pkl"

# Browser Configuration
HEADLESS_MODE = False  # Set to True for headless mode, False for GUI mode
CLEAR_CART_FIRST = True  # Set to True to clear cart before adding new products

class BigBasketAutomation:
    def __init__(self, headless=False):
        self.driver = None
        self.headless = headless
        self.setup_driver(headless)
    
    def setup_driver(self, headless=False):
        """Setup Edge browser with stealth settings"""
        print(f"Setting up Edge browser... (headless: {headless})")
        
        edge_options = Options()
        
        # Add headless mode if requested
        if headless:
            edge_options.add_argument("--headless")
            edge_options.add_argument("--disable-gpu")
            edge_options.add_argument("--window-size=1920,1080")
            print("Browser will run in headless mode (no GUI)")
        else:
            edge_options.add_argument("--start-maximized")
        
        edge_options.add_argument("--no-sandbox")
        edge_options.add_argument("--disable-dev-shm-usage")
        edge_options.add_argument("--disable-blink-features=AutomationControlled")
        edge_options.add_experimental_option("excludeSwitches", ["enable-automation"])
        edge_options.add_experimental_option('useAutomationExtension', False)
        edge_options.add_argument("--user-agent=Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36 Edg/120.0.0.0")
        
        try:
            self.driver = webdriver.Edge(options=edge_options)
            self.driver.execute_script("Object.defineProperty(navigator, 'webdriver', {get: () => undefined})")
            if headless:
                print("Headless browser setup complete")
            else:
                print("Browser setup complete")
        except Exception as e:
            print(f"Error setting up browser: {e}")
            return False
        
        return True
    
    def save_session(self):
        """Save login session cookies"""
        try:
            cookies = self.driver.get_cookies()
            # Filter BigBasket cookies only
            bb_cookies = [cookie for cookie in cookies if 'bigbasket' in cookie.get('domain', '')]
            
            with open(SESSION_FILE, 'wb') as file:
                pickle.dump(bb_cookies, file)
            print(f"Session saved with {len(bb_cookies)} cookies")
            return True
        except Exception as e:
            print(f"Error saving session: {e}")
            return False
    
    def load_session(self):
        """Load saved login session"""
        if not os.path.exists(SESSION_FILE):
            print("No saved session found")
            return False
        
        try:
            # Go to BigBasket first
            self.driver.get(BIGBASKET_URL)
            time.sleep(3)
            
            # Load cookies
            with open(SESSION_FILE, 'rb') as file:
                cookies = pickle.load(file)
            
            for cookie in cookies:
                try:
                    self.driver.add_cookie(cookie)
                except Exception as e:
                    print(f"Could not add cookie: {e}")
            
            # Refresh page to apply cookies
            self.driver.refresh()
            time.sleep(3)
            
            print(f"Session loaded with {len(cookies)} cookies")
            return True
        except Exception as e:
            print(f"Error loading session: {e}")
            return False
    
    def is_logged_in(self):
        """Check if user is logged in"""
        login_indicators = [
            "//span[contains(text(),'My Account')]",
            "//div[contains(@class,'user')]",
            "//span[contains(text(),'Hi')]",
            "//button[contains(text(),'Logout')]"
        ]
        
        for selector in login_indicators:
            try:
                elements = self.driver.find_elements(By.XPATH, selector)
                if elements and any(el.is_displayed() for el in elements):
                    print("User is logged in")
                    return True
            except:
                continue
        
        print("User is not logged in")
        return False
    
    def login_with_otp(self):
        """Handle OTP-based login"""
        print("Starting OTP login process...")
        
        # Go to BigBasket
        try:
            self.driver.get(BIGBASKET_URL)
            time.sleep(5)
            print("Successfully accessed BigBasket")
        except Exception as e:
            print(f"Error accessing BigBasket: {e}")
            return False
        
        # Look for login button
        login_selectors = [
            "//button[contains(text(),'Login')]",
            "//span[contains(text(),'Login')]//ancestor::button",
            "//a[contains(text(),'Login')]"
        ]
        
        login_btn = None
        for selector in login_selectors:
            try:
                elements = self.driver.find_elements(By.XPATH, selector)
                for element in elements:
                    if element.is_displayed():
                        login_btn = element
                        break
                if login_btn:
                    break
            except:
                continue
        
        if not login_btn:
            print("Login button not found")
            return False
        
        # Click login button
        try:
            self.driver.execute_script("arguments[0].click();", login_btn)
            print("Clicked login button")
            time.sleep(3)
        except Exception as e:
            print(f"Error clicking login: {e}")
            return False
        
        # Find phone input field
        phone_selectors = [
            "//input[@id='multiform']",
            "//input[@name='multiform']",
            "//input[@placeholder='Enter Phone number/ Email Id']",
            "//input[contains(@placeholder,'Phone number')]",
            "//input[@type='tel']"
        ]
        
        phone_input = None
        for selector in phone_selectors:
            try:
                elements = self.driver.find_elements(By.XPATH, selector)
                for element in elements:
                    if element.is_displayed():
                        phone_input = element
                        print(f"Found phone input field")
                        break
                if phone_input:
                    break
            except:
                continue
        
        if not phone_input:
            print("Phone input field not found")
            return False
        
        # Enter phone number
        try:
            phone_input.clear()
            time.sleep(1)
            phone_input.send_keys(PHONE_NUMBER)
            print(f"Entered phone number: {PHONE_NUMBER}")
            time.sleep(2)
        except Exception as e:
            print(f"Error entering phone number: {e}")
            return False
        
        # Find and click continue button
        continue_selectors = [
            "//button[contains(@class,'bg-rossoCorsa-500')]",
            "//button[contains(text(),'Continue')]",
            "//button[@type='submit']"
        ]
        
        continue_btn = None
        for selector in continue_selectors:
            try:
                elements = self.driver.find_elements(By.XPATH, selector)
                for element in elements:
                    if element.is_displayed():
                        continue_btn = element
                        break
                if continue_btn:
                    break
            except:
                continue
        
        if continue_btn:
            try:
                self.driver.execute_script("arguments[0].click();", continue_btn)
                print("Clicked continue button")
            except:
                continue_btn.click()
                print("Clicked continue button (fallback)")
        else:
            print("Continue button not found, trying Enter key...")
            phone_input.send_keys(Keys.RETURN)
        
        print("OTP requested")
        time.sleep(5)
        
        # Handle OTP input
        return self.handle_otp_verification()
    
    def handle_otp_verification(self):
        """Handle OTP verification process"""
        print("Looking for OTP input fields...")
        
        otp_selectors = [
            "//div[contains(@class,'flex')]//input[@type='number']",
            "//form//input[@type='number']",
            "//input[@type='number']"
        ]
        
        otp_input = None
        for selector in otp_selectors:
            try:
                elements = self.driver.find_elements(By.XPATH, selector)
                if elements and elements[0].is_displayed():
                    otp_input = elements[0]
                    print("Found OTP input field")
                    break
            except:
                continue
        
        if not otp_input:
            print("OTP input field not found")
            return False
        
        # Get OTP from user
        otp = input("Enter the 6-digit OTP sent to your phone: ")
        
        try:
            # Check if multiple OTP input fields exist (BigBasket style)
            all_otp_inputs = self.driver.find_elements(By.XPATH, "//form//input[@type='number']")
            
            if len(all_otp_inputs) > 1:
                print(f"Found {len(all_otp_inputs)} OTP input fields")
                # Fill each input field with one digit
                for i, digit in enumerate(otp[:len(all_otp_inputs)]):
                    if i < len(all_otp_inputs):
                        all_otp_inputs[i].clear()
                        all_otp_inputs[i].send_keys(digit)
                        time.sleep(0.2)
                print("Entered OTP in individual fields")
            else:
                # Single input field
                otp_input.clear()
                otp_input.send_keys(otp)
                print("Entered OTP")
            
            time.sleep(2)
        except Exception as e:
            print(f"Error entering OTP: {e}")
            return False
        
        # Find and click verify button
        verify_selectors = [
            "//button[contains(@class,'bg-rossoCorsa-500') and contains(@class,'text-rossoCorsa-50')]",
            "//button[contains(text(),'Verify & Continue')]",
            "//button[@type='submit']",
            "//button[contains(text(),'Verify')]"
        ]
        
        verify_btn = None
        for selector in verify_selectors:
            try:
                elements = self.driver.find_elements(By.XPATH, selector)
                for element in elements:
                    if element.is_displayed():
                        verify_btn = element
                        print("Found verify button")
                        break
                if verify_btn:
                    break
            except:
                continue
        
        if verify_btn:
            try:
                self.driver.execute_script("arguments[0].scrollIntoView(true);", verify_btn)
                time.sleep(1)
                self.driver.execute_script("arguments[0].click();", verify_btn)
                print("Clicked verify button")
            except Exception as e:
                print(f"JavaScript click failed: {e}, trying regular click...")
                try:
                    verify_btn.click()
                    print("Clicked verify button (fallback)")
                except:
                    print("Both click methods failed, trying Enter key...")
                    if 'all_otp_inputs' in locals() and len(all_otp_inputs) > 1:
                        all_otp_inputs[-1].send_keys(Keys.RETURN)
                    else:
                        otp_input.send_keys(Keys.RETURN)
        else:
            print("Verify button not found, trying Enter key...")
            try:
                # Check if we have the all_otp_inputs variable
                all_otp_inputs = self.driver.find_elements(By.XPATH, "//form//input[@type='number']")
                if len(all_otp_inputs) > 1:
                    all_otp_inputs[-1].send_keys(Keys.RETURN)
                else:
                    otp_input.send_keys(Keys.RETURN)
            except:
                otp_input.send_keys(Keys.RETURN)
        
        print("Submitted OTP")
        time.sleep(8)
        
        # Check if login was successful
        if self.is_logged_in():
            print("Login successful!")
            self.save_session()
            return True
        else:
            print("Login failed or still in progress")
            return False
    
    def search_product(self, product_name):
        """Search for a product"""
        print(f"Searching for product: {product_name}")
        
        search_selectors = [
            "//input[@placeholder='Search for Products...']",
            "//input[@placeholder='Search for products, brands and more']",
            "//div[contains(@class,'QuickSearch')]//input",
            "//input[contains(@class,'flex-1')]",
            "//input[contains(@class,'_3qnLc-')]",  # Latest BigBasket search input
            "//input[@type='text'][contains(@placeholder,'Search')]",
            "//input[contains(@placeholder,'Search')]",
            "//input[@type='search']",
            "//input[@data-testid='searchInputBox']"
        ]
        
        search_input = None
        for selector in search_selectors:
            try:
                elements = self.driver.find_elements(By.XPATH, selector)
                for element in elements:
                    if element.is_displayed():
                        search_input = element
                        print(f"✓ Found search input with selector: {selector}")
                        break
                if search_input:
                    break
            except:
                continue
        
        if not search_input:
            print("✗ Search input not found")
            return False
        
        try:
            search_input.clear()
            search_input.send_keys(product_name)
            time.sleep(2)
            search_input.send_keys(Keys.RETURN)
            print(f"✓ Searched for: {product_name}")
            time.sleep(6)  # Wait longer for search results
            
            # Verify we're on a search results page
            current_url = self.driver.current_url
            print(f"After search URL: {current_url}")
            
            # Check if we have search results with improved detection
            result_indicators = [
                "//div[contains(@class,'_3IXj4F')]",  # Latest product container
                "//div[@data-testid='productCardContainer']",
                "//div[contains(@class,'product')]",
                "//div[contains(@class,'item')]",
                "//div[contains(@class,'search')]",
                "//h1[contains(text(),'Search')]",
                "//span[contains(text(),'results')]",
                "//span[contains(text(),'result')]"
            ]
            
            has_results = False
            for indicator in result_indicators:
                try:
                    elements = self.driver.find_elements(By.XPATH, indicator)
                    if elements:
                        print(f"✓ Found search results: {len(elements)} items with indicator: {indicator}")
                        has_results = True
                        break
                except:
                    continue
            
            if not has_results:
                print("⚠ No search results found, but continuing...")
                # Try to capture what's on the page for debugging
                try:
                    page_title = self.driver.find_element(By.TAG_NAME, 'h1').text
                    print(f"Page title: {page_title}")
                except:
                    pass
            
            return True
        except Exception as e:
            print(f"✗ Error searching: {e}")
            return False
    
    def _find_element_with_selectors(self, container, selectors, element_type):
        """Helper to find element using multiple selectors"""
        for selector in selectors:
            try:
                elements = container.find_elements(By.XPATH, selector)
                for element in elements:
                    if element.is_displayed():
                        return element
            except:
                continue
        return None
    
    def _find_valid_increment_button(self, container, selectors):
        """Find increment button while excluding Save for Later buttons"""
        for selector in selectors:
            try:
                buttons = container.find_elements(By.XPATH, selector)
                for button in buttons:
                    if button.is_displayed():
                        button_html = button.get_attribute('outerHTML')
                        # Skip Save for Later buttons
                        if 'SaveIcon' in button_html or 'bookmark' in button_html.lower():
                            continue
                        # Ensure it's a plus button
                        if 'M19 11H13V5' in button_html or 'Plus' in button_html:
                            return button
            except:
                continue
        return None
    
    def _get_current_quantity(self, container):
        """Get current quantity from quantity display"""
        selectors = [
            ".//div[contains(@class,'CtaOnDeck___StyledDiv3')]//span[contains(@class,'CtaOnDeck___StyledLabel')]",
            ".//span[contains(@class,'CtaOnDeck___StyledLabel') and contains(@class,'ezEGzY')]",
            ".//div[contains(@class,'kFTYbO')]//span",
            ".//div[contains(@class,'jqLNGe')]//span"
        ]
        
        for selector in selectors:
            try:
                elements = container.find_elements(By.XPATH, selector)
                for element in elements:
                    if element.is_displayed():
                        qty_text = element.text.strip()
                        if qty_text and qty_text.isdigit():
                            return int(qty_text)
            except:
                continue
        return 0
    
    def _check_if_out_of_stock(self, container):
        """Check if product is out of stock"""
        try:
            out_of_stock_indicators = [
                ".//div[contains(text(),'Out of stock')]",
                ".//div[contains(text(),'Currently unavailable')]",
                ".//span[contains(text(),'Out of stock')]",
                ".//span[contains(text(),'Currently unavailable')]",
                ".//button[contains(text(),'Notify') and contains(text(),'available')]",
                ".//button[contains(@class,'notify') or contains(@class,'Notify')]",
                ".//div[contains(@class,'out-of-stock') or contains(@class,'outOfStock')]"
            ]
            
            for selector in out_of_stock_indicators:
                try:
                    elements = container.find_elements(By.XPATH, selector)
                    for element in elements:
                        if element.is_displayed():
                            print("⚠️ Product is out of stock")
                            return True
                except:
                    continue
            return False
        except Exception as e:
            print(f"Error checking stock status: {e}")
            return False
    
    def _click_button_multiple_methods(self, button, button_name="button"):
        """Try multiple click methods for reliability"""
        methods = [
            ("direct", lambda: button.click()),
            ("javascript", lambda: self.driver.execute_script("arguments[0].click();", button)),
            ("actionchain", lambda: ActionChains(self.driver).move_to_element(button).click().perform())
        ]
        
        for method_name, click_func in methods:
            try:
                click_func()
                print(f"✅ {button_name} clicked using {method_name}")
                return True
            except Exception as e:
                print(f"❌ {method_name} failed: {e}")
        return False

    def add_to_cart(self, product_index=0, quantity=1):
        """Add product from search results page with specified quantity
        Returns: dict with 'success' (bool), 'reason' (str), 'out_of_stock' (bool)
        """
        print(f"🛒 Adding product (index: {product_index}, quantity: {quantity})")
        
        try:
            # Find product containers
            container_selectors = [
                "//li[contains(@class,'PaginateItems___StyledLi')]",
                "//div[contains(@class,'SKUDeck___StyledDiv')]", 
                "//div[contains(@class,'ProductTile')]",
                "//div[contains(@class,'product')]"
            ]
            
            containers = None
            for selector in container_selectors:
                try:
                    containers = self.driver.find_elements(By.XPATH, selector)
                    if containers:
                        print(f"Found {len(containers)} products")
                        break
                except:
                    continue
            
            if not containers or product_index >= len(containers):
                print("❌ Product container not found")
                return {'success': False, 'reason': 'product_not_found', 'out_of_stock': False}
            
            target_product = containers[product_index]
            self.driver.execute_script("arguments[0].scrollIntoView({block: 'center'});", target_product)
            time.sleep(1)
            
            # Check if product is out of stock FIRST
            if self._check_if_out_of_stock(target_product):
                return {'success': False, 'reason': 'out_of_stock', 'out_of_stock': True}
            
            # Get current quantity
            current_quantity = self._get_current_quantity(target_product)
            print(f"Current quantity: {current_quantity}")
            
            # Define selectors
            increment_selectors = [
                ".//button[.//svg//path[contains(@d,'M19 11H13V5')]]",
                ".//button[contains(@class,'GGExL') and .//svg[contains(@class,'kyqQMg')]]",
                ".//button[contains(@class,'dcJzPv') and contains(@class,'CtaOnDeck___StyledButton2')]"
            ]
            
            decrement_selectors = [
                ".//button[.//svg//path[contains(@d,'M19 13H5C4.448 13')]]",
                ".//button[contains(@class,'CtaOnDeck___StyledButton') and .//svg[contains(@class,'CtaOnDeck___StyledMinusIcon')]]"
            ]
            
            add_button_selectors = [
                ".//button[contains(@class,'CtaOnDeck___StyledButton3') and contains(text(),'Add')]",
                ".//button[contains(@class,'gFVhCS') and contains(text(),'Add')]"
            ]
            
            # Add product to cart if not already added
            if current_quantity == 0:
                add_button = self._find_element_with_selectors(target_product, add_button_selectors, "add")
                if not add_button:
                    print("❌ No Add button found - possibly out of stock")
                    # Double-check for out of stock
                    if self._check_if_out_of_stock(target_product):
                        return {'success': False, 'reason': 'out_of_stock', 'out_of_stock': True}
                    return {'success': False, 'reason': 'add_button_not_found', 'out_of_stock': False}
                
                if self._click_button_multiple_methods(add_button, "Add button"):
                    current_quantity = 1
                    time.sleep(3)  # Wait for UI update
                else:
                    print("❌ Failed to click Add button")
                    return {'success': False, 'reason': 'add_button_click_failed', 'out_of_stock': False}
            
            # Adjust quantity
            if quantity > current_quantity:
                # Increment
                increments_needed = quantity - current_quantity
                increment_button = self._find_valid_increment_button(target_product, increment_selectors)
                
                if not increment_button:
                    print("❌ No increment button found")
                    return {'success': False, 'reason': 'increment_button_not_found', 'out_of_stock': False}
                
                time.sleep(1)
                for i in range(increments_needed):
                    if self._click_button_multiple_methods(increment_button, f"Increment {i+1}"):
                        time.sleep(1.5)
                    else:
                        print(f"❌ Failed increment {i+1}")
                        return {'success': False, 'reason': f'increment_failed_at_{i+1}', 'out_of_stock': False}
                        
            elif quantity < current_quantity:
                # Decrement
                decrements_needed = current_quantity - quantity
                decrement_button = self._find_element_with_selectors(target_product, decrement_selectors, "decrement")
                
                if not decrement_button:
                    print("❌ No decrement button found")
                    return {'success': False, 'reason': 'decrement_button_not_found', 'out_of_stock': False}
                
                for i in range(decrements_needed):
                    if self._click_button_multiple_methods(decrement_button, f"Decrement {i+1}"):
                        time.sleep(0.8)
                    else:
                        print(f"❌ Failed decrement {i+1}")
                        return {'success': False, 'reason': f'decrement_failed_at_{i+1}', 'out_of_stock': False}
            
            print(f"✅ Successfully set quantity to {quantity}")
            return {'success': True, 'reason': 'added_successfully', 'out_of_stock': False}
            
        except Exception as e:
            print(f"❌ Error: {e}")
            return {'success': False, 'reason': f'exception: {str(e)}', 'out_of_stock': False}

    def get_alternative_products(self):
        """Get first 5 products when target product is not available"""
        print("Target product not available, searching for alternative products...")
        
        try:
            alternative_products = []
            
            # Wait for dynamic content to load
            time.sleep(2)
            
            # Use the selector that's actually finding results on the search page
            product_items = self.driver.find_elements(By.XPATH, "//div[contains(@class,'item')]")
            print(f"✓ Found {len(product_items)} product items with 'item' class")
            
            if not product_items:
                print("✗ No products found, trying alternative patterns...")
                # Try other common product container patterns
                for selector in ["//div[contains(@class,'product')]", "//article", "//li"]:
                    product_items = self.driver.find_elements(By.XPATH, selector)
                    if product_items:
                        print(f"  Found {len(product_items)} items with selector: {selector}")
                        break
            
            if product_items:
                # Extract first 5 products
                for i, item in enumerate(product_items[:5]):
                    try:
                        product_info = {
                            'name': '',
                            'price': '',
                            'link': '',
                            'brand': ''
                        }
                        
                        # Try multiple selectors for product name
                        name_selectors = [
                            ".//h2",
                            ".//h3",
                            ".//a[@href]",
                            ".//span[contains(@class,'name')]",
                            ".//div[contains(text(),'')]",  # Any div with text
                        ]
                        
                        for name_sel in name_selectors:
                            try:
                                name_elem = item.find_element(By.XPATH, name_sel)
                                if name_elem and name_elem.text.strip():
                                    product_info['name'] = name_elem.text.strip()
                                    break
                            except:
                                continue
                        
                        # Try multiple selectors for price
                        price_selectors = [
                            ".//span[contains(@class,'price')]",
                            ".//div[contains(@class,'price')]",
                            ".//span[contains(text(),'₹')]",
                            ".//span[contains(text(),'Rs')]",
                        ]
                        
                        for price_sel in price_selectors:
                            try:
                                price_elem = item.find_element(By.XPATH, price_sel)
                                if price_elem and price_elem.text.strip():
                                    price_text = price_elem.text.strip()
                                    if '₹' in price_text or 'Rs' in price_text or price_text[0].isdigit():
                                        product_info['price'] = price_text
                                        break
                            except:
                                continue
                        
                        # Try to find product link
                        link_selectors = [
                            ".//a[@href]",
                            ".//@href",
                        ]
                        
                        for link_sel in link_selectors:
                            try:
                                if link_sel == ".//@href":
                                    href = item.get_attribute('href')
                                    if href:
                                        product_info['link'] = href
                                        break
                                else:
                                    link_elem = item.find_element(By.XPATH, link_sel)
                                    href = link_elem.get_attribute('href')
                                    if href:
                                        product_info['link'] = href
                                        break
                            except:
                                continue
                        
                        # Try to find brand
                        brand_selectors = [
                            ".//span[contains(@class,'brand')]",
                            ".//div[contains(@class,'brand')]",
                            ".//a[1]",  # Sometimes brand is first link
                        ]
                        
                        for brand_sel in brand_selectors:
                            try:
                                brand_elem = item.find_element(By.XPATH, brand_sel)
                                if brand_elem and brand_elem.text.strip():
                                    product_info['brand'] = brand_elem.text.strip()
                                    break
                            except:
                                continue
                        
                        # Validate product info
                        if product_info['name'] and product_info['name'].lower() not in ['home', 'copyright', 'back', 'close', 'filter']:
                            alternative_products.append(product_info)
                            print(f"  ✓ Product {len(alternative_products)}: {product_info['name'][:60]}")
                            if product_info['price']:
                                print(f"    Price: {product_info['price']}")
                        
                    except Exception as e:
                        print(f"[DEBUG] Error extracting product {i}: {e}")
                        continue
            
            if alternative_products:
                print(f"✓ Found {len(alternative_products)} valid alternative products")
                return alternative_products
            else:
                print("✗ No alternative products found after trying all selectors")
                # Debug output
                try:
                    print(f"[DEBUG] Total items found: {len(product_items)}")
                    if product_items:
                        print(f"[DEBUG] First item HTML: {product_items[0].get_attribute('outerHTML')[:500]}")
                except:
                    pass
                return []
                
        except Exception as e:
            print(f"Error getting alternative products: {e}")
            import traceback
            traceback.print_exc()
            return []

    def _extract_product_info(self, product_element, index):
        """Extract product information from a product element"""
        try:
            product_info = {
                'name': '',
                'price': '',
                'brand': '',
                'index': index
            }
            
            # DEBUG: Print element classes to understand structure
            element_classes = product_element.get_attribute('class')
            element_html_snippet = product_element.get_attribute('outerHTML')[:500]
            print(f"\n[DEBUG Product {index}] Classes: {element_classes}")
            print(f"[DEBUG Product {index}] HTML: {element_html_snippet}...")
            
            # Extract product name - updated selectors for 2024+ BigBasket
            name_selectors = [
                ".//h2",  # Latest BigBasket uses h2 for product names
                ".//span[contains(@class,'_3qnLc-')]",  # Product name class
                ".//h3",
                ".//h4",
                ".//div[contains(@class,'name')]",
                ".//div[contains(@class,'title')]",
                ".//span[contains(@class,'name')]",
                ".//a[contains(@class,'title')]",
                ".//div[contains(@class,'Product___StyledProductName')]",
                ".//a[@data-testid='productTitle']",
                ".//div[@data-testid='productTitle']",
                ".//a",  # Fallback: first link often has product name
                ".//p",  # Fallback: paragraph
                ".//span[not(contains(@class,'price'))]"  # Non-price span
            ]
            
            for selector in name_selectors:
                try:
                    name_elements = product_element.find_elements(By.XPATH, selector)
                    for name_element in name_elements:
                        if name_element and name_element.is_displayed():
                            name_text = name_element.text.strip()
                            if name_text and len(name_text) > 3 and len(name_text) < 200:
                                # Skip if it looks like a button or price
                                if 'add to cart' not in name_text.lower() and '₹' not in name_text:
                                    product_info['name'] = name_text
                                    print(f"[DEBUG] Found name with selector {selector}: {name_text}")
                                    break
                    if product_info['name']:
                        break
                except:
                    continue
            
            # Extract price - updated selectors for 2024+ BigBasket
            price_selectors = [
                ".//div[contains(@class,'_1sPsX')]",  # Price wrapper class
                ".//span[contains(@class,'_1l7iYw')]",  # Price amount class
                ".//span[contains(text(),'₹')]",
                ".//div[contains(text(),'₹')]",
                ".//span[contains(@class,'price')]",
                ".//div[contains(@class,'price')]",
                ".//span[contains(@class,'amount')]",
                ".//div[contains(@class,'amount')]",
                ".//span[contains(@class,'bold')]",  # Sometimes price is in bold
                ".//span"  # Any span might have price
            ]
            
            for selector in price_selectors:
                try:
                    price_elements = product_element.find_elements(By.XPATH, selector)
                    for price_elem in price_elements:
                        if price_elem and price_elem.is_displayed():
                            price_text = price_elem.text.strip()
                            if '₹' in price_text or (price_text and any(c.isdigit() for c in price_text)):
                                product_info['price'] = price_text
                                print(f"[DEBUG] Found price with selector {selector}: {price_text}")
                                break
                    if product_info['price']:
                        break
                except:
                    continue
            
            # Extract brand (if available)
            brand_selectors = [
                ".//span[contains(@class,'_2DzOKT')]",  # Brand class
                ".//span[contains(@class,'brand')]",
                ".//div[contains(@class,'brand')]",
                ".//span[contains(@class,'manufacturer')]"
            ]
            
            for selector in brand_selectors:
                try:
                    brand_element = product_element.find_element(By.XPATH, selector)
                    if brand_element and brand_element.is_displayed():
                        brand_text = brand_element.text.strip()
                        if brand_text:
                            product_info['brand'] = brand_text
                            print(f"[DEBUG] Found brand: {brand_text}")
                            break
                except:
                    continue
            
            # Only return if we have at least a name
            if product_info['name']:
                print(f"✓ Product {index}: {product_info}")
                return product_info
            else:
                print(f"✗ Product {index}: NO NAME FOUND")
                return None
                
        except Exception as e:
            print(f"✗ Error extracting product info for index {index}: {e}")
            import traceback
            traceback.print_exc()
            return None
    
    def go_to_cart(self):
        """Navigate to shopping cart - try direct URL first, then basket button"""
        print("Navigating to cart...")
        
        # Try direct URL navigation first (most reliable)
        print("Trying direct URL navigation first...")
        if self.goto_cart():
            return True
        
        # Fallback to basket button clicking
        print("Direct URL failed, trying basket button as fallback...")
        print("Looking for basket button...")
        
        basket_selectors = [
            # Exact BigBasket basket button from HTML
            "//button[contains(@class,'Header___StyledButton-sc-19kl9m3-6')]",
            "//button[contains(@class,'FCIoq') and contains(@class,'gKUOcO')]",
            "//span[contains(text(),'Items')]//ancestor::button",
            "//span[contains(text(),'Item')]//ancestor::button",
            
            # Alternative selectors for basket button
            "//button[@color='rossoCorsa'][@pattern='filled']",
            "//button[contains(@class,'Header___StyledButton')]",
            "//span[contains(@class,'Header___StyledLabel')]//ancestor::button",
            
            # More generic basket/cart selectors
            "//a[@href='/basket/']",
            "//a[contains(@href,'basket')]//button",
            "//a[contains(@href,'cart')]",
            "//button[contains(text(),'Cart')]",
            
            # Additional patterns for basket buttons
            "//div[contains(@class,'basket')]//button",
            "//div[contains(@class,'cart')]//button",
            "//button[contains(@aria-label,'basket')]",
            "//button[contains(@aria-label,'cart')]",
            "//svg[contains(@class,'basket')]//ancestor::button",
            "//svg[contains(@class,'cart')]//ancestor::button",
            
            # Look for buttons with cart/basket icons or numbers
            "//button[contains(@class,'Header') and contains(@class,'Button')]",
            "//button[.//*[contains(@class,'basket')]]",
            "//button[.//*[contains(@class,'cart')]]",
            
            # Text-based fallbacks
            "//span[contains(text(),'₹')]//ancestor::button",
            "//div[contains(text(),'₹')]//ancestor::button"
        ]
        
        for selector in basket_selectors:
            try:
                elements = self.driver.find_elements(By.XPATH, selector)
                for element in elements:
                    if element.is_displayed():
                        # Check if it's actually a basket button (should contain Items text)
                        try:
                            element_text = element.text.lower()
                            if 'item' in element_text or selector in basket_selectors[:4]:
                                self.driver.execute_script("arguments[0].scrollIntoView(true);", element)
                                time.sleep(1)
                                self.driver.execute_script("arguments[0].click();", element)
                                print(f"Successfully clicked basket button")
                                
                                # Wait for cart page to load
                                time.sleep(5)
                                
                                # Check if we're on cart/basket page
                                current_url = self.driver.current_url
                                if 'basket' in current_url or 'cart' in current_url:
                                    print(f"Successfully navigated to cart page: {current_url}")
                                    return True
                                else:
                                    print(f"Basket button clicked but not on cart page. Current URL: {current_url}")
                                    return True  # Continue anyway, might be a popup/modal
                                    
                        except Exception as text_error:
                            # Handle stale element reference by re-finding the element
                            print(f"Stale element detected, re-finding basket button...")
                            try:
                                # Re-find elements after DOM change
                                fresh_elements = self.driver.find_elements(By.XPATH, selector)
                                if fresh_elements and fresh_elements[0].is_displayed():
                                    fresh_elements[0].click()
                                    print("Successfully clicked basket button (retry)")
                                    time.sleep(5)
                                    return True
                            except:
                                continue
                                
            except Exception as e:
                # Skip stale element errors and continue to next selector
                if "stale element reference" in str(e).lower():
                    print(f"Stale element with selector {selector}, continuing...")
                    continue
                else:
                    print(f"Error with basket selector {selector}: {e}")
                    continue
        
        print("Both direct URL and basket button methods failed")
        return False
    
    def goto_cart(self):
        """Navigate directly to cart using BigBasket basket URL"""
        try:
            basket_url = "https://www.bigbasket.com/basket/"
            print(f"Navigating to: {basket_url}")
            self.driver.get(basket_url)
            time.sleep(5)  # Wait for basket page to load
            print("Successfully accessed basket page")
            return True
        except Exception as e:
            print(f"Failed to navigate to basket URL: {e}")
            return False
    
    def get_cart_items(self):
        """Get list of items currently in cart with details (name, price, quantity)"""
        print("Getting cart items...")
        cart_items = []
        
        try:
            # Navigate to cart first
            if not self.goto_cart():
                print("Failed to access cart")
                return []
            
            time.sleep(3)
            
            # Check if cart is empty
            empty_indicators = [
                "//div[contains(text(),'Your basket is empty')]",
                "//div[contains(text(),'No items in cart')]"
            ]
            
            for indicator in empty_indicators:
                try:
                    elements = self.driver.find_elements(By.XPATH, indicator)
                    if elements and any(el.is_displayed() for el in elements):
                        print("Cart is empty")
                        return []
                except:
                    continue
            
            # Find cart item containers
            item_selectors = [
                "//div[contains(@class,'BasketItemDetails')]",
                "//div[contains(@class,'cart-item')]",
                "//div[contains(@class,'basket-item')]",
                "//li[contains(@class,'cart')]//div[contains(@class,'product')]"
            ]
            
            items = []
            for selector in item_selectors:
                try:
                    items = self.driver.find_elements(By.XPATH, selector)
                    if items:
                        print(f"Found {len(items)} items using selector: {selector}")
                        break
                except:
                    continue
            
            if not items:
                print("No cart items found")
                return []
            
            # Extract details from each item
            for i, item in enumerate(items):
                try:
                    item_info = {
                        'name': '',
                        'price': '',
                        'quantity': 1,
                        'brand': ''
                    }
                    
                    # Get product name
                    name_selectors = [
                        ".//div[contains(@class,'truncate')]",
                        ".//h3",
                        ".//span[contains(@class,'name')]",
                        ".//div[contains(@class,'product-name')]"
                    ]
                    
                    for sel in name_selectors:
                        try:
                            name_elem = item.find_element(By.XPATH, sel)
                            if name_elem and name_elem.text.strip():
                                item_info['name'] = name_elem.text.strip()
                                break
                        except:
                            continue
                    
                    # Get price
                    price_selectors = [
                        ".//span[contains(text(),'₹')]",
                        ".//div[contains(text(),'₹')]"
                    ]
                    
                    for sel in price_selectors:
                        try:
                            price_elem = item.find_element(By.XPATH, sel)
                            if price_elem and '₹' in price_elem.text:
                                item_info['price'] = price_elem.text.strip()
                                break
                        except:
                            continue
                    
                    # Get quantity
                    qty_selectors = [
                        ".//span[contains(@class,'label')]",
                        ".//div[contains(@class,'quantity')]//span"
                    ]
                    
                    for sel in qty_selectors:
                        try:
                            qty_elem = item.find_element(By.XPATH, sel)
                            qty_text = qty_elem.text.strip()
                            if qty_text.isdigit():
                                item_info['quantity'] = int(qty_text)
                                break
                        except:
                            continue
                    
                    if item_info['name']:
                        cart_items.append(item_info)
                        print(f"Cart item {i+1}: {item_info['name']} - {item_info['price']} (qty: {item_info['quantity']})")
                    
                except Exception as e:
                    print(f"Error extracting item {i}: {e}")
                    continue
            
            return cart_items
            
        except Exception as e:
            print(f"Error getting cart items: {e}")
            return []
    
    def clear_cart(self):
        """Clear all items from the cart by directly navigating to basket URL"""
        print("Clearing cart by navigating directly to basket URL...")
        
        # Use the reusable goto_cart function
        if not self.goto_cart():
            print("Failed to access cart, skipping cart clearing and continuing with automation...")
            return True  # Don't fail the entire automation
        
        # Wait for cart page to load
        time.sleep(3)
        
        # Check if cart is already empty
        empty_cart_indicators = [
            "//div[contains(text(),'Your basket is empty')]",
            "//div[contains(text(),'No items in cart')]",
            "//div[contains(text(),'Cart is empty')]",
            "//span[contains(text(),'empty')]",
            "//div[contains(@class,'empty-cart')]",
            "//div[contains(@class,'no-items')]"
        ]
        
        for indicator in empty_cart_indicators:
            try:
                elements = self.driver.find_elements(By.XPATH, indicator)
                if elements and any(el.is_displayed() for el in elements):
                    print("Cart is already empty")
                    return True
            except:
                continue
        
        # Look for individual "Delete" buttons for each cart item (based on actual HTML structure)
        delete_button_selectors = [
            # Exact selector based on the provided HTML
            "//button[contains(@class,'BasketControls___StyledButton2-sc-k63v4f-3') and contains(@class,'fJvtwC') and text()='Delete']",
            
            # More generic selectors for Delete buttons
            "//button[contains(text(),'Delete')]",
            "//button[contains(@class,'BasketControls') and contains(text(),'Delete')]",
            "//div[contains(@class,'BasketControls')]//button[contains(text(),'Delete')]",
            
            # Alternative patterns
            "//button[contains(@class,'StyledButton2') and contains(text(),'Delete')]",
            "//li[contains(@class,'BasketItem')]//button[contains(text(),'Delete')]"
        ]
        
        items_deleted = 0
        max_attempts = 10  # Prevent infinite loop
        
        for attempt in range(max_attempts):
            delete_button_found = False
            
            # Try to find and click any Delete button
            for selector in delete_button_selectors:
                try:
                    elements = self.driver.find_elements(By.XPATH, selector)
                    if elements:
                        for element in elements:
                            if element.is_displayed():
                                try:
                                    # Scroll to element and click
                                    self.driver.execute_script("arguments[0].scrollIntoView(true);", element)
                                    time.sleep(0.5)
                                    
                                    # Click the delete button
                                    self.driver.execute_script("arguments[0].click();", element)
                                    print(f"Deleted item from cart (attempt {attempt + 1})")
                                    items_deleted += 1
                                    delete_button_found = True
                                    time.sleep(2)  # Wait for item removal to process
                                    break
                                    
                                except Exception as click_error:
                                    # Try regular click if JavaScript fails
                                    try:
                                        element.click()
                                        print(f"Deleted item from cart (fallback click)")
                                        items_deleted += 1
                                        delete_button_found = True
                                        time.sleep(2)
                                        break
                                    except:
                                        continue
                        
                        if delete_button_found:
                            break
                            
                except Exception as e:
                    continue
            
            # If no delete button found, cart might be empty
            if not delete_button_found:
                break
            
            # Wait before next attempt
            time.sleep(1)
        
        # Report results
        if items_deleted > 0:
            print(f"Successfully deleted {items_deleted} items from cart")
            
            # Wait for cart to update
            time.sleep(3)
            
            # Check if cart is now empty
            for indicator in empty_cart_indicators:
                try:
                    elements = self.driver.find_elements(By.XPATH, indicator)
                    if elements and any(el.is_displayed() for el in elements):
                        print("Cart is now empty")
                        return True
                except:
                    continue
            
            print("Items deleted, cart should be cleared")
            return True
        else:
            print("No delete buttons found - cart might already be empty")
            return True
    
    def get_order_summary(self):
        """Extract detailed order summary from BigBasket checkout page"""
        print("Extracting detailed order summary...")
        order_details = {
            'products': [],
            'basket_value': '',
            'delivery_charge': '',
            'handling_charge': '',
            'feed_needy': '',
            'bag_charge': '',
            'bbwallet_discount': '',
            'neucoins_discount': '',
            'total_payable': '',
            'total_savings': '',
            'vouchers_available': ''
        }
        
        try:
            # Extract basket value
            try:
                basket_value = self.driver.find_element(By.XPATH, "//span[text()='Basket Value']/following-sibling::span")
                order_details['basket_value'] = basket_value.text.strip()
                print(f"Found basket value: {order_details['basket_value']}")
            except:
                print("Could not find basket value")
            
            # Extract delivery & handling charges
            try:
                delivery_elements = self.driver.find_elements(By.XPATH, "//span[contains(text(),'Delivery & Handling Charges')]/following-sibling::div//span")
                if delivery_elements:
                    order_details['delivery_charge'] = delivery_elements[-1].text.strip()
                    print(f"Found delivery charge: {order_details['delivery_charge']}")
            except:
                print("Could not find delivery charge")
            
            # Extract handling charge specifically
            try:
                handling_element = self.driver.find_element(By.XPATH, "//span[contains(text(),'Handling Charge')]/following-sibling::div//span[last()]")
                order_details['handling_charge'] = handling_element.text.strip()
                print(f"Found handling charge: {order_details['handling_charge']}")
            except:
                print("Could not find handling charge")
            
            # Extract Feed the Needy charge
            try:
                needy_element = self.driver.find_element(By.XPATH, "//span[contains(text(),'Feed the Needy')]/following-sibling::div//span[last()]")
                order_details['feed_needy'] = needy_element.text.strip()
                print(f"Found feed needy charge: {order_details['feed_needy']}")
            except:
                print("Could not find feed needy charge")
            
            # Extract bag charge
            try:
                bag_element = self.driver.find_element(By.XPATH, "//span[contains(text(),'Get your bbNow order in a bag')]/following-sibling::div//span[last()]")
                order_details['bag_charge'] = bag_element.text.strip()
                print(f"Found bag charge: {order_details['bag_charge']}")
            except:
                print("Could not find bag charge")
            
            # Extract bbWallet discount
            try:
                bbwallet_element = self.driver.find_element(By.XPATH, "//span[contains(text(),'Use bbWallet')]/following-sibling::span")
                order_details['bbwallet_discount'] = bbwallet_element.text.strip()
                print(f"Found bbWallet discount: {order_details['bbwallet_discount']}")
            except:
                print("Could not find bbWallet discount")
            
            # Extract Neucoins discount
            try:
                neucoins_element = self.driver.find_element(By.XPATH, "//span[contains(text(),'Redeemed Neucoins')]/following-sibling::span")
                order_details['neucoins_discount'] = neucoins_element.text.strip()
                print(f"Found Neucoins discount: {order_details['neucoins_discount']}")
            except:
                print("Could not find Neucoins discount")
            
            # Extract total payable amount
            try:
                total_element = self.driver.find_element(By.XPATH, "//span[contains(text(),'Total Amount Payable')]/following-sibling::span")
                order_details['total_payable'] = total_element.text.strip()
                print(f"Found total payable: {order_details['total_payable']}")
            except:
                print("Could not find total payable")
            
            # Extract total savings
            try:
                savings_element = self.driver.find_element(By.XPATH, "//span[contains(text(),'Total Savings')]/following-sibling::div//span")
                order_details['total_savings'] = savings_element.text.strip()
                print(f"Found total savings: {order_details['total_savings']}")
            except:
                print("Could not find total savings")
            
            # Extract vouchers available
            try:
                voucher_element = self.driver.find_element(By.XPATH, "//span[contains(text(),'vouchers are available')]")
                order_details['vouchers_available'] = voucher_element.text.strip()
                print(f"Found vouchers: {order_details['vouchers_available']}")
            except:
                print("Could not find vouchers info")
            
            # Try to extract product names from various possible locations
            product_selectors = [
                "//div[contains(@class,'product-name')]",
                "//span[contains(@class,'product')]",
                "//div[contains(@class,'item-name')]",
                "//h3",
                "//h4"
            ]
            
            for selector in product_selectors:
                try:
                    products = self.driver.find_elements(By.XPATH, selector)
                    for product in products[:5]:  # Limit to first 5 items
                        if product.is_displayed():
                            text = product.text.strip()
                            if len(text) > 3 and '₹' not in text and text not in order_details['products']:
                                order_details['products'].append(text)
                    if order_details['products']:
                        break
                except:
                    continue
            
            return order_details
            
        except Exception as e:
            print(f"Error extracting order summary: {e}")
            return order_details
    
    def display_order_summary(self, order_details):
        """Display detailed order summary to user"""
        print("\n" + "="*60)
        print("                   BIGBASKET ORDER SUMMARY")
        print("="*60)
        
        # Products
        if order_details['products']:
            print("PRODUCTS:")
            for i, product in enumerate(order_details['products'][:5], 1):
                print(f"  {i}. {product}")
        else:
            print("PRODUCTS: Unable to extract product details")
        
        print("\n" + "-"*60)
        print("PRICING BREAKDOWN:")
        print("-"*60)
        
        # Basket value
        if order_details['basket_value']:
            print(f"Basket Value:                {order_details['basket_value']}")
        
        # Delivery charges
        if order_details['delivery_charge']:
            print(f"Delivery & Handling Charges:     {order_details['delivery_charge']}")
        
        if order_details['handling_charge']:
            print(f"  - Handling Charge:             {order_details['handling_charge']}")
        
        # Additional charges
        if order_details['feed_needy']:
            print(f"Feed the Needy (Optional):       {order_details['feed_needy']}")
        
        if order_details['bag_charge']:
            print(f"Bag Charge:                      {order_details['bag_charge']}")
        
        # Discounts
        print("\nDISCOUNTS & SAVINGS:")
        print("-"*30)
        
        if order_details['bbwallet_discount']:
            print(f"bbWallet Discount:               {order_details['bbwallet_discount']}")
        
        if order_details['neucoins_discount']:
            print(f"NeuCoins Discount:               {order_details['neucoins_discount']}")
        
        if order_details['total_savings']:
            print(f"Total Savings:                   {order_details['total_savings']}")
        
        # Final amount
        print("\n" + "="*60)
        if order_details['total_payable']:
            print(f"TOTAL AMOUNT PAYABLE:            {order_details['total_payable']}")
        else:
            print("TOTAL AMOUNT PAYABLE:            Unable to extract")
        
        # Vouchers info
        if order_details['vouchers_available']:
            print(f"Available Vouchers:              {order_details['vouchers_available']}")
        
        print("="*60)
    
    def proceed_to_checkout(self):
        """Proceed to checkout by clicking checkout button"""
        print("Looking for checkout button...")
        
        checkout_selectors = [
            # BigBasket specific "Proceed to Checkout" button
            "//button[contains(@class,'BasketDoor___StyledButton3')]",
            "//button[contains(text(),'Proceed to Checkout')]",
            "//button[contains(@class,'druTpf') and contains(@class,'eEsjCJ')]",
            
            # Generic checkout selectors
            "//button[contains(text(),'Checkout')]",
            "//button[contains(text(),'Proceed')]",
            "//a[contains(text(),'Checkout')]",
            "//span[contains(text(),'Checkout')]//ancestor::button",
            "//button[contains(@class,'checkout')]",
            
            # Color-based selector (rossoCorsa is BigBasket's red color)
            "//button[@color='rossoCorsa']",
            "//button[contains(@pattern,'filled')]",
            
            # Additional checkout button patterns
            "//div[contains(@class,'checkout')]//button",
            "//button[contains(@aria-label,'checkout')]",
            "//button[contains(@title,'checkout')]"
        ]
        
        for selector in checkout_selectors:
            try:
                elements = self.driver.find_elements(By.XPATH, selector)
                for element in elements:
                    if element.is_displayed():
                        element_text = element.text.strip()
                        print(f"Found potential checkout button: '{element_text}'")
                        
                        # Verify it's likely a checkout button
                        checkout_keywords = ['checkout', 'proceed', 'continue', 'next']
                        if any(keyword in element_text.lower() for keyword in checkout_keywords) or selector in checkout_selectors[:3]:
                            
                            self.driver.execute_script("arguments[0].scrollIntoView(true);", element)
                            time.sleep(1)
                            self.driver.execute_script("arguments[0].click();", element)
                            print(f"Clicked checkout button: '{element_text}'")
                            time.sleep(5)
                            
                            # Get current URL after checkout
                            checkout_url = self.driver.current_url
                            print(f"Checkout page URL: {checkout_url}")
                            return checkout_url
                            
            except Exception as e:
                print(f"Error with checkout selector {selector}: {e}")
                continue
        
        print("Checkout button not found")
        return None
    
    def select_cash_on_delivery(self):
        """Select Cash on Delivery payment option in iframe"""
        print("Looking for Cash on Delivery option...")
        
        # Wait for payment page to load
        time.sleep(8)
        
        # Find the payment iframe
        iframe_element = self._find_payment_iframe()
        if not iframe_element:
            print("No payment iframe found")
            return False
        
        # Switch to iframe context
        if not self._switch_to_iframe():
            print("Could not switch to iframe")
            return False
        
        # Wait for iframe content to load
        self._wait_for_iframe_content()
        
        # Find and click COD option
        cod_clicked = self._find_and_click_cod()
        
        # Return to main page
        self.driver.switch_to.default_content()
        
        if cod_clicked:
            print("Cash on Delivery selected successfully")
            return True
        else:
            print("Could not find or click COD option")
            return False
    
    def _find_payment_iframe(self):
        """Find the BigBasket payment iframe"""
        iframe_locations = [
            "//iframe[@name='HyperServices']",
            "//div[@id='sdkTarget']//iframe",
            "//iframe[contains(@src,'juspay')]"
        ]
        
        # Try multiple times with delays
        for attempt in range(3):
            for location in iframe_locations:
                try:
                    iframes = self.driver.find_elements(By.XPATH, location)
                    if iframes:
                        print(f"Found payment iframe: {location}")
                        return iframes[0]
                except:
                    continue
            
            if attempt < 2:
                time.sleep(3)
        
        print("No payment iframe found")
        return None
    
    def _switch_to_iframe(self):
        """Switch to the payment iframe"""
        # Method 1: Switch by name (most reliable for BigBasket)
        try:
            self.driver.switch_to.frame("HyperServices")
            return True
        except:
            pass
        
        # Method 2: Switch by index (fallback)
        try:
            self.driver.switch_to.frame(0)
            return True
        except:
            pass
        
        print("Could not switch to iframe")
        return False
    
    def _wait_for_iframe_content(self):
        """Wait for iframe content to fully load"""
        time.sleep(10)
    
    def _debug_iframe_content(self):
        """Take screenshot for debugging if needed"""
        try:
            self.driver.save_screenshot("payment_iframe_debug.png")
        except:
            pass
    
    def _find_and_click_cod(self):
        """Find and click the Cash on Delivery option"""
        # Key COD patterns that work
        cod_patterns = [
            "//*[contains(translate(text(),'ABCDEFGHIJKLMNOPQRSTUVWXYZ','abcdefghijklmnopqrstuvwxyz'),'cash on delivery')]",
            "//div[contains(text(),'Cash on Delivery')]",
            "//span[contains(text(),'Cash on Delivery')]",
            "//input[@type='radio'][@value='cod']",
            "//input[@type='radio'][contains(@value,'cash')]"
        ]
        
        # Try each pattern
        for pattern in cod_patterns:
            try:
                elements = self.driver.find_elements(By.XPATH, pattern)
                for element in elements:
                    if self._is_cod_element(element) and self._click_element(element):
                        print("COD option clicked successfully")
                        return True
            except:
                continue
        
        print("No COD option found")
        return False
    
    def _is_cod_element(self, element):
        """Check if an element is likely the COD option"""
        try:
            if not element.is_displayed():
                return False
            
            text = element.text.strip().lower()
            value = (element.get_attribute('value') or '').lower()
            
            cod_keywords = ['cash on delivery', 'cod', 'cash']
            return any(keyword in text or keyword in value for keyword in cod_keywords)
            
        except:
            return False
    
    def _click_element(self, element):
        """Try to click an element using multiple methods"""
        # Method 1: JavaScript click (most reliable for iframes)
        try:
            self.driver.execute_script("arguments[0].scrollIntoView(true);", element)
            time.sleep(1)
            self.driver.execute_script("arguments[0].click();", element)
            time.sleep(2)
            return True
        except:
            pass
        
        # Method 2: Regular click
        try:
            element.click()
            time.sleep(2)
            return True
        except:
            pass
        
        # Method 3: Action chains
        try:
            from selenium.webdriver.common.action_chains import ActionChains
            actions = ActionChains(self.driver)
            actions.move_to_element(element).click().perform()
            time.sleep(2)
            return True
        except:
            pass
        
        return False
    
    def proceed_with_payment(self):
        """Handle payment process - Cash on Delivery only"""
        print("Looking for Cash on Delivery payment option...")
        
        # Try to select Cash on Delivery
        cod_selected = self.select_cash_on_delivery()
        
        if cod_selected:
            print("Cash on Delivery selected successfully")
            return "cod_selected"
        else:
            print("Could not find or select Cash on Delivery option")
            return "cod_failed"
    
    def get_upi_payment_link(self):
        """Extract UPI payment link"""
        print("Looking for UPI payment link...")
        
        # Wait for UPI interface to load
        time.sleep(5)
        
        try:
            # Look for UPI link in various formats
            upi_link_selectors = [
                "//a[starts-with(@href,'upi://')]",
                "//input[contains(@value,'upi://')]",
                "//span[contains(text(),'upi://')]",
                "//div[contains(text(),'upi://')]"
            ]
            
            for selector in upi_link_selectors:
                try:
                    elements = self.driver.find_elements(By.XPATH, selector)
                    for element in elements:
                        if element.is_displayed():
                            # Try to get UPI link from different attributes
                            upi_link = element.get_attribute('href') or element.get_attribute('value') or element.text
                            if upi_link and 'upi://' in upi_link:
                                print(f"Found UPI link: {upi_link}")
                                return upi_link
                except:
                    continue
            
            # If no direct UPI link found, return current URL for manual payment
            current_url = self.driver.current_url
            print(f"UPI link not found, payment page URL: {current_url}")
            return current_url
            
        except Exception as e:
            print(f"Error getting UPI link: {e}")
            return self.driver.current_url
    
    def place_order(self):
        """Click the Place Order button"""
        print("Looking for Place Order button...")
        
        # Try main page first
        if self._find_and_click_place_order_main():
            return self.driver.current_url
        
        # Then check payment iframe
        if self._find_and_click_place_order_iframe():
            return self.driver.current_url
        
        print("Place Order button not found")
        return None
    
    def _find_and_click_place_order_main(self):
        """Look for Place Order button on main page"""
        place_order_selectors = [
            "//button[contains(text(),'Place Order')]",
            "//button[contains(text(),'Confirm Order')]",
            "//button[contains(text(),'Proceed to Pay')]",
            "//button[@type='submit'][contains(@class,'btn')]"
        ]
        
        for selector in place_order_selectors:
            try:
                elements = self.driver.find_elements(By.XPATH, selector)
                for element in elements:
                    if element.is_displayed():
                        element_text = element.text.strip()
                        order_keywords = ['place', 'order', 'confirm', 'proceed', 'pay']
                        if any(keyword in element_text.lower() for keyword in order_keywords):
                            if self._click_element(element):
                                print(f"Clicked Place Order button: {element_text}")
                                time.sleep(5)
                                return True
            except:
                continue
        
        return False
    
    def _find_and_click_place_order_iframe(self):
        """Look for Place Order button inside payment iframe"""
        if not self._switch_to_iframe():
            return False
        
        try:
            # Wait for iframe to update after COD selection
            time.sleep(8)
            
            # Take screenshot for debugging
            try:
                self.driver.save_screenshot("place_order_iframe_debug.png")
            except:
                pass
            
            # Key Place Order selectors that work
            iframe_order_selectors = [
                "//*[contains(translate(text(),'ABCDEFGHIJKLMNOPQRSTUVWXYZ','abcdefghijklmnopqrstuvwxyz'),'place order')]",
                "//button[contains(text(),'Place Order')]",
                "//button[@type='submit']",
                "//div[@role='button'][contains(text(),'Place')]",
                "//button[contains(@class,'submit')]"
            ]
            
            # Try each selector
            for selector in iframe_order_selectors:
                try:
                    elements = self.driver.find_elements(By.XPATH, selector)
                    for element in elements:
                        if element.is_displayed():
                            element_text = element.text.strip()
                            order_indicators = ['place', 'order', 'confirm', 'proceed', 'pay', 'submit']
                            
                            if (any(word in element_text.lower() for word in order_indicators) or 
                                element.get_attribute('type') == 'submit'):
                                
                                if self._click_element(element):
                                    print(f"Place Order clicked in iframe: {element_text}")
                                    time.sleep(5)
                                    self.driver.switch_to.default_content()
                                    return True
                except:
                    continue
            
        finally:
            try:
                self.driver.switch_to.default_content()
            except:
                pass
        
        # Check if order was placed automatically
        current_url = self.driver.current_url
        if any(keyword in current_url.lower() for keyword in ['success', 'confirm', 'order-details', 'track-order']):
            print("Order placed automatically after COD selection")
            return True
        
        return False
       
    
    def run_automation(self, product_name, payment_choice="COD", quantity=1):
        """Main automation workflow"""
        print(f"Starting BigBasket automation... (quantity: {quantity})")
        
        try:
            # Try to load existing session first
            if self.load_session() and self.is_logged_in():
                print("Using existing session")
            else:
                print("Existing session invalid, logging in...")
                if not self.login_with_otp():
                    print("Login failed")
                    return False
            
            # Clear cart first to ensure clean start (if enabled)
            if CLEAR_CART_FIRST:
                print("Clearing cart before adding new products...")
                try:
                    cart_cleared = self.clear_cart()
                    if cart_cleared:
                        print("Cart clearing completed")
                    else:
                        print("Cart clearing had issues, but continuing with automation...")
                except Exception as e:
                    print(f"Cart clearing failed with error: {e}")
                    print("Continuing with automation anyway...")
            else:
                print("Skipping cart clearing (disabled in configuration)")
            
            # Search for product
            if not self.search_product(product_name):
                print("Product search failed")
                return False
            
            # Try to add product to cart
            print(f"Attempting to add product to cart (quantity: {quantity})...")
            if self.add_to_cart(product_index=0, quantity=quantity):
                print(f"Product added to cart successfully (quantity: {quantity})")
            else:
                print("Add to cart button not found for target product")
                print("This might mean:")
                print("1. Target product is out of stock")
                print("2. Target product is not available")
                print("3. Product name doesn't match exactly")
                
                # Get alternative products
                alternatives = self.get_alternative_products()
                
                if alternatives:
                    print(f"\nFound {len(alternatives)} alternative products (shown above)")
                    print("Please review the alternatives and restart the automation with your preferred product name.")
                    print("Closing browser for your review...")
                    
                    # Close browser after showing alternatives
                    self.close()
                    
                    return {
                        'status': 'alternatives_found',
                        'alternatives': alternatives,
                        'message': 'Target product not available. Please review alternatives and restart.'
                    }
                else:
                    print("No alternative products found")
                    print("This might be due to:")
                    print("- No products on current search results page")
                    print("- Different page structure than expected")
                    print("- Need to try different search terms")
                    
                    user_choice = input("\nWould you like to:\n1. Continue anyway (manual addition)\n2. Exit and try different search terms\nEnter choice (1/2): ").strip()
                    
                    if user_choice == "2":
                        print("Exiting for different search terms...")
                        self.close()
                        return {
                            'status': 'exit_for_new_search',
                            'message': 'User chose to exit and try different search terms'
                        }
                    else:
                        print("Continuing with manual addition...")
                        input("Please manually add the product to cart and press Enter to continue...")
            
            # Go to cart by clicking basket button
            cart_success = self.go_to_cart()
            if not cart_success:
                print("Basket button click had issues, but continuing to look for checkout...")
                # Continue anyway, might already be on cart page or popup appeared
            
            # Wait a bit more for any popups/modals to load
            time.sleep(3)
            
            # Proceed to checkout
            checkout_url = self.proceed_to_checkout()
            if checkout_url:
                print(f"SUCCESS: Reached checkout page: {checkout_url}")
                
                # Wait for checkout page to fully load
                print("Waiting for checkout page to fully load...")
                time.sleep(5)
                
                # Extract and display order summary
                order_details = self.get_order_summary()
                self.display_order_summary(order_details)
                
                # Ask user for payment method preference
                print(f"\nPayment Method: {payment_choice}")

                if payment_choice == "COD":
                    print("Proceeding with Cash on Delivery...")
                    print("Please wait while payment options are loading...")
                    
                    # Add extra wait before attempting payment selection
                    time.sleep(3)
                    
                    # Select COD payment method
                    payment_result = self.proceed_with_payment()
                    
                    if payment_result == "cod_selected":
                        print("Cash on Delivery selected successfully!")
                        
                        # Ask final confirmation before placing order
                        print(f"\nFinal Order Confirmation:")
                        print(f"Payment Method: Cash on Delivery")
                        print(f"Total Amount: {order_details.get('total_payable', 'Unknown')}")
                        
                        final_confirm = input("\nDo you want to PLACE THE ORDER? (yes/no): ").lower().strip()
                        
                        if final_confirm in ['yes', 'y']:
                            print("Placing order with Cash on Delivery...")
                            order_url = self.place_order()
                            
                            if order_url:
                                return {
                                    'status': 'order_placed',
                                    'payment_method': 'cod',
                                    'checkout_url': checkout_url,
                                    'order_url': order_url,
                                    'order_details': order_details
                                }
                            else:
                                return {
                                    'status': 'cod_selected_no_order',
                                    'payment_method': 'cod',
                                    'checkout_url': checkout_url,
                                    'order_details': order_details
                                }
                        else:
                            print("Order not placed. COD selected but user cancelled.")
                            return {
                                'status': 'cod_selected_cancelled',
                                'payment_method': 'cod',
                                'checkout_url': checkout_url,
                                'order_details': order_details
                            }
                    else:
                        print("Could not select Cash on Delivery option")
                     
                        return {
                            'status': 'cod_failed',
                            'checkout_url': checkout_url,
                            'order_details': order_details
                        }
                
                elif payment_choice == 'CHECKOUT_ONLY':
                    print("User chose not to proceed with any payment")
                    return {
                        'status': 'checkout_only',
                        'checkout_url': checkout_url,
                        'order_details': order_details
                    }
            else:
                print("Checkout button not found, but basket was clicked successfully")
                current_url = self.driver.current_url
                print(f"Current page URL: {current_url}")
                
                # If we're on a cart-related page, consider it a partial success
                if 'basket' in current_url or 'cart' in current_url or 'checkout' in current_url:
                    print("We are on a cart/checkout related page!")
                    return {
                        'status': 'cart_page',
                        'checkout_url': current_url
                    }
                else:
                    print("Not on expected cart/checkout page")
                    return False
                
        except Exception as e:
            print(f"Automation error: {e}")
            return False
    
    def close(self):
        """Clean up and close browser"""
        if self.driver:
            self.driver.quit()
            print("Browser closed")
            self.driver = None

    def close_browser(self):
        """Close the browser session cleanly."""
        try:
            if self.driver:
                self.driver.quit()
                print("Browser session closed.")
                self.driver = None
                return True
            else:
                print("No browser session to close.")
                return False
        except Exception as e:
            print(f"Error closing browser: {e}")
            return False

# Usage example
if __name__ == "__main__":
    # Use the configuration setting for headless mode
    automation = BigBasketAutomation(headless=HEADLESS_MODE)
    
    try:
        # Run automation for a specific product
        product_to_search = "Amul Taaza Milk, 500 ml"
        result = automation.run_automation(product_to_search, quantity=6)
        
        if result:
            print(f"\nAutomation completed successfully!")
            
            if isinstance(result, dict):
                print(f"Status: {result['status']}")
                print(f"Checkout URL: {result.get('checkout_url', 'N/A')}")
                
                # Handle different status types
                if result['status'] == 'order_placed':
                    print("ORDER SUCCESSFULLY PLACED!")
                    print(f"Payment Method: {result.get('payment_method', 'Unknown').upper()}")
                    print(f"Order Confirmation URL: {result.get('order_url', 'N/A')}")
                    if result.get('payment_method') == 'cod':
                        print("Payment: Cash on Delivery")
                        print("Your order will be delivered and payment collected at your doorstep")
                
                elif result['status'] == 'cod_selected_no_order':
                    print("COD selected but order placement failed")
                    print("You may need to manually click 'Place Order' button")
                
                elif result['status'] == 'cod_selected_cancelled':
                    print("Order cancelled by user after COD selection")
                
                elif result['status'] == 'cod_failed':
                    print("Could not select Cash on Delivery option")
                
                # Show order total
                if result.get('order_details'):
                    order = result['order_details']
                    total = order.get('total_payable') or order.get('total')
                    if total:
                        print(f"Order Total: {total}")
            else:
                print(f"Result: {result}")
        else:
            print("Automation failed")
            print("No valid checkout URL found")
        # Keep browser open for manual inspection
        input("Press Enter to close browser...")
        
    except KeyboardInterrupt:
        print("Automation interrupted by user")
    except Exception as e:
        print(f"Unexpected error: {e}")
    finally:
        automation.close()