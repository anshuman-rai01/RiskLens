/**
 * Change-notification layer.
 *
 * In the FastAPI/Postgres deployment, all data persistence goes through
 * the REST API (db.ts → api.ts).  This module provides the reactive
 * change-event plumbing that db.ts calls after mutations and that the
 * UI consumes via useSyncExternalStore (useDataVersion in ui.tsx).
 *
 * The localStorage-based persistence functions (readTable, writeTable,
 * readValue, writeValue, etc.) have been removed — they are no longer
 * called by any live code path now that db.ts talks to the backend.
 */

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
