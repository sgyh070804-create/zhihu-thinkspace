<script setup lang="ts">
import { onMounted, ref } from "vue";
import { api, ApiError } from "./api";
import UserProfile from "./components/UserProfile.vue";
import type {
  ArticleGroup,
  AuthStatus,
  Bubble,
  ContentItem,
  Favlist,
  Followee,
  Profile,
} from "./types";

type TabKey = "favorites" | "creations" | "followees" | "likes" | "comments" | "bubbles";
type ViewKey = "home" | "profile";

const tabs: { key: TabKey; label: string }[] = [
  { key: "favorites", label: "收藏" },
  { key: "creations", label: "创作" },
  { key: "followees", label: "关注" },
  { key: "likes", label: "点赞" },
  { key: "comments", label: "评论" },
  { key: "bubbles", label: "文章泡泡" },
];

const status = ref<AuthStatus | null>(null);
const profile = ref<Profile | null>(null);
const view = ref<ViewKey>("home");
const activeTab = ref<TabKey>("favorites");
const loading = ref(true);
const error = ref("");
const favlists = ref<Favlist[]>([]);
const recent = ref<ContentItem[]>([]);
const favoriteItems = ref<ContentItem[]>([]);
const selectedFavlist = ref<Favlist | null>(null);
const creations = ref<ContentItem[]>([]);
const followees = ref<Followee[]>([]);
const articles = ref<ArticleGroup[]>([]);
const bubbles = ref<Bubble[]>([]);
const selectedArticle = ref<ArticleGroup | null>(null);
const pairCode = ref("");
const pairLoading = ref(false);

function showError(reason: unknown) {
  error.value = reason instanceof ApiError ? reason.message : "操作失败，请检查服务是否已启动。";
}

async function loadFavorites() {
  const [lists, recentData] = await Promise.all([
    api<{ Items: Favlist[] }>("/zhihu/favorites/lists"),
    api<{ Items: ContentItem[] }>("/zhihu/favorites/recent"),
  ]);
  favlists.value = lists.Items || [];
  recent.value = recentData.Items || [];
}

async function loadCreations() {
  const data = await api<{ Items: ContentItem[] }>("/zhihu/contents?content_type=all");
  creations.value = data.Items || [];
}

async function loadFollowees() {
  const data = await api<{ Items: Followee[] }>("/zhihu/followees");
  followees.value = data.Items || [];
}

async function loadArticles() {
  const data = await api<{ items: ArticleGroup[] }>("/articles");
  articles.value = data.items;
}

async function loadActive() {
  if (!status.value?.authenticated || ["likes", "comments"].includes(activeTab.value)) return;
  loading.value = true;
  error.value = "";
  try {
    if (activeTab.value === "favorites") await loadFavorites();
    if (activeTab.value === "creations") await loadCreations();
    if (activeTab.value === "followees") await loadFollowees();
    if (activeTab.value === "bubbles") await loadArticles();
  } catch (reason) {
    showError(reason);
  } finally {
    loading.value = false;
  }
}

async function loadStatus() {
  loading.value = true;
  error.value = "";
  try {
    status.value = await api<AuthStatus>("/auth/status");
    if (status.value.authenticated) {
      profile.value = await api<Profile>("/zhihu/me").catch(() => null);
    }
    await loadActive();
  } catch (reason) {
    showError(reason);
  } finally {
    loading.value = false;
  }
}

async function loginDemo() {
  loading.value = true;
  try {
    await api("/auth/demo", { method: "POST" });
    await loadStatus();
  } catch (reason) {
    showError(reason);
  } finally {
    loading.value = false;
  }
}

function loginZhihu() {
  window.location.href = "/api/auth/zhihu/start";
}

async function logout() {
  await api("/auth/logout", { method: "POST" });
  status.value = { ...(status.value as AuthStatus), authenticated: false, mode: null };
  profile.value = null;
  view.value = "home";
  pairCode.value = "";
}

function selectTab(tab: TabKey) {
  activeTab.value = tab;
  error.value = "";
  void loadActive();
}

