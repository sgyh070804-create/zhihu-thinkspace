<script setup lang="ts">
import { computed, nextTick, onBeforeUnmount, onMounted, ref, watch } from "vue";
import { api } from "../api";
import { RequestScope } from "../request-scope";
import { connectionDraft, filterNotes, fromSavedBubble, PAGE_SIZE, sampleNotes, sceneItems } from "../bubble-space";
import type { SpaceNote } from "../bubble-space";
import type { AuthStatus, Bubble } from "../types";
import { bubbleEngine } from "../bubble-engine";
import type { BubbleScene, Thought } from "../bubble-engine";
import SpaceIcon from "./SpaceIcon.vue";
import "../thought-bubbles.css";

const host = ref<HTMLElement>(), reader = ref<HTMLElement>(), dialog = ref<HTMLElement>(), input = ref<HTMLTextAreaElement>();
const notes = ref<SpaceNote[]>([]), sceneNotes = ref<SpaceNote[]>([]), folded = ref(new Set<string>());
const reading = ref<SpaceNote | null>(null), loading = ref(true), error = ref(""), notice = ref("");
const mode = ref<"account" | "sample">("account"), status = ref<AuthStatus | null>(null);
const query = ref(""), draftsOnly = ref(false), page = ref(0), paused = ref(false), busy = ref(false);
const compactScreen = matchMedia("(max-width: 760px)"), pageSize = ref(compactScreen.matches ? 4 : PAGE_SIZE);
const composer = ref<{ a: SpaceNote; b: SpaceNote } | null>(null), body = ref("");
const requestedNote = new URLSearchParams(window.location.search).get("note");
const picked = ref<string[]>([]), picking = ref(false), renderer = ref(""), rafRate = ref(0);
const lastMerge = ref<{ child: string; parents: string[] } | null>(null);
const filtered = computed(() => filterNotes(notes.value, query.value, draftsOnly.value, folded.value));
const pageCount = computed(() => Math.max(1, Math.ceil(filtered.value.length / pageSize.value)));
const pageNotes = computed(() => filtered.value.slice(page.value * pageSize.value, (page.value + 1) * pageSize.value));
const readingIndex = computed(() => sceneNotes.value.findIndex(note => note.id === reading.value?.id));
const draftCount = computed(() => notes.value.filter(note => note.generated).length);
const request = new RequestScope();
let scene: BubbleScene | undefined, disposed = false, statsTimer: ReturnType<typeof setInterval> | undefined;
let resolveDraft: ((thought: Thought) => void) | undefined, rejectDraft: ((reason: Error) => void) | undefined;
let pendingDraft: SpaceNote | undefined, previousFocus: HTMLElement | null = null, toastTimer: ReturnType<typeof setTimeout> | undefined;
const resolveNote = (item: Thought): SpaceNote => notes.value.find(note => note.id === item.id) || { ...item, source: item.source || "阅读手记" };

