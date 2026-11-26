<script setup lang="ts">
import { computed, nextTick, onBeforeUnmount, onMounted, ref } from "vue";
import { api, ApiError } from "./api";
import { RequestScope } from "./request-scope";
import UserProfile from "./components/UserProfile.vue";
import SiteHeader from "./components/SiteHeader.vue";
import SpaceTools from "./components/SpaceTools.vue";
import WorkspaceHome from "./components/WorkspaceHome.vue";
import LibraryShelf from "./components/LibraryShelf.vue";
import { createWheelStep, wheelPixels, workspaceIndex, workspacePages } from "./workspace-navigation";
import "./workspace.css";
import ThoughtBranches from "./components/ThoughtBranches.vue";
import ThoughtTree from "./components/ThoughtTree.vue";
import ThoughtBubblePage from "./components/ThoughtBubblePage.vue";
import ThoughtContext from "./components/ThoughtContext.vue";
import ThoughtDebate from "./components/ThoughtDebate.vue";
import ThoughtLibrary from "./components/ThoughtLibrary.vue";
import type { ArticleGroup, AuthStatus, Bubble, ContentItem, Favlist, Profile, QaMessage, QaSession } from "./types";

const readPath = () => window.location.pathname.replace(/\/$/, "") || "/";
const path = ref(readPath());
const isBranchPage = computed(() => path.value === "/thought-branches");
const experimentMode = new URLSearchParams(window.location.search).get("mode") === "experiment";
const isBubblePage = computed(() => path.value === "/thought-bubbles");
const thoughtId = ref(new URLSearchParams(window.location.search).get("thought") || "");
const route = computed(() => {
  if (path.value === "/library") return "library";
  if (path.value === "/account") return "account";
  return ["/space", "/space/debate", "/thought-bubbles", "/thought-branches"].includes(path.value) ? "space" : "home";
});
const activePage = computed(() => workspaceIndex(path.value));
const direction = ref("forward");
const wheelStep = createWheelStep();
let transitionUntil = 0;
let workspaceSearch = window.location.search;
const resumeLabels: Record<string, string> = {
  "/library": "资料库", "/thought-bubbles": "思维泡泡", "/thought-branches": "思想分叉", "/space/debate": "长桌讨论室",
};
const resume = ref<{ href: string; label: string }>();
const recentNotes = ref<Bubble[]>([]), recentLoading = ref(false), recentFailed = ref(false);
const recentRequest = new RequestScope();

type TabKey = "materials" | "thoughts";
const tabs: { key: TabKey; label: string }[] = [
  { key: "materials", label: "阅读资料" }, { key: "thoughts", label: "思绪" },
];
const status = ref<AuthStatus | null>(null), profile = ref<Profile | null>(null);
const activeTab = ref<TabKey>("materials");
const loading = ref(true), authBusy = ref(false), error = ref("");
const favlists = ref<Favlist[]>([]), recent = ref<ContentItem[]>([]), favoriteItems = ref<ContentItem[]>([]);
const selectedFavlist = ref<Favlist | null>(null);
const selectedRecent = ref<ContentItem | null>(null);
const articles = ref<ArticleGroup[]>([]), bubbles = ref<Bubble[]>([]), selectedArticle = ref<ArticleGroup | null>(null);
const shelfBooks = computed(() => [
  ...favlists.value.map(list => ({
    id: `folder:${list.UrlToken}`, title: list.Title || "未命名收藏夹", subtitle: list.Description || "公开收藏夹",
  })),
  ...recent.value.map(item => ({
    id: `recent:${item.Url}`, title: item.Title || "未命名收藏", subtitle: "近期收藏",
  })),
  ...articles.value.map(article => ({
    id: `source:${article.article_key}`, title: article.title || "未命名文章", subtitle: `来源文章 · ${article.bubble_count} 条想法`,
  })),
]);
const openedBook = computed(() => selectedFavlist.value ? `folder:${selectedFavlist.value.UrlToken}`
  : selectedRecent.value ? `recent:${selectedRecent.value.Url}`
    : selectedArticle.value ? `source:${selectedArticle.value.article_key}` : undefined);
