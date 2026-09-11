# MediBot Backend

FastAPI backend for MediBot RAG chatbot with Role-Based Access Control (RBAC).

---

## Architecture Overview

```
┌──────────────────────────────────────────────────────────────────────────────────┐
│                               MediBot Backend                                     │
├──────────────────────────────────────────────────────────────────────────────────┤
│                                                                                   │
│  ┌──────────────┐                                                                │
│  │   main.py    │  POST /chat                                                    │
│  │  (FastAPI)   │─────────────────────────────────────────┐                      │
│  └──────────────┘                                         │                      │
│                                                           ▼                      │
│                              ┌─────────────────────────────────────────────────┐ │
│                              │              rag_pipeline.py                     │ │
│                              │                                                  │ │
│                              │  ┌────────────────────────────────────────────┐ │ │
│                              │  │         is_analytical_question()           │ │ │
│                              │  │         (LLM-based Query Router)           │ │ │
│                              │  └────────────────────────────────────────────┘ │ │
│                              │                      │                          │ │
│                              │          ┌───────────┴───────────┐              │ │
│                              │          │ SQL?                  │ DOCUMENT?    │ │
│                              │          ▼                       ▼              │ │
│                              │  ┌──────────────┐        ┌──────────────┐       │ │
│                              │  │sql_rag_chain │        │hybrid_rag    │       │ │
│                              │  │     ()       │        │  _chain()    │       │ │
│                              │  └──────┬───────┘        └──────┬───────┘       │ │
│                              │         │                       │               │ │
│                              │         │               Cross-Encoder Reranking │ │
│                              │         │                 + RBAC Filter         │ │
│                              │         │                       │               │ │
│                              └─────────┼───────────────────────┼───────────────┘ │
│                                        │                       │                 │
│                                        ▼                       ▼                 │
│            ┌─────────────────────────────┐       ┌─────────────────────────────┐ │
│            │     SQLite Database         │       │    Qdrant Vector Store      │ │
│            │  (claims, maintenance_      │       │     (Hybrid Search)         │ │
│            │       tickets)              │       │   backend/qdrant_data       │ │
│            │  mediassist_data/db/        │       │                             │ │
│            └─────────────────────────────┘       └─────────────────────────────┘ │
└──────────────────────────────────────────────────────────────────────────────────┘
```

---

## Directory Structure

```
backend/
├── __init__.py           # Package marker
├── main.py               # FastAPI application (REST API endpoints)
├── rag_pipeline.py       # Core RAG pipeline (ingestion, retrieval, chains)
├── qdrant_data/          # Qdrant vector database storage
└── README.md             # This file
```

---

## Running the Backend

### Prerequisites

#### 1. Navigate to the Repository
```bash
cd /home/himesh/codebasics_cohort/AI_Projects/Medibot_Hybrid_And_Sql_RAG
```

#### 2. Install uv (Python Package Manager)
```bash
# Check if uv is installed
which uv && uv --version

# If not installed, install it
curl -LsSf https://astral.sh/uv/install.sh | sh
source ~/.bashrc
```

#### 3. Create .env File
Create a `.env` file in the project root with your Groq API key:
```bash
# .env
GROQ_API_KEY=gsk_your_api_key_here
GROQ_MODEL=qwen/qwen3.8-27b
```
Get your free API key from: https://console.groq.com/keys

#### 4. Create Virtual Environment
```bash
uv venv
```

#### 5. Activate Virtual Environment
```bash
source .venv/bin/activate
```

#### 6. Install Dependencies
```bash
uv pip install -r requirements.txt
```

### Running the Application

#### Step 1: Run Ingestion (First Time Only)
```bash
python backend/rag_pipeline.py
```
This will:
- Parse all documents from `mediassist_data/`
- Create chunks with RBAC metadata
- Store in Qdrant (`backend/qdrant_data/`)
- Run test queries for both Hybrid and SQL RAG

#### Step 2: Start the API Server

**Option A: Local Only (localhost)**
```bash
uvicorn backend.main:app --reload
```
- Binds to `127.0.0.1:8000` (localhost only)
- Use when: Backend and frontend are on the **same machine**
- Access: http://127.0.0.1:8000

**Option B: Network Accessible (with --host)**
```bash
uvicorn backend.main:app --reload --host 0.0.0.0
```
- Binds to `0.0.0.0:8000` (all network interfaces)
- Use when: Frontend is on a **different machine** (e.g., WSL backend + Windows browser, or remote server)
- Access: http://<your-ip>:8000

**Alternative: FastAPI CLI**
```bash
# Local only
fastapi dev backend/main.py

# Network accessible
fastapi dev backend/main.py --host 0.0.0.0
```

