// Learner progress and preferences, kept in the browser's localStorage.

export interface Progress {
  completed: Record<string, number>;
  attempts: Record<string, string>;
  visited: Record<string, number>;
}

export interface KeyValueStorage {
  getItem(key: string): string | null;
  setItem(key: string, value: string): void;
  removeItem(key: string): void;
}

const KEY = 'joinery.progress.v1';
const empty = (): Progress => ({ completed: {}, attempts: {}, visited: {} });

function valid(data: unknown): data is Progress {
  if (typeof data !== 'object' || data === null) return false;
  const record = data as Record<string, unknown>;
  return ['completed', 'attempts', 'visited'].every((key) => typeof record[key] === 'object' && record[key] !== null);
}

export function createStore(storage: KeyValueStorage | null, now: () => number = Date.now) {
  let state: Progress = empty();
  const listeners = new Set<() => void>();
  try {
    const raw = storage?.getItem(KEY);
    const parsed: unknown = raw ? JSON.parse(raw) : null;
    if (valid(parsed)) state = parsed;
  } catch {
    state = empty();
  }
  const save = () => {
    try {
      storage?.setItem(KEY, JSON.stringify(state));
    } catch {
      // Storage can be full or blocked; progress then lasts for this visit only.
    }
    listeners.forEach((listener) => listener());
  };
  return {
    get: (): Progress => state,
    isComplete: (id: string): boolean => id in state.completed,
    complete(id: string): void {
      if (!(id in state.completed)) {
        state.completed[id] = now();
        save();
      }
    },
    attempt: (id: string): string | undefined => state.attempts[id],
    saveAttempt(id: string, sql: string): void {
      state.attempts[id] = sql.slice(0, 20_000);
      save();
    },
    visit(lessonId: string): void {
      state.visited[lessonId] = now();
      save();
    },
    reset(): void {
      state = empty();
      save();
    },
    exportJson: (): string => JSON.stringify({ format: 'joinery-progress', version: 1, ...state }, null, 2),
    importJson(text: string): boolean {
      try {
        const data: unknown = JSON.parse(text);
        if (!valid(data)) return false;
        state = { completed: data.completed, attempts: data.attempts, visited: data.visited };
        save();
        return true;
      } catch {
        return false;
      }
    },
    subscribe(listener: () => void): () => void {
      listeners.add(listener);
      return () => listeners.delete(listener);
    },
  };
}

export type Store = ReturnType<typeof createStore>;

function browserStorage(): KeyValueStorage | null {
  try {
    const storage = globalThis.localStorage;
    storage.setItem('joinery.probe', '1');
    storage.removeItem('joinery.probe');
    return storage;
  } catch {
    return null;
  }
}

export const store = createStore(browserStorage());

export function preference(name: string, fallback: string): string {
  try {
    return globalThis.localStorage.getItem(`joinery.pref.${name}`) ?? fallback;
  } catch {
    return fallback;
  }
}

export function setPreference(name: string, value: string): void {
  try {
    globalThis.localStorage.setItem(`joinery.pref.${name}`, value);
  } catch {
    // Preferences are a convenience only.
  }
}
