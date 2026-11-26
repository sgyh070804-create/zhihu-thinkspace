/**
 * 讨论室与后端的连接层。
 *
 * 只做四件事：登录、建讨论、收发消息、订阅 SSE。渲染和 3D 完全不碰。
 * 路径用相对地址，Vite 会把 /api 代理到后端 8000。
 */

const BASE = '';

async function request(path, options = {}) {
  const response = await fetch(BASE + path, {
    credentials: 'include',
    headers: { 'Content-Type': 'application/json' },
    ...options,
  });
  if (!response.ok) {
    let payload = {};
    try { payload = await response.json(); } catch (_) { /* 忽略非 JSON */ }
    const detail = payload.detail;
    const message = typeof detail === 'string'
      ? detail
      : (detail && (detail.message || detail.code)) || `HTTP ${response.status}`;
    const error = new Error(message);
    error.status = response.status;
    error.code = detail && detail.code;
    throw error;
  }
  return response.status === 204 ? null : response.json();
}

// 服务端的 role_id 对应到 3D 场景里的动作
const GESTURE_BY_ROLE = {
  explorer: 'explain',
  skeptic: 'question',
  weaver: 'open',
  user: 'talk',
};

export class CouncilClient {
  constructor() {
    this.discussion = null;
    this.cursor = 0;
    this.source = null;
    this.retryTimer = null;
    // 每次创建/切换讨论都 +1；异步响应回来时比对，防止旧讨论的结果串到新页面。
    this.epoch = 0;
    this.ended = false;
    this.onMessage = () => {};
    this.onDiscussion = () => {};
    this.onEvent = () => {};
    this.onConnection = () => {};
  }

  async ensureLogin() {
    const status = await request('/api/auth/status');
    if (status.authenticated) return status;
    // 只有未登录时才调 demo，避免每次刷新都新建一个用户
    return request('/api/auth/demo', { method: 'POST' });
  }

  async create(topic, maxTurns = 6) {
    const discussion = await request('/api/discussions', {
      method: 'POST',
      body: JSON.stringify({
        topic: String(topic || '今天我们聊点什么？').slice(0, 200),
        max_turns: maxTurns,
      }),
    });
    this.epoch += 1;
    this.ended = false;
    this.discussion = discussion;
    this.cursor = discussion.event_seq;
    return discussion;
  }

  async load(id) {
    const discussion = await request('/api/discussions/' + encodeURIComponent(id));
    this.epoch += 1;
    this.ended = false;
    this.discussion = discussion;
    this.cursor = 0;
    return discussion;
  }

  /** 拉全部历史：单讨论上限 500 条，一页 200 条要翻几次。 */
  async history(pageSize = 200) {
    const all = [];
    let after = 0;
    for (let guard = 0; guard < 20; guard += 1) {
      const data = await request(
        `/api/discussions/${this.discussion.id}/messages?after_seq=${after}&limit=${pageSize}`
      );
      all.push(...data.items);
      if (!data.has_more || data.items.length === 0) break;
      after = data.items[data.items.length - 1].seq;
    }
    return all;
  }

  async send(body) {
    const epoch = this.epoch;
    const data = await request(`/api/discussions/${this.discussion.id}/messages`, {
      method: 'POST',
      body: JSON.stringify({
        body,
        client_msg_id: `room-${Date.now()}-${Math.random().toString(16).slice(2, 8)}`,
      }),
    });
    if (epoch !== this.epoch) throw new Error('讨论已切换，这条结果已丢弃');
    return data.message;
  }

  /** 让编排器（E）选一位 AI 角色说一句。暂停、终态、达轮次上限时 advanced=false。 */
  async advance() {
    const epoch = this.epoch;
    const result = await request(`/api/discussions/${this.discussion.id}/advance`, {
      method: 'POST',
    });
    if (epoch !== this.epoch) throw new Error('讨论已切换，这条结果已丢弃');
    return result;
  }

  connect() {
    if (!this.discussion || this.ended) return;
    this.close();
    this.onConnection('connecting');

    const epoch = this.epoch;
    const path = `/api/discussions/${this.discussion.id}/stream?after_seq=${this.cursor}`;
    const source = new EventSource(path, { withCredentials: true });
    this.source = source;

    source.onopen = () => {
      if (epoch === this.epoch) this.onConnection('live');
    };

    const types = [
      'message.created',
      'discussion.paused', 'discussion.resumed',
      'discussion.stopped', 'discussion.finished',
      'stream.end', 'stream.timeout', 'error',
    ];

    types.forEach((type) => {
      source.addEventListener(type, (event) => {
        // 切换讨论后，旧连接可能还会送来几帧，直接丢弃
        if (epoch !== this.epoch) return;
        let data = {};
        try { data = JSON.parse(event.data); } catch (_) { /* 忽略 */ }
        if (typeof data.seq === 'number' && data.seq > this.cursor) {
          this.cursor = data.seq;
        }
        this.onEvent(type, data);

        if (type === 'message.created' && data.message) {
          this.onMessage(data.message);
        }
        // stream.end：讨论真的结束了，不再重连
        if (type === 'stream.end') {
          this.ended = true;
          this.close();
          this.onConnection('closed');
          if (this.discussion) {
            request('/api/discussions/' + this.discussion.id)
              .then((fresh) => { this.discussion = fresh; this.onDiscussion(fresh); })
              .catch(() => {});
          }
          return;
        }
        // stream.timeout：只是这条连接到了寿命上限，讨论还在继续。
        // 必须带 after_seq 重连，否则活跃讨论 10 分钟后就不再有新消息了。
        if (type === 'stream.timeout') {
          source.close();
          this.source = null;
          this.onConnection('timeout');
          clearTimeout(this.retryTimer);
          this.retryTimer = setTimeout(() => this.connect(), 2000);
        }
      });
    });

    source.onerror = () => {
      source.close();
      this.source = null;
      this.onConnection('reconnecting');
      clearTimeout(this.retryTimer);
      // 重连带 after_seq，断线期间的消息会补发
      this.retryTimer = setTimeout(() => this.connect(), 1500);
    };
  }

  close() {
    clearTimeout(this.retryTimer);
    if (this.source) {
      this.source.close();
      this.source = null;
    }
  }

  gestureFor(roleId) {
    return GESTURE_BY_ROLE[roleId] || 'explain';
  }
}
