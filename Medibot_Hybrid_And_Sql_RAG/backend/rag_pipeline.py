"""
MediBot Document Ingestion & RAG Pipeline

Pipeline Steps:
    - Step 1: Document Loading using Docling (PDF/MD parsing with structure awareness)
    - Step 2: Hierarchical Chunking (preserves sections, tables, headings)
    - Step 3: Store in Qdrant with Hybrid Search (dense + sparse/BM25 vectors)
    - Step 4: Hybrid Retrieval with RBAC Filter (role-based access control)
    - Step 5: Reranking with Cross-Encoder (fetch k → rerank → top_n)

Key Components:
    - Docling: Parses PDFs/MD with structural awareness (tables, headings, code blocks)
    - HybridChunker: Token-aware chunking that preserves document hierarchy
    - Qdrant: Vector store with hybrid search (semantic + keyword matching)
    - RBAC: Metadata filter ensures users only see authorized documents
    - Cross-Encoder: Reranks initial candidates for better relevance
"""

from pathlib import Path
from docling.document_converter import DocumentConverter
from docling.chunking import HybridChunker
from langchain_core.documents import Document
from langchain_huggingface import HuggingFaceEmbeddings
from langchain_qdrant import FastEmbedSparse
from langchain_qdrant import QdrantVectorStore, RetrievalMode
from qdrant_client.models import Filter, FieldCondition, MatchAny
from langchain_community.cross_encoders import HuggingFaceCrossEncoder
from langchain_groq import ChatGroq
from langchain_core.prompts import ChatPromptTemplate
from langchain_core.output_parsers import StrOutputParser
from langchain_classic.chains.retrieval import create_retrieval_chain
from langchain_classic.chains.combine_documents import create_stuff_documents_chain
from langchain_classic.retrievers import ContextualCompressionRetriever
from langchain_classic.retrievers.document_compressors import CrossEncoderReranker
from langchain_community.utilities import SQLDatabase
from langchain_classic.chains import create_sql_query_chain
import os
import re
from dotenv import load_dotenv


load_dotenv()  # Load environment variables from .env

# ============================================
# CONFIGURATION
# ============================================

# Chunking settings
MAX_TOKENS = 2000                                       # Max tokens per chunk (bge-m3 supports 8192)
EMBEDDING_MODEL = "BAAI/bge-m3"                         # 1024-dim dense vectors, 8192 token limit
#MAX_TOKENS = 500
#EMBEDDING_MODEL = "sentence-transformers/all-MiniLM-L6-v2"

# Paths
BASE_DIR = Path(__file__).parent.parent
DATA_DIR = BASE_DIR / "mediassist_data"
QDRANT_PATH = BASE_DIR / "backend" / "qdrant_data"   # Store vectors in backend/qdrant_data/
SQL_DB_PATH = DATA_DIR / "db" / "mediassist.db"      # SQLite database for SQL RAG
# Collection → Folder paths
COLLECTION_PATHS = {
    "general": DATA_DIR / "general",
    "clinical": DATA_DIR / "clinical",
    "nursing": DATA_DIR / "nursing",
    "billing": DATA_DIR / "billing",
    "equipment": DATA_DIR / "equipment",
}

# RBAC: Collection → Roles that can access (from assignment spec)
COLLECTION_ACCESS_ROLES = {
    "general": ["doctor", "nurse", "billing_executive", "technician", "admin"],
    "clinical": ["doctor", "admin"],
    "nursing": ["nurse", "doctor", "admin"],
    "billing": ["billing_executive", "admin"],
    "equipment": ["technician", "admin"],
}


# ============================================
# LLM INITIALIZATION
# ============================================

def get_llm():
    """
    Initialize ChatGroq LLM instance.
    Single source of truth - avoids duplicate initialization.

    Returns:
        ChatGroq instance configured with environment variables

    Example:
        llm = get_llm()
        response = llm.invoke("Hello!")
    """
    return ChatGroq(
        api_key=os.environ.get("GROQ_API_KEY"),
        model=os.environ.get("GROQ_MODEL"),
        reasoning_format="parsed",
        max_tokens=None,
        temperature=0,
        timeout=None,
        max_retries=2,
    )


# ============================================
# STEP 1: DOCUMENT LOADING
# ============================================

