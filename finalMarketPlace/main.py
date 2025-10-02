"""
Main FastAPI application entry point
"""

import re
from telethon.tl.functions.messages import ImportChatInviteRequest
from telethon.tl.functions.channels import JoinChannelRequest
import asyncio
import time
from contextlib import asynccontextmanager

import uvicorn
from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles
from telethon import TelegramClient
from telethon.sessions import StringSession

from config import API_ID, API_HASH, WEB_HOST, WEB_PORT, DB_PATH, ADMIN_TOKENS, MAX_GROUPS_PER_RECEIVER, active_telegram_clients
from database import init_database, get_connection
from telegram_handler import (
    check_group, verify_receiver_ownership, get_free_checker_session,
    get_free_receiver_session, mark_session_failed
)

# Import routes
from routes.user_routes import router as user_router
from routes.listing_routes import router as listing_router
from routes.admin_routes import router as admin_router
from routes.telegram_routes import router as telegram_router

from fastapi.staticfiles import StaticFiles

async def checker_worker():
    """Background worker to process pending listings"""
    while True:
        await asyncio.sleep(2)
        
        conn = get_connection()
        cursor = conn.cursor()
        
        # Get next pending listing
        cursor.execute(
            "SELECT id, campaign_id, group_link FROM listings WHERE status='pending' ORDER BY created_ts ASC LIMIT 1"
        )
        row = cursor.fetchone()
        
        if not row:
            conn.close()
            await asyncio.sleep(3)
            continue
        
        listing_id, campaign_id, link = row
        
        # Get campaign year and month
        cursor.execute('SELECT year, month FROM campaigns WHERE id=?', (campaign_id,))
        campaign = cursor.fetchone()

        if not campaign:
            cursor.execute(
                "UPDATE listings SET status='failed', check_reason='no_campaign' WHERE id=?",
                (listing_id,)
            )
            conn.commit()
            conn.close()
            continue

        year = campaign[0]
        month = campaign[1]  # This can be None if no month specified
        
        # Try up to 3 checker sessions
        for attempt in range(3):
            session_id = await get_free_checker_session()
            
            if not session_id:
                print(f"No available checker sessions, waiting...")
                conn.close()
                await asyncio.sleep(5)
                break
            
            print(f"Checking listing {listing_id} with checker session {session_id} (attempt {attempt+1})")
            
            # Update session last used time
            cursor.execute(
                'UPDATE admin_sessions SET last_used_ts=? WHERE id=?',
                (int(time.time()), session_id)
            )
            conn.commit()
            conn.close()
            
            # Run verification with month
            result = await check_group(session_id, link, year, month)
            
            # Reconnect to database
            conn = get_connection()
            cursor = conn.cursor()
            
            # Check if session failed
            if result['reason'] == 'no_session' or 'EXCEPTION' in '\n'.join(result['log']):
                print(f"Checker session {session_id} failed, marking as failed")
                await mark_session_failed(session_id)
                conn.close()
                await asyncio.sleep(2)
                continue
            
            # Process result
            if result['ok']:
                # Find available receiver
                receiver_session = await get_free_receiver_session()
                
                if not receiver_session:
                    cursor.execute(
                        'UPDATE listings SET status="failed", check_reason="no_receiver_available", check_log=? WHERE id=?',
                        ('\n'.join(result['log']), listing_id)
                    )
                    print(f"No receiver available for listing {listing_id}")
                else:
                    # Have receiver join the group immediately
                    print(f"Receiver {receiver_session} joining group for listing {listing_id}...")
                    
                    join_log = ""
                    try:
                        receiver_client = active_telegram_clients.get(receiver_session)
                        if receiver_client:
                            # Join the group using the same logic as checker
                            if 't.me/joinchat/' in link or 't.me/+' in link:
                                match = re.search(r't\.me/(?:joinchat/|\+)([a-zA-Z0-9_-]+)', link)
                                if match:
                                    invite_hash = match.group(1)
                                    await receiver_client(ImportChatInviteRequest(invite_hash))
                                    join_log = "Receiver joined via invite link"
                                    print(f"Receiver joined via invite link")
                            else:
                                match = re.search(r't\.me/([a-zA-Z0-9_]+)', link)
                                username = match.group(1) if match else link.replace('t.me/', '').replace('@', '').strip()
                                await receiver_client(JoinChannelRequest(username))
                                join_log = f"Receiver joined @{username}"
                                print(f"Receiver joined @{username}")
                            
                            await asyncio.sleep(2)  # Give it a moment to settle
                        else:
                            join_log = "Receiver client not found in active sessions"
                            print(f"Warning: Receiver client {receiver_session} not found")
                    except Exception as e:
                        error_msg = str(e)
                        if "already a participant" in error_msg.lower():
                            join_log = "Receiver already in group"
                            print(f"Receiver already in group")
                        else:
                            join_log = f"Receiver join failed: {error_msg[:100]}"
                            print(f"Warning: Receiver failed to join: {error_msg}")
                        # Continue anyway - user might still be able to add them manually
                    
                    # Update listing with receiver info and join log
                    full_log = '\n'.join(result['log']) + f"\n\nReceiver join: {join_log}"
                    cursor.execute(
                        '''UPDATE listings SET status="ready_for_transfer", check_log=?, 
                           checked_by_session=?, receiver_session=? WHERE id=?''',
                        (full_log, session_id, receiver_session, listing_id)
                    )
                    print(f"Listing {listing_id} passed checks, assigned to receiver {receiver_session}")
            else:
                cursor.execute(
                    'UPDATE listings SET status="failed", check_reason=?, check_log=?, checked_by_session=? WHERE id=?',
                    (result['reason'], '\n'.join(result['log']), session_id, listing_id)
                )
                print(f"Listing {listing_id} failed: {result['reason']}")
            
            conn.commit()
            conn.close()
            break
        
        await asyncio.sleep(3)

