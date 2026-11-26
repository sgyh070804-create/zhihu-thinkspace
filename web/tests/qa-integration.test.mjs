import test from 'node:test';
import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import ts from 'typescript';

const compile = source => ts.transpileModule(source, { compilerOptions: { target: ts.ScriptTarget.ES2022, module: ts.ModuleKind.ESNext } }).outputText;
const importSource = path => import('data:text/javascript;base64,' + Buffer.from(compile(readFileSync(new URL(path, import.meta.url), 'utf8'))).toString('base64'));
const { RequestScope } = await importSource('../src/request-scope.ts');
const { createWheelStep, wheelPixels, workspaceIndex, workspacePages } = await importSource('../src/workspace-navigation.ts');
const setup = readFileSync(new URL('../src/App.vue', import.meta.url), 'utf8').split('<script setup lang="ts">')[1].split('</script>')[0].replace(/^import[\s\S]*?;\s*/gm, '');
function harness() {
  const requests = [], unmount = [];
  const api = (path, options = {}) => new Promise((resolve, reject) => requests.push({ path, options, resolve, reject }));
  const create = new Function('ref', 'computed', 'nextTick', 'onMounted', 'onBeforeUnmount', 'api', 'ApiError', 'RequestScope', 'window', 'document', 'createWheelStep', 'wheelPixels', 'workspaceIndex', 'workspacePages', compile(setup) + '\nreturn {selectFavlist,collapseFavlist,selectTab,clearPrivateData,askQa,qaSession,qaQuestion,qaMessages,qaAsking,qaError,qaLoading,favoriteItems,selectedFavlist,selectedArticle,bubbles,articles,openShelfBook,loadActive,status,shelfBooks,error};');
  const window = Object.assign(new EventTarget(), { location: new URL('http://localhost/library'), history: { replaceState() {} } });
  const state = create(value => ({ value }), getter => ({ get value() { return getter(); } }), () => Promise.resolve(), () => {}, cb => unmount.push(cb), api, Error, RequestScope, window, new EventTarget(), createWheelStep, wheelPixels, workspaceIndex, workspacePages);
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

test('one trackpad gesture cannot skip the middle workspace page', () => {
  const step = createWheelStep();
  assert.equal(step(24, 0), 0);
  assert.equal(step(50, 15), 1);
  assert.equal(step(190, 75), 0);
  assert.equal(step(130, 190), 0);
  assert.equal(step(-100, 370), -1);
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
    if (action === 'tab') h.selectTab('thoughts'); else h.unmount();
    h.requests[0].resolve({ session: { id: 'private' }, question: { id: 'q' }, answer: { id: 'a' } });
    await pending;
    assert.equal(h.requests[0].options.signal.aborted, true);
    assert.equal(h.qaSession.value, null); assert.deepEqual(h.qaMessages.value, []);
  }
});

test('one shelf retains source articles when the favorites provider fails', async () => {
  const h = harness();
  h.status.value = { authenticated: true };
  const pending = h.loadActive();
  const source = { article_key: 'article:1', title: '原文', bubble_count: 1 };
  h.requests.find(r => r.path === '/articles').resolve({ items: [source] });
  h.requests.find(r => r.path.endsWith('/recent')).resolve({ Items: [{ Title: '近期收藏', Url: '/recent' }] });
  h.requests.find(r => r.path.endsWith('/lists')).reject(new Error('收藏夹读取失败'));
  await pending;
  assert.deepEqual(h.shelfBooks.value.map(b => b.id), ['recent:/recent', 'source:article:1']);
  assert.equal(h.error.value, '收藏夹读取失败');
});

test('opening a source book cancels the folder requests and shows only its notes', async () => {
  const h = harness();
  const stale = h.selectFavlist(list(1));
  const source = { article_key: 'article:1', title: '原文', bubble_count: 1 };
  h.articles.value = [source];
  h.openShelfBook('source:article:1');
  assert.ok(h.requests.slice(0, 2).every(r => r.options.signal.aborted));
  h.requests[0].resolve({ id: 'old' });
  h.requests[1].resolve({ Items: [{ Title: '旧收藏' }] });
  assert.equal(h.requests[2].path, '/bubbles?article_key=article%3A1');
  h.requests[2].resolve({ items: [{ id: 'note' }] });
  await stale; await flush();
  assert.equal(h.selectedFavlist.value, null);
  assert.equal(h.qaSession.value, null);
  assert.equal(h.selectedArticle.value, source);
  assert.deepEqual(h.bubbles.value, [{ id: 'note' }]);
});