const pairCode = ref(""), pairLoading = ref(false), detailLoading = ref(false), deletingId = ref("");
const authRequest = new RequestScope(), tabRequest = new RequestScope(), favoriteRequest = new RequestScope();
const articleRequest = new RequestScope(), pairRequest = new RequestScope(), deleteRequest = new RequestScope();
const dataRequests = [tabRequest, favoriteRequest, articleRequest, pairRequest, deleteRequest, recentRequest];

const qaSession = ref<QaSession | null>(null), qaMessages = ref<QaMessage[]>([]);
const qaQuestion = ref(""), qaLoading = ref(false), qaAsking = ref(false), qaError = ref("");
const qaList = ref<HTMLElement>();
const qaRequest = new RequestScope(), qaMessageRequest = new RequestScope();

let retryOperation: () => Promise<void> = loadStatus;
function showError(reason: unknown, operation: () => Promise<void> = loadActive) {
  retryOperation = operation;
  error.value = reason instanceof ApiError ? reason.message : "操作失败，请检查服务是否已启动。";
}

function clearPrivateData() {
  clearQa();
  dataRequests.forEach(request => request.invalidate());
  profile.value = null; favlists.value = []; recent.value = []; favoriteItems.value = [];
  selectedFavlist.value = null; selectedRecent.value = null;
  recentNotes.value = []; recentLoading.value = false; recentFailed.value = false;
  articles.value = []; bubbles.value = []; selectedArticle.value = null;
  pairCode.value = ""; pairLoading.value = false; detailLoading.value = false;
  deletingId.value = ""; loading.value = false; error.value = "";
  activeTab.value = "materials";
}

async function loadActive() {
  const request = tabRequest.begin();
  if (!status.value?.authenticated || route.value !== "library" || activeTab.value === "thoughts") {
    loading.value = false; return;
  }
  loading.value = true; error.value = "";
  const options = { signal: request.signal };
  const [lists, items, sources] = await Promise.allSettled([
    api<{ Items: Favlist[] }>("/zhihu/favorites/lists", options),
    api<{ Items: ContentItem[] }>("/zhihu/favorites/recent", options),
    api<{ items: ArticleGroup[] }>("/articles", options),
  ]);
  if (!request.isCurrent()) return;
  if (lists.status === "fulfilled") favlists.value = lists.value.Items || [];
  if (items.status === "fulfilled") recent.value = items.value.Items || [];
  if (sources.status === "fulfilled") {
    articles.value = (sources.value.items || []).filter(item => item.bubble_count > 0);
    if (selectedArticle.value && !articles.value.some(item => item.article_key === selectedArticle.value?.article_key)) {
      collapseArticle();
    }
  }
  const failed = [lists, items, sources].find(result => result.status === "rejected");
  if (failed) showError(failed.reason, loadPageData);
  loading.value = false;
}

async function loadRecentNotes() {
  const request = recentRequest.begin();
  recentLoading.value = true; recentFailed.value = false;
  try {
    const data = await api<{ items: Bubble[] }>("/bubbles", { signal: request.signal });
    if (request.isCurrent()) recentNotes.value = data.items.slice(0, 3);
  } catch {
    if (request.isCurrent()) recentFailed.value = true;
  } finally { if (request.isCurrent()) recentLoading.value = false; }
}

async function loadStatus() {
  const request = authRequest.begin(); authBusy.value = true; error.value = "";
  try {
    const nextStatus = await api<AuthStatus>("/auth/status", { signal: request.signal });
    if (!request.isCurrent()) return;
    if (nextStatus.user_id !== status.value?.user_id || !nextStatus.authenticated) clearPrivateData();
    status.value = nextStatus; authBusy.value = false;
    if (nextStatus.authenticated) {
      const nextProfile = await api<Profile>("/zhihu/me", { signal: request.signal }).catch(() => null);
      if (!request.isCurrent()) return;
      profile.value = nextProfile;
    }
    if (!request.isCurrent()) return;
    await loadPageData();
  } catch (reason) { if (request.isCurrent()) showError(reason, loadStatus); }
  finally { if (request.isCurrent()) { authBusy.value = false; if (!status.value?.authenticated) loading.value = false; } }
}

