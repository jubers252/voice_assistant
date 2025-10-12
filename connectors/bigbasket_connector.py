"""
BigBasket LangChain Tools
Simple tools for LangChain agent integration
Agent controls browser lifecycle - browser stays open between tools
Agent decides when to close browser using close_browser() tool
"""

import time

from bigbasket_raw import BigBasketAutomation

class BigBasketTools:
    def __init__(self, headless=True):
        """
        Initialize BigBasket tools for LangChain agent
        Args:
            headless (bool): Run browser in headless mode (default: True)
        """
        self.headless = headless
        self.automation = None  # Persistent automation instance
        self.session_active = False
        print(f"BigBasket Tools initialized (headless: {headless})")
    
    def _ensure_automation_ready(self):
        """Ensure automation instance is ready (create if needed)"""
        if not self.automation:
            self.automation = BigBasketAutomation(headless=self.headless)
            print("Browser session started")
        return self.automation is not None
    
    # ============================================================================
    # LANGCHAIN TOOLS - Simple Individual Actions
    # ============================================================================
    
    def login_to_bigbasket(self):
        """
        Tool: Login to BigBasket
        Returns: {'status': 'success'/'failed', 'method': 'session'/'otp'}
        """
        print("TOOL: LOGIN")
        
        if not self._ensure_automation_ready():
            return {'status': 'failed', 'error': 'Failed to initialize browser'}
        
        try:
            # Try session first
            if self.automation.load_session() and self.automation.is_logged_in():
                print("Login successful using session")
                self.session_active = True
                return {'status': 'success', 'method': 'session'}
            else:
                # Try OTP
                print("Session invalid, trying OTP...")
                if self.automation.login_with_otp():
                    print("Login successful using OTP")
                    self.session_active = True
                    return {'status': 'success', 'method': 'otp'}
                else:
                    print("Login failed")
                    return {'status': 'failed', 'method': 'both_failed'}
            
        except Exception as e:
            print(f"Login error: {e}")
            return {'status': 'failed', 'error': str(e)}
    
    def clear_cart(self):
        """
        Tool: Clear BigBasket cart
        Returns: {'status': 'success'/'failed', 'cart_cleared': bool}
        """
        print("TOOL: CLEAR CART")
        
        if not self._ensure_automation_ready():
            return {'status': 'failed', 'error': 'Failed to initialize browser'}
        
        try:
            # Check login status
            if not self.session_active:
                if not (self.automation.load_session() and self.automation.is_logged_in()):
                    return {'status': 'failed', 'error': 'Please login first using login_to_bigbasket()'}
            
            # Clear cart
            cart_cleared = self.automation.clear_cart()
            
            if cart_cleared:
                print("Cart cleared successfully")
                return {'status': 'success', 'cart_cleared': True}
            else:
                print("Cart clearing completed (may have been empty)")
                return {'status': 'success', 'cart_cleared': True}
            
        except Exception as e:
            print(f"Clear cart error: {e}")
            return {'status': 'failed', 'error': str(e)}
    
    def add_product_to_cart(self, product_name, quantity=1):
        """
        Tool: Search and add product to cart
        Args: 
            product_name (str): Product to search and add
            quantity (int): Quantity to add (default: 1)
        Returns: {'status': 'success'/'alternatives'/'failed', 'product_added': bool, 'alternatives': list}
        """
        print(f"TOOL: ADD TO CART")
        print(f"Product: {product_name}, Quantity: {quantity}")
        
        if not self._ensure_automation_ready():
            return {'status': 'failed', 'error': 'Failed to initialize browser'}
        
        try:
            # Check login status
            if not self.session_active:
                if not (self.automation.load_session() and self.automation.is_logged_in()):
                    return {'status': 'failed', 'error': 'Please login first using login_to_bigbasket()'}
            
            # Search product
            if not self.automation.search_product(product_name):
                return {'status': 'failed', 'error': 'Product search failed'}
            
            # Use the new approach: increment quantity on product listing page
            if self.automation.add_to_cart(quantity):
                print(f"Product added to cart (quantity: {quantity})")
                return {'status': 'success', 'product_added': True, 'quantity_added': quantity}
            
            # If we reach here, no products were added
            print("Product not found, getting alternatives...")
            alternatives = self.automation.get_alternative_products()
            if alternatives:
                return {
                    'status': 'alternatives',
                    'product_added': False,
                    'alternatives': alternatives[:5]
                }
            else:
                return {'status': 'failed', 'error': 'Product not found'}
            
        except Exception as e:
            print(f"Add to cart error: {e}")
            return {'status': 'failed', 'error': str(e)}
    
    def add_multiple_products(self, products_string):
        """
        Tool: Add multiple products to cart in one operation
        Args: products_string (str): Format "product1:qty1,product2:qty2,product3:qty3"
        Returns: {'status': 'success'/'partial'/'failed', 'results': list, 'summary': dict}
        """
        print(f"TOOL: ADD MULTIPLE PRODUCTS")
        print(f"Products string: {products_string}")
        
        if not self._ensure_automation_ready():
            return {'status': 'failed', 'error': 'Failed to initialize browser'}
        
        try:
            # Check login status
            if not self.session_active:
                if not (self.automation.load_session() and self.automation.is_logged_in()):
                    return {'status': 'failed', 'error': 'Please login first using login_to_bigbasket()'}
            
            # Parse the products string
            try:
                products_list = []
                items = products_string.split(',')
                
                for item in items:
                    if ':' in item:
                        product_name, qty_str = item.split(':', 1)
                        product_name = product_name.strip()
                        try:
                            quantity = int(qty_str.strip())
                        except ValueError:
                            quantity = 1
                    else:
                        product_name = item.strip()
                        quantity = 1
                    
                    if product_name:
                        products_list.append({'name': product_name, 'quantity': quantity})
                
                print(f"Parsed {len(products_list)} products: {products_list}")
                
            except Exception as e:
                return {'status': 'failed', 'error': f'Failed to parse products string: {str(e)}'}
            
            if not products_list:
                return {'status': 'failed', 'error': 'No valid products found in input'}
            
            # Add each product
            results = []
            successful_adds = 0
            failed_adds = 0
            
            for i, product_info in enumerate(products_list):
                product_name = product_info['name']
                quantity = product_info['quantity']
                
                print(f"\nAdding product {i+1}/{len(products_list)}: {product_name} (qty: {quantity})")
                
                try:
                    # Search product
                    if not self.automation.search_product(product_name):
                        result = {
                            'product': product_name,
                            'quantity': quantity,
                            'status': 'search_failed',
                            'message': 'Product search failed'
                        }
                        results.append(result)
                        failed_adds += 1
                        continue
                    
                    # Use the new quantity approach on product listing page
                    if self.automation.add_to_cart(product_index=0, quantity=quantity):
                        result = {
                            'product': product_name,
                            'quantity': quantity,
                            'status': 'added',
                            'message': f'Successfully added {quantity} units'
                        }
                        results.append(result)
                        successful_adds += 1
                        print(f"Added {product_name} (qty: {quantity})")
                    else:
                        # Get alternatives if product not found
                        alternatives = self.automation.get_alternative_products()
                        result = {
                            'product': product_name,
                            'quantity': quantity,
                            'status': 'not_found',
                            'message': 'Product not found',
                            'alternatives': alternatives[:3] if alternatives else []
                        }
                        results.append(result)
                        failed_adds += 1
                        print(f"✗ Could not add {product_name}")
                
                except Exception as e:
                    result = {
                        'product': product_name,
                        'quantity': quantity,
                        'status': 'error',
                        'message': f'Error: {str(e)}'
                    }
                    results.append(result)
                    failed_adds += 1
                    print(f"✗ Error adding {product_name}: {e}")
                
                # Small delay between products
                time.sleep(1)
            
            # Determine overall status
            if successful_adds == len(products_list):
                status = 'success'
            elif successful_adds > 0:
                status = 'partial'
            else:
                status = 'failed'
            
            summary = {
                'total_products': len(products_list),
                'successful': successful_adds,
                'failed': failed_adds,
                'success_rate': f"{(successful_adds/len(products_list))*100:.1f}%"
            }
            
            return {
                'status': status,
                'results': results,
                'summary': summary
            }
            
        except Exception as e:
            print(f"Multiple products error: {e}")
            return {'status': 'failed', 'error': str(e)}
    
    def proceed_to_checkout(self):
        """
        Tool: Go to cart and proceed to checkout
        Returns: {'status': 'success'/'failed', 'checkout_url': str, 'order_summary': dict}
        """
        print("TOOL: PROCEED TO CHECKOUT")
        
        if not self._ensure_automation_ready():
            return {'status': 'failed', 'error': 'Failed to initialize browser'}
        
        try:
            # Check login status
            if not self.session_active:
                if not (self.automation.load_session() and self.automation.is_logged_in()):
                    return {'status': 'failed', 'error': 'Please login first using login_to_bigbasket()'}
            
            # Go to cart
            if not self.automation.go_to_cart():
                print("Cart navigation had issues, but continuing...")
            
            # Proceed to checkout
            checkout_url = self.automation.proceed_to_checkout()
            
            if checkout_url:
                print("Reached checkout page")
                # Get order summary
                time.sleep(3)
                order_summary = self.automation.get_order_summary()
                self.automation.display_order_summary(order_summary)
                
                return {
                    'status': 'success',
                    'checkout_url': checkout_url,
                    'order_summary': order_summary
                }
            else:
                return {'status': 'failed', 'error': 'Could not reach checkout'}
            
        except Exception as e:
            print(f"Checkout error: {e}")
            return {'status': 'failed', 'error': str(e)}
    
    def place_order_cod(self):
        """
        Tool: Select COD and place order
        Returns: {'status': 'success'/'failed', 'order_placed': bool, 'order_url': str}
        """
        print("TOOL: PLACE ORDER COD")
        
        if not self._ensure_automation_ready():
            return {'status': 'failed', 'error': 'Failed to initialize browser'}
        
        try:
            # Check login status
            if not self.session_active:
                if not (self.automation.load_session() and self.automation.is_logged_in()):
                    return {'status': 'failed', 'error': 'Please login first using login_to_bigbasket()'}
            
            # Navigate to checkout if not already there
            if not self.automation.go_to_cart():
                print("Cart navigation had issues...")
            
            checkout_url = self.automation.proceed_to_checkout()
            if not checkout_url:
                print("Trying to select COD anyway...")
            
            # Select COD
            payment_result = self.automation.proceed_with_payment()
            
            if payment_result != "cod_selected":
                return {'status': 'failed', 'error': 'Could not select COD'}
            
            print("COD selected")
            
            # Place order
            order_url = self.automation.place_order()
            
            if order_url:
                print("Order placed successfully!")
                return {
                    'status': 'success',
                    'order_placed': True,
                    'order_url': order_url
                }
            else:
                return {
                    'status': 'cod_selected',
                    'order_placed': False,
                    'message': 'COD selected but order needs manual confirmation'
                }
            
        except Exception as e:
            print(f"Place order error: {e}")
            return {'status': 'failed', 'error': str(e)}
    
    
    def search_product_info(self, product_name):
        """
        Tool: Search and get product information only
        Args: product_name (str): Product to search for
        Returns: {'status': 'success'/'failed', 'alternatives': list}
        """
        print(f"TOOL: SEARCH PRODUCT INFO")
        print(f"Product: {product_name}")
        
        if not self._ensure_automation_ready():
            return {'status': 'failed', 'error': 'Failed to initialize browser'}
        
        try:
            # Check login status
            if not self.session_active:
                if not (self.automation.load_session() and self.automation.is_logged_in()):
                    return {'status': 'failed', 'error': 'Please login first using login_to_bigbasket()'}
            
            # Search product
            if not self.automation.search_product(product_name):
                return {'status': 'failed', 'error': 'Product search failed'}
            
            # Get alternatives (shows available products)
            alternatives = self.automation.get_alternative_products()
            
            if alternatives:
                return {
                    'status': 'success',
                    'alternatives': alternatives[:10]  # Show top 10
                }
            else:
                return {'status': 'failed', 'error': 'No products found'}
            
        except Exception as e:
            print(f"Search error: {e}")
            return {'status': 'failed', 'error': str(e)}
    
    def close_browser(self):
        """
        Tool: Close browser when agent decides it's time
        Returns: {'status': 'success'/'failed', 'message': str}
        """
        print("TOOL: CLOSE BROWSER")
        
        try:
            if self.automation:
                # Force close the browser driver
                if hasattr(self.automation, 'driver') and self.automation.driver:
                    self.automation.driver.quit()
                    print("Browser driver quit successfully")
                
                # Call the close_browser method if it exists
                if hasattr(self.automation, 'close_browser'):
                    self.automation.close_browser()
                
                self.automation = None
                self.session_active = False
                print("Browser closed successfully")
                return {
                    'status': 'success',
                    'message': 'Browser session ended'
                }
            else:
                return {
                    'status': 'success',
                    'message': 'Browser was already closed'
                }
                
        except Exception as e:
            print(f"Close browser error: {e}")
            # Force cleanup even on error
            try:
                if self.automation and hasattr(self.automation, 'driver') and self.automation.driver:
                    self.automation.driver.quit()
            except:
                pass
            self.automation = None
            self.session_active = False
            return {
                'status': 'failed',
                'error': str(e),
                'message': 'Browser session reset due to error'
            }

