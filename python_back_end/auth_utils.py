"""Authentication utilities for FastAPI backend"""

import os
import asyncpg
from fastapi import Depends, HTTPException, status, Request
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from jose import JWTError, jwt
from typing import Optional, Dict

# Auth configuration
SECRET_KEY = os.getenv("JWT_SECRET", "key")
ALGORITHM = "HS256"
DATABASE_URL = os.getenv("DATABASE_URL", "postgresql://pguser:pgpassword@pgsql-db:5432/database")

security = HTTPBearer(auto_error=False)

async def get_db_pool(request: Request):
    """Get database connection pool from app state"""
    return getattr(request.app.state, 'pg_pool', None)

async def get_current_user_cookie_only(
    request: Request,
    pool = Depends(get_db_pool)
) -> Optional[Dict]:
    """Get user from cookie authentication (returns None if not authenticated)"""
    token = request.cookies.get("access_token")
    if not token:
        return None
    
    try:
        # Decode JWT token  
        payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
        user_id = payload.get("sub")
        
        if user_id is None:
            return None
        
        # Get user from database
        if pool:
            async with pool.acquire() as conn:
                user_record = await conn.fetchrow(
                    "SELECT id, username, email, avatar FROM users WHERE id = $1",
                    int(user_id)
                )
        else:
            conn = await asyncpg.connect(DATABASE_URL, timeout=10)
            try:
                user_record = await conn.fetchrow(
                    "SELECT id, username, email, avatar FROM users WHERE id = $1",
                    int(user_id)
                )
            finally:
                await conn.close()
        
        return dict(user_record) if user_record else None
            
    except JWTError:
        return None

async def get_current_user(
    credentials: HTTPAuthorizationCredentials = Depends(security),
    request: Request = None,
    pool = Depends(get_db_pool)
) -> Dict:
    """
    Verify JWT token and return current user info
    """
    if not credentials:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Authorization header missing",
            headers={"WWW-Authenticate": "Bearer"},
        )
    
    token = credentials.credentials
    
    try:
        # Decode JWT token
        payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
        user_id = payload.get("sub")
        
        if user_id is None:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Invalid token: missing user ID",
                headers={"WWW-Authenticate": "Bearer"},
            )
        
        # Get user from database
        import logging
        logger = logging.getLogger(__name__)
        logger.info(f"Pool status: {pool is not None}, Pool: {type(pool) if pool else 'None'}")
        
        if pool:
            # Use connection pool (preferred)
            import logging
            logger = logging.getLogger(__name__)
            logger.info(f"Using connection pool for user {user_id}")
            try:
                async with pool.acquire() as conn:
                    user_record = await conn.fetchrow(
                        "SELECT id, username, email, avatar FROM users WHERE id = $1",
                        int(user_id)
                    )
                logger.info(f"Successfully fetched user {user_id} from database")
            except Exception as e:
                logger.error(f"Pool connection failed for user {user_id}: {e}")
                raise
        else:
            # Fallback to direct connection
            conn = await asyncpg.connect(DATABASE_URL, timeout=10)
            try:
                user_record = await conn.fetchrow(
                    "SELECT id, username, email, avatar FROM users WHERE id = $1",
                    int(user_id)
                )
            finally:
                await conn.close()
        
        if not user_record:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="User not found",
                headers={"WWW-Authenticate": "Bearer"},
            )
        
        return dict(user_record)
            
    except JWTError:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid token",
            headers={"WWW-Authenticate": "Bearer"},
        )

# Option B: Hybrid auth dependency (Bearer OR cookie)
async def get_user_bearer_or_cookie(
    request: Request,
    credentials: HTTPAuthorizationCredentials = Depends(security),
    cookie_user = Depends(get_current_user_cookie_only),
    pool = Depends(get_db_pool)
) -> int:
    """
    Authentication dependency that accepts either Bearer token or cookie.
    Returns user_id for use in session endpoints.
    """
    # Try Bearer token first
    if credentials and credentials.credentials:
        try:
            payload = jwt.decode(credentials.credentials, SECRET_KEY, algorithms=[ALGORITHM])
            user_id = payload.get("sub")
            if user_id:
                return int(user_id)
        except JWTError:
            pass  # Fall through to cookie auth
    
    # Try cookie auth
    if cookie_user:
        return int(cookie_user["id"])
    
    # No valid auth found
    raise HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="UNAUTHORIZED",
        headers={"WWW-Authenticate": "Bearer"},
    )