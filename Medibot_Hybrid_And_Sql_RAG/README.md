# MediBot - Hybrid and SQL RAG Chatbot with RBAC

An intelligent medical assistant for MediAssist Health Network featuring Hybrid RAG, SQL RAG, Cross-Encoder Reranking, and Role-Based Access Control (RBAC) enforced at the retrieval layer.

---

## Business Context

**MediAssist Health Network** is a mid-sized private healthcare group operating across 12 hospitals and 40+ clinics in India. Internal knowledge (clinical treatment protocols, drug formularies, hospital policy handbooks, insurance billing guides, and equipment maintenance manuals) is scattered across hundreds of PDFs.

**Problems Solved:**
- **Knowledge Retrieval:** Doctors, nurses, and technicians waste time searching outdated PDFs
- **Access Control Leakage:** A ward nurse should not be able to query drug procurement pricing or executive financial reports

**Solution:** MediBot - an internal intelligent assistant with **intelligent retrieval** and **Role-Based Access Control (RBAC)** enforced at the vector-database retrieval layer.

---

## MediBot UI

![MediBot UI](images/Medibot_Screenshot.jpg)

---

## Features

- **Hybrid RAG:** Combines dense vector search (semantic) with BM25 sparse search (keyword) for better retrieval
- **Cross-Encoder Reranking:** Two-stage retrieval (fetch 10 → rerank → top 3) for improved relevance
- **SQL RAG:** Answers analytical questions by generating and executing SQL queries
- **RBAC at Retrieval Layer:** Role-based document filtering enforced at Qdrant query level (not just UI)
- **Token-Based Auth:** Login issues a signed JWT; the role is read from the verified token, never from the request body
- **Sliding Session Expiry:** 30-minute *idle* timeout that renews on activity, with an 8-hour absolute cap
- **Query Routing:** LLM-based classifier routes questions to Hybrid RAG or SQL RAG
- **Hierarchical Chunking:** Docling preserves document structure (headings, tables, code blocks)
- **Source Citations:** Document-backed answers include document name, section title, and collection; greetings and "not found" responses cite nothing
- **5 Demo Accounts:** Color-coded login for different hospital roles

---

## Architecture

```
┌──────────────────────────────────────────────────────────────────────────────────┐
│                               MediBot System                                      │
├──────────────────────────────────────────────────────────────────────────────────┤
│                                                                                   │
│  ┌─────────────────┐         ┌──────────────────────────────────────────────────┐│
│  │   Next.js       │ Bearer  │                  FastAPI Backend                  ││
│  │   Frontend      │────────▶│                                                   ││
│  │   (Port 3000)   │  token  │  ┌────────────────────────────────────────────┐  ││
│  └─────────────────┘         │  │          get_current_user()                │  ││
│         ▲                    │  │  verify JWT signature + expiry → role      │  ││
│         │                    │  │  (401 if missing/forged/expired)           │  ││
│         └────────────────────│  └────────────────────────────────────────────┘  ││
│          X-Refreshed-Token   │                      │                            ││
│          (sliding expiry)    │                      ▼                            ││
│                              │  ┌────────────────────────────────────────────┐  ││
│                              │  │         is_analytical_question()           │  ││
│                              │  │         (LLM-based Query Router)           │  ││
│                              │  └────────────────────────────────────────────┘  ││
│                              │                      │                            ││
│                              │          ┌───────────┴───────────┐                ││
│                              │          │ SQL?                  │ DOCUMENT?      ││
│                              │          ▼                       ▼                ││
│                              │  ┌──────────────┐        ┌──────────────┐         ││
│                              │  │ sql_rag_chain│        │hybrid_rag    │         ││
│                              │  │     ()       │        │  _chain()    │         ││
│                              │  └──────┬───────┘        └──────┬───────┘         ││
│                              │         │                       │                 ││
│                              │         │               Cross-Encoder Reranking   ││
│                              │         │                 + RBAC Filter           ││
│                              │         │                       │                 ││
│                              └─────────┼───────────────────────┼─────────────────┘│
│                                        │                       │                  │
│                                        ▼                       ▼                  │
│            ┌─────────────────────────────┐       ┌─────────────────────────────┐  │
│            │     SQLite Database         │       │    Qdrant Vector Store      │  │
│            │  - claims                   │       │    - Dense: BAAI/bge-m3     │  │
│            │  - maintenance_tickets      │       │    - Sparse: BM25           │  │
│            └─────────────────────────────┘       └─────────────────────────────┘  │
└──────────────────────────────────────────────────────────────────────────────────┘
```

