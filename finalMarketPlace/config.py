"""
Configuration settings for Telegram Group Seller Platform
"""
import os
from dotenv import load_dotenv
load_dotenv()
# Database
DB_PATH = os.getenv('DB_PATH', 'sellgroup.db')

# Admin Authentication
ADMIN_TOKENS = set(t.strip() for t in os.getenv('ADMIN_API_TOKENS', 'admin123').split(',') if t.strip())

# Server Settings
WEB_HOST = os.getenv('WEB_HOST', '0.0.0.0')
WEB_PORT = int(os.getenv('WEB_PORT', '8000'))

# Payment Settings
USD_RATE = 1.0
USDT_NETWORK = 'Polygon'

# Telegram API Credentials
API_ID = int(os.getenv('TELEGRAM_API_ID', '22678810'))
API_HASH = os.getenv('TELEGRAM_API_HASH', 'e1bae6cf96738d4f22dd7fe14c583713')

# Business Rules
MAX_GROUPS_PER_RECEIVER = 10
MIN_WITHDRAWAL_AMOUNT = 1

# Group Verification Keywords
CRYPTO_KEYWORDS = [
    'investment', 'ico', 'staking', 'apy', 'usdt', 'tron', 'bnb', 
    'coin', 'token', 'presale', 'airdrop', 'btc', 'crypto', 
    'exchange', 'binance', 'bybit'
]

LOCATION_KEYWORDS = [
    'location', 'near', 'latitude', 'longitude', 'address', 
    'city', 'geolocation'
]

IMPORTED_KEYWORDS = [
    'imported', 'import from', 'migrated', 'history imported', 
    'messages imported', 'message history', 'history was'
]

ADDED_KEYWORDS = [
    'added', 'joined the group', 'invited', 'has joined'
]

REMOVED_KEYWORDS = [
    'left', 'kicked', 'removed', 'banned', 'deleted'
]

# Session types
SESSION_TYPES = [
    'checker',
    'receiver', 
    'withdrawal_request',
    'withdrawal_paid'
]

# Channel IDs (set these after creating channels)
WITHDRAWAL_REQUEST_CHANNEL = os.getenv('WITHDRAWAL_REQUEST_CHANNEL', '')  # e.g., '@your_withdraw_requests'
WITHDRAWAL_PAID_CHANNEL = os.getenv('WITHDRAWAL_PAID_CHANNEL', '')  # e.g., '@your_withdraw_paid'

# Session Storage (in-memory)
telegram_login_sessions = {}
active_telegram_clients = {}