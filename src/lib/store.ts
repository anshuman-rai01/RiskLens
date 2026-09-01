/**
 * Persistence + change-notification layer.
 * In the FastAPI/Postgres deployment this module is replaced by the DB driver —
 * every repository in db.ts talks to storage only through this interface.
 * Falls back to an in-memory map if localStorage is unavailable (sandboxed frames).
 */

const PREFIX = "risklens.";
const memory = new Map<string, string>();

function lsGet(key: string): string | null {
  try {
    return localStorage.getItem(PREFIX + key);
  } catch {
    return memory.get(PREFIX + key) ?? null;
  }
}

function lsSet(key: string, value: string): void {
  try {
    localStorage.setItem(PREFIX + key, value);
  } catch {
    memory.set(PREFIX + key, value);
  }
}

function lsDel(key: string): void {
  try {
    localStorage.removeItem(PREFIX + key);
  } catch {
    memory.delete(PREFIX + key);
  }
}

/* ---------------- tables ---------------- */

export function readTable<T>(name: string): T[] {
  const raw = lsGet("table." + name);
  if (!raw) return [];
  try {
    const parsed: unknown = JSON.parse(raw);
    return Array.isArray(parsed) ? (parsed as T[]) : [];
  } catch {
    return [];
  }
}

export function writeTable<T>(name: string, rows: T[]): void {
  lsSet("table." + name, JSON.stringify(rows));
  emitChange();
}

/* ---------------- scalar values ---------------- */

export function readValue<T>(name: string, fallback: T): T {
  const raw = lsGet("value." + name);
  if (raw == null) return fallback;
  try {
    return JSON.parse(raw) as T;
  } catch {
    return fallback;
  }
}

export function writeValue(name: string, value: unknown): void {
  lsSet("value." + name, JSON.stringify(value));
}

export function removeValue(name: string): void {
  lsDel("value." + name);
}

/* ---------------- change events ---------------- */

type Listener = () => void;
const listeners = new Set<Listener>();
let version = 0;

export function subscribeData(fn: Listener): () => void {
  listeners.add(fn);
  return () => {
    listeners.delete(fn);
  };
}

/** Monotonic counter for useSyncExternalStore — bumps on every write. */
export function getDataVersion(): number {
  return version;
}

export function emitChange(): void {
  version += 1;
  listeners.forEach((fn) => fn());
}

/* ---------------- ids ---------------- */

export function uid(prefix: string): string {
  let rand: string;
  try {
    const bytes = crypto.getRandomValues(new Uint8Array(9));
    rand = Array.from(bytes, (b) => b.toString(16).padStart(2, "0")).join("");
  } catch {
    rand = Math.random().toString(16).slice(2) + Math.random().toString(16).slice(2);
  }
  return `${prefix}_${Date.now().toString(36)}${rand}`;
}
