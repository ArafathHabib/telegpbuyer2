"""
Telegram/Telethon integration for group verification and ownership transfer
"""
import re
import asyncio
import emoji
import time
import threading
from typing import Dict, Tuple, Optional
from telethon import TelegramClient
from telethon.sessions import StringSession
from telethon.tl.functions.messages import ImportChatInviteRequest
from telethon.tl.functions.channels import JoinChannelRequest, LeaveChannelRequest, GetParticipantRequest, GetFullChannelRequest
from telethon.tl.types import Channel, ChannelParticipantCreator, Message as TMessage
from telethon.errors import SessionPasswordNeededError
from telethon.tl.functions.messages import GetFullChatRequest
from telethon.tl.types import Chat, Channel
from telethon.tl.functions.channels import GetFullChannelRequest

from config import (
    API_ID, API_HASH, CRYPTO_KEYWORDS, LOCATION_KEYWORDS, 
    IMPORTED_KEYWORDS, ADDED_KEYWORDS, REMOVED_KEYWORDS,
    active_telegram_clients, telegram_login_sessions
)
from database import get_connection


def cleanup_old_sessions():
    """Remove login sessions older than 10 minutes"""
    current_time = time.time()
    expired = [
        phone for phone, data in telegram_login_sessions.items()
        if current_time - data.get('created_at', 0) > 600  # 600 seconds = 10 minutes
    ]
    for phone in expired:
        try:
            telegram_login_sessions[phone]['client'].disconnect()
        except:
            pass  # Ignore errors during disconnect
        del telegram_login_sessions[phone]
    print(f"Cleaned up {len(expired)} expired login sessions")


def start_session_cleanup():
    """Start the periodic session cleanup"""
    def cleanup_wrapper():
        cleanup_old_sessions()
        # Schedule next cleanup in 10 minutes
        threading.Timer(600, cleanup_wrapper).start()
    
    # Start the first cleanup
    cleanup_wrapper()


# Start session cleanup when module is imported
try:
    start_session_cleanup()
    print("✓ Session cleanup started")
except Exception as e:
    print(f"✗ Failed to start session cleanup: {e}")


def is_only_emoji(text: str) -> bool:
    """Check if text contains only emojis"""
    if not text or not text.strip():
        return False
    return all(ch in emoji.EMOJI_DATA or ch.isspace() for ch in text.strip())


async def get_group_location(client, entity) -> Optional[str]:
    """
    Extract location from a group if it's a GeoChat / location-based group.
    Returns the address string or lat/lon, or None if not a geo group.
    """
    try:
        if isinstance(entity, Channel):
            full = await client(GetFullChannelRequest(entity))
            if hasattr(full, "full_chat") and full.full_chat:
                loc = getattr(full.full_chat, "location", None)
                if loc:
                    if getattr(loc, "address", None):
                        return loc.address
                    if getattr(loc, "geo_point", None):
                        return f"Lat: {loc.geo_point.lat}, Lon: {loc.geo_point.long}"

        elif isinstance(entity, Chat):
            full = await client(GetFullChatRequest(entity.id))
            if hasattr(full, "full_chat") and full.full_chat:
                loc = getattr(full.full_chat, "location", None)
                if loc:
                    if getattr(loc, "address", None):
                        return loc.address
                    if getattr(loc, "geo_point", None):
                        return f"Lat: {loc.geo_point.lat}, Lon: {loc.geo_point.long}"

        return None
    except Exception as e:
        print(f"⚠️ Location fetch failed: {e}")
        return None