#### Step 3: Access API Documentation
- Swagger UI: http://127.0.0.1:8000/docs
- ReDoc: http://127.0.0.1:8000/redoc

---

## Key Concepts with Code Walkthrough

### 1. Hybrid RAG (Retrieval-Augmented Generation)

Combines two retrieval methods for better search results:

| Method | How it Works | Good For |
|--------|--------------|----------|
| **Dense (Semantic)** | Embedding similarity (BAAI/bge-m3, 1024-dim) | Conceptual matches, paraphrases |
| **Sparse (BM25)** | Keyword frequency matching | Exact terms, acronyms, codes |

```
User Query: "IV cannula size for pediatric"
                    │
    ┌───────────────┴───────────────┐
    ▼                               ▼
Dense Search                    Sparse Search
"IV cannula" ≈ "intravenous"    Exact match: "IV", "cannula", "pediatric"
    │                               │
    └───────────────┬───────────────┘
                    ▼
            Reciprocal Rank Fusion (RRF)
                    │
                    ▼
            Top-K Combined Results
```

**Code: Storing with Hybrid Search** (`rag_pipeline.py:store_in_qdrant`)
```python
def store_in_qdrant(chunks: list[Document]):
    # Dense embeddings (semantic search)
    dense_embeddings = HuggingFaceEmbeddings(
        model_name="BAAI/bge-m3",
        model_kwargs={"device": "cpu"},
        encode_kwargs={"normalize_embeddings": True}
    )
    
    # Sparse embeddings (BM25 keyword search)
    sparse_embeddings = FastEmbedSparse(model_name="Qdrant/bm25")
    
    # RetrievalMode.HYBRID stores BOTH dense and sparse vectors
    vectorstore = QdrantVectorStore.from_documents(
        documents=chunks,
        embedding=dense_embeddings,
        sparse_embedding=sparse_embeddings,
        path=str(QDRANT_PATH),
        collection_name="medibot_docs_vectorstore",
        retrieval_mode=RetrievalMode.HYBRID,
        force_recreate=True,
    )
    return vectorstore
```

---

### 2. Role-Based Access Control (RBAC)

Users can only access documents from their authorized collections:

| Role | Accessible Collections |
|------|------------------------|
| doctor | general, clinical, nursing |
| nurse | general, nursing |
| billing_executive | general, billing |
| technician | general, equipment |
| admin | all collections |

**Code: RBAC Configuration** (`rag_pipeline.py`)
```python
COLLECTION_ACCESS_ROLES = {
    "general": ["doctor", "nurse", "billing_executive", "technician", "admin"],
    "clinical": ["doctor", "admin"],
    "nursing": ["nurse", "doctor", "admin"],
    "billing": ["billing_executive", "admin"],
    "equipment": ["technician", "admin"],
}
```

**Code: RBAC Filter at Query Time** (`rag_pipeline.py:get_hybrid_retriever_with_rbac`)
```python
def get_hybrid_retriever_with_rbac(vectorstore, role: str, k: int = 5):
    # Build RBAC filter - only retrieve docs where access_roles contains user's role
    rbac_filter = Filter(
        must=[
            FieldCondition(
                key="metadata.access_roles",
                match=MatchAny(any=[role])
            )
        ]
    )
    
    # Create retriever with RBAC filter
    hybrid_retriever = vectorstore.as_retriever(
        search_kwargs={"k": k, "filter": rbac_filter}
    )
    return hybrid_retriever
```

**Code: RBAC Metadata on Chunks** (`rag_pipeline.py:chunk_document`)
```python
chunk_doc = Document(
    page_content=chunk_text,
    metadata={
        "source_document": file_path.name,
        "collection": collection_name,
        "access_roles": COLLECTION_ACCESS_ROLES[collection_name],  # e.g., ["nurse", "doctor", "admin"]
        "section_title": full_section_title,
        "chunk_type": chunk_type,
    }
)
```

---

### 3. Cross-Encoder Reranking

Two-stage retrieval for better relevance:

```
Stage 1: Hybrid Search → Fetch 10 candidates (fast, approximate)
Stage 2: Cross-Encoder → Score each (query, doc) pair → Return top 3 (slow, precise)
```

**Code: Reranking Retriever** (`rag_pipeline.py:get_reranking_retriever`)
```python
def get_reranking_retriever(vectorstore, role: str, top_n: int = 3, k: int = 10):
    # Cross-encoder scores (query, document) pairs for relevance
    cross_encoder = HuggingFaceCrossEncoder(
        model_name="cross-encoder/ms-marco-MiniLM-L-6-v2"
    )
    
    crossEncoderReranker = CrossEncoderReranker(
        model=cross_encoder,
        top_n=top_n  # Return top 3 after reranking
    )
    
    # Broad retriever fetches k=10 candidates with RBAC filter
    broad_retriever = vectorstore.as_retriever(
        search_kwargs={"k": k, "filter": rbac_filter}
    )
    
    # ContextualCompressionRetriever applies reranking
    reranking_retriever = ContextualCompressionRetriever(
        base_compressor=crossEncoderReranker,
        base_retriever=broad_retriever
    )
    return reranking_retriever
```