@asynccontextmanager
async def lifespan(app: FastAPI):
    """Application lifespan manager"""
    # Startup
    print("Starting Telegram Group Marketplace...")
    
    # Initialize database
    init_database()
    
    # Start checker worker
    asyncio.create_task(checker_worker())
    
    # Load Telegram sessions
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute('SELECT id, session_text FROM admin_sessions WHERE status="ready"')
    
    for session_id, session_text in cursor.fetchall():
        try:
            client = TelegramClient(StringSession(session_text), API_ID, API_HASH)
            await client.start()
            active_telegram_clients[session_id] = client
            print(f"✓ Loaded Telegram session {session_id}")
        except Exception as e:
            print(f"✗ Failed to load session {session_id}: {e}")
    
    conn.close()
    
    print("✓ Application started successfully")
    
    yield
    
    # Shutdown
    print("Shutting down...")
    for client in active_telegram_clients.values():
        await client.disconnect()
    print("✓ All connections closed")


# Create FastAPI app
app = FastAPI(
    title="Telegram Group Marketplace",
    version="2.0.0",
    lifespan=lifespan
)

# Include routers
app.include_router(user_router)
app.include_router(listing_router)
app.include_router(admin_router)
app.include_router(telegram_router)

# Mount static files
try:
    app.mount("/static", StaticFiles(directory="static"), name="static")
except:
    pass  # Static directory might not exist yet


if __name__ == '__main__':
    print('=' * 60)
    print('TELEGRAM GROUP MARKETPLACE')
    print('=' * 60)
    print(f'Server: http://{WEB_HOST}:{WEB_PORT}')
    print(f'Database: {DB_PATH}')
    print(f'Admin Token: {list(ADMIN_TOKENS)[0] if ADMIN_TOKENS else "Not Set"}')
    print(f'Max Groups per Receiver: {MAX_GROUPS_PER_RECEIVER}')
    print('=' * 60)
    print('Press CTRL+C to quit')
    print('=' * 60)
    
    uvicorn.run(
        app,
        host=WEB_HOST,
        port=WEB_PORT,
        log_level="info"
    )