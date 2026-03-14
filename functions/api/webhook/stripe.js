/**
 * Cloudflare Pages Function: POST /api/webhook/stripe
 * Handles Stripe webhook events: payment success, failure, disputes.
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

const JSON_HEADERS = { 'Content-Type': 'application/json' };

function jsonResp(data, status = 200) {
  return new Response(JSON.stringify(data), { status, headers: JSON_HEADERS });
}

async function verifyStripeSignature(payload, sigHeader, secret) {
  const parts = {};
  for (const item of sigHeader.split(',')) {
    const [key, value] = item.split('=');
    parts[key] = value;
  }

  const timestamp = parts['t'];
  const expectedSig = parts['v1'];
  if (!timestamp || !expectedSig) throw new Error('Missing signature components');

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

function deriveAddons(metadata) {
  const addons = [];
  if (metadata?.airgap === 'true') addons.push('airgap');
  if (metadata?.cloud === 'true') addons.push('cloud');
  if (parseInt(metadata?.extra_machines) > 0) addons.push('extra_machines');
  return addons;
}

async function handlePaymentSucceeded(pi, KV) {
  const piId = pi.id;

  const existing = await KV.get(`pi:${piId}`, 'text');
  if (existing) {
    return jsonResp({ received: true, license_key: existing });
  }

  const tier = pi.metadata?.tier || 'personal';
  const addons = deriveAddons(pi.metadata);
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

  if (email) {
    const userKey = `user:${email}`;
    const user = await KV.get(userKey, 'json');
    if (user) {
      user.licenses = [...(user.licenses || []), licenseKey];
      user.addons = [...new Set([...(user.addons || []), ...addons])];
      user.stripe_customer_id = pi.customer || user.stripe_customer_id;
      await KV.put(userKey, JSON.stringify(user));
    }
  }

  return jsonResp({ received: true, license_key: licenseKey });
}

async function handlePaymentFailed(pi, KV) {
  const email = pi.metadata?.email || pi.receipt_email;
  if (email) {
    const failKey = `payment_failed:${pi.id}`;
    await KV.put(failKey, JSON.stringify({
      email,
      tier: pi.metadata?.tier || 'unknown',
      amount: pi.amount,
      failure_message: pi.last_payment_error?.message || 'Unknown error',
      created_at: new Date().toISOString(),
    }), { expirationTtl: 60 * 60 * 24 * 30 });
  }
  return jsonResp({ received: true });
}

async function handleDisputeCreated(dispute, KV) {
  const disputeKey = `dispute:${dispute.id}`;
  await KV.put(disputeKey, JSON.stringify({
    id: dispute.id,
    payment_intent: dispute.payment_intent,
    amount: dispute.amount,
    reason: dispute.reason,
    status: dispute.status,
    created_at: new Date().toISOString(),
  }));
  return jsonResp({ received: true });
}

export async function onRequestPost(context) {
  const { STRIPE_WEBHOOK_SECRET, KV } = context.env;

  const rawBody = await context.request.text();
  const sigHeader = context.request.headers.get('stripe-signature');

  if (!sigHeader) {
    return jsonResp({ error: 'Missing stripe-signature' }, 400);
  }

  try {
    await verifyStripeSignature(rawBody, sigHeader, STRIPE_WEBHOOK_SECRET);
  } catch (err) {
    return jsonResp({ error: err.message }, 401);
  }

  const event = JSON.parse(rawBody);

  switch (event.type) {
    case 'payment_intent.succeeded':
      return handlePaymentSucceeded(event.data.object, KV);
    case 'payment_intent.payment_failed':
      return handlePaymentFailed(event.data.object, KV);
    case 'charge.dispute.created':
      return handleDisputeCreated(event.data.object, KV);
    default:
      return jsonResp({ received: true });
  }
}
