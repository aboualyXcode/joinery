// The engine map: database components as stations on a schematic. It plays
// flows (a packet travels the wires step by step) and traces failures (red
// from where they start, highlighted where they pass, ringed where you notice).
import { h, mount, s, uid } from '../lib/dom.ts';
import { failureById, KIND_NAMES } from '../lib/explore.ts';
import { href } from '../router.ts';
import type { ExploreData, Failure, Flow, MapEdge, Station } from '../types.ts';

const W = 160;
const H = 44;
const STATES = ['active', 'visited', 'origin', 'passes', 'noticed', 'selected', 'dim'];

export interface EngineMap {
  element: HTMLElement;
  clear(): void;
  select(id: string | null): void;
  flowStep(flow: Flow, index: number): void;
  trace(failure: Failure): void;
}

const pairKey = (a: string, b: string) => (a < b ? `${a}|${b}` : `${b}|${a}`);

function wirePath(edge: MapEdge, from: Station, to: Station): string {
  return edge.bend
    ? `M ${from.x} ${from.y} Q ${edge.bend[0]} ${edge.bend[1]} ${to.x} ${to.y}`
    : `M ${from.x} ${from.y} L ${to.x} ${to.y}`;
}

const reducedMotion = () => window.matchMedia('(prefers-reduced-motion: reduce)').matches;

