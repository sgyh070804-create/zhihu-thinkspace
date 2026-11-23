import test from 'node:test';
import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import ts from 'typescript';

const compile = source => ts.transpileModule(source, { compilerOptions: { target: ts.ScriptTarget.ES2022, module: ts.ModuleKind.ESNext } }).outputText;
const scopeSource = compile(readFileSync(new URL('../src/request-scope.ts', import.meta.url), 'utf8'));
const { RequestScope } = await import('data:text/javascript;base64,' + Buffer.from(scopeSource).toString('base64'));
const setup = readFileSync(new URL('../src/App.vue', import.meta.url), 'utf8').split('<script setup lang="ts">')[1].split('</script>')[0].replace(/^import[\s\S]*?;\s*/gm, '');
function harness() {
  const requests = [], unmount = [];
  const api = (path, options = {}) => new Promise((resolve, reject) => requests.push({ path, options, resolve, reject }));
  const create = new Function('ref', 'nextTick', 'onMounted', 'onBeforeUnmount', 'api', 'ApiError', 'RequestScope', 'window', compile(setup) + '\nreturn {selectFavlist,collapseFavlist,selectTab,clearPrivateData,askQa,qaSession,qaQuestion,qaMessages,qaAsking,qaError,qaLoading,favoriteItems,selectedFavlist,error};');
  const state = create(value => ({ value }), () => Promise.resolve(), () => {}, cb => unmount.push(cb), api, Error, RequestScope, { location: { pathname: '/' } });
  return { ...state, requests, unmount: () => unmount.forEach(cb => cb()) };
}
const list = id => ({ UrlToken: id, Title: String(id) });
const flush = async () => { for (let i = 0; i < 8; i++) await Promise.resolve(); };

test('collapsing a folder cancels both requests and ignores late contents and sessions', async () => {
  const h = harness(), pending = h.selectFavlist(list(1));
  assert.equal(h.requests.length, 2);
  h.collapseFavlist();
  assert.ok(h.requests.every(r => r.options.signal.aborted));
  h.requests.find(r => r.path === '/qa/sessions').resolve({ id: 'old' });
  h.requests.find(r => r.path.includes('/contents')).resolve({ Items: [{ Title: 'old private data' }] });
  await pending; await flush();
  assert.equal(h.qaSession.value, null); assert.deepEqual(h.favoriteItems.value, []);
  assert.equal(h.requests.length, 2); assert.equal(h.qaLoading.value, false);
});

test('a late failure from the old question cannot replace the new session error or busy state', async () => {
  const h = harness();
  h.qaSession.value = { id: 'old' }; h.qaQuestion.value = 'old question';
  const old = h.askQa(), request = h.requests[0];
  h.clearPrivateData(); h.qaSession.value = { id: 'new' }; h.qaQuestion.value = 'new question';
  const current = h.askQa();
  request.reject(new Error('obsolete failure')); await old;
  assert.equal(request.options.signal.aborted, true);
  assert.equal(h.qaError.value, ''); assert.equal(h.qaAsking.value, true);
  h.requests[1].resolve({ session: { id: 'new' }, question: { id: 'q' }, answer: { id: 'a' } });
  await current; assert.equal(h.qaAsking.value, false); assert.equal(h.qaMessages.value.length, 2);
});

test('switching tabs or unmounting clears QA and rejects stale successful replies', async () => {
  for (const action of ['tab', 'unmount']) {
    const h = harness(); h.qaSession.value = { id: 'private' }; h.qaQuestion.value = 'question';
    const pending = h.askQa();
    if (action === 'tab') h.selectTab('likes'); else h.unmount();
    h.requests[0].resolve({ session: { id: 'private' }, question: { id: 'q' }, answer: { id: 'a' } });
    await pending;
    assert.equal(h.requests[0].options.signal.aborted, true);
    assert.equal(h.qaSession.value, null); assert.deepEqual(h.qaMessages.value, []);
  }
});
