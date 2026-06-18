const state = {
    accessToken: null,
    sessionId: null,
    currentUser: null,
    lastTraceId: null,
    pendingApproval: null,
  };
  
  const el = {
    loginStatus: document.getElementById("loginStatus"),
    currentUser: document.getElementById("currentUser"),
    sessionIdText: document.getElementById("sessionIdText"),
    username: document.getElementById("username"),
    password: document.getElementById("password"),
    loginBtn: document.getElementById("loginBtn"),
  
    chatBox: document.getElementById("chatBox"),
    messageInput: document.getElementById("messageInput"),
    sendBtn: document.getElementById("sendBtn"),
  
    approvalBox: document.getElementById("approvalBox"),
    approvalText: document.getElementById("approvalText"),
    approveBtn: document.getElementById("approveBtn"),
    rejectBtn: document.getElementById("rejectBtn"),
  
    memoryBtn: document.getElementById("memoryBtn"),
    clearBtn: document.getElementById("clearBtn"),
    memoryOutput: document.getElementById("memoryOutput"),
  
    traceIdText: document.getElementById("traceIdText"),
    rateLimitText: document.getElementById("rateLimitText"),
  };
  
  function setLoading(isLoading) {
    el.sendBtn.disabled = isLoading;
    el.loginBtn.disabled = isLoading;
    el.messageInput.disabled = isLoading;
  }
  
  function updateStatus() {
    if (state.accessToken) {
      el.loginStatus.textContent = "已登录";
      el.loginStatus.className = "badge badge-green";
    } else {
      el.loginStatus.textContent = "未登录";
      el.loginStatus.className = "badge badge-gray";
    }
  
    el.currentUser.textContent = state.currentUser
      ? `${state.currentUser.username} (${state.currentUser.user_id})`
      : "-";
  
    el.sessionIdText.textContent = state.sessionId || "-";
    el.traceIdText.textContent = state.lastTraceId || "-";
  
    if (state.pendingApproval) {
      el.approvalBox.classList.remove("hidden");
      el.approvalText.textContent =
        `${state.pendingApproval.tool_name} ` +
        JSON.stringify(state.pendingApproval.args, null, 2);
    } else {
      el.approvalBox.classList.add("hidden");
      el.approvalText.textContent = "";
    }
  }
  
  function addMessage(role, text) {
    const row = document.createElement("div");
    row.className = `message ${role}`;
  
    const bubble = document.createElement("div");
    bubble.className = "bubble";
    bubble.textContent = text;
  
    row.appendChild(bubble);
    el.chatBox.appendChild(row);
    el.chatBox.scrollTop = el.chatBox.scrollHeight;
  }
  
  function addSystemMessage(text) {
    const row = document.createElement("div");
    row.className = "message system";
  
    const bubble = document.createElement("div");
    bubble.className = "bubble";
    bubble.textContent = text;
  
    row.appendChild(bubble);
    el.chatBox.appendChild(row);
    el.chatBox.scrollTop = el.chatBox.scrollHeight;
  }
  
  async function apiFetch(url, options = {}) {
    const headers = options.headers || {};
  
    const finalHeaders = {
      ...headers,
    };
  
    if (state.accessToken) {
      finalHeaders.Authorization = `Bearer ${state.accessToken}`;
    }
  
    const response = await fetch(url, {
      ...options,
      headers: finalHeaders,
    });
  
    let data = null;
  
    const contentType = response.headers.get("content-type") || "";
  
    if (contentType.includes("application/json")) {
      data = await response.json();
    } else {
      data = await response.text();
    }
  
    if (!response.ok) {
      const message =
        typeof data === "object" && data.detail
          ? data.detail
          : `请求失败：${response.status}`;
  
      const error = new Error(message);
      error.status = response.status;
      error.data = data;
      error.headers = response.headers;
      throw error;
    }
  
    return {
      data,
      headers: response.headers,
    };
  }
  
  async function login() {
    const username = el.username.value.trim();
    const password = el.password.value;
  
    if (!username || !password) {
      addSystemMessage("请输入用户名和密码。");
      return;
    }
  
    setLoading(true);
  
    try {
      const body = new URLSearchParams();
      body.set("username", username);
      body.set("password", password);
  
      const { data } = await apiFetch("/auth/login", {
        method: "POST",
        headers: {
          "Content-Type": "application/x-www-form-urlencoded",
        },
        body,
      });
  
      state.accessToken = data.access_token;
  
      const me = await apiFetch("/auth/me", {
        method: "GET",
      });
  
      state.currentUser = me.data;
  
      addSystemMessage(`登录成功：${state.currentUser.username}`);
      updateStatus();
    } catch (error) {
      addSystemMessage(`登录失败：${error.message}`);
    } finally {
      setLoading(false);
    }
  }
  
  function readRateLimit(data, headers) {
    if (data.rate_limit) {
      return `${data.rate_limit.remaining}/${data.rate_limit.limit}，重置约 ${data.rate_limit.retry_after_seconds}s`;
    }
  
    const remaining = headers.get("X-RateLimit-Remaining");
    const limit = headers.get("X-RateLimit-Limit");
    const reset = headers.get("X-RateLimit-Reset");
  
    if (remaining && limit) {
      return `${remaining}/${limit}，重置约 ${reset}s`;
    }
  
    return "-";
  }
  
  async function sendMessage(message) {
    if (!state.accessToken) {
      addSystemMessage("请先登录。");
      return;
    }
  
    const text = message.trim();
  
    if (!text) {
      return;
    }
  
    addMessage("user", text);
    el.messageInput.value = "";
  
    setLoading(true);
  
    try {
      const payload = {
        message: text,
      };
  
      if (state.sessionId) {
        payload.session_id = state.sessionId;
      }
  
      const { data, headers } = await apiFetch("/chat", {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
        },
        body: JSON.stringify(payload),
      });
  
      state.sessionId = data.session_id;
      state.lastTraceId = data.trace_id;
      state.pendingApproval = data.pending_approval || null;
  
      el.rateLimitText.textContent = readRateLimit(data, headers);
  
      addMessage("agent", data.answer);
  
      updateStatus();
    } catch (error) {
      if (error.status === 401) {
        addSystemMessage("登录已失效或未登录，请重新登录。");
        state.accessToken = null;
        state.currentUser = null;
        updateStatus();
      } else if (error.status === 429) {
        const retryAfter = error.headers?.get("Retry-After");
        addSystemMessage(`触发限流：${error.message}${retryAfter ? `，${retryAfter}s 后再试。` : ""}`);
      } else {
        addSystemMessage(`请求失败：${error.message}`);
      }
    } finally {
      setLoading(false);
    }
  }
  
  async function submitApproval(decision) {
    if (!state.accessToken) {
      addSystemMessage("请先登录。");
      return;
    }
  
    if (!state.sessionId) {
      addSystemMessage("当前还没有 session。");
      return;
    }
  
    if (!state.pendingApproval) {
      addSystemMessage("当前没有待确认操作。");
      return;
    }
  
    const displayText =
      decision === "approve"
        ? "[点击确认执行]"
        : "[点击拒绝执行]";
  
    addMessage("user", displayText);
  
    setLoading(true);
  
    try {
      const { data, headers } = await apiFetch(
        `/sessions/${state.sessionId}/approval`,
        {
          method: "POST",
          headers: {
            "Content-Type": "application/json",
          },
          body: JSON.stringify({
            decision,
          }),
        }
      );
  
      state.sessionId = data.session_id;
      state.lastTraceId = data.trace_id;
      state.pendingApproval = data.pending_approval || null;
  
      el.rateLimitText.textContent = readRateLimit(data, headers);
  
      addMessage("agent", data.answer);
  
      updateStatus();
    } catch (error) {
      if (error.status === 401) {
        addSystemMessage("登录已失效或未登录，请重新登录。");
        state.accessToken = null;
        state.currentUser = null;
        updateStatus();
      } else {
        addSystemMessage(`审批失败：${error.message}`);
      }
    } finally {
      setLoading(false);
    }
  }
  
  async function loadMemory() {
    if (!state.accessToken) {
      addSystemMessage("请先登录。");
      return;
    }
  
    if (!state.sessionId) {
      addSystemMessage("当前还没有 session。先发送一条消息。");
      return;
    }
  
    setLoading(true);
  
    try {
      const { data } = await apiFetch(`/sessions/${state.sessionId}/memory`, {
        method: "GET",
      });
  
      el.memoryOutput.textContent = JSON.stringify(data, null, 2);
    } catch (error) {
      addSystemMessage(`读取 Memory 失败：${error.message}`);
    } finally {
      setLoading(false);
    }
  }
  
  function clearPage() {
    el.chatBox.innerHTML = "";
    el.memoryOutput.textContent = "点击「查看 Memory」后显示。";
    el.rateLimitText.textContent = "-";
    state.sessionId = null;
    state.lastTraceId = null;
    state.pendingApproval = null;
    updateStatus();
  }
  
  function bindEvents() {
    el.loginBtn.addEventListener("click", login);
  
    el.sendBtn.addEventListener("click", () => {
      sendMessage(el.messageInput.value);
    });
  
    el.messageInput.addEventListener("keydown", (event) => {
      if (event.key === "Enter") {
        sendMessage(el.messageInput.value);
      }
    });
  
    el.approveBtn.addEventListener("click", () => {
        submitApproval("approve");
      });
      
      el.rejectBtn.addEventListener("click", () => {
        submitApproval("reject");
      });
    el.memoryBtn.addEventListener("click", loadMemory);
    el.clearBtn.addEventListener("click", clearPage);
  
    document.querySelectorAll("[data-demo]").forEach((button) => {
      button.addEventListener("click", () => {
        const message = button.getAttribute("data-demo");
        sendMessage(message);
      });
    });
  }
  
  bindEvents();
  updateStatus();
