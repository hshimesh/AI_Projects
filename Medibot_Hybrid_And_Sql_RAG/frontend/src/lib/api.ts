/**
 * API utility functions for MediBot backend
 */

// Backend API URL (hardcoded since frontend and backend run on same server)
const API_URL = "http://localhost:8000";

// Types
export interface LoginRequest {
  username: string;
  password: string;
}

export interface LoginResponse {
  role: string;
  collections: string[];
}

export interface ChatRequest {
  question: string;
  role: string;
}

export interface Source {
  source_document: string;
  section_title: string;
  collection: string;
}

export interface ChatResponse {
  answer: string;
  sources: Source[];
  retrieval_type: "hybrid_rag" | "sql_rag";
  role: string;
}

/**
 * Login to MediBot API
 */
export async function login(data: LoginRequest): Promise<LoginResponse> {
  const response = await fetch(`${API_URL}/login`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(data),
  });

  if (!response.ok) {
    const error = await response.json();
    throw new Error(error.detail || "Login failed");
  }

  return response.json();
}

/**
 * Send chat message to MediBot API
 */
export async function chat(data: ChatRequest): Promise<ChatResponse> {
  const response = await fetch(`${API_URL}/chat`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(data),
  });

  if (!response.ok) {
    const error = await response.json();
    throw new Error(error.detail || "Chat request failed");
  }

  return response.json();
}

/**
 * Get collections accessible to a role
 */
export async function getCollections(role: string): Promise<{ role: string; collections: string[] }> {
  const response = await fetch(`${API_URL}/collections/${role}`);

  if (!response.ok) {
    const error = await response.json();
    throw new Error(error.detail || "Failed to get collections");
  }

  return response.json();
}

/**
 * Health check
 */
export async function healthCheck(): Promise<{ status: string }> {
  const response = await fetch(`${API_URL}/health`);
  return response.json();
}