async def is_imported_group(client: TelegramClient, entity) -> Tuple[bool, str]:
    """
    Enhanced imported content detection
    Returns: (is_imported, reason)
    """
    try:
        # Check recent messages for import indicators
        messages = await client.get_messages(entity, limit=100)
        
        for msg in messages:
            # Check forwarded messages with explicit import flag
            fwd = getattr(msg, 'fwd_from', None)
            if fwd is not None:
                # Explicit imported flag (most reliable)
                if getattr(fwd, 'imported', False):
                    return True, "Contains messages with 'imported' flag"
                
                # Saved from peer (indicates imported from saved messages)
                if hasattr(fwd, 'saved_from_peer') and fwd.saved_from_peer:
                    return True, "Contains messages imported from saved messages"
                
                # from_name without from_id indicates hidden/imported source
                if getattr(fwd, 'from_name', None) and not getattr(fwd, 'from_id', None):
                    return True, "Contains forwarded messages from hidden sources"
        
        # Also check message text for import keywords (secondary check)
        for msg in messages[:50]:
            if msg.message:
                msg_lower = msg.message.lower()
                for keyword in IMPORTED_KEYWORDS:
                    if keyword in msg_lower:
                        return True, f"Message text mentions import: '{keyword}'"
        
        return False, ""
        
    except Exception as e:
        print(f"Error checking imported group: {e}")
        return False, ""


async def check_emoji_first_messages(client: TelegramClient, entity, limit: int = 100) -> Tuple[bool, int]:
    """
    Check if users have emoji-only first messages (spam indicator)
    Returns: (found_emoji_only, count)
    """
    try:
        user_first_messages = {}
        emoji_only_count = 0
        
        messages = await client.get_messages(entity, limit=limit, reverse=True)
        
        for msg in messages:
            if not msg.message:
                continue
                
            sender = await msg.get_sender()
            if not sender:
                continue
            
            uid = sender.id
            if uid not in user_first_messages:
                user_first_messages[uid] = msg
                if is_only_emoji(msg.message):
                    emoji_only_count += 1
        
        # Flag if more than 5 users have emoji-only first messages
        return emoji_only_count > 5, emoji_only_count
        
    except Exception as e:
        print(f"Error checking emoji messages: {e}")
        return False, 0


async def leave_group(client: TelegramClient, link: str) -> bool:
    """Leave a Telegram group"""
    try:
        if 't.me/joinchat/' in link or 't.me/+' in link:
            # For invite links, iterate through dialogs to find and leave
            async for dialog in client.iter_dialogs():
                if dialog.is_group or dialog.is_channel:
                    try:
                        await client(LeaveChannelRequest(dialog.entity))
                        return True
                    except:
                        continue
        else:
            # For username links
            match = re.search(r't\.me/([a-zA-Z0-9_]+)', link)
            username = match.group(1) if match else link.replace('t.me/', '').replace('@', '').strip()
            entity = await client.get_entity(username)
            await client(LeaveChannelRequest(entity))
            return True
    except Exception as e:
        print(f"Failed to leave group: {e}")
    return False