async function loadPageData() {
  if (route.value === "home" && status.value?.authenticated) {
    await loadRecentNotes();
    return;
  }
  if (route.value !== "library") return;
  const params = new URLSearchParams(window.location.search);
  const source = params.get("source");
  if ((params.has("thought") || params.get("tab") === "thoughts") && status.value?.authenticated) {
    activeTab.value = "thoughts";
    loading.value = false;
    return;
  }
  await loadActive();
  const article = source && articles.value.find(item => item.article_key === source);
  if (status.value?.authenticated && path.value === "/library" && activeTab.value === "materials" &&
      !openedBook.value && article && new URLSearchParams(window.location.search).get("source") === source) {
    await selectArticle(article);
  }
}

function openShelfBook(id: string) {
  const wasOpen = openedBook.value === id;
  collapseFavlist();
  collapseArticle();
  selectedRecent.value = null;
  if (wasOpen) return;

  const list = favlists.value.find(item => `folder:${item.UrlToken}` === id);
  if (list) { void selectFavlist(list); return; }
  const article = articles.value.find(item => `source:${item.article_key}` === id);
  if (article) { void selectArticle(article); return; }
  selectedRecent.value = recent.value.find(item => `recent:${item.Url}` === id) || null;
}

async function loginDemo() {
  const request = authRequest.begin(); authBusy.value = true; clearPrivateData();
  try {
    await api("/auth/demo", { method: "POST", signal: request.signal });
    if (request.isCurrent()) await loadStatus();
  } catch (reason) { if (request.isCurrent()) showError(reason, loginDemo); }
  finally { if (request.isCurrent()) authBusy.value = false; }
}
function loginZhihu() { window.location.href = "/api/auth/zhihu/start"; }

async function logout() {
  const request = authRequest.begin(), previous = status.value; authBusy.value = true;
  // Clear and cancel immediately, including the mounted profile and pairing code.
  clearPrivateData();
  if (previous) status.value = { ...previous, authenticated: false, mode: null, user_id: null };
  try {
    await api("/auth/logout", { method: "POST", signal: request.signal });
    if (request.isCurrent() && status.value) status.value = { ...status.value, authenticated: false, mode: null, user_id: null };
  } catch (reason) { if (request.isCurrent()) { status.value = previous; showError(reason, logout); } }
  finally { if (request.isCurrent()) authBusy.value = false; }
}

function selectTab(tab: TabKey) {
  if (activeTab.value === tab) return;
  collapseFavlist();
  collapseArticle();
  selectedRecent.value = null;
  syncThoughtLibraryLink("", tab === "thoughts");
  activeTab.value = tab; void loadActive();
}

function syncThoughtLibraryLink(id: string, stayOnThoughts = true) {
  const url = new URL(window.location.href);
  url.searchParams.delete("source");
  url.searchParams.delete("thought");
  url.searchParams.delete("tab");
  url.searchParams.delete("source");
  if (id) url.searchParams.set("thought", id);
  else if (stayOnThoughts) url.searchParams.set("tab", "thoughts");
  thoughtId.value = id;
  workspaceSearch = url.search;
  window.history.replaceState(window.history.state, "", url);
}

