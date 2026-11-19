<script setup lang="ts">
import { onBeforeUnmount, onMounted, ref } from "vue";
import { api, ApiError } from "./api";
import { RequestScope } from "./request-scope";
import UserProfile from "./components/UserProfile.vue";
import ExperienceGallery from "./components/ExperienceGallery.vue";
import ThoughtBranches from "./components/ThoughtBranches.vue";
import type { ArticleGroup, AuthStatus, Bubble, ContentItem, Favlist, Followee, Profile } from "./types";

const isBranchPage = window.location.pathname.replace(/\/$/, "") === "/thought-branches";

type TabKey = "favorites" | "creations" | "followees" | "likes" | "comments" | "bubbles";
type ViewKey = "home" | "profile" | "experiences";
const tabs: { key: TabKey; label: string }[] = [
  { key: "favorites", label: "收藏" }, { key: "creations", label: "创作" },
  { key: "followees", label: "关注" }, { key: "likes", label: "点赞" },
  { key: "comments", label: "评论" }, { key: "bubbles", label: "文章泡泡" },
];
const status = ref<AuthStatus | null>(null), profile = ref<Profile | null>(null);
const view = ref<ViewKey>("home"), activeTab = ref<TabKey>("favorites");
const loading = ref(true), authBusy = ref(false), error = ref("");
const favlists = ref<Favlist[]>([]), recent = ref<ContentItem[]>([]), favoriteItems = ref<ContentItem[]>([]);
const selectedFavlist = ref<Favlist | null>(null), creations = ref<ContentItem[]>([]), followees = ref<Followee[]>([]);
const articles = ref<ArticleGroup[]>([]), bubbles = ref<Bubble[]>([]), selectedArticle = ref<ArticleGroup | null>(null);
const pairCode = ref(""), pairLoading = ref(false), detailLoading = ref(false), deletingId = ref("");
const authRequest = new RequestScope(), tabRequest = new RequestScope(), favoriteRequest = new RequestScope();
const articleRequest = new RequestScope(), pairRequest = new RequestScope(), deleteRequest = new RequestScope();
const dataRequests = [tabRequest, favoriteRequest, articleRequest, pairRequest, deleteRequest];

let retryOperation: () => Promise<void> = loadStatus;
function showError(reason: unknown, operation: () => Promise<void> = loadActive) {
  retryOperation = operation;
  error.value = reason instanceof ApiError ? reason.message : "操作失败，请检查服务是否已启动。";
}

function clearPrivateData() {
  dataRequests.forEach(request => request.invalidate());
  profile.value = null; favlists.value = []; recent.value = []; favoriteItems.value = [];
  selectedFavlist.value = null; creations.value = []; followees.value = [];
  articles.value = []; bubbles.value = []; selectedArticle.value = null;
  pairCode.value = ""; pairLoading.value = false; detailLoading.value = false;
  deletingId.value = ""; loading.value = false; error.value = "";
  activeTab.value = "favorites";
  if (view.value !== "experiences") view.value = "home";
}

