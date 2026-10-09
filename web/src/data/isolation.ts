// Concurrency scenarios for the isolation simulator. Outcomes follow
// PostgreSQL 18; the "standard" text gives what ISO SQL permits.

export type Level = 'read-uncommitted' | 'read-committed' | 'repeatable-read' | 'serializable';

export const LEVELS: { id: Level; name: string }[] = [
  { id: 'read-uncommitted', name: 'Read uncommitted' },
  { id: 'read-committed', name: 'Read committed' },
  { id: 'repeatable-read', name: 'Repeatable read' },
  { id: 'serializable', name: 'Serializable' },
];

export interface Step { tx: 'T1' | 'T2'; sql: string }
export interface Outcome { results: string[]; errors: number[]; anomaly: boolean; verdict: string }
export interface Scenario {
  id: string;
  title: string;
  summary: string;
  setup: string;
  steps: Step[];
  outcomes: Record<Level, Outcome>;
  standard: Record<Level, string>;
}

const each = (low: Outcome, high: Outcome, highFrom: Level): Record<Level, Outcome> => {
  const order = LEVELS.map((l) => l.id);
  const cut = order.indexOf(highFrom);
  return Object.fromEntries(order.map((level, i) => [level, i < cut ? low : high])) as Record<Level, Outcome>;
};