def get_all_document_paths():
    """
    Find all PDF/MD documents from each collection folder.
    Returns list of (collection_name, file_path) tuples.

    Example return:
    [
        ("general", Path("mediassist_data/general/hr_handbook.pdf")),
        ("general", Path("mediassist_data/general/staff_leave_policy.pdf")),
        ("clinical", Path("mediassist_data/clinical/drug_formulary.pdf")),
        ("billing", Path("mediassist_data/billing/claim_submission_guide.md")),
        ...
    ]
    """
    documents = []
    #print(COLLECTION_PATHS)
    for folder_name, folder_path in COLLECTION_PATHS.items():
        if not folder_path.exists():
            print(f"Warning: {folder_path} does not exist")
            continue

        for file_path in folder_path.iterdir():
            if file_path.suffix.lower() in [".pdf", ".md"]:
                documents.append((folder_name, file_path))
    return documents


def load_document(file_path: Path):
    """
    Load and parse a single document using Docling.
    Docling extracts structure: headings, tables, code blocks, lists.

    Args:
        file_path: Path to PDF or MD file

    Returns:
        DoclingDocument object with parsed structure

    Example return:
        DoclingDocument(
            name="drug_formulary.pdf",
            tables=[...],      # Parsed tables
            texts=[...],       # Text blocks
            pictures=[...],    # Images
            ...
        )

    Usage:
        doc = load_document(Path("clinical/drug_formulary.pdf"))
        markdown = doc.export_to_markdown()
    """
    converter = DocumentConverter()
    result = converter.convert(file_path)
    return result.document


# ============================================
# STEP 2: HIERARCHICAL CHUNKING
# ============================================

def chunk_document(doc, collection_name: str, file_path: Path) -> list[Document]:
    """
    Chunk document using Docling's HybridChunker.
    Preserves document structure (sections, tables, headings).
    Attaches RBAC metadata to each chunk.

    Args:
        doc: DoclingDocument from load_document()
        collection_name: Folder name (general, clinical, nursing, billing, equipment)
        file_path: Original file path (for metadata)

    Returns:
        List of LangChain Document objects with RBAC metadata

    Example return:
    [
        Document(
            page_content="## Drug Dosages > Paracetamol\n\n25mg twice daily for adults...",
            metadata={
                "source_document": "drug_formulary.pdf",
                "collection": "clinical",
                "access_roles": ["doctor", "admin"],
                "section_title": "Drug Dosages > Paracetamol",
                "chunk_type": "text"
            }
        ),
        Document(
            page_content="## Drug Dosages > Ibuprofen\n\n| Age | Dose |\n|-----|------|...",
            metadata={
                "source_document": "drug_formulary.pdf",
                "collection": "clinical",
                "access_roles": ["doctor", "admin"],
                "section_title": "Drug Dosages > Ibuprofen",
                "chunk_type": "table"
            }
        ),
        ...
    ]
    """
    chunker = HybridChunker(
        tokenizer=EMBEDDING_MODEL,
        max_tokens=MAX_TOKENS,
        merge_peers=True,
    )

    chunks = []
    chunk_iter = chunker.chunk(doc)

    # Track parent section to fix Docling's limitation of not preserving full heading hierarchy
    # e.g., when we see "A. BM-500", remember it so child chunks like "Setup procedure" get full path
    current_parent_section = ""

    for chunk in chunk_iter:
        # contextualize() adds some heading context, but not full parent hierarchy
        chunk_text = chunker.contextualize(chunk)

        # Detect chunk type from Docling's doc_items (table, heading, code, or default text)
        chunk_type = "text"
        if hasattr(chunk, 'meta') and chunk.meta:
            if hasattr(chunk.meta, 'doc_items') and chunk.meta.doc_items:
                first_item = chunk.meta.doc_items[0]
                item_label = str(type(first_item).__name__).lower()
                if "table" in item_label:
                    chunk_type = "table"
                elif "heading" in item_label or "section" in item_label:
                    chunk_type = "heading"
                elif "code" in item_label:
                    chunk_type = "code"

        # Extract section title from Docling metadata (often only immediate heading, not full path)
        section_title = ""
        if hasattr(chunk, 'meta') and chunk.meta:
            headings = getattr(chunk.meta, 'headings', [])
            if headings:
                section_title = " > ".join(headings)

        # Fallback: extract heading from markdown syntax (# or **) in first 3 lines
        if not section_title:
            lines = chunk_text.split('\n')
            for line in lines[:3]:
                if line.startswith('#') or line.startswith('**'):
                    section_title = line.strip('#* ').strip()
                    break

        # Update parent tracker when we see a major section (A., B., 1., 2., etc.)
        # This handles 1-level nesting: major section → child subsections
        if section_title:
            first_heading = section_title.split(' > ')[0] if ' > ' in section_title else section_title
            if re.match(r'^[A-Z]\.|^\d+\.', first_heading):
                current_parent_section = first_heading

        # Build full path: prepend parent if current section doesn't already include it
        # e.g., "Setup procedure" → "A. Patient Monitoring - BM-500 > Setup procedure"
        full_section_title = section_title
        if current_parent_section and section_title and current_parent_section not in section_title:
            full_section_title = f"{current_parent_section} > {section_title}"

        # Prepend full path to chunk content so parent terms become searchable
        # Query "BM-500 setup" now matches chunks with "A. BM-500 > Setup procedure" in content
        if full_section_title and full_section_title not in chunk_text[:200]:
            chunk_text = f"{full_section_title}\n\n{chunk_text}"

        # Create LangChain Document with RBAC metadata for role-based filtering
        chunk_doc = Document(
            page_content=chunk_text,
            metadata={
                "source_document": file_path.name,
                "collection": collection_name,
                "access_roles": COLLECTION_ACCESS_ROLES[collection_name],
                "section_title": full_section_title or "General",
                "chunk_type": chunk_type,
            }
        )
        chunks.append(chunk_doc)

    return chunks