function tell(message: string) { notice.value = message; clearTimeout(toastTimer); toastTimer = setTimeout(() => { notice.value = ""; }, 5000); }
function syncScene() {
  if (!scene || busy.value) return;
  sceneNotes.value = pageNotes.value;
  scene.setItems(sceneItems(sceneNotes.value, host.value?.clientWidth, host.value?.clientHeight));
  picked.value = []; picking.value = false;
}
function resetSpace(next: SpaceNote[]) {
  notes.value = next; folded.value = new Set(); lastMerge.value = null;
  query.value = ""; draftsOnly.value = false; page.value = 0;
  syncScene();
}
async function loadAccount() {
  if (busy.value) return;
  const current = request.begin(); loading.value = true; error.value = "";
  resetSpace([]);
  try {
    const auth = await api<AuthStatus>("/auth/status", { signal: current.signal });
    if (!current.isCurrent()) return;
    status.value = auth;
    if (!auth.authenticated) {
      mode.value = "sample"; resetSpace(structuredClone(sampleNotes));
      return;
    }
    mode.value = "account";
    const data = await api<{ items: Bubble[] }>("/bubbles", { signal: current.signal });
    if (!current.isCurrent()) return;
    resetSpace(data.items.map(fromSavedBubble));
    if (requestedNote) {
      const index = notes.value.findIndex(note => note.id === requestedNote);
      if (index < 0) tell("这条想法已不存在，或不属于当前账号。");
      else {
        page.value = Math.floor(index / pageSize.value);
        await nextTick();
        if (current.isCurrent()) scene?.focus(requestedNote);
      }
    }
  } catch {
    if (current.isCurrent()) error.value = "暂时无法读取泡泡，请检查服务后重试。也可以先进入示例空间。";
  } finally { if (current.isCurrent()) loading.value = false; }
}
function useSamples() {
  if (busy.value) return;
  request.invalidate(); loading.value = false; error.value = ""; mode.value = "sample";
  resetSpace(structuredClone(sampleNotes));
}
function openNote(note: SpaceNote) {
  if (picking.value) {
    picked.value = picked.value.includes(note.id) ? picked.value.filter(id => id !== note.id) : [...picked.value, note.id].slice(-2);
    return;
  }
  scene?.focus(note.id);
}
function closeReader() {
  const id = reading.value?.id;
  scene?.closeFocus();
  nextTick(() => {
    const card = Array.from(document.querySelectorAll<HTMLButtonElement>(".ts-note-card")).find(el => el.dataset.note === id);
    card?.focus({ preventScroll: true });
  });
}
function stepReader(amount: number) {
  const next = (readingIndex.value + amount + sceneNotes.value.length) % sceneNotes.value.length;
  if (sceneNotes.value[next]) scene?.focus(sceneNotes.value[next].id);
}
function focusReader(element: Element) { (element as HTMLElement).focus({ preventScroll: true }); }
function togglePause() { paused.value = !paused.value; if (paused.value) scene?.pause(); else scene?.resume(); }
async function startMerge() {
  if (!scene || picked.value.length !== 2 || busy.value) return;
  try { await scene.merge(picked.value[0], picked.value[1]); }
  catch { /* Cancellation is handled by the composer; source notes remain intact. */ }
}
async function requestDraft(a: Thought, b: Thought): Promise<Thought> {
  busy.value = true;
  previousFocus = document.activeElement as HTMLElement;
  composer.value = { a: resolveNote(a), b: resolveNote(b) };
  body.value = "";
  const promise = new Promise<Thought>((resolve, reject) => { resolveDraft = resolve; rejectDraft = reject; });
  await nextTick(); input.value?.focus();
  return promise;
}
function confirmDraft() {
  if (!composer.value || !body.value.trim()) return;
  pendingDraft = connectionDraft(composer.value.a, composer.value.b, body.value);
  composer.value = null;
  resolveDraft?.(pendingDraft); resolveDraft = undefined; rejectDraft = undefined;
  nextTick(() => host.value?.focus({ preventScroll: true }));
}
function cancelDraft() {
  composer.value = null; busy.value = false;
  rejectDraft?.(new Error("连接已取消")); resolveDraft = undefined; rejectDraft = undefined;
  nextTick(() => previousFocus?.isConnected && previousFocus.focus({ preventScroll: true }));
}
function onSceneChange(items: Thought[]) {
  if (pendingDraft) {
    const draft = pendingDraft; pendingDraft = undefined;
    notes.value.push(draft);
    folded.value = new Set([...folded.value, ...(draft.parents || [])]);
    lastMerge.value = { child: draft.id, parents: draft.parents || [] };
    tell("新的连接已形成。原想法保留，草稿可导出或撤销。");
  }
  sceneNotes.value = items.map(resolveNote);
  picked.value = []; picking.value = false; busy.value = false;
  previousFocus = null;
  // A new connection can stop matching an active search, or reduce the final page.
  // Wait for the engine's merge callback to finish before replacing its data.
  if (query.value || draftsOnly.value || sceneNotes.value.length > pageSize.value || page.value >= pageCount.value) {
    page.value = Math.min(page.value, pageCount.value - 1);
    nextTick(() => { if (!disposed) syncScene(); });
  }
}
function undoMerge() {
  if (!lastMerge.value || busy.value) return;
  const { child, parents } = lastMerge.value;
  notes.value = notes.value.filter(note => note.id !== child);
  folded.value = new Set([...folded.value].filter(id => !parents.includes(id)));
  lastMerge.value = null; page.value = 0; draftsOnly.value = false;
  syncScene(); tell("已恢复连接前的想法。");
}
function exportDrafts() {
  const drafts = notes.value.filter(note => note.generated);
  const text = "# ThinkSpace · 我的连接\n\n" + drafts.map(note => `## ${note.source}\n\n${note.text}\n\n原想法：\n${(note.parents || []).map(id => notes.value.find(parent => parent.id === id)?.text || id).join("\n\n")}\n`).join("\n---\n\n");
  const url = URL.createObjectURL(new Blob([text], { type: "text/markdown;charset=utf-8" }));
  const a = document.createElement("a"); a.href = url; a.download = "ThinkSpace-我的连接.md"; a.click();
  setTimeout(() => URL.revokeObjectURL(url), 1000);
  tell("已导出连接草稿。");
}
function keydown(event: KeyboardEvent) {
  if (event.key !== "Escape") return;
  if (composer.value) { event.preventDefault(); cancelDraft(); }
  else if (reading.value) closeReader();
  else if (picking.value) { picking.value = false; picked.value = []; }
}
function trapFocus(event: KeyboardEvent) {
  if (event.key !== "Tab") return;
  const controls = dialog.value?.querySelectorAll<HTMLElement>("button:not(:disabled), textarea, a[href]");
  if (!controls?.length) return;
  const first = controls[0], last = controls[controls.length - 1];
  if (event.shiftKey && document.activeElement === first) { event.preventDefault(); last.focus(); }
  else if (!event.shiftKey && document.activeElement === last) { event.preventDefault(); first.focus(); }
}
function resizePage() {
  pageSize.value = compactScreen.matches ? 4 : PAGE_SIZE;
  if (busy.value) return;
  page.value = 0; syncScene();
}
watch([query, draftsOnly], () => { page.value = 0; syncScene(); });
watch(page, syncScene);
watch(reading, async value => { if (value) { await nextTick(); reader.value?.focus({ preventScroll: true }); } });
onMounted(() => {
  document.title = "思维泡泡 · ThinkSpace";
  scene = bubbleEngine.create(host.value!, {
    items: [], maxDpr: 1.15, speed: .7, externalReader: true, animateEntrance: true,
    onFocusChange: item => { reading.value = item ? resolveNote(item) : null; },
    onMerge: requestDraft, onChange: onSceneChange,
    onError: () => { if (!disposed) { busy.value = false; pendingDraft = undefined; } },
  });
  if (import.meta.env.DEV) statsTimer = setInterval(() => {
    const stats = scene?.getStats(); renderer.value = stats?.renderer || ""; rafRate.value = Math.round(stats?.averageFps || 0);
  }, 1000);
  document.addEventListener("keydown", keydown);
  compactScreen.addEventListener("change", resizePage);
  void loadAccount();
});
onBeforeUnmount(() => {
  disposed = true; request.invalidate(); clearInterval(statsTimer); clearTimeout(toastTimer);
  document.removeEventListener("keydown", keydown);
  compactScreen.removeEventListener("change", resizePage);
  rejectDraft?.(new Error("页面已离开")); scene?.destroy();
});
</script>

