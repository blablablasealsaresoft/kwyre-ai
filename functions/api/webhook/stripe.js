/**
 * Cloudflare Pages Function: POST /api/webhook/stripe
 * Handles Stripe payment_intent.succeeded webhooks.
 * Verifies signature, auto-activates license, stores in KV.
 */

import { generateProvisionalKey } from '../_helpers.js';

const TIER_MACHINES = {
  personal: 1,
  professional: 3,
  airgapped: 5,
  air: 1,
  mlx: 1,
};

async function verifyStripeSignature(payload, sigHeader, secret) {
  const parts = {};
  for (const item of sigHeader.split(',')) {
    const [key, value] = item.split('=');
    parts[key] = value;
  }

  const timestamp = parts['t'];
  const expectedSig = parts['v1'];
  if (!timestamp || !expectedSig) throw new Error('Missing signature components');

  // Reject timestamps older than 5 minutes
  const age = Math.floor(Date.now() / 1000) - parseInt(timestamp, 10);
  if (age > 300) throw new Error('Webhook timestamp too old');

  const signed = `${timestamp}.${payload}`;
  const enc = new TextEncoder();
  const key = await crypto.subtle.importKey(
    'raw',
    enc.encode(secret),
    { name: 'HMAC', hash: 'SHA-256' },
    false,
    ['sign'],
  );
  const sig = await crypto.subtle.sign('HMAC', key, enc.encode(signed));
  const computed = Array.from(new Uint8Array(sig))
    .map((b) => b.toString(16).padStart(2, '0'))
    .join('');

  if (computed !== expectedSig) throw new Error('Invalid webhook signature');
}

export async function onRequestPost(context) {
  const { STRIPE_WEBHOOK_SECRET, KV } = context.env;

  const rawBody = await context.request.text();
  const sigHeader = context.request.headers.get('stripe-signature');

  if (!sigHeader) {
    return new Response(JSON.stringify({ error: 'Missing stripe-signature' }), {
      status: 400,
      headers: { 'Content-Type': 'application/json' },
    });
  }

  try {
    await verifyStripeSignature(rawBody, sigHeader, STRIPE_WEBHOOK_SECRET);
  } catch (err) {
    return new Response(JSON.stringify({ error: err.message }), {
      status: 401,
      headers: { 'Content-Type': 'application/json' },
    });
  }

  const event = JSON.parse(rawBody);

  if (event.type !== 'payment_intent.succeeded') {
    return new Response(JSON.stringify({ received: true }), {
      status: 200,
      headers: { 'Content-Type': 'application/json' },
    });
  }

  const pi = event.data.object;
  const piId = pi.id;

  // Idempotency: skip if already activated
  const existing = await KV.get(`pi:${piId}`, 'text');
  if (existing) {
    return new Response(JSON.stringify({ received: true, license_key: existing }), {
      status: 200,
      headers: { 'Content-Type': 'application/json' },
    });
  }

  const tier = pi.metadata?.tier || 'personal';
  const addons = pi.metadata?.addons ? pi.metadata.addons.split(',') : [];
  const email = pi.metadata?.email || pi.receipt_email;
  const machines = TIER_MACHINES[tier] || 1;

  const licenseKey = generateProvisionalKey(tier);
  const license = {
    key: licenseKey,
    tier,
    addons,
    email: email || null,
    payment_intent_id: piId,
    machines_allowed: machines,
    machines_used: 0,
    activated_machines: [],
    created_at: new Date().toISOString(),
    expires: null,
  };

  await KV.put(`license:${licenseKey}`, JSON.stringify(license));
  await KV.put(`pi:${piId}`, licenseKey);

  // Attach license to user if email is known
  if (email) {
    const userKey = `user:${email}`;
    const user = await KV.get(userKey, 'json');
    if (user) {
      user.licenses = [...(user.licenses || []), licenseKey];
      user.addons = [...new Set([...(user.addons || []), ...addons])];
      await KV.put(userKey, JSON.stringify(user));
    }
  }

  return new Response(JSON.stringify({ received: true, license_key: licenseKey }), {
    status: 200,
    headers: { 'Content-Type': 'application/json' },
  });
}
