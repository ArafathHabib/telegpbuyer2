"""
User-related routes: login, register, profile, withdraw
"""
import time
import sqlite3  # ADD THIS IMPORT
from fastapi import APIRouter, Request, Form
from fastapi.responses import HTMLResponse, RedirectResponse
from jinja2 import Template

from auth import get_current_user, login_required
from database import get_connection, create_user, verify_user_password
from config import USDT_NETWORK, MIN_WITHDRAWAL_AMOUNT
from templates.template_loader import load_template

router = APIRouter()


@router.get('/', response_class=HTMLResponse)
async def index(request: Request):
    """Home page"""
    user = get_current_user(request)
    
    conn = get_connection()
    cursor = conn.cursor()
    
    # Get campaigns
    cursor.execute(
    'SELECT id, title, year, month, price_usd, target_count, sold_count FROM campaigns ORDER BY id DESC'
    )
    campaigns = []
    for row in cursor.fetchall():
        target_count = row[5]
        sold_count = row[6]
        progress = int((sold_count / target_count) * 100) if target_count > 0 else 0
        campaigns.append({
            'id': row[0],
            'title': row[1],
            'year': row[2],
            'month': row[3],
            'price_usd': row[4],
            'target_count': target_count,
            'sold_count': sold_count,
            'progress': progress
        })


    
    # Get user listings if logged in
    user_listings = []
    if user:
        cursor.execute(
            '''SELECT l.id, l.group_link, l.status, c.title, l.price_usd, l.created_ts 
               FROM listings l 
               LEFT JOIN campaigns c ON l.campaign_id = c.id 
               WHERE l.user_id = ? 
               ORDER BY l.created_ts DESC LIMIT 5''',
            (user['id'],)
        )
        for row in cursor.fetchall():
            user_listings.append({
                'id': row[0],
                'group_link': row[1],
                'status': row[2],
                'campaign_title': row[3],
                'price_usd': row[4],
                'created_ts': time.strftime('%Y-%m-%d', time.localtime(row[5]))
            })
    
    conn.close()
    
    return load_template('index.html', {
        'user': user,
        'campaigns': campaigns,
        'user_listings': user_listings,
        'network': USDT_NETWORK,
        'is_admin': user and user.get('is_admin')
    })


@router.get('/login', response_class=HTMLResponse)
async def login_form(request: Request, error: str = None):
    """Login page"""
    return load_template('login.html', {'error': error})


@router.post('/login')
async def login(request: Request, username: str = Form(...), password: str = Form(...)):
    """Process login"""
    user_id = verify_user_password(username, password)
    
    if not user_id:
        return RedirectResponse('/login?error=Invalid+credentials', status_code=303)
    
    response = RedirectResponse('/', status_code=303)
    response.set_cookie('uid', str(user_id), httponly=True, max_age=2592000)
    return response


@router.get('/register', response_class=HTMLResponse)
async def register_form(request: Request, error: str = None):
    """Registration page"""
    return load_template('register.html', {'error': error})


@router.post('/register')
async def register(
    request: Request,
    username: str = Form(...),
    password: str = Form(...),
    telegram_username: str = Form(...),
    usdt_wallet: str = Form(...)
):
    """Process registration"""
    user_id = create_user(username, password, telegram_username, usdt_wallet, int(time.time()))
    
    if not user_id:
        return RedirectResponse('/register?error=Username+already+exists', status_code=303)
    
    response = RedirectResponse('/', status_code=303)
    response.set_cookie('uid', str(user_id), httponly=True, max_age=2592000)
    return response


@router.get('/logout')
async def logout():
    """Logout"""
    response = RedirectResponse('/')
    response.delete_cookie('uid')
    return response


