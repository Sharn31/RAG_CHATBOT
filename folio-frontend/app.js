/* ============================================================
   Folio — frontend logic
   Talks to the PDF RAG Chatbot FastAPI backend:
     GET    /health
     POST   /upload          (multipart file) -> UploadResponse
     POST   /chat             {session_id, question} -> ChatResponse
     GET    /session/{id}    -> SessionInfo
     DELETE /session/{id}
   ============================================================ */

// Surface any uncaught error visibly instead of silently breaking the page.
// If you ever see a red banner at the top, screenshot it — that's the real bug.
window.addEventListener("error", (e) => {
  showErrorBanner(`Script error: ${e.message} (${e.filename}:${e.lineno})`);
});
window.addEventListener("unhandledrejection", (e) => {
  showErrorBanner(`Unhandled promise rejection: ${e.reason}`);
});
function showErrorBanner(message) {
  let banner = document.getElementById("jsErrorBanner");
  if (!banner) {
    banner = document.createElement("div");
    banner.id = "jsErrorBanner";
    banner.style.cssText =
      "position:fixed;top:0;left:0;right:0;z-index:9999;background:#A9463D;color:#fff;" +
      "font-family:monospace;font-size:12px;padding:8px 14px;white-space:pre-wrap;";
    document.body.prepend(banner);
  }
  banner.textContent = message;
}

