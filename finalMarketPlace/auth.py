"""
Authentication and authorization decorators
"""
from functools import wraps
import inspect
from typing import Optional
from fastapi import Request, HTTPException
from database import get_user_by_id
from config import ADMIN_TOKENS


def get_current_user(request: Request) -> Optional[dict]:
    """Get current logged-in user from cookies"""
    if not request:
        return None
    
    cookies = getattr(request, 'cookies', None)
    if not cookies:
        return None
    
    uid = cookies.get('uid')
    if not uid:
        return None
    
    try:
        user = get_user_by_id(int(uid))
        return user
    except (ValueError, TypeError):
        return None


def login_required(f):
    """Decorator to require user login"""
    @wraps(f)
    async def wrapper(*args, **kwargs):
        # Find the Request object in args or kwargs
        request = kwargs.get('request') or kwargs.get('req') or next(
            (v for v in args if isinstance(v, Request)), None
        )
        
        user = get_current_user(request)
        if not user:
            raise HTTPException(status_code=401, detail="Authentication required")
        
        return await f(*args, **kwargs)
    
    # Preserve function signature for FastAPI
    try:
        wrapper.__signature__ = inspect.signature(f)
    except:
        pass
    
    return wrapper


def admin_required(f):
    """Decorator to require admin privileges"""
    @wraps(f)
    async def wrapper(*args, **kwargs):
        # Find the Request object
        request = kwargs.get('request') or kwargs.get('req') or next(
            (v for v in args if isinstance(v, Request)), None
        )
        
        # Check if user is logged in as admin
        user = get_current_user(request)
        if user and user.get('is_admin'):
            return await f(*args, **kwargs)
        
        # Check for admin token in query params
        token = request.query_params.get('token') if request else None
        
        # Check for token in form data (POST requests)
        if not token and request and getattr(request, 'method', '').upper() in ('POST', 'PUT', 'DELETE'):
            try:
                form = await request.form()
                token = form.get('token')
            except:
                pass
        
        if token and token in ADMIN_TOKENS:
            return await f(*args, **kwargs)
        
        raise HTTPException(status_code=403, detail="Admin access required")
    
    # Preserve function signature for FastAPI
    try:
        wrapper.__signature__ = inspect.signature(f)
    except:
        pass
    
    return wrapper