# ============================================
# STEP 3: STORE IN QDRANT (HYBRID SEARCH)
# ============================================

def store_in_qdrant(chunks: list[Document]):
    """
    Store chunks in Qdrant with hybrid search (dense + sparse vectors).
    LangChain handles embedding generation automatically.

    Args:
        chunks: List of LangChain Document objects with page_content and metadata

    Returns:
        QdrantVectorStore object that can be used for retrieval

    Example return:
        QdrantVectorStore(
            collection_name="medibot_documents",
            embeddings=HuggingFaceEmbeddings(...),
            sparse_embeddings=FastEmbedSparse(...),
            retrieval_mode=RetrievalMode.HYBRID,
            # Stored vectors:
            #   - dense: 384-dim vectors (semantic similarity)
            #   - sparse: BM25 vectors (keyword matching)
        )

    Usage for retrieval:
        vectorstore = store_in_qdrant(chunks)
        results = vectorstore.similarity_search("IV cannula size", k=5)
    """
    # Dense embeddings (semantic search)
    dense_embeddings = HuggingFaceEmbeddings(
        model_name=EMBEDDING_MODEL,
        model_kwargs={"device": "cpu"},
        encode_kwargs={"normalize_embeddings": True}
    )

    # Sparse embeddings (BM25 keyword search)
    sparse_embeddings = FastEmbedSparse(model_name="Qdrant/bm25")

    print(f"Dense embedding model: {EMBEDDING_MODEL}")
    print("Sparse embedding model: Qdrant/bm25")

    # RetrievalMode.HYBRID stores BOTH dense and sparse vectors
    # force_recreate=True deletes existing collection and creates fresh
    vectorstore = QdrantVectorStore.from_documents(
        documents=chunks,
        embedding=dense_embeddings,
        sparse_embedding=sparse_embeddings,
        path=str(QDRANT_PATH),                    # Local file storage (backend/qdrant_data/)
        collection_name="medibot_docs_vectorstore",
        retrieval_mode=RetrievalMode.HYBRID,
        force_recreate=True,                      # Overwrite on re-run
    )

    print(f"✅ Indexed {len(chunks)} chunks into Qdrant collection 'medibot_documents'")
    return vectorstore


# ==============================================================
# STEP 4: HYBRID RETRIEVAL WITH RBAC FILTER WITHOUT RERANKING
# ==============================================================

def get_vectorstore():
    """
    Load existing Qdrant vector store (without re-ingesting).
    Use this when you just want to query, not ingest.

    Returns:
        QdrantVectorStore connected to existing collection

    Example return:
        QdrantVectorStore(
            collection_name="medibot_docs_vectorstore",
            embedding=HuggingFaceEmbeddings(...),
            sparse_embedding=FastEmbedSparse("Qdrant/bm25"),
            retrieval_mode=RetrievalMode.HYBRID,
            path="backend/qdrant_data"
        )

    Usage:
        vectorstore = get_vectorstore()
        retriever = get_hybrid_retriever_with_rbac(vectorstore, "nurse", k=5)
        docs = retriever.invoke("IV cannula size")
    """
    dense_embeddings = HuggingFaceEmbeddings(
        model_name=EMBEDDING_MODEL,
        model_kwargs={"device": "cpu"},
        encode_kwargs={"normalize_embeddings": True}
    )
    sparse_embeddings = FastEmbedSparse(model_name="Qdrant/bm25")

    vectorstore = QdrantVectorStore.from_existing_collection(
        embedding=dense_embeddings,
        sparse_embedding=sparse_embeddings,
        collection_name="medibot_docs_vectorstore",
        path=str(QDRANT_PATH),
        retrieval_mode=RetrievalMode.HYBRID,
    )
    return vectorstore


