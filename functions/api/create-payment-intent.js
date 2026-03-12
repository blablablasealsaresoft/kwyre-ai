/**
 * Cloudflare Pages Function: POST /api/create-payment-intent
 *
 * Creates a Stripe PaymentIntent for the selected tier.
 * Set STRIPE_SECRET_KEY in Cloudflare Pages → Settings → Environment Variables.
 */

const TIER_CONFIG = {
  personal:     { amount: 49900,  description: 'Kwyre Personal — 1 machine license' },
  professional: { amount: 149900, description: 'Kwyre Professional — 3 machine licenses' },
  airgapped:    { amount: 349900, description: 'Kwyre Air-Gapped Kit — 5 machine licenses' },
  air:          { amount: 34900,  description: 'Kwyre Air (CPU) — 1 machine license' },
  mlx:          { amount: 29900,  description: 'Kwyre Apple Silicon — 1 machine license' },
};

const CORS_HEADERS = {
  'Access-Control-Allow-Origin': 'https://kwyre.com',
  'Access-Control-Allow-Methods': 'POST, OPTIONS',
  'Access-Control-Allow-Headers': 'Content-Type',
  'Access-Control-Max-Age': '86400',
};

function json(data, status = 200) {
  return new Response(JSON.stringify(data), {
    status,
    headers: { 'Content-Type': 'application/json', ...CORS_HEADERS },
  });
}

export async function onRequestOptions() {
  return new Response(null, { status: 204, headers: CORS_HEADERS });
}

export async function onRequestPost(context) {
  const { STRIPE_SECRET_KEY } = context.env;

  if (!STRIPE_SECRET_KEY || STRIPE_SECRET_KEY.startsWith('sk_live_REPLACE')) {
    return json({ error: 'Stripe secret key not configured. Set STRIPE_SECRET_KEY in Cloudflare Pages environment variables.' }, 503);
  }

  let tier;
  try {
    const body = await context.request.json();
    tier = body.tier;
  } catch {
    return json({ error: 'Invalid request body' }, 400);
  }

  const tierConfig = TIER_CONFIG[tier];
  if (!tierConfig) {
    return json({ error: `Unknown tier: ${tier}` }, 400);
  }

  const params = new URLSearchParams({
    amount: String(tierConfig.amount),
    currency: 'usd',
    description: tierConfig.description,
    'metadata[tier]': tier,
    'metadata[product]': 'kwyre-ai',
    'automatic_payment_methods[enabled]': 'true',
  });

  const resp = await fetch('https://api.stripe.com/v1/payment_intents', {
    method: 'POST',
    headers: {
      Authorization: `Bearer ${STRIPE_SECRET_KEY}`,
      'Content-Type': 'application/x-www-form-urlencoded',
    },
    body: params.toString(),
  });

  const data = await resp.json();

  if (!resp.ok) {
    return json({ error: data.error?.message || 'Stripe error' }, resp.status);
  }

  return json({ client_secret: data.client_secret });
}
