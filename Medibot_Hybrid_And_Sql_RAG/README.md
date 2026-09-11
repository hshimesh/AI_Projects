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
- **Query Routing:** LLM-based classifier routes questions to Hybrid RAG or SQL RAG
- **Hierarchical Chunking:** Docling preserves document structure (headings, tables, code blocks)
- **Source Citations:** Every response includes document name, section title, and collection
- **Session Timeout:** 30-minute session timeout for security
- **5 Demo Accounts:** Color-coded login for different hospital roles

---

## Architecture

```
┌──────────────────────────────────────────────────────────────────────────────────┐
│                               MediBot System                                      │
├──────────────────────────────────────────────────────────────────────────────────┤
│                                                                                   │
│  ┌─────────────────┐         ┌──────────────────────────────────────────────────┐│
│  │   Next.js       │  HTTP   │                  FastAPI Backend                  ││
│  │   Frontend      │────────▶│                                                   ││
│  │   (Port 3000)   │         │  ┌────────────────────────────────────────────┐  ││
│  └─────────────────┘         │  │         is_analytical_question()           │  ││
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

Create a `.env` file in the project root:

```bash
GROQ_API_KEY=gsk_your_api_key_here
GROQ_MODEL=openai/gpt-oss-120b
# OR
#GROQ_MODEL=qwen/qwen3.8-27b
```

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

### POST /login
```json
// Request
{"username": "dr.mehta", "password": "doctor"}

// Response
{"role": "doctor", "collections": ["general", "clinical", "nursing"]}
```

### POST /chat
```json
// Request
{"question": "What is IV cannula size for pediatric?", "role": "nurse"}

// Response
{
  "answer": "For pediatric patients under 5kg, use 24G IV cannula...",
  "sources": [{"source_document": "icu_nursing.pdf", "section_title": "IV Cannula > Pediatric", "collection": "nursing"}],
  "retrieval_type": "hybrid_rag",
  "role": "nurse"
}
```

---

## RBAC Testing (Adversarial Prompts)

The following tests verify RBAC is enforced at the retrieval layer:

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

---

## Query Routing Examples

| Question | Route | Why |
|----------|-------|-----|
| "How many claims are pending?" | SQL RAG | Querying actual claim records |
| "What are claim rejection codes?" | Hybrid RAG | Asking about code definitions |
| "What is IV cannula size?" | Hybrid RAG | Medical procedure question |
| "Total claimed amount by department?" | SQL RAG | Analytical aggregation |

---

## Troubleshooting

| Issue | Solution |
|-------|----------|
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