export const SCENARIOS: Scenario[] = [
  {
    id: 'dirty-read',
    title: 'Dirty read',
    summary: 'Can T2 see a change that T1 has not committed, and later rolls back?',
    setup: 'accounts: id 1 has balance 100.',
    steps: [
      { tx: 'T1', sql: 'BEGIN; UPDATE accounts SET balance = 50 WHERE id = 1;' },
      { tx: 'T2', sql: 'BEGIN; SELECT balance FROM accounts WHERE id = 1;' },
      { tx: 'T1', sql: 'ROLLBACK;' },
      { tx: 'T2', sql: 'SELECT balance FROM accounts WHERE id = 1; COMMIT;' },
    ],
    outcomes: each(
      { results: ['Updated, not committed', 'T2 reads 100', 'Rolled back', 'T2 reads 100'], errors: [], anomaly: false,
        verdict: 'PostgreSQL runs READ UNCOMMITTED as READ COMMITTED, so T2 never sees the uncommitted 50.' },
      { results: ['Updated, not committed', 'T2 reads 100', 'Rolled back', 'T2 reads 100'], errors: [], anomaly: false,
        verdict: 'T2 only ever sees committed data.' },
      'read-committed'),
    standard: {
      'read-uncommitted': 'permitted: T2 may read 50, a value that never officially existed.',
      'read-committed': 'prevented.', 'repeatable-read': 'prevented.', serializable: 'prevented.',
    },
  },
  {
    id: 'non-repeatable-read',
    title: 'Non-repeatable read',
    summary: 'Does reading the same row twice inside one transaction give the same answer?',
    setup: 'accounts: id 1 has balance 100.',
    steps: [
      { tx: 'T1', sql: 'BEGIN; SELECT balance FROM accounts WHERE id = 1;' },
      { tx: 'T2', sql: 'UPDATE accounts SET balance = 80 WHERE id = 1; -- autocommit' },
      { tx: 'T1', sql: 'SELECT balance FROM accounts WHERE id = 1;' },
      { tx: 'T1', sql: 'COMMIT;' },
    ],
    outcomes: each(
      { results: ['T1 reads 100', 'Committed', 'T1 reads 80', 'Committed'], errors: [], anomaly: true,
        verdict: 'Each statement takes a fresh snapshot, so T1 reads two different values inside one transaction.' },
      { results: ['T1 reads 100', 'Committed', 'T1 reads 100', 'Committed'], errors: [], anomaly: false,
        verdict: 'T1 keeps the snapshot taken by its first query, so both reads agree.' },
      'repeatable-read'),
    standard: {
      'read-uncommitted': 'permitted.', 'read-committed': 'permitted.', 'repeatable-read': 'prevented.',
      serializable: 'prevented.',
    },
  },
  {
    id: 'phantom-read',
    title: 'Phantom read',
    summary: 'Does re-running the same query inside one transaction return new rows?',
    setup: 'orders: 2 rows with status pending.',
    steps: [
      { tx: 'T1', sql: "BEGIN; SELECT count(*) FROM orders WHERE status = 'pending';" },
      { tx: 'T2', sql: "INSERT INTO orders (status) VALUES ('pending'); -- autocommit" },
      { tx: 'T1', sql: "SELECT count(*) FROM orders WHERE status = 'pending';" },
      { tx: 'T1', sql: 'COMMIT;' },
    ],
    outcomes: each(
      { results: ['T1 counts 2', 'Committed', 'T1 counts 3', 'Committed'], errors: [], anomaly: true,
        verdict: 'A new matching row appeared between two identical queries.' },
      { results: ['T1 counts 2', 'Committed', 'T1 counts 2', 'Committed'], errors: [], anomaly: false,
        verdict: "The standard allows phantoms at REPEATABLE READ, but PostgreSQL's snapshot also hides rows inserted later." },
      'repeatable-read'),
    standard: {
      'read-uncommitted': 'permitted.', 'read-committed': 'permitted.', 'repeatable-read': 'permitted.',
      serializable: 'prevented.',
    },
  },
  {
    id: 'lost-update',
    title: 'Lost update',
    summary: 'Two transactions read a balance, compute a new one in the application and write it back.',
    setup: 'accounts: id 1 has balance 100. T1 deposits 10, T2 withdraws 20.',
    steps: [
      { tx: 'T1', sql: 'BEGIN; SELECT balance FROM accounts WHERE id = 1;' },
      { tx: 'T2', sql: 'BEGIN; SELECT balance FROM accounts WHERE id = 1;' },
      { tx: 'T1', sql: 'UPDATE accounts SET balance = 110 WHERE id = 1; COMMIT;' },
      { tx: 'T2', sql: 'UPDATE accounts SET balance = 80 WHERE id = 1; COMMIT;' },
    ],
    outcomes: each(
      { results: ['T1 reads 100', 'T2 reads 100', 'Committed: 110', 'Committed: 80'], errors: [], anomaly: true,
        verdict: "Both commits succeed and the final balance is 80: T1's deposit is lost. Use SELECT ... FOR UPDATE, or let the database do the arithmetic: SET balance = balance - 20." },
      { results: ['T1 reads 100', 'T2 reads 100', 'Committed: 110',
        'ERROR: could not serialize access due to concurrent update'], errors: [3], anomaly: false,
        verdict: "T2's update fails. The application retries the whole transaction, reads 110 and writes 90." },
      'repeatable-read'),
    standard: {
      'read-uncommitted': 'permitted.', 'read-committed': 'permitted.', 'repeatable-read': 'prevented.',
      serializable: 'prevented.',
    },
  },
  {
    id: 'write-skew',
    title: 'Write skew',
    summary: 'The rule: at least one doctor must be on call. Two doctors each check the rule, then go off call.',
    setup: 'doctors: Alice and Bob are both on call.',
    steps: [
      { tx: 'T1', sql: 'BEGIN; SELECT count(*) FROM doctors WHERE on_call;' },
      { tx: 'T2', sql: 'BEGIN; SELECT count(*) FROM doctors WHERE on_call;' },
      { tx: 'T1', sql: "UPDATE doctors SET on_call = false WHERE name = 'Alice'; COMMIT;" },
      { tx: 'T2', sql: "UPDATE doctors SET on_call = false WHERE name = 'Bob'; COMMIT;" },
    ],
    outcomes: each(
      { results: ['T1 counts 2', 'T2 counts 2', 'Committed', 'Committed'], errors: [], anomaly: true,
        verdict: 'Each transaction saw two doctors on call and removed one. Nobody is on call now.' },
      { results: ['T1 counts 2', 'T2 counts 2', 'Committed',
        'ERROR: could not serialize access due to read/write dependencies among transactions'], errors: [3],
        anomaly: false, verdict: 'Serializable snapshot isolation detects the dangerous pattern and aborts T2, which can retry and see that Alice already left.' },
      'serializable'),
    standard: {
      'read-uncommitted': 'permitted.', 'read-committed': 'permitted.',
      'repeatable-read': 'permitted by snapshot isolation (PostgreSQL); lock-based implementations block it.',
      serializable: 'prevented.',
    },
  },
];