# ============================================================================
# LANGCHAIN USAGE EXAMPLES
# ============================================================================

def demo_langchain_tools():
    """Demo showing how LangChain agent would use individual tools with browser control"""
    print("BIGBASKET LANGCHAIN TOOLS DEMO")
    print("Agent has full control over browser lifecycle")
    
    tools = BigBasketTools(headless=False)  # Set to True for actual LangChain use
    
    try:
        print("\n1. Agent Tool: Login (starts browser)")
        result1 = tools.login_to_bigbasket()
        print(f"Login Result: {result1}")
        result3 = tools.clear_cart()
        print(f"Clear Cart Result: {result3}")
        print("\n2. Agent Tool: Search Product Info (browser stays open)")
        'add_multiple|milk:2,bread:1,eggs:6'
        result2 = tools.add_multiple_products("mccains:2,toast:3")
        print(f"Clear Cart Result: {result2}")
        
        # print("\n3. Agent Tool: Add Product (browser stays open)")
        # result3 = tools.add_product_to_cart("milk")
        # print(f"Add Product Result: {result3}")
                
        # print("\n5. Agent Tool: Checkout (browser stays open)")
        # result5 = tools.proceed_to_checkout()
        # print(f"Checkout Result: {result5}")
        
        # print("\n6. Agent Tool: Place COD Order (browser stays open)")
        # result6 = tools.place_order_cod()
        # print(f"Place Order Result: {result6}")
        
        print("\n7. Agent Tool: Close Browser (agent decides when)")
        result7 = tools.close_browser()
        print(f"Close Browser Result: {result7}")
        
    except Exception as e:
        print(f"Demo error: {e}")
    finally:
        # Ensure cleanup
        if tools.automation:
            tools.close_browser()

if __name__ == "__main__":
    # Demo the individual tools with agent-controlled browser lifecycle
    demo_langchain_tools()