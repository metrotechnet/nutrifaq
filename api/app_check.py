from fastapi import APIRouter

router = APIRouter()

"""
Firebase App Check Middleware

This module provides middleware and utilities to verify App Check tokens and ensure requests come from legitimate app instances in the Nutria Agent backend.
"""

from fastapi import Request
from fastapi.responses import JSONResponse
import os
import json
import logging
import firebase_admin
from firebase_admin import credentials, app_check

logger = logging.getLogger(__name__)

# Get configuration from environment
FIREBASE_PROJECT_ID = os.getenv("FIREBASE_PROJECT_ID", "")
APP_CHECK_ENABLED = os.getenv("APP_CHECK_ENABLED", "false").lower() == "true"
APP_CHECK_DEBUG = os.getenv("APP_CHECK_DEBUG", "false").lower() == "true"

# Initialize Firebase Admin SDK if not already done
if not firebase_admin._apps:
    # Initialize with project ID
    firebase_admin.initialize_app(options={
        'projectId': FIREBASE_PROJECT_ID
    })
    logger.info(f"[App Check] Firebase Admin SDK initialized with project: {FIREBASE_PROJECT_ID}")

# Paths that require App Check verification
PROTECTED_PATHS = [
    "/api/translate",
    "/api/tts",
    "/query"
]

# Paths that are exempt from App Check (for debugging, health checks, etc.)
EXEMPT_PATHS = [
    "/api/config",
    "/api/debug",
    "/health"
]


async def verify_app_check_middleware(request: Request, call_next):
    """
    Middleware to verify Firebase App Check tokens for protected API routes.

    Only applied to API routes, not static files or templates.
    Can be disabled via APP_CHECK_ENABLED environment variable.

    Args:
        request (Request): FastAPI request object.
        call_next (callable): The next middleware or route handler.

    Returns:
        Response: The response from the next handler or an error if verification fails.
    """
    
    # Debug trace: Entry
    if APP_CHECK_DEBUG:
        logger.debug(f"[App Check] Middleware called for path: {request.url.path}")

    # Skip CORS preflight requests (OPTIONS)
    if request.method == "OPTIONS":
        if APP_CHECK_DEBUG:
            logger.debug("[App Check] Skipping OPTIONS preflight request")
        return await call_next(request)

    # Skip if App Check is disabled
    if not APP_CHECK_ENABLED:
        if APP_CHECK_DEBUG:
            logger.debug("[App Check] App Check is disabled, skipping verification")
        return await call_next(request)

    # Check if this path should be protected
    path = request.url.path
    should_verify = any(path.startswith(protected) for protected in PROTECTED_PATHS)
    is_exempt = any(path.startswith(exempt) for exempt in EXEMPT_PATHS)

    if APP_CHECK_DEBUG:
        logger.debug(f"[App Check] Path: {path} | Should verify: {should_verify} | Is exempt: {is_exempt}")

    if not should_verify or is_exempt:
        if APP_CHECK_DEBUG:
            logger.debug(f"[App Check] Path {path} is not protected or is exempt. Skipping App Check.")
        return await call_next(request)

    # Get App Check token from header
    app_check_token = request.headers.get("X-Firebase-AppCheck")

    if APP_CHECK_DEBUG:
        logger.debug(f"[App Check] Token present: {bool(app_check_token)}")
        logger.debug(f"[App Check] All headers: {dict(request.headers)}")
        if app_check_token:
            logger.debug(f"[App Check] Token value (first 50 chars): {app_check_token[:50]}...")

    if not app_check_token:
        logger.warning(f"[App Check] Missing App Check token for {path}")
        return JSONResponse(
            status_code=401,
            content={
                "error": "Unauthorized",
                "message": "App Check token required"
            }
        )

    # Verify the token
    try:
        if APP_CHECK_DEBUG:
            logger.debug(f"[App Check] Verifying token for path: {path}")
            logger.debug(f"[App Check] Project ID: {FIREBASE_PROJECT_ID}")
        
        # Verify the App Check token using Firebase Admin SDK
        decoded_token = app_check.verify_token(app_check_token)

        if APP_CHECK_DEBUG:
            logger.info(f"[App Check] App Check token verified for {path}")
            logger.debug(f"[App Check] Token app_id: {decoded_token.get('app_id', 'unknown')}")

        # Token is valid, proceed with request
        return await call_next(request)

    except firebase_admin.exceptions.InvalidArgumentError as e:
        logger.error(f"[App Check] Invalid argument in token for {path}: {str(e)}")
        return JSONResponse(
            status_code=401,
            content={
                "error": "Unauthorized",
                "message": "Invalid App Check token format"
            }
        )
    except firebase_admin.exceptions.FirebaseError as e:
        logger.error(f"[App Check] Firebase error verifying token for {path}: {str(e)}")
        return JSONResponse(
            status_code=401,
            content={
                "error": "Unauthorized",
                "message": "Invalid App Check token"
            }
        )
    except ValueError as e:
        logger.error(f"[App Check] Invalid App Check token for {path}: {str(e)}")
        return JSONResponse(
            status_code=401,
            content={
                "error": "Unauthorized",
                "message": "Invalid App Check token"
            }
        )
    except Exception as e:
        logger.error(f"[App Check] Verification error for {path}: {str(e)}")
        return JSONResponse(
            status_code=500,
            content={
                "error": "Internal Server Error",
                "message": "App Check verification failed"
            }
        )


def get_app_check_status():
    """Return current App Check configuration status"""
    return {
        "enabled": APP_CHECK_ENABLED,
        "debug_mode": APP_CHECK_DEBUG,
        "project_id": FIREBASE_PROJECT_ID,
        "protected_paths": PROTECTED_PATHS,
        "exempt_paths": EXEMPT_PATHS
    }
