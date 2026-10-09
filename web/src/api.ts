// Thin, typed wrapper around the JSON API.
import type {
  CheckResponse, DatasetDetail, DialectReference, ExplainResponse, Lesson, Meta, Module, RunResponse,
  StepsResponse,
} from './types.ts';

export class ApiError extends Error {
  readonly status: number;

  constructor(message: string, status: number) {
    super(message);
    this.status = status;
  }
}

async function request<T>(path: string, init?: RequestInit): Promise<T> {
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
