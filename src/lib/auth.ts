/**
 * Auth service — the client-side analogue of the FastAPI auth router.
 *  - register / login            → POST /auth/register, POST /auth/login
 *  - refresh (with rotation)     → POST /auth/refresh
 *  - logout / logoutEverywhere   → POST /auth/logout, DELETE /auth/sessions
 *  - changePassword              → POST /auth/password
 * Access tokens: 30 min. Refresh tokens: 7 days, rotated on every use.
 * Refresh-token reuse (theft indicator) revokes every session for the user.
 */

import { hashPassword, initSigning, signToken, verifyPassword, verifyToken } from "./crypto";
import { buildDemoRows, DEMO_EMAIL } from "./seed";
import { readTable, readValue, removeValue, uid, writeTable, writeValue } from "./store";
import { checkPassword, validateEmail } from "./validation";
import type { AuthBundle, Profile, PublicUser, SessionRecord, StoredUser } from "./types";

export const ACCESS_TTL_MS = 30 * 60_000;
export const REFRESH_TTL_MS = 7 * 24 * 3_600_000;

export class ApiError extends Error {
  code: string;
  field?: string;
  constructor(code: string, message: string, field?: string) {
    super(message);
    this.code = code;
    this.field = field;
  }
}

/* ---------------- current session (module singleton) ---------------- */

interface CurrentSession {
  user: PublicUser;
  access: string;
  accessExp: number;
  refresh: string;
}

let current: CurrentSession | null = null;
const authListeners = new Set<() => void>();

export function subscribeAuth(fn: () => void): () => void {
  authListeners.add(fn);
  return () => {
    authListeners.delete(fn);
  };
}

function setAuth(next: CurrentSession | null): void {
  current = next;
  authListeners.forEach((fn) => fn());
}

export function getAuthSnapshot(): CurrentSession | null {
  return current;
}

/* ---------------- table accessors ---------------- */

const readUsers = () => readTable<StoredUser>("users");
const readSessions = () => readTable<SessionRecord>("sessions");
const toPublic = (u: StoredUser): PublicUser => ({ id: u.id, email: u.email, createdAt: u.createdAt });

function defaultProfile(userId: string): Profile {
  return {
    userId,
    name: "",
    age: null,
    role: "student",
    currency: "$",
    monthlySpendingCap: null,
    monthlySavingsTarget: null,
    weeklyStudyHours: null,
    weeklyFitnessMinutes: null,
    weeklyHabitCompletions: null,
    updatedAt: new Date().toISOString(),
  };
}

/* ---------------- bootstrap & demo seed ---------------- */

export async function ensureReady(): Promise<void> {
  await initSigning();
  const seeded = readValue("seeded.v1", false);
  if (!seeded) {
    writeValue("seeded.v1", true);
    if (!readUsers().some((u) => u.email === DEMO_EMAIL)) {
      const demo = await buildDemoRows();
      writeTable("users", [...readUsers(), demo.user]);
      writeTable("profiles", [...readTable<Profile>("profiles"), demo.profile]);
      writeTable("entries", [...readTable("entries"), ...demo.entries]);
    }
  }
  const refresh = readValue<string | null>("currentRefresh", null);
  if (refresh) {
    try {
      await rotate(refresh);
    } catch {
      removeValue("currentRefresh");
    }
  }
}

/* ---------------- session machinery ---------------- */

async function createSession(userId: string): Promise<string> {
  const now = Date.now();
  const jti = uid("ses");
  const refresh = await signToken({ sub: userId, type: "refresh", jti, iat: now, exp: now + REFRESH_TTL_MS });
  const agent = typeof navigator !== "undefined" && navigator.userAgent ? navigator.userAgent.slice(0, 90) : "unknown";
  const sessions = readSessions().filter((s) => new Date(s.expiresAt).getTime() > now);
  sessions.push({
    jti,
    userId,
    createdAt: new Date(now).toISOString(),
    expiresAt: new Date(now + REFRESH_TTL_MS).toISOString(),
    rotatedAt: new Date(now).toISOString(),
    userAgent: agent,
  });
  writeTable("sessions", sessions);
  return refresh;
}

async function issueAccess(user: StoredUser): Promise<{ token: string; exp: number }> {
  const now = Date.now();
  const exp = now + ACCESS_TTL_MS;
  const token = await signToken({ sub: user.id, email: user.email, type: "access", iat: now, exp });
  return { token, exp };
}

async function rotate(refreshToken: string): Promise<void> {
  const payload = await verifyToken(refreshToken);
  if (!payload || payload.type !== "refresh" || !payload.jti) {
    throw new ApiError("REFRESH_INVALID", "This session is no longer valid. Sign in again.");
  }
  const sessions = readSessions();
  const rec = sessions.find((s) => s.jti === payload.jti);
  const now = Date.now();

  if (!rec || rec.userId !== payload.sub || new Date(rec.expiresAt).getTime() < now) {
    // Unknown, mismatched, or expired jti → possible token reuse. Revoke everything for this user.
    writeTable(
      "sessions",
      sessions.filter((s) => s.userId !== payload.sub),
    );
    removeValue("currentRefresh");
    setAuth(null);
    throw new ApiError("SESSION_REVOKED", "Session was revoked for safety. Sign in again.");
  }

  const userRow = readUsers().find((u) => u.id === rec.userId);
  if (!userRow) throw new ApiError("USER_GONE", "Account no longer exists.");

  // Rotation: retire the old jti, issue a fresh refresh token.
  const newJti = uid("ses");
  const newRefresh = await signToken({ sub: rec.userId, type: "refresh", jti: newJti, iat: now, exp: now + REFRESH_TTL_MS });
  const next: SessionRecord = {
    ...rec,
    jti: newJti,
    rotatedAt: new Date(now).toISOString(),
  };
  writeTable(
    "sessions",
    sessions.filter((s) => s.jti !== rec.jti).concat(next),
  );
  writeValue("currentRefresh", newRefresh);

  const access = await issueAccess(userRow);
  setAuth({ user: toPublic(userRow), access: access.token, accessExp: access.exp, refresh: newRefresh });
}

