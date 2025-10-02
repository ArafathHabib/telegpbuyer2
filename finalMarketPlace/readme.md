# Telegram Group Marketplace

A complete marketplace platform for buying and selling Telegram groups with automated verification.

## 🚀 Features

- **Multi-session support**: Separate checker and receiver accounts
- **Automated verification**: Checks for crypto content, location groups, imported history, etc.
- **Real ownership transfer**: Verifies CREATOR status (not just admin)
- **Session failover**: Automatically moves to next session if current one fails
- **Group limits**: Max 10 groups per receiver account
- **Bulk submissions**: Add multiple groups at once
- **Premium UI**: Modern, glassmorphic design
- **Secure payments**: USDT withdrawal system

## 📁 Project Structure

```
project/
├── main.py                      # FastAPI application entry point
├── config.py                    # Configuration settings
├── database.py                  # Database operations
├── auth.py                      # Authentication decorators
├── telegram_handler.py          # Telegram/Telethon logic
├── routes/
│   ├── __init__.py
│   ├── user_routes.py          # Login, register, profile
│   ├── listing_routes.py       # Sell, status, transfer
│   ├── admin_routes.py         # Admin dashboard
│   └── telegram_routes.py      # Telegram account management
├── templates/
│   ├── template_loader.py      # Jinja2 template loader
│   ├── base.html               # Base template
│   ├── index.html              # Homepage
│   ├── login.html              # Login page
│   ├── register.html           # Registration page
│   ├── sell.html               # Sell groups page
│   ├── profile.html            # User profile
│   ├── withdraw.html           # Withdrawal page
│   ├── campaigns.html          # All campaigns
│   ├── admin.html              # Admin dashboard
│   └── telegram_login.html     # Telegram account login
├── static/
│   └── styles.css              # CSS styles
├── requirements.txt            # Python dependencies
└── README.md                   # This file
```

## 🛠️ Installation

### 1. Clone or Download

Download all files to your project directory.

### 2. Install Dependencies

```bash
pip install -r requirements.txt
```

### 3. Environment Variables (Optional)

Create a `.env` file or set environment variables:

```bash
# Database
DB_PATH=sellgroup.db

# Admin API Tokens (comma-separated)
ADMIN_API_TOKENS=your_secure_token_here

# Server
WEB_HOST=0.0.0.0
WEB_PORT=8000

# Telegram API (get from my.telegram.org)
TELEGRAM_API_ID=your_api_id
TELEGRAM_API_HASH=your_api_hash
```

### 4. Initialize Database

```bash
python test.py
```

This will verify your setup and create the database.

### 5. Run the Application

```bash
python main.py
```

Or with uvicorn directly:

```bash
uvicorn main:app --host 0.0.0.0 --port 8000 --reload
```

## 📋 First-Time Setup

### 1. Access Admin Panel

Navigate to: `http://localhost:8000/admin?token=admin123`

(Replace `admin123` with your actual admin token)

### 2. Add Telegram Accounts

1. Go to **Telegram Accounts** section
2. Click **Add Account**
3. Choose account type:
   - **Checker**: Joins groups and verifies them
   - **Receiver**: Receives group ownership after verification
4. Enter phone number with country code (+1234567890)
5. Enter verification code from Telegram
6. If 2FA enabled, enter password

Add at least:
- 1 checker account (recommended: 2-3 for redundancy)
- 1 receiver account (add more as needed, max 10 groups each)

### 3. Create Campaigns

1. In admin panel, fill out **Create Campaign** form:
   - **Title**: e.g., "2020 Groups"
   - **Year**: e.g., 2020
   - **Price USD**: e.g., 50
   - **Target count**: e.g., 100
2. Click **Create**

### 4. Test the System

1. Register a test user account
2. Submit a test group
3. Monitor the console logs for verification process
4. Check admin panel for session status

## 🔧 Configuration

### Group Verification Rules

The system automatically rejects groups that:

- Have folder links (`t.me/addlist/`)
- Are not supergroups (must be megagroup)
- Have hidden message history
- Started in a different year than campaign
- Contain crypto keywords (investment, ICO, staking, etc.)
- Are location-based groups
- Have been imported from another platform
- Have excessive member additions (>50 in recent messages)
- Have excessive member removals (>50 in recent messages)

### Business Rules

- **Minimum withdrawal**: $10
- **Max groups per receiver**: 10
- **Session types**: Checker (verifies) and Receiver (collects ownership)
- **Ownership verification**: Must be CREATOR, not just admin

## 🔐 Security

### Admin Access

Admin panel requires either:
1. Admin token in URL: `/admin?token=your_token`
2. Logged in as admin user (is_admin=1 in database)

### User Authentication

- Cookie-based sessions (httponly)
- SHA256 password hashing
- 30-day session duration

## 📊 Database Schema

### Tables

**users**
- id, username, password_hash, telegram_username, usdt_wallet, balance, created_ts, is_admin

**campaigns**
- id, title, year, price_usd, target_count, sold_count, created_ts

**listings**
- id, user_id, campaign_id, group_link, seller_tg, seller_usdt, price_usd, status, check_reason, check_log, checked_by_session, receiver_session, created_ts, transferred_ts

**withdrawals**
- id, user_id, listing_id, seller_usdt, amount_usdt, status, txid, created_ts, paid_ts

**admin_sessions**
- id, session_text, username, session_type, status, groups_received, last_used_ts

## 🔄 Workflow

### For Sellers