<template>
  <main class="thought-space" :data-renderer="renderer" :data-raf="rafRate">
    <div class="ts-page-content" :inert="!!composer">
      <section class="ts-intro" aria-labelledby="ts-title">
        <div><a class="hub-back" href="/space">思考空间</a><h1 id="ts-title">思维泡泡</h1><p>留住阅读里的片刻灵光，给新的连接一点空间。</p></div>
        <div class="ts-intro-detail"><SpaceIcon name="spark"/><span>不急着找到答案<br/><strong>先让思绪自由游动</strong></span></div>
      </section>

      <div class="ts-workspace" :class="{ 'is-reading': reading, 'is-busy': busy }">
        <section class="ts-stage" aria-label="思绪空间">
          <div ref="host" class="ts-bubble-host" tabindex="-1"></div>
          <div class="ts-stage-heading" :inert="!!reading">
            <div><span class="ts-live-dot"></span>思绪空间 <small>{{ sceneNotes.length }} 颗想法</small></div>
            <button class="ts-icon-button" :aria-label="paused ? '继续漂浮' : '暂停漂浮'" :aria-pressed="paused" @click="togglePause"><SpaceIcon :name="paused ? 'play' : 'pause'"/></button>
          </div>
          <Transition name="ts-fade">
            <div v-if="loading || error || !sceneNotes.length" class="ts-stage-state">
              <div v-if="loading" class="ts-loading-orb" aria-hidden="true"></div><SpaceIcon v-else name="bubbles"/>
              <h2>{{ loading ? '把思绪轻轻展开…' : error ? '思绪还在路上' : draftsOnly ? '新的连接，等你写下' : query ? '没有找到这颗想法' : '从一个小小的想法开始' }}</h2>
              <p>{{ loading ? '正在读取你的泡泡' : error || (draftsOnly ? '拖动两颗泡泡相遇，写下它们带来的新观点。' : query ? '试试其他关键词，或清空搜索。' : '在阅读扩展里记下想法，它会出现在这里。') }}</p>
              <div v-if="error" class="ts-state-actions"><button class="ts-primary" @click="loadAccount">重新读取</button><button class="ts-secondary" @click="useSamples">先看示例</button></div>
              <button v-else-if="!loading && query" class="ts-secondary" @click="query = ''">清空搜索</button>
              <button v-else-if="!loading && draftsOnly" class="ts-secondary" @click="draftsOnly = false">回到全部想法</button>
              <button v-else-if="!loading && mode === 'account'" class="ts-secondary" @click="useSamples">探索示例空间</button>
            </div>
          </Transition>
          <Transition name="ts-reader">
            <section v-if="reading" class="ts-reader" aria-label="沉浸阅读">
              <div class="ts-reader-top"><button class="ts-reader-back" @click="closeReader"><SpaceIcon name="left"/>回到空间</button><span>沉浸阅读</span><button class="ts-icon-button" aria-label="关闭阅读" @click="closeReader"><SpaceIcon name="close"/></button></div>
              <Transition name="ts-card" mode="out-in" @after-enter="focusReader">
                <article :key="reading.id" ref="reader" class="ts-reader-content" tabindex="-1" :aria-label="reading.source">
                  <div class="ts-reader-kicker">{{ reading.generated ? '一次新的连接' : '阅读留下的想法' }}</div>
                  <p class="ts-reader-body">{{ reading.text }}</p>
                  <blockquote v-if="reading.quote">{{ reading.quote }}</blockquote>
                  <footer>
                    <span>{{ reading.source }}</span>
                    <a v-if="reading.articleKey" :href="`/library?source=${encodeURIComponent(reading.articleKey)}`">查看关联记录</a>
                    <a v-if="reading.url" :href="reading.url" target="_blank" rel="noopener noreferrer">阅读原文</a>
                  </footer>
                </article>
              </Transition>
              <div class="ts-reader-nav"><button class="ts-icon-button" aria-label="上一个想法" :disabled="sceneNotes.length < 2" @click="stepReader(-1)"><SpaceIcon name="left"/></button><span>{{ readingIndex + 1 }} / {{ sceneNotes.length }}</span><button class="ts-icon-button" aria-label="下一个想法" :disabled="sceneNotes.length < 2" @click="stepReader(1)"><SpaceIcon name="right"/></button></div>
            </section>
          </Transition>
          <div class="ts-stage-bottom" :inert="!!reading">
            <span><SpaceIcon name="bubbles"/>点击阅读 <i>·</i> 拖动相遇，松手连接</span>
            <span class="ts-stage-caption">让连接自然发生</span>
          </div>
        </section>

        <aside class="ts-notebook" aria-labelledby="ts-notebook-title" :inert="busy && !composer">
          <header><div><span class="ts-kicker">THOUGHT COLLECTION</span><h2 id="ts-notebook-title">思绪手记 <span>{{ filtered.length }}</span></h2></div><button class="ts-icon-button" :disabled="busy || loading" :aria-label="mode === 'sample' ? '重置示例空间' : '刷新我的泡泡'" @click="mode === 'sample' ? useSamples() : loadAccount()"><SpaceIcon name="refresh"/></button></header>
          <p class="ts-data-note">{{ mode === 'sample' ? '示例观点，供你感受思绪的流动。' : '来自当前账号保存的阅读泡泡。' }}</p>
          <div class="ts-segments" aria-label="手记分类"><span :class="{ 'at-drafts': draftsOnly }"></span><button :disabled="busy" :aria-pressed="!draftsOnly" @click="draftsOnly = false">全部想法</button><button :disabled="busy" :aria-pressed="draftsOnly" @click="draftsOnly = true">连接草稿 <small>{{ draftCount }}</small></button></div>
          <label class="ts-search"><SpaceIcon name="search"/><input v-model="query" :disabled="busy" placeholder="寻找一个想法…" aria-label="搜索想法"/><button v-if="query" class="ts-icon-button" aria-label="清空搜索" @click="query = ''"><SpaceIcon name="close"/></button></label>
          <div v-if="loading" class="ts-skeletons" aria-hidden="true"><div v-for="n in 3" :key="n"></div></div>
          <TransitionGroup v-else name="ts-notes" tag="div" class="ts-note-list" :class="{ 'is-picking': picking }">
            <button v-for="note in sceneNotes" :key="note.id" class="ts-note-card" :class="{ 'is-active': reading?.id === note.id, 'is-picked': picked.includes(note.id) }" :data-note="note.id" :aria-pressed="picking ? picked.includes(note.id) : reading?.id === note.id" :disabled="busy" @click="openNote(note)">
              <span class="ts-note-meta"><SpaceIcon :name="note.generated ? 'link' : 'bubbles'"/><span>{{ note.source }}</span><i v-if="picking">{{ picked.includes(note.id) ? '已选' : '选择' }}</i><SpaceIcon v-else name="right"/></span>
              <p>{{ note.text }}</p><span class="ts-card-cue">{{ picking ? '选择两个想法，试着建立连接' : note.generated ? '本页草稿 · 点击阅读' : '点击，走进这颗想法' }}</span>
            </button>
          </TransitionGroup>
          <div v-if="!sceneNotes.length && !loading" class="ts-list-empty">{{ error ? '读取后，你的手记会出现在这里。' : '给尚未出现的想法，留一个位置。' }}</div>
          <div class="ts-pagination"><span>{{ filtered.length ? page * pageSize + 1 : 0 }}–{{ Math.min((page + 1) * pageSize, filtered.length) }} / {{ filtered.length }}</span><div><button class="ts-icon-button" aria-label="上一组泡泡" :disabled="page === 0 || busy" @click="page--"><SpaceIcon name="left"/></button><button class="ts-icon-button" aria-label="下一组泡泡" :disabled="page >= pageCount - 1 || busy" @click="page++"><SpaceIcon name="right"/></button></div></div>
          <div class="ts-connection-tools"><button v-if="!picking" class="ts-secondary" :disabled="sceneNotes.length < 2 || busy" @click="closeReader(); picking = true"><SpaceIcon name="link"/>连接两个想法</button><template v-else><button class="ts-primary" :disabled="picked.length !== 2 || busy" @click="startMerge">{{ picked.length === 2 ? '写下新的连接' : `再选 ${2 - picked.length} 个想法` }}</button><button class="ts-quiet" :disabled="busy" @click="picking = false; picked = []">取消</button></template><button v-if="lastMerge" class="ts-icon-button" aria-label="撤销上一次连接" :disabled="busy" @click="undoMerge"><SpaceIcon name="undo"/></button></div>
        </aside>
      </div>
      <footer class="ts-page-footer"><span>{{ mode === 'sample' ? '示例不与账号同步。' : '原始泡泡保留在账号中。' }}连接草稿仅留在本页，离开前请导出。</span><div><button v-if="draftCount" class="ts-quiet" @click="exportDrafts"><SpaceIcon name="download"/>导出草稿</button><button v-if="mode === 'sample' && status?.authenticated" class="ts-quiet" :disabled="busy" @click="loadAccount">回到我的泡泡</button><a v-else-if="mode === 'sample'" href="/account">连接阅读资料</a><a v-else href="/library">打开资料库</a></div></footer>
    </div>
    <Transition name="ts-toast"><div v-if="notice" class="ts-toast" role="status">{{ notice }}</div></Transition>
    <Transition name="ts-composer">
      <div v-if="composer" class="ts-composer-backdrop" @click.self="cancelDraft">
        <form ref="dialog" class="ts-composer-dialog" role="dialog" aria-modal="true" aria-labelledby="ts-compose-title" @submit.prevent="confirmDraft" @keydown="trapFocus">
          <header><span class="ts-composer-symbol"><SpaceIcon name="link"/></span><button type="button" class="ts-icon-button" aria-label="取消连接" @click="cancelDraft"><SpaceIcon name="close"/></button></header>
          <span class="ts-kicker">WHEN THOUGHTS MEET</span><h2 id="ts-compose-title">两个想法，一次新的连接。</h2><p class="ts-composer-lead">它们让你想到了什么？用自己的话记下来。</p>
          <div class="ts-parents"><blockquote>{{ composer.a.text }}</blockquote><span>与</span><blockquote>{{ composer.b.text }}</blockquote></div>
          <label for="ts-connection-body">我的新观点</label><textarea id="ts-connection-body" ref="input" v-model="body" required maxlength="4000" placeholder="也许，这两件事之间的联系是…" rows="4"></textarea>
          <div class="ts-compose-note"><span>由你书写，不调用 AI。原想法不会被删除。</span><span>{{ body.length }} / 4000</span></div>
          <footer><button type="button" class="ts-secondary" @click="cancelDraft">再想一想</button><button type="submit" class="ts-primary" :disabled="!body.trim()">形成新的泡泡</button></footer>
        </form>
      </div>
    </Transition>
  </main>
</template>