async def check_group(session_id: int, link: str, year: int, month: Optional[int] = None) -> dict:
    """
    Enhanced group verification with month checking
    Returns: {'ok': bool, 'log': list, 'reason': str or None}
    """
    info = {'ok': False, 'log': [], 'reason': None}
    
    if session_id not in active_telegram_clients:
        info['reason'] = 'no_session'
        info['log'].append('No active Telegram session available')
        return info
    
    client = active_telegram_clients[session_id]
    entity = None
    
    try:
        link = link.strip()

        # Check for folder links (not supported)
        if 't.me/addlist/' in link:
            info['reason'] = 'folder_link_detected'
            info['log'].append('ERROR: Folder links are not supported. Provide individual group links.')
            return info
        
        # Join group via invite link
        if 't.me/joinchat/' in link or 't.me/+' in link:
            match = re.search(r't\.me/(?:joinchat/|\+)([a-zA-Z0-9_-]+)', link)
            if match:
                invite_hash = match.group(1)
                info['log'].append(f'Joining via invite: {invite_hash}')
                try:
                    result = await client(ImportChatInviteRequest(invite_hash))
                    info['log'].append('Successfully joined via invite link')
                    if hasattr(result, 'chats') and result.chats:
                        entity = result.chats[0]
                    else:
                        info['reason'] = 'failed_to_get_chat'
                        info['log'].append('ERROR: Could not get chat after joining')
                        return info
                except Exception as join_err:
                    info['reason'] = 'join_failed'
                    info['log'].append(f'Join failed: {str(join_err)[:200]}')
                    return info
            else:
                info['reason'] = 'invalid_link'
                info['log'].append('ERROR: Could not parse invite link')
                return info
        
        # Join group via username
        else:
            match = re.search(r't\.me/([a-zA-Z0-9_]+)', link)
            username = match.group(1) if match else link.replace('t.me/', '').replace('@', '').strip()
            info['log'].append(f'Joining: @{username}')

            try:
                await client(JoinChannelRequest(username))
                info['log'].append('Successfully joined group')
            except Exception as join_err:
                info['log'].append(f'Join attempt: {str(join_err)[:100]}')

            await asyncio.sleep(1)
            entity = await client.get_entity(username)

        # Verify it's a supergroup/channel
        if not isinstance(entity, Channel):
            info['reason'] = 'not_supergroup'
            info['log'].append('ERROR: Must be a supergroup/channel')
            await leave_group(client, link)
            return info

        # Check if it's a megagroup (supergroup)
        if not getattr(entity, 'megagroup', False):
            info['reason'] = 'not_megagroup'
            info['log'].append('ERROR: Must be a supergroup (megagroup), not a channel')
            await leave_group(client, link)
            return info

        group_title = getattr(entity, 'title', str(entity))
        info['log'].append(f'Group: {group_title}')

        # Extract geo location if available
        location = await get_group_location(client, entity)
        if location:
            info['reason'] = 'location_based_group'
            info['log'].append(f'ERROR: Group is location-based (GeoChat) — {location}')
            await leave_group(client, link)
            return info


        # Try to retrieve message history
        messages = await client.get_messages(entity, limit=300)
        if not messages or len(messages) == 0:
            info['reason'] = 'no_message_history'
            info['log'].append('ERROR: No message history visible (history hidden for new members)')
            await leave_group(client, link)
            return info

        info['log'].append(f'Retrieved {len(messages)} messages - History visible')

        # Check for imported content (ENHANCED)
        is_imported, import_reason = await is_imported_group(client, entity)
        if is_imported:
            info['reason'] = 'imported_group_detected'
            info['log'].append(f'ERROR: {import_reason}')
            await leave_group(client, link)
            return info

        # Check first message date for year and month verification
        first_msg = messages[-1]
        first_year = first_msg.date.year
        first_month = first_msg.date.month
        
        month_names = ['January', 'February', 'March', 'April', 'May', 'June', 
                      'July', 'August', 'September', 'October', 'November', 'December']
        
        # Log both year and month information
        if month:
            info['log'].append(f'First message: {first_msg.date.strftime("%Y-%m-%d")} (Year: {first_year}, Month: {first_month} - {month_names[first_month-1]})')
        else:
            info['log'].append(f'First message: {first_msg.date.strftime("%Y-%m-%d")} (Year: {first_year})')

        # Year verification
        if first_year != int(year):
            info['reason'] = 'year_mismatch'
            info['log'].append(f'ERROR: Group started in {first_year}, required {year}')
            await leave_group(client, link)
            return info

        # Month verification (if required)
        if month and first_month != int(month):
            info['reason'] = 'month_mismatch'
            info['log'].append(f'ERROR: Group started in {month_names[first_month-1]}, required {month_names[month-1]}')
            await leave_group(client, link)
            return info

        # Check for emoji-only first messages (spam indicator)
        has_emoji_spam, emoji_count = await check_emoji_first_messages(client, entity)
        if has_emoji_spam:
            info['reason'] = 'emoji_spam_detected'
            info['log'].append(f'ERROR: Too many users ({emoji_count}) have emoji-only first messages')
            await leave_group(client, link)
            return info

        # Analyze recent messages and description
        recent_text = ' '.join([
            (msg.message or '').lower() 
            for msg in messages[:20] 
            if isinstance(msg, TMessage)
        ])
        description = (getattr(entity, 'about', '') or '').lower()

        # Check for crypto-related content
        if any(kw in description for kw in CRYPTO_KEYWORDS) or any(kw in recent_text for kw in CRYPTO_KEYWORDS):
            info['reason'] = 'crypto_related_group'
            info['log'].append('ERROR: Group appears to be crypto-related')
            await leave_group(client, link)
            return info

        # Check for excessive member addition activity
        added_count = sum(
            1 for msg in messages[:200] 
            if any(keyword in (msg.message or '').lower() for keyword in ADDED_KEYWORDS)
        )
        info['log'].append(f'Member additions: {added_count} messages')
        
        if added_count > 50:
            info['reason'] = 'excessive_member_additions'
            info['log'].append('ERROR: Too many member addition messages')
            await leave_group(client, link)
            return info

        # Check for excessive member removal activity
        removed_count = sum(
            1 for msg in messages[:200] 
            if any(keyword in (msg.message or '').lower() for keyword in REMOVED_KEYWORDS)
        )
        info['log'].append(f'Member removals: {removed_count} messages')
        
        if removed_count > 50:
            info['reason'] = 'excessive_member_removals'
            info['log'].append('ERROR: Too many member removal messages')
            await leave_group(client, link)
            return info

        # All checks passed
        info['log'].append('All checks passed! Leaving group.')
        await leave_group(client, link)
        info['ok'] = True
        return info
        
    except Exception as e:
        info['reason'] = f'error: {str(e)[:200]}'
        info['log'].append(f'EXCEPTION: {str(e)}')
        if entity:
            await leave_group(client, link)
        return info


