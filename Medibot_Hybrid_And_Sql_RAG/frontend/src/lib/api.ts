/**
 * API utility functions for MediBot backend.
 *
 * Auth model: /login returns a signed JWT which is sent as a Bearer token on
 * every subsequent request. The role is never sent by the client - the backend
 * reads it from the verified token. Each authenticated response carries a
 * refreshed token (X-Refreshed-Token), giving a 30-minute *idle* timeout rather
 * than a hard cutoff 30 minutes after login.
 */

// Backend API URL. The backend runs on the same host as the frontend, on port
// 8000, so the host is derived from the browser's own address rather than
// hardcoded. This works unchanged whether the app is opened at localhost:3000
// or over the LAN at <server-ip>:3000 - no configuration, no per-machine edits.
const API_URL =
  typeof window !== "undefined"
    ? `${window.location.protocol}//${window.location.hostname}:8000`
    : "http://localhost:8000";

const TOKEN_KEY = "token";
const USER_KEY = "user";
const ACTIVITY_KEY = "lastActivity";
const REFRESH_HEADER = "X-Refreshed-Token";

/** Idle timeout, mirroring JWT_EXPIRY_MINUTES in backend/main.py. */
export const IDLE_TIMEOUT_MS = 30 * 60 * 1000;

// Types
export interface LoginRequest {
  username: string;
  password: string;
}

export interface LoginResponse {
  token: string;
  role: string;
  collections: string[];
}

export interface StoredUser {
  username: string;
  role: string;
  collections: string[];
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

// ============================================
// Session storage
// ============================================

export function getToken(): string | null {
  return localStorage.getItem(TOKEN_KEY);
}

export function getStoredUser(): StoredUser | null {
  const raw = localStorage.getItem(USER_KEY);
  if (!raw) return null;
  try {
    return JSON.parse(raw) as StoredUser;
  } catch {
    return null;
  }
}

function markActivity(): void {
  localStorage.setItem(ACTIVITY_KEY, String(Date.now()));
}

/** Milliseconds since the last successful API call, or Infinity if unknown. */
export function msSinceLastActivity(): number {
  const last = Number(localStorage.getItem(ACTIVITY_KEY) || 0);
  return last ? Date.now() - last : Infinity;
}

export function clearSession(): void {
  localStorage.removeItem(TOKEN_KEY);
  localStorage.removeItem(USER_KEY);
  localStorage.removeItem(ACTIVITY_KEY);
}

/** Clear the session and send the user back to the login screen. */
export function endSession(expired = false): void {
  clearSession();
  window.location.href = expired ? "/login?expired=true" : "/login";
}

// ============================================
// Authenticated fetch
// ============================================

/**
 * fetch() wrapper for endpoints that require a token.
 *
 * Attaches the Authorization header, swaps in the refreshed token the backend
 * returns, and handles 401 centrally by ending the session.
 */
async function authFetch(path: string, init: RequestInit = {}): Promise<Response> {
  const token = getToken();
  if (!token) {
    endSession();
    throw new Error("Not authenticated");
  }

  const response = await fetch(`${API_URL}${path}`, {
    ...init,
    headers: {
      ...(init.headers || {}),
      Authorization: `Bearer ${token}`,
    },
  });

  // Sliding expiry: the backend issues a replacement token on every
  // authenticated request. Requires expose_headers on the backend CORS config.
  const refreshed = response.headers.get(REFRESH_HEADER);
  if (refreshed) {
    localStorage.setItem(TOKEN_KEY, refreshed);
  }

  if (response.status === 401) {
    endSession(true);
    throw new Error("Session expired");
  }

  markActivity();
  return response;
}

// ============================================
// Endpoints
// ============================================

/**
 * Login to MediBot API and store the session.
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

  const result: LoginResponse = await response.json();

  localStorage.setItem(TOKEN_KEY, result.token);
  localStorage.setItem(
    USER_KEY,
    JSON.stringify({
      username: data.username,
      role: result.role,
      collections: result.collections,
    })
  );
  markActivity();

  return result;
}

/**
 * Send chat message to MediBot API.
 *
 * No role is sent: the backend derives it from the bearer token.
 */
export async function chat(question: string): Promise<ChatResponse> {
  const response = await authFetch("/chat", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ question }),
  });

  if (!response.ok) {
    const error = await response.json();
    throw new Error(error.detail || "Chat request failed");
  }

  return response.json();
}

/**
 * Get collections accessible to a role.
 *
 * The backend rejects any role other than the authenticated one with 403, so
 * this is only callable for your own role.
 */
export async function getCollections(role: string): Promise<{ role: string; collections: string[] }> {
  const response = await authFetch(`/collections/${role}`);

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
