"""
MediBot FastAPI Backend
REST API for MediBot RAG chatbot with RBAC
"""

import os
from datetime import datetime, timedelta, timezone

import jwt
from dotenv import load_dotenv
from fastapi import Depends, FastAPI, HTTPException, Response, status
from fastapi.middleware.cors import CORSMiddleware
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from pydantic import BaseModel

# Import from ingest.py to avoid duplication
from backend.rag_pipeline import (
    COLLECTION_ACCESS_ROLES,
    is_analytical_question,
    sql_rag_chain,
    hybrid_rag_chain,
)

load_dotenv()

# ============================================
# JWT CONFIGURATION
# ============================================

# The signing secret is the only thing preventing a client from forging a token
# with "role": "admin". It must never be committed - it lives in .env, which is
# gitignored. Generate one with:
#     python -c "import secrets; print(secrets.token_urlsafe(32))"
JWT_SECRET = os.getenv("JWT_SECRET")
if not JWT_SECRET:
    raise RuntimeError(
        "JWT_SECRET is not set. Add it to your .env file:\n"
        '  JWT_SECRET=<python -c "import secrets; print(secrets.token_urlsafe(32))">'
    )

JWT_ALGORITHM = "HS256"

# Idle timeout. Every authenticated request mints a replacement token with a
# fresh window, so the session only ends after this long with no activity.
JWT_EXPIRY_MINUTES = 30

# Hard ceiling on a single login, regardless of activity (~one hospital shift).
# Past this, tokens stop being refreshed and the user must re-authenticate.
JWT_MAX_SESSION_HOURS = 8

# Response header carrying the refreshed token back to the client. Must be
# listed in the CORS expose_headers below, or the browser hides it from JS.
REFRESH_HEADER = "X-Refreshed-Token"

VALID_ROLES = ["doctor", "nurse", "billing_executive", "technician", "admin"]


# ============================================
# PYDANTIC MODELS (Request/Response Validation)
# ============================================

class LoginRequest(BaseModel):
    """
    Login request body.

    Example:
        {"username": "dr.mehta", "password": "doctor"}
    """
    username: str
    password: str


class LoginResponse(BaseModel):
    """
    Login response.

    `role` and `collections` are returned for display only (the sidebar badge and
    collection list). Authorization is driven entirely by `token` - the server
    never trusts a role sent back by the client.

    Example:
        {"token": "eyJhbGci...", "role": "doctor", "collections": ["general", "clinical", "nursing"]}
    """
    token: str
    role: str
    collections: list[str]


class ChatRequest(BaseModel):
    """
    Chat request body.

    Note there is deliberately no `role` field: the caller does not get to state
    who they are. The role is read from the verified bearer token instead.

    Example:
        {"question": "What is the IV cannula size for pediatric patients?"}
    """
    question: str


class ChatResponse(BaseModel):
    """
    Chat response.

    Example:
        {
            "answer": "For pediatric patients under 5kg...",
            "sources": [{"source_document": "icu_nursing.pdf", "section_title": "IV Cannula", "collection": "nursing"}],
            "retrieval_type": "hybrid_rag",
            "role": "nurse"
        }
    """
    answer: str
    sources: list[dict]
    retrieval_type: str
    role: str

# ============================================
# FASTAPI APP
# ============================================

app = FastAPI(
    title="MediBot API",
    description="MediAssist Health Network RAG Chatbot with RBAC",
    version="1.0.0"
)

# CORS middleware - allow frontend to access backend
#
# allow_credentials is False because auth travels in the Authorization header,
# not cookies. (Browsers reject allow_origins=["*"] combined with credentials.)
# expose_headers is required for the frontend to see the refreshed token.
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # Allow all origins (for development)
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"],
    expose_headers=[REFRESH_HEADER],
)

# ============================================
# DEMO USERS (from assignment spec)
# ============================================

