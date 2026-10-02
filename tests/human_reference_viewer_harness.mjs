// Source-level handler harness. No browser, HTML engine, network or URL navigation.
import fs from 'node:fs';
import vm from 'node:vm';
import {fileURLToPath} from 'node:url';

const request = JSON.parse(fs.readFileSync(0, 'utf8'));
const html = fs.readFileSync(fileURLToPath(new URL('../scripts/human_reference_viewer.html', import.meta.url)), 'utf8');
const scripts = [...html.matchAll(/<script>([\s\S]*?)<\/script>/g)];
if (scripts.length !== 1) throw Error('Expected exactly one template script');
const elements = new Map(), created = [], anchors = [], blobs = [], revoked = [], timers = [];
class Element {
  constructor(tag, id = '') {
    Object.assign(this, {tag, id, value: '', checked: false, textContent: '', style: {},
      children: [], listeners: {}, className: '', rect: {left: 50, top: 75, width: 300, height: 200}});
  }
  append(child) {child.parent = this; this.children.push(child);}
  remove() {this.removed = true; this.parent.children = this.parent.children.filter(c => c !== this);}
  addEventListener(name, fn) {(this.listeners[name] ??= []).push(fn);}
  fire(name, event = {}) {
    for (const fn of this.listeners[name] ?? []) fn(event);
    this['on' + name]?.(event);
  }
  click() {
    if (this.tag === 'a') anchors.push({href: this.href, filename: this.download});
    this.fire('click');
  }
  getBoundingClientRect() {return this.rect;}
  setPointerCapture(pointerId) {this.capturedPointer = pointerId;}
}
// Read real template IDs/tags, but do not pretend to parse/render HTML or implement browser events.
for (const match of html.matchAll(/<([a-z][a-z0-9]*)\b[^>]*\bid="([^"]+)"[^>]*>/g)) {
  elements.set(match[2], new Element(match[1], match[2]));
}
function element(id) {
  if (!elements.has(id)) throw Error('Unknown template element: ' + id);
  return elements.get(id);
}
const document = {
  getElementById: element,
  createElement(tag) {const el = new Element(tag); created.push(el); return el;},
  querySelectorAll(selector) {
    if (selector === 'select,input,textarea') return [...elements.values()].filter(e => ['select', 'input', 'textarea'].includes(e.tag));
    if (selector === '.box') return created.filter(e => !e.removed && e.className === 'box');
    throw Error('Unsupported selector: ' + selector);
  }
};
const window = new Element('window');
// Advance a fixed clock per constructor call; timing/real event scheduling are not under test.
let tick = Date.parse('2026-09-28T00:00:00Z');
class TestDate extends Date {constructor(...args) {super(...(args.length ? args : [tick++]));}}
const context = vm.createContext({document, window, Date: TestDate, structuredClone, Blob,
  URL: {
    createObjectURL(blob) {blobs.push(blob); return 'mock-object-' + blobs.length;},
    revokeObjectURL(token) {revoked.push(token);}
  },
  setTimeout(callback) {timers.push(callback);}
});
const script = scripts[0][1].replace('/*PAYLOAD*/', JSON.stringify(request.payload).replaceAll('<', '\\u003c'));
vm.runInContext(script, context, {filename: 'human_reference_viewer.template.js', timeout: 1000});
function snapshot(name, unload = null) {
  return {name, status: element('status').textContent, progress: element('progress').textContent,
    fields: Object.fromEntries([...elements.values()].filter(e => ['input', 'textarea', 'select'].includes(e.tag)).map(e => [e.id, e.value])),
    no_visible_change: element('no_visible_change').checked,
    regions: JSON.parse(element('regions').textContent),
    boxes: document.querySelectorAll('.box').map(e => ({side: e.parent.id, style: {...e.style}})),
    anchors: [...anchors], blob_count: blobs.length, unload};
}
const snapshots = [snapshot('initial')];
for (const [index, action] of request.actions.entries()) {
  let unload = null;
  if (action.op === 'fill') {
    for (const [id, value] of Object.entries(action.values)) {
      const el = element(id);
      if (typeof value === 'boolean') el.checked = value;
      else el.value = value;
      el.fire(action.event ?? 'input'); // No implicit change, blur or synthetic save.
    }
  } else if (action.op === 'click') element(action.id).click();
  else if (action.op === 'pointer') {
    const el = element('image' + action.side);
    if (action.rect) el.rect = action.rect;
    el.fire(action.event, {clientX: action.x, clientY: action.y, pointerId: 1});
  } else if (action.op === 'beforeunload') {
    const event = {prevented: false, returnValue: null, preventDefault() {this.prevented = true;}};
    window.fire('beforeunload', event);
    unload = {prevented: event.prevented, returnValue: event.returnValue};
  } else throw Error('Unsupported action: ' + action.op);
  snapshots.push(snapshot(action.name ?? String(index), unload));
}
for (const callback of timers) callback();
const blobOutputs = [];
for (const blob of blobs) blobOutputs.push({type: blob.type, text: await blob.text()});
process.stdout.write(JSON.stringify({snapshots, blob_outputs: blobOutputs, revoked}));