async def verify_receiver_ownership(session_id: int, link: str) -> Tuple[bool, str]:
    """
    Verify that the receiver account has CREATOR (owner) status
    Ensure receiver joins the group first
    """
    if session_id not in active_telegram_clients:
        return False, "Receiver session not active"
    
    client = active_telegram_clients[session_id]
    entity = None
    
    try:
        link = link.strip()
        print(f"🔄 Receiver attempting to join: {link}")

        # Join group via invite link
        if 't.me/joinchat/' in link or 't.me/+' in link:
            match = re.search(r't\.me/(?:joinchat/|\+)([a-zA-Z0-9_-]+)', link)
            if match:
                invite_hash = match.group(1)
                print(f"📨 Joining via invite hash: {invite_hash}")
                try:
                    result = await client(ImportChatInviteRequest(invite_hash))
                    print("✅ Receiver joined via invite link")
                    if hasattr(result, 'chats') and result.chats:
                        entity = result.chats[0]
                    else:
                        return False, "Could not get chat after joining"
                except Exception as join_err:
                    if "already a participant" in str(join_err):
                        print("ℹ️ Receiver already in group")
                        # Try to get entity from the link
                        try:
                            # For invite links, we need to find it in dialogs
                            async for dialog in client.iter_dialogs():
                                if dialog.is_group or dialog.is_channel:
                                    entity = dialog.entity
                                    break
                        except Exception as e:
                            print(f"Error finding dialog: {e}")
                    else:
                        return False, f"Receiver failed to join: {str(join_err)}"
        
        # Join group via username
        else:
            match = re.search(r't\.me/([a-zA-Z0-9_]+)', link)
            username = match.group(1) if match else link.replace('t.me/', '').replace('@', '').strip()
            print(f"📨 Joining via username: @{username}")
            
            try:
                await client(JoinChannelRequest(username))
                print("✅ Receiver joined via username")
            except Exception as join_err:
                if "already a participant" in str(join_err):
                    print("ℹ️ Receiver already in group")
                else:
                    return False, f"Receiver failed to join: {str(join_err)}"
            
            # Wait a bit for join to complete
            await asyncio.sleep(3)
            try:
                entity = await client.get_entity(username)
                print(f"✅ Got entity: {getattr(entity, 'title', 'Unknown')}")
            except Exception as e:
                return False, f"Could not get group entity: {str(e)}"

        if not entity:
            return False, "Could not get group entity after join attempt"

        # Get our own user info
        me = await client.get_me()
        print(f"👤 Receiver: {me.username or me.phone}")

        # Check our participant status
        try:
            print("🔍 Checking participant status...")
            participant = await client(GetParticipantRequest(entity, me))
            
            # Must be ChannelParticipantCreator (owner)
            if isinstance(participant.participant, ChannelParticipantCreator):
                print("✅ Ownership verified: User is CREATOR")
                
                # Optional: Clean up other members
                try:
                    members = await client.get_participants(entity, limit=10)
                    if len(members) > 1:
                        print(f"🧹 Cleaning up {len(members)-1} remaining members...")
                        for member in members:
                            if member.id != me.id:
                                try:
                                    await client.kick_participant(entity, member)
                                    print(f"✅ Removed: {getattr(member, 'username', member.id)}")
                                except Exception as e:
                                    print(f"⚠️ Failed to remove: {e}")
                except Exception as e:
                    print(f"⚠️ Member cleanup failed: {e}")
                
                return True, "Ownership verified"
                
            else:
                participant_type = type(participant.participant).__name__
                print(f"❌ User is {participant_type}, not CREATOR")
                return False, f"User is {participant_type}, not CREATOR"
                
        except Exception as e:
            print(f"❌ Error checking participant: {e}")
            return False, f"Could not verify participant status: {str(e)}"

    except Exception as e:
        print(f"❌ Verification error: {e}")
        return False, f"Verification failed: {str(e)}"
    

