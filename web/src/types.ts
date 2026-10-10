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
  vm_steps?: number | null;
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
  static?: boolean;
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
  widget: { type: string; flow?: string; symptom?: string; failure?: string; preset?: string } | null;
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

export interface Station {
  id: string;
  name: string;
  layer: 'client' | 'compiler' | 'execution' | 'storage' | 'guard';
  x: number;
  y: number;
  does: string;
  inside: string[];
  sqlite: string;
}

export interface MapEdge { from: string; to: string; bend: [number, number] | null }
export interface FlowStep { at: string; from?: string; caption: string }
export interface Flow { id: string; title: string; steps: FlowStep[] }
export interface CompareSide { sql: string; setup?: string; label?: string }

export interface Failure {
  id: string;
  title: string;
  kind: 'error' | 'hang' | 'slow' | 'wrong';
  origin: string;
  path: string[];
  knock?: [string, string][];
  tell: string;
  sees: string;
  cause: string;
  fix: string;
  patterns?: string[];
  messages?: Record<string, string>;
  demo?: { dataset: string; sql: string };
  compare?: { dataset: string; slow: CompareSide; fast: CompareSide };
}

export interface Symptom { id: string; title: string; failures: string[] }
export interface QueryPreset { id: string; title: string; dataset: string; sql: string }

export interface ExploreData {
  stations: Station[];
  edges: MapEdge[];
  flows: Flow[];
  failures: Failure[];
  symptoms: Symptom[];
  queries: QueryPreset[];
  presets: {
    journey: string;
    processing: [string, string, number][];
    playground: Record<string, string>;
    join_lab: { players: string; teams: string; sql: Record<string, string>; notes: Record<string, string> };
    index_lab: { title: string; table: string; columns: string[]; sql: string }[];
  };
}

export interface DepNode {
  id: string;
  kind: 'table' | 'cte' | 'subquery' | 'function' | 'missing' | 'query';
  label: string;
  rows?: number | null;
  work?: number | null;
  sql?: string;
  role?: string;
  correlated?: boolean;
  recursive?: boolean;
  status: 'ok' | 'error' | 'blocked' | 'failed';
  error?: EngineError;
  message?: string;
  blocked_by?: string[];
}

export interface DepEdge { from: string; to: string; kind: string; broken?: boolean }

export interface Dependencies {
  supported: boolean;
  reason?: string;
  statement?: string;
  nodes?: DepNode[];
  edges?: DepEdge[];
}

export interface VisualizeResponse {
  engine: string;
  dataset: string;
  statement: string;
  dependencies: Dependencies;
  steps: StepsResponse;
  plan: ExplainResponse;
}