@router.get('/campaigns', response_class=HTMLResponse)
async def campaigns_page(request: Request):
    """All campaigns page"""
    user = get_current_user(request)
    
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute(
    'SELECT id, title, year, month, price_usd, target_count, sold_count FROM campaigns ORDER BY id DESC'
    )
    campaigns = []
    for row in cursor.fetchall():
        target_count = row[5]
        sold_count = row[6]
        progress = int((sold_count / target_count) * 100) if target_count > 0 else 0
        campaigns.append({
            'id': row[0],
            'title': row[1],
            'year': row[2],
            'month': row[3],
            'price_usd': row[4],
            'target_count': target_count,
            'sold_count': sold_count,
            'progress': progress
        })

    
    conn.close()
    
    return load_template('campaigns.html', {'user': user, 'campaigns': campaigns})


@router.get('/profile', response_class=HTMLResponse)
@login_required
async def profile(request: Request):
    """User profile page"""
    user = get_current_user(request)
    
    conn = get_connection()
    cursor = conn.cursor()
    
    # Get stats
    cursor.execute('SELECT COUNT(*) FROM listings WHERE user_id=?', (user['id'],))
    total = cursor.fetchone()[0]
    
    cursor.execute('SELECT COUNT(*) FROM listings WHERE user_id=? AND status="sold"', (user['id'],))
    sold = cursor.fetchone()[0]
    
    stats = {'total': total, 'sold': sold}
    
    # Get listings
    cursor.execute(
        '''SELECT l.id, l.group_link, l.status, l.price_usd, l.check_log, c.title, l.created_ts, l.receiver_session 
           FROM listings l 
           LEFT JOIN campaigns c ON l.campaign_id = c.id 
           WHERE l.user_id = ? 
           ORDER BY l.created_ts DESC''',
        (user['id'],)
    )
    
    listings = []
    for row in cursor.fetchall():
        target_username = None
        if row[7]:
            cursor.execute('SELECT username FROM admin_sessions WHERE id=?', (row[7],))
            session = cursor.fetchone()
            if session:
                target_username = session[0]
        
        listings.append({
            'id': row[0],
            'group_link': row[1],
            'status': row[2],
            'price_usd': row[3],
            'check_log': row[4],
            'campaign_title': row[5],
            'created_ts': time.strftime('%Y-%m-%d', time.localtime(row[6])),
            'target_username': target_username
        })
    
    # Get withdrawals
    cursor.execute(
        'SELECT amount_usdt, seller_usdt, status, created_ts FROM withdrawals WHERE user_id=? ORDER BY created_ts DESC',
        (user['id'],)
    )
    
    withdrawals = []
    for row in cursor.fetchall():
        withdrawals.append({
            'amount_usdt': row[0],
            'seller_usdt': row[1],
            'status': row[2],
            'created_ts': time.strftime('%Y-%m-%d', time.localtime(row[3]))
        })
    
    conn.close()
    
    return load_template('profile.html', {
        'user': user,
        'stats': stats,
        'listings': listings,
        'withdrawals': withdrawals
    })


@router.get('/withdraw', response_class=HTMLResponse)
@login_required
async def withdraw_page(request: Request):
    """Withdrawal page"""
    user = get_current_user(request)
    
    conn = get_connection()
    cursor = conn.cursor()
    
    # Get pending withdrawals
    cursor.execute(
        'SELECT amount_usdt, status, created_ts FROM withdrawals WHERE user_id=? AND status="pending" ORDER BY created_ts DESC',
        (user['id'],)
    )
    
    pending_withdrawals = []
    for row in cursor.fetchall():
        pending_withdrawals.append({
            'amount_usdt': row[0],
            'status': row[1],
            'created_ts': time.strftime('%Y-%m-%d %H:%M', time.localtime(row[2]))
        })
    
    conn.close()
    
    return load_template('withdraw.html', {
        'user': user,
        'network': USDT_NETWORK,
        'pending_withdrawals': pending_withdrawals,
        'min_amount': MIN_WITHDRAWAL_AMOUNT
    })


