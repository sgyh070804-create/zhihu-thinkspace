<script setup lang="ts">
import { nextTick, onBeforeUnmount, onMounted, ref } from "vue";
import { api, ApiError } from "./api";
import { RequestScope } from "./request-scope";
import UserProfile from "./components/UserProfile.vue";
import SiteHeader from "./components/SiteHeader.vue";
import SpaceTools from "./components/SpaceTools.vue";
import WorkspaceHome from "./components/WorkspaceHome.vue";
import "./workspace.css";
import ThoughtBranches from "./components/ThoughtBranches.vue";
import ThoughtBubblePage from "./components/ThoughtBubblePage.vue";
import type { ArticleGroup, AuthStatus, Bubble, ContentItem, Favlist, Profile, QaMessage, QaSession } from "./types";

const path = window.location.pathname.replace(/\/$/, "") || "/";
const isBranchPage = path === "/thought-branches", isBubblePage = path === "/thought-bubbles";
const route = path === "/library" ? "library" : path === "/account" ? "account"
  : ["/space", "/space/debate", "/thought-bubbles", "/thought-branches"].includes(path) ? "space" : "home";
const resumeLabels: Record<string, string> = {
  "/library": "资料库", "/thought-bubbles": "思维泡泡", "/thought-branches": "思想分叉", "/space/debate": "长桌讨论室",
};
const resume = ref<{ href: string; label: string }>();
const recentNotes = ref<Bubble[]>([]), recentLoading = ref(false), recentFailed = ref(false);
const recentRequest = new RequestScope();

type TabKey = "favorites" | "bubbles";
const tabs: { key: TabKey; label: string }[] = [
  { key: "favorites", label: "收藏" }, { key: "bubbles", label: "来源文章" },
];
const status = ref<AuthStatus | null>(null), profile = ref<Profile | null>(null);
const activeTab = ref<TabKey>("favorites");
const loading = ref(true), authBusy = ref(false), error = ref("");
const favlists = ref<Favlist[]>([]), recent = ref<ContentItem[]>([]), favoriteItems = ref<ContentItem[]>([]);
const selectedFavlist = ref<Favlist | null>(null);
const articles = ref<ArticleGroup[]>([]), bubbles = ref<Bubble[]>([]), selectedArticle = ref<ArticleGroup | null>(null);
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
  selectedFavlist.value = null; recentNotes.value = []; recentLoading.value = false; recentFailed.value = false;
  articles.value = []; bubbles.value = []; selectedArticle.value = null;
  pairCode.value = ""; pairLoading.value = false; detailLoading.value = false;
  deletingId.value = ""; loading.value = false; error.value = "";
  activeTab.value = "favorites";
}

async function loadActive() {
  const request = tabRequest.begin();
  if (!status.value?.authenticated || route !== "library") {
    loading.value = false; return;
  }
  const tab = activeTab.value;
  loading.value = true; error.value = "";
  try {
    const options = { signal: request.signal };
    if (tab === "favorites") {
      const [lists, data] = await Promise.all([
        api<{ Items: Favlist[] }>("/zhihu/favorites/lists", options),
        api<{ Items: ContentItem[] }>("/zhihu/favorites/recent", options),
      ]);
      if (request.isCurrent()) { favlists.value = lists.Items || []; recent.value = data.Items || []; }
    } else {
      const data = await api<{ items: ArticleGroup[] }>("/articles", options);
      if (request.isCurrent()) {
        articles.value = (data.items || []).filter(item => item.bubble_count > 0);
        if (selectedArticle.value && !articles.value.some(a => a.article_key === selectedArticle.value?.article_key)) {
          articleRequest.invalidate(); selectedArticle.value = null; bubbles.value = []; detailLoading.value = false;
        }
      }
    }
  } catch (reason) { if (request.isCurrent()) showError(reason); }
  finally { if (request.isCurrent()) loading.value = false; }
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
    if (route === "library") {
      const source = new URLSearchParams(window.location.search).get("source");
      if (source && nextStatus.authenticated) activeTab.value = "bubbles";
      await loadActive();
      const article = source && articles.value.find(item => item.article_key === source);
      if (request.isCurrent() && activeTab.value === "bubbles" && !selectedArticle.value && article) {
        await selectArticle(article);
      }
    } else if (route === "home" && nextStatus.authenticated) await loadRecentNotes();
  } catch (reason) { if (request.isCurrent()) showError(reason, loadStatus); }
  finally { if (request.isCurrent()) { authBusy.value = false; if (!status.value?.authenticated) loading.value = false; } }
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
  clearQa();
  favoriteRequest.invalidate(); articleRequest.invalidate(); detailLoading.value = false;
  selectedFavlist.value = null; favoriteItems.value = []; selectedArticle.value = null; bubbles.value = [];
  activeTab.value = tab; void loadActive();
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
    if (activeTab.value === "bubbles") {
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
    if (Object.hasOwn(resumeLabels, path)) localStorage.setItem("thinkspace:last-workspace", path);
    const previous = localStorage.getItem("thinkspace:last-workspace");
    if (previous && Object.hasOwn(resumeLabels, previous)) resume.value = { href: previous, label: resumeLabels[previous] };
  } catch { /* The workspace remains usable with storage disabled. */ }
}

