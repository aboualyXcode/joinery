// Shapes of the JSON returned by the Joinery API.

export type Cell = string | number | boolean | null | { blob: string; bytes: number };

export interface Explanation {
  title: string;
  detail: string;
  hint: string;
  suggestions: string[];
  position: { start: number; end: number } | null;
}

export interface EngineError {
  type: string;
  message: string;
  code: string | null;
  explanation?: Explanation | null;
  statement_index?: number;
}

export interface StatementResult {
  index: number;
  sql: string;
  kind: 'rows' | 'command';
  columns: string[];
  rows: Cell[][];
  row_count: number;
  row_count_capped: boolean;
  truncated: boolean;
  changes: number;
  elapsed_ms: number;
  vm_steps: number | null;
  error: EngineError | null;
}

export interface Finding {
  rule: string;
  severity: 'warning' | 'info';
  message: string;
  start: number | null;
  end: number | null;
}

export interface RunResponse {
  engine: string;
  engine_version: string | null;
  dataset: string;
  statements: StatementResult[];
  skipped: number;
  error: EngineError | null;
  warnings: Finding[];
  elapsed_ms: number;
}

export interface PlanNode {
  id: number;
  label: string;
  kind: string;
  table: string | null;
  index: string | null;
  severity: 'good' | 'info' | 'warn';
  note: string;
  metrics: Record<string, number>;
  children: PlanNode[];
}

export interface Advice {
  severity: 'warn' | 'info';
  message: string;
}

export interface Instruction {
  addr: number;
  opcode: string;
  p1: Cell;
  p2: Cell;
  p3: Cell;
  p4: Cell;
  p5: Cell;
  comment: Cell;
  note: string;
  loop_to: number | null;
}

export interface ExplainResponse {
  engine: string;
  statement: string;
  tree: PlanNode[];
  advice: Advice[];
  plan_text: string | null;
  bytecode: Instruction[];
  bytecode_summary: { instructions: number; loops: number; common: [string, number][] } | null;
  metrics: { row_count: number; elapsed_ms: number; vm_steps: number | null; changes: number } | null;
  error: EngineError | null;
  setup_error: EngineError | null;
}

export interface Stage {
  id: string;
  clause: string;
  title: string;
  sql: string;
  columns: string[];
  rows: Cell[][];
  row_count: number;
  truncated: boolean;
  kept: boolean[] | null;
  kept_count: number | null;
  input_count: number | null;
  description: string;
  error: EngineError | null;
}

export interface StepsResponse {
  supported: boolean;
  reason: string | null;
  statement: string;
  stages: Stage[];
  written_order?: string[];
  logical_order?: string[];
  error?: EngineError | null;
}

export interface Preview {
  columns: string[];
  rows: Cell[][];
  row_count: number;
}

export interface CheckResponse {
  exercise: string;
  passed: boolean;
  summary: string;
  details: string[];
  hint: string | null;
  expected: Preview;
  actual: Preview | null;
  warnings: Finding[];
  error: EngineError | null;
}

export interface EngineInfo {
  id: string;
  name: string;
  dialect: string;
  version: string;
  experimental: boolean;
  available: boolean;
}

export interface DatasetSummary {
  id: string;
  title: string;
  summary: string;
  tables: number;
  rows: number;
}

export interface Meta {
  version: string;
  engines: EngineInfo[];
  datasets: DatasetSummary[];
  limits: { timeout_ms: number; max_rows: number; max_sql_chars: number };
}

export interface LessonSummary {
  id: string;
  number: string;
  title: string;
  level: string;
  minutes: number;
  summary: string;
  exercises: string[];
}

export interface Module {
  id: string;
  number: number;
  title: string;
  summary: string;
  lessons: LessonSummary[];
}

export interface Example {
  id: string;
  title: string;
  dataset: string;
  sql: string;
  variants: Record<string, string>;
  portable: boolean;
  note_html: string;
  mode: 'run' | 'steps' | 'plan';
  setup: string | null;
}

export interface Section {
  title: string;
  html: string;
  examples: Example[];
  widget: { type: string } | null;
}

export interface Exercise {
  id: string;
  title: string;
  prompt_html: string;
  dataset: string;
  starter: string;
  mode: string;
  order_matters: boolean;
  plan_check: boolean;
  hints: string[];
}

export interface Lesson {
  id: string;
  number: string;
  title: string;
  module: string;
  level: string;
  minutes: number;
  dataset: string;
  summary: string;
  objectives: string[];
  sections: Section[];
  exercises: Exercise[];
  dialect_notes: Record<string, string>;
  references: { title: string; url: string }[];
  previous: string | null;
  next: string | null;
}

export interface Column {
  name: string;
  type: string;
  nullable: boolean;
  primary_key: boolean;
  unique: boolean;
  references: string | null;
  doc: string;
}

export interface TableSchema {
  name: string;
  doc: string;
  row_count: number;
  position: [number, number];
  columns: Column[];
  indexes: { name: string; columns: string[]; unique: boolean }[];
}

export interface DatasetDetail {
  id: string;
  title: string;
  summary: string;
  description_html: string;
  tables: TableSchema[];
  dialects: string[];
}

export interface FeatureSupport {
  level: 'yes' | 'partial' | 'no';
  note?: string;
  note_html?: string;
}

export interface DialectReference {
  engines: { id: string; name: string; release: string; status: string; driver: string; docs: string }[];
  standard: string;
  features: { id: string; name: string; standard: string; support: Record<string, FeatureSupport> }[];
}