DEMO_USERS = {
    "dr.mehta": {"password": "doctor", "role": "doctor"},
    "nurse.priya": {"password": "nurse", "role": "nurse"},
    "billing.ravi": {"password": "billing", "role": "billing_executive"},
    "tech.anand": {"password": "tech", "role": "technician"},
    "admin.sys": {"password": "admin", "role": "admin"},
}

# ============================================
# ROLE → COLLECTIONS MAPPING
# ============================================

def get_collections_for_role(role: str) -> list[str]:
    """
    Get list of collections accessible to a role.
    Derived from COLLECTION_ACCESS_ROLES (collection → roles) in ingest.py.

    Example:
        get_collections_for_role("nurse") -> ["general", "nursing"]
    """
    collections = []
    for collection, roles in COLLECTION_ACCESS_ROLES.items():
        if role in roles:
            collections.append(collection)
    return collections


# ============================================
# AUTHENTICATION (JWT with sliding expiry)
# ============================================

# auto_error=False so a missing header returns our own 401 rather than
# HTTPBearer's default 403.
security = HTTPBearer(auto_error=False)


def _unauthorized(detail: str) -> HTTPException:
    """401 with the WWW-Authenticate header the Bearer scheme expects."""
    return HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail=detail,
        headers={"WWW-Authenticate": "Bearer"},
    )


def mint_token(username: str, role: str, auth_time: int | None = None) -> str:
    """
    Create a signed JWT valid for JWT_EXPIRY_MINUTES.

    `auth_time` is the timestamp of the original login. It is carried forward
    unchanged through every refresh so JWT_MAX_SESSION_HOURS can be enforced
    against the real session start rather than the last refresh.
    """
    now = datetime.now(timezone.utc)

    # No auth_time passed = this is a fresh login, so stamp the session start.
    # On a refresh the caller passes the original value straight through.
    if auth_time is None:
        auth_time = int(now.timestamp())

    payload = {
        "sub": username,        # who the token belongs to
        "role": role,           # the only source of authority for RBAC filtering
        "auth_time": auth_time, # original login - anchors the 8-hour absolute cap
        "iat": now,             # when this particular token was issued
        "exp": now + timedelta(minutes=JWT_EXPIRY_MINUTES),  # idle deadline
    }

    # Signing binds the payload to JWT_SECRET: change any field and the
    # signature no longer matches, and only this server can produce a new one.
    return jwt.encode(payload, JWT_SECRET, algorithm=JWT_ALGORITHM)


def verify_token(token: str) -> dict:
    """
    Verify a token's signature and expiry, returning its claims.

    jwt.decode() checks both: a payload edited to say "role": "admin" no longer
    matches its signature, and an expired token raises. Either way -> 401.
    """
    try:
        # Recomputes the signature over the payload that arrived and compares it
        # to the one attached; also rejects the token if `exp` has passed.
        return jwt.decode(token, JWT_SECRET, algorithms=[JWT_ALGORITHM])
    except jwt.ExpiredSignatureError:
        # Genuine token, but its window closed. Distinct message so the frontend
        # can say "session expired" instead of a generic failure.
        raise _unauthorized("Session expired. Please log in again.")
    except jwt.InvalidTokenError:
        # Tampered payload, wrong signing key, or malformed string.
        raise _unauthorized("Invalid authentication token.")