function onPageShow(event: PageTransitionEvent) {
  if (!event.persisted) return;
  restoreWorkspaceLink();
  void loadStatus();
}

onMounted(async () => {
  document.title = ({
    home: "ThinkSpace · 首页", library: "资料库 · ThinkSpace", account: "个人中心 · ThinkSpace",
    space: isBubblePage ? "思维泡泡 · ThinkSpace" : isBranchPage ? "思想分叉 · ThinkSpace"
      : path === "/space/debate" ? "长桌讨论室 · ThinkSpace" : "思考空间 · ThinkSpace",
  })[route];
  restoreWorkspaceLink();
  window.addEventListener("pageshow", onPageShow);
  if (new URLSearchParams(window.location.search).get("auth") === "success") window.history.replaceState({}, "", "/");
  await loadStatus();
});
onBeforeUnmount(() => {
  window.removeEventListener("pageshow", onPageShow);
  clearQa(); authRequest.invalidate(); dataRequests.forEach(request => request.invalidate());
});
</script>

<template>
  <SiteHeader :section="route" :status="status" :profile="profile" />
  <div v-if="error" class="shell hub-alert">
    <div class="error-banner" role="alert"><span>{{ error }}</span><button @click="retry">重试</button></div>
  </div>
  <ThoughtBubblePage v-if="isBubblePage" />
  <ThoughtBranches v-else-if="isBranchPage" />
  <WorkspaceHome v-else-if="route === 'home'" :authenticated="!!status?.authenticated"
    :recent="recentNotes" :loading="authBusy || recentLoading" :failed="recentFailed" :resume="resume" />
  <main v-else-if="route === 'space'" class="shell hub-page">
    <template v-if="path === '/space/debate'">
      <div class="hub-page-title">
        <a class="hub-back" href="/space">思考空间</a>
        <h1>长桌讨论室</h1><p>角色发言为预设示例。你可以换话题、发言，或查看动作试演。</p>
      </div>
      <iframe src="/experiences/debate/" title="长桌讨论室" class="experience-frame"></iframe>
    </template>
    <template v-else>
      <div class="hub-page-title">
        <h1>思考空间</h1><p>选择一种方式，把刚读到的内容再想一遍。</p>
      </div>
      <div class="hub-space-tools"><SpaceTools /></div>
    </template>
  </main>
  <main v-else class="shell hub-page">
    <div class="hub-page-title">
      <h1>{{ route === "account" ? "个人中心" : "资料库" }}</h1>
      <p v-if="route === 'library'">在收藏里提问，按来源回看记下的想法。</p>
      <p v-if="status?.oauth_expired" class="warning">知乎授权已过期，请退出后重新授权。</p>
    </div>
    <section v-if="!status?.authenticated" class="panel hub-gate" aria-label="登录">
      <h2>连接你的阅读资料</h2>
      <p>登录后可查看收藏、阅读手记和个人资料。</p>
      <div class="hub-welcome-actions">
        <button class="hub-action primary" @click="loginZhihu" :disabled="!status?.oauth_configured || authBusy">使用知乎账号登录</button>
        <button v-if="status?.demo_enabled" class="hub-action quiet" @click="loginDemo" :disabled="authBusy">先体验本地演示</button>
      </div>
      <p v-if="status && !status.oauth_configured" class="hub-help">当前环境可以使用演示账号体验，知乎授权待配置。</p>
    </section>

    <template v-else-if="route === 'account'">
      <section id="extension" class="panel hub-account-tools" aria-label="账户与扩展">
        <div><h2>阅读扩展</h2><p>在知乎原文旁记录想法，保存到当前账户。</p></div>
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
      <nav class="tabs" aria-label="数据分类">
        <button
          v-for="tab in tabs"
          :key="tab.key"
          :class="{ active: activeTab === tab.key }"
          :aria-pressed="activeTab === tab.key"
          @click="selectTab(tab.key)"
        >{{ tab.label }}</button>
      </nav>

      <p v-if="loading" class="load-status" role="status">正在加载资料…</p>

      <section v-if="activeTab === 'favorites'" class="content-grid two-columns">
        <div class="panel">
          <div class="panel-heading"><h2>公开收藏夹</h2><span>{{ favlists.length }} 个</span></div>
          <button
            v-for="list in favlists"
            :key="list.UrlToken"
            class="favlist"
            :class="{ selected: selectedFavlist?.UrlToken === list.UrlToken }"
            :aria-expanded="selectedFavlist?.UrlToken === list.UrlToken"
            @click="selectFavlist(list)"
          >
            <strong>{{ list.Title }}</strong><span>{{ list.Description || "无描述" }}</span>
          </button>
          <p v-if="!loading && favlists.length === 0" class="empty">没有发现公开收藏夹。</p>
          <div v-if="selectedFavlist" class="nested-list">
            <h3>{{ selectedFavlist.Title }} · 条目</h3><p v-if="detailLoading" class="empty" role="status">正在加载条目…</p>
            <article v-for="item in favoriteItems" :key="item.Url" class="content-card compact">
              <a :href="item.Url" target="_blank" rel="noreferrer">{{ item.Title }}</a>
              <p>{{ item.Summary }}</p><small>摘要 · {{ item.Author?.Name || "未标注作者" }}</small>
            </article>
          </div>
        </div>
        <div class="panel">
          <div class="panel-heading"><h2>近期收藏</h2><span>摘要视图</span></div>
          <article v-for="item in recent" :key="item.Url" class="content-card">
            <div class="content-meta">{{ item.ContentType }} · {{ formatDate(item.FavTime) }}</div>
            <a :href="item.Url" target="_blank" rel="noreferrer">{{ item.Title }}</a>
            <p>{{ item.Summary }}</p>
            <footer><span>{{ item.Author?.Name || "未标注作者" }}</span><span>{{ item.LikeCount || 0 }} 赞同 · {{ item.CommentCount || 0 }} 评论</span></footer>
          </article>
          <p v-if="!loading && recent.length === 0" class="empty">近期没有公开收藏。</p>
        </div>
      </section>

      <section v-if="activeTab === 'favorites' && selectedFavlist" class="panel qa-panel">
        <div class="panel-heading">
          <h2>问「{{ selectedFavlist.Title }}」</h2>
          <span>只基于收藏摘要</span>
        </div>
        <p v-if="qaLoading" class="empty">正在打开问答…</p>
        <div v-else-if="!qaSession" class="empty">
          <p>{{ qaError || "问答会话暂时不可用。" }}</p>
          <button class="button secondary" @click="retryQa">重试</button>
        </div>
        <template v-else>
          <div ref="qaList" class="qa-messages">
            <p v-if="qaMessages.length === 0" class="empty">
              还没有提问。可以问这个收藏夹里讲了什么、有哪些不同观点，或让它指出资料不足的地方。
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
          <p class="qa-note">回答只基于收藏摘要，不是全文；引用可以打开原文核对。当前不调用生成模型。</p>
        </template>
      </section>

      <section v-if="activeTab === 'bubbles'" class="content-grid bubble-layout">
        <div class="panel">
          <div class="panel-heading"><h2>有泡泡的文章</h2><span>{{ articles.length }} 篇</span></div>
          <button v-for="article in articles" :key="article.article_key" class="article-row" :class="{ selected: selectedArticle?.article_key === article.article_key }" @click="selectArticle(article)">
            <span><strong>{{ article.title || "未命名文章" }}</strong><small>{{ article.author_name || "未标注作者" }} · {{ article.content_type }}</small></span>
            <span class="count">{{ article.bubble_count }}</span>
          </button>
          <div v-if="!loading && articles.length === 0" class="empty">
            <strong>还没有文章泡泡</strong><p>连接浏览器扩展后，在知乎回答或文章页点击右下角泡泡即可记录。</p>
          </div>
        </div>
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
          <p v-else class="empty">选择左侧文章，查看与之关联的想法和选中引用。</p>
        </div>
      </section>
    </template>
  </main>
</template>
