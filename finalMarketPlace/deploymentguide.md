# Complete Deployment Guide

## Quick Start Checklist

- [ ] Python 3.9+ installed
- [ ] All files in project directory
- [ ] Dependencies installed
- [ ] Telegram API credentials obtained
- [ ] Database initialized
- [ ] At least 1 checker account added
- [ ] At least 1 receiver account added
- [ ] First campaign created
- [ ] Test submission completed

## Step-by-Step Setup

### 1. Project Structure Setup

Create the following directory structure:

```
project/
├── main.py
├── config.py
├── database.py
├── auth.py
├── telegram_handler.py
├── test.py
├── requirements.txt
├── README.md
├── routes/
│   ├── __init__.py
│   ├── user_routes.py
│   ├── listing_routes.py
│   ├── admin_routes.py
│   └── telegram_routes.py
├── templates/
│   ├── template_loader.py
│   ├── base.html
│   ├── index.html
│   ├── login.html
│   ├── register.html
│   ├── sell.html
│   ├── profile.html
│   ├── withdraw.html
│   ├── campaigns.html
│   ├── admin.html
│   └── telegram_login.html
└── static/
    └── styles.css
```

### 2. Get Telegram API Credentials

1. Visit https://my.telegram.org
2. Login with your phone number
3. Go to "API development tools"
4. Create a new application
5. Note down:
   - `api_id` (numbers)
   - `api_hash` (letters and numbers)

### 3. Environment Setup

Option A: Using `.env` file (recommended)

Create `.env` file:
```bash
TELEGRAM_API_ID=your_api_id_here
TELEGRAM_API_HASH=your_api_hash_here
ADMIN_API_TOKENS=your_secret_token_here,another_token
DB_PATH=sellgroup.db
WEB_HOST=0.0.0.0
WEB_PORT=8000
```

Install python-dotenv:
```bash
pip install python-dotenv
```

Update `config.py` to load from .env:
```python
from dotenv import load_dotenv
load_dotenv()
```

Option B: Export environment variables

```bash
export TELEGRAM_API_ID=12345678
export TELEGRAM_API_HASH=abcdef1234567890
export ADMIN_API_TOKENS=mysecrettoken123
```

### 4. Install Dependencies

```bash
pip install -r requirements.txt
```

For production with PostgreSQL:
```bash
pip install psycopg2-binary sqlalchemy
```

### 5. Run Tests

```bash
python test.py
```

Expected output:
```
============================================================
SETUP VERIFICATION TEST
============================================================
Testing imports...
✓ config.py imported
✓ database.py imported
✓ auth.py imported
✓ FastAPI available
✓ Telethon available
...
✓ All tests passed! Ready to proceed.
```

### 6. Start Application

```bash
python main.py
```

Application will start on http://localhost:8000

### 7. Initial Admin Setup

#### 7.1 Access Admin Panel

Navigate to: `http://localhost:8000/admin?token=your_token_here`

Replace `your_token_here` with the token from your config.

#### 7.2 Add Telegram Checker Account

1. Click "Add Account" button
2. Select "Checker (joins & verifies groups)"
3. Enter phone number with country code: `+1234567890`
4. Click "Send Code"
5. Check your Telegram app for verification code
6. Enter the 5-digit code
7. If 2FA enabled, enter your password
8. Wait for "✅ Checker account added successfully"

#### 7.3 Add Telegram Receiver Account

Repeat above steps but select "Receiver (receives group ownership)"

Recommended setup:
- 2-3 checker accounts (for redundancy)
- 2-3 receiver accounts (each can hold max 10 groups)

#### 7.4 Create First Campaign

In admin panel:
1. Fill "Create Campaign" form:
   - Title: `2020 Premium Groups`
   - Year: `2020`
   - Price USD: `50.00`
   - Target count: `100`
2. Click "Create"

### 8. Test the System

#### 8.1 Register Test User

