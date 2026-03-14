"""
Zepto Order Database Manager - Simple SQLite-based order tracking
"""
import sqlite3
import json
import os
from datetime import datetime
from typing import Optional, Dict, Any, List

DB_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "data", "zepto_orders.db")


class ZeptoOrderDatabase:
    """Simple Zepto order state management using SQLite"""
    
    def __init__(self, db_path=DB_FILE):
        self.db_path = db_path
        self._ensure_data_dir()
        self._create_table()
    
    def _ensure_data_dir(self):
        """Ensure the data directory exists"""
        dirpath = os.path.dirname(self.db_path)
        os.makedirs(dirpath, exist_ok=True)
    
    def _create_table(self):
        """Create the zepto_orders table if it doesn't exist"""
        try:
            conn = sqlite3.connect(self.db_path)
            cursor = conn.cursor()
            
            cursor.execute('''
                CREATE TABLE IF NOT EXISTS zepto_orders (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    status TEXT DEFAULT 'pending',
                    current_task TEXT,
                    items TEXT,
                    total_price REAL DEFAULT 0.0,
                    error INTEGER DEFAULT 0,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    context TEXT
                )
            ''')
            
            conn.commit()
            conn.close()
        except Exception as e:
            print(f"[ZEPTO_DB] Error creating table: {e}")
    
    def save_order(self, status="pending", current_task="", items=None, total_price=0.0, error=False, context=""):
        """
        Save a new order (creates new entry)
        
        Args:
            status: 'pending', 'processing', 'payment', 'completed'
            current_task: Task name ('searching', 'selection', etc.)
            items: List of items
            total_price: Order total
            error: Error occurred?
            context: Log/notes
        """
        try:
            conn = sqlite3.connect(self.db_path)
            cursor = conn.cursor()
            
            items_json = json.dumps(items if items else [])
            
            cursor.execute('''
                INSERT INTO zepto_orders (status, current_task, items, total_price, error, context)
                VALUES (?, ?, ?, ?, ?, ?)
            ''', (status, current_task, items_json, total_price, int(error), context))
            
            conn.commit()
            order_id = cursor.lastrowid
            conn.close()
            
            print(f"[ZEPTO_DB] Saved order #{order_id}")
            return order_id
        except Exception as e:
            print(f"[ZEPTO_DB] Error saving order: {e}")
            return None
    
    def get_latest_order(self) -> Optional[Dict[str, Any]]:
        """
        Get the latest incomplete order (pending or processing)
        
        Returns:
            Order dict or None
        """
        try:
            conn = sqlite3.connect(self.db_path)
            conn.row_factory = sqlite3.Row
            cursor = conn.cursor()
            
            cursor.execute('''
                SELECT * FROM zepto_orders 
                WHERE status IN ('pending', 'processing')
                ORDER BY updated_at DESC LIMIT 1
            ''')
            
            row = cursor.fetchone()
            conn.close()
            
            if not row:
                return None
            
            order = dict(row)
            order['items'] = json.loads(order['items'])
            order['error'] = bool(order['error'])
            return order
        except Exception as e:
            print(f"[ZEPTO_DB] Error getting latest order: {e}")
            return None
    
    def update_task(self, order_id: int, task: str, append_context: str = ""):
        """
        Update the current task for an order
        
        Args:
            order_id: Order ID to update
            task: New task name
            append_context: Text to append to context log
        """
        try:
            conn = sqlite3.connect(self.db_path)
            cursor = conn.cursor()
            
            if append_context:
                cursor.execute('''
                    UPDATE zepto_orders 
                    SET current_task = ?, updated_at = CURRENT_TIMESTAMP, 
                        context = context || '\n' || ?
                    WHERE id = ?
                ''', (task, f"[{datetime.now().strftime('%H:%M:%S')}] {append_context}", order_id))
            else:
                cursor.execute('''
                    UPDATE zepto_orders 
                    SET current_task = ?, updated_at = CURRENT_TIMESTAMP
                    WHERE id = ?
                ''', (task, order_id))
            
            conn.commit()
            conn.close()
            print(f"[ZEPTO_DB] Updated task: {task}")
        except Exception as e:
            print(f"[ZEPTO_DB] Error updating task: {e}")
    
    def update_items(self, order_id: int, items: list, total_price: float = 0.0):
        """
        Update items in an order
        
        Args:
            order_id: Order ID to update
            items: New items list
            total_price: New total price
        """
        try:
            conn = sqlite3.connect(self.db_path)
            cursor = conn.cursor()
            
            items_json = json.dumps(items)
            
            if total_price > 0:
                cursor.execute('''
                    UPDATE zepto_orders 
                    SET items = ?, total_price = ?, updated_at = CURRENT_TIMESTAMP
                    WHERE id = ?
                ''', (items_json, total_price, order_id))
            else:
                cursor.execute('''
                    UPDATE zepto_orders 
                    SET items = ?, updated_at = CURRENT_TIMESTAMP
                    WHERE id = ?
                ''', (items_json, order_id))
            
            conn.commit()
            conn.close()
            print(f"[ZEPTO_DB] Updated items in order #{order_id}")
        except Exception as e:
            print(f"[ZEPTO_DB] Error updating items: {e}")
    
    def set_error(self, order_id: int, error: bool = True, error_msg: str = ""):
        """
        Set error flag for an order
        
        Args:
            order_id: Order ID
            error: True/False
            error_msg: Error message to log
        """
        try:
            conn = sqlite3.connect(self.db_path)
            cursor = conn.cursor()
            
            error_log = f"ERROR: {error_msg}" if error_msg else "ERROR occurred"
            cursor.execute('''
                UPDATE zepto_orders 
                SET error = ?, context = context || '\n' || ?
                WHERE id = ?
            ''', (int(error), f"[{datetime.now().strftime('%H:%M:%S')}] {error_log}", order_id))
            
            conn.commit()
            conn.close()
            print(f"[ZEPTO_DB] Error flag set for order #{order_id}")
        except Exception as e:
            print(f"[ZEPTO_DB] Error setting error flag: {e}")
    
    def update_status(self, order_id: int, status: str):
        """
        Update order status
        
        Args:
            order_id: Order ID
            status: 'pending', 'processing', 'payment', 'completed'
        """
        try:
            conn = sqlite3.connect(self.db_path)
            cursor = conn.cursor()
            
            cursor.execute('''
                UPDATE zepto_orders 
                SET status = ?, updated_at = CURRENT_TIMESTAMP
                WHERE id = ?
            ''', (status, order_id))
            
            conn.commit()
            conn.close()
            print(f"[ZEPTO_DB] Updated status to: {status}")
        except Exception as e:
            print(f"[ZEPTO_DB] Error updating status: {e}")
    
    def get_summary(self, order_id: int) -> str:
        """Get readable summary of an order"""
        try:
            conn = sqlite3.connect(self.db_path)
            conn.row_factory = sqlite3.Row
            cursor = conn.cursor()
            
            cursor.execute("SELECT * FROM zepto_orders WHERE id = ?", (order_id,))
            row = cursor.fetchone()
            conn.close()
            
            if not row:
                return "Order not found"
            
            order = dict(row)
            items = json.loads(order['items'])
            
            summary = f"Order #{order_id}\n"
            summary += f"Status: {order['status'].upper()}\n"
            summary += f"Task: {order['current_task']}\n"
            summary += f"Items: {len(items)}\n"
            summary += f"Total: ₹{order['total_price']}\n"
            
            if order['error']:
                summary += "⚠️ ERROR FLAG SET\n"
            
            return summary
        except Exception as e:
            print(f"[ZEPTO_DB] Error: {e}")
            return "Error getting summary"
    
    def clear(self, order_id: int):
        """Delete an order"""
        try:
            conn = sqlite3.connect(self.db_path)
            cursor = conn.cursor()
            cursor.execute("DELETE FROM zepto_orders WHERE id = ?", (order_id,))
            conn.commit()
            conn.close()
            print(f"[ZEPTO_DB] Cleared order #{order_id}")
        except Exception as e:
            print(f"[ZEPTO_DB] Error clearing: {e}")

if __name__ == "__main__":
    db = ZeptoOrderDatabase()
    db._create_table()
    # order_id = db.save_order(status="pending", current_task="searching", items=["milk", "bread"], total_price=50.0)
    # print(db.get_summary(order_id))
    # db.update_task(order_id, "selection", append_context="Selected 2 items")
    # db.update_items(order_id, ["milk", "bread", "eggs"], total_price=80.0)
    # print(db.get_summary(order_id))
    # db.set_error(order_id, error=True, error_msg="Payment failed")
    # print(db.get_summary(order_id))
    # db.update_status(order_id, "payment")
    # print(db.get_summary(order_id))