def get_hybrid_retriever_with_rbac(vectorstore, role: str, k: int = 5):
    """
    Create a retriever with RBAC filter applied.
    Only retrieves documents where access_roles contains the user's role.

    Args:
        vectorstore: QdrantVectorStore instance
        role: User's role (doctor, nurse, billing_executive, technician, admin)
        k: Number of results to return per query

    Returns:
        VectorStoreRetriever with RBAC filter configured

    Example:
        retriever = get_hybrid_retriever_with_rbac(vectorstore, "nurse", k=3)
        docs = retriever.invoke("IV cannula size")
        # Returns only docs from nursing and general collections

    Example return:
        VectorStoreRetriever(
            vectorstore=QdrantVectorStore(...),
            search_kwargs={
                "k": 3,
                "filter": Filter(must=[FieldCondition(key="metadata.access_roles", ...)])
            }
        )

    Usage with RAG chain:
        retriever = get_hybrid_retriever_with_rbac(vectorstore, "nurse", k=3)
        question_answer_chain = create_stuff_documents_chain(llm, prompt)
        rag_chain = create_retrieval_chain(retriever, question_answer_chain)
        result = rag_chain.invoke({"input": "IV cannula size"})
    """
    # Build RBAC filter - only retrieve docs where access_roles contains user's role
    rbac_filter = Filter(
        must=[
            FieldCondition(
                key="metadata.access_roles",   # LangChain nests metadata
                match=MatchAny(any=[role])     # Match if role is in the list
            )
        ]
    )
    # Create retriever with RBAC filter
    hybrid_retriever = vectorstore.as_retriever(
        search_kwargs={
            "k": k,
            "filter": rbac_filter
        }
    )
    # Invoke retriever to get results
    #results = hybrid_retriever.invoke(query)
    #return results
    return hybrid_retriever


# ============================================
# STEP 5: RERANKING WITH CROSS-ENCODER
# ============================================

def get_reranking_retriever(vectorstore, role: str, top_n: int = 3, k: int = 10):
    """
    Create a retriever with RBAC filter + cross-encoder reranking.
    Fetches k candidates, then reranks to top_n using cross-encoder.

    Args:
        vectorstore: QdrantVectorStore instance
        role: User's role (doctor, nurse, billing_executive, technician, admin)
        top_n: Number of documents to return after reranking
        k: Number of initial candidates to fetch before reranking

    Returns:
        ContextualCompressionRetriever with reranking pipeline

    Pipeline:
        1. Hybrid search (dense + BM25) → fetch k candidates with RBAC filter
        2. Cross-encoder reranker → score each (query, doc) pair
        3. Return top_n highest-scoring documents

    Example:
        retriever = get_reranking_retriever(vectorstore, "nurse", top_n=3, k=10)
        docs = retriever.invoke("IV cannula size")
        # Returns 3 best docs from initial 10 candidates

    Example return:
        ContextualCompressionRetriever(
            base_compressor=CrossEncoderReranker(model="ms-marco-MiniLM-L-6-v2", top_n=3),
            base_retriever=VectorStoreRetriever(search_kwargs={"k": 10, "filter": rbac_filter})
        )

    Usage with RAG chain:
        retriever = get_reranking_retriever(vectorstore, "nurse", top_n=3, k=10)
        question_answer_chain = create_stuff_documents_chain(llm, prompt)
        rag_chain = create_retrieval_chain(retriever, question_answer_chain)
        result = rag_chain.invoke({"input": "IV cannula size"})
    """
    cross_encoder = HuggingFaceCrossEncoder(
        model_name="cross-encoder/ms-marco-MiniLM-L-6-v2"
    )

    crossEncoderReranker = CrossEncoderReranker(
        model=cross_encoder,
        top_n=top_n
    )
    print("✅ Cross-encoder reranker ready")
    print("Model: cross-encoder/ms-marco-MiniLM-L-6-v2")

    # Build RBAC filter - only retrieve docs where access_roles contains user's role
    rbac_filter = Filter(
        must=[
            FieldCondition(
                key="metadata.access_roles",   # LangChain nests metadata
                match=MatchAny(any=[role])     # Match if role is in the list
            )
        ]
    )

    broad_retriever = vectorstore.as_retriever( # fetch 10, rerank down to 3
        search_kwargs={
            "k": k,
            "filter": rbac_filter#,
            #"score_threshold": 0.5  # Only return docs with similarity > 0.7
        }
    ) 
    
    reranking_retriever = ContextualCompressionRetriever(
        base_compressor=crossEncoderReranker,
        base_retriever=broad_retriever
    )
    print("Retrieval pipeline:")
    print("  1. Hybrid search → Top-10 candidates")
    print("  2. Cross-encoder reranker → Top-3 best documents")
    return reranking_retriever


