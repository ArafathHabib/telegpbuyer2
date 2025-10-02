"""
Database operations and schema management
"""
import sqlite3
import hashlib
from typing import Optional, Dict, Any
from config import DB_PATH


def get_connection():
    """Get database connection"""
    return sqlite3.connect(DB_PATH)


def init_database():
    """Initialize database schema"""
    conn = get_connection()
    cursor = conn.cursor()
    
    # Users table
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS users (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            username TEXT UNIQUE NOT NULL,
            password_hash TEXT NOT NULL,
            telegram_username TEXT,
            usdt_wallet TEXT,
            balance REAL DEFAULT 0,
            created_ts INTEGER NOT NULL,
            is_admin INTEGER DEFAULT 0
        )
    ''')
    
    # Campaigns table - UPDATED WITH MONTH COLUMN
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS campaigns (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            title TEXT NOT NULL,
            year INTEGER NOT NULL,
            month INTEGER,                    -- ADDED MONTH COLUMN
            price_usd REAL NOT NULL,
            target_count INTEGER NOT NULL,
            sold_count INTEGER DEFAULT 0,
            created_ts INTEGER NOT NULL
        )
    ''')
    
    # System settings table for tracking round-robin state
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS system_settings (
            key TEXT PRIMARY KEY,
            value TEXT
        )
    ''')

    # Listings table - UPDATED with included_in_withdrawal column
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS listings (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER NOT NULL,
            campaign_id INTEGER NOT NULL,
            group_link TEXT NOT NULL,
            seller_tg TEXT,
            seller_usdt TEXT,
            price_usd REAL NOT NULL,
            status TEXT NOT NULL,
            check_reason TEXT,
            check_log TEXT,
            checked_by_session INTEGER,
            receiver_session INTEGER,
            created_ts INTEGER NOT NULL,
            transferred_ts INTEGER,
            included_in_withdrawal INTEGER DEFAULT 0,
            FOREIGN KEY (user_id) REFERENCES users(id),
            FOREIGN KEY (campaign_id) REFERENCES campaigns(id)
        )
    ''')
    
    # Withdrawals table
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS withdrawals (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER NOT NULL,
            seller_usdt TEXT NOT NULL,
            amount_usdt REAL NOT NULL,
            status TEXT DEFAULT 'pending',
            txid TEXT,
            created_ts INTEGER NOT NULL,
            paid_ts INTEGER,
            withdrawal_request_msg_id INTEGER,
            FOREIGN KEY (user_id) REFERENCES users(id)
        )
    ''')
    
    # Admin sessions table
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS admin_sessions (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            session_text TEXT NOT NULL,
            username TEXT NOT NULL,
            session_type TEXT DEFAULT 'checker',
            status TEXT NOT NULL,
            groups_received INTEGER DEFAULT 0,
            last_used_ts INTEGER,
            channel_id TEXT
        )
    ''')
    
    # ADD MISSING COLUMNS if they don't exist
    try:
        cursor.execute("ALTER TABLE listings ADD COLUMN included_in_withdrawal INTEGER DEFAULT 0")
    except sqlite3.OperationalError:
        pass  # Column already exists
    
    try:
        cursor.execute("ALTER TABLE admin_sessions ADD COLUMN channel_id TEXT")
    except sqlite3.OperationalError:
        pass  # Column already exists
    
    try:
        cursor.execute("ALTER TABLE withdrawals ADD COLUMN withdrawal_request_msg_id INTEGER")
    except sqlite3.OperationalError:
        pass  # Column already exists
    try:
        cursor.execute("ALTER TABLE campaigns ADD COLUMN month INTEGER")
    except sqlite3.OperationalError:
        pass  # Column already exists
    
    conn.commit()
    conn.close()
    print("Database initialized successfully")


def hash_password(password: str) -> str:
    """Hash password using SHA256"""
    return hashlib.sha256(password.encode()).hexdigest()


# User operations
def create_user(username: str, password: str, telegram_username: str, usdt_wallet: str, created_ts: int) -> Optional[int]:
    """Create new user"""
    try:
        conn = get_connection()
        cursor = conn.cursor()
        cursor.execute(
            'INSERT INTO users (username, password_hash, telegram_username, usdt_wallet, created_ts) VALUES (?, ?, ?, ?, ?)',
            (username, hash_password(password), telegram_username, usdt_wallet, created_ts)
        )
        user_id = cursor.lastrowid
        conn.commit()
        conn.close()
        return user_id
    except sqlite3.IntegrityError:
        return None


def get_user_by_id(user_id: int) -> Optional[Dict[str, Any]]:
    """Get user by ID"""
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute(
        'SELECT id, username, balance, telegram_username, usdt_wallet, created_ts, is_admin FROM users WHERE id = ?',
        (user_id,)
    )
    row = cursor.fetchone()
    conn.close()
    
    if row:
        return {
            'id': row[0],
            'username': row[1],
            'balance': round(row[2], 2),
            'telegram_username': row[3],
            'usdt_wallet': row[4],
            'created_ts': row[5],
            'is_admin': row[6]
        }
    return None


def get_user_by_username(username: str) -> Optional[Dict[str, Any]]:
    """Get user by username (for login)"""
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute(
        'SELECT id, password_hash FROM users WHERE username = ?',
        (username,)
    )
    row = cursor.fetchone()
    conn.close()
    
    if row:
        return {
            'id': row[0],
            'password_hash': row[1]
        }
    return None


def verify_user_password(username: str, password: str) -> Optional[int]:
    """Verify user credentials and return user ID"""
    user = get_user_by_username(username)
    if user and user['password_hash'] == hash_password(password):
        return user['id']
    return None


# Campaign operations
def get_all_campaigns():
    """Get all campaigns"""
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute(
        'SELECT id, title, year, price_usd, target_count, sold_count FROM campaigns ORDER BY id DESC'
    )
    campaigns = []
    for row in cursor.fetchall():
        progress = min(100, int((row[5] / row[4]) * 100) if row[4] > 0 else 0)
        campaigns.append({
            'id': row[0],
            'title': row[1],
            'year': row[2],
            'price_usd': row[3],
            'target_count': row[4],
            'sold_count': row[5],
            'progress': progress
        })
    conn.close()
    return campaigns


def get_campaign_by_id(campaign_id: int):
    """Get campaign by ID"""
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute(
        'SELECT id, title, year, price_usd FROM campaigns WHERE id = ?',
        (campaign_id,)
    )
    row = cursor.fetchone()
    conn.close()
    
    if row:
        return {
            'id': row[0],
            'title': row[1],
            'year': row[2],
            'price_usd': row[3]
        }
    return None


if __name__ == '__main__':
    # Initialize database when run directly
    init_database()