(() => {
  "use strict";

  const DEFAULT_API_BASE = "http://127.0.0.1:8000";
  const STORAGE_KEYS = {
    apiBase: "folio.apiBase.v2",
    sessionId: "folio.sessionId.v2",
    filename: "folio.filename.v2",
  };

  // ---------- state ----------
  let apiBase = localStorage.getItem(STORAGE_KEYS.apiBase) || DEFAULT_API_BASE;
  let sessionId = localStorage.getItem(STORAGE_KEYS.sessionId) || null;
  let filename = localStorage.getItem(STORAGE_KEYS.filename) || null;
  let turnsCount = 0;
  let citationCounter = 0;

  // ---------- element refs ----------
  const el = {
    statusPill: document.getElementById("statusPill"),
    statusDot: document.getElementById("statusDot"),
    statusLabel: document.getElementById("statusLabel"),
    settingsBtn: document.getElementById("settingsBtn"),

    dropzone: document.getElementById("dropzone"),
    fileInput: document.getElementById("fileInput"),
    uploadProgress: document.getElementById("uploadProgress"),
    uploadProgressFill: document.getElementById("uploadProgressFill"),
    uploadProgressLabel: document.getElementById("uploadProgressLabel"),

    docCard: document.getElementById("docCard"),
    docFilename: document.getElementById("docFilename"),
    docStats: document.getElementById("docStats"),
    docSessionId: document.getElementById("docSessionId"),
    docTurns: document.getElementById("docTurns"),
    refreshSessionBtn: document.getElementById("refreshSessionBtn"),
    endSessionBtn: document.getElementById("endSessionBtn"),

    chatTitle: document.getElementById("chatTitle"),
    chatSubtitle: document.getElementById("chatSubtitle"),
    chatBody: document.getElementById("chatBody"),
    emptyState: document.getElementById("emptyState"),

    composerForm: document.getElementById("composerForm"),
    questionInput: document.getElementById("questionInput"),
    sendBtn: document.getElementById("sendBtn"),

    modalDialog: document.getElementById("settingsDialog"),
    apiBaseInput: document.getElementById("apiBaseInput"),
    modalSave: document.getElementById("modalSave"),

    toast: document.getElementById("toast"),
  };

  // ---------- helpers ----------
  function showToast(message, isError = false) {
    el.toast.textContent = message;
    el.toast.className = "toast" + (isError ? " error" : "");
    el.toast.hidden = false;
    clearTimeout(showToast._t);
    showToast._t = setTimeout(() => { el.toast.hidden = true; }, 3600);
  }

  function apiUrl(path) {
    return apiBase.replace(/\/+$/, "") + path;
  }

  function truncateMiddle(str, max = 22) {
    if (!str || str.length <= max) return str || "—";
    const half = Math.floor((max - 3) / 2);
    return str.slice(0, half) + "…" + str.slice(str.length - half);
  }

  function scrollChatToBottom() {
    el.chatBody.scrollTop = el.chatBody.scrollHeight;
  }

  function setEmptyState(visible) {
    el.emptyState.hidden = !visible;
  }

  // ---------- health check ----------
  async function checkHealth() {
    try {
      const res = await fetch(apiUrl("/health"), { method: "GET" });
      if (!res.ok) throw new Error("bad status");
      const data = await res.json();
      el.statusDot.className = "status-dot ok";
      el.statusLabel.textContent = data.status === "ok" ? "Connected" : "Connected";
    } catch (err) {
      el.statusDot.className = "status-dot bad";
      el.statusLabel.textContent = "Offline";
    }
  }

  // ---------- session / document card ----------
  function renderDocCard({ filename: fname, num_pages, num_chunks, sid }) {
    el.docCard.hidden = false;
    el.docFilename.textContent = fname || "—";
    const parts = [];
    if (num_pages !== undefined && num_pages !== null) parts.push(`${num_pages} page${num_pages === 1 ? "" : "s"}`);
    if (num_chunks !== undefined && num_chunks !== null) parts.push(`${num_chunks} chunks indexed`);
    el.docStats.textContent = parts.join(" · ") || "—";
    el.docSessionId.textContent = truncateMiddle(sid);
    el.docSessionId.title = sid || "";

    el.chatTitle.textContent = fname || "Document loaded";
    el.chatSubtitle.textContent = "Ask a question — answers are grounded in this PDF, with page citations.";

    el.questionInput.disabled = false;
    el.questionInput.placeholder = "Ask something about this document…";
    el.sendBtn.disabled = false;
  }

  function resetSessionUI() {
    sessionId = null;
    filename = null;
    turnsCount = 0;
    localStorage.removeItem(STORAGE_KEYS.sessionId);
    localStorage.removeItem(STORAGE_KEYS.filename);

    el.docCard.hidden = true;
    el.chatTitle.textContent = "No document loaded";
    el.chatSubtitle.textContent = "Upload a PDF on the left to start asking questions.";
    el.questionInput.disabled = true;
    el.questionInput.placeholder = "Upload a PDF to start asking questions";
    el.sendBtn.disabled = true;

    el.chatBody.querySelectorAll(".msg-row").forEach((n) => n.remove());
    setEmptyState(true);
  }

  async function refreshSessionInfo(showFeedback = false) {
    if (!sessionId) return;
    try {
      const res = await fetch(apiUrl(`/session/${encodeURIComponent(sessionId)}`));
      if (res.status === 404) {
        showToast("That session no longer exists on the server.", true);
        resetSessionUI();
        return;
      }
      if (!res.ok) throw new Error("Failed to fetch session");
      const data = await res.json();
      turnsCount = data.turns || 0;
      el.docTurns.textContent = String(turnsCount);
      renderDocCard({
        filename: data.filename,
        num_pages: data.num_pages,
        num_chunks: undefined,
        sid: sessionId,
      });
      if (data.num_pages !== undefined && data.num_pages !== null) {
        el.docStats.textContent = `${data.num_pages} page${data.num_pages === 1 ? "" : "s"}`;
      }
      if (showFeedback) showToast("Session refreshed.");
    } catch (err) {
      if (showFeedback) showToast("Couldn't reach the backend.", true);
    }
  }

  async function endSession() {
    if (!sessionId) return;
    const idToDelete = sessionId;
    try {
      const res = await fetch(apiUrl(`/session/${encodeURIComponent(idToDelete)}`), { method: "DELETE" });
      if (!res.ok && res.status !== 404) throw new Error("Failed to delete session");
      showToast("Session ended.");
    } catch (err) {
      showToast("Couldn't reach the backend to end the session.", true);
    } finally {
      resetSessionUI();
    }
  }

  // ---------- upload ----------
  function handleFiles(files) {
    if (!files || !files.length) return;
    const file = files[0];
    if (file.type !== "application/pdf" && !file.name.toLowerCase().endsWith(".pdf")) {
      showToast("Only PDF files are supported.", true);
      return;
    }
    uploadFile(file);
  }

  function uploadFile(file) {
    const formData = new FormData();
    formData.append("file", file);

    el.uploadProgress.hidden = false;
    el.uploadProgressFill.style.width = "6%";
    el.uploadProgressLabel.textContent = "Uploading…";
    el.dropzone.setAttribute("aria-busy", "true");

    const xhr = new XMLHttpRequest();
    xhr.open("POST", apiUrl("/upload"));

    xhr.upload.onprogress = (e) => {
      if (e.lengthComputable) {
        const pct = Math.min(60, Math.round((e.loaded / e.total) * 60));
        el.uploadProgressFill.style.width = pct + "%";
      }
    };
    xhr.upload.onload = () => {
      el.uploadProgressFill.style.width = "75%";
      el.uploadProgressLabel.textContent = "Extracting, chunking, embedding…";
    };

    xhr.onload = () => {
      el.dropzone.removeAttribute("aria-busy");
      let data;
      try { data = JSON.parse(xhr.responseText); } catch (e) { data = null; }

      if (xhr.status >= 200 && xhr.status < 300 && data) {
        el.uploadProgressFill.style.width = "100%";
        el.uploadProgressLabel.textContent = "Indexed.";
        setTimeout(() => { el.uploadProgress.hidden = true; el.uploadProgressFill.style.width = "0%"; }, 700);

        sessionId = data.session_id;
        filename = data.filename;
        turnsCount = 0;
        localStorage.setItem(STORAGE_KEYS.sessionId, sessionId);
        localStorage.setItem(STORAGE_KEYS.filename, filename);

        el.chatBody.querySelectorAll(".msg-row").forEach((n) => n.remove());
        setEmptyState(false);
        appendSystemMessage(`"${filename}" is indexed and ready. Ask anything covered in the document.`);

        renderDocCard({
          filename: data.filename,
          num_pages: data.num_pages,
          num_chunks: data.num_chunks,
          sid: data.session_id,
        });
        el.docTurns.textContent = "0";
        el.questionInput.focus();
        showToast(`Loaded "${data.filename}" — ${data.num_pages} pages, ${data.num_chunks} chunks.`);
      } else {
        el.uploadProgress.hidden = true;
        el.uploadProgressFill.style.width = "0%";
        const detail = (data && data.detail) ? data.detail : `Upload failed (${xhr.status}).`;
        showToast(detail, true);
      }
    };

    xhr.onerror = () => {
      el.dropzone.removeAttribute("aria-busy");
      el.uploadProgress.hidden = true;
      el.uploadProgressFill.style.width = "0%";
      showToast("Couldn't reach the backend. Check the API URL in settings.", true);
    };

    xhr.send(formData);
  }

  // ---------- chat rendering ----------
  function appendSystemMessage(text) {
    const row = document.createElement("div");
    row.className = "msg-row assistant";
    row.innerHTML = `
      <div class="msg-col">
        <div class="bubble">${escapeHtml(text)}</div>
      </div>`;
    el.chatBody.appendChild(row);
    scrollChatToBottom();
  }

  function appendUserMessage(text) {
    const row = document.createElement("div");
    row.className = "msg-row user";
    row.innerHTML = `
      <div class="msg-col">
        <div class="bubble">${escapeHtml(text)}</div>
      </div>`;
    el.chatBody.appendChild(row);
    scrollChatToBottom();
  }

  function appendPendingAssistant() {
    const row = document.createElement("div");
    row.className = "msg-row assistant pending-row";
    row.innerHTML = `
      <div class="msg-col">
        <div class="bubble pending">
          <span class="typing-dots"><span></span><span></span><span></span></span>
        </div>
      </div>`;
    el.chatBody.appendChild(row);
    scrollChatToBottom();
    return row;
  }

  function replacePendingWithAnswer(row, response) {
    const { answer, sources, in_scope } = response;
    const bubbleClass = in_scope ? "bubble" : "bubble out-of-scope";

    let citationsHtml = "";
    if (sources && sources.length) {
      const groupId = "cite-" + (citationCounter++);
      const tabs = sources.map((s, i) =>
        `<button type="button" class="citation-tab" data-group="${groupId}" data-index="${i}">p.${s.page}</button>`
      ).join("");
      const snippets = sources.map((s) =>
        `<div class="citation-snippet"><b>p.${s.page}</b>${escapeHtml(s.snippet)}</div>`
      ).join("");
      citationsHtml = `
        <div class="citations">${tabs}</div>
        <div class="citation-snippets" id="${groupId}" hidden>${snippets}</div>`;
    }

    row.querySelector(".msg-col").innerHTML = `
      <div class="${bubbleClass}">${escapeHtml(answer)}</div>
      ${citationsHtml}
      <div class="msg-meta">${in_scope ? "answered from document" : "outside document scope"}</div>
    `;
    row.classList.remove("pending-row");
    scrollChatToBottom();
  }

  function replacePendingWithError(row, message) {
    row.className = "msg-row error";
    row.querySelector(".msg-col").innerHTML = `<div class="bubble">${escapeHtml(message)}</div>`;
    scrollChatToBottom();
  }

  function escapeHtml(str) {
    const d = document.createElement("div");
    d.textContent = str == null ? "" : String(str);
    return d.innerHTML;
  }

  // delegate citation tab clicks
  el.chatBody.addEventListener("click", (e) => {
    const tab = e.target.closest(".citation-tab");
    if (!tab) return;
    const groupId = tab.dataset.group;
    const panel = document.getElementById(groupId);
    if (!panel) return;
    const isHidden = panel.hidden;
    panel.hidden = !isHidden;
    panel.parentElement.querySelectorAll(".citation-tab").forEach((t) => t.classList.remove("open"));
    if (isHidden) tab.classList.add("open");
    scrollChatToBottom();
  });

  // ---------- send question ----------
  async function sendQuestion(question) {
    if (!sessionId) {
      showToast("Upload a PDF first.", true);
      return;
    }
    setEmptyState(false);
    appendUserMessage(question);
    const pendingRow = appendPendingAssistant();
    el.sendBtn.disabled = true;

    try {
      const res = await fetch(apiUrl("/chat"), {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ session_id: sessionId, question }),
      });
      const data = await res.json().catch(() => null);

      if (res.status === 404) {
        replacePendingWithError(pendingRow, "This session has expired on the server. Please upload the PDF again.");
        resetSessionUI();
        return;
      }
      if (!res.ok) {
        const detail = (data && data.detail) ? data.detail : `Request failed (${res.status}).`;
        replacePendingWithError(pendingRow, detail);
        return;
      }

      replacePendingWithAnswer(pendingRow, data);
      turnsCount += 1;
      el.docTurns.textContent = String(turnsCount);
    } catch (err) {
      replacePendingWithError(pendingRow, "Couldn't reach the backend. Check the API URL in settings.");
    } finally {
      el.sendBtn.disabled = false;
    }
  }

  // ---------- events: upload ----------
  el.dropzone.addEventListener("click", () => el.fileInput.click());
  el.dropzone.addEventListener("keydown", (e) => {
    if (e.key === "Enter" || e.key === " ") { e.preventDefault(); el.fileInput.click(); }
  });
  el.fileInput.addEventListener("change", (e) => handleFiles(e.target.files));

  ["dragenter", "dragover"].forEach((evt) =>
    el.dropzone.addEventListener(evt, (e) => { e.preventDefault(); el.dropzone.classList.add("dragover"); })
  );
  ["dragleave", "drop"].forEach((evt) =>
    el.dropzone.addEventListener(evt, (e) => { e.preventDefault(); el.dropzone.classList.remove("dragover"); })
  );
  el.dropzone.addEventListener("drop", (e) => {
    handleFiles(e.dataTransfer.files);
  });

  // ---------- events: composer ----------
  el.composerForm.addEventListener("submit", (e) => {
    e.preventDefault();
    const text = el.questionInput.value.trim();
    if (!text) return;
    el.questionInput.value = "";
    el.questionInput.style.height = "auto";
    sendQuestion(text);
  });
  el.questionInput.addEventListener("keydown", (e) => {
    if (e.key === "Enter" && !e.shiftKey) {
      e.preventDefault();
      el.composerForm.requestSubmit();
    }
  });
  el.questionInput.addEventListener("input", () => {
    el.questionInput.style.height = "auto";
    el.questionInput.style.height = Math.min(140, el.questionInput.scrollHeight) + "px";
  });

  // ---------- events: session actions ----------
  el.refreshSessionBtn.addEventListener("click", () => refreshSessionInfo(true));
  el.endSessionBtn.addEventListener("click", () => {
    if (confirm("End this session? You'll need to re-upload the PDF to continue.")) {
      endSession();
    }
  });

  // ---------- events: settings dialog ----------
  // Native <dialog> handles Esc-to-close, backdrop click (via the click-outside
  // check below), and the Cancel button (a submit button inside a
  // method="dialog" form) automatically — none of that can get "stuck".
  function openModal() {
    el.apiBaseInput.value = apiBase;
    el.modalDialog.showModal();
    el.apiBaseInput.focus();
  }

  el.settingsBtn.addEventListener("click", openModal);

  // Click on the backdrop (outside the dialog's own box) closes it.
  el.modalDialog.addEventListener("click", (e) => {
    const rect = el.modalDialog.getBoundingClientRect();
    const inside =
      e.clientX >= rect.left && e.clientX <= rect.right &&
      e.clientY >= rect.top && e.clientY <= rect.bottom;
    if (!inside) el.modalDialog.close("cancel");
  });

  // Fires for every close: Esc, backdrop click, Cancel, or Save.
  el.modalDialog.addEventListener("close", async () => {
    if (el.modalDialog.returnValue !== "save") return; // cancelled/escaped — nothing to do
    let val = el.apiBaseInput.value.trim().replace(/\/+$/, "");
    if (!val) val = DEFAULT_API_BASE;
    apiBase = val;
    localStorage.setItem(STORAGE_KEYS.apiBase, apiBase);
    await checkHealth();
    showToast(`Backend URL set to ${apiBase}`);
  });

  // ---------- init ----------
  (async function init() {
    checkHealth();
    setInterval(checkHealth, 20000);

    if (sessionId) {
      setEmptyState(false);
      appendSystemMessage(`Restored session for "${filename || "your document"}". Ask another question, or end the session to start fresh.`);
      await refreshSessionInfo(false);
    } else {
      setEmptyState(true);
    }
  })();

})();