// The Explore data (engine map, flows, failures, presets), loaded once at startup.
import type { ExploreData, Failure, Station } from '../types.ts';

let data: ExploreData | null = null;
let compiled: { failure: Failure; patterns: RegExp[] }[] = [];

export function setExplore(value: ExploreData): void {
  data = value;
  compiled = value.failures.map((failure) => ({
    failure, patterns: (failure.patterns ?? []).map((pattern) => new RegExp(pattern, 'i')),
  }));
}

export function hasExplore(): boolean {
  return data !== null;
}

export function exploreData(): ExploreData {
  if (!data) throw new Error('The Explore data has not loaded.');
  return data;
}

/** The first failure whose patterns match an engine message, as the server's matcher does. */
export function matchFailure(message: string): Failure | null {
  for (const entry of compiled) {
    if (entry.patterns.some((pattern) => pattern.test(message))) return entry.failure;
  }
  return null;
}

export function failureById(id: string): Failure | undefined {
  return data?.failures.find((failure) => failure.id === id);
}

export function stationById(id: string): Station | undefined {
  return data?.stations.find((station) => station.id === id);
}

export const KIND_NAMES: Record<string, string> = {
  error: 'Error', hang: 'Hang or timeout', slow: 'Slow', wrong: 'Wrong result',
};