def hybrid_rag_chain(question: str, role: str, top_n: int = 3, k: int = 10) -> dict:
    """
    Hybrid RAG with RBAC and reranking - returns structured response for FastAPI.

    Pipeline:
        1. Load vectorstore
        2. Create reranking retriever with RBAC filter
        3. Build RAG chain (retriever → prompt → LLM)
        4. Invoke chain and extract sources

    Args:
        question: User's question
        role: User's role for RBAC filtering
        top_n: Number of documents after reranking (default 3)
        k: Initial candidates before reranking (default 10)

    Returns:
        dict with keys: answer, sources, retrieval_type, role

    Example:
        result = hybrid_rag_chain("What is IV cannula size for pediatric?", "nurse")
        # Returns:
        # {
        #     "answer": "For pediatric patients under 5kg, use 24G...",
        #     "sources": [
        #         {"source_document": "icu_nursing_procedures.pdf", "section_title": "IV Cannula", "collection": "nursing"}
        #     ],
        #     "retrieval_type": "hybrid_rag",
        #     "role": "nurse"
        # }
    """
    # Initialize components
    llm = get_llm()
    vectorstore = get_vectorstore()

    # Create reranking retriever with RBAC filter
    reranking_retriever = get_reranking_retriever(vectorstore, role=role, top_n=top_n, k=k)

    # Get accessible collections for this role to include in prompt
    accessible_collections = [
        col for col, roles in COLLECTION_ACCESS_ROLES.items() if role in roles
    ]

    # System prompt with role-aware messaging for better "access denied" responses
    system_prompt = f"""You are MediBot, a helpful medical assistant for MediAssist Health Network.

Current user role: {role}
Accessible document collections: {', '.join(accessible_collections)}

Answer the user's question using ONLY the information provided in the context below.
Keep answers concise and professional.

If you find the answer in the context:
- Provide the answer
- Cite the source document and section at the end

If the answer is NOT in the context:
- Do NOT cite any sources
- Respond EXACTLY with: "I don't have that information in your accessible documents. This could be because:
1. The information doesn't exist in the internal documents, OR
2. Your role ({role}) may not have access to the relevant collection.
Your accessible collections are: {', '.join(accessible_collections)}."

Context:
{{context}}"""

    prompt = ChatPromptTemplate.from_messages([
        ("system", system_prompt),
        ("human", "{input}"),
    ])

    # Build RAG chain
    question_answer_chain = create_stuff_documents_chain(llm, prompt)
    rag_chain = create_retrieval_chain(reranking_retriever, question_answer_chain)

    # Invoke chain
    result = rag_chain.invoke({"input": question})
    answer = result.get("answer", "No answer generated")

    # Only include sources if the answer was found in the context
    # If LLM says "I don't have that information", return empty sources
    sources = []
    if "I don't have that information" not in answer:
        for doc in result.get("context", []):
            sources.append({
                "source_document": doc.metadata.get("source_document", "unknown"),
                "section_title": doc.metadata.get("section_title", "unknown"),
                "collection": doc.metadata.get("collection", "unknown")
            })

    return {
        "answer": answer,
        "sources": sources,
        "retrieval_type": "hybrid_rag",
        "role": role
    }


# ============================================
# QUERY ROUTING
# ============================================