def get_current_user(
    response: Response,
    credentials: HTTPAuthorizationCredentials | None = Depends(security),
) -> dict:
    """
    FastAPI dependency: the single point where a caller's role is established.

    Verifies the bearer token and, while the session is inside its absolute cap,
    attaches a replacement token with a fresh idle window to the response. That
    sliding refresh is why an active user is never logged out mid-conversation.
    """
    # No Authorization header at all - the request never reaches the endpoint.
    if credentials is None:
        raise _unauthorized("Not authenticated. Log in to obtain a token.")

    # Raises 401 on a forged, malformed or expired token.
    payload = verify_token(credentials.credentials)

    # Defence in depth: a token we signed should always carry a known role, but
    # never pass an unexpected value down to the RBAC filter.
    role = payload.get("role")
    if role not in VALID_ROLES:
        raise _unauthorized("Token contains an unrecognised role.")

    # Sliding expiry: hand back a replacement token with a fresh 30-minute
    # window, so only inactivity ends the session. auth_time is passed through
    # unchanged, so the 8-hour ceiling stays pinned to the original login.
    auth_time = payload.get("auth_time", 0)
    session_age_hours = (datetime.now(timezone.utc).timestamp() - auth_time) / 3600
    
    if session_age_hours < JWT_MAX_SESSION_HOURS:
        # Past the cap we simply stop renewing; the current token still runs out
        # its remaining minutes, then the user has to log in again.
        response.headers[REFRESH_HEADER] = mint_token(
            payload["sub"], role, auth_time
        )

    # Endpoints read user["role"] from this - never from the request body.
    return payload


# ============================================
# ENDPOINTS
# ============================================

@app.get("/health")
def health_check():
    """Health check endpoint."""
    return {"status": "healthy"}


@app.post("/login", response_model=LoginResponse)
def login(request: LoginRequest):
    """
    Authenticate user and return role with accessible collections.

    Example:
        POST /login {"username": "dr.mehta", "password": "doctor"}
        -> {"role": "doctor", "collections": ["general", "clinical", "nursing"]}
    """
    # Check if username exists
    if request.username not in DEMO_USERS:
        raise HTTPException(status_code=401, detail="Invalid username")

    # Check password
    user = DEMO_USERS[request.username]
    if request.password != user["password"]:
        raise HTTPException(status_code=401, detail="Invalid password")

    # Issue a signed token carrying the role. Everything after this point
    # derives the role from the token, never from the request body.
    role = user["role"]
    collections = get_collections_for_role(role)
    token = mint_token(request.username, role)
    return LoginResponse(token=token, role=role, collections=collections)


@app.get("/collections/{role}")
def get_collections(role: str, user: dict = Depends(get_current_user)):
    """
    Get the document collections accessible to a role.

    The role in the path is checked against the authenticated token: you may
    only ask about your own role. Requesting another role's collections returns
    403 rather than disclosing them.

    Example:
        GET /collections/nurse  (Authorization: Bearer <nurse token>)
        -> {"role": "nurse", "collections": ["general", "nursing"]}

        GET /collections/admin  (Authorization: Bearer <nurse token>)
        -> 403 Forbidden
    """
    if role != user["role"]:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=f"Authenticated as '{user['role']}' - cannot view collections for '{role}'.",
        )

    return {"role": role, "collections": get_collections_for_role(role)}


@app.post("/chat", response_model=ChatResponse)
def chat(request: ChatRequest, user: dict = Depends(get_current_user)):
    """
    Main RAG endpoint. Routes to SQL RAG or Hybrid RAG based on question type.

    Query Routing:
        - Analytical questions (counts, totals, etc.) → SQL RAG (billing_executive/admin only)
        - Other questions → Hybrid RAG with RBAC filtering

    The role used for RBAC filtering comes from the verified token, so it cannot
    be forged by the caller.

    Example:
        POST /chat {"question": "How many claims are pending?"}
        Authorization: Bearer <admin token>
        -> {"answer": "There are 17 pending claims...", "sources": [...], "retrieval_type": "sql_rag", "role": "admin"}
    """
    question = request.question
    role = user["role"]

    # Query routing: SQL RAG or Hybrid RAG?
    if is_analytical_question(question):
        # SQL RAG for analytical questions
        result = sql_rag_chain(question, role)
    else:
        # Hybrid RAG for document-based questions
        result = hybrid_rag_chain(question, role)

    return ChatResponse(
        answer=result["answer"],
        sources=result.get("sources", []),
        retrieval_type=result["retrieval_type"],
        role=result["role"]
    )


# Main block for running with uvicorn directly
if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
