"""
FastAPI Basics - Learning Sample

FastAPI is a modern Python web framework for building REST APIs.
It's fast, easy to use, and auto-generates documentation.

Run this file:
    uvicorn sample_fastapi:app --reload

Then open:
    http://127.0.0.1:8000        → See "Hello World"
    http://127.0.0.1:8000/docs   → Interactive API documentation (Swagger UI)
"""

from fastapi import FastAPI, HTTPException
from pydantic import BaseModel

# ============================================
# STEP 1: Create the FastAPI app
# ============================================

app = FastAPI(
    title="MediBot Learning API",
    description="A simple API to learn FastAPI concepts",
    version="1.0.0"
)


# ============================================
# STEP 2: Define data models with Pydantic
# ============================================
# Pydantic models define the structure of request/response data
# FastAPI automatically validates incoming data against these models

class LoginRequest(BaseModel):
    """Request body for login endpoint"""
    username: str
    password: str

class LoginResponse(BaseModel):
    """Response body for login endpoint"""
    message: str
    role: str
    token: str

class ChatRequest(BaseModel):
    """Request body for chat endpoint"""
    question: str
    role: str

class ChatResponse(BaseModel):
    """Response body for chat endpoint"""
    answer: str
    retrieval_type: str
    role: str


# ============================================
# STEP 3: Define fake data (in real app, use database)
# ============================================

DEMO_USERS = {
    "dr.mehta": {"password": "doctor", "role": "doctor"},
    "nurse.priya": {"password": "nurse", "role": "nurse"},
    "admin.sys": {"password": "admin", "role": "admin"},
}


# ============================================
# STEP 4: Create endpoints (routes)
# ============================================

# GET endpoint - simplest form
# Access via: http://127.0.0.1:8000/
@app.get("/")
def root():
    """Root endpoint - just returns a welcome message"""
    return {"message": "Welcome to MediBot API!"}


# GET endpoint with path parameter
# Access via: http://127.0.0.1:8000/greet/Himesh
@app.get("/greet/{name}")
def greet(name: str):
    """
    Greet a user by name.

    Path parameter: {name} is extracted from the URL
    """
    return {"message": f"Hello, {name}!"}


# GET endpoint - health check
# Access via: http://127.0.0.1:8000/health
@app.get("/health")
def health_check():
    """Health check endpoint - useful for monitoring"""
    return {"status": "healthy", "service": "medibot-api"}


# GET endpoint with path parameter
# Access via: http://127.0.0.1:8000/collections/nurse
@app.get("/collections/{role}")
def get_collections(role: str):
    """
    Return accessible collections for a given role.

    This demonstrates:
    - Path parameters (role comes from URL)
    - Conditional logic based on input
    """
    ROLE_ACCESS = {
        "doctor": ["clinical", "nursing", "general"],
        "nurse": ["nursing", "general"],
        "billing_executive": ["billing", "general"],
        "technician": ["equipment", "general"],
        "admin": ["clinical", "nursing", "billing", "equipment", "general"],
    }

    if role not in ROLE_ACCESS:
        # HTTPException returns an error response
        raise HTTPException(status_code=404, detail=f"Role '{role}' not found")

    return {
        "role": role,
        "collections": ROLE_ACCESS[role]
    }


# POST endpoint - receives data in request body
# Access via: POST http://127.0.0.1:8000/login with JSON body
@app.post("/login", response_model=LoginResponse)
def login(request: LoginRequest):
    """
    Login endpoint.

    This demonstrates:
    - POST request (sends data in body, not URL)
    - Pydantic model for request validation (LoginRequest)
    - Pydantic model for response structure (LoginResponse)
    - Error handling with HTTPException
    """
    # Check if user exists
    if request.username not in DEMO_USERS:
        raise HTTPException(status_code=401, detail="Invalid username")

    # Check password
    user = DEMO_USERS[request.username]
    if request.password != user["password"]:
        raise HTTPException(status_code=401, detail="Invalid password")

    # Return success response
    return LoginResponse(
        message="Login successful",
        role=user["role"],
        token=f"fake-jwt-token-for-{user['role']}"  # In real app, generate real JWT
    )


# POST endpoint - main chat endpoint
@app.post("/chat", response_model=ChatResponse)
def chat(request: ChatRequest):
    """
    Main chat endpoint.

    This demonstrates:
    - How the real MediBot /chat endpoint will work
    - Query routing logic (analytical vs document questions)
    """
    question = request.question.lower()
    role = request.role

    # Simple query routing (in real app, use LLM or better logic)
    is_analytical = any(word in question for word in ["how many", "count", "total", "average"])

    if is_analytical:
        # Route to SQL RAG
        if role not in ["billing_executive", "admin"]:
            return ChatResponse(
                answer=f"As a {role}, you don't have access to analytics data.",
                retrieval_type="sql_rag",
                role=role
            )
        return ChatResponse(
            answer="[SQL RAG] There are 17 pending claims totaling $1,043,000.",
            retrieval_type="sql_rag",
            role=role
        )
    else:
        # Route to Hybrid RAG
        return ChatResponse(
            answer="[Hybrid RAG] Based on the nursing procedures document, IV cannula size for pediatric patients under 5kg is 24G.",
            retrieval_type="hybrid_rag",
            role=role
        )


# ============================================
# STEP 5: Run the app
# ============================================
#
# Option 1: Command line
#     uvicorn sample_fastapi:app --reload
#
# Option 2: Add this at the bottom and run with python
if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)


# ============================================
# KEY CONCEPTS SUMMARY
# ============================================
#
# 1. @app.get("/path")   → GET request (fetch data)
# 2. @app.post("/path")  → POST request (send data)
# 3. Path parameters     → @app.get("/users/{user_id}")
# 4. Request body        → def func(request: PydanticModel)
# 5. Response model      → @app.post("/path", response_model=Model)
# 6. HTTPException       → Return error responses
# 7. /docs               → Auto-generated Swagger UI
#
# ============================================
