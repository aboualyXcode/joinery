// Entity relationship diagrams drawn from the dataset schema.
import { api } from '../api.ts';
import { h, mount, s, uid } from '../lib/dom.ts';
import { formatNumber, plural } from '../lib/format.ts';
import { highlightHTML } from '../lib/sql.ts';
import { href } from '../router.ts';
import type { DatasetDetail, TableSchema } from '../types.ts';

const WIDTH = 236;
const HEAD = 34;
const ROW = 21;

interface Box { x: number; y: number; w: number; h: number; table: TableSchema }

export function renderErd(dataset: DatasetDetail, onSelect?: (table: TableSchema) => void): HTMLElement {
  const boxes = new Map<string, Box>();
  for (const table of dataset.tables) {
    boxes.set(table.name, {
      x: table.position[0], y: table.position[1], w: WIDTH, h: HEAD + table.columns.length * ROW + 10, table,
    });
  }
  const all = [...boxes.values()];
  const width = Math.max(...all.map((b) => b.x + b.w)) + 60;
  const height = Math.max(...all.map((b) => b.y + b.h)) + 20;
  const marker = uid('erd-arrow');
  const svg = s('svg', {
    class: 'erd', viewBox: `0 0 ${width} ${height}`, role: 'group',
    'aria-label': `Tables and relationships in ${dataset.title}`,
  });
  svg.style.setProperty('--erd-width', `${width}px`);
  const links = s('g', { class: 'links' });
  const tables = s('g', { class: 'tables' });
  const paths: SVGPathElement[] = [];

  for (const table of dataset.tables) {
    const source = boxes.get(table.name);
    table.columns.forEach((column, i) => {
      if (!column.references || !source) return;
      const [refTable = '', refColumn = ''] = column.references.split('.');
      const target = boxes.get(refTable);
      if (!target) return;
      const ti = Math.max(0, target.table.columns.findIndex((c) => c.name === refColumn));
      const sy = source.y + HEAD + i * ROW + ROW / 2;
      const ty = target.y + HEAD + ti * ROW + ROW / 2;
      let d: string;
      let sx: number;
      let tx: number;
      let sOff: number;
      let tOff: number;
      if (target === source) {
        sx = tx = source.x + source.w;
        d = `M ${sx} ${sy} C ${sx + 46} ${sy}, ${sx + 46} ${ty}, ${tx} ${ty}`;
        sOff = tOff = 6;
      } else if (Math.abs(target.x - source.x) < 10) {
        sx = source.x;
        tx = target.x;
        d = `M ${sx} ${sy} C ${sx - 46} ${sy}, ${tx - 46} ${ty}, ${tx} ${ty}`;
        sOff = tOff = -14;
      } else {
        const right = target.x > source.x;
        sx = right ? source.x + source.w : source.x;
        tx = right ? target.x : target.x + target.w;
        const bend = Math.max(36, Math.abs(tx - sx) / 2);
        d = `M ${sx} ${sy} C ${sx + (right ? bend : -bend)} ${sy}, ${tx + (right ? -bend : bend)} ${ty}, ${tx} ${ty}`;
        sOff = right ? 5 : -13;
        tOff = right ? -13 : 5;
      }
      links.append(s('text', { class: 'cardinality', x: sx + sOff, y: sy - 5 }, 'N'),
        s('text', { class: 'cardinality', x: tx + tOff, y: ty - 5 }, '1'));
      const path = s('path', { d, class: 'link', 'data-from': table.name, 'data-to': refTable, 'marker-end': `url(#${marker})` },
        s('title', null, `${table.name}.${column.name} references ${column.references}`));
      paths.push(path);
      links.append(path);
    });
  }

  const focus = (name: string | null) => {
    svg.classList.toggle('focused', name !== null);
    tables.querySelectorAll<SVGGElement>('.erd-table').forEach((group) => {
      const other = group.dataset.table;
      const related = name !== null && (other === name || paths.some((p) =>
        (p.dataset.from === name && p.dataset.to === other) || (p.dataset.to === name && p.dataset.from === other)));
      group.classList.toggle('active', related);
    });
    paths.forEach((p) => p.classList.toggle('active', name !== null && (p.dataset.from === name || p.dataset.to === name)));
  };

  for (const box of all) {
    const t = box.table;
    tables.append(s('g', {
      class: 'erd-table', 'data-table': t.name, transform: `translate(${box.x} ${box.y})`, tabindex: '0', role: 'button',
      'aria-label': `${t.name}: ${t.columns.length} columns, ${formatNumber(t.row_count)} rows`,
      on: {
        mouseenter: () => focus(t.name), mouseleave: () => focus(null), focus: () => focus(t.name), blur: () => focus(null),
        click: () => onSelect?.(t),
        keydown: (event: KeyboardEvent) => {
          if (event.key === 'Enter' || event.key === ' ') {
            event.preventDefault();
            onSelect?.(t);
          }
        },
      },
    },
    s('rect', { class: 'erd-box', width: box.w, height: box.h, rx: 5 }),
    s('path', { class: 'erd-head', d: `M 0 5 Q 0 0 5 0 H ${box.w - 5} Q ${box.w} 0 ${box.w} 5 V ${HEAD} H 0 Z` }),
    s('text', { class: 'erd-name', x: 12, y: 22 }, t.name),
    s('text', { class: 'erd-count', x: box.w - 12, y: 22, 'text-anchor': 'end' }, `${formatNumber(t.row_count)} rows`),
    t.columns.map((c, i) => [
      s('text', { class: `erd-column${c.primary_key ? ' pk' : ''}${c.references ? ' fk' : ''}`, x: 12, y: HEAD + i * ROW + 15 },
        `${c.primary_key ? 'PK ' : c.references ? 'FK ' : ''}${c.name}`),
      s('text', { class: 'erd-type', x: box.w - 12, y: HEAD + i * ROW + 15, 'text-anchor': 'end' }, c.type),
    ])));
  }
  svg.append(
    s('defs', null, s('marker', {
      id: marker, viewBox: '0 0 10 10', refX: '9', refY: '5', markerWidth: '7', markerHeight: '7',
      orient: 'auto-start-reverse',
    }, s('path', { d: 'M 0 0 L 10 5 L 0 10 z', class: 'arrow' }))),
    links, tables);
  return h('div', { class: 'erd-wrap', role: 'region', tabindex: '0', 'aria-label': 'Entity relationship diagram' }, svg);
}