# Database schema context for LLM classifier
DATABASE_SCHEMA_CONTEXT = """
DATABASE contains actual records/data:
1. claims - Insurance claim RECORDS (patient claims with amounts, status, dates)
2. maintenance_tickets - Equipment maintenance RECORDS (tickets with fault codes, status)

DOCUMENTS contain policies, procedures, guidelines, definitions:
- Medical procedures (IV cannula sizes, ventilator settings, NGT insertion)
- Drug formulary (dosages, tiers, high-alert medications)
- Billing POLICIES (rejection code DEFINITIONS like EXCL-01, EXCL-02, escalation matrix)
- Equipment manuals (fault code MEANINGS, maintenance schedules, setup procedures)
- Staff handbook (working hours, dress code, password policy)
- Infection control guidelines

ROUTING RULES:
→ SQL: Counting/summing/averaging ACTUAL DATA from claims or maintenance_tickets
   Examples: "How many claims are pending?", "Total claimed amount?", "Average claim by department?"

→ DOCUMENT: Asking about DEFINITIONS, PROCEDURES, POLICIES, or HOW-TO information
   Examples: "What are claim rejection codes?", "What do fault codes mean?", "How to insert NGT?"

KEY DISTINCTION:
- "How many claims are pending?" → SQL (counting actual claim records)
- "What are the claim rejection codes?" → DOCUMENT (asking about code definitions/policies)
- "What fault codes are in maintenance tickets?" → SQL (querying actual ticket data)
- "What are the fault codes for infusion pump?" → DOCUMENT (asking what codes mean)
"""


def is_analytical_question(question: str) -> bool:
    """
    Use LLM to classify if a question should use SQL RAG or Hybrid RAG.

    The LLM considers:
    - Database schema (claims, maintenance_tickets tables)
    - Question intent (analytical vs informational)
    - Context (is it asking about data in DB or info in documents?)

    Args:
        question: User's natural language question

    Returns:
        True if SQL RAG (analytical query on database)
        False if Hybrid RAG (document-based question)

    Example:
        is_analytical_question("How many claims are pending?")  # True → SQL RAG
        is_analytical_question("How many hospitals does MediAssist operate?")  # False → Hybrid RAG
        is_analytical_question("What is IV cannula size?")      # False → Hybrid RAG
    """
    llm = get_llm()

    classification_prompt = ChatPromptTemplate.from_messages([
        ("system", """You are a query router for a hospital information system.
Classify questions into SQL or DOCUMENT:

SQL = Query actual DATA/RECORDS (counts, totals, averages of claims or tickets)
DOCUMENT = Look up POLICIES, PROCEDURES, DEFINITIONS, HOW-TO information

{schema}

Think: Is this asking for DATA from records, or INFORMATION from documentation?
Respond with ONLY one word: SQL or DOCUMENT"""),
        ("human", "Question: {question}")
    ])

    chain = classification_prompt | llm | StrOutputParser()

    try:
        result = chain.invoke({
            "schema": DATABASE_SCHEMA_CONTEXT,
            "question": question
        }).strip().upper()

        return result == "SQL"
    except Exception as e:
        print(f"LLM classification failed: {e}, falling back to keyword detection")
        return _keyword_based_classification(question)


def _keyword_based_classification(question: str) -> bool:
    """
    Fallback keyword-based classification if LLM fails.

    Args:
        question: User's natural language question

    Returns:
        True if likely analytical, False otherwise
    """
    # Database-specific terms that strongly indicate SQL
    sql_indicators = [
        "claim", "claims", "pending", "approved", "rejected",
        "maintenance", "ticket", "equipment", "insurer",
        "department", "campus"
    ]

    analytical_keywords = [
        "how many", "count", "total", "average", "sum",
        "number of", "statistics", "percentage", "ratio",
        "highest", "lowest", "maximum", "minimum", "most", "least"
    ]

    question_lower = question.lower()

    # Must have BOTH an analytical keyword AND a database-related term
    has_analytical = any(kw in question_lower for kw in analytical_keywords)
    has_db_term = any(term in question_lower for term in sql_indicators)

    return has_analytical and has_db_term


def clean_sql(raw: str) -> str:
    """
    Strip markdown fences and any preamble, leaving only the SQL statement.

    Args:
        raw: Raw LLM output that may contain ```sql blocks or prefixes

    Returns:
        Clean SQL query string
    """
    raw = re.sub(r"```(?:sql)?", "", raw).strip("`").strip()
    if "SQLQuery:" in raw:
        raw = raw.split("SQLQuery:")[-1].strip()
    return raw


# ============================================
# STEP 6: SQL RAG
# ============================================