async def get_free_checker_session() -> Optional[int]:
    """Get an available checker session"""
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute(
        'SELECT id FROM admin_sessions WHERE session_type="checker" AND status="ready" ORDER BY last_used_ts ASC LIMIT 1'
    )
    row = cursor.fetchone()
    conn.close()
    return row[0] if row else None


async def get_free_receiver_session() -> Optional[int]:
    """Get an available receiver session with capacity for more groups"""
    from config import MAX_GROUPS_PER_RECEIVER
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute(
        '''SELECT id FROM admin_sessions 
           WHERE session_type="receiver" AND status="ready" AND groups_received < ? 
           ORDER BY groups_received ASC, last_used_ts ASC LIMIT 1''',
        (MAX_GROUPS_PER_RECEIVER,)
    )
    row = cursor.fetchone()
    conn.close()
    return row[0] if row else None


async def mark_session_failed(session_id: int):
    """Mark a session as failed"""
    import time
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute(
        'UPDATE admin_sessions SET status="failed", last_used_ts=? WHERE id=?',
        (int(time.time()), session_id)
    )
    conn.commit()
    conn.close()


async def send_telegram_verification_code(phone_number: str) -> Tuple[bool, str]:
    """Send Telegram verification code"""
    try:
        client = TelegramClient(StringSession(), API_ID, API_HASH)
        await client.connect()
        sent_code = await client.send_code_request(phone_number)
        telegram_login_sessions[phone_number] = {
            'client': client, 
            'phone_code_hash': sent_code.phone_code_hash,
            'created_at': time.time()  # Track session creation time
        }
        return True, "Verification code sent! Check your Telegram app."
    except Exception as e:
        return False, f"Failed to send code: {str(e)}"


async def verify_telegram_code(phone_number: str, code: str) -> Tuple[bool, any]:
    """Verify Telegram code"""
    try:
        if phone_number not in telegram_login_sessions:
            return False, "Session expired. Please try again."
        
        session_data = telegram_login_sessions[phone_number]
        client = session_data['client']
        phone_code_hash = session_data['phone_code_hash']
        
        try:
            await client.sign_in(phone=phone_number, code=code, phone_code_hash=phone_code_hash)
        except TypeError:
            await client.sign_in(code=code)
        except SessionPasswordNeededError:
            # KEEP THE SESSION for password verification instead of deleting it
            return False, "password_needed"

        session_string = client.session.save()
        me = await client.get_me()
        
        # Clean up session only after successful verification
        if phone_number in telegram_login_sessions:
            await telegram_login_sessions[phone_number]['client'].disconnect()
            del telegram_login_sessions[phone_number]
        
        return True, (session_string, me)
        
    except SessionPasswordNeededError:
        # Don't delete session when password is needed
        return False, "password_needed"
    except Exception as e:
        # Clean up on error
        try:
            if phone_number in telegram_login_sessions:
                await telegram_login_sessions[phone_number]['client'].disconnect()
                del telegram_login_sessions[phone_number]
        except:
            pass
        return False, f"Verification failed: {str(e)}"