export function renderTableDetail(table: TableSchema, datasetId: string): HTMLElement {
  return h('section', { class: 'table-detail', 'aria-label': `The ${table.name} table` },
    h('div', { class: 'detail-head' },
      h('h3', null, table.name),
      h('a', {
        class: 'button',
        href: href('playground', { dataset: datasetId, sql: `SELECT *\nFROM ${table.name}\nLIMIT 20;` }),
      }, `Query ${table.name}`)),
    h('p', null, table.doc, ` ${formatNumber(table.row_count)} rows.`),
    h('div', { class: 'table-wrap', role: 'region', tabindex: '0', 'aria-label': `Columns of ${table.name}` },
      h('table', { class: 'data' },
        h('thead', null, h('tr', null, ['Column', 'Type', 'Key', 'Required', 'Notes'].map((c) => h('th', { scope: 'col' }, c)))),
        h('tbody', null, table.columns.map((c) => h('tr', null,
          h('td', null, h('code', null, c.name)),
          h('td', null, c.type),
          h('td', null, c.primary_key ? 'primary key' : c.references ? `references ${c.references}` : c.unique ? 'unique' : ''),
          h('td', null, c.nullable ? 'no' : 'yes'),
          h('td', null, c.doc)))))),
    table.indexes.length ? h('p', { class: 'muted' }, 'Indexes: ',
      table.indexes.map((index, i) => [i ? ', ' : '', h('code', null, `${index.name} (${index.columns.join(', ')})`)])) : null);
}

interface Hop { table: string; on: string }

