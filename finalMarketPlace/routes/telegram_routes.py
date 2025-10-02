"""
Telegram account management routes
"""
import time
from fastapi import APIRouter, Request, Form
from fastapi.responses import HTMLResponse
from telethon import TelegramClient
from telethon.sessions import StringSession

from auth import admin_required
from database import get_connection
from telegram_handler import (
    send_telegram_verification_code,
    verify_telegram_code,
    verify_telegram_password
)
from config import API_ID, API_HASH, active_telegram_clients, MAX_GROUPS_PER_RECEIVER
from templates.template_loader import load_template

router = APIRouter()


@router.get('/admin/telegram_login', response_class=HTMLResponse)
@admin_required
async def telegram_login_form(
    request: Request,
    phone_number: str = "",
    error: str = "",
    success: str = "",
    require_code: bool = False,
    require_password: bool = False,
    session_type: str = "checker",
    channel_id: str = "",
    token: str = ""  # FIXED: Added token parameter
):
    """Telegram account login form"""
    
    # Get token from query params if not provided
    if not token:
        token = request.query_params.get('token', '')
    
    # Get existing sessions
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute(
        '''SELECT id, username, session_type, status, groups_received, last_used_ts, channel_id
           FROM admin_sessions 
           ORDER BY session_type, last_used_ts DESC'''
    )
    sessions = cursor.fetchall()
    conn.close()
    
    sessions_list = []
    for session in sessions:
        last_used = time.strftime('%Y-%m-%d %H:%M', time.localtime(session[5])) if session[5] else 'Never'
        sessions_list.append({
            'id': session[0],
            'username': session[1],
            'session_type': session[2],
            'status': session[3],
            'groups_received': session[4],
            'last_used': last_used,
            'channel_id': session[6] or 'Not set'
        })
    
    return load_template('telegram_login.html', {
        'phone_number': phone_number,
        'error': error,
        'success': success,
        'require_code': require_code,
        'require_password': require_password,
        'session_type': session_type,
        'channel_id': channel_id,  # ADD THIS LINE
        'sessions_list': sessions_list,
        'token': token,
        'max_groups': MAX_GROUPS_PER_RECEIVER
    })


@router.post('/admin/telegram_login', response_class=HTMLResponse)
@admin_required
async def handle_telegram_login(
    request: Request,
    phone_number: str = Form(""),
    session_type: str = Form("checker"),
    channel_id: str = Form(""),  # ADD THIS LINE - accept channel_id from form
    code: str = Form(""),
    password: str = Form(""),
    token: str = Form("")
):
    """Handle Telegram login flow"""
    try:
        # Get token from form or query params
        if not token:
            token = request.query_params.get('token', '')
        
        if not phone_number:
            return await telegram_login_form(
                request=request,
                phone_number=phone_number,
                error="Phone number is required",
                token=token
            )
        
        phone_number = phone_number.strip()
        
        # Validate channel_id for withdrawal sessions
        if session_type in ['withdrawal_request', 'withdrawal_paid'] and not channel_id:
            return await telegram_login_form(
                request=request,
                phone_number=phone_number,
                session_type=session_type,
                error="Channel username is required for withdrawal sessions",
                token=token
            )
        
        # Clean channel_id format
        if channel_id:
            channel_id = channel_id.strip()
            if channel_id.startswith('@'):
                channel_id = channel_id[1:]  # Remove @ if present
            if not channel_id:
                channel_id = None
        
        # Step 1: Send verification code
        if not code and not password:
            success, message = await send_telegram_verification_code(phone_number)
            if success:
                return await telegram_login_form(
                    request=request,
                    phone_number=phone_number,
                    session_type=session_type,
                    channel_id=channel_id,  # PASS CHANNEL_ID
                    require_code=True,
                    success=message,
                    token=token
                )
            else:
                return await telegram_login_form(
                    request=request,
                    phone_number=phone_number,
                    session_type=session_type,
                    channel_id=channel_id,  # PASS CHANNEL_ID
                    error=message,
                    token=token
                )
        
        # Step 2: Verify code
        elif code and not password:
            success, result = await verify_telegram_code(phone_number, code)
            
            if success:
                session_string, me = result
                
                # Save session to database
                conn = get_connection()
                cursor = conn.cursor()
                cursor.execute(
                    '''INSERT INTO admin_sessions 
                    (session_text, username, session_type, status, groups_received, last_used_ts, channel_id) 
                    VALUES (?, ?, ?, ?, ?, ?, ?)''',
                    (session_string, me.username or str(me.id), session_type, 'ready', 0, int(time.time()), channel_id or None)
                )
                session_id = cursor.lastrowid
                conn.commit()
                conn.close()
                
                # Load session into active clients
                client = TelegramClient(StringSession(session_string), API_ID, API_HASH)
                await client.start()
                active_telegram_clients[session_id] = client
                
                return await telegram_login_form(
                    request=request,
                    success=f"✅ {session_type.title()} account added successfully",
                    token=token
                )
            
            elif result == "password_needed":
                return await telegram_login_form(
                    request=request,
                    phone_number=phone_number,
                    session_type=session_type,
                    channel_id=channel_id,  # PASS CHANNEL_ID
                    require_password=True,
                    error="Two-step verification required",
                    token=token
                )
            else:
                return await telegram_login_form(
                    request=request,
                    phone_number=phone_number,
                    session_type=session_type,
                    channel_id=channel_id,  # PASS CHANNEL_ID
                    require_code=True,
                    error=result,
                    token=token
                )
        
        # Step 3: Verify password (2FA)
        elif password:
            success, result = await verify_telegram_password(phone_number, password)
            
            if success:
                session_string, me = result
                
                # Save session to database
                conn = get_connection()
                cursor = conn.cursor()
                cursor.execute(
                    '''INSERT INTO admin_sessions 
                    (session_text, username, session_type, status, groups_received, last_used_ts, channel_id) 
                    VALUES (?, ?, ?, ?, ?, ?, ?)''',
                    (session_string, me.username or str(me.id), session_type, 'ready', 0, int(time.time()), channel_id or None)
                )
                session_id = cursor.lastrowid
                conn.commit()
                conn.close()
                
                # Load session into active clients
                client = TelegramClient(StringSession(session_string), API_ID, API_HASH)
                await client.start()
                active_telegram_clients[session_id] = client
                
                return await telegram_login_form(
                    request=request,
                    success=f"✅ {session_type.title()} account added successfully",
                    token=token
                )
            else:
                return await telegram_login_form(
                    request=request,
                    phone_number=phone_number,
                    session_type=session_type,
                    channel_id=channel_id,  # PASS CHANNEL_ID
                    require_password=True,
                    error=result,
                    token=token
                )
            
    except Exception as e:
        # Log the full error for debugging
        print(f"ERROR in handle_telegram_login: {str(e)}")
        import traceback
        traceback.print_exc()
        
        return await telegram_login_form(
            request=request,
            phone_number=phone_number,
            session_type=session_type,
            channel_id=channel_id,  # PASS CHANNEL_ID
            error=f"Error: {str(e)}",
            token=token
        )