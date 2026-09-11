# Learning Resources

This directory contains learning scripts and guides for understanding the technologies used in MediBot.

---

## Contents

| Script | Purpose |
|--------|---------|
| `database_explorer.py` | Explore the SQLite database structure |
| `explore_qdrant.py` | Explore the Qdrant vector database |
| `sample_fastapi.py` | Learn FastAPI basics |

---

# 1. Database Explorer

A simple script to explore the `mediassist.db` SQLite database used for SQL RAG.

## How to Run

```bash
cd /home/himesh/codebasics_cohort/AI_Projects/Medibot_Hybrid_And_Sql_RAG

python3 learning/database_explorer.py
```

## Database Overview

The `mediassist.db` database contains **2 tables**:

### 1.1 `claims` Table

Billing claims across hospital departments.

| Column | Type | Description |
|--------|------|-------------|
| claim_id | TEXT | Unique claim ID (e.g., CLM-2024-1000) |
| patient_id | TEXT | Patient ID |
| patient_name | TEXT | Patient name |
| department | TEXT | Hospital department (cardiology, neurology, etc.) |
| claim_type | TEXT | Type (cashless, reimbursement) |
| diagnosis_code | TEXT | ICD diagnosis code |
| insurer | TEXT | Insurance company |
| claimed_amount | REAL | Amount claimed |
| approved_amount | REAL | Amount approved (NULL if pending) |
| status | TEXT | Status (pending, approved, rejected, escalated) |
| submitted_date | TEXT | Date submitted |
| resolved_date | TEXT | Date resolved (NULL if pending) |

### 1.2 `maintenance_tickets` Table

Equipment maintenance records.

| Column | Type | Description |
|--------|------|-------------|
| ticket_id | TEXT | Unique ticket ID (e.g., TKT-2024-2000) |
| equipment_name | TEXT | Equipment name |
| equipment_id | TEXT | Equipment ID |
| category | TEXT | Category (infusion, sterilisation, imaging, etc.) |
| campus | TEXT | Hospital campus |
| issue_type | TEXT | Type of issue |
| fault_code | TEXT | Fault code (if any) |
| raised_by | TEXT | Person who raised the ticket |
| raised_date | TEXT | Date raised |
| resolved_date | TEXT | Date resolved |
| status | TEXT | Status (in_progress, resolved, pending) |
| resolution_note | TEXT | Notes on resolution |

## Example SQL Queries

### Claims Queries
```sql
-- Count pending claims
SELECT COUNT(*) FROM claims WHERE status = 'pending';

-- Total claimed amount by department
SELECT department, SUM(claimed_amount) FROM claims GROUP BY department;

-- Average approved amount by insurer
SELECT insurer, AVG(approved_amount) FROM claims 
WHERE approved_amount IS NOT NULL GROUP BY insurer;
```

### Maintenance Queries
```sql
-- Count tickets by status
SELECT status, COUNT(*) FROM maintenance_tickets GROUP BY status;

-- Equipment with most issues
SELECT equipment_name, COUNT(*) as issues 
FROM maintenance_tickets GROUP BY equipment_name ORDER BY issues DESC;
```

## SQL RAG Access Control

| Role | Access |
|------|--------|
| billing_executive | Can query both tables |
| admin | Can query both tables |
| doctor, nurse, technician | No access to SQL RAG |

---

# 2. Qdrant Explorer

A script to explore the Qdrant vector database used for Hybrid RAG.

## What is Qdrant?

Qdrant is a vector database that stores:
- **Dense vectors**: 384-dimensional embeddings for semantic search
- **Sparse vectors**: BM25 vectors for keyword search
- **Metadata/Payload**: Information about each chunk (source, collection, access_roles, etc.)

## How to Run

```bash
cd /home/himesh/codebasics_cohort/AI_Projects/Medibot_Hybrid_And_Sql_RAG

python3 learning/explore_qdrant.py
```

## What the Script Shows

### 2.1 Collections
```
Collections in Qdrant:
  - medibot_docs_vectorstore
```

### 2.2 Collection Info
```
Collection: medibot_docs_vectorstore
  Points count: 409
  Vectors config: {dense: 384-dim, sparse: BM25}
```

### 2.3 Sample Points
```
[Point 1] ID: abc123
  Payload: {
    'page_content': '## IV Cannula Sizes > Pediatric...',
    'metadata': {
      'source_document': 'icu_nursing_procedures.pdf',
      'collection': 'nursing',
      'access_roles': ['nurse', 'doctor', 'admin'],
      'section_title': 'IV Cannula Sizes > Pediatric',
      'chunk_type': 'text'
    }
  }
  Vectors: dense (384-dim), sparse (BM25)
```

## Understanding Stored Data

