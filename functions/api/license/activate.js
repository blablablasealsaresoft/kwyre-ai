/**
 * Cloudflare Pages Function: POST /api/license/activate
 * Verifies Stripe payment, generates and stores a license key.
 */

import {
  verifyJWT, extractBearer,
  jsonResponse, optionsResponse,
} from '../_helpers.js';

const KEY_PREFIXES = {
  personal: 'KWYRE-PER', professional: 'KWYRE-PRO', air: 'KWYRE-AIR', apple_silicon: 'KWYRE-MAC',
  quantedge: 'QEDGE', labmind: 'LMIND', dentai: 'DENTAI', codeforge: 'CFRGE',
  taxshield: 'TSHLD', launchpad: 'LNCHP', soulsync: 'SSYNC', nfl_playcaller: 'NFLPC',
};

const DOWNLOAD_URLS = {
  personal: { base: 'https://cdn.kwyre.com/releases/kwyre-latest', addon: null },
  professional: { base: 'https://cdn.kwyre.com/releases/kwyre-latest', addon: null },
  air: { base: 'https://cdn.kwyre.com/releases/kwyre-air-latest', addon: null },
  apple_silicon: { base: 'https://cdn.kwyre.com/releases/kwyre-mlx-latest', addon: null },
  quantedge: { base: 'https://cdn.kwyre.com/releases/kwyre-latest', addon: 'https://cdn.kwyre.com/products/quantedge-addon-latest.zip' },
  labmind: { base: 'https://cdn.kwyre.com/releases/kwyre-latest', addon: 'https://cdn.kwyre.com/products/labmind-addon-latest.zip' },
  dentai: { base: 'https://cdn.kwyre.com/releases/kwyre-latest', addon: 'https://cdn.kwyre.com/products/dentai-addon-latest.zip' },
  codeforge: { base: 'https://cdn.kwyre.com/releases/kwyre-latest', addon: 'https://cdn.kwyre.com/products/codeforge-addon-latest.zip' },
  taxshield: { base: 'https://cdn.kwyre.com/releases/kwyre-latest', addon: 'https://cdn.kwyre.com/products/taxshield-addon-latest.zip' },
  launchpad: { base: 'https://cdn.kwyre.com/releases/kwyre-latest', addon: 'https://cdn.kwyre.com/products/launchpad-addon-latest.zip' },
  soulsync: { base: 'https://cdn.kwyre.com/releases/kwyre-latest', addon: 'https://cdn.kwyre.com/products/soulsync-addon-latest.zip' },
  nfl_playcaller: { base: 'https://cdn.kwyre.com/releases/kwyre-latest', addon: 'https://cdn.kwyre.com/products/nfl-playcaller-addon-latest.zip' },
};

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

  const prefix = KEY_PREFIXES[tier] || 'KWYRE';
  const licenseKey = `${prefix}-${crypto.randomUUID().split('-').slice(0, 3).join('-').toUpperCase()}`;
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

  const downloads = DOWNLOAD_URLS[tier] || DOWNLOAD_URLS.personal;

  return jsonResponse({
    license_key: licenseKey,
    tier,
    addons,
    machines: machines,
    downloads,
  }, 201, origin);
}