function clearQa() {
  qaRequest.invalidate(); qaMessageRequest.invalidate();
  qaSession.value = null; qaMessages.value = []; qaQuestion.value = "";
  qaError.value = ""; qaLoading.value = false; qaAsking.value = false;
}
function collapseFavlist() {
  favoriteRequest.invalidate(); detailLoading.value = false;
  selectedFavlist.value = null; favoriteItems.value = []; clearQa();
}
async function selectFavlist(list: Favlist) {
  if (selectedFavlist.value?.UrlToken === list.UrlToken) { collapseFavlist(); return; }
  const request = favoriteRequest.begin(); selectedFavlist.value = list;
  favoriteItems.value = []; detailLoading.value = true; error.value = "";
  void openQa(list);
  try {
    const data = await api<{ Items: ContentItem[] }>(`/zhihu/favorites/contents?favlist_url_token=${encodeURIComponent(list.UrlToken)}`, { signal: request.signal });
    if (request.isCurrent()) favoriteItems.value = data.Items || [];
  } catch (reason) { if (request.isCurrent()) showError(reason, () => { collapseFavlist(); return selectFavlist(list); }); }
  finally { if (request.isCurrent()) detailLoading.value = false; }
}
async function openQa(list: Favlist) {
  clearQa(); const request = qaRequest.begin();
  qaLoading.value = true;
  try {
    const session = await api<QaSession>("/qa/sessions", {
      method: "POST", signal: request.signal,
      body: JSON.stringify({ favlist_url_token: list.UrlToken, favlist_title: list.Title }),
    });
    if (!request.isCurrent()) return;
    const detail = await api<QaSession>(`/qa/sessions/${session.id}`, { signal: request.signal });
    if (!request.isCurrent()) return;
    qaSession.value = detail; qaMessages.value = detail.messages || [];
    await nextTick();
    if (request.isCurrent() && qaList.value) qaList.value.scrollTop = qaList.value.scrollHeight;
  } catch (reason) {
    if (request.isCurrent()) qaError.value = reason instanceof ApiError ? reason.message : "问答会话加载失败，请稍后重试。";
  } finally { if (request.isCurrent()) qaLoading.value = false; }
}
function retryQa() { if (selectedFavlist.value) void openQa(selectedFavlist.value); }
async function askQa() {
  const question = qaQuestion.value.trim(), session = qaSession.value;
  if (!question || !session || qaAsking.value) return;
  const request = qaMessageRequest.begin();
  qaAsking.value = true; qaError.value = "";
  try {
    const result = await api<{ session: QaSession; question: QaMessage; answer: QaMessage }>(`/qa/sessions/${session.id}/messages`, {
      method: "POST", signal: request.signal, body: JSON.stringify({ question }),
    });
    if (!request.isCurrent() || qaSession.value?.id !== session.id) return;
    qaMessages.value.push(result.question, result.answer); qaSession.value = result.session; qaQuestion.value = "";
    await nextTick();
    if (request.isCurrent() && qaList.value) qaList.value.scrollTop = qaList.value.scrollHeight;
  } catch (reason) {
    if (request.isCurrent()) qaError.value = reason instanceof ApiError ? reason.message : "提问失败，请稍后重试。";
  } finally { if (request.isCurrent()) qaAsking.value = false; }
}

function collapseArticle() {
  articleRequest.invalidate(); detailLoading.value = false;
  selectedArticle.value = null; bubbles.value = [];
}
async function selectArticle(article: ArticleGroup) {
  const request = articleRequest.begin(); selectedArticle.value = article;
  bubbles.value = []; detailLoading.value = true; error.value = "";
  try {
    const data = await api<{ items: Bubble[] }>(`/bubbles?article_key=${encodeURIComponent(article.article_key)}`, { signal: request.signal });
    if (request.isCurrent()) bubbles.value = data.items || [];
  } catch (reason) { if (request.isCurrent()) showError(reason, () => selectArticle(article)); }
  finally { if (request.isCurrent()) detailLoading.value = false; }
}
async function removeBubble(id: string) {
  if (!window.confirm("确定删除这条泡泡记录吗？")) return;
  const request = deleteRequest.begin(), article = selectedArticle.value; deletingId.value = id; error.value = "";
  try {
    await api(`/bubbles/${id}`, { method: "DELETE", signal: request.signal });
    if (!request.isCurrent()) return;
    // Refresh groups first: deleting the final bubble can remove the article itself.
    if (activeTab.value === "materials") {
      await loadActive();
      if (request.isCurrent() && article && selectedArticle.value?.article_key === article.article_key && articles.value.some(item => item.article_key === article.article_key)) {
        await selectArticle(article);
      }
    }
  } catch (reason) { if (request.isCurrent()) showError(reason, () => removeBubble(id)); }
  finally { if (request.isCurrent()) deletingId.value = ""; }
}
async function createPairCode() {
  const request = pairRequest.begin(); pairLoading.value = true; pairCode.value = ""; error.value = "";
  try {
    const data = await api<{ code: string }>("/extension/pair", { method: "POST", signal: request.signal });
    if (request.isCurrent()) pairCode.value = data.code;
  } catch (reason) { if (request.isCurrent()) showError(reason, createPairCode); }
  finally { if (request.isCurrent()) pairLoading.value = false; }
}
async function retry() { await retryOperation(); }