| Field | Description |
|-------|-------------|
| `id` | Unique identifier for the chunk |
| `payload.page_content` | The actual text content |
| `payload.metadata.source_document` | Original PDF/MD filename |
| `payload.metadata.collection` | Document collection (general, clinical, nursing, billing, equipment) |
| `payload.metadata.access_roles` | List of roles that can access this chunk |
| `payload.metadata.section_title` | Parent heading for context |
| `payload.metadata.chunk_type` | Type: text, table, heading, code |
| `vector.dense` | 384-dim semantic embedding |
| `vector.sparse` | BM25 sparse vector for keyword matching |

## Hybrid Search Flow

```
User Query: "IV cannula size for pediatric patients"
                    |
    +---------------+---------------+
    |                               |
Dense Search                    Sparse Search
(semantic similarity)           (keyword matching)
    |                               |
    +---------------+---------------+
                    |
            Fusion (RRF)
                    |
        Top-K Combined Results
```

## RBAC Filtering

```python
from qdrant_client.models import Filter, FieldCondition, MatchAny

rbac_filter = Filter(
    must=[
        FieldCondition(
            key="metadata.access_roles",
            match=MatchAny(any=["nurse"])  # Only chunks nurse can access
        )
    ]
)
```

## Collection Statistics

| Metric | Value |
|--------|-------|
| Total chunks | 409 |
| Dense vector dimensions | 384 |
| Sparse vector type | BM25 |
| Documents indexed | 12 |
| Collections | 5 (general, clinical, nursing, billing, equipment) |

---

# 3. Sample FastAPI

A beginner-friendly guide to understanding FastAPI.

## What is FastAPI?

FastAPI is a modern, fast Python web framework for building REST APIs:
- **Fast**: High performance (on par with Node.js and Go)
- **Easy**: Intuitive and minimal boilerplate
- **Auto-docs**: Generates interactive API documentation automatically
- **Type-safe**: Uses Python type hints for validation

## How to Run

```bash
cd /home/himesh/codebasics_cohort/AI_Projects/Medibot_Hybrid_And_Sql_RAG

# Install FastAPI (if not already installed)
pip install fastapi[standard]

# Run the server
uvicorn learning.sample_fastapi:app --reload --host 0.0.0.0
```

### Access Points

| URL | Description |
|-----|-------------|
| http://127.0.0.1:8000 | Root endpoint |
| http://127.0.0.1:8000/docs | Interactive Swagger UI |
| http://127.0.0.1:8000/health | Health check |

## Core Concepts

### 3.1 Create the FastAPI App

```python
from fastapi import FastAPI

app = FastAPI(
    title="MediBot Learning API",
    description="A simple API to learn FastAPI concepts",
    version="1.0.0"
)
```

### 3.2 Pydantic Models (Data Validation)

```python
from pydantic import BaseModel

class LoginRequest(BaseModel):
    username: str
    password: str
```

FastAPI automatically validates incoming JSON against these models.

### 3.3 GET Endpoints

```python
@app.get("/health")
def health_check():
    return {"status": "healthy"}
```

### 3.4 Path Parameters

```python
@app.get("/greet/{name}")
def greet(name: str):
    return {"message": f"Hello, {name}!"}
```

### 3.5 POST Endpoints

```python
@app.post("/login")
def login(request: LoginRequest):
    return {"message": "Login successful", "role": "doctor"}
```

### 3.6 Error Handling

```python
from fastapi import HTTPException

if request.username not in DEMO_USERS:
    raise HTTPException(status_code=401, detail="Invalid username")
```

## Available Endpoints

| Endpoint | Method | Purpose |
|----------|--------|---------|
| `/` | GET | Welcome message |
| `/health` | GET | Health check |
| `/greet/{name}` | GET | Greet user |
| `/collections/{role}` | GET | Get role's collections |
| `/login` | POST | Authenticate user |
| `/chat` | POST | Chat with MediBot |

## Testing the API

### Using Swagger UI (Recommended)
1. Go to http://127.0.0.1:8000/docs
2. Click on an endpoint
3. Click "Try it out"
4. Fill in parameters/body
5. Click "Execute"

### Using curl
```bash
# GET request
curl http://127.0.0.1:8000/health

# POST request
curl -X POST http://127.0.0.1:8000/login \
  -H "Content-Type: application/json" \
  -d '{"username": "dr.mehta", "password": "doctor"}'
```

## Quick Reference

| Concept | Code |
|---------|------|
| Create app | `app = FastAPI()` |
| GET endpoint | `@app.get("/path")` |
| POST endpoint | `@app.post("/path")` |
| Path parameter | `@app.get("/users/{id}")` |
| Request body | `def func(request: PydanticModel)` |
| Error response | `raise HTTPException(status_code=404, detail="Not found")` |
| Auto docs | Visit `/docs` |

---

## Related Files

| File | Purpose |
|------|---------|
| `mediassist_data/db/mediassist.db` | SQLite database |
| `backend/qdrant_data/` | Qdrant vector storage |
| `backend/rag_pipeline.py` | Main RAG pipeline |
| `backend/main.py` | Production FastAPI app |