async def verify_telegram_password(phone_number: str, password: str) -> Tuple[bool, any]:
    """Verify Telegram 2FA password"""
    try:
        if phone_number not in telegram_login_sessions:
            return False, "Session expired. Please try again."
        
        session_data = telegram_login_sessions[phone_number]
        client = session_data['client']
        
        await client.sign_in(password=password)
        session_string = client.session.save()
        me = await client.get_me()
        
        if phone_number in telegram_login_sessions:
            del telegram_login_sessions[phone_number]
        
        return True, (session_string, me)
        
    except Exception as e:
        try:
            if phone_number in telegram_login_sessions:
                await telegram_login_sessions[phone_number]['client'].disconnect()
        except:
            pass
        return False, f"Password verification failed: {str(e)}"
    

async def send_purchase_message(session_id: int, group_link: str, year: int, seller_username: str, price: float) -> Tuple[bool, str]:
    """
    Send a message in the group after ownership transfer
    Returns: (success, message)
    """
    if session_id not in active_telegram_clients:
        return False, "Session not active"
    
    client = active_telegram_clients[session_id]
    
    try:
        # Get entity
        if 't.me/joinchat/' in group_link or 't.me/+' in group_link:
            # For invite links, find in dialogs
            entity = None
            async for dialog in client.iter_dialogs():
                if dialog.is_group or dialog.is_channel:
                    entity = dialog.entity
                    break
        else:
            match = re.search(r't\.me/([a-zA-Z0-9_]+)', group_link)
            username = match.group(1) if match else group_link.replace('t.me/', '').replace('@', '').strip()
            entity = await client.get_entity(username)
        
        if not entity:
            return False, "Could not find group"
        
        # Format date
        from datetime import datetime
        date_str = datetime.now().strftime('%B %d, %Y')
        
        # Send message
        message = f"This group [{year}] was purchased from {seller_username} at ${price} on {date_str}."
        await client.send_message(entity, message)
        
        return True, "Purchase message sent"
        
    except Exception as e:
        return False, f"Failed to send message: {str(e)}"


async def post_withdrawal_request(session_id: int, withdrawal_data: dict) -> Tuple[bool, int, str]:
    """
    Post withdrawal request to channel
    Returns: (success, message_id, error_message)
    """
    if session_id not in active_telegram_clients:
        return False, 0, "Session not active"
    
    client = active_telegram_clients[session_id]
    
    try:
        # Get channel
        conn = get_connection()
        cursor = conn.cursor()
        cursor.execute('SELECT channel_id FROM admin_sessions WHERE id=?', (session_id,))
        row = cursor.fetchone()
        conn.close()
        
        if not row or not row[0]:
            return False, 0, "Channel ID not configured"
        
        channel_id = row[0]
        entity = await client.get_entity(channel_id)
        
        # Build message
        groups_info = withdrawal_data.get('groups', [])
        groups_text = "\n".join([
            f"  • {g['link']} (${g['price']}) - Receiver: {g['receiver']}"
            for g in groups_info
        ])
        
        message = f"""
🔔 **New Withdrawal Request** 🔔

👤 **User:** {withdrawal_data['username']} ({withdrawal_data['telegram']})
💰 **Amount:** ${withdrawal_data['amount']}
🏦 **Wallet:** `{withdrawal_data['wallet']}`
📊 **Groups Sold:** {len(groups_info)}

📋 **Group Details:**
{groups_text}

🕐 **Requested:** {withdrawal_data['date']}
🆔 **Withdrawal ID:** {withdrawal_data['id']}
"""
        
        # Send message
        result = await client.send_message(entity, message)
        
        return True, result.id, ""
        
    except Exception as e:
        return False, 0, f"Failed to post: {str(e)}"