function formatDate(timestamp?: number) { return timestamp ? new Date(timestamp * 1000).toLocaleString("zh-CN") : "未标注时间"; }

function restoreWorkspaceLink() {
  try {
    if (Object.hasOwn(resumeLabels, path.value)) localStorage.setItem("thinkspace:last-workspace", path.value);
    const previous = localStorage.getItem("thinkspace:last-workspace");
    if (previous && Object.hasOwn(resumeLabels, previous)) resume.value = { href: previous, label: resumeLabels[previous] };
  } catch { /* The workspace remains usable with storage disabled. */ }
}

function onPageShow(event: PageTransitionEvent) {
  if (!event.persisted) return;
  restoreWorkspaceLink();
  void loadStatus();
}

function refreshTitle() {
  document.title = ({
    home: "ThinkSpace · 首页", library: "资料库 · ThinkSpace", account: "个人中心 · ThinkSpace",
    space: isBubblePage.value ? "思维泡泡 · ThinkSpace" : isBranchPage.value ? (experimentMode ? "控制变量实验 · ThinkSpace" : "思想树 · ThinkSpace")
      : path.value === "/space/debate" ? "长桌讨论室 · ThinkSpace" : "思考空间 · ThinkSpace",
  })[route.value];
}

function switchWorkspace(url: URL, push: boolean) {
  const index = workspaceIndex(url.pathname);
  if (index < 0) return;
  direction.value = index >= activePage.value ? "forward" : "backward";
  transitionUntil = performance.now() + 520;
  if (push) window.history.pushState({}, "", url);
  workspaceSearch = url.search;
  thoughtId.value = url.searchParams.get("thought") || "";
  path.value = url.pathname;
  clearQa();
  tabRequest.invalidate(); favoriteRequest.invalidate(); articleRequest.invalidate(); recentRequest.invalidate();
  deleteRequest.invalidate(); deletingId.value = "";
  selectedFavlist.value = null; selectedRecent.value = null; favoriteItems.value = [];
  selectedArticle.value = null; bubbles.value = [];
  activeTab.value = "materials"; detailLoading.value = false; recentLoading.value = false;
  loading.value = status.value?.authenticated === true && route.value === "library";
  error.value = "";
  refreshTitle(); restoreWorkspaceLink();
  void loadPageData();
}

function onWorkspaceClick(event: MouseEvent) {
  if (event.defaultPrevented || event.button !== 0 || event.metaKey || event.ctrlKey || event.shiftKey || event.altKey) return;
  const anchor = (event.target as Element | null)?.closest?.("a[href]") as HTMLAnchorElement | null;
  if (!anchor || anchor.target || anchor.hasAttribute("download")) return;
  const url = new URL(anchor.href);
  if (url.origin !== location.origin || url.hash || workspaceIndex(url.pathname) < 0 || activePage.value < 0) return;
  event.preventDefault();
  if (url.href !== location.href) switchWorkspace(url, true);
}

function onWorkspacePop() {
  const next = readPath();
  if (next === path.value && location.search === workspaceSearch) return;
  if (activePage.value >= 0 && workspaceIndex(next) >= 0) switchWorkspace(new URL(location.href), false);
}

