"""Simple test for order_again() function"""

import asyncio
from connectors.zepto_order_automation import ZeptoScraper


async def test_order_again():
    """Test reordering the most recent order"""
    
    phone_number = "9028129764"
    scraper = ZeptoScraper(phone_number, headless=False)
    
    try:
        await scraper.setup_browser()
        
        # Get order history
        orders = await scraper.get_order_history(max_orders=3)
        print(f"\nFound {len(orders)} orders:")
        for order in orders:
            print(f"  [{order['order_number']-1}] {order['status']} - {order['amount']}")
        
        # Reorder first order (index 0)
        print("\nReordering order at index 0...")
        success = await scraper.order_again(order_index=0)
        
        if success:
            print("✓ Order reordered successfully!")
        else:
            print("✗ Failed to reorder")
        
    finally:
        await scraper.cleanup()


if __name__ == "__main__":
    asyncio.run(test_order_again())
