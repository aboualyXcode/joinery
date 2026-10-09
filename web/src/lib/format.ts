// Formatting helpers for result cells and figures.
import type { Cell } from '../types.ts';

export function formatNumber(value: number): string {
  return value.toLocaleString('en-US', { maximumFractionDigits: 6 });
}

export function plural(count: number, word: string, pluralWord = `${word}s`): string {
  return `${formatNumber(count)} ${count === 1 ? word : pluralWord}`;
}

export function formatMs(ms: number | null | undefined): string {
  if (ms === null || ms === undefined) return '';
  if (ms < 1) return `${ms.toFixed(2)} ms`;
  if (ms < 100) return `${ms.toFixed(1)} ms`;
  return `${Math.round(ms)} ms`;
}

export function formatSteps(steps: number | null | undefined): string {
  if (steps === null || steps === undefined) return '';
  return steps < 100 ? 'under 100 VM steps' : `${formatNumber(steps)} VM steps`;
}

export interface CellView {
  text: string;
  kind: 'null' | 'number' | 'blob' | 'text' | 'boolean';
}

export function formatCell(value: Cell): CellView {
  if (value === null) return { text: 'NULL', kind: 'null' };
  if (typeof value === 'number') return { text: String(value), kind: 'number' };
  if (typeof value === 'boolean') return { text: value ? 'true' : 'false', kind: 'boolean' };
  if (typeof value === 'object') return { text: `x'${value.blob}${value.bytes > 32 ? '…' : ''}' (${value.bytes} bytes)`, kind: 'blob' };
  return { text: value, kind: 'text' };
}

/** A column is numeric when every non-NULL value in it is a number. */
export function numericColumns(rows: Cell[][], width: number): boolean[] {
  return Array.from({ length: width }, (_, index) => {
    let seen = false;
    for (const row of rows) {
      const value = row[index];
      if (value === null || value === undefined) continue;
      if (typeof value !== 'number') return false;
      seen = true;
    }
    return seen;
  });
}

export const DIALECT_NAMES: Record<string, string> = {
  sqlite: 'SQLite',
  postgres: 'PostgreSQL',
  mysql: 'MySQL',
  mssql: 'SQL Server',
  duckdb: 'DuckDB',
};
