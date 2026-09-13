const API_BASE = (__VERCEL_API_PROXY__
  ? "/api"
  : (import.meta.env.VITE_API_BASE ?? "http://127.0.0.1:8000"))
  .trim()
  .replace(/\/+$/, "");

function query(params = {}) {
  const search = new URLSearchParams();
  Object.entries(params).forEach(([key, value]) => {
    if (Array.isArray(value)) {
      value.forEach((item) => search.append(key, item));
    } else if (value !== undefined && value !== null && value !== "") {
      search.append(key, value);
    }
  });
  const text = search.toString();
  return text ? `?${text}` : "";
}

const pendingReads = new Map();
function request(path, options = {}) {
  if (options.method && options.method !== "GET")
    return fetchJson(path, options);
  if (pendingReads.has(path)) return pendingReads.get(path);
  const promise = fetchJson(path, options).finally(() =>
    pendingReads.delete(path),
  );
  pendingReads.set(path, promise);
  return promise;
}

async function fetchJson(path, options = {}) {
  const response = await fetch(`${API_BASE}${path}`, {
    ...(options.body
      ? { headers: { "Content-Type": "application/json" } }
      : {}),
    ...options,
  });

  if (!response.ok) {
    const detail = await response.text();
    let message = detail || `Request failed: ${response.status}`;
    try {
      const parsed = JSON.parse(detail);
      message = Array.isArray(parsed.detail)
        ? parsed.detail
            .map((item) => `${item.loc?.at(-1) ?? "Input"}: ${item.msg}`)
            .join("; ")
        : parsed.detail || message;
    } catch {
      // Keep the raw response text when the API did not return JSON.
    }
    throw new Error(message);
  }

  return response.json();
}

export const api = {
  base: API_BASE,
  options: () => request("/options"),
  overview: (filters) => request(`/market/overview${query(filters)}`),
  areas: (filters) => request(`/market/areas${query(filters)}`),
  predictionOptions: (scopes) => request(`/prediction/options${query(scopes)}`),
  predictPrice: (payload) =>
    request("/predict/price", {
      method: "POST",
      body: JSON.stringify(payload),
    }),
  roi: (payload) =>
    request("/roi/calculate", {
      method: "POST",
      body: JSON.stringify(payload),
    }),
  opportunities: (filters) => request(`/opportunities${query(filters)}`),
  performance: () => request("/model/performance"),
};
