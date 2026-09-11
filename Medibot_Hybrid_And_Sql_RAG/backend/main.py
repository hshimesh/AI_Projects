"""
MediBot FastAPI Backend
REST API for MediBot RAG chatbot with RBAC
"""

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

# Import from ingest.py to avoid duplication
from backend.rag_pipeline import (
    COLLECTION_ACCESS_ROLES,
    is_analytical_question,
    sql_rag_chain,
    hybrid_rag_chain,
)


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

    Example:
        {"role": "doctor", "collections": ["general", "clinical", "nursing"]}
    """
    role: str
    collections: list[str]


class ChatRequest(BaseModel):
    """
    Chat request body.

    Example:
        {"question": "What is the IV cannula size for pediatric patients?", "role": "nurse"}
    """
    question: str
    role: str


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
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # Allow all origins (for development)
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
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
# ENDPOINTS (to be implemented)
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

    # Return role and collections
    role = user["role"]
    collections = get_collections_for_role(role)
    return LoginResponse(role=role, collections=collections)


@app.get("/collections/{role}")
def get_collections(role: str):
    """
    Get list of document collections accessible to a role.

    Example:
        GET /collections/nurse -> {"role": "nurse", "collections": ["general", "nursing"]}
    """
    valid_roles = ["doctor", "nurse", "billing_executive", "technician", "admin"]
    if role not in valid_roles:
        raise HTTPException(status_code=400, detail=f"Invalid role: {role}")

    collections = get_collections_for_role(role)
    return {"role": role, "collections": collections}


@app.post("/chat", response_model=ChatResponse)
def chat(request: ChatRequest):
    """
    Main RAG endpoint. Routes to SQL RAG or Hybrid RAG based on question type.

    Query Routing:
        - Analytical questions (counts, totals, etc.) → SQL RAG (billing_executive/admin only)
        - Other questions → Hybrid RAG with RBAC filtering

    Example:
        POST /chat {"question": "How many claims are pending?", "role": "admin"}
        -> {"answer": "There are 17 pending claims...", "sources": [...], "retrieval_type": "sql_rag", "role": "admin"}
    """
    question = request.question
    role = request.role

    # Validate role
    valid_roles = ["doctor", "nurse", "billing_executive", "technician", "admin"]
    if role not in valid_roles:
        raise HTTPException(status_code=400, detail=f"Invalid role: {role}")

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