async function selectFavlist(list: Favlist) {
  selectedFavlist.value = list;
  favoriteItems.value = [];
  error.value = "";
  try {
    const data = await api<{ Items: ContentItem[] }>(
      `/zhihu/favorites/contents?favlist_url_token=${list.UrlToken}`,
    );
    favoriteItems.value = data.Items || [];
  } catch (reason) {
    showError(reason);
  }
}

async function selectArticle(article: ArticleGroup) {
  selectedArticle.value = article;
  try {
    const data = await api<{ items: Bubble[] }>(
      `/bubbles?article_key=${encodeURIComponent(article.article_key)}`,
    );
    bubbles.value = data.items;
  } catch (reason) {
    showError(reason);
  }
}

async function removeBubble(id: string) {
  if (!window.confirm("确定删除这条泡泡记录吗？")) return;
  try {
    await api(`/bubbles/${id}`, { method: "DELETE" });
    if (selectedArticle.value) await selectArticle(selectedArticle.value);
    await loadArticles();
  } catch (reason) {
    showError(reason);
  }
}

async function createPairCode() {
  pairLoading.value = true;
  pairCode.value = "";
  try {
    const data = await api<{ code: string }>("/extension/pair", { method: "POST" });
    pairCode.value = data.code;
  } catch (reason) {
    showError(reason);
  } finally {
    pairLoading.value = false;
  }
}

function formatDate(timestamp?: number) {
  if (!timestamp) return "未标注时间";
  return new Date(timestamp * 1000).toLocaleString("zh-CN");
}

onMounted(async () => {
  if (new URLSearchParams(window.location.search).get("auth") === "success") {
    window.history.replaceState({}, "", "/");
  }
  await loadStatus();
});
</script>

<template>
  <main class="shell">
    <header class="topbar">
      <a class="brand" href="/" aria-label="ThinkSpace 首页">
        <span class="brand-mark">T</span>
        <span><strong>ThinkSpace</strong><small>让阅读留下自己的思考</small></span>
      </a>
      <div v-if="status?.authenticated" class="account-actions">
        <button
          class="mode-badge clickable"
          :title="profile?.fullname || '查看用户信息'"
          aria-label="查看用户信息"
          @click="view = 'profile'"
        >
          <img v-if="profile?.avatar_path" class="badge-avatar" :src="profile.avatar_path" alt="" />
          {{ profile?.fullname || (status.mode === "demo" ? "本地演示" : "知乎已授权") }}
        </button>
        <button class="button secondary" @click="createPairCode" :disabled="pairLoading">
          {{ pairLoading ? "生成中…" : "连接阅读扩展" }}
        </button>
        <button class="text-button" @click="logout">退出</button>
      </div>
    </header>

    <section v-if="!status?.authenticated" class="hero">
      <div class="eyebrow">ZHIHU × THINKSPACE</div>
      <h1>读到的内容，<br /><em>长成自己的想法。</em></h1>
      <p class="hero-copy">连接知乎账号，集中查看公开收藏与创作；阅读时用悬浮泡泡记录疑问、引用和判断。</p>
      <div class="hero-actions">
        <button class="button primary" @click="loginZhihu" :disabled="!status?.oauth_configured">
          使用知乎账号登录
        </button>
        <button v-if="status?.demo_enabled" class="button secondary" @click="loginDemo">先体验本地演示</button>
      </div>
      <p v-if="status && !status.oauth_configured" class="setup-note">
        知乎登录链路已开发完成并验证。按赛事手册流程，OAuth App ID / App Key 将在 12 月 5 日作品提交入口开启后，
        随「创建项目」由赛事页面分配；拿到后填入根目录 .env 的两行配置并重启后端，此按钮即可真实登录。
        当前可先进入演示模式体验完整产品流程。
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

      <div v-if="error" class="error-banner">
        <span>{{ error }}</span><button @click="loadActive">重试</button>
      </div>

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
            <h3>{{ selectedFavlist.Title }} · 条目</h3>
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
            <article v-for="bubble in bubbles" :key="bubble.id" class="bubble-card">
              <time>{{ formatDate(bubble.created_at) }}</time>
              <blockquote v-if="bubble.quote">{{ bubble.quote }}</blockquote>
              <p>{{ bubble.body }}</p>
              <button class="text-button danger" @click="removeBubble(bubble.id)">删除</button>
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