/** Returns a valid access token, transparently refreshing when expired. */
export async function getValidAccess(): Promise<string> {
  if (!current) throw new ApiError("UNAUTHENTICATED", "Not signed in.");
  if (Date.now() < current.accessExp - 20_000) return current.access;
  await rotate(current.refresh);
  if (!current) throw new ApiError("UNAUTHENTICATED", "Session expired.");
  return current.access;
}

/** Manually rotate the refresh token (exposed as "rotate now" in the session panel). */
export async function forceRotate(): Promise<void> {
  if (!current) throw new ApiError("UNAUTHENTICATED", "Not signed in.");
  await rotate(current.refresh);
}

/**
 * The isolation boundary. Every repository call resolves the acting user from a
 * cryptographically verified token — never from client-supplied ids.
 */
export async function requireUserId(): Promise<string> {
  const token = await getValidAccess();
  const payload = await verifyToken(token);
  if (!payload || payload.type !== "access") throw new ApiError("UNAUTHENTICATED", "Invalid access token.");
  return payload.sub;
}

/* ---------------- public auth API ---------------- */

export async function register(emailRaw: string, password: string): Promise<AuthBundle> {
  const email = emailRaw.trim().toLowerCase();
  const emailErr = validateEmail(email);
  if (emailErr) throw new ApiError("VALIDATION", emailErr, "email");
  const pw = checkPassword(password);
  if (!pw.ok) throw new ApiError("VALIDATION", pw.message ?? "Password too weak.", "password");
  if (readUsers().some((u) => u.email === email))
    throw new ApiError("EMAIL_TAKEN", "An account with this email already exists.", "email");

  const { salt, hash, iterations } = await hashPassword(password);
  const id = uid("usr");
  const now = new Date().toISOString();
  const userRow: StoredUser = { id, email, passwordHash: hash, salt, iterations, createdAt: now };
  writeTable("users", [...readUsers(), userRow]);
  writeTable("profiles", [...readTable<Profile>("profiles"), defaultProfile(id)]);

  const refresh = await createSession(id);
  const access = await issueAccess(userRow);
  writeValue("currentRefresh", refresh);
  const user = toPublic(userRow);
  setAuth({ user, access: access.token, accessExp: access.exp, refresh });
  return { user, accessToken: access.token, accessExpiresAt: access.exp, refreshToken: refresh };
}

export async function login(emailRaw: string, password: string): Promise<AuthBundle> {
  const email = emailRaw.trim().toLowerCase();
  const userRow = readUsers().find((u) => u.email === email);
  // Same cost & message whether the user exists or not — no account enumeration.
  const ok = userRow
    ? await verifyPassword(password, userRow.salt, userRow.passwordHash, userRow.iterations)
    : await verifyPassword(password, "00".repeat(16), "00".repeat(32), 1000).then(() => false);
  if (!ok || !userRow) throw new ApiError("INVALID_CREDENTIALS", "Email or password is incorrect.");

  const refresh = await createSession(userRow.id);
  const access = await issueAccess(userRow);
  writeValue("currentRefresh", refresh);
  const user = toPublic(userRow);
  setAuth({ user, access: access.token, accessExp: access.exp, refresh });
  return { user, accessToken: access.token, accessExpiresAt: access.exp, refreshToken: refresh };
}

export async function logout(): Promise<void> {
  if (current) {
    const myId = current.user.id;
    const payload = await verifyToken(current.refresh);
    const now = Date.now();
    writeTable(
      "sessions",
      readSessions().filter(
        (s) =>
          s.jti !== payload?.jti &&
          !(s.userId === myId && new Date(s.expiresAt).getTime() < now),
      ),
    );
  }
  removeValue("currentRefresh");
  setAuth(null);
}

export async function logoutEverywhere(): Promise<void> {
  if (current) {
    writeTable(
      "sessions",
      readSessions().filter((s) => s.userId !== current!.user.id),
    );
  }
  removeValue("currentRefresh");
  setAuth(null);
}

export async function changePassword(currentPw: string, newPw: string): Promise<void> {
  const userId = await requireUserId();
  const userRow = readUsers().find((u) => u.id === userId);
  if (!userRow) throw new ApiError("USER_GONE", "Account no longer exists.");
  const ok = await verifyPassword(currentPw, userRow.salt, userRow.passwordHash, userRow.iterations);
  if (!ok) throw new ApiError("INVALID_CREDENTIALS", "Current password is incorrect.", "currentPassword");
  const check = checkPassword(newPw);
  if (!check.ok) throw new ApiError("VALIDATION", check.message ?? "New password too weak.", "newPassword");

  const { salt, hash, iterations } = await hashPassword(newPw);
  writeTable(
    "users",
    readUsers().map((u) => (u.id === userId ? { ...u, passwordHash: hash, salt, iterations } : u)),
  );
  // Hygiene: revoke every other device's session.
  if (current) {
    const payload = await verifyToken(current.refresh);
    writeTable(
      "sessions",
      readSessions().filter((s) => s.userId !== userId || s.jti === payload?.jti),
    );
  }
}

export function listMySessions(): SessionRecord[] {
  if (!current) return [];
  const now = Date.now();
  return readSessions()
    .filter((s) => s.userId === current!.user.id && new Date(s.expiresAt).getTime() > now)
    .sort((a, b) => b.rotatedAt.localeCompare(a.rotatedAt));
}