1. Register account with Telegram username and USDT wallet
2. Browse active campaigns
3. Click "Sell Now" on desired campaign
4. Submit group link(s) - can add multiple
5. System automatically verifies group
6. If approved, transfer CREATOR ownership to specified account
7. Click "I Transferred Creator Rights"
8. System verifies ownership transfer
9. Payment added to balance instantly
10. Request withdrawal (min $10)

### For Admins

1. Add Telegram checker accounts (for verification)
2. Add Telegram receiver accounts (for collecting groups)
3. Create campaigns with year, price, target
4. Monitor verification progress
5. Process withdrawal requests
6. Mark payments as paid with TXID

### System Process

1. User submits group → Status: `pending`
2. Checker account joins group → Runs all checks
3. If fails → Status: `failed` with reason
4. If passes → Status: `ready_for_transfer`
5. Assigns available receiver account
6. User transfers CREATOR ownership
7. User confirms transfer
8. System verifies CREATOR status
9. If verified → Status: `sold`, balance updated
10. If not verified → Error message shown

## 🐛 Troubleshooting

### "No available checker sessions"

**Solution**: Add more checker accounts in admin panel

### "Receiver session offline"

**Solution**: 
1. Check admin panel session status
2. Restart application to reload sessions
3. Add new receiver account if needed

### "User is ChannelParticipantAdmin, not CREATOR"

**Problem**: User transferred admin rights, not creator ownership

**Solution**: User must transfer CREATOR ownership:
1. Open group in Telegram
2. Group Info → Edit → Administrators
3. Find receiver account
4. Tap their name → Transfer Ownership

### Database locked errors

**Solution**: 
- SQLite doesn't handle high concurrency well
- For production, migrate to PostgreSQL
- Or add connection pooling

### Session fails repeatedly

**Solution**:
1. Check if account is banned/limited by Telegram
2. Remove session from database
3. Add new account

## 🚀 Production Deployment

### Using PostgreSQL

1. Install psycopg2: `pip install psycopg2-binary`
2. Update `database.py` to use PostgreSQL
3. Set DATABASE_URL environment variable

### Using Docker

Create `Dockerfile`:

```dockerfile
FROM python:3.11-slim

WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

CMD ["python", "main.py"]
```

Build and run:
```bash
docker build -t tg-marketplace .
docker run -p 8000:8000 -v $(pwd)/data:/app/data tg-marketplace
```

### Using Systemd (Linux)

Create `/etc/systemd/system/tg-marketplace.service`:

```ini
[Unit]
Description=Telegram Group Marketplace
After=network.target

[Service]
Type=simple
User=www-data
WorkingDirectory=/var/www/tg-marketplace
ExecStart=/usr/bin/python3 /var/www/tg-marketplace/main.py
Restart=always

[Install]
WantedBy=multi-user.target
```

Enable and start:
```bash
sudo systemctl enable tg-marketplace
sudo systemctl start tg-marketplace
```

### Nginx Reverse Proxy

```nginx
server {
    listen 80;
    server_name yourdomain.com;

    location / {
        proxy_pass http://127.0.0.1:8000;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
    }
}
```

## 📝 API Endpoints

### Public Routes
- `GET /` - Homepage
- `GET /login` - Login page
- `POST /login` - Process login
- `GET /register` - Registration page
- `POST /register` - Process registration
- `GET /logout` - Logout
- `GET /campaigns` - All campaigns

### User Routes (Authentication Required)
- `GET /profile` - User profile
- `GET /sell?cid={id}` - Sell page for campaign
- `POST /sell` - Submit groups
- `GET /status/{listing_id}` - Check listing status
- `POST /transfer/{listing_id}` - Confirm transfer
- `GET /withdraw` - Withdrawal page
- `POST /withdraw` - Request withdrawal

### Admin Routes (Admin Required)
- `GET /admin` - Admin dashboard
- `POST /admin/campaign` - Create campaign
- `POST /admin/del_campaign/{id}` - Delete campaign
- `POST /admin/pay/{withdrawal_id}` - Mark withdrawal paid
- `GET /admin/telegram_login` - Add Telegram account
- `POST /admin/telegram_login` - Process Telegram login

## 🎨 Customization

### Styling

Edit `static/styles.css` to customize colors and design.

CSS variables in `:root`:
```css
--primary: #7b61ff;
--secondary: #4dd0ff;
--accent: #9fe8c6;
--dark: #06060a;
```

### Templates

All templates in `templates/` directory use Jinja2.

Modify `templates/base.html` to change overall layout.

### Verification Rules

Edit `config.py` to modify keyword lists:
- `CRYPTO_KEYWORDS`
- `LOCATION_KEYWORDS`
- `IMPORTED_KEYWORDS`
- `ADDED_KEYWORDS`
- `REMOVED_KEYWORDS`

## 📞 Support

For issues or questions:
1. Check troubleshooting section
2. Review console logs for errors
3. Verify Telegram account status
4. Check database for session status

## ⚠️ Important Notes

1. **Telegram API Limits**: Don't spam group joins. Telegram may temporarily ban accounts that join too many groups too quickly.

2. **Session Security**: Keep `admin_sessions.session_text` secure. These contain full account access.

3. **Backup Database**: Regularly backup your `sellgroup.db` file.

4. **Rate Limiting**: Consider adding rate limiting for production use.

5. **HTTPS**: Always use HTTPS in production for security.

## 📄 License

This project is for educational purposes. Ensure compliance with Telegram's Terms of Service and local laws.#   f i n a l M a r k e t P l a c e  
 