---

### 4. Query Routing (SQL vs Hybrid RAG)

LLM-based classifier routes questions to the appropriate RAG:

| Route | When | Example |
|-------|------|---------|
| **SQL RAG** | Analytical questions about data | "How many claims are pending?" |
| **Hybrid RAG** | Document-based questions | "What is IV cannula size?" |

Key distinction:
- "What are claim rejection codes?" → Hybrid RAG (asking about definitions in documents)
- "How many claims were rejected?" → SQL RAG (querying actual claim records)

**Code: Query Router** (`rag_pipeline.py:is_analytical_question`)
```python
def is_analytical_question(question: str) -> bool:
    llm = get_llm()
    
    classification_prompt = ChatPromptTemplate.from_messages([
        ("system", """You are a query router for a hospital information system.
Classify questions into SQL or DOCUMENT:

SQL = Query actual DATA/RECORDS (counts, totals, averages of claims or tickets)
DOCUMENT = Look up POLICIES, PROCEDURES, DEFINITIONS, HOW-TO information

{schema}

Respond with ONLY one word: SQL or DOCUMENT"""),
        ("human", "Question: {question}")
    ])
    
    chain = classification_prompt | llm | StrOutputParser()
    result = chain.invoke({"schema": DATABASE_SCHEMA_CONTEXT, "question": question})
    
    return result.strip().upper() == "SQL"
```

**Code: Chat Endpoint with Routing** (`main.py`)
```python
@app.post("/chat", response_model=ChatResponse)
def chat(request: ChatRequest):
    question = request.question
    role = request.role
    
    # Query routing: SQL RAG or Hybrid RAG?
    if is_analytical_question(question):
        result = sql_rag_chain(question, role)
    else:
        result = hybrid_rag_chain(question, role)
    
    return ChatResponse(
        answer=result["answer"],
        sources=result.get("sources", []),
        retrieval_type=result["retrieval_type"],
        role=result["role"]
    )
```

---

### 5. Hierarchical Chunking with Docling

Docling preserves document structure (headings, tables, code blocks) during chunking.

**Problem**: Child chunks lose parent heading context
```
Original PDF:
# A. Patient Monitoring - BM-500
  ## Setup Procedure
    Step 1: Connect power...

Without fix: Chunk only contains "Setup Procedure" + content
→ Search for "BM-500 setup" fails to match!
```

**Solution**: Track parent sections and prepend to chunks

**Code: Parent Section Tracking** (`rag_pipeline.py:chunk_document`)
```python
def chunk_document(doc, collection_name: str, file_path: Path) -> list[Document]:
    chunker = HybridChunker(tokenizer=EMBEDDING_MODEL, max_tokens=MAX_TOKENS)
    
    # Track parent section for hierarchy
    current_parent_section = ""
    
    for chunk in chunker.chunk(doc):
        chunk_text = chunker.contextualize(chunk)
        
        # Extract section title from metadata
        section_title = " > ".join(getattr(chunk.meta, 'headings', []))
        
        # Update parent tracker when we see a major section (A., B., 1., 2.)
        if section_title:
            first_heading = section_title.split(' > ')[0]
            if re.match(r'^[A-Z]\.|^\d+\.', first_heading):
                current_parent_section = first_heading
        
        # Build full path: prepend parent if not already included
        full_section_title = section_title
        if current_parent_section and current_parent_section not in section_title:
            full_section_title = f"{current_parent_section} > {section_title}"
        
        # Prepend full path to chunk content (makes parent terms searchable)
        if full_section_title and full_section_title not in chunk_text[:200]:
            chunk_text = f"{full_section_title}\n\n{chunk_text}"
```

**Result**:
```
Chunk content now includes:
"A. Patient Monitoring - BM-500 > Setup Procedure

Step 1: Connect power..."

→ Search for "BM-500 setup" now matches!
```

---

### 6. SQL RAG for Analytics

Three-step process for analytical queries:

```
Step 1: LLM generates SQL from question
Step 2: Execute SQL against SQLite database
Step 3: LLM generates natural language answer from result
```

