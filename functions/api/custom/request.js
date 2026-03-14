import { jsonResponse, optionsResponse } from '../_helpers.js';

export async function onRequestPost(context) {
  const { request, env } = context;
  const origin = request.headers.get('Origin');

  try {
    const body = await request.json();
    const { industry, email, company, useCase, budget, timeline } = body;

    if (!industry || !email) {
      return jsonResponse({ error: 'Industry and email are required' }, 400, origin);
    }

    const requestId = crypto.randomUUID();
    const record = {
      id: requestId,
      industry,
      email,
      company: company || '',
      useCase: useCase || '',
      budget: budget || '',
      timeline: timeline || '',
      created_at: new Date().toISOString(),
      status: 'pending',
    };

    if (env.KV) {
      await env.KV.put(`custom_request:${requestId}`, JSON.stringify(record));
    }

    return jsonResponse({ success: true, requestId }, 200, origin);
  } catch (err) {
    return jsonResponse({ error: 'Invalid request' }, 400, origin);
  }
}

export async function onRequestOptions(context) {
  return optionsResponse(context.request.headers.get('Origin'));
}
