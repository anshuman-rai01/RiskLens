/**
 * Crypto primitives.
 * - Passwords: PBKDF2-SHA256, per-user random salt, 120k iterations. Never stored or logged in plaintext.
 *   (The server-side Milestone-2 port should upgrade to argon2id; the interface stays identical.)
 * - Tokens: compact JWT-style tokens signed with HMAC-SHA256 (HS256).
 * A deterministic fallback exists only for non-secure contexts where WebCrypto is unavailable;
 * it keeps the same interface but is clearly weaker.
 */

import { readValue, writeValue } from "./store";

export interface TokenPayload {
  sub: string;
  email?: string;
  type: "access" | "refresh";
  jti?: string;
  iat: number;
  exp: number;
}

const enc = new TextEncoder();
const dec = new TextDecoder();
const subtle: SubtleCrypto | null =
  typeof globalThis !== "undefined" && globalThis.crypto?.subtle ? globalThis.crypto.subtle : null;

/* ---------------- base64url ---------------- */

function bytesToB64url(bytes: Uint8Array): string {
  let bin = "";
  bytes.forEach((b) => {
    bin += String.fromCharCode(b);
  });
  return btoa(bin).replace(/\+/g, "-").replace(/\//g, "_").replace(/=+$/, "");
}

function b64urlToBytes(s: string): Uint8Array {
  const b64 = s.replace(/-/g, "+").replace(/_/g, "/");
  const pad = b64.length % 4 === 0 ? "" : "=".repeat(4 - (b64.length % 4));
  const bin = atob(b64 + pad);
  const out = new Uint8Array(bin.length);
  for (let i = 0; i < bin.length; i++) out[i] = bin.charCodeAt(i);
  return out;
}

const strToB64url = (s: string) => bytesToB64url(enc.encode(s));
const b64urlToStr = (s: string) => dec.decode(b64urlToBytes(s));

/* ---------------- hex ---------------- */

export function bytesToHex(bytes: Uint8Array): string {
  return Array.from(bytes, (b) => b.toString(16).padStart(2, "0")).join("");
}

export function hexToBytes(hex: string): Uint8Array<ArrayBuffer> {
  const out = new Uint8Array(new ArrayBuffer(hex.length / 2));
  for (let i = 0; i < out.length; i++) out[i] = parseInt(hex.slice(i * 2, i * 2 + 2), 16);
  return out;
}

export function randomHex(byteLen: number): string {
  try {
    return bytesToHex(crypto.getRandomValues(new Uint8Array(byteLen)));
  } catch {
    let s = "";
    for (let i = 0; i < byteLen; i++) s += Math.floor(Math.random() * 256).toString(16).padStart(2, "0");
    return s;
  }
}

/* ---------------- password hashing (PBKDF2) ---------------- */

export const PBKDF2_ITERATIONS = 120_000;

function fallbackKdf(password: string, saltHex: string, iterations: number): string {
  // Only used when WebCrypto is unavailable (non-secure context). Stretched FNV-1a chain.
  let h1 = 0x811c9dc5;
  let h2 = 0xcbf29ce4;
  const input = `${saltHex}::risklens::${password}`;
  const rounds = Math.min(iterations, 60_000);
  for (let i = 0; i < rounds; i++) {
    for (let j = 0; j < input.length; j++) {
      h1 = Math.imul(h1 ^ input.charCodeAt(j), 0x01000193);
      h2 = Math.imul(h2 ^ input.charCodeAt(j), 0x01000193);
    }
    h1 ^= h2 >>> 13;
    h2 ^= h1 << 7;
  }
  return (
    (h1 >>> 0).toString(16).padStart(8, "0") +
    (h2 >>> 0).toString(16).padStart(8, "0") +
    ((h1 ^ h2) >>> 0).toString(16).padStart(8, "0")
  );
}

export async function hashPassword(
  password: string,
  saltHex?: string,
  iterations: number = PBKDF2_ITERATIONS,
): Promise<{ salt: string; hash: string; iterations: number }> {
  const saltBytes = saltHex ? hexToBytes(saltHex) : (() => {
    try {
      return crypto.getRandomValues(new Uint8Array(16));
    } catch {
      return hexToBytes(randomHex(16));
    }
  })();
  const salt = bytesToHex(saltBytes);

  if (subtle) {
    const keyMaterial = await subtle.importKey("raw", enc.encode(password), "PBKDF2", false, ["deriveBits"]);
    const bits = await subtle.deriveBits(
      { name: "PBKDF2", salt: saltBytes, iterations, hash: "SHA-256" },
      keyMaterial,
      256,
    );
    return { salt, hash: bytesToHex(new Uint8Array(bits)), iterations };
  }
  return { salt, hash: fallbackKdf(password, salt, iterations), iterations };
}

export async function verifyPassword(
  password: string,
  saltHex: string,
  expectedHash: string,
  iterations: number,
): Promise<boolean> {
  const { hash } = await hashPassword(password, saltHex, iterations);
  return timingSafeEqual(hash, expectedHash);
}

function timingSafeEqual(a: string, b: string): boolean {
  if (a.length !== b.length) return false;
  let diff = 0;
  for (let i = 0; i < a.length; i++) diff |= a.charCodeAt(i) ^ b.charCodeAt(i);
  return diff === 0;
}

/* ---------------- token signing (HS256) ---------------- */

let hmacKey: CryptoKey | null = null;
let fallbackSecret: string | null = null;

export async function initSigning(): Promise<void> {
  let secret = readValue<string | null>("signingSecret", null);
  if (!secret) {
    secret = randomHex(32);
    writeValue("signingSecret", secret);
  }
  if (subtle) {
    hmacKey = await subtle.importKey(
      "raw",
      hexToBytes(secret),
      { name: "HMAC", hash: "SHA-256" },
      false,
      ["sign", "verify"],
    );
  } else {
    fallbackSecret = secret;
  }
}

async function computeSig(signingInput: string): Promise<string> {
  if (subtle && hmacKey) {
    const sig = await subtle.sign("HMAC", hmacKey, enc.encode(signingInput));
    return bytesToB64url(new Uint8Array(sig));
  }
  if (fallbackSecret) return bytesToB64url(enc.encode(fallbackKdf(signingInput, fallbackSecret, 4096)));
  throw new Error("Signing key not initialized");
}

export async function signToken(payload: TokenPayload): Promise<string> {
  const header = { alg: "HS256", typ: "RL1" };
  const signingInput = `${strToB64url(JSON.stringify(header))}.${strToB64url(JSON.stringify(payload))}`;
  const sig = await computeSig(signingInput);
  return `${signingInput}.${sig}`;
}

export async function verifyToken(token: string): Promise<TokenPayload | null> {
  const parts = token.split(".");
  if (parts.length !== 3) return null;
  try {
    const expected = await computeSig(`${parts[0]}.${parts[1]}`);
    if (!timingSafeEqual(expected, parts[2])) return null;
    const payload = JSON.parse(b64urlToStr(parts[1])) as TokenPayload;
    if (typeof payload.sub !== "string" || typeof payload.exp !== "number") return null;
    if (Date.now() > payload.exp) return null;
    return payload;
  } catch {
    return null;
  }
}
