// Thin, typed wrapper around the JSON API.
import type {
  CheckResponse, DatasetDetail, DialectReference, ExplainResponse, ExploreData, Lesson, Meta, Module, RunResponse,
  StepsResponse, VisualizeResponse,
} from './types.ts';

/** True in the published preview, which replays recorded responses instead of calling a server. */
export const STATIC = typeof __STATIC__ !== 'undefined' && __STATIC__ === true;
export const STATIC_MESSAGE = 'This published copy replays results recorded from the real engine, so it can only run the SQL it was recorded with. Run Joinery yourself (docker compose up) to try your own SQL and check answers.';
export const REPOSITORY = 'https://github.com/aboualyXcode/joinery';

/** Must match joinery/snapshot.py: the canonical request string, hashed with SHA-1. */
export async function snapshotKey(path: string, body: Record<string, unknown>): Promise<string> {
  const canonical = [path, body.dataset || 'shop', body.engine || 'sqlite', body.setup || '', body.sql || '']
    .map(String).join('\n');
  const digest = await crypto.subtle.digest('SHA-1', new TextEncoder().encode(canonical));
  return [...new Uint8Array(digest)].map((byte) => byte.toString(16).padStart(2, '0')).join('');
}

export class ApiError extends Error {
  readonly status: number;

  constructor(message: string, status: number) {
    super(message);
    this.status = status;
  }
}

async function replay<T>(path: string, init?: RequestInit): Promise<T> {
  const file = init?.method === 'POST'
    ? `snapshots/post/${await snapshotKey(path, JSON.parse(String(init.body)) as Record<string, unknown>)}.json`
    : `snapshots/get/${path.replace(/^\/api\//, '')}.json`;
  let response: Response;
  try {
    response = await fetch(file);
  } catch {
    throw new ApiError(STATIC_MESSAGE, 0);
  }
  if (!response.ok) throw new ApiError(STATIC_MESSAGE, 404);
  const record = await response.json() as { status: number; body: unknown };
  if (record.status >= 400) {
    const message = (record.body as { error?: { message?: string } } | null)?.error?.message;
    throw new ApiError(message ?? STATIC_MESSAGE, record.status);
  }
  return record.body as T;
}

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  if (STATIC) return replay<T>(path, init);
  let response: Response;
  try {
    response = await fetch(path, init);
  } catch {
    throw new ApiError('Joinery could not reach its server. Check that it is running, then try again.', 0);
  }
  const body: unknown = await response.json().catch(() => null);
  if (!response.ok) {
    const message = (body as { error?: { message?: string } } | null)?.error?.message;
    throw new ApiError(message ?? `The server answered ${response.status}.`, response.status);
  }
  return body as T;
}

function post<T>(path: string, payload: unknown): Promise<T> {
  return request<T>(path, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(payload),
  });
}

const cache = new Map<string, Promise<unknown>>();

function cached<T>(path: string): Promise<T> {
  let entry = cache.get(path) as Promise<T> | undefined;
  if (!entry) {
    entry = request<T>(path);
    entry.catch(() => cache.delete(path));
    cache.set(path, entry);
  }
  return entry;
}

export interface QueryInput {
  sql: string;
  dataset: string;
  engine?: string | undefined;
}

export const api = {
  meta: () => cached<Meta>('/api/meta'),
  curriculum: () => cached<{ modules: Module[] }>('/api/curriculum'),
  lesson: (id: string) => cached<Lesson>(`/api/lessons/${encodeURIComponent(id)}`),
  dataset: (id: string) => cached<DatasetDetail>(`/api/datasets/${encodeURIComponent(id)}`),
  dialects: () => cached<DialectReference>('/api/dialects'),
  explore: () => cached<ExploreData>('/api/explore'),
  visualize: (input: QueryInput) => post<VisualizeResponse>('/api/visualize', input),
  run: (input: QueryInput) => post<RunResponse>('/api/run', input),
  steps: (input: QueryInput) => post<StepsResponse>('/api/steps', input),
  explain: (input: QueryInput & { setup?: string | null }) => post<ExplainResponse>('/api/explain', input),
  check: (exercise: string, sql: string) =>
    post<CheckResponse>(`/api/exercises/${encodeURIComponent(exercise)}/check`, { sql }),
  solution: (exercise: string) =>
    request<{ solution: string }>(`/api/exercises/${encodeURIComponent(exercise)}/solution`),
  exportUrl: (dataset: string, dialect: string) =>
    `/api/datasets/${encodeURIComponent(dataset)}/export?dialect=${encodeURIComponent(dialect)}`,
};
