import os, time, hashlib
from database import init_database, get_connection
from config import DB_PATH

def reset_db():
    # Delete old DB
    if os.path.exists(DB_PATH):
        os.remove(DB_PATH)
        print("🗑️ Old database deleted")

    # Recreate tables
    init_database()
    print("✅ Fresh database initialized")

    # Create default admin
    conn = get_connection()
    cursor = conn.cursor()

    username = "admin"
    password = "admin123"   # change later
    hashed = hashlib.sha256(password.encode()).hexdigest()

    cursor.execute("""
        INSERT INTO users (username, password_hash, telegram_username, usdt_wallet, balance, created_ts, is_admin)
        VALUES (?, ?, ?, ?, ?, ?, ?)
    """, (username, hashed, "AdminTG", "USDTwalletHere", 0, int(time.time()), 1))

    conn.commit()
    conn.close()
    print("👑 Admin user created: admin / admin123")

if __name__ == "__main__":
    reset_db()
