// A tiny hyperscript helper: build DOM nodes declaratively without a framework.

export type Child = Node | string | number | false | null | undefined | Child[];
type Handler = (event: never) => void;

export interface Props {
  [attribute: string]: unknown;
  class?: string | undefined;
  on?: Record<string, Handler> | undefined;
  html?: string | undefined;
  styles?: Record<string, string> | undefined;
}

const PROPERTIES = new Set(['value', 'checked', 'selected', 'disabled', 'indeterminate']);

function apply(el: Element, props: Props | null): void {
  if (!props) return;
  for (const [key, value] of Object.entries(props)) {
    if (value === undefined || value === null) continue;
    if (key === 'on') {
      for (const [event, handler] of Object.entries(value as Record<string, Handler>)) {
        el.addEventListener(event, handler as EventListener);
      }
    } else if (key === 'html') {
      // Only ever used for Markdown that the server rendered with raw HTML disabled.
      el.innerHTML = String(value);
    } else if (key === 'styles') {
      for (const [name, style] of Object.entries(value as Record<string, string>)) {
        (el as HTMLElement).style.setProperty(name, style);
      }
    } else if (PROPERTIES.has(key)) {
      (el as unknown as Record<string, unknown>)[key] = value;
    } else if (value === false) {
      continue;
    } else if (value === true) {
      el.setAttribute(key, '');
    } else {
      el.setAttribute(key, String(value));
    }
  }
}

export function append(parent: Node, children: Child[]): void {
  for (const child of children) {
    if (child === null || child === undefined || child === false) continue;
    if (Array.isArray(child)) append(parent, child);
    else if (child instanceof Node) parent.appendChild(child);
    else parent.appendChild(document.createTextNode(String(child)));
  }
}

export function h<K extends keyof HTMLElementTagNameMap>(
  tag: K,
  props: Props | null = null,
  ...children: Child[]
): HTMLElementTagNameMap[K] {
  const el = document.createElement(tag);
  apply(el, props);
  append(el, children);
  return el;
}

const SVG_NS = 'http://www.w3.org/2000/svg';

export function s<K extends keyof SVGElementTagNameMap>(
  tag: K,
  props: Props | null = null,
  ...children: Child[]
): SVGElementTagNameMap[K] {
  const el = document.createElementNS(SVG_NS, tag);
  apply(el, props);
  append(el, children);
  return el;
}

export function mount(el: Element, ...children: Child[]): void {
  el.replaceChildren();
  append(el, children);
}

let counter = 0;
export function uid(prefix = 'j'): string {
  counter += 1;
  return `${prefix}-${counter}`;
}

export function announce(message: string): void {
  const region = document.getElementById('announcer');
  if (!region) return;
  region.textContent = '';
  window.setTimeout(() => { region.textContent = message; }, 30);
}

export function spinner(label: string): HTMLElement {
  return h('p', { class: 'loading', role: 'status' }, label);
}