function joinPath(dataset: DatasetDetail, from: string, to: string): Hop[] | null {
  const links = new Map<string, Hop[]>();
  const add = (a: string, hop: Hop) => links.set(a, [...(links.get(a) ?? []), hop]);
  for (const table of dataset.tables) {
    for (const column of table.columns) {
      if (!column.references) continue;
      const [refTable = '', refColumn = ''] = column.references.split('.');
      if (refTable === table.name) continue;
      const on = `${refTable}.${refColumn} = ${table.name}.${column.name}`;
      add(table.name, { table: refTable, on });
      add(refTable, { table: table.name, on });
    }
  }
  const previous = new Map<string, { from: string; hop: Hop }>();
  const queue = [from];
  const seen = new Set([from]);
  while (queue.length) {
    const current = queue.shift() ?? '';
    if (current === to) break;
    for (const hop of links.get(current) ?? []) {
      if (seen.has(hop.table)) continue;
      seen.add(hop.table);
      previous.set(hop.table, { from: current, hop });
      queue.push(hop.table);
    }
  }
  if (from !== to && !previous.has(to)) return null;
  const hops: Hop[] = [];
  for (let at = to; at !== from;) {
    const step = previous.get(at);
    if (!step) break;
    hops.unshift(step.hop);
    at = step.from;
  }
  return hops;
}

/** Pick two tables; the diagram highlights the foreign-key path between them and writes the joins. */
export function renderPathFinder(dataset: DatasetDetail, diagram: HTMLElement): HTMLElement {
  const names = dataset.tables.map((t) => t.name);
  const pick = (label: string, value: string) => {
    const select = h('select', { 'aria-label': label }, names.map((n) => h('option', { value: n }, n)));
    select.value = value;
    return select;
  };
  const from = pick('Join from', names[0] ?? '');
  const to = pick('Join to', names[Math.min(3, names.length - 1)] ?? '');
  const output = h('div', { class: 'path-output', 'aria-live': 'polite' });
  const find = () => {
    const svgEl = diagram.querySelector('svg.erd');
    const hops = joinPath(dataset, from.value, to.value);
    svgEl?.classList.toggle('pathing', !!hops);
    const onPath = new Set([from.value, ...(hops ?? []).map((hop) => hop.table)]);
    svgEl?.querySelectorAll<SVGGElement>('.erd-table').forEach((g) => g.classList.toggle('on-path', onPath.has(g.dataset.table ?? '')));
    const order = [from.value, ...(hops ?? []).map((hop) => hop.table)];
    svgEl?.querySelectorAll<SVGPathElement>('.link').forEach((path) => {
      const a = order.indexOf(path.dataset.from ?? '');
      const b = order.indexOf(path.dataset.to ?? '');
      path.classList.toggle('on-path', a >= 0 && b >= 0 && Math.abs(a - b) === 1);
    });
    if (!hops) {
      mount(output, h('p', { class: 'muted' }, `No chain of foreign keys connects ${from.value} and ${to.value}.`));
      return;
    }
    const sql = [`SELECT *`, `FROM ${from.value}`, ...hops.map((hop) => `JOIN ${hop.table} ON ${hop.on}`), 'LIMIT 20;'].join('\n');
    mount(output,
      h('p', { class: 'muted' }, hops.length ? `${plural(hops.length, 'join')} through ${order.join(', ')}.` : 'The same table: no join needed.'),
      h('pre', { class: 'code small' }, h('code', { html: highlightHTML(sql) })),
      h('a', { class: 'button', href: href('playground', { dataset: dataset.id, sql }) }, 'Open it in the playground'));
  };
  from.addEventListener('change', find);
  to.addEventListener('change', find);
  queueMicrotask(find);
  return h('div', { class: 'path-finder' },
    h('div', { class: 'toolbar' }, h('span', null, 'Find the join path from'), from, h('span', null, 'to'), to),
    output);
}

/** The relationship explorer used on the Explore page and as a lesson widget. */
export function renderRelationships(datasetId: string): HTMLElement {
  const holder = h('div', { class: 'relationships' }, h('p', { class: 'loading', role: 'status' }, 'Drawing the relationships\u2026'));
  api.dataset(datasetId).then((detail) => {
    const tableArea = h('div', { class: 'table-area', 'aria-live': 'polite' });
    const diagram = renderErd(detail, (table) => mount(tableArea, renderTableDetail(table, detail.id)));
    mount(holder, h('p', { class: 'muted' }, 'N marks the many side of each relationship and 1 the side it points to.'),
      diagram, renderPathFinder(detail, diagram), tableArea);
  }).catch((error: unknown) => mount(holder, h('p', { class: 'muted' }, String(error))));
  return holder;
}