1. Go to homepage
2. Click "Sign Up"
3. Fill form:
   - Username: `testuser`
   - Password: `testpass123`
   - Telegram: `@testuser`
   - USDT Wallet: `0x742d35Cc6634C0532925a3b844Bc9e7595f0bEb`
4. Click "Sign Up"

#### 8.2 Submit Test Group

1. Click "SELL NOW" on a campaign
2. Enter a test group link (must match campaign year)
3. Click "Submit & Auto-Check All"
4. Monitor console logs for verification process

#### 8.3 Monitor Progress

Watch the terminal/console output:
```
Checking listing 1 with checker session 1 (attempt 1)
✓ Listing 1 passed checks, assigned to receiver 1
```

#### 8.4 Complete Transfer

1. In Telegram, transfer CREATOR ownership to receiver account
2. In profile page, click "Transfer Ownership"
3. Click "I Transferred Creator Rights"
4. System verifies ownership
5. Balance updated

### 9. Production Deployment

#### Option A: Ubuntu/Debian Server

```bash
# Update system
sudo apt update && sudo apt upgrade -y

# Install Python 3.11
sudo apt install python3.11 python3.11-venv python3-pip -y

# Create app directory
sudo mkdir -p /var/www/tg-marketplace
sudo chown $USER:$USER /var/www/tg-marketplace
cd /var/www/tg-marketplace

# Upload all project files here

# Create virtual environment
python3.11 -m venv venv
source venv/bin/activate

# Install dependencies
pip install -r requirements.txt

# Set environment variables
sudo nano /etc/environment
# Add your variables here

# Create systemd service
sudo nano /etc/systemd/system/tg-marketplace.service
```

Service file content:
```ini
[Unit]
Description=Telegram Group Marketplace
After=network.target

[Service]
Type=simple
User=www-data
WorkingDirectory=/var/www/tg-marketplace
Environment="PATH=/var/www/tg-marketplace/venv/bin"
ExecStart=/var/www/tg-marketplace/venv/bin/python main.py
Restart=always
RestartSec=10

[Install]
WantedBy=multi-user.target
```

Enable and start:
```bash
sudo systemctl daemon-reload
sudo systemctl enable tg-marketplace
sudo systemctl start tg-marketplace
sudo systemctl status tg-marketplace
```

#### Option B: Docker Deployment

Create `Dockerfile`:
```dockerfile
FROM python:3.11-slim

WORKDIR /app

# Install dependencies
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy application
COPY . .

# Create data directory
RUN mkdir -p /app/data

# Expose port
EXPOSE 8000

# Run application
CMD ["python", "main.py"]
```

Create `docker-compose.yml`:
```yaml
version: '3.8'

services:
  app:
    build: .
    ports:
      - "8000:8000"
    volumes:
      - ./data:/app/data
    environment:
      - TELEGRAM_API_ID=${TELEGRAM_API_ID}
      - TELEGRAM_API_HASH=${TELEGRAM_API_HASH}
      - ADMIN_API_TOKENS=${ADMIN_API_TOKENS}
      - DB_PATH=/app/data/sellgroup.db
    restart: unless-stopped
```

Deploy:
```bash
docker-compose up -d
```

### 10. Nginx Configuration

Install Nginx:
```bash
sudo apt install nginx -y
```

Create config:
```bash
sudo nano /etc/nginx/sites-available/tg-marketplace
```

Config content:
```nginx
server {
    listen 80;
    server_name yourdomain.com;

    # Redirect HTTP to HTTPS
    return 301 https://$server_name$request_uri;
}

server {
    listen 443 ssl http2;
    server_name yourdomain.com;

    # SSL certificates (use Let's Encrypt)
    ssl_certificate /etc/letsencrypt/live/yourdomain.com/fullchain.pem;
    ssl_certificate_key /etc/letsencrypt/live/yourdomain.com/privkey.pem;

    # Security headers
    add_header X-Frame-Options "SAMEORIGIN" always;
    add_header X-Content-Type-Options "nosniff" always;
    add_header X-XSS-Protection "1; mode=block" always;

    location / {
        proxy_pass http://127.0.0.1:8000;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
    }
}
```