def sql_rag_chain(question: str, role: str) -> dict:
    """
    SQL RAG: Answer analytical questions from the database.

    Three-step process:
        1. LLM generates SQL from natural language question
        2. Clean/extract SQL from LLM output (remove markdown fences)
        3. Execute SQL, pass result to LLM for natural language answer

    Args:
        question: Natural language question about data
        role: User's role (only billing_executive and admin can use SQL RAG)

    Returns:
        dict with keys: answer, sql_query, sql_result, table, retrieval_type, role

    Example:
        result = sql_rag_chain("How many claims are pending?", "admin")
        # Returns: {"answer": "There are 17 pending claims...", "sql_query": "SELECT...", ...}
    """
    # Role check - only billing_executive and admin can use SQL RAG
    if role not in ["billing_executive", "admin"]:
        return {
            "answer": f"As a {role}, you do not have access to analytics data. SQL RAG is only available to billing_executive and admin roles.",
            "sql_query": None,
            "sql_result": None,
            "table": None,
            "retrieval_type": "sql_rag",
            "role": role
        }

    # Initialize database and LLM
    db = SQLDatabase.from_uri(f"sqlite:///{SQL_DB_PATH}")
    db_name = SQL_DB_PATH.name  # Extract db filename (e.g., "mediassist.db")
    llm = get_llm()

    # Step 1: LLM generates SQL from question
    sql_query_chain = create_sql_query_chain(llm, db)
    raw_sql = sql_query_chain.invoke({"question": question})
    sql_query = clean_sql(raw_sql)

    # Step 2: Execute SQL against database
    try:
        sql_result = db.run(sql_query)
    except Exception as e:
        return {
            "answer": f"Error executing SQL query: {str(e)}",
            "sql_query": sql_query,
            "sql_result": None,
            "table": None,
            "retrieval_type": "sql_rag",
            "role": role
        }

    # Extract table name from SQL query
    table_match = re.search(r'FROM\s+["\']?(\w+)["\']?', sql_query, re.IGNORECASE)
    table_name = table_match.group(1) if table_match else "unknown"

    # Step 3: LLM generates natural language answer from SQL result
    answer_prompt = ChatPromptTemplate.from_messages([
        ("system", f"""You are MediBot, an analytics assistant for MediAssist Health Network.
Given a user question and the SQL query result from our hospital database,
provide a clear, concise natural language answer.
Be specific with numbers, dates, and facts from the data.

If you find the answer in the SQL result:
- Provide the answer
- Cite the source at the end: "Source: {db_name}"

If the SQL result is empty or doesn't answer the question:
- Do NOT cite any source
- Respond that the data is not available"""),
        ("human", "Question: {question}\nSQL Result: {result}\n\nAnswer:"),
    ])
    response = answer_prompt | llm
    answer = response.invoke({"question": question, "result": sql_result}).content

    return {
        "answer": answer,
        "sql_query": sql_query,
        "sql_result": sql_result,
        "table": table_name,
        "retrieval_type": "sql_rag",
        "role": role
    }


# ============================================
# MAIN: RUN INGESTION PIPELINE
# ============================================

