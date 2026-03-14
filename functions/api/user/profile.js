/**
 * Cloudflare Pages Function: GET /api/user/profile
 * Returns authenticated user's profile from KV with resolved license objects.
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

  const user = await KV.get(`user:${claims.email}`, 'json');
  if (!user) {
    return jsonResponse({ error: 'User not found' }, 404, origin);
  }

  const licenses = await resolveLicenses(KV, user.licenses || []);
  const usage = await KV.get(`usage:${claims.email}`, 'json') || {
    total_tokens: 0,
    total_requests: 0,
    last_active: null,
  };

  let billingUrl = null;
  if (STRIPE_SECRET_KEY && user.stripe_customer_id) {
    try {
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
      if (session.url) billingUrl = session.url;
    } catch (_) {
      // Stripe unavailable; billing_url stays null
    }
  }

  return jsonResponse({
    email: user.email,
    name: user.name,
    avatar: user.picture || null,
    created_at: user.created_at,
    licenses,
    addons: user.addons || [],
    api_key: user.api_key || null,
    billing_url: billingUrl,
    usage,
  }, 200, origin);
}

async function resolveLicenses(KV, licenseKeys) {
  if (!licenseKeys.length) return [];

  const resolved = await Promise.all(
    licenseKeys.map(async (key) => {
      const lic = await KV.get(`license:${key}`, 'json');
      if (!lic) {
        return { key, product: 'unknown', tier: 'unknown', status: 'unknown', machines: 1 };
      }
      return {
        key: lic.key,
        product: lic.tier || 'personal',
        tier: lic.tier || 'personal',
        status: lic.expires && new Date(lic.expires) < new Date() ? 'expired' : 'active',
        machines: lic.machines_allowed || 1,
        created_at: lic.created_at || null,
        addons: lic.addons || [],
      };
    })
  );

  return resolved;
}
