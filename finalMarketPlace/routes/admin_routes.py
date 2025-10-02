"""
Admin routes: dashboard, campaigns, sessions, withdrawals
"""
import time
from fastapi import APIRouter, Request, Form
from fastapi.responses import HTMLResponse, RedirectResponse

from auth import get_current_user, admin_required
from database import get_connection
from config import MAX_GROUPS_PER_RECEIVER
from templates.template_loader import load_template

router = APIRouter()


@router.get('/admin', response_class=HTMLResponse)
@admin_required
async def admin_dashboard(request: Request):
    """Admin dashboard"""
    user = get_current_user(request)
    
    # Get the token from query params
    token = request.query_params.get('token', '')
    
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

    
    # Get Telegram accounts/sessions
    cursor.execute(
        'SELECT id, username, session_type, status, groups_received, last_used_ts FROM admin_sessions ORDER BY session_type, id'
    )
    accounts = []
    for row in cursor.fetchall():
        accounts.append({
            'id': row[0],
            'username': row[1],
            'session_type': row[2],
            'status': row[3],
            'groups_received': row[4],
            'last_used': time.strftime('%Y-%m-%d %H:%M', time.localtime(row[5])) if row[5] else 'Never'
        })
    
    # Get pending withdrawals
    cursor.execute(
        'SELECT id, seller_usdt, amount_usdt FROM withdrawals WHERE status="pending"'
    )
    withdrawals = []
    for row in cursor.fetchall():
        withdrawals.append({
            'id': row[0],
            'seller_usdt': row[1],
            'amount_usdt': row[2]
        })
    
    conn.close()
    
    return load_template('admin.html', {
        'user': user,
        'campaigns': campaigns,
        'accounts': accounts,
        'withdrawals': withdrawals,
        'max_groups': MAX_GROUPS_PER_RECEIVER,
        'token': token  # ADD THIS LINE - pass token to template
    })


@router.post('/admin/campaign')
@admin_required
async def create_campaign(
    request: Request,
    title: str = Form(...),
    year: int = Form(...),
    month: int = Form(None),  # ADD THIS: month can be None
    price_usd: float = Form(...),
    target: int = Form(...),
    token: str = Form(None)
):
    """Create new campaign with optional month"""
    # Convert empty month to None
    if month == "" or month is None:
        month_value = None
    else:
        month_value = int(month)
    
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute(
        'INSERT INTO campaigns (title, year, month, price_usd, target_count, created_ts) VALUES (?, ?, ?, ?, ?, ?)',
        (title, year, month_value, price_usd, target, int(time.time()))
    )
    conn.commit()
    conn.close()
    
    return RedirectResponse(f'/admin?token={token}' if token else '/admin', status_code=303)


@router.post('/admin/del_campaign/{campaign_id}')
@admin_required
async def delete_campaign(request: Request, campaign_id: int):
    """Delete campaign"""
    # GET TOKEN FROM QUERY PARAMS
    token = request.query_params.get('token', '')
    
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute('DELETE FROM campaigns WHERE id=?', (campaign_id,))
    conn.commit()
    conn.close()
    
    # ADD TOKEN TO REDIRECT
    return RedirectResponse(f'/admin?token={token}' if token else '/admin', status_code=303)


@router.post('/admin/pay/{withdrawal_id}')
@admin_required
async def mark_paid(request: Request, withdrawal_id: int, txid: str = Form(...)):
    """Mark withdrawal as paid and post to public channel"""
    token = request.query_params.get('token', '')
    
    conn = get_connection()
    cursor = conn.cursor()
    
    try:
        # Get withdrawal details
        cursor.execute(
            '''SELECT w.user_id, w.amount_usdt, w.status, u.username
               FROM withdrawals w
               JOIN users u ON w.user_id = u.id
               WHERE w.id = ?''',
            (withdrawal_id,)
        )
        row = cursor.fetchone()
        
        if not row:
            conn.close()
            return RedirectResponse(f'/admin?token={token}&error=Withdrawal+not+found', status_code=303)
        
        user_id, amount, current_status, username = row
        
        if current_status == 'paid':
            conn.close()
            return RedirectResponse(f'/admin?token={token}&error=Withdrawal+already+paid', status_code=303)
        
        # Update withdrawal status
        cursor.execute(
            'UPDATE withdrawals SET status="paid", txid=?, paid_ts=? WHERE id=?',
            (txid, int(time.time()), withdrawal_id)
        )
        
        conn.commit()
        
        # Post to public payment channel
        from telegram_handler import get_withdrawal_sessions, post_withdrawal_paid
        from datetime import datetime
        from config import USDT_NETWORK
        
        withdrawal_sessions = await get_withdrawal_sessions()
        
        if withdrawal_sessions['paid']:
            payment_data = {
                'username': username,
                'amount': amount,
                'txid': txid,
                'network': USDT_NETWORK,
                'date': datetime.now().strftime('%Y-%m-%d %H:%M')
            }
            
            success, error = await post_withdrawal_paid(
                withdrawal_sessions['paid'],
                payment_data
            )
            
            if not success:
                print(f"Failed to post payment: {error}")
        
        conn.close()
        
        return RedirectResponse(f'/admin?token={token}&success=Withdrawal+marked+as+paid', status_code=303)
        
    except Exception as e:
        conn.rollback()
        conn.close()
        return RedirectResponse(f'/admin?token={token}&error=Failed+to+mark+paid:+{str(e)}', status_code=303)