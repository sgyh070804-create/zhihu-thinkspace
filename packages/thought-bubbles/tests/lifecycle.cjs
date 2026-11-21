const test = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const vm = require('node:vm');
const physics = require('../dist/bubble-physics.js');

function setup(reduced = false) {
  let now = 0, serial = 0, disconnects = 0;
  const frames = new Map();
  class Element {
    constructor(tag) { this.tag = tag; this.children = []; this.style = {}; this.events = {}; this.classList = { add() {}, remove() {}, toggle() {} }; this.clientWidth = 900; this.clientHeight = 600; }
    appendChild(el) { this.children.push(el); el.parent = this; return el; }
    remove() { if (this.parent) this.parent.children = this.parent.children.filter(el => el !== this); }
    setAttribute() {}
    addEventListener(name, cb) { (this.events[name] ||= []).push(cb); }
    getContext() { return null; }
  }
  const context = { BubblePhysics: physics, performance: { now: () => now }, document: { hidden: false, createElement: tag => new Element(tag) },
    matchMedia: () => ({ matches: reduced }), devicePixelRatio: 1, console,
    requestAnimationFrame: cb => { frames.set(++serial, cb); return serial; }, cancelAnimationFrame: id => frames.delete(id),
    ResizeObserver: class { observe() {} disconnect() { disconnects++; } },
  };
  context.window = context;
  vm.runInNewContext(fs.readFileSync(require.resolve('../dist/thought-bubbles.js'), 'utf8'), context);
  return { create: context.ThoughtBubbles.create, host: new Element('host'), frames,
    tick() { now += 16.667; const callbacks = [...frames.values()]; frames.clear(); callbacks.forEach(cb => cb(now)); },
    disconnected: () => disconnects };
}
const items = [{ id: 'a', text: 'A', x: .2, y: .3 }, { id: 'b', text: 'B', x: .7, y: .6 }];

test('host reader receives focus and close events; hidden bubble buttons leave the tab order', () => {
  const env = setup(), events = [];
  const scene = env.create(env.host, { items, externalReader: true, onFocusChange: item => events.push(item?.id ?? null) });
  assert.equal(scene.focus('a'), true);
  const labels = env.host.children[0].children[2];
  assert.ok(labels.children.every(el => el.tabIndex === -1 && el.style.pointerEvents === 'none'));
  scene.focus('b'); scene.closeFocus();
  assert.deepEqual(events, ['a', 'b', null]);
  assert.ok(labels.children.every(el => el.tabIndex === 0));
  assert.equal(scene.focus('missing'), false);
  scene.destroy();
  assert.equal(env.frames.size, 0); assert.equal(env.disconnected(), 1); assert.equal(env.host.children.length, 0);
});

test('keyboard entry continues real-time motion and replacing items closes stale reader state', () => {
  const env = setup(), events = [];
  const scene = env.create(env.host, { items, onFocusChange: item => events.push(item?.id ?? null) });
  const button = env.host.children[0].children[2].children[0];
  button.events.keydown[0]({ key: 'Enter', preventDefault() {} });
  assert.equal(scene.getStats().focusedId, 'a');
  for (let i = 0; i < 10; i++) env.tick();
  const before = scene.getItems()[0].x;
  for (let i = 0; i < 100; i++) env.tick();
  assert.notEqual(scene.getItems()[0].x, before);
  scene.setItems([{ id: 'c', text: 'C' }]);
  assert.equal(scene.getStats().focusedId, null); assert.deepEqual(events, ['a', null]);
  scene.destroy();
});

test('reduced motion keeps autonomous positions stable', () => {
  const env = setup(true), scene = env.create(env.host, { items, externalReader: true, animateEntrance: true });
  const before = scene.getItems().map(item => [item.x, item.y]);
  for (let i = 0; i < 120; i++) env.tick();
  assert.deepEqual(scene.getItems().map(item => [item.x, item.y]), before);
  const button = env.host.children[0].children[2].children[0];
  assert.equal(button.style.opacity, 1); assert.match(button.style.transform, /scale\(1\)/);
  scene.destroy();
});

test('cancelled authoring preserves parents and clears the busy state', async () => {
  const env = setup(); let reject;
  const scene = env.create(env.host, { items, onMerge: () => new Promise((resolve, fail) => { reject = fail; }) });
  const promise = scene.merge('a', 'b');
  assert.equal(scene.getStats().busy, true);
  reject(new Error('cancelled')); await assert.rejects(promise, /cancelled/);
  assert.equal(scene.getStats().count, 2); assert.equal(scene.getStats().busy, false);
  scene.destroy();
});
