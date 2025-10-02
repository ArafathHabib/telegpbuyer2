"""
Listing-related routes: sell, status check, transfer
"""
import time
from fastapi import APIRouter, Request, Form
from fastapi.responses import HTMLResponse, JSONResponse
from jinja2 import Template

from auth import get_current_user, login_required
from database import get_connection
from telegram_handler import verify_receiver_ownership
from config import active_telegram_clients
from templates.template_loader import load_template

router = APIRouter()


@router.get('/sell', response_class=HTMLResponse)
@login_required
async def sell_form(request: Request, cid: int = None):
    """Group selling form"""
    user = get_current_user(request)
    
    campaign = None
    if cid:
        conn = get_connection()
        cursor = conn.cursor()
        cursor.execute('SELECT id, title, year, month, price_usd FROM campaigns WHERE id=?', (cid,))
        row = cursor.fetchone()
        conn.close()
        
        if row:
            campaign = {
                'id': row[0],
                'title': row[1],
                'year': row[2],
                'month': row[3],  # ADD THIS
                'price_usd': row[4]
            }
    
    return load_template('sell.html', {'user': user, 'campaign': campaign})


@router.post('/sell')
@login_required
async def create_listing(request: Request):
    """Submit groups for verification - return JSON for AJAX handling"""
    form = await request.form()
    campaign_id = form.get('cid')
    group_links = form.getlist('group_link[]')
    
    if not campaign_id:
        return JSONResponse({
            'status': 'error',
            'message': 'No campaign selected'
        })
    
    if not group_links:
        return JSONResponse({
            'status': 'error',
            'message': 'No groups provided'
        })
    
    try:
        campaign_id = int(campaign_id)
    except:
        return JSONResponse({
            'status': 'error',
            'message': 'Invalid campaign ID'
        })
    
    user = get_current_user(request)
    
    conn = get_connection()
    cursor = conn.cursor()
    
    # Verify campaign exists
    cursor.execute('SELECT price_usd FROM campaigns WHERE id=?', (campaign_id,))
    row = cursor.fetchone()
    
    if not row:
        conn.close()
        return JSONResponse({
            'status': 'error',
            'message': 'Invalid campaign'
        })
    
    price = row[0]
    count = 0
    
    # Create listings
    for link in group_links:
        link = link.strip()
        if link:
            cursor.execute(
                '''INSERT INTO listings 
                   (user_id, campaign_id, group_link, seller_tg, seller_usdt, price_usd, status, created_ts) 
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?)''',
                (user['id'], campaign_id, link, user['telegram_username'], 
                 user['usdt_wallet'], price, 'pending', int(time.time()))
            )
            count += 1
    
    conn.commit()
    conn.close()
    
    return JSONResponse({
        'status': 'success',
        'count': count,
        'message': f'{count} group(s) submitted for checking'
    })


@router.get('/status/{listing_id}')
@login_required
async def check_status(request: Request, listing_id: int):
    """Get listing status"""
    user = get_current_user(request)
    
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute(
        'SELECT status, check_reason, check_log, user_id, receiver_session FROM listings WHERE id=?',
        (listing_id,)
    )
    row = cursor.fetchone()
    
    if not row or row[3] != user['id']:
        conn.close()
        return JSONResponse({
            'status': 'error',
            'message': 'Not found'
        })
    
    target_username = None
    if row[0] == 'ready_for_transfer' and row[4]:
        cursor.execute('SELECT username FROM admin_sessions WHERE id=?', (row[4],))
        session_row = cursor.fetchone()
        if session_row:
            target_username = session_row[0]
    
    conn.close()
    
    return JSONResponse({
        'status': row[0],
        'reason': row[1],
        'log': row[2],
        'target_username': target_username
    })


@router.post('/transfer/{listing_id}')
@login_required
async def confirm_transfer(request: Request, listing_id: int):
    """Confirm ownership transfer and send purchase message"""
    user = get_current_user(request)
    
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute(
        '''SELECT l.user_id, l.receiver_session, l.group_link, l.campaign_id, l.price_usd, l.status, c.year
           FROM listings l
           JOIN campaigns c ON l.campaign_id = c.id
           WHERE l.id=?''',
        (listing_id,)
    )
    row = cursor.fetchone()
    
    if not row or row[0] != user['id']:
        conn.close()
        return JSONResponse({
            'status': 'error',
            'message': 'Not found'
        })
    
    if row[5] != 'ready_for_transfer':
        conn.close()
        return JSONResponse({
            'status': 'error',
            'message': 'Listing not ready for transfer'
        })
    
    receiver_session_id = row[1]
    group_link = row[2]
    campaign_year = row[6]
    
    if not receiver_session_id or receiver_session_id not in active_telegram_clients:
        conn.close()
        return JSONResponse({
            'status': 'error',
            'message': 'Receiver session offline'
        })
    
    # Verify ownership
    verified, message = await verify_receiver_ownership(receiver_session_id, group_link)
    
    if not verified:
        conn.close()
        return JSONResponse({
            'status': 'error',
            'message': message
        })
    
    # Send purchase message in the group
    from telegram_handler import send_purchase_message
    
    msg_sent, msg_status = await send_purchase_message(
        receiver_session_id,
        group_link,
        campaign_year,
        user['telegram_username'],
        row[4]
    )
    
    # Process successful transfer
    now = int(time.time())
    
    cursor.execute(
        'UPDATE listings SET status="sold", transferred_ts=? WHERE id=?',
        (now, listing_id)
    )
    
    # Update user balance
    cursor.execute(
        'UPDATE users SET balance = balance + ? WHERE id=?',
        (row[4], user['id'])
    )
    
    # Update campaign sold count
    cursor.execute(
        'UPDATE campaigns SET sold_count = sold_count + 1 WHERE id=?',
        (row[3],)
    )
    
    # Update receiver session group count
    cursor.execute(
        'UPDATE admin_sessions SET groups_received = groups_received + 1 WHERE id=?',
        (receiver_session_id,)
    )
    
    conn.commit()
    conn.close()
    
    return JSONResponse({
        'status': 'success',
        'amount': row[4],
        'message_sent': msg_sent
    })