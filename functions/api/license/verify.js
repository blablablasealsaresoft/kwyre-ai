/**
 * Cloudflare Pages Function: POST /api/license/verify
 * Validates a license key and returns its status.
 */

import { jsonResponse, optionsResponse } from '../_helpers.js';

export async function onRequestOptions(context) {
  return optionsResponse(context.request.headers.get('Origin'));
}

export async function onRequestPost(context) {
  const { KV } = context.env;
  const origin = context.request.headers.get('Origin');

  let licenseKey;
  try {
    const body = await context.request.json();
    licenseKey = body.license_key;
  } catch {
    return jsonResponse({ error: 'Invalid request body' }, 400, origin);
  }

  if (!licenseKey) {
    return jsonResponse({ error: 'license_key required' }, 400, origin);
  }

  const license = await KV.get(`license:${licenseKey}`, 'json');
  if (!license) {
    return jsonResponse({ valid: false, error: 'License not found' }, 404, origin);
  }

  const expired = license.expires && new Date(license.expires) < new Date();

  return jsonResponse({
    valid: !expired,
    tier: license.tier,
    machines_used: license.machines_used,
    machines_allowed: license.machines_allowed,
    addons: license.addons,
    expires: license.expires,
  }, 200, origin);
}
