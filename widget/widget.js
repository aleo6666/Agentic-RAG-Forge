/*!
 * RAGForgeWidget — 可嵌入任意网页的智能客服聊天挂件
 * 纯原生 JS，零依赖。全局仅暴露 window.RAGForgeWidget 一个名字，
 * 其余变量/函数均封装在 IIFE 内；所有 CSS 类名带 rf- 前缀。
 *
 * 用法：
 *   new RAGForgeWidget({
 *     apiBase: 'http://localhost:8777',   // 后端地址
 *     apiKey:  'ragforge-dev-change-me',  // X-API-Key；留空则首次打开弹出设置窗口
 *     title:   '智能客服',
 *     placeholder: '请输入问题…'
 *   }).mount('#rf-widget-root');          // 不传参则自动注入到 <body>
 */
(function (global) {
  'use strict';

  var STORAGE_KEY = 'ragforge_widget_settings';
  var REQUEST_TIMEOUT = 120000; // Agentic 链路可能多轮检索+生成，超时放宽到 120s

  var DEFAULTS = {
    apiBase: 'http://localhost:8777',
    apiKey: '',
    title: '智能客服',
    placeholder: '请输入问题…'
  };

  // ────────────────────────── 工具函数 ──────────────────────────

  function trimSlash(url) {
    return String(url || '').replace(/\/+$/, '');
  }

  function loadSettings() {
    try {
      var raw = global.localStorage.getItem(STORAGE_KEY);
      return raw ? JSON.parse(raw) : {};
    } catch (e) {
      return {};
    }
  }

  function saveSettings(settings) {
    try {
      global.localStorage.setItem(STORAGE_KEY, JSON.stringify(settings));
    } catch (e) { /* 隐私模式等场景下静默失败 */ }
  }

  function el(tag, className, text) {
    var node = document.createElement(tag);
    if (className) node.className = className;
    if (text != null) node.textContent = text;
    return node;
  }

  function fmtTime(d) {
    var h = d.getHours();
    var m = d.getMinutes();
    return (h < 10 ? '0' : '') + h + ':' + (m < 10 ? '0' : '') + m;
  }

  function citationLabel(c, i) {
    if (c == null) return '引用 ' + (i + 1);
    if (typeof c === 'string') return c;
    if (typeof c === 'object') {
      return c.source || c.doc_id || c.document || c.title || ('引用 ' + (i + 1));
    }
    return String(c);
  }

  // ────────────────────────── 内联 SVG 图标 ──────────────────────────

  var ICON_CHAT = '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M21 11.5a8.38 8.38 0 0 1-.9 3.8 8.5 8.5 0 0 1-7.6 4.7 8.38 8.38 0 0 1-3.8-.9L3 21l1.9-5.7a8.38 8.38 0 0 1-.9-3.8 8.5 8.5 0 0 1 4.7-7.6 8.38 8.38 0 0 1 3.8-.9h.5a8.48 8.48 0 0 1 8 8v.5z"/></svg>';
  var ICON_CLOSE = '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><line x1="18" y1="6" x2="6" y2="18"/><line x1="6" y1="6" x2="18" y2="18"/></svg>';
  var ICON_GEAR = '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><circle cx="12" cy="12" r="3"/><path d="M19.4 15a1.65 1.65 0 0 0 .33 1.82l.06.06a2 2 0 0 1 0 2.83 2 2 0 0 1-2.83 0l-.06-.06a1.65 1.65 0 0 0-1.82-.33 1.65 1.65 0 0 0-1 1.51V21a2 2 0 0 1-2 2 2 2 0 0 1-2-2v-.09A1.65 1.65 0 0 0 9 19.4a1.65 1.65 0 0 0-1.82.33l-.06.06a2 2 0 0 1-2.83 0 2 2 0 0 1 0-2.83l.06-.06a1.65 1.65 0 0 0 .33-1.82 1.65 1.65 0 0 0-1.51-1H3a2 2 0 0 1-2-2 2 2 0 0 1 2-2h.09A1.65 1.65 0 0 0 4.6 9a1.65 1.65 0 0 0-.33-1.82l-.06-.06a2 2 0 0 1 0-2.83 2 2 0 0 1 2.83 0l.06.06a1.65 1.65 0 0 0 1.82.33H9a1.65 1.65 0 0 0 1-1.51V3a2 2 0 0 1 2-2 2 2 0 0 1 2 2v.09a1.65 1.65 0 0 0 1 1.51 1.65 1.65 0 0 0 1.82-.33l.06-.06a2 2 0 0 1 2.83 0 2 2 0 0 1 0 2.83l-.06.06a1.65 1.65 0 0 0-.33 1.82V9a1.65 1.65 0 0 0 1.51 1H21a2 2 0 0 1 2 2 2 2 0 0 1-2 2h-.09a1.65 1.65 0 0 0-1.51 1z"/></svg>';
  var ICON_SEND = '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><line x1="22" y1="2" x2="11" y2="13"/><polygon points="22 2 15 22 11 13 2 9 22 2"/></svg>';

  // ────────────────────────── 构造函数 ──────────────────────────

  function RAGForgeWidget(options) {
    options = options || {};
    var stored = loadSettings();

    this.config = {
      apiBase: trimSlash(options.apiBase || stored.apiBase || DEFAULTS.apiBase),
      // 显式传了 apiKey（含空串）以传入值为准；否则读 localStorage
      apiKey: options.apiKey != null ? options.apiKey : (stored.apiKey || DEFAULTS.apiKey),
      title: options.title || DEFAULTS.title,
      placeholder: options.placeholder || DEFAULTS.placeholder
    };

    this.sessionId = null;   // 同一挂件实例内复用，保证多轮上下文连续
    this.rounds = 0;
    this.busy = false;
    this.isOpen = false;
    this._welcomed = false;
    this._els = {};
  }

  RAGForgeWidget.version = '1.0.0';

  // ────────────────────────── 挂载 ──────────────────────────

  RAGForgeWidget.prototype.mount = function (selector) {
    var host = selector ? document.querySelector(selector) : null;
    if (!host) {
      host = el('div', 'rf-widget');
      document.body.appendChild(host);
    } else if (host.className.indexOf('rf-widget') === -1) {
      host.className = (host.className ? host.className + ' ' : '') + 'rf-widget';
    }
    this._build(host);
    return this;
  };

  RAGForgeWidget.prototype._build = function (host) {
    var self = this;
    var cfg = this.config;

    // 悬浮气泡按钮
    var bubble = el('button', 'rf-bubble');
    bubble.type = 'button';
    bubble.setAttribute('aria-label', '打开客服聊天');
    bubble.innerHTML = '<span class="rf-bubble-icon rf-icon-chat">' + ICON_CHAT + '</span>' +
                       '<span class="rf-bubble-icon rf-icon-close">' + ICON_CLOSE + '</span>';
    bubble.addEventListener('click', function () { self.toggle(); });

    // 聊天窗口
    var panel = el('div', 'rf-panel');
    panel.setAttribute('role', 'dialog');
    panel.setAttribute('aria-label', cfg.title);

    var header = el('div', 'rf-header');
    var headerText = el('div', 'rf-header-text');
    headerText.appendChild(el('div', 'rf-header-title', cfg.title));
    headerText.appendChild(el('div', 'rf-header-sub', 'RAG 智能问答 · 在线'));
    var headerActions = el('div', 'rf-header-actions');

    var settingsBtn = el('button', 'rf-icon-btn');
    settingsBtn.type = 'button';
    settingsBtn.title = '连接设置';
    settingsBtn.setAttribute('aria-label', '连接设置');
    settingsBtn.innerHTML = ICON_GEAR;
    settingsBtn.addEventListener('click', function () { self._openSettings(''); });

    var closeBtn = el('button', 'rf-icon-btn');
    closeBtn.type = 'button';
    closeBtn.title = '收起';
    closeBtn.setAttribute('aria-label', '收起');
    closeBtn.innerHTML = ICON_CLOSE;
    closeBtn.addEventListener('click', function () { self.close(); });

    headerActions.appendChild(settingsBtn);
    headerActions.appendChild(closeBtn);
    header.appendChild(headerText);
    header.appendChild(headerActions);

    var messages = el('div', 'rf-messages');

    var inputArea = el('div', 'rf-input-area');
    var input = el('textarea', 'rf-input');
    input.rows = 1;
    input.placeholder = cfg.placeholder;
    input.addEventListener('keydown', function (e) {
      // 中文输入法组词期间（IME composition）回车不应触发发送
      if (e.key === 'Enter' && !e.shiftKey && !e.isComposing && e.keyCode !== 229) {
        e.preventDefault();
        self._send();
      }
    });
    var sendBtn = el('button', 'rf-send-btn');
    sendBtn.type = 'button';
    sendBtn.title = '发送';
    sendBtn.setAttribute('aria-label', '发送');
    sendBtn.innerHTML = ICON_SEND;
    sendBtn.addEventListener('click', function () { self._send(); });

    inputArea.appendChild(input);
    inputArea.appendChild(sendBtn);

    panel.appendChild(header);
    panel.appendChild(messages);
    panel.appendChild(inputArea);

    // 设置弹窗
    var modalMask = el('div', 'rf-modal-mask');
    var modal = el('div', 'rf-modal');
    modal.appendChild(el('div', 'rf-modal-title', '连接设置'));
    var modalHint = el('div', 'rf-modal-hint');
    modal.appendChild(modalHint);

    var baseField = el('label', 'rf-field');
    baseField.appendChild(el('span', 'rf-field-label', '后端地址（apiBase）'));
    var baseInput = el('input', 'rf-field-input');
    baseInput.type = 'text';
    baseInput.placeholder = DEFAULTS.apiBase;
    baseField.appendChild(baseInput);

    var keyField = el('label', 'rf-field');
    keyField.appendChild(el('span', 'rf-field-label', 'API Key（X-API-Key）'));
    var keyInput = el('input', 'rf-field-input');
    keyInput.type = 'text';
    keyInput.placeholder = '后端 .env 中的 RAGFORGE_API_KEY';
    keyField.appendChild(keyInput);

    var actions = el('div', 'rf-modal-actions');
    var cancelBtn = el('button', 'rf-btn rf-btn-ghost', '取消');
    cancelBtn.type = 'button';
    cancelBtn.addEventListener('click', function () { self._closeSettings(); });
    var saveBtn = el('button', 'rf-btn rf-btn-primary', '保存并连接');
    saveBtn.type = 'button';
    saveBtn.addEventListener('click', function () {
      var newBase = trimSlash(baseInput.value) || DEFAULTS.apiBase;
      var newKey = keyInput.value.trim();
      self.config.apiBase = newBase;
      self.config.apiKey = newKey;
      saveSettings({ apiBase: newBase, apiKey: newKey });
      self.sessionId = null; // key 可能换了租户，会话作废重建
      self._closeSettings();
      if (newKey) {
        self._ensureSession().catch(function (err) {
          self._addErrorMessage(err);
        });
      }
    });
    actions.appendChild(cancelBtn);
    actions.appendChild(saveBtn);

    modal.appendChild(baseField);
    modal.appendChild(keyField);
    modal.appendChild(actions);
    modalMask.appendChild(modal);
    modalMask.addEventListener('click', function (e) {
      if (e.target === modalMask) self._closeSettings();
    });

    host.appendChild(bubble);
    host.appendChild(panel);
    host.appendChild(modalMask);

    this._els = {
      host: host,
      bubble: bubble,
      panel: panel,
      messages: messages,
      input: input,
      sendBtn: sendBtn,
      modalMask: modalMask,
      modalHint: modalHint,
      baseInput: baseInput,
      keyInput: keyInput
    };
  };

  // ────────────────────────── 展开 / 收起 ──────────────────────────

  RAGForgeWidget.prototype.open = function () {
    if (this.isOpen) return;
    this.isOpen = true;
    this._els.panel.className += ' rf-open';
    this._els.bubble.className += ' rf-bubble-open';

    if (!this._welcomed) {
      this._welcomed = true;
      this._addAssistantText('您好，我是' + this.config.title + '，请问有什么可以帮您？');
    }

    if (!this.config.apiKey) {
      this._openSettings('首次使用请先配置后端地址和 API Key');
    } else if (!this.sessionId) {
      var self = this;
      this._ensureSession().catch(function (err) {
        if (err && (err.status === 401 || err.status === 403)) {
          self._openSettings('API Key 校验失败（' + err.status + '），请检查后重新保存');
        }
        self._addErrorMessage(err);
      });
    }
    this._els.input.focus();
  };

  RAGForgeWidget.prototype.close = function () {
    if (!this.isOpen) return;
    this.isOpen = false;
    this._els.panel.className = this._els.panel.className.replace(' rf-open', '');
    this._els.bubble.className = this._els.bubble.className.replace(' rf-bubble-open', '');
  };

  RAGForgeWidget.prototype.toggle = function () {
    if (this.isOpen) this.close(); else this.open();
  };

  // ────────────────────────── 设置弹窗 ──────────────────────────

  RAGForgeWidget.prototype._openSettings = function (hint) {
    this._els.baseInput.value = this.config.apiBase;
    this._els.keyInput.value = this.config.apiKey;
    this._els.modalHint.textContent = hint || '';
    this._els.modalHint.style.display = hint ? '' : 'none';
    this._els.modalMask.className += ' rf-open';
  };

  RAGForgeWidget.prototype._closeSettings = function () {
    this._els.modalMask.className = this._els.modalMask.className.replace(' rf-open', '');
  };

  // ────────────────────────── 后端请求 ──────────────────────────

  RAGForgeWidget.prototype._request = function (path, payload) {
    var cfg = this.config;
    return new Promise(function (resolve, reject) {
      var ctrl = new AbortController();
      var timer = setTimeout(function () { ctrl.abort(); }, REQUEST_TIMEOUT);

      fetch(cfg.apiBase + path, {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
          'X-API-Key': cfg.apiKey || ''
        },
        body: JSON.stringify(payload || {}),
        signal: ctrl.signal
      }).then(function (res) {
        clearTimeout(timer);
        if (res.ok) {
          res.json().then(resolve, function () { resolve({}); });
          return;
        }
        res.json().catch(function () { return {}; }).then(function (body) {
          var err = new Error((body && body.detail) || ('HTTP ' + res.status));
          err.status = res.status;
          reject(err);
        });
      }).catch(function (e) {
        clearTimeout(timer);
        if (e && e.status != null) { reject(e); return; }
        var aborted = e && (e.name === 'AbortError');
        var err = new Error(aborted
          ? '请求超时，请稍后重试'
          : '无法连接后端服务（' + cfg.apiBase + '），请确认服务已启动');
        err.status = 0;
        reject(err);
      });
    });
  };

  RAGForgeWidget.prototype._ensureSession = function () {
    var self = this;
    if (this.sessionId) return Promise.resolve(this.sessionId);
    return this._request('/session', {}).then(function (data) {
      self.sessionId = data.session_id;
      return self.sessionId;
    });
  };

  // ────────────────────────── 发送消息 ──────────────────────────

  RAGForgeWidget.prototype._send = function () {
    var self = this;
    var input = this._els.input;
    var question = input.value.replace(/\s+$/,'').replace(/^\s+/,'');
    if (!question || this.busy) return;

    if (!this.config.apiKey) {
      this._openSettings('请先配置 API Key 再提问');
      return;
    }

    input.value = '';
    this._addUserMessage(question);
    this._setBusy(true);
    var typing = this._addTyping();

    function attempt(allowRetry) {
      return self._ensureSession()
        .then(function () {
          return self._request('/chat', { session_id: self.sessionId, question: question });
        })
        .catch(function (err) {
          // 会话过期（后端重启等）：作废后重建并重试一次
          if (err && err.status === 404 && allowRetry) {
            self.sessionId = null;
            return attempt(false);
          }
          throw err;
        });
    }

    attempt(true).then(function (data) {
      typing.remove();
      self.sessionId = data.session_id || self.sessionId;
      self.rounds = data.rounds || self.rounds;
      self._addAssistantMessage(data);
    }).catch(function (err) {
      typing.remove();
      self._addErrorMessage(err);
    }).then(function () {
      self._setBusy(false);
      self._els.input.focus();
    });
  };

  RAGForgeWidget.prototype._setBusy = function (busy) {
    this.busy = busy;
    this._els.sendBtn.disabled = busy;
    this._els.input.disabled = busy;
  };

  // ────────────────────────── 消息渲染 ──────────────────────────

  RAGForgeWidget.prototype._scrollToBottom = function () {
    var m = this._els.messages;
    m.scrollTop = m.scrollHeight;
  };

  RAGForgeWidget.prototype._msgRow = function (kind) {
    var row = el('div', 'rf-msg rf-msg-' + kind);
    if (kind === 'assistant' || kind === 'error') {
      var avatar = el('div', 'rf-avatar');
      avatar.innerHTML = ICON_CHAT;
      row.appendChild(avatar);
    }
    var main = el('div', 'rf-msg-main');
    row.appendChild(main);
    this._els.messages.appendChild(row);
    return main;
  };

  RAGForgeWidget.prototype._addUserMessage = function (text) {
    var main = this._msgRow('user');
    main.appendChild(el('div', 'rf-msg-bubble', text));
    var meta = el('div', 'rf-msg-meta');
    meta.appendChild(el('span', 'rf-time', fmtTime(new Date())));
    main.appendChild(meta);
    this._scrollToBottom();
  };

  RAGForgeWidget.prototype._addAssistantText = function (text) {
    var main = this._msgRow('assistant');
    main.appendChild(el('div', 'rf-msg-bubble', text));
    this._scrollToBottom();
  };

  RAGForgeWidget.prototype._addAssistantMessage = function (data) {
    var grounded = data.grounded === true;
    var citations = Array.isArray(data.citations) ? data.citations : [];

    var main = this._msgRow('assistant');
    main.appendChild(el('div', 'rf-msg-bubble', data.answer || '（空回答）'));

    var meta = el('div', 'rf-msg-meta');
    var badge = el('span', 'rf-badge ' + (grounded ? 'rf-badge-grounded' : 'rf-badge-ungrounded'),
      grounded ? '有引用' : '无引用');
    if (grounded && citations.length) {
      var labels = [];
      for (var i = 0; i < citations.length; i++) labels.push(citationLabel(citations[i], i));
      badge.title = '引用来源：' + labels.join('、');
    }
    meta.appendChild(badge);
    if (data.rounds) meta.appendChild(el('span', 'rf-rounds', '第 ' + data.rounds + ' 轮'));
    meta.appendChild(el('span', 'rf-time', fmtTime(new Date())));
    main.appendChild(meta);

    // 答不上来（无引用）→ 提供「转人工」占位按钮（纯 UI，不调后端）
    if (!grounded) {
      var humanBtn = el('button', 'rf-human-btn', '转人工');
      humanBtn.type = 'button';
      humanBtn.addEventListener('click', function () {
        humanBtn.parentNode.replaceChild(
          el('span', 'rf-human-note', '人工客服即将上线，已记录您的问题'), humanBtn);
      });
      main.appendChild(humanBtn);
    }
    this._scrollToBottom();
  };

  RAGForgeWidget.prototype._addTyping = function () {
    var main = this._msgRow('assistant');
    var bubbleBox = el('div', 'rf-msg-bubble rf-typing');
    bubbleBox.appendChild(el('span', 'rf-dot'));
    bubbleBox.appendChild(el('span', 'rf-dot'));
    bubbleBox.appendChild(el('span', 'rf-dot'));
    main.appendChild(bubbleBox);
    this._scrollToBottom();
    var row = main.parentNode;
    return { remove: function () { row.parentNode && row.parentNode.removeChild(row); } };
  };

  RAGForgeWidget.prototype._addErrorMessage = function (err) {
    var status = err && err.status;
    var text;
    if (status === 401) text = '未提供 API Key（401），请先完成连接设置。';
    else if (status === 403) text = 'API Key 无效（403），请检查后重新配置。';
    else if (status === 429) text = '请求过于频繁，请稍后再试（429）。';
    else text = (err && err.message) || '请求失败，请稍后重试。';

    var main = this._msgRow('error');
    main.appendChild(el('div', 'rf-msg-bubble', text));
    if (status === 401 || status === 403) {
      var self = this;
      var btn = el('button', 'rf-error-action', '打开设置');
      btn.type = 'button';
      btn.addEventListener('click', function () { self._openSettings(''); });
      main.appendChild(btn);
    }
    this._scrollToBottom();
  };

  // ────────────────────────── 导出（全局唯一名字） ──────────────────────────

  global.RAGForgeWidget = RAGForgeWidget;

})(window);
