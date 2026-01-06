"""
Simple Zepto Login with Async Playwright
Focused on login and session handling only
"""

import asyncio
import json
import os
import logging
from datetime import datetime
from playwright.async_api import async_playwright

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

class ZeptoLoginAsync:
    def __init__(self, phone_number, headless=False):
        self.phone_number = phone_number
        self.base_url = "https://www.zeptonow.com"
        self.headless = headless
        self.browser = None
        self.context = None
        self.page = None
        self.playwright = None
        self.user_data_dir = "connectors/zepto_browser_data"
        self.session_metadata_file = "zepto_session_metadata.json"
        
        # Create browser data directory
        if not os.path.exists(self.user_data_dir):
            os.makedirs(self.user_data_dir)
            logger.info(f"Created browser data directory: {self.user_data_dir}")
    
    async def check_existing_session(self):
        """Check if a valid session exists locally"""
        try:
            # Check if browser data directory has session files
            session_files = ['Local State', 'Default/Preferences', 'Default/Cookies']
            session_exists = False
            
            for file_path in session_files:
                full_path = os.path.join(self.user_data_dir, file_path)
                if os.path.exists(full_path):
                    session_exists = True
                    break
            
            # Check session metadata
            metadata_path = os.path.join(self.user_data_dir, self.session_metadata_file)
            if os.path.exists(metadata_path):
                with open(metadata_path, 'r', encoding='utf-8') as f:
                    metadata = json.load(f)
                    
                last_login = metadata.get('last_login_time')
                phone_number = metadata.get('phone_number')
                
                if last_login and phone_number == self.phone_number:
                    logger.info(f"Found valid session for {phone_number} from {last_login}")
                    return True
            
            if session_exists:
                logger.info("Browser data found but no metadata - will validate during login check")
                return True
                
            logger.info("No existing session found")
            return False
            
        except Exception as e:
            logger.warning(f"Error checking existing session: {e}")
            return False
    
    async def save_session_metadata(self, login_successful=True):
        """Save session metadata for validation"""
        try:
            metadata = {
                'phone_number': self.phone_number,
                'last_login_time': datetime.now().isoformat(),
                'login_successful': login_successful,
                'browser_data_dir': self.user_data_dir,
                'session_version': '2.0'
            }
            
            metadata_path = os.path.join(self.user_data_dir, self.session_metadata_file)
            with open(metadata_path, 'w', encoding='utf-8') as f:
                json.dump(metadata, f, indent=2, ensure_ascii=False)
            
            logger.info(f"Session metadata saved: {metadata_path}")
            return True
            
        except Exception as e:
            logger.error(f"Failed to save session metadata: {e}")
            return False
    
    async def clear_session(self):
        """Clear existing session data"""
        try:
            import shutil
            
            if os.path.exists(self.user_data_dir):
                shutil.rmtree(self.user_data_dir)
                logger.info(f"Cleared session data: {self.user_data_dir}")
                
            # Recreate the directory
            os.makedirs(self.user_data_dir)
            return True
            
        except Exception as e:
            logger.error(f"Failed to clear session: {e}")
            return False
    
    async def start_browser(self):
        """Initialize browser with session persistence - using Firefox for better headless support"""
        try:
            self.playwright = await async_playwright().start()
            
            # Check if existing session exists (file-based check only)
            session_exists = await self.check_existing_session()
            if session_exists:
                logger.info("Found existing session data - will attempt to restore")
            else:
                logger.info("No existing session found - fresh start")
            
            logger.info(f"Starting Firefox browser in {'headless' if self.headless else 'headed'} mode")
            
            # Firefox has excellent headless support and is less detectable than Chrome
            browser_args = []
            
            # Use persistent context for session management with Firefox
            self.context = await self.playwright.firefox.launch_persistent_context(
                self.user_data_dir,
                headless=self.headless,
                viewport={'width': 1920, 'height': 1080},
                user_agent='Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:122.0) Gecko/20100101 Firefox/122.0',
                args=browser_args,
                accept_downloads=True,
                java_script_enabled=True,
                permissions=['geolocation', 'notifications'],
                ignore_https_errors=True,
                locale='en-US',
                timezone_id='Asia/Kolkata',
                device_scale_factor=1,
                has_touch=False,
                is_mobile=False,
            )
            
            self.page = self.context.pages[0] if self.context.pages else await self.context.new_page()
            
            logger.info("Firefox browser started successfully")
            return True
            
        except Exception as e:
            logger.error(f"Failed to start browser: {e}")
            return False
    
    async def navigate_to_zepto(self):
        """Navigate to Zepto homepage"""
        try:
            await self.page.goto(self.base_url, wait_until='networkidle')
            await self.page.wait_for_timeout(3000)
            logger.info("Navigated to Zepto homepage")
            return True
        except Exception as e:
            logger.error(f"Failed to navigate to Zepto: {e}")
            return False
    
    async def is_logged_in(self):
        """Check if user is already logged in"""
        try:
            # Wait a bit for page to load
            await self.page.wait_for_timeout(1000)
            
            # Check for login indicators
            login_indicators = [
                "text=Login",
                "text=Sign In", 
                "text=Enter your phone number",
                "[data-testid*='login']"
            ]
            
            for indicator in login_indicators:
                try:
                    element = await self.page.wait_for_selector(indicator, timeout=1000)
                    if element and await element.is_visible():
                        return False
                except:
                    continue
            
            # Check for logged-in indicators
            logged_in_indicators = [
                "text=Profile",
                "text=Account", 
                "text=My Orders",
                "[data-testid*='profile']",
                "[data-testid*='account']"
            ]
            
            for indicator in logged_in_indicators:
                try:
                    element = await self.page.wait_for_selector(indicator, timeout=2000)
                    if element and await element.is_visible():
                        return True
                except:
                    continue
            
            # Check page content for login status
            page_content = await self.page.content()
            if "login" in page_content.lower() and "phone" in page_content.lower():
                return False
            
            logger.info("Login status unclear, assuming logged in")
            return True
            
        except Exception as e:
            logger.error(f"Failed to check login status: {e}")
            return False
    
    async def perform_login(self):
        """Perform login to Zepto"""
        logger.info("Starting login process")
        
        try:
            # Look for login button/link
            login_selectors = [
                "text=Login",
                "text=Sign In",
                "[data-testid*='login']",
                "button:has-text('Login')",
                "a:has-text('Login')"
            ]
            
            login_clicked = False
            for selector in login_selectors:
                try:
                    element = await self.page.wait_for_selector(selector, timeout=2000)
                    if element and await element.is_visible():
                        await element.click()
                        logger.info("Clicked login button")
                        login_clicked = True
                        break
                except:
                    continue
            
            if not login_clicked:
                logger.info("No explicit login button found, checking if login form is already visible")
            
            # Wait for login form
            await self.page.wait_for_timeout(2000)
            
            # Enter phone number
            phone_selectors = [
                "input[type='tel']",
                "input[placeholder*='phone']",
                "input[placeholder*='number']",
                "[data-testid*='phone']",
                "input[name*='phone']"
            ]
            
            phone_entered = False
            for selector in phone_selectors:
                try:
                    phone_input = await self.page.wait_for_selector(selector, timeout=3000)
                    if phone_input and await phone_input.is_visible():
                        await phone_input.click()
                        await phone_input.fill('')  # Clear first
                        await phone_input.fill(self.phone_number)
                        logger.info("Phone number entered")
                        phone_entered = True
                        break
                except:
                    continue
            
            if not phone_entered:
                logger.error("Could not find phone number input field")
                return False
            
            # Click continue/submit button
            submit_selectors = [
                "button:has-text('Continue')",
                "button:has-text('Send OTP')",
                "button:has-text('Submit')",
                "button[type='submit']",
                "[data-testid*='continue']",
                "[data-testid*='submit']"
            ]
            
            for selector in submit_selectors:
                try:
                    submit_btn = await self.page.wait_for_selector(selector, timeout=3000)
                    if submit_btn and await submit_btn.is_enabled():
                        await submit_btn.click()
                        logger.info("Submit button clicked")
                        break
                except:
                    continue
            
            # Wait for OTP input
            logger.info("Waiting for OTP input fields...")
            
            # Wait for OTP input fields (6 separate boxes)
            try:
                # Wait for the OTP container to appear
                await self.page.wait_for_selector("div.fugkX", timeout=10000)
                logger.info("OTP input fields detected")
                
                # Get all 6 OTP input fields
                otp_inputs = await self.page.query_selector_all("div.fugkX input[inputmode='numeric']")
                
                if len(otp_inputs) == 6:
                    # Prompt user to enter OTP in command line
                    print("\n" + "="*50)
                    otp_code = await asyncio.get_event_loop().run_in_executor(
                        None, 
                        lambda: input("Enter 6-digit OTP: ")
                    )
                    print("="*50 + "\n")
                    
                    # Remove any spaces or dashes
                    otp_code = otp_code.replace(" ", "").replace("-", "").strip()
                    
                    if len(otp_code) != 6 or not otp_code.isdigit():
                        logger.error("Invalid OTP format. Must be 6 digits")
                        return False
                    
                    # Fill each digit into its respective input field
                    for i, digit in enumerate(otp_code):
                        await otp_inputs[i].click()
                        await otp_inputs[i].fill(digit)
                        await self.page.wait_for_timeout(100)
                    
                    logger.info("OTP entered successfully")
                    
                    # Wait for automatic verification (usually auto-submits)
                    await self.page.wait_for_timeout(2000)
                else:
                    logger.error(f"Expected 6 OTP input fields, found {len(otp_inputs)}")
                    return False
                
            except Exception as e:
                logger.warning(f"OTP handling failed: {e}")
                return False
            
            # Check if login was successful
            await self.page.wait_for_timeout(3000)
            if await self.is_logged_in():
                logger.info("Login successful!")
                await self.save_session_metadata(login_successful=True)
                return True
            else:
                logger.error("Login may have failed")
                return False
                
        except Exception as e:
            logger.error(f"Login process failed: {e}")
            return False
    
    async def handle_popups(self):
        """Handle various popups that may appear after login"""
        logger.info("Checking for and handling popups...")
        
        try:
            # Wait a moment for popups to appear
            await self.page.wait_for_timeout(2000)
            
            # Common popup close button selectors
            close_button_selectors = [
                "button:has-text('✕')",
                "button:has-text('×')",
                "button:has-text('Close')",
                "[aria-label='close' i]",
                "[aria-label='dismiss' i]",
                ".close-button",
                "[data-testid*='close']",
                "[data-testid*='dismiss']",
                "button:has-text('Not now')",
                "button:has-text('Maybe later')",
                "button:has-text('Skip')",
                "button:has-text('Cancel')",
                "button:has-text('No thanks')"
            ]
            
            popups_closed = 0
            max_attempts = 3
            
            for attempt in range(max_attempts):
                popup_found = False
                
                # Try to close any visible popups
                for selector in close_button_selectors:
                    try:
                        element = await self.page.wait_for_selector(selector, timeout=1000)
                        if element and await element.is_visible():
                            await element.click()
                            logger.info(f"Closed popup using: {selector}")
                            popups_closed += 1
                            popup_found = True
                            await self.page.wait_for_timeout(1000)
                            break
                    except:
                        continue
                
                # Try pressing Escape key to close popups
                if not popup_found:
                    try:
                        await self.page.keyboard.press('Escape')
                        await self.page.wait_for_timeout(1000)
                    except:
                        pass
                
                if not popup_found:
                    break
            
            if popups_closed > 0:
                logger.info(f"Closed {popups_closed} popup(s)")
            else:
                logger.info("No popups found to close")
                
            return True
            
        except Exception as e:
            logger.warning(f"Error handling popups: {e}")
            return True  # Continue anyway
    
    async def complete_login_workflow(self):
        """Complete login workflow: browser → navigate → login → cleanup popups"""
        try:
            logger.info("Starting complete login workflow...")
            
            # Step 1: Start browser
            if not await self.start_browser():
                return False
            
            # Step 2: Navigate to Zepto
            if not await self.navigate_to_zepto():
                return False
            
            # Step 3: Check if already logged in
            if await self.is_logged_in():
                logger.info("Already logged in")
            else:
                # Step 4: Perform login
                if not await self.perform_login():
                    return False
            
            # Step 5: Handle any popups
            await self.handle_popups()
            
            logger.info("Login workflow completed successfully!")
            logger.info("Browser session is ready for use")
            return True
            
        except Exception as e:
            logger.error(f"Login workflow failed: {e}")
            return False
    
    async def get_session_info(self):
        """Get information about current session"""
        try:
            metadata_path = os.path.join(self.user_data_dir, self.session_metadata_file)
            if os.path.exists(metadata_path):
                with open(metadata_path, 'r', encoding='utf-8') as f:
                    metadata = json.load(f)
                return metadata
            return None
        except:
            return None
    
    async def cleanup(self):
        """Cleanup browser resources"""
        try:
            if self.context:
                await self.context.close()
            if self.browser:
                await self.browser.close()
            if self.playwright:
                await self.playwright.stop()
        except:
            pass

async def main():
    """Main function to run the login workflow"""
    phone_number = '9028129764'  # Replace with your phone number
    
    scraper = ZeptoLoginAsync(
        phone_number=phone_number,
        headless=False  # Set to True for headless mode
    )
    
    # Check existing session info
    session_info = await scraper.get_session_info()
    if session_info:
        logger.info(f"Found existing session from: {session_info.get('last_login_time', 'Unknown')}")
        logger.info(f"Session phone number: {session_info.get('phone_number', 'Unknown')}")
    else:
        logger.info("No existing session found - will perform fresh login")
    
    try:
        success = await scraper.complete_login_workflow()
        
        if success:
            logger.info("Zepto login completed successfully!")
            logger.info("Browser session is ready for automation")
        else:
            logger.error("Login failed")
        
        # Keep browser open for manual inspection
        logger.info("Press Enter to close browser...")
        await asyncio.get_event_loop().run_in_executor(None, input)
        
    finally:
        await scraper.cleanup()

if __name__ == "__main__":
    asyncio.run(main())
