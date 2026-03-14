/**
 * Cloudflare Pages Function: POST /api/create-payment-intent
 *
 * Creates a Stripe PaymentIntent for the selected tier + add-ons.
 * Accepts: { tier, addons: { airgap, cloud, extraMachines }, email }
 * Returns: { clientSecret, amount, breakdown }
 *
 * Set STRIPE_SECRET_KEY in Cloudflare Pages → Settings → Environment Variables.
 */

const BASE_PRICES = {
  personal:       29900,
  professional:   79900,
  air:            29900,
  apple_silicon:  29900,
  airgapped:     149900,
  cloud:           4900,
  cloud_pro:      14900,
  quantedge:      49900,
  labmind:        49900,
  dentai:         39900,
  codeforge:      39900,
  taxshield:      39900,
  launchpad:      29900,
  soulsync:       29900,
  nfl_playcaller: 19900,
};

const ADDON_PRICES = {
  airgap:            500000,
  cloud_monthly:       4900,
  cloud_pro_monthly:  14900,
  extra_machine:       9900,
};

const TIER_LABELS = {
  personal:       'Kwyre Personal',
  professional:   'Kwyre Professional',
  air:            'Kwyre Air',
  apple_silicon:  'Kwyre Apple Silicon',
  airgapped:      'Kwyre Air-Gapped Kit',
  cloud:          'Kwyre Cloud',
  cloud_pro:      'Kwyre Cloud Pro',
  quantedge:      'QuantEdge',
  labmind:        'LabMind',
  dentai:         'DentAI',
  codeforge:      'CodeForge',
  taxshield:      'TaxShield',
  launchpad:      'LaunchPad',
  soulsync:       'SoulSync',
  nfl_playcaller: 'NFL PlayCaller',
};

const ALLOWED_ORIGINS = [
  'https://kwyre.com',
  'https://www.kwyre.com',
  'https://mintrail.io',
  'https://www.mintrail.io',
  'https://mintrail.com',
  'https://www.mintrail.com',
  'http://localhost:8788',
  'http://localhost:3000',
];

function getCorsHeaders(request) {
  const origin = request.headers.get('Origin') || '';
  const allowed = ALLOWED_ORIGINS.includes(origin) ? origin : ALLOWED_ORIGINS[0];
  return {
    'Access-Control-Allow-Origin': allowed,
    'Access-Control-Allow-Methods': 'POST, OPTIONS',
    'Access-Control-Allow-Headers': 'Content-Type',
    'Access-Control-Max-Age': '86400',
  };
}

function json(data, status, corsHeaders) {
  return new Response(JSON.stringify(data), {
    status,
    headers: { 'Content-Type': 'application/json', ...corsHeaders },
  });
}

async function stripeRequest(path, params, secretKey) {
  const resp = await fetch('https://api.stripe.com/v1' + path, {
    method: 'POST',
    headers: {
      Authorization: `Bearer ${secretKey}`,
      'Content-Type': 'application/x-www-form-urlencoded',
    },
    body: params.toString(),
  });
  return { ok: resp.ok, status: resp.status, data: await resp.json() };
}

async function findOrCreateCustomer(email, secretKey) {
  if (!email) return null;

  const searchResp = await fetch(
    `https://api.stripe.com/v1/customers/search?query=${encodeURIComponent(`email:"${email}"`)}`,
    { headers: { Authorization: `Bearer ${secretKey}` } }
  );
  const searchData = await searchResp.json();

  if (searchData.data && searchData.data.length > 0) {
    return searchData.data[0].id;
  }

  const createParams = new URLSearchParams({ email });
  const { data } = await stripeRequest('/customers', createParams, secretKey);
  return data.id || null;
}

export async function onRequestOptions(context) {
  return new Response(null, {
    status: 204,
    headers: getCorsHeaders(context.request),
  });
}

export async function onRequestPost(context) {
  const cors = getCorsHeaders(context.request);
  const { STRIPE_SECRET_KEY } = context.env;

  if (!STRIPE_SECRET_KEY || STRIPE_SECRET_KEY.startsWith('sk_live_REPLACE')) {
    return json({ error: 'Stripe secret key not configured.' }, 503, cors);
  }

  let tier, addons, email;
  try {
    const body = await context.request.json();
    tier   = body.tier;
    addons = body.addons || {};
    email  = body.email || '';
  } catch {
    return json({ error: 'Invalid request body.' }, 400, cors);
  }

  const basePrice = BASE_PRICES[tier];
  if (basePrice === undefined) {
    return json({ error: `Unknown tier: ${tier}` }, 400, cors);
  }

  const airgap        = !!addons.airgap;
  const cloud         = !!addons.cloud;
  const extraMachines = Math.max(0, Math.min(10, parseInt(addons.extraMachines) || 0));

  let total = basePrice;
  const breakdown = [{ item: TIER_LABELS[tier], amount: basePrice }];

  if (airgap) {
    total += ADDON_PRICES.airgap;
    breakdown.push({ item: 'Air-Gapped Kit', amount: ADDON_PRICES.airgap });
  }

  if (extraMachines > 0) {
    const machineTotal = extraMachines * ADDON_PRICES.extra_machine;
    total += machineTotal;
    breakdown.push({ item: `Extra Licenses ×${extraMachines}`, amount: machineTotal });
  }

  if (total < 100) {
    return json({ error: 'Invalid total amount.' }, 400, cors);
  }

  const description = breakdown.map(b => b.item).join(' + ');

  let customerId = null;
  if (email) {
    try {
      customerId = await findOrCreateCustomer(email, STRIPE_SECRET_KEY);
    } catch {
      /* Customer lookup failed; proceed without customer */
    }
  }

  const params = new URLSearchParams({
    amount: String(total),
    currency: 'usd',
    description,
    'metadata[tier]': tier,
    'metadata[product]': 'kwyre-ai',
    'metadata[airgap]': String(airgap),
    'metadata[cloud]': String(cloud),
    'metadata[extra_machines]': String(extraMachines),
    'automatic_payment_methods[enabled]': 'true',
  });

  if (email) params.set('receipt_email', email);
  if (customerId) params.set('customer', customerId);

  const { ok, status, data } = await stripeRequest('/payment_intents', params, STRIPE_SECRET_KEY);

  if (!ok) {
    return json({ error: data.error?.message || 'Stripe error' }, status, cors);
  }

  return json({
    clientSecret: data.client_secret,
    amount: total,
    breakdown: breakdown.map(b => ({ ...b, amount: b.amount / 100 })),
  }, 200, cors);
}