function onWorkspaceWheel(event: WheelEvent) {
  const index = activePage.value;
  if (index < 0 || event.defaultPrevented || event.ctrlKey || event.metaKey || event.shiftKey ||
      Math.abs(event.deltaX) > Math.abs(event.deltaY)) return;
  const target = event.target as Element | null;
  if (target?.closest?.("input, textarea, select, [contenteditable], [data-workspace-wheel], .qa-messages, dialog")) return;
  const delta = wheelPixels(event, window.innerHeight);
  if (!delta) return;
  const next = workspacePages[index + Math.sign(delta)];
  const scroller = document.scrollingElement;
  if (!next || !scroller) return;
  const hasRoom = delta > 0
    ? scroller.scrollTop < scroller.scrollHeight - scroller.clientHeight - 3
    : scroller.scrollTop > 3;
  const now = performance.now();
  if (now < transitionUntil) {
    event.preventDefault();
    wheelStep(delta, now);
    return;
  }
  if (hasRoom) return;
  event.preventDefault();
  if (wheelStep(delta, now)) switchWorkspace(new URL(next.path, location.origin), true);
}

function resetPageScroll() { window.scrollTo({ top: 0, behavior: "instant" }); }

onMounted(async () => {
  refreshTitle();
  restoreWorkspaceLink();
  window.addEventListener("pageshow", onPageShow);
  window.addEventListener("popstate", onWorkspacePop);
  window.addEventListener("wheel", onWorkspaceWheel, { passive: false });
  document.addEventListener("click", onWorkspaceClick);
  if (new URLSearchParams(window.location.search).get("auth") === "success") {
    window.history.replaceState({}, "", "/");
    workspaceSearch = "";
  }
  await loadStatus();
});
onBeforeUnmount(() => {
  window.removeEventListener("pageshow", onPageShow);
  window.removeEventListener("popstate", onWorkspacePop);
  window.removeEventListener("wheel", onWorkspaceWheel);
  document.removeEventListener("click", onWorkspaceClick);
  clearQa(); authRequest.invalidate(); dataRequests.forEach(request => request.invalidate());
});
</script>