**Code: SQL RAG Chain** (`rag_pipeline.py:sql_rag_chain`)
```python
def sql_rag_chain(question: str, role: str) -> dict:
    # Role check - only billing_executive and admin can use SQL RAG
    if role not in ["billing_executive", "admin"]:
        return {"answer": f"As a {role}, you do not have access to analytics data..."}
    
    db = SQLDatabase.from_uri(f"sqlite:///{SQL_DB_PATH}")
    llm = get_llm()
    
    # Step 1: LLM generates SQL
    sql_query_chain = create_sql_query_chain(llm, db)
    raw_sql = sql_query_chain.invoke({"question": question})
    sql_query = clean_sql(raw_sql)
    
    # Step 2: Execute SQL
    sql_result = db.run(sql_query)
    
    # Step 3: LLM generates answer from result
    answer_prompt = ChatPromptTemplate.from_messages([
        ("system", "Given a SQL result, provide a clear natural language answer."),
        ("human", "Question: {question}\nSQL Result: {result}\n\nAnswer:"),
    ])
    response = answer_prompt | llm
    answer = response.invoke({"question": question, "result": sql_result}).content
    
    return {"answer": answer, "sql_query": sql_query, "retrieval_type": "sql_rag", "role": role}
```

---

## Configuration

### Environment Variables (.env)

```bash
GROQ_API_KEY=gsk_...         # Groq API key
GROQ_MODEL=qwen/qwen3.8-27b  # LLM model (free tier friendly)
```

### Constants (rag_pipeline.py)

```python
MAX_TOKENS = 2000                # Max tokens per chunk
EMBEDDING_MODEL = "BAAI/bge-m3"  # 1024-dim, 8192 token context

# Paths
QDRANT_PATH = "backend/qdrant_data"
SQL_DB_PATH = "mediassist_data/db/mediassist.db"
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
// Request (Hybrid RAG)
{"question": "What is IV cannula size for pediatric?", "role": "nurse"}

// Response
{
  "answer": "For pediatric patients under 5kg, use 24G IV cannula...",
  "sources": [
    {"source_document": "icu_nursing.pdf", "section_title": "IV Cannula > Pediatric", "collection": "nursing"}
  ],
  "retrieval_type": "hybrid_rag",
  "role": "nurse"
}
```

```json
// Request (SQL RAG)
{"question": "How many claims are pending?", "role": "admin"}

// Response
{
  "answer": "There are 17 pending claims in the system.",
  "sources": [],
  "retrieval_type": "sql_rag",
  "role": "admin"
}
```

---

## Key Functions Reference

| Function | File | Purpose |
|----------|------|---------|
| `get_llm()` | rag_pipeline.py | Initialize ChatGroq LLM |
| `load_document()` | rag_pipeline.py | Parse PDF/MD with Docling |
| `chunk_document()` | rag_pipeline.py | Create chunks with RBAC metadata |
| `store_in_qdrant()` | rag_pipeline.py | Index chunks (dense + sparse vectors) |
| `get_vectorstore()` | rag_pipeline.py | Load existing Qdrant collection |
| `get_hybrid_retriever_with_rbac()` | rag_pipeline.py | Retriever with role filter |
| `get_reranking_retriever()` | rag_pipeline.py | Retriever with reranking |
| `hybrid_rag_chain()` | rag_pipeline.py | Full Hybrid RAG pipeline |
| `is_analytical_question()` | rag_pipeline.py | LLM-based query router |
| `sql_rag_chain()` | rag_pipeline.py | SQL RAG for analytics queries |
| `login()` | main.py | Authenticate user |
| `chat()` | main.py | Main RAG endpoint |

---

## Dependencies

Key packages used:
- **FastAPI** - REST API framework
- **LangChain** - RAG chain orchestration
- **Docling** - PDF/MD parsing with structure awareness
- **Qdrant** - Vector database with hybrid search
- **HuggingFace** - Embeddings (bge-m3) and cross-encoder
- **Groq** - LLM API (qwen3.8-27b)

---

## Troubleshooting

| Issue | Solution |
|-------|----------|
| Groq rate limit error | Switch to a different model in `.env` or wait |
| Import errors | Ensure venv is activated and dependencies installed |
| Qdrant not found | Run `python backend/rag_pipeline.py` to create index |
| CORS errors | Backend is configured to allow all origins for dev |
| Frontend can't connect | Use `--host 0.0.0.0` if frontend is on different machine |
| venv broken after repo rename | Delete `.venv` and recreate with `uv venv` |

---

## Related Files

| File | Purpose |
|------|---------|
| `mediassist_data/` | Source documents (PDF, MD) by collection |
| `mediassist_data/db/mediassist.db` | SQLite database for SQL RAG |
| `frontend/` | Next.js frontend application |
| `learning/` | Learning scripts (database explorer, sample FastAPI) |
