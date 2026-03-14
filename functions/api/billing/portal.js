/**
 * Cloudflare Pages Function: GET /api/billing/portal
 * Creates a Stripe Customer Portal session and redirects the user.
 */

import { verifyJWT, extractBearer, jsonResponse, optionsResponse } from '../_helpers.js';

export async function onRequestOptions(context) {
  return optionsResponse(context.request.headers.get('Origin'));
}

export async function onRequestGet(context) {
  const { JWT_SECRET, KV, STRIPE_SECRET_KEY } = context.env;
  const origin = context.request.headers.get('Origin');

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

  if (!STRIPE_SECRET_KEY) {
    return jsonResponse({ error: 'Billing not configured' }, 503, origin);
  }

  const user = await KV.get(`user:${claims.email}`, 'json');
  if (!user) {
    return jsonResponse({ error: 'User not found' }, 404, origin);
  }

  if (!user.stripe_customer_id) {
    return jsonResponse({ error: 'No billing account linked. Purchase a product first.' }, 400, origin);
  }

  const returnUrl = `${new URL(context.request.url).origin}/dashboard.html`;
  const res = await fetch('https://api.stripe.com/v1/billing_portal/sessions', {
    method: 'POST',
    headers: {
      'Authorization': `Bearer ${STRIPE_SECRET_KEY}`,
      'Content-Type': 'application/x-www-form-urlencoded',
    },
    body: `customer=${encodeURIComponent(user.stripe_customer_id)}&return_url=${encodeURIComponent(returnUrl)}`,
  });

  const session = await res.json();
  if (!session.url) {
    return jsonResponse({ error: 'Failed to create billing portal session' }, 502, origin);
  }

  return Response.redirect(session.url, 302);
}
