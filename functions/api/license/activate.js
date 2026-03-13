/**
 * Cloudflare Pages Function: POST /api/license/activate
 * Verifies Stripe payment, generates and stores a license key.
 */

import {
  verifyJWT, extractBearer, generateLicenseKey,
  jsonResponse, optionsResponse,
} from '../_helpers.js';

const TIER_MACHINES = {
  personal: 1,
  professional: 3,
  airgapped: 5,
  air: 1,
  mlx: 1,
};

export async function onRequestOptions(context) {
  return optionsResponse(context.request.headers.get('Origin'));
}

export async function onRequestPost(context) {
  const { STRIPE_SECRET_KEY, JWT_SECRET, KV } = context.env;
  const origin = context.request.headers.get('Origin');

  // Authenticate
  const token = extractBearer(context.request);
  if (!token) {
    return jsonResponse({ error: 'Missing Authorization header' }, 401, origin);
  }

  let claims;
  try {
    claims = await verifyJWT(token, JWT_SECRET);
  } catch (err) {
    return jsonResponse({ error: err.message }, 401, origin);
  }

  // Parse body
  let paymentIntentId;
  try {
    const body = await context.request.json();
    paymentIntentId = body.payment_intent_id;
  } catch {
    return jsonResponse({ error: 'Invalid request body' }, 400, origin);
  }

  if (!paymentIntentId) {
    return jsonResponse({ error: 'payment_intent_id required' }, 400, origin);
  }

  // Verify payment with Stripe
  const piRes = await fetch(`https://api.stripe.com/v1/payment_intents/${encodeURIComponent(paymentIntentId)}`, {
    headers: { Authorization: `Bearer ${STRIPE_SECRET_KEY}` },
  });
  const pi = await piRes.json();

  if (!piRes.ok) {
    return jsonResponse({ error: 'Failed to verify payment' }, 502, origin);
  }
  if (pi.status !== 'succeeded') {
    return jsonResponse({ error: `Payment not succeeded (status: ${pi.status})` }, 400, origin);
  }

  // Prevent double-activation
  const existingLicense = await KV.get(`pi:${paymentIntentId}`, 'text');
  if (existingLicense) {
    const license = await KV.get(`license:${existingLicense}`, 'json');
    return jsonResponse({ license_key: existingLicense, ...license }, 200, origin);
  }

  const tier = pi.metadata?.tier || 'personal';
  const addons = pi.metadata?.addons ? pi.metadata.addons.split(',') : [];
  const machines = TIER_MACHINES[tier] || 1;

  const licenseKey = generateLicenseKey(tier);
  const license = {
    key: licenseKey,
    tier,
    addons,
    email: claims.email,
    payment_intent_id: paymentIntentId,
    machines_allowed: machines,
    machines_used: 0,
    activated_machines: [],
    created_at: new Date().toISOString(),
    expires: null,
  };

  // Store license + map PI to license key for idempotency
  await KV.put(`license:${licenseKey}`, JSON.stringify(license));
  await KV.put(`pi:${paymentIntentId}`, licenseKey);

  // Append to user's license list
  const userKey = `user:${claims.email}`;
  const user = await KV.get(userKey, 'json');
  if (user) {
    user.licenses = [...(user.licenses || []), licenseKey];
    user.addons = [...new Set([...(user.addons || []), ...addons])];
    await KV.put(userKey, JSON.stringify(user));
  }

  return jsonResponse({
    license_key: licenseKey,
    tier,
    addons,
    machines: machines,
    downloads: tier === 'airgapped' ? 'unlimited-offline' : 'online',
  }, 201, origin);
}
