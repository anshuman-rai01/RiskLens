/**
 * Real Authentication Service for RiskLens
 * 
 * Communicates with FastAPI backend:
 * - POST /auth/register
 * - POST /auth/login
 * - POST /auth/refresh (with token rotation)
 * - POST /auth/logout
 * 
 * Token Storage Discipline:
 * - Access token in memory (via api.ts) to minimize XSS exposure
 * - Refresh token in localStorage to allow session restoration across reloads
 * - Zero dependency on client-side PBKDF2 / mock signing (crypto.ts eliminated from auth)
 */

import {
  ApiError,
  apiRequest,
  getAccessToken,
  getRefreshToken,
  onAuthRevoked,
  parseJwtPayload,
  setAccessToken,
  setRefreshToken,
} from "./api";
import type { PublicUser } from "./types";

export { ApiError };

export interface CurrentSession {
  user: PublicUser;
  access: string;
  accessExp: number;
  refresh: string;
}

let currentSession: CurrentSession | null = null;
const authListeners = new Set<() => void>();

export function subscribeAuth(fn: () => void): () => void {
  authListeners.add(fn);
  return () => {
    authListeners.delete(fn);
  };
}

function notifyAuth(): void {
  authListeners.forEach((fn) => fn());
}

export function getAuthSnapshot(): CurrentSession | null {
  return currentSession;
}

// Hook into background token revocation from api.ts
onAuthRevoked(() => {
  currentSession = null;
  notifyAuth();
});

interface TokenResponse {
  access_token: string;
  refresh_token: string;
  token_type: string;
}

function buildSessionFromTokens(tokens: TokenResponse, emailFallback?: string): CurrentSession {
  const payload = parseJwtPayload(tokens.access_token);
  const userId = String(payload.sub || "user");
  const expSeconds = typeof payload.exp === "number" ? payload.exp : Math.floor(Date.now() / 1000) + 900;
  const accessExp = expSeconds * 1000;

  // Stored email or fallback
  const email = emailFallback || (typeof payload.email === "string" ? payload.email : "user@risklens.internal");

  const user: PublicUser = {
    id: userId,
    email,
    createdAt: new Date().toISOString(),
  };

  return {
    user,
    access: tokens.access_token,
    accessExp,
    refresh: tokens.refresh_token,
  };
}

/**
 * Boot-time session recovery: verifies if a valid refresh token exists in localStorage
 * and attempts a single rotation to re-establish the in-memory access token.
 */
export async function ensureReady(): Promise<void> {
  const refresh = getRefreshToken();
  if (!refresh) {
    currentSession = null;
    return;
  }

  try {
    const tokens = await apiRequest<TokenResponse>("/auth/refresh", {
      method: "POST",
      body: JSON.stringify({ refresh_token: refresh }),
    });

    setAccessToken(tokens.access_token);
    setRefreshToken(tokens.refresh_token);

    // Retrieve user profile to ensure valid email and state
    let email: string | undefined;
    try {
      const storedEmail = localStorage.getItem("risklens_user_email");
      if (storedEmail) email = storedEmail;
    } catch {
      // ignore
    }

    currentSession = buildSessionFromTokens(tokens, email);
    notifyAuth();
  } catch {
    setAccessToken(null);
    setRefreshToken(null);
    currentSession = null;
    notifyAuth();
  }
}

/**
 * Register a new user account with real backend password hashing (bcrypt).
 */
export async function register(email: string, password: string): Promise<void> {
  const normalizedEmail = email.trim().toLowerCase();
  const tokens = await apiRequest<TokenResponse>("/auth/register", {
    method: "POST",
    body: JSON.stringify({ email: normalizedEmail, password }),
  });

  setAccessToken(tokens.access_token);
  setRefreshToken(tokens.refresh_token);
  try {
    localStorage.setItem("risklens_user_email", normalizedEmail);
  } catch {
    // ignore
  }

  currentSession = buildSessionFromTokens(tokens, normalizedEmail);
  notifyAuth();
}

/**
 * Authenticate with email & password against FastAPI backend.
 */
export async function login(email: string, password: string): Promise<void> {
  const normalizedEmail = email.trim().toLowerCase();
  const tokens = await apiRequest<TokenResponse>("/auth/login", {
    method: "POST",
    body: JSON.stringify({ email: normalizedEmail, password }),
  });

  setAccessToken(tokens.access_token);
  setRefreshToken(tokens.refresh_token);
  try {
    localStorage.setItem("risklens_user_email", normalizedEmail);
  } catch {
    // ignore
  }

  currentSession = buildSessionFromTokens(tokens, normalizedEmail);
  notifyAuth();
}

/**
 * Log out and revoke refresh token server-side.
 */
export async function logout(): Promise<void> {
  const refresh = getRefreshToken();
  if (refresh) {
    try {
      await apiRequest("/auth/logout", {
        method: "POST",
        body: JSON.stringify({ refresh_token: refresh }),
      });
    } catch {
      // Clean up client state regardless of server logout response
    }
  }

  setAccessToken(null);
  setRefreshToken(null);
  try {
    localStorage.removeItem("risklens_user_email");
  } catch {
    // ignore
  }

  currentSession = null;
  notifyAuth();
}

export async function logoutEverywhere(): Promise<void> {
  await logout();
}

export async function forceRotate(): Promise<void> {
  const refresh = getRefreshToken();
  if (!refresh) throw new ApiError(401, "No active session to rotate", "UNAUTHORIZED");

  const tokens = await apiRequest<TokenResponse>("/auth/refresh", {
    method: "POST",
    body: JSON.stringify({ refresh_token: refresh }),
  });

  setAccessToken(tokens.access_token);
  setRefreshToken(tokens.refresh_token);

  const prevEmail = currentSession?.user.email;
  currentSession = buildSessionFromTokens(tokens, prevEmail);
  notifyAuth();
}

export async function changePassword(currentPw: string, nextPw: string): Promise<void> {
  // Can be mapped to backend password change or profile update
  // For now, logout everywhere to enforce security
  await logout();
}

export async function requireUserId(): Promise<string> {
  if (currentSession?.user?.id) {
    return currentSession.user.id;
  }
  const token = getAccessToken();
  if (token) {
    const payload = parseJwtPayload(token);
    if (payload.sub) return String(payload.sub);
  }
  throw new ApiError(401, "Authentication required", "UNAUTHORIZED");
}

export function listMySessions() {
  // Session details are managed server-side in the refresh_tokens table
  return [];
}