async function loadActive() {
  const request = tabRequest.begin();
  if (!status.value?.authenticated || ["likes", "comments"].includes(activeTab.value)) {
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
    } else if (tab === "creations") {
      const data = await api<{ Items: ContentItem[] }>("/zhihu/contents?content_type=all", options);
      if (request.isCurrent()) creations.value = data.Items || [];
    } else if (tab === "followees") {
      const data = await api<{ Items: Followee[] }>("/zhihu/followees", options);
      if (request.isCurrent()) followees.value = data.Items || [];
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
    if (request.isCurrent()) await loadActive();
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
  favoriteRequest.invalidate(); articleRequest.invalidate(); detailLoading.value = false;
  selectedFavlist.value = null; favoriteItems.value = []; selectedArticle.value = null; bubbles.value = [];
  activeTab.value = tab; void loadActive();
}
async function selectFavlist(list: Favlist) {
  const request = favoriteRequest.begin(); selectedFavlist.value = list;
  favoriteItems.value = []; detailLoading.value = true; error.value = "";
  try {
    const data = await api<{ Items: ContentItem[] }>(`/zhihu/favorites/contents?favlist_url_token=${encodeURIComponent(list.UrlToken)}`, { signal: request.signal });
    if (request.isCurrent()) favoriteItems.value = data.Items || [];
  } catch (reason) { if (request.isCurrent()) showError(reason, () => selectFavlist(list)); }
  finally { if (request.isCurrent()) detailLoading.value = false; }
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

onMounted(async () => {
  if (isBranchPage) return;
  if (new URLSearchParams(window.location.search).get("auth") === "success") window.history.replaceState({}, "", "/");
  await loadStatus();
});
onBeforeUnmount(() => { authRequest.invalidate(); dataRequests.forEach(request => request.invalidate()); });
</script>

<template>
  <ThoughtBranches v-if="isBranchPage" />
  <main v-else class="shell">
    <header class="topbar">
      <a class="brand" href="/" aria-label="ThinkSpace 首页">
        <span class="brand-mark">T</span>
        <span><strong>ThinkSpace</strong><small>让阅读留下自己的思考</small></span>
      </a>
      <nav class="site-nav" aria-label="主导航">
        <button :class="{ active: view !== 'experiences' }" @click="view = 'home'">资料与想法</button>
        <button :class="{ active: view === 'experiences' }" @click="view = 'experiences'">思考体验</button>
        <a href="/thought-branches">思想分叉</a>
      </nav>
      <div v-if="status?.authenticated" class="account-actions">
        <button
          class="mode-badge clickable"
          :title="profile?.fullname || '查看用户信息'"
          aria-label="查看用户信息"
          @click="view = 'profile'"
          :disabled="authBusy"
        >
          <img v-if="profile?.avatar_path" class="badge-avatar" :src="profile.avatar_path" alt="" />
          {{ profile?.fullname || (status.mode === "demo" ? "本地演示" : "知乎已授权") }}
        </button>
        <button class="button secondary" @click="createPairCode" :disabled="pairLoading || authBusy">
          {{ pairLoading ? "生成中…" : "连接阅读扩展" }}
        </button>
        <button class="text-button" @click="logout" :disabled="authBusy">退出</button>
      </div>
    </header>

    <div v-if="error && view !== 'experiences'" class="error-banner" role="alert">
      <span>{{ error }}</span><button @click="retry">重试</button>
    </div>
    <ExperienceGallery v-if="view === 'experiences'" />
    <section v-else-if="!status?.authenticated" class="hero">
      <div class="eyebrow">ZHIHU × THINKSPACE</div>
      <h1>读到的内容，<br /><em>长成自己的想法。</em></h1>
      <p class="hero-copy">连接知乎账号，集中查看公开收藏与创作；阅读时用悬浮泡泡记录疑问、引用和判断。</p>
      <div class="hero-actions">
        <button class="button primary" @click="loginZhihu" :disabled="!status?.oauth_configured || authBusy">
          使用知乎账号登录
        </button>
        <button v-if="status?.demo_enabled" class="button secondary" @click="loginDemo" :disabled="authBusy">先体验本地演示</button>
        <button class="button secondary" @click="view = 'experiences'">先看思考体验</button>
      </div>
      <p v-if="status && !status.oauth_configured" class="setup-note">
        当前环境尚未配置真实知乎授权。登录骨架已提供，真实账号链路需配置凭证并完成联调。
        可以先体验演示资料、泡泡动画和预设讨论；演示内容不是你的知乎数据。
      </p>
      <div class="boundary-note">
        <strong>数据边界</strong>
        <span>只通过官方接口读取授权范围内的数据。收藏摘要不是全文；点赞与评论历史在公开文档中暂未开放。</span>
      </div>
    </section>

    <template v-else>
      <UserProfile v-if="view === 'profile'" @back="view = 'home'" />

      <template v-else>
      <section class="workspace-heading">
        <div>
          <div class="eyebrow">MY THINKSPACE</div>
          <h1>阅读资料与思考</h1>
        </div>
        <p v-if="status.oauth_expired" class="warning">知乎授权已过期，请退出后重新授权。</p>
      </section>

      <section v-if="pairCode" class="pair-panel">
        <div><strong>扩展一次性配对码</strong><span>5 分钟内粘贴到浏览器扩展，不要发给其他人。</span></div>
        <code>{{ pairCode }}</code>
        <button class="text-button" @click="pairCode = ''">关闭</button>
      </section>

      <nav class="tabs" aria-label="数据分类">
        <button
          v-for="tab in tabs"
          :key="tab.key"
          :class="{ active: activeTab === tab.key }"
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

      <section v-else-if="activeTab === 'creations'" class="panel">
        <div class="panel-heading"><h2>公开创作</h2><span>回答、文章、想法等</span></div>
        <div class="card-list">
          <article v-for="item in creations" :key="item.Url" class="content-card">
            <div class="content-meta">{{ item.ContentType }} · {{ formatDate(item.CreatedAt) }}</div>
            <a :href="item.Url" target="_blank" rel="noreferrer">{{ item.Title }}</a>
            <p>{{ item.Summary }}</p>
            <footer><span>公开摘要</span><span>{{ item.LikeCount || 0 }} 赞同 · {{ item.FavoriteCount || 0 }} 收藏</span></footer>
          </article>
        </div>
        <p v-if="!loading && creations.length === 0" class="empty">没有可展示的公开创作。</p>
      </section>

      <section v-else-if="activeTab === 'followees'" class="panel">
        <div class="panel-heading"><h2>关注用户</h2><span>公开范围</span></div>
        <a v-for="person in followees" :key="person.Url" class="person" :href="person.Url" target="_blank" rel="noreferrer">
          <span class="avatar">{{ person.Fullname.slice(0, 1) }}</span>
          <span><strong>{{ person.Fullname }}</strong><small>{{ person.Headline || "无简介" }}</small></span>
          <span>{{ person.FollowerCount }} 关注者</span>
        </a>
        <p v-if="!loading && followees.length === 0" class="empty">没有可展示的关注用户。</p>
      </section>

      <section v-else-if="activeTab === 'likes' || activeTab === 'comments'" class="panel capability-panel">
        <span class="capability-icon">!</span>
        <h2>{{ activeTab === "likes" ? "点赞历史" : "评论历史" }}暂未接入</h2>
        <p>截至 2026-11-14 查阅的知乎官方公开用户数据文档，没有提供这类历史记录接口。</p>
        <p>ThinkSpace 不会把内容上的累计{{ activeTab === "likes" ? "点赞数" : "评论数" }}误当成你的历史，也不会调用私有网页 API 绕过权限。</p>
        <a href="https://developer.zhihu.com/docs" target="_blank" rel="noreferrer">查看知乎开放平台文档</a>
      </section>

      <section v-else class="content-grid bubble-layout">
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
            <a class="source-link" :href="selectedArticle.source_url" target="_blank" rel="noreferrer">打开知乎原文 ↗</a>
            <p v-if="detailLoading" class="empty" role="status">正在加载想法…</p>
            <article v-for="bubble in bubbles" :key="bubble.id" class="bubble-card">
              <time>{{ formatDate(bubble.created_at) }}</time>
              <blockquote v-if="bubble.quote">{{ bubble.quote }}</blockquote>
              <p>{{ bubble.body }}</p>
              <button class="text-button danger" @click="removeBubble(bubble.id)" :disabled="deletingId === bubble.id">{{ deletingId === bubble.id ? "删除中…" : "删除" }}</button>
            </article>
          </template>
          <p v-else class="empty">选择左侧文章，查看与之关联的想法和选中引用。</p>
        </div>
      </section>
      </template>
    </template>

    <footer class="page-footer">ThinkSpace 首版接入骨架 · 凭证仅存服务端 · 收藏不等于认同</footer>
  </main>
</template>