export function createEngineMap(data: ExploreData, onSelect?: (station: Station) => void): EngineMap {
  const stations = new Map(data.stations.map((station) => [station.id, station]));
  const arrow = uid('arrow');
  const svg = s('svg', {
    class: 'engine-map', viewBox: '0 0 1060 530', role: 'group',
    'aria-label': 'Database components and how they connect',
  });
  const wires = s('g', { class: 'wires' });
  const overlay = s('g', { class: 'overlay' });
  const nodes = s('g', { class: 'stations' });
  const edges = new Map<string, { path: SVGPathElement; edge: MapEdge }>();
  for (const edge of data.edges) {
    const a = stations.get(edge.from);
    const b = stations.get(edge.to);
    if (!a || !b) continue;
    const path = s('path', { class: 'wire', d: wirePath(edge, a, b) });
    wires.append(path);
    edges.set(pairKey(edge.from, edge.to), { path, edge });
  }
  const groups = new Map<string, SVGGElement>();
  for (const station of data.stations) {
    const group = s('g', {
      class: `station layer-${station.layer}`, transform: `translate(${station.x - W / 2} ${station.y - H / 2})`,
      tabindex: '0', role: 'button', 'aria-label': `${station.name}. ${station.does}`,
      on: {
        click: () => onSelect?.(station),
        keydown: (event: KeyboardEvent) => {
          if (event.key === 'Enter' || event.key === ' ') {
            event.preventDefault();
            onSelect?.(station);
          }
        },
      },
    },
    s('rect', { class: 'station-box', width: W, height: H, rx: 6 }),
    s('rect', { class: 'station-tab', x: 0, y: 0, width: 7, height: H, rx: 3 }),
    s('text', { class: 'station-name', x: 18, y: 27 }, station.name));
    groups.set(station.id, group);
    nodes.append(group);
  }
  const packet = s('circle', { class: 'packet', r: 9, cx: -40, cy: -40 });
  const label = s('text', { class: 'noticed-label', x: -100, y: -100 });
  svg.append(
    s('defs', null, s('marker', {
      id: arrow, viewBox: '0 0 10 10', refX: '8', refY: '5', markerWidth: '6', markerHeight: '6', orient: 'auto',
    }, s('path', { d: 'M 0 0 L 10 5 L 0 10 z', class: 'trace-arrow' }))),
    wires, overlay, nodes, packet, label);
  let frame = 0;

  const clear = () => {
    cancelAnimationFrame(frame);
    groups.forEach((group) => group.classList.remove(...STATES));
    edges.forEach(({ path }) => path.classList.remove('travel'));
    overlay.replaceChildren();
    svg.classList.remove('tracing', 'playing');
    packet.setAttribute('cx', '-40');
    label.setAttribute('x', '-100');
  };

  const movePacket = (from: string, to: string) => {
    const entry = edges.get(pairKey(from, to));
    if (!entry) return;
    const length = entry.path.getTotalLength();
    const forward = entry.edge.from === from;
    const started = performance.now();
    const duration = reducedMotion() ? 0 : 650;
    cancelAnimationFrame(frame);
    const tick = (now: number) => {
      const t = duration ? Math.min(1, (now - started) / duration) : 1;
      const point = entry.path.getPointAtLength((forward ? t : 1 - t) * length);
      packet.setAttribute('cx', String(point.x));
      packet.setAttribute('cy', String(point.y));
      if (t < 1) frame = requestAnimationFrame(tick);
    };
    frame = requestAnimationFrame(tick);
  };

  const hop = (a: string, b: string, cls: string, delay: number) => {
    const entry = edges.get(pairKey(a, b));
    const from = stations.get(a);
    const to = stations.get(b);
    if (!entry || !from || !to) return;
    const path = s('path', { class: cls, d: wirePath({ ...entry.edge, from: a, to: b }, from, to), 'marker-end': `url(#${arrow})` });
    path.style.setProperty('animation-delay', `${delay}ms`);
    overlay.append(path);
  };

  return {
    element: h('div', { class: 'engine-map-wrap' }, svg),
    clear,
    select(id) {
      groups.forEach((group, key) => group.classList.toggle('selected', key === id));
    },
    flowStep(flow, index) {
      clear();
      svg.classList.add('playing');
      flow.steps.slice(0, index).forEach((step) => groups.get(step.at)?.classList.add('visited'));
      const step = flow.steps[index];
      if (!step) return;
      groups.get(step.at)?.classList.add('active');
      if (step.from) {
        edges.get(pairKey(step.from, step.at))?.path.classList.add('travel');
        movePacket(step.from, step.at);
      } else {
        const station = stations.get(step.at);
        if (station) {
          packet.setAttribute('cx', String(station.x));
          packet.setAttribute('cy', String(station.y - H / 2 - 12));
        }
      }
    },
    trace(failure) {
      clear();
      svg.classList.add('tracing');
      const onPath = new Set([...failure.path, ...(failure.knock ?? []).flat()]);
      groups.forEach((group, key) => { if (!onPath.has(key)) group.classList.add('dim'); });
      failure.path.forEach((id, i) => {
        const cls = i === 0 ? 'origin' : i === failure.path.length - 1 ? 'noticed' : 'passes';
        groups.get(id)?.classList.add(cls);
      });
      failure.path.slice(1).forEach((id, i) => hop(failure.path[i] ?? id, id, 'trace-path', i * 260));
      (failure.knock ?? []).forEach(([a, b], i) => hop(a, b, 'trace-knock', (failure.path.length + i) * 260));
      const end = stations.get(failure.path[failure.path.length - 1] ?? '');
      if (end) {
        label.textContent = failure.kind === 'slow' ? 'felt here' : 'noticed here';
        label.setAttribute('x', String(end.x - W / 2));
        label.setAttribute('y', String(end.y + H / 2 + 16));
      }
    },
  };
}

function stationDetail(data: ExploreData, station: Station): HTMLElement {
  const starts = data.failures.filter((f) => f.origin === station.id);
  const flows = data.flows.filter((f) => f.steps.some((step) => step.at === station.id));
  return h('div', { class: 'station-detail' },
    h('h3', null, station.name),
    h('p', null, station.does),
    h('ul', { class: 'inside' }, station.inside.map((item) => h('li', null, item))),
    h('p', { class: 'muted' }, h('strong', null, 'SQLite: '), station.sqlite),
    starts.length ? h('div', { class: 'chip-row' }, h('span', { class: 'chip-label' }, 'Starts here'),
      starts.map((f) => h('a', { class: `chip kind-${f.kind}`, href: href(`explore/failures/${f.id}`) }, f.title))) : null,
    flows.length ? h('div', { class: 'chip-row' }, h('span', { class: 'chip-label' }, 'Flows'),
      flows.map((f) => h('a', { class: 'chip', href: href(`explore/flows/${f.id}`) }, f.title))) : null);
}