<template>
  <SiteHeader :section="route" :status="status" :profile="profile" />
  <div v-if="error" class="shell hub-alert">
    <div class="error-banner" role="alert"><span>{{ error }}</span><button @click="retry">重试</button></div>
  </div>
  <div class="hub-transition-frame">
    <Transition :name="`hub-page-${direction}`" mode="out-in" @before-enter="resetPageScroll">
      <div :key="path">
  <ThoughtTree v-if="isBranchPage && !experimentMode" :key="(status?.user_id || '') + ':' + thoughtId"
    :authenticated="!!status?.authenticated" :source-id="thoughtId || undefined" />
  <ThoughtContext v-else-if="thoughtId && (isBubblePage || isBranchPage || path === '/space/debate')"
    :key="(status?.user_id || '') + ':' + thoughtId" :id="thoughtId" :active-path="path" v-slot="{ record }">
    <ThoughtBubblePage v-if="isBubblePage" :thought="record" />
    <ThoughtBranches v-else-if="isBranchPage" :thought="record" />
    <ThoughtDebate v-else :thought="record" />
  </ThoughtContext>
  <ThoughtBubblePage v-else-if="isBubblePage" />
  <ThoughtBranches v-else-if="isBranchPage" />
  <WorkspaceHome v-else-if="route === 'home'" :authenticated="!!status?.authenticated"
    :recent="recentNotes" :loading="authBusy || recentLoading" :failed="recentFailed" :resume="resume" />
  <main v-else-if="route === 'space'" class="shell hub-page">
    <template v-if="path === '/space/debate'">
      <div class="hub-page-title">
        <a class="hub-back" href="/space">思考空间</a>
        <h1>长桌讨论室</h1>
      </div>
      <iframe src="/experiences/debate/" title="长桌讨论室" class="experience-frame"></iframe>
    </template>
    <template v-else>
      <div class="hub-page-title">
        <h1>思考空间</h1>
      </div>
      <div class="hub-space-tools"><SpaceTools /></div>
    </template>
  </main>
  <main v-else class="shell hub-page">
    <div class="hub-page-title library-heading">
      <div>
        <h1>{{ route === "account" ? "个人中心" : "资料库" }}</h1>
        <p v-if="status?.oauth_expired" class="warning">知乎授权已过期，请退出后重新授权。</p>
      </div>
      <a v-if="route === 'library' && status && !status.authenticated" class="hub-action quiet"
        href="#library-connect">连接阅读资料</a>
    </div>
    <nav v-if="route === 'library' && status?.authenticated" class="tabs shelf-tabs" aria-label="资料分类">
      <button v-for="tab in tabs" :key="tab.key" :class="{ active: activeTab === tab.key }"
        :aria-pressed="activeTab === tab.key" @click="selectTab(tab.key)">{{ tab.label }}</button>
    </nav>
    <ThoughtLibrary v-if="route === 'library' && activeTab === 'thoughts' && status?.authenticated"
      :key="status.user_id || ''" :initial-id="thoughtId" @select="syncThoughtLibraryLink" />
    <LibraryShelf v-else-if="route === 'library'" :key="activeTab" :books="shelfBooks" :open-id="openedBook"
      :loading="authBusy || (!!status?.authenticated && loading)"
      @open="openShelfBook" />
    <section v-if="!status?.authenticated" id="library-connect" class="panel hub-gate" aria-label="登录">
      <h2>连接你的阅读资料</h2>
      <div class="hub-welcome-actions">
        <button class="hub-action primary" @click="loginZhihu" :disabled="!status?.oauth_configured || authBusy">使用知乎账号登录</button>
        <button v-if="status?.demo_enabled" class="hub-action quiet" @click="loginDemo" :disabled="authBusy">先体验本地演示</button>
      </div>
      <p v-if="status && !status.oauth_configured" class="hub-help">知乎授权待配置。</p>
    </section>

    <template v-else-if="route === 'account'">
      <section id="extension" class="panel hub-account-tools" aria-label="账户与扩展">
        <div><h2>阅读扩展</h2></div>
        <button class="hub-action quiet" @click="createPairCode" :disabled="pairLoading || authBusy">
          {{ pairLoading ? "生成中…" : "连接阅读扩展" }}
        </button>
        <button class="text-button" @click="logout" :disabled="authBusy">退出登录</button>
        <div v-if="pairCode" class="pair-panel">
          <div><strong>扩展一次性配对码</strong><span>5 分钟内粘贴到浏览器扩展，不要发给其他人。</span></div>
          <code>{{ pairCode }}</code>
          <button class="text-button" @click="pairCode = ''">关闭</button>
        </div>
      </section>
      <UserProfile />
      <details class="hub-data-boundary">
        <summary>数据范围</summary>
        <p>收藏和创作仅显示公开摘要。当前公开接口未提供点赞及评论历史。</p>
      </details>
    </template>

    <template v-else>
      <section v-if="activeTab === 'materials' && selectedFavlist" class="panel library-detail">
        <div class="panel-heading"><h2>{{ selectedFavlist.Title }} · 条目</h2></div>
        <p v-if="detailLoading" class="empty" role="status">正在加载条目…</p>
        <p v-else-if="!favoriteItems.length && !error" class="empty">这个收藏夹还没有可显示的条目。</p>
        <article v-for="item in favoriteItems" :key="item.Url" class="content-card compact">
          <a :href="item.Url" target="_blank" rel="noreferrer">{{ item.Title }}</a>
          <p>{{ item.Summary }}</p><small>摘要 · {{ item.Author?.Name || "未标注作者" }}</small>
        </article>
      </section>

      <section v-if="activeTab === 'materials' && selectedRecent" class="panel library-detail">
        <div class="panel-heading"><h2>近期收藏</h2><span>摘要</span></div>
        <article class="content-card">
          <div class="content-meta">{{ selectedRecent.ContentType }} · {{ formatDate(selectedRecent.FavTime) }}</div>
          <a :href="selectedRecent.Url" target="_blank" rel="noreferrer">{{ selectedRecent.Title }}</a>
          <p>{{ selectedRecent.Summary }}</p>
          <footer>
            <span>{{ selectedRecent.Author?.Name || "未标注作者" }}</span>
            <span>{{ selectedRecent.LikeCount || 0 }} 赞同 · {{ selectedRecent.CommentCount || 0 }} 评论</span>
          </footer>
        </article>
      </section>

      <section v-if="activeTab === 'materials' && selectedFavlist" class="panel qa-panel">
        <div class="panel-heading">
          <h2>问「{{ selectedFavlist.Title }}」</h2>
          <span>仅基于收藏摘要 · 无生成模型</span>
        </div>
        <p v-if="qaLoading" class="empty">正在打开问答…</p>
        <div v-else-if="!qaSession" class="empty">
          <p>{{ qaError || "问答会话暂时不可用。" }}</p>
          <button class="button secondary" @click="retryQa">重试</button>
        </div>
        <template v-else>
          <div ref="qaList" class="qa-messages">
            <p v-if="qaMessages.length === 0" class="empty">
              暂无提问。
            </p>
            <article
              v-for="message in qaMessages"
              :key="message.id"
              :class="['qa-message', message.role]"
            >
              <div class="qa-role">
                {{ message.role === "user" ? "你" : "ThinkSpace" }} · {{ formatDate(message.created_at) }}
              </div>
              <p class="qa-body">{{ message.body }}</p>
              <div v-if="message.citations.length" class="qa-citations">
                <a
                  v-for="citation in message.citations"
                  :key="citation.source_url"
                  class="qa-citation"
                  :href="citation.source_url"
                  target="_blank"
                  rel="noreferrer"
                >
                  <strong>{{ citation.title || "未命名来源" }}</strong>
                  <small>{{ citation.author_name || "未标注作者" }} · 收藏摘要</small>
                  <span>{{ citation.snippet }}</span>
                </a>
              </div>
            </article>
          </div>
          <p v-if="qaError" class="qa-error" role="alert">{{ qaError }}</p>
          <form class="qa-compose" @submit.prevent="askQa">
            <textarea
              v-model="qaQuestion"
              maxlength="2000"
              rows="2"
              placeholder="在这个收藏夹里问一个问题……"
              :disabled="qaAsking"
            ></textarea>
            <button class="button primary" type="submit" :disabled="qaAsking || !qaQuestion.trim()">
              {{ qaAsking ? "回答中…" : "提问" }}
            </button>
          </form>
        </template>
      </section>

      <section v-if="activeTab === 'materials' && selectedArticle" class="library-detail">
        <div class="panel bubble-detail">
          <template v-if="selectedArticle">
            <div class="panel-heading"><h2>{{ selectedArticle.title }}</h2></div>
            <a class="source-link" :href="selectedArticle.source_url" target="_blank" rel="noreferrer">打开知乎原文</a>
            <p v-if="detailLoading" class="empty" role="status">正在加载想法…</p>
            <article v-for="bubble in bubbles" :key="bubble.id" class="bubble-card">
              <time>{{ formatDate(bubble.created_at) }}</time>
              <blockquote v-if="bubble.quote">{{ bubble.quote }}</blockquote>
              <p>{{ bubble.body }}</p>
              <a class="hub-note-link" :href="`/thought-bubbles?note=${encodeURIComponent(bubble.id)}`">在思维泡泡中阅读</a>
              <button class="text-button danger" @click="removeBubble(bubble.id)" :disabled="deletingId === bubble.id">{{ deletingId === bubble.id ? "删除中…" : "删除" }}</button>
            </article>
          </template>
        </div>
      </section>
    </template>
  </main>
      </div>
    </Transition>
  </div>
</template>
