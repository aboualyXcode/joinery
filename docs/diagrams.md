# Diagrams

The engine map, the flows, the failure map and the query-map presets are data in [`content/explore.yaml`](../content/explore.yaml). The loader rejects anything that would draw wrong, so a mistake shows up when the server starts or in the tests, not in the browser.

## Components and connections

A station has an `id`, a `name`, a `layer` (`client`, `compiler`, `execution`, `storage` or `guard`), a centre `x` and `y` on a 1060 by 530 canvas, a one-line `does`, a short `inside` list and a `sqlite` note. Stations are 160 by 44 and sit on a grid of 210 by 130.

A connection is `[a, b]`, or `{from: a, to: b, bend: [x, y]}` for a curve through a control point when a straight line would cross another station. The loader samples every connection and refuses one that passes through a station it does not connect.

## Flows

A flow is a list of steps. Each step names the station it reaches (`at`) and, when the packet travels, where it comes `from`; the two must be connected. Keep captions to one short sentence.

## Failures

```yaml
- id: check-violation
  title: Rule broken
  kind: error                  # error, hang, slow or wrong
  origin: constraints          # where it starts
  path: [constraints, executor, session, pool, app]   # to where you notice it
  knock: [[executor, memory]]  # optional knock-on effects, drawn dashed
  tell: CHECK constraint failed
  sees: An UPDATE stops part-way and changes nothing.
  cause: A value breaks a CHECK rule.
  fix: Change the value, or the rule if the rule is wrong.
  patterns: ['check constraint failed', 'violates check constraint']
  messages: {sqlite: "CHECK constraint failed: ck_order_items_quantity"}
  demo: {dataset: shop, sql: "UPDATE order_items SET quantity = 0 WHERE order_id = 1"}
```

The path starts at the origin and every hop follows a connection. Patterns are case-insensitive regular expressions shared by the server and the browser, so avoid lookbehind. The tests run every `demo` and require its message to match this failure before any other, and require every sample in `messages` to do the same, so order more specific failures first. Instead of a `demo`, slow and wrong-result failures can have a `compare` with a `slow` and a `fast` side (labelled `Wrong` and `Right` for wrong results), each with `sql` and an optional `setup`.

Add a new failure to a symptom in `symptoms` so it appears in a fan.

## Query-map presets

A query has an `id`, a `title`, a `dataset` and `sql`. Lessons show one with `widget: {type: query-map, preset: <id>}`, and the preview records each preset, so a new one appears there on the next deploy.
