"""
Amazon India Order Scraper
===========================
A simple, independent script that fetches and parses Amazon India order history.

Features:
- Uses amazon-orders library for authentication
- Fetches order pages from Amazon India (.in domain)
- Parses orders using custom logic for Indian Amazon structure
- Saves results to JSON with detailed summary

Usage:
    python amazon_india_scraper.py

Requirements:
    - amazon-orders library
    - beautifulsoup4
    - config.py with user_id and user_password
"""

import os
import re
import json
import time
import pickle
import sys
from datetime import datetime, timedelta
from typing import List, Dict, Any, Optional
from bs4 import BeautifulSoup

# Add current directory to Python path for imports
current_dir = os.path.dirname(os.path.abspath(__file__))
if current_dir not in sys.path:
    sys.path.insert(0, current_dir)

# Amazon orders library
from amazonorders.session import AmazonSession
from amazonorders.conf import AmazonOrdersConfig
from dotenv import load_dotenv

load_dotenv()

class AmazonIndiaScraper:
    """
    Advanced Amazon India order scraper with flexible date filtering
    
    Supports multiple date filtering options:
    - Latest month orders
    - Specific date range
    - Custom year filtering
    - Last N days/weeks/months
    """
    
    def __init__(self, username: str, password: str, debug: bool = True):
        self.username = username
        self.password = password
        self.debug = debug
        self.session = None
        self.output_dir = "output"
        self.session_file = os.path.join(self.output_dir, "amazon_session.pkl")
        
        # Ensure output directory exists
        os.makedirs(self.output_dir, exist_ok=True)
    
    def _is_within_days(self, date_str: str, days: int) -> bool:
        """
        Check if a date string falls within the last N days.
        
        Args:
            date_str: Date string from order (various formats)
            days: Number of days to check against
            
        Returns:
            bool: True if date is within the last N days, False otherwise
        """
        if not date_str:
            return False
        
        try:
            # Parse different date formats that Amazon India uses
            date_formats = [
                "%d %B %Y",     # "17 September 2025"
                "%d %b %Y",     # "17 Sep 2025"
                "%d/%m/%Y",     # "17/09/2025"
                "%Y-%m-%d",     # "2025-09-17"
                "%d-%m-%Y",     # "17-09-2025"
            ]
            
            parsed_date = None
            for date_format in date_formats:
                try:
                    parsed_date = datetime.strptime(date_str.strip(), date_format)
                    break
                except ValueError:
                    continue
            
            if not parsed_date:
                # If we can't parse the date, assume it's too old
                return False
            
            # Calculate the cutoff date (N days ago from today)
            cutoff_date = datetime.now() - timedelta(days=days)
            
            # Check if the order date is after the cutoff
            return parsed_date >= cutoff_date
            
        except Exception as e:
            if self.debug:
                print(f"Date parsing error for '{date_str}': {e}")
            return False
    
    def _save_session(self) -> bool:
        """
        Save the current authenticated session to a file.
        
        Returns:
            bool: True if session saved successfully, False otherwise
        """
        try:
            if self.session and self.session.is_authenticated:
                session_data = {
                    'cookies': self.session.session.cookies,
                    'username': self.username,
                    'saved_at': datetime.now().isoformat(),
                    'expires_at': (datetime.now() + timedelta(hours=24)).isoformat()  # Assume 24h expiry
                }
                
                with open(self.session_file, 'wb') as f:
                    pickle.dump(session_data, f)
                
                if self.debug:
                    print(f"Session saved to {self.session_file}")
                return True
        except Exception as e:
            if self.debug:
                print(f"Failed to save session: {e}")
        return False
    
    def _load_session(self) -> bool:
        """
        Load a previously saved session from file.
        
        Returns:
            bool: True if session loaded and is valid, False otherwise
        """
        try:
            if not os.path.exists(self.session_file):
                if self.debug:
                    print("No saved session file found")
                return False
            
            with open(self.session_file, 'rb') as f:
                session_data = pickle.load(f)
            
            # Check if session is expired
            expires_at = datetime.fromisoformat(session_data.get('expires_at', ''))
            if datetime.now() > expires_at:
                if self.debug:
                    print("Saved session has expired")
                os.remove(self.session_file)  # Remove expired session
                return False
            
            # Check if session is for the same username
            if session_data.get('username') != self.username:
                if self.debug:
                    print("Saved session is for different username")
                return False
            
            # Try to restore the session
            # Configure for Amazon India with custom constants and selectors
            # Try different import paths for compatibility
            config_data = {}
            
            try:
                # When called from voice assistant
                from connectors.amazon_in_constants import AmazonInConstants
                from connectors.amazon_in_selectors import AmazonInSelectors
                config_data = {
                    "constants_class": "connectors.amazon_in_constants.AmazonInConstants",
                    "selectors_class": "connectors.amazon_in_selectors.AmazonInSelectors",
                    "max_auth_attempts": 3,
                    "output_dir": self.output_dir
                }
            except ImportError:
                try:
                    # When run directly
                    from amazon_in_constants import AmazonInConstants
                    from amazon_in_selectors import AmazonInSelectors
                    config_data = {
                        "constants_class": "amazon_in_constants.AmazonInConstants",
                        "selectors_class": "amazon_in_selectors.AmazonInSelectors",
                        "max_auth_attempts": 3,
                        "output_dir": self.output_dir
                    }
                except ImportError:
                    # Fallback to basic configuration
                    config_data = {
                        "base_url": "https://www.amazon.in",
                        "max_auth_attempts": 3,
                        "output_dir": self.output_dir
                    }
            
            amazon_config = AmazonOrdersConfig(data=config_data)
            self.session = AmazonSession(self.username, self.password, config=amazon_config, debug=self.debug)
            
            # Restore cookies
            self.session.session.cookies = session_data['cookies']
            
            # Test if session is still valid
            if self._validate_session():
                if self.debug:
                    print("Successfully loaded and validated saved session")
                return True
            else:
                if self.debug:
                    print("Loaded session is no longer valid")
                os.remove(self.session_file)  # Remove invalid session
                return False
                
        except Exception as e:
            if self.debug:
                print(f"Failed to load session: {e}")
            if os.path.exists(self.session_file):
                os.remove(self.session_file)  # Remove corrupted session file
        return False
    
    def _validate_session(self) -> bool:
        """
        Validate if the current session is still authenticated and working.
        
        Returns:
            bool: True if session is valid, False otherwise
        """
        try:
            if not self.session:
                return False
            
            # Try to access a protected page to test if session is valid
            test_url = "https://www.amazon.in/gp/your-account/order-history"
            response = self.session.get(test_url, persist_cookies=True)
            
            if response.response.ok:
                # Check if we're redirected to login page
                if "signin" in response.response.url or "login" in response.response.url:
                    return False
                
                # Check for elements that indicate we're logged in
                soup = BeautifulSoup(response.response.text, 'html.parser')
                
                # Look for order history elements or account-specific content
                if soup.find('div', class_='order') or soup.find('div', class_='a-box-group') or 'order-history' in response.response.text.lower():
                    self.session.is_authenticated = True
                    return True
                    
            return False
            
        except Exception as e:
            if self.debug:
                print(f"Session validation error: {e}")
            return False
    
    def login(self) -> bool:
        """
        Authenticate with Amazon India using saved session or fresh login.
        
        This function:
        1. First tries to load and validate a saved session
        2. If no valid session exists, performs fresh authentication
        3. Saves the session after successful login for future use
        4. Validates the authentication was successful
        
        Returns:
            bool: True if authentication successful, False otherwise
        """
        try:
            # First, try to load existing session
            print("Checking for saved session...")
            if self._load_session():
                print("Using saved session - no login required!")
                return True
            
            print("No valid saved session found, logging into Amazon India...")
            
            # Configure for Amazon India with custom constants and selectors
            # Try different import paths for compatibility
            config_data = {}
            
            # Try to determine the correct module path
            try:
                # When called from voice assistant
                from connectors.amazon_in_constants import AmazonInConstants
                from connectors.amazon_in_selectors import AmazonInSelectors
                config_data = {
                    "constants_class": "connectors.amazon_in_constants.AmazonInConstants",
                    "selectors_class": "connectors.amazon_in_selectors.AmazonInSelectors",
                    "max_auth_attempts": 3,
                    "output_dir": self.output_dir
                }
            except ImportError:
                try:
                    # When run directly
                    from amazon_in_constants import AmazonInConstants
                    from amazon_in_selectors import AmazonInSelectors
                    config_data = {
                        "constants_class": "amazon_in_constants.AmazonInConstants",
                        "selectors_class": "amazon_in_selectors.AmazonInSelectors",
                        "max_auth_attempts": 3,
                        "output_dir": self.output_dir
                    }
                except ImportError as e:
                    print(f"Warning: Could not import custom constants/selectors: {e}")
                    # Fallback to basic configuration
                    config_data = {
                        "base_url": "https://www.amazon.in",
                        "max_auth_attempts": 3,
                        "output_dir": self.output_dir
                    }
            
            amazon_config = AmazonOrdersConfig(data=config_data)
            self.session = AmazonSession(self.username, self.password, config=amazon_config, debug=self.debug)
            
            # Perform authentication with Amazon India
            self.session.login()
            
            if self.session.is_authenticated:
                print("Successfully logged into Amazon India!")
                
                # Save session for future use
                if self._save_session():
                    print("Session saved for future use")
                
                return True
            else:
                print("Login failed!")
                return False
                
        except Exception as e:
            print(f"Login error: {e}")
            return False
    
    def clear_saved_session(self) -> bool:
        """
        Clear any saved session file to force fresh login.
        
        Returns:
            bool: True if session file was removed or didn't exist, False on error
        """
        try:
            if os.path.exists(self.session_file):
                os.remove(self.session_file)
                print("Saved session cleared - next login will be fresh")
                return True
            else:
                print("No saved session to clear")
                return True
        except Exception as e:
            print(f"Error clearing saved session: {e}")
            return False
    
    def fetch_orders(self, days: int = 2) -> List[str]:
        """
        Fetch order history pages from Amazon India for the last N days.
        
        Args:
            days: Number of recent days to fetch orders for (default: 2)
            
        Returns:
            List[str]: Paths to saved HTML files
        """
        if not self.session or not self.session.is_authenticated:
            print("ERROR: Not authenticated!")
            return []
        
        # Build URL for last N days
        base_url = "https://www.amazon.in/gp/your-account/order-history"
        url = f"{base_url}?timeFilter=days-{days}"
        label = f"last_{days}_days"
        
        saved_files = []
        
        try:
            print(f"Fetching orders from last {days} days...")
            page = 0
            
            while url:
                print(f"  Processing page {page + 1}...")
                response = self.session.get(url, persist_cookies=True)
                
                if response.response.ok:
                    # Save HTML file with descriptive name
                    filename = f"orders_{label}_page_{page}.html"
                    filepath = os.path.join(self.output_dir, filename)
                    
                    with open(filepath, 'w', encoding='utf-8') as f:
                        f.write(response.response.text)
                    
                    saved_files.append(filepath)
                    print(f"    Saved: {filename}")
                    
                    # Check for next page using pagination
                    soup = BeautifulSoup(response.response.text, 'html.parser')
                    pagination = soup.find('ul', class_='a-pagination')
                    next_link = None
                    
                    if pagination:
                        next_item = pagination.find('li', class_='a-last')
                        if next_item and next_item.find('a'):
                            next_href = next_item.find('a')['href']
                            if next_href and 'startIndex=' in next_href:
                                next_link = f"https://www.amazon.in{next_href}"
                    
                    if next_link:
                        url = next_link
                        page += 1
                        time.sleep(2)  # Rate limiting - be respectful to Amazon servers
                    else:
                        print(f"  Completed last {days} days ({page + 1} pages total)")
                        break
                else:
                    print(f"    ERROR: Failed to fetch page (HTTP {response.response.status_code})")
                    break
        
        except Exception as e:
            print(f"ERROR: Failed to fetch orders: {e}")
        
        return saved_files
    
    def parse_orders(self, file_paths: List[str] = None, days_filter: int = None) -> List[Dict[str, Any]]:
        """
        Parse order information from saved HTML files.
        
        This function:
        1. Reads HTML files from the output directory
        2. Extracts order details using BeautifulSoup and regex patterns
        3. Applies client-side date filtering if days_filter is specified
        4. Removes duplicate orders based on price, date, and order ID
        5. Returns structured order data
        
        Args:
            file_paths: Optional list of specific files to parse. If None, parses all HTML files.
            days_filter: Optional number of days to filter orders by (only keep recent orders)
            
        Returns:
            List[Dict[str, Any]]: List of parsed order dictionaries
        """
        if file_paths is None:
            # Parse all HTML files in output directory
            file_paths = [
                os.path.join(self.output_dir, f) 
                for f in os.listdir(self.output_dir) 
                if f.endswith('.html')
            ]
        
        print(f"Parsing {len(file_paths)} HTML files...")
        
        all_orders = []
        for filepath in file_paths:
            filename = os.path.basename(filepath)
            print(f"  Processing {filename}...")
            
            try:
                with open(filepath, 'r', encoding='utf-8', errors='ignore') as f:
                    content = f.read()
                
                orders = self._parse_html(content, filename)
                all_orders.extend(orders)
                print(f"    Found {len(orders)} orders")
                
            except Exception as e:
                print(f"    ERROR: {e}")
        
        # Remove duplicate orders across all files
        unique_orders = self._remove_duplicates(all_orders)
        
        # Apply client-side date filtering if specified
        if days_filter is not None:
            filtered_orders = []
            for order in unique_orders:
                if order.get('date') and self._is_within_days(order['date'], days_filter):
                    filtered_orders.append(order)
                elif not order.get('date'):
                    # Keep orders without dates (they might be very recent)
                    filtered_orders.append(order)
            
            print(f"Filtered {len(unique_orders)} orders to {len(filtered_orders)} orders within last {days_filter} days")
            unique_orders = filtered_orders
        
        print(f"Total unique orders found: {len(unique_orders)}")
        
        return unique_orders
    
    def _parse_html(self, html_content: str, source_file: str) -> List[Dict[str, Any]]:
        """
        Extract order information from HTML content using BeautifulSoup.
        
        This function:
        1. Searches for order containers in the HTML structure
        2. Extracts order details from each container using regex patterns
        3. Returns structured data for each order found
        
        Args:
            html_content: Raw HTML content from order history page
            source_file: Name of the source HTML file (for tracking)
            
        Returns:
            List[Dict[str, Any]]: List of order dictionaries with extracted data
        """
        orders = []
        soup = BeautifulSoup(html_content, 'html.parser')
        
        # Find order containers - Amazon uses div elements with specific classes
        containers = soup.find_all('div', class_='a-box-group')
        if not containers:
            # Fallback: try broader container search
            containers = soup.find_all('div', class_='a-box')
        
        for i, container in enumerate(containers):
            order = self._extract_order(container, source_file, i)
            # Only include orders that have meaningful data (price or date)
            if order and (order.get('price') or order.get('date')):
                orders.append(order)
        
        return orders
    
    def _extract_order(self, container, source_file: str, index: int) -> Dict[str, Any]:
        """
        Extract individual order details from an HTML container.
        
        This function uses regex patterns to extract:
        - Order dates (multiple date formats)
        - Prices in Indian Rupees (₹)
        - Order IDs and statuses
        - Product names and item details
        
        Args:
            container: BeautifulSoup element containing order information
            source_file: Source HTML filename for tracking
            index: Container index within the file
            
        Returns:
            Dict[str, Any]: Dictionary containing extracted order details
        """
        order = {
            'source_file': source_file,
            'container_index': index,
            'extraction_method': 'html_container',
            'extracted_at': datetime.now().isoformat()
        }
        
        # Get all text from container for pattern matching
        text = container.get_text(separator=' ', strip=True)
        
        # Extract order date using multiple patterns to handle different formats
        date_patterns = [
            r'(\d{1,2}\s+(?:January|February|March|April|May|June|July|August|September|October|November|December)\s+\d{4})',
            r'(\d{1,2}\s+(?:Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec)\s+\d{4})',
            r'(\d{1,2}/\d{1,2}/\d{4})',
            r'(\d{4}-\d{2}-\d{2})'
        ]
        
        for pattern in date_patterns:
            match = re.search(pattern, text, re.I)
            if match:
                order['date'] = match.group(1)
                break
        
        # Extract prices in Indian Rupees (₹) - find all amounts and use the highest
        price_patterns = [
            r'₹\s*([\d,]+\.?\d*)',
            r'INR\s*([\d,]+\.?\d*)',
            r'Total[:\s]*₹\s*([\d,]+\.?\d*)'
        ]
        
        all_prices = []
        for pattern in price_patterns:
            prices = re.findall(pattern, text)
            all_prices.extend(prices)
        
        if all_prices:
            # Remove duplicates, sort, and take the highest price as order total
            unique_prices = list(set(all_prices))
            unique_prices.sort(key=lambda x: float(x.replace(',', '')))
            order['price'] = f"₹{unique_prices[-1]}"  # Highest price
        
        # Extract order ID using common Amazon order ID patterns
        id_patterns = [
            r'Order\s*#?\s*([A-Z0-9-]+)',
            r'ORDER\s*#?\s*([A-Z0-9-]+)',
            r'\b(\d{3}-\d{7}-\d{7})\b',
            r'Order ID[:\s]*([A-Z0-9-]+)'
        ]
        
        for pattern in id_patterns:
            match = re.search(pattern, text, re.I)
            if match:
                order['order_id'] = match.group(1)
                break
        
        # Extract order status from common keywords
        statuses = ['Delivered', 'Shipped', 'Cancelled', 'Processing', 'Pending', 'Returned', 'Refunded']
        for status in statuses:
            if re.search(rf'\b{status}\b', text, re.I):
                order['status'] = status
                break
        
        # Extract product names and item details
        items = self._extract_product_names(container)
        if items:
            order['items'] = items
            order['item_count'] = len(items)
            # Set the first item as the main order name for convenience
            order['order_name'] = items[0]['name'] if items else None
        
        return order
    
    def _extract_product_names(self, container) -> List[Dict[str, Any]]:
        """
        Extract product names and details from order container.
        
        This function looks for:
        - Product title links
        - Item descriptions
        - Product images with alt text
        - ASIN codes
        - Quantity information
        
        Args:
            container: BeautifulSoup element containing order information
            
        Returns:
            List[Dict[str, Any]]: List of product information
        """
        items = []
        
        # Method 1: Look for product links with titles
        product_links = container.find_all('a', class_='a-link-normal')
        for link in product_links:
            item_text = link.get_text(strip=True)
            # Filter out non-product links (navigation, actions, etc.)
            if (len(item_text) > 10 and 
                not re.match(r'^(View|Buy|Track|Return|Archive|See|More|Order|Account)', item_text, re.I) and
                not re.search(r'^(https?://|www\.)', item_text)):
                
                href = link.get('href', '')
                # Extract ASIN from product URL if available
                asin_match = re.search(r'/dp/([A-Z0-9]{10})', href) or re.search(r'asin=([A-Z0-9]{10})', href)
                asin = asin_match.group(1) if asin_match else None
                
                items.append({
                    'name': item_text[:200],  # Limit length to avoid overly long names
                    'link': href,
                    'asin': asin,
                    'extraction_method': 'product_link'
                })
        
        # Method 2: Look for specific product title classes
        product_titles = container.find_all(['span', 'div', 'a'], class_=re.compile(r'.*product.*title.*|.*item.*title.*', re.I))
        for title in product_titles:
            title_text = title.get_text(strip=True)
            if title_text and len(title_text) > 5 and title_text not in [item['name'] for item in items]:
                items.append({
                    'name': title_text[:200],
                    'link': '',
                    'asin': None,
                    'extraction_method': 'title_class'
                })
        
        # Method 3: Look for image alt texts (often contain product names)
        product_images = container.find_all('img')
        for img in product_images:
            alt_text = img.get('alt', '').strip()
            if (alt_text and len(alt_text) > 10 and 
                not re.search(r'(logo|icon|button|arrow)', alt_text, re.I) and
                alt_text not in [item['name'] for item in items]):
                
                src = img.get('src', '')
                # Extract ASIN from image URL if available
                asin_match = re.search(r'/images/I/[^/]*\.([A-Z0-9]{10})', src)
                asin = asin_match.group(1) if asin_match else None
                
                items.append({
                    'name': alt_text[:200],
                    'link': src,
                    'asin': asin,
                    'extraction_method': 'image_alt'
                })
        
        # Method 4: Extract from structured text patterns
        text = container.get_text(separator=' ', strip=True)
        
        # Look for "Qty: X" patterns to get quantity info
        qty_matches = re.findall(r'Qty[:\s]*(\d+)', text, re.I)
        
        # Look for product names in common patterns
        product_patterns = [
            r'(?:Item|Product)[:\s]+([^.]{10,100}?)(?:\s+₹|\s+Qty|\s+Delivered|\s+$)',
            r'(?:^|\s)([A-Z][^.₹]{15,150}?)(?:\s+₹|\s+Qty|\s+Delivered)',
        ]
        
        for pattern in product_patterns:
            matches = re.findall(pattern, text, re.MULTILINE)
            for match in matches:
                clean_match = re.sub(r'\s+', ' ', match.strip())
                if (len(clean_match) > 10 and 
                    clean_match not in [item['name'] for item in items] and
                    not re.search(r'^(Order|Delivered|Shipped)', clean_match, re.I)):
                    
                    items.append({
                        'name': clean_match[:200],
                        'link': '',
                        'asin': None,
                        'extraction_method': 'text_pattern'
                    })
        
        # Add quantity information if available
        if qty_matches and items:
            for i, qty in enumerate(qty_matches):
                if i < len(items):
                    items[i]['quantity'] = int(qty)
        
        # Remove duplicates based on name similarity
        unique_items = []
        for item in items:
            is_duplicate = False
            for unique_item in unique_items:
                # Check for similarity (simple word overlap check)
                item_words = set(item['name'].lower().split())
                unique_words = set(unique_item['name'].lower().split())
                overlap = len(item_words & unique_words) / max(len(item_words), len(unique_words))
                
                if overlap > 0.7:  # 70% word overlap considered duplicate
                    is_duplicate = True
                    break
            
            if not is_duplicate:
                unique_items.append(item)
        
        return unique_items[:5]  # Limit to first 5 items to avoid clutter
    
    def _remove_duplicates(self, orders: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """
        Remove duplicate orders based on price, date, and order ID.
        
        This function creates a unique key for each order using available
        identifying information and filters out duplicates that may appear
        across multiple HTML pages.
        
        Args:
            orders: List of order dictionaries that may contain duplicates
            
        Returns:
            List[Dict[str, Any]]: List of unique orders
        """
        seen = set()
        unique_orders = []
        
        for order in orders:
            # Create unique identifier using available order data
            key_parts = []
            if order.get('price'):
                key_parts.append(order['price'])
            if order.get('date'):
                key_parts.append(order['date'])
            if order.get('order_id'):
                key_parts.append(order['order_id'])
            
            if key_parts:
                key = '|'.join(key_parts)
                if key not in seen:
                    seen.add(key)
                    unique_orders.append(order)
            else:
                # If no identifying information, keep the order anyway
                unique_orders.append(order)
        
        return unique_orders
    
    def generate_summary(self, orders: List[Dict[str, Any]]) -> Dict[str, Any]:
        """
        Generate comprehensive summary statistics from parsed orders.
        
        This function calculates:
        - Total number of orders and data completeness statistics
        - Price range (minimum and maximum order values)
        - Total monetary value of all orders
        - Product name and item statistics
        - Data quality metrics
        
        Args:
            orders: List of parsed order dictionaries
            
        Returns:
            Dict[str, Any]: Summary statistics dictionary
        """
        if not orders:
            return {}
        
        summary = {
            'total_orders': len(orders),
            'orders_with_prices': 0,
            'orders_with_dates': 0,
            'orders_with_names': 0,
            'orders_with_items': 0,
            'price_range': {'min': None, 'max': None},
            'total_value': 0,
            'total_items': 0,
            'top_products': [],
            'extraction_methods': {}
        }
        
        prices = []
        all_products = []
        all_items = []
        
        for order in orders:
            if order.get('price'):
                summary['orders_with_prices'] += 1
                try:
                    # Convert price string to float for calculations
                    price_value = float(re.sub(r'[₹,]', '', order['price']))
                    prices.append(price_value)
                    summary['total_value'] += price_value
                except:
                    pass
            
            if order.get('date'):
                summary['orders_with_dates'] += 1
            
            if order.get('order_name'):
                summary['orders_with_names'] += 1
                all_products.append(order['order_name'])
            
            if order.get('items'):
                summary['orders_with_items'] += 1
                items = order['items']
                summary['total_items'] += len(items)
                
                # Collect all item names for analysis
                for item in items:
                    if isinstance(item, dict) and 'name' in item:
                        all_items.append(item['name'])
                        all_products.append(item['name'])
                    elif isinstance(item, str):
                        all_items.append(item)
                        all_products.append(item)
            
            # Count extraction methods
            method = order.get('extraction_method', 'unknown')
            summary['extraction_methods'][method] = summary['extraction_methods'].get(method, 0) + 1
        
        # Calculate price statistics if we have valid prices
        if prices:
            summary['price_range']['min'] = f"₹{min(prices):,.2f}"
            summary['price_range']['max'] = f"₹{max(prices):,.2f}"
            summary['total_value'] = f"₹{summary['total_value']:,.2f}"
            summary['average_order_value'] = f"₹{sum(prices) / len(prices):,.2f}"
        
        # Generate top products list (most frequently ordered)
        if all_products:
            from collections import Counter
            product_counts = Counter(all_products)
            summary['top_products'] = [
                {'name': product[:100], 'count': count} 
                for product, count in product_counts.most_common(10)
            ]
        
        return summary
    
    def save_results(self, orders: List[Dict[str, Any]], filename: str = None) -> str:
        """Save results to JSON file"""
        if filename is None:
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            filename = f"amazon_india_orders_{timestamp}.json"
        
        summary = self.generate_summary(orders)
        
        results = {
            'scraping_info': {
                'username': self.username,
                'scraped_at': datetime.now().isoformat(),
                'script_version': 'Amazon India Scraper v2.0',
                'total_orders': len(orders),
                'method': 'amazon_orders_library + custom_parser'
            },
            'summary': summary,
            'orders': orders
        }
        
        with open(filename, 'w', encoding='utf-8') as f:
            json.dump(results, f, indent=2, ensure_ascii=False)
        
        print(f"Results saved to: {filename}")
        return filename
    
    def print_summary(self, orders: List[Dict[str, Any]]):
        """
        Print a formatted summary of scraping results to console.
        
        Displays:
        - Total number of orders found
        - Data completeness statistics (orders with prices/dates/names)
        - Price range and total value information
        - Product name statistics and top products
        - Formatted output for easy reading
        
        Args:
            orders: List of parsed order dictionaries
        """
        summary = self.generate_summary(orders)
        
        print("\n" + "="*60)
        print("AMAZON INDIA ORDER SUMMARY")
        print("="*60)
        print(f"Total Orders: {summary.get('total_orders', 0)}")
        print(f"Orders with Prices: {summary.get('orders_with_prices', 0)}")
        print(f"Orders with Dates: {summary.get('orders_with_dates', 0)}")
        print(f"Orders with Product Names: {summary.get('orders_with_names', 0)}")
        print(f"Orders with Item Details: {summary.get('orders_with_items', 0)}")
        print(f"Total Items Found: {summary.get('total_items', 0)}")
        
        if summary.get('price_range', {}).get('min'):
            print(f"Price Range: {summary['price_range']['min']} - {summary['price_range']['max']}")
            print(f"Total Value: {summary.get('total_value', '₹0')}")
            print(f"Average Order Value: {summary.get('average_order_value', '₹0')}")
        
        # Show top products if available
        if summary.get('top_products'):
            print(f"\nTOP PRODUCTS:")
            for i, product in enumerate(summary['top_products'][:5], 1):
                print(f"  {i}. {product['name'][:80]}... ({product['count']} orders)")
        
        print("="*60)
    
    def run_full_scrape(self, days: int = 2) -> bool:
        """
        Execute the complete order scraping workflow for last N days.
        
        This is the main orchestration function that:
        1. Authenticates with Amazon India
        2. Fetches order history pages for the last N days
        3. Parses orders from the downloaded HTML files
        4. Generates summary statistics and saves results
        
        Args:
            days: Number of recent days to fetch orders for (default: 2)
            
        Returns:
            bool: True if scraping completed successfully, False otherwise
        """
        print("Amazon India Order Scraper")
        print("="*40)
        
        # Step 1: Authentication
        if not self.login():
            return False
        
        # Step 2: Fetch order pages
        print(f"\nFetching orders from last {days} days...")
        saved_files = self.fetch_orders(days)
        
        if not saved_files:
            print("ERROR: No pages fetched!")
            return False
        
        # Step 3: Parse orders
        print("\nParsing orders...")
        orders = self.parse_orders(saved_files, days_filter=days)
        
        if not orders:
            print("ERROR: No orders found!")
            return False
        
        # # Step 4: Display results and save
        # self.print_summary(orders)
        # self.save_results(orders)
        
        print("\nScraping completed successfully!")
        return orders
    
def get_order(tool_request) -> List[Dict[str, Any]]:
    """
    Main entry point for the Amazon India order scraper.
    
    This function:
    1. Creates a scraper instance with user credentials
    2. Checks for existing HTML files from previous runs
    3. Fetches orders from the last 2-3 days by default
    4. Handles user interaction and error management
    """
    try:
        scraper = AmazonIndiaScraper(
            username=os.getenv("AMAZON_USER_ID"),
            password=os.getenv("AMAZON_USER_PASSWORD"),
            debug=False  # Set to True for detailed debugging output
        )

        if os.path.exists(scraper.output_dir):
            for file in os.listdir(scraper.output_dir):
                if file.endswith('.html'):
                   os.remove(os.path.join(scraper.output_dir, file))
        
        days = tool_request.get("days", 2)
        print(f"Fetching orders from last {days} days...")
        result = scraper.run_full_scrape(days)
        return result
    
    except KeyboardInterrupt:
        print("\nOperation stopped by user")
    except Exception as e:
        print(f"ERROR: {e}")
        import traceback
        traceback.print_exc()
if __name__ == "__main__":
    tool_request = {"days": 30}  # Example input to
    result = get_order(tool_request)
    print(result)
    pass