/** The map with its flow player and station details. */
export function renderEngineExplorer(data: ExploreData, options: { flow?: string | undefined; compact?: boolean } = {}): HTMLElement {
  const panel = h('div', { class: 'map-panel', 'aria-live': 'polite' });
  const map = createEngineMap(data, (station) => {
    map.select(station.id);
    stop();
    mount(stationArea, stationDetail(data, station));
  });
  const stationArea = h('div', { class: 'station-area' },
    h('p', { class: 'muted' }, 'Select a component to see what it does and which failures start there.'));
  let flow = data.flows.find((f) => f.id === options.flow) ?? data.flows[0];
  let index = 0;
  let timer = 0;
  const caption = h('p', { class: 'flow-caption' });
  const counter = h('span', { class: 'flow-counter' });
  const dots = h('div', { class: 'flow-dots', 'aria-hidden': 'true' });
  const play = h('button', { type: 'button', class: 'button primary', on: { click: () => (timer ? stop() : start()) } }, 'Play');
  const prev = h('button', { type: 'button', class: 'button', on: { click: () => { stop(); show(index - 1); } } }, 'Back');
  const next = h('button', { type: 'button', class: 'button', on: { click: () => { stop(); show(index + 1); } } }, 'Next');
  const flowButtons = data.flows.map((f) => h('button', {
    type: 'button', 'aria-pressed': String(f === flow), on: { click: () => { flow = f; stop(); show(0); } },
  }, f.title));

  function show(i: number): void {
    if (!flow) return;
    index = Math.max(0, Math.min(flow.steps.length - 1, i));
    flowButtons.forEach((b, n) => b.setAttribute('aria-pressed', String(data.flows[n] === flow)));
    map.flowStep(flow, index);
    caption.textContent = flow.steps[index]?.caption ?? '';
    counter.textContent = `Step ${index + 1} of ${flow.steps.length}`;
    dots.replaceChildren(...flow.steps.map((_, n) => h('span', { class: n < index ? 'done' : n === index ? 'now' : undefined })));
    prev.disabled = index === 0;
    next.disabled = index === flow.steps.length - 1;
  }
  function start(): void {
    if (!flow) return;
    if (index >= flow.steps.length - 1) show(0);
    play.textContent = 'Pause';
    timer = window.setInterval(() => {
      if (!flow || index >= flow.steps.length - 1) stop();
      else show(index + 1);
    }, 1700);
  }
  function stop(): void {
    window.clearInterval(timer);
    timer = 0;
    play.textContent = 'Play';
  }

  mount(panel,
    h('div', { class: 'segmented', role: 'group', 'aria-label': 'Flow' }, flowButtons),
    counter, caption, dots,
    h('div', { class: 'toolbar' }, prev, play, next),
    stationArea);
  show(0);
  return h('div', { class: options.compact ? 'map-layout compact' : 'map-layout' },
    h('div', { class: 'map-main' }, map.element, legend()), panel);
}

export function legend(): HTMLElement {
  const layers: [string, string][] = [['client', 'Client'], ['compiler', 'Compiler'], ['execution', 'Execution'],
    ['storage', 'Storage'], ['guard', 'Guards and limits']];
  return h('ul', { class: 'map-legend', 'aria-label': 'Layers' },
    layers.map(([id, name]) => h('li', null, h('span', { class: `swatch layer-${id}` }), name)));
}

/** A row of station chips from origin to where the failure is noticed. */
export function pathChips(data: ExploreData, failure: Failure): HTMLElement {
  const names = new Map(data.stations.map((station) => [station.id, station.name]));
  return h('ol', { class: 'path-chips', 'aria-label': 'Where it starts and where it travels' },
    failure.path.map((id, i) => h('li', { class: i === 0 ? 'origin' : i === failure.path.length - 1 ? 'noticed' : undefined },
      names.get(id) ?? id)));
}

export function failureLink(id: string): HTMLElement | null {
  const failure = failureById(id);
  return failure ? h('a', { class: `chip kind-${failure.kind}`, href: href(`explore/failures/${failure.id}`) },
    `${KIND_NAMES[failure.kind] ?? ''}: ${failure.title}`) : null;
}