@router.post('/withdraw')
@login_required
async def process_withdrawal(request: Request, amount: float = Form(...)):
    """Process withdrawal request and post to channel"""
    user = get_current_user(request)
    
    if amount < MIN_WITHDRAWAL_AMOUNT:
        return RedirectResponse(f'/withdraw?error=Minimum+withdrawal+is+${MIN_WITHDRAWAL_AMOUNT}', status_code=303)
    
    if amount > user['balance']:
        return RedirectResponse('/withdraw?error=Insufficient+balance', status_code=303)
    
    conn = get_connection()
    cursor = conn.cursor()
    
    try:
        # Start transaction
        # 1. Deduct from user balance immediately
        cursor.execute(
            'UPDATE users SET balance = balance - ? WHERE id=? AND balance >= ?',
            (amount, user['id'], amount)
        )
        
        if cursor.rowcount == 0:
            conn.close()
            return RedirectResponse('/withdraw?error=Insufficient+balance+or+concurrent+withdrawal', status_code=303)
        
        # 2. Get groups that haven't been included in withdrawals yet
        # Use try-except to handle potential missing column
        try:
            cursor.execute(
                '''SELECT l.id, l.group_link, l.price_usd, l.receiver_session, a.username
                   FROM listings l
                   LEFT JOIN admin_sessions a ON l.receiver_session = a.id
                   WHERE l.user_id = ? AND l.status = 'sold' AND l.included_in_withdrawal = 0
                   ORDER BY l.transferred_ts ASC''',
                (user['id'],)
            )
        except sqlite3.OperationalError:
            # If column doesn't exist, get all sold groups
            cursor.execute(
                '''SELECT l.id, l.group_link, l.price_usd, l.receiver_session, a.username
                   FROM listings l
                   LEFT JOIN admin_sessions a ON l.receiver_session = a.id
                   WHERE l.user_id = ? AND l.status = 'sold'
                   ORDER BY l.transferred_ts ASC''',
                (user['id'],)
            )
        
        groups_data = cursor.fetchall()
        
        groups_info = []
        listing_ids = []
        for row in groups_data:
            listing_ids.append(row[0])
            groups_info.append({
                'link': row[1],
                'price': row[2],
                'receiver': row[3] or 'Unknown'
            })
        
        # 3. Create withdrawal record
        cursor.execute(
            'INSERT INTO withdrawals (user_id, seller_usdt, amount_usdt, status, created_ts) VALUES (?, ?, ?, "pending", ?)',
            (user['id'], user['usdt_wallet'], amount, int(time.time()))
        )
        withdrawal_id = cursor.lastrowid
        
        # 4. Mark groups as included in withdrawal (if column exists)
        if listing_ids:
            try:
                placeholders = ','.join('?' * len(listing_ids))
                cursor.execute(
                    f'UPDATE listings SET included_in_withdrawal = 1 WHERE id IN ({placeholders})',
                    listing_ids
                )
            except sqlite3.OperationalError:
                # Column doesn't exist, skip this step
                pass
        
        conn.commit()
        
        # 5. Post to withdrawal request channel (optional)
        try:
            from telegram_handler import get_withdrawal_sessions, post_withdrawal_request
            from datetime import datetime
            
            withdrawal_sessions = await get_withdrawal_sessions()
            
            if withdrawal_sessions['request']:
                withdrawal_data = {
                    'id': withdrawal_id,
                    'username': user['username'],
                    'telegram': user['telegram_username'],
                    'amount': amount,
                    'wallet': user['usdt_wallet'],
                    'groups': groups_info,
                    'date': datetime.now().strftime('%Y-%m-%d %H:%M')
                }
                
                success, msg_id, error = await post_withdrawal_request(
                    withdrawal_sessions['request'],
                    withdrawal_data
                )
                
                if success:
                    # Update withdrawal with message ID
                    try:
                        cursor.execute(
                            'UPDATE withdrawals SET withdrawal_request_msg_id = ? WHERE id = ?',
                            (msg_id, withdrawal_id)
                        )
                        conn.commit()
                    except sqlite3.OperationalError:
                        pass  # Column doesn't exist
        except Exception as e:
            print(f"Warning: Failed to post withdrawal request: {e}")
        
        conn.close()
        
        return RedirectResponse('/withdraw?success=Withdrawal+requested+successfully', status_code=303)
        
    except Exception as e:
        conn.rollback()
        conn.close()
        return RedirectResponse(f'/withdraw?error=Withdrawal+failed:+{str(e)}', status_code=303)
    