async def post_withdrawal_paid(session_id: int, payment_data: dict) -> Tuple[bool, str]:
    """
    Post payment confirmation to public channel
    Returns: (success, error_message)
    """
    if session_id not in active_telegram_clients:
        return False, "Session not active"
    
    client = active_telegram_clients[session_id]
    
    try:
        # Get channel
        conn = get_connection()
        cursor = conn.cursor()
        cursor.execute('SELECT channel_id FROM admin_sessions WHERE id=?', (session_id,))
        row = cursor.fetchone()
        conn.close()
        
        if not row or not row[0]:
            return False, "Channel ID not configured"
        
        channel_id = row[0]
        entity = await client.get_entity(channel_id)
        
        # Mask username for privacy
        username = payment_data['username']
        if len(username) > 5:
            masked = username[:4] + '***'
        else:
            masked = username[0] + '***'
        
        # Build message
        message = f"""
✅ **Payment Completed** ✅

👤 **User:** @{masked}
💵 **Amount:** ${payment_data['amount']} USDT
🌐 **Network:** {payment_data.get('network', 'Polygon')}
🔗 **TX ID:** `{payment_data['txid']}`
📅 **Date:** {payment_data['date']}
"""
        
        # Send message
        await client.send_message(entity, message)
        
        return True, ""
        
    except Exception as e:
        return False, f"Failed to post: {str(e)}"


async def get_withdrawal_sessions() -> dict:
    """Get withdrawal request and paid session IDs"""
    conn = get_connection()
    cursor = conn.cursor()
    
    cursor.execute('SELECT id FROM admin_sessions WHERE session_type="withdrawal_request" AND status="ready" LIMIT 1')
    request_row = cursor.fetchone()
    request_session = request_row[0] if request_row else None
    
    cursor.execute('SELECT id FROM admin_sessions WHERE session_type="withdrawal_paid" AND status="ready" LIMIT 1')
    paid_row = cursor.fetchone()
    paid_session = paid_row[0] if paid_row else None
    
    conn.close()
    
    return {
        'request': request_session,
        'paid': paid_session
    }


# Add these functions to telegram_handler.py

async def get_next_receiver_round_robin() -> Optional[int]:
    """
    Get next receiver in round-robin fashion
    Returns receiver session ID or None if no receivers available
    """
    from config import MAX_GROUPS_PER_RECEIVER
    
    conn = get_connection()
    cursor = conn.cursor()
    
    # Get all available receivers with capacity
    cursor.execute(
        '''SELECT id, groups_received FROM admin_sessions 
           WHERE session_type="receiver" AND status="ready" AND groups_received < ?
           ORDER BY id''',
        (MAX_GROUPS_PER_RECEIVER,)
    )
    receivers = cursor.fetchall()
    
    if not receivers:
        conn.close()
        return None
    
    # Get the last used receiver from a tracking table or use first receiver
    cursor.execute(
        'SELECT value FROM system_settings WHERE key = "last_receiver_id"'
    )
    last_receiver_row = cursor.fetchone()
    
    if last_receiver_row:
        last_receiver_id = int(last_receiver_row[0])
        # Find the next receiver in sequence
        receiver_ids = [r[0] for r in receivers]
        
        try:
            current_index = receiver_ids.index(last_receiver_id)
            next_index = (current_index + 1) % len(receiver_ids)
        except ValueError:
            # Last receiver not found in available receivers, start from first
            next_index = 0
    else:
        # No last receiver recorded, start from first
        next_index = 0
    
    next_receiver_id = receivers[next_index][0]
    
    # Update the last used receiver
    cursor.execute(
        'REPLACE INTO system_settings (key, value) VALUES ("last_receiver_id", ?)',
        (str(next_receiver_id),)
    )
    
    conn.commit()
    conn.close()
    
    print(f"🔁 Round-robin: Selected receiver {next_receiver_id} (index {next_index + 1}/{len(receivers)})")
    return next_receiver_id


async def get_free_receiver_session() -> Optional[int]:
    """
    Get an available receiver session using round-robin approach
    Now uses sequential assignment instead of random/first-available
    """
    return await get_next_receiver_round_robin()