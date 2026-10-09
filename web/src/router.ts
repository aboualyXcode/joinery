// Hash-based routing: works from any static host and needs no server rules.

export interface Route {
  path: string[];
  params: URLSearchParams;
}

export function parseHash(hash: string): Route {
  if (!hash.startsWith('#/')) return { path: [], params: new URLSearchParams() };
  const [rawPath = '', query = ''] = hash.slice(2).split('?', 2);
  const path = rawPath.split('/').filter(Boolean).map((part) => decodeURIComponent(part));
  return { path, params: new URLSearchParams(query) };
}

export function href(path: string, params: Record<string, string | undefined> = {}): string {
  const query = new URLSearchParams();
  for (const [key, value] of Object.entries(params)) {
    if (value !== undefined && value !== '') query.set(key, value);
  }
  const text = query.toString();
  return `#/${path.replace(/^\/+/, '')}${text ? `?${text}` : ''}`;
}