---

## Tech Stack

### Backend
| Technology | Purpose |
|------------|---------|
| **Python 3.12** | Runtime |
| **FastAPI** | REST API framework |
| **LangChain** | RAG chain orchestration |
| **Docling** | PDF/MD parsing with structure awareness |
| **Qdrant** | Vector database with hybrid search |
| **BAAI/bge-m3** | Dense embeddings (1024-dim, 8192 token context) |
| **BM25** | Sparse embeddings for keyword search |
| **Cross-Encoder** | ms-marco-MiniLM-L-6-v2 for reranking |
| **Groq API** | LLM inference (qwen/qwen3.8-27b or openai/gpt-oss-120b) |
| **SQLite** | Database for claims and maintenance tickets |
| **PyJWT** | Signed session tokens (HS256) |

### Frontend
| Technology | Purpose |
|------------|---------|
| **Next.js 16** | React framework (App Router) |
| **TypeScript** | Type-safe JavaScript |
| **Tailwind CSS** | Styling |
| **react-markdown** | Markdown rendering in responses |

### Tools
| Tool | Purpose |
|------|---------|
| **uv** | Fast Python package manager |
| **nvm** | Node.js version manager |

---

## Demo Accounts

| Username | Password | Role | Accessible Collections |
|----------|----------|------|------------------------|
| dr.mehta | doctor | Doctor | general, clinical, nursing |
| nurse.priya | nurse | Nurse | general, nursing |
| billing.ravi | billing | Billing Executive | general, billing, mediassist.db |
| tech.anand | tech | Technician | general, equipment |
| admin.sys | admin | Admin | all collections + mediassist.db |

---

## User Roles & Access Matrix

| Collection | Documents | doctor | nurse | billing_executive | technician | admin |
|------------|-----------|--------|-------|-------------------|------------|-------|
| `general` | HR handbook, leave policy, code of conduct | ✅ | ✅ | ✅ | ✅ | ✅ |
| `clinical` | Treatment protocols, drug formulary | ✅ | ❌ | ❌ | ❌ | ✅ |
| `nursing` | ICU procedures, infection control | ✅ | ✅ | ❌ | ❌ | ✅ |
| `billing` | Insurance codes, claim procedures | ❌ | ❌ | ✅ | ❌ | ✅ |
| `equipment` | Maintenance manuals, calibration guides | ❌ | ❌ | ❌ | ✅ | ✅ |
| **mediassist.db** | Claims & maintenance analytics | ❌ | ❌ | ✅ | ❌ | ✅ |

---

## Setup

### Prerequisites

