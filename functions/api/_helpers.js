/**
 * Shared utilities for Kwyre Cloudflare Pages Functions.
 * Uses Web Crypto API (no Node.js dependencies).
 */

const ALLOWED_ORIGINS = [
  'https://kwyre.com',
  'https://www.kwyre.com',
];

export function corsHeaders(origin) {
  const allowed = ALLOWED_ORIGINS.includes(origin) ? origin : ALLOWED_ORIGINS[0];
  return {
    'Access-Control-Allow-Origin': allowed,
    'Access-Control-Allow-Methods': 'GET, POST, OPTIONS',
    'Access-Control-Allow-Headers': 'Content-Type, Authorization',
    'Access-Control-Max-Age': '86400',
  };
}

export function jsonResponse(data, status = 200, origin) {
  return new Response(JSON.stringify(data), {
    status,
    headers: { 'Content-Type': 'application/json', ...corsHeaders(origin) },
  });
}

export function optionsResponse(origin) {
  return new Response(null, { status: 204, headers: corsHeaders(origin) });
}

// --- JWT (HMAC-SHA256 via Web Crypto) ---

function base64UrlEncode(data) {
  const str = typeof data === 'string' ? data : new TextDecoder().decode(data);
  return btoa(str).replace(/\+/g, '-').replace(/\//g, '_').replace(/=+$/, '');
}

function base64UrlDecode(str) {
  const padded = str.replace(/-/g, '+').replace(/_/g, '/');
  const binary = atob(padded);
  return Uint8Array.from(binary, (c) => c.charCodeAt(0));
}

async function hmacKey(secret) {
  const enc = new TextEncoder();
  return crypto.subtle.importKey(
    'raw',
    enc.encode(secret),
    { name: 'HMAC', hash: 'SHA-256' },
    false,
    ['sign', 'verify'],
  );
}

export async function generateJWT(payload, secret, expiresInSec = 86400) {
  const header = { alg: 'HS256', typ: 'JWT' };
  const now = Math.floor(Date.now() / 1000);
  const claims = { ...payload, iat: now, exp: now + expiresInSec };

  const enc = new TextEncoder();
  const segments = base64UrlEncode(JSON.stringify(header)) + '.' + base64UrlEncode(JSON.stringify(claims));
  const key = await hmacKey(secret);
  const sig = await crypto.subtle.sign('HMAC', key, enc.encode(segments));
  return segments + '.' + base64UrlEncodeBytes(sig);
}

function base64UrlEncodeBytes(buf) {
  const bytes = new Uint8Array(buf);
  let binary = '';
  for (const b of bytes) binary += String.fromCharCode(b);
  return btoa(binary).replace(/\+/g, '-').replace(/\//g, '_').replace(/=+$/, '');
}

export async function verifyJWT(token, secret) {
  const parts = token.split('.');
  if (parts.length !== 3) throw new Error('Malformed JWT');

  const enc = new TextEncoder();
  const key = await hmacKey(secret);
  const valid = await crypto.subtle.verify(
    'HMAC',
    key,
    base64UrlDecode(parts[2]),
    enc.encode(parts[0] + '.' + parts[1]),
  );
  if (!valid) throw new Error('Invalid JWT signature');

  const payload = JSON.parse(new TextDecoder().decode(base64UrlDecode(parts[1])));
  if (payload.exp && payload.exp < Math.floor(Date.now() / 1000)) {
    throw new Error('JWT expired');
  }
  return payload;
}

// --- License Key ---

export function generateLicenseKey(tier) {
  const prefix = tier.toUpperCase().slice(0, 4);
  const segments = Array.from({ length: 4 }, () =>
    crypto.getRandomValues(new Uint8Array(2))
      .reduce((s, b) => s + b.toString(16).padStart(2, '0'), ''),
  );
  return `KWYRE-${prefix}-${segments.join('-')}`;
}

// --- Auth helpers ---

export function extractBearer(request) {
  const auth = request.headers.get('Authorization') || '';
  if (!auth.startsWith('Bearer ')) return null;
  return auth.slice(7);
}