Enable site:
```bash
sudo ln -s /etc/nginx/sites-available/tg-marketplace /etc/nginx/sites-enabled/
sudo nginx -t
sudo systemctl reload nginx
```

### 11. SSL Certificate (Let's Encrypt)

```bash
sudo apt install certbot python3-certbot-nginx -y
sudo certbot --nginx -d yourdomain.com
```

### 12. Database Backup

Create backup script `/usr/local/bin/backup-tg-marketplace.sh`:
```bash
#!/bin/bash
BACKUP_DIR="/var/backups/tg-marketplace"
DB_PATH="/var/www/tg-marketplace/sellgroup.db"
DATE=$(date +%Y%m%d_%H%M%S)

mkdir -p $BACKUP_DIR
cp $DB_PATH "$BACKUP_DIR/sellgroup_$DATE.db"

# Keep only last 30 backups
ls -t $BACKUP_DIR/sellgroup_*.db | tail -n +31 | xargs rm -f
```

Make executable and add to cron:
```bash
sudo chmod +x /usr/local/bin/backup-tg-marketplace.sh
sudo crontab -e
```

Add line:
```
0 2 * * * /usr/local/bin/backup-tg-marketplace.sh
```

### 13. Monitoring

#### Check application logs:
```bash
sudo journalctl -u tg-marketplace -f
```

#### Check Nginx logs:
```bash
sudo tail -f /var/log/nginx/access.log
sudo tail -f /var/log/nginx/error.log
```

#### Monitor system resources:
```bash
htop
```

### 14. Maintenance

#### Restart application:
```bash
sudo systemctl restart tg-marketplace
```

#### Update application:
```bash
cd /var/www/tg-marketplace
git pull  # if using git
sudo systemctl restart tg-marketplace
```

#### Clear stuck listings:
```sql
sqlite3 sellgroup.db
UPDATE listings SET status='failed', check_reason='manual_reset' WHERE status='pending' AND created_ts < strftime('%s', 'now') - 3600;
.quit
```

## Troubleshooting Production Issues

### High CPU Usage

Check number of concurrent verifications. Limit by adding delay in checker_worker:
```python
await asyncio.sleep(5)  # Increase from 2 to 5 seconds
```

### Memory Leaks

Restart service daily:
```bash
sudo crontab -e
# Add: 0 4 * * * systemctl restart tg-marketplace
```

### Telegram Rate Limits

Symptoms: "FloodWaitError"

Solution:
1. Add more checker accounts
2. Increase delays between operations
3. Reduce verification concurrency

### Database Locked

For high traffic, migrate to PostgreSQL:
```bash
pip install psycopg2-binary sqlalchemy alembic
```

## Security Checklist

- [ ] Change default admin token
- [ ] Use HTTPS (SSL certificate)
- [ ] Enable firewall (ufw)
- [ ] Regular database backups
- [ ] Keep dependencies updated
- [ ] Monitor logs for suspicious activity
- [ ] Use strong passwords for Telegram accounts
- [ ] Restrict SSH access
- [ ] Enable fail2ban

## Performance Optimization

### For High Traffic

1. Use PostgreSQL instead of SQLite
2. Add Redis for caching
3. Use Gunicorn with multiple workers
4. Enable Nginx caching
5. Add CDN for static files
6. Implement rate limiting

### Example Gunicorn Setup

```bash
pip install gunicorn
gunicorn main:app --workers 4 --worker-class uvicorn.workers.UvicornWorker --bind 0.0.0.0:8000
```

Update systemd service:
```ini
ExecStart=/var/www/tg-marketplace/venv/bin/gunicorn main:app --workers 4 --worker-class uvicorn.workers.UvicornWorker --bind 0.0.0.0:8000
```

## Support & Maintenance

Keep this guide handy for future reference. Document any custom changes you make to the system.

Remember to regularly:
- Check session status
- Monitor verification success rate
- Process withdrawal requests
- Backup database
- Update dependencies
- Review logs for errors