- Python 3.10+
- Node.js 20+ (via nvm)
- Groq API Key (free at [console.groq.com](https://console.groq.com/keys))
- uv (fast Python package manager)

### Step 1: Clone the Repository

```bash
git clone <your-repo-url>
cd Medibot_Hybrid_And_Sql_RAG
```

### Step 2: Install uv (Python Package Manager)

```bash
# Install uv
curl -LsSf https://astral.sh/uv/install.sh | sh
source ~/.bashrc

# Verify
uv --version
```

### Step 3: Install nvm and Node.js

```bash
# Install nvm
curl -o- https://raw.githubusercontent.com/nvm-sh/nvm/v0.39.7/install.sh | bash
source ~/.bashrc

# Install Node.js LTS
nvm install --lts

# Verify
node --version
npm --version
```

### Step 4: Create .env File

**First, generate your own `JWT_SECRET`.** This key signs the auth tokens, so
anyone who knows it can forge an admin session. Generate a fresh one — never
reuse the example below, and never commit it:

```bash
python3 -c "import secrets; print(secrets.token_urlsafe(32))"
```

Then create a `.env` file in the project root, pasting that value in:

```bash
GROQ_API_KEY=gsk_your_api_key_here
GROQ_MODEL=openai/gpt-oss-120b
# OR
#GROQ_MODEL=qwen/qwen3.8-27b

JWT_SECRET=paste_the_generated_secret_here
```

The backend refuses to start if `JWT_SECRET` is missing, rather than falling
back to an insecure default.

### Step 5: Setup Backend

```bash
# Create virtual environment
uv venv

# Activate virtual environment
source .venv/bin/activate

# Install dependencies
uv pip install -r requirements.txt
```

### Step 6: Setup Frontend

```bash
cd frontend
npm install
cd ..
```

### Step 7: Run Ingestion (First Time Only)

```bash
source .venv/bin/activate
python backend/rag_pipeline.py
```

This will:
- Parse all documents from `mediassist_data/`
- Create chunks with RBAC metadata
- Store in Qdrant (`backend/qdrant_data/`)
- Run test queries

### Step 8: Running the MediBot Application (Frontend + Backend)

#### Option 1: Run frontend + backend together (Recommended)

```bash
./run_frontend_and_backend.sh
```

- Starts both backend and frontend
- Press `Ctrl+C` to stop both
- Colored output shows status

**Note (Linux only):** If you get "OS file watch limit reached" error, run this before starting:
```bash
sudo sysctl fs.inotify.max_user_watches=524288
```

#### Option 2: Run frontend and backend separately (Two Terminals)

**Terminal 1: Backend**
```bash
cd Medibot_Hybrid_And_Sql_RAG
source .venv/bin/activate
uvicorn backend.main:app --reload --host 0.0.0.0
# Runs on http://localhost:8000
```

**Terminal 2: Frontend**
```bash
cd Medibot_Hybrid_And_Sql_RAG/frontend
npm run dev -- -H 0.0.0.0
# Runs on http://localhost:3000
```

#### Access Points

| URL | Description |
|-----|-------------|
| http://localhost:3000 | Frontend (MediBot Chat) |
| http://localhost:8000 | Backend API |
| http://localhost:8000/docs | Swagger API Documentation |

---

## Project Structure

```
Medibot_Hybrid_And_Sql_RAG/
├── backend/
│   ├── main.py                 # FastAPI application
│   ├── rag_pipeline.py         # RAG pipeline (ingestion, retrieval, chains)
│   ├── qdrant_data/            # Vector database storage
│   └── README.md               # Backend documentation
├── frontend/
│   ├── src/
│   │   ├── app/                # Next.js pages (login, chat)
│   │   └── lib/api.ts          # API client
│   ├── next.config.ts          # Next.js config
│   └── README.md               # Frontend documentation
├── mediassist_data/
│   ├── general/                # HR docs (all roles)
│   ├── clinical/               # Medical protocols (doctor, admin)
│   ├── nursing/                # Nursing procedures (nurse, doctor, admin)
│   ├── billing/                # Insurance docs (billing_executive, admin)
│   ├── equipment/              # Maintenance manuals (technician, admin)
│   └── db/mediassist.db        # SQLite database
├── learning/
│   ├── database_explorer.py    # Explore SQLite database
│   ├── explore_qdrant.py       # Explore Qdrant vectors
│   ├── sample_fastapi.py       # FastAPI learning script
│   └── README.md               # Learning resources
├── project_instructions/
│   ├── MediBot_Requirement_Instructions.pdf
│   └── Medibot_Requirement_Instruction.md
├── .env                        # Environment variables (not in git)
├── requirements.txt            # Python dependencies
├── run_frontend_and_backend.sh # Script to run both services
└── README.md                   # This file
```

---

## API Reference

All endpoints except `/login` and `/health` require a bearer token:
`Authorization: Bearer <token>`

### POST /login

The only public endpoint. Returns a signed JWT valid for 30 minutes.

```json
// Request
{"username": "dr.mehta", "password": "doctor"}

// Response
{
  "token": "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9...",
  "role": "doctor",
  "collections": ["general", "clinical", "nursing"]
}
```

`role` and `collections` are returned for **display only** (sidebar badge and
collection list). Authorization is driven entirely by `token`.

### POST /chat

Note there is no `role` field in the request — the server reads it from the token.

```json
// Request  (header: Authorization: Bearer <token>)
{"question": "What is IV cannula size for pediatric?"}

// Response
{
  "answer": "For pediatric patients under 5kg, use 24G IV cannula...",
  "sources": [{"source_document": "icu_nursing.pdf", "section_title": "IV Cannula > Pediatric", "collection": "nursing"}],
  "retrieval_type": "hybrid_rag",
  "role": "nurse"
}
```

Every authenticated response also carries an `X-Refreshed-Token` header holding a
replacement token with a fresh 30-minute window. The frontend swaps it in
automatically, which is what makes the timeout idle-based rather than absolute.

### GET /collections/{role}

The role in the path is checked against the token — you can only ask about your
own role.

```json
// GET /collections/nurse   (header: Authorization: Bearer <nurse token>)
{"role": "nurse", "collections": ["general", "nursing"]}

// GET /collections/admin   (header: Authorization: Bearer <nurse token>)
// 403 Forbidden
{"detail": "Authenticated as 'nurse' - cannot view collections for 'admin'."}
```

### Testing in Swagger

http://localhost:8000/docs has an **Authorize** button. Call `/login`, copy the
`token` from the response, paste it into Authorize, and the protected endpoints
become callable from the browser.

---

## Authentication & Authorization

Two separate layers, both enforced server-side:

```
┌─────────────────────────────────────────────────────────────────────┐
│  1. AUTHENTICATION — who are you?                                   │
│                                                                      │
│     POST /login  ──▶  password checked  ──▶  signed JWT             │
│                                                                      │
│     payload: {sub, role, auth_time, iat, exp}                       │
│     signature: HMAC-SHA256(header.payload, JWT_SECRET)              │
│                                                                      │
│     Editing the payload to "role":"admin" breaks the signature.      │
│     Producing a valid one requires JWT_SECRET, which never leaves    │
│     the server.                                                      │
└─────────────────────────────────────────────────────────────────────┘
                                 │
                                 ▼
┌─────────────────────────────────────────────────────────────────────┐
│  2. AUTHORIZATION — what may you see?                               │
│                                                                      │
│     role (from verified token)  ──▶  Qdrant metadata filter          │
│                                                                      │
│     Restricted documents are never retrieved, so they never reach    │
│     the LLM context. Prompt injection cannot surface them.           │
└─────────────────────────────────────────────────────────────────────┘
```

**The client never states its own role.** `/chat` has no `role` field at all, and
the role in `/collections/{role}` is checked against the token rather than
trusted. The authoritative role exists only inside a token the server signed.

### Session handling

| Property | Value |
|----------|-------|
| Idle timeout | 30 minutes, renewed on every authenticated request |
| Absolute cap | 8 hours from login, regardless of activity |
| Renewal mechanism | `X-Refreshed-Token` response header |
| Algorithm | HS256 |

Because the token is reissued on each request, an active user is never logged out
mid-conversation; 30 minutes of *silence* ends the session. `auth_time` is carried
forward unchanged through every renewal so the 8-hour ceiling stays anchored to
the original login.

### Worked example: `nurse.priya` logs in and asks a question

**Login — happens once**

```
BROWSER                          BACKEND
───────                          ───────
login/page.tsx handleLogin()
      │
      └─▶ api.ts login()
             POST /login {"username":"nurse.priya","password":"nurse"}
                  │
                  ▼
             main.py login()
               ├─ DEMO_USERS["nurse.priya"]  password ✓
               ├─ get_collections_for_role("nurse") → [general, nursing]
               └─ mint_token("nurse.priya", "nurse")
                     auth_time = 09:00   ← session start stamped
                     exp       = 09:30
                  │
                  ▼
             {token, role:"nurse", collections:[general, nursing]}
      │
      ▼
 localStorage:  token = eyJhbGc...
                user  = {username, role, collections}   ← display only
```

**Q1 at 09:05 — "What is the recommended IV cannula gauge for pediatric patients?"**

```
chat/page.tsx handleSubmit()
      │
      └─▶ api.ts chat(question) ─▶ authFetch("/chat")
             header: Authorization: Bearer eyJhbGc...
             body:   {"question": "..."}          ← NO role field
                         │
                         ▼
╔═══════════════════════════════════════════════════════════════╗
║  FastAPI resolves Depends(get_current_user) BEFORE chat()     ║
║                                                                ║
║   HTTPBearer security             → pulls token from header   ║
║   get_current_user()                                           ║
║     ├─ credentials present?          yes ✓                    ║
║     ├─ verify_token(token)                                     ║
║     │    jwt.decode(token, JWT_SECRET)                         ║
║     │      ├─ signature matches?     yes ✓                    ║
║     │      └─ exp (09:30) passed?    no  ✓                    ║
║     ├─ role "nurse" in VALID_ROLES?  yes ✓                    ║
║     └─ session_age 5min < 8h?        yes ✓                    ║
║          └─ mint_token() → X-Refreshed-Token   exp = 09:35    ║
╚═══════════════════════════════════════════════════════════════╝
                         │  returns payload
                         ▼
             main.py chat(request, user)
               question = request.question
               role     = user["role"] = "nurse"    ← FROM THE TOKEN
                         │
               is_analytical_question()  ──LLM──▶ DOCUMENT
                         │
                         ▼
               hybrid_rag_chain(question, "nurse")
                 ├─ get_reranking_retriever(vs, role="nurse", top_n=3, k=10)
                 │    └─ get_hybrid_retriever_with_rbac(vs, "nurse", k=10)
                 │         ┌────────────────────────────────────────┐
                 │         │ QDRANT QUERY                           │
                 │         │  dense (bge-m3) + sparse (BM25)        │
                 │         │  FILTER access_roles CONTAINS nurse    │◀─ RBAC
                 │         │  → 10 candidates, nursing + general    │
                 │         └────────────────────────────────────────┘
                 │    └─ CrossEncoderReranker → top 3
                 ├─ rag_chain.invoke()  ──LLM──▶ answer
                 └─ answer is grounded → attach the 3 chunks as sources
                         │
                         ▼
             {answer, sources:[icu_nursing_procedures.pdf …],
              retrieval_type:"hybrid_rag", role:"nurse"}
      │
      ▼
 authFetch stores X-Refreshed-Token, updates lastActivity
 UI renders: answer + source cards + green "Hybrid RAG" badge
```

**What runs when**

| Frequency | Functions |
|-----------|-----------|
| Once per session | `login` → `get_collections_for_role` → `mint_token` |
| Every request | `HTTPBearer` → `get_current_user` → `verify_token` → `mint_token` |
| Per question | `chat` → `is_analytical_question` → `hybrid_rag_chain` *or* `sql_rag_chain` |

Had the nurse instead asked *"What is the standard dose of paracetamol?"*, every
step above would be identical until the Qdrant query — where `drug_formulary.pdf`
(`access_roles = [doctor, admin]`) is filtered out before retrieval. The LLM never
receives it, so no amount of prompt injection can surface it, and the response
comes back with `sources: []`.

### Known limitations

Deliberate tradeoffs, documented rather than hidden:

- **Logout is client-side.** The token stays valid until it expires; a copied token
  would keep working. The production fix is a short access token paired with a
  revocable refresh token.
- **The token is stored in `localStorage`**, which is readable by XSS. An
  `httpOnly` cookie is the safer choice but requires CSRF handling, kept out of
  scope here.
- **Demo users are hardcoded** with plaintext passwords, per the assignment spec.
  Production would delegate authentication to the hospital's identity provider
  (Entra ID / Okta) over OIDC — the token *verification* path here is unchanged by
  that substitution, only the issuer changes.

---

## RBAC Testing (Adversarial Prompts)

Tests 1–3 verify RBAC at the retrieval layer. Test 4 verifies the auth layer
underneath it — the UI tests cannot cover that, because the attack bypasses the UI.

### Test 1: Nurse trying to access SQL RAG (mediassist.db)
**Login:** nurse.priya | **Role:** nurse  
**Prompt:** "How many claims are in cardiology department?"  
**Expected:** Blocked - SQL RAG only accessible to billing_executive and admin

![Nurse Adversarial Test](images/adversarial_prompts_screenshots/nurse_adversarial_prompt.jpg)

### Test 2: Technician trying to access clinical documents
**Login:** tech.anand | **Role:** technician  
**Prompt:** "What is the drug dosage for paracetamol for adults?"  
**Expected:** "I don't have that information in your accessible documents. This could be because: 1. The information doesn't exist in the internal documents, OR 2. Your role (technician) may not have access to the relevant collection. Your accessible collections are: general, equipment."

![Technician Adversarial Test](images/adversarial_prompts_screenshots/tech_adversarial_prompt.jpg)

### Test 3: Billing Executive trying to access equipment documents
**Login:** billing.ravi | **Role:** billing_executive  
**Prompt:** "How do I calibrate the infusion pump?"  
**Expected:** "I don't have that information in your accessible documents. This could be because: 1. The information doesn't exist in the internal documents, OR 2. Your role (billing_executive) may not have access to the relevant collection. Your accessible collections are: general, billing."

![Billing Adversarial Test](images/adversarial_prompts_screenshots/billing_adversarial_prompt.jpg)

**Why this works:** RBAC metadata filter is applied at the Qdrant query level, so restricted documents are never retrieved or passed to the LLM.

### Test 4: Forging a role directly against the API

Tests 1–3 go through the browser, where the frontend sends an honest role. This
test skips the UI entirely and attacks the API, which is where the security
boundary actually lives.

Reproduce it in the browser at **http://localhost:8000/docs** — no terminal, no code.

#### Step 1: The attack fails

Expand **POST `/chat`** → **Try it out** → replace the request body with:

```json
{"question": "Show every claim with amounts", "role": "admin"}
```

**Execute** →

```
401  {"detail": "Not authenticated. Log in to obtain a token."}
```

The `role` field is ignored entirely — `ChatRequest` has no such field — and the
request is rejected before the endpoint body ever runs.

#### Step 2: Get a token

Expand **POST `/login`** → **Try it out** → body:

```json
{"username": "nurse.priya", "password": "nurse"}
```

**Execute**, then copy the `token` value from the response.

#### Step 3: Authorize

Click **Authorize 🔒** at the top right, paste the token, then **Authorize** → **Close**.

#### Step 4: RBAC holds even with a valid token

Expand **GET `/collections/{role}`** → **Try it out**:

| `role` entered | Result |
|----------------|--------|
| `admin` | `403  {"detail": "Authenticated as 'nurse' - cannot view collections for 'admin'."}` |
| `nurse` | `200  {"role": "nurse", "collections": ["general", "nursing"]}` |

Holding a genuine token does not let a nurse widen their own access. The role is
whatever the server signed, not what the client asks for.

---

## Query Routing Examples

| Question | Route | Why |
|----------|-------|-----|
| "How many claims are pending?" | SQL RAG | Querying actual claim records |
| "What are claim rejection codes?" | Hybrid RAG | Asking about code definitions |
| "What is IV cannula size?" | Hybrid RAG | Medical procedure question |
| "Total claimed amount by department?" | SQL RAG | Analytical aggregation |
| "hi" / "thanks" / "bye" | Neither | Greeting — answered directly, no sources cited |

---

## Troubleshooting

| Issue | Solution |
|-------|----------|
| `RuntimeError: JWT_SECRET is not set` | Add `JWT_SECRET` to `.env` (see Step 4) |
| Logged out immediately after login | Backend restarted with a different `JWT_SECRET`, invalidating existing tokens — log in again |
| `npm: command not found` | Run `source ~/.bashrc` to load nvm |
| Groq rate limit error | Switch model in `.env` or wait |
| `Blocked cross-origin request` | Add your IP to `frontend/next.config.ts` |
| Backend not accessible from browser | Use `--host 0.0.0.0` when starting backend |
| Qdrant not found | Run `python backend/rag_pipeline.py` to create index |
| venv broken after rename | Delete `.venv` and recreate with `uv venv` |

---

## Tool Substitutions

| Component | Tool Used | Why |
|-----------|-----------|-----|
| **LLM API** | Groq (qwen/qwen3.8-27b or openai/gpt-oss-120b) | Free tier with generous limits, fast inference |
| **Embeddings** | BAAI/bge-m3 (1024-dim) | Free, 8192 token context (good for medical docs), multilingual support |
| **Sparse Embeddings** | Qdrant/bm25 via FastEmbed | Native BM25 support for hybrid search |
| **Vector Database** | Qdrant (local file-based) | No cloud dependency, simple setup, native hybrid search support |
| **Cross-Encoder** | ms-marco-MiniLM-L-6-v2 | Good balance of speed and accuracy for reranking |
| **Document Parser** | Docling | Structure-aware parsing (tables, headings, code blocks) |

---

## Author

**Himesh Sarkari**