if __name__ == "__main__":
    print("=" * 60)
    print("MediBot Ingestion Pipeline")
    print("=" * 60)

    # Get all document paths
    doc_files = get_all_document_paths()
    print(f"\nFound {len(doc_files)} documents:")
    for collection, path in doc_files:
        print(f"  [{collection}] {path.name}")

    # Process all documents
    print("\n" + "=" * 60)
    print("Step 1 & 2: Load + Chunk all documents")
    print("=" * 60)

    all_chunks = []
    for collection_name, file_path in doc_files:
        print(f"\nProcessing: {file_path.name} [{collection_name}]")

        # Step 1: Load
        doc = load_document(file_path)
        print(f"  ✓ Document loaded")

        # Step 2: Chunk
        chunks = chunk_document(doc, collection_name, file_path)
        print(f"  ✓ Created {len(chunks)} chunks")

        all_chunks.extend(chunks)

    print(f"\n📊 Total chunks from all documents: {len(all_chunks)}")

    # Show sample chunks
    print("\n" + "-" * 60)
    print("Sample chunks:")
    print("-" * 60)
    for i, chunk in enumerate(all_chunks[:2]):
        print(f"\n[Chunk {i+1}]")
        print(f"  Collection: {chunk.metadata['collection']}")
        print(f"  Access roles: {chunk.metadata['access_roles']}")
        print(f"  Section: {chunk.metadata['section_title']}")
        print(f"  Type: {chunk.metadata['chunk_type']}")
        print(f"  Source: {chunk.metadata['source_document']}")
        print(f"  Text preview: {chunk.page_content[:100]}...")

    # Step 3: Store in Qdrant
    print("\n" + "=" * 60)
    print("Step 3: Store in Qdrant (Hybrid Search)")
    print("=" * 60)
    vectorstore = store_in_qdrant(all_chunks)

    # Cleanup: Close Qdrant client to avoid shutdown error
    if hasattr(vectorstore, 'client') and vectorstore.client:
        vectorstore.client.close()

    print("\n" + "=" * 60)
    print("✅ Ingestion Complete!")
    print("=" * 60)

    # Step 4: Test Hybrid RAG using hybrid_rag_chain()
    print("\n" + "=" * 60)
    print("Step 4: Testing Hybrid RAG")
    print("=" * 60)

    # List of (question, role) tuples to test
    hybrid_rag_tests = [
        ("What is the IV cannula size for pediatric patients?", "nurse"),
        ("How do you set up the patient monitoring system BM-500?", "admin"),
        ("What is the drug dosage for paracetamol for adults?", "doctor"),
        ("What are the common claim rejection codes?", "billing_executive"),
        ("What are the fault codes for the infusion pump?", "technician"),
    ]

    for i, (question, role) in enumerate(hybrid_rag_tests, 1):
        print(f"\n{'─' * 60}")
        print(f"Test {i}/{len(hybrid_rag_tests)}")
        print(f"{'─' * 60}")
        print(f"Question: '{question}'")
        print(f"Role: {role}")
        print(f"Is analytical: {is_analytical_question(question)}")

        result = hybrid_rag_chain(question, role)

        print("\n🤖 MediBot Response:")
        answer = result["answer"]
        print(answer[:300] + "..." if len(answer) > 300 else answer)

        print("\n📚 Sources:")
        if result["sources"]:
            for j, source in enumerate(result["sources"]):
                print(f"  {j+1}. [{source['collection']}] {source['source_document']} - {source['section_title'][:40]}...")
        else:
            print("  (none)")

        print(f"\nRetrieval type: {result['retrieval_type']}")

    print("\n" + "=" * 60)
    print(f"✅ Hybrid RAG Test Complete! ({len(hybrid_rag_tests)} tests)")
    print("=" * 60)

    # Step 5: Test SQL RAG using sql_rag_chain()
    print("\n" + "=" * 60)
    print("Step 5: Testing SQL RAG")
    print("=" * 60)

    # List of (question, role) tuples to test
    # Authorized roles: admin, billing_executive
    # Unauthorized roles: nurse, doctor, technician (should be blocked)
    sql_rag_tests = [
        ("How many claims are pending?", "admin"),
        ("Which department has the most claims?", "billing_executive"),
        ("What is the total claimed amount by insurer?", "admin"),
        ("How many maintenance tickets are open?", "billing_executive"),
        ("How many claims are pending?", "nurse"),  # Should be blocked
        ("What is the average approved amount?", "doctor"),  # Should be blocked
    ]

    for i, (question, role) in enumerate(sql_rag_tests, 1):
        print(f"\n{'─' * 60}")
        print(f"Test {i}/{len(sql_rag_tests)}")
        print(f"{'─' * 60}")
        print(f"Question: '{question}'")
        print(f"Role: {role}")

        result = sql_rag_chain(question, role)

        # Check if access was blocked
        is_blocked = "do not have access" in result["answer"].lower() or result.get("sql_query") is None

        if is_blocked:
            print(f"Access: BLOCKED (as expected for {role})")
        else:
            print(f"SQL: {result.get('sql_query', 'N/A')}")
            print(f"Table: {result.get('table', 'N/A')}")

        print("\n🤖 MediBot Response:")
        answer = result["answer"]
        print(answer[:300] + "..." if len(answer) > 300 else answer)

        print(f"\nRetrieval type: {result['retrieval_type']}")

    print("\n" + "=" * 60)
    print(f"✅ SQL RAG Test Complete! ({len(sql_rag_tests)} tests)")
    print("=" * 60)

    # Step 6: Test Query Routing
    print("\n" + "=" * 60)
    print("Step 6: Testing Query Routing")
    print("=" * 60)

    routing_tests = [
        ("How many claims are pending?", True),
        ("What is IV cannula size for pediatric?", False),
        ("Total amount claimed by department?", True),
        ("What is the drug dosage for paracetamol?", False),
        ("Count of maintenance tickets?", True),
    ]

    print("\nQuery Routing Test:")
    for question, expected in routing_tests:
        actual = is_analytical_question(question)
        status = "✅" if actual == expected else "❌"
        route = "SQL RAG" if actual else "Hybrid RAG"
        print(f"  {status} '{question[:45]}...' → {route}")

    print("\n" + "=" * 60)
    print("✅ All Tests Complete!")
    print("=" * 60)
