/* ============================================================
   AwarePDF web UI (no build step, plain JS)
   Talks to app/server.py under /api
   ============================================================ */

"use strict";

const $ = (sel, root = document) => root.querySelector(sel);
const el = (tag, attrs = {}, ...children) => {
  const node = document.createElement(tag);
  for (const [k, v] of Object.entries(attrs)) {
    if (v == null || v === false) continue;
    if (k === "class") node.className = v;
    else if (k === "html") node.innerHTML = v;
    else if (k.startsWith("on")) node.addEventListener(k.slice(2), v);
    else node.setAttribute(k, v === true ? "" : v);
  }
  for (const child of children.flat()) {
    if (child == null || child === false) continue;
    node.append(child instanceof Node ? child : document.createTextNode(child));
  }
  return node;
};
const icon = (name) => {
  const svg = document.createElementNS("http://www.w3.org/2000/svg", "svg");
  const use = document.createElementNS("http://www.w3.org/2000/svg", "use");
  use.setAttribute("href", `#i-${name}`);
  svg.append(use);
  return svg;
};

const store = {
  get(key, fallback = null) {
    try { const v = localStorage.getItem(key); return v == null ? fallback : JSON.parse(v); } catch { return fallback; }
  },
  set(key, value) {
    try { localStorage.setItem(key, JSON.stringify(value)); } catch { /* storage full or blocked */ }
  },
  remove(key) {
    try { localStorage.removeItem(key); } catch { /* ignore */ }
  },
};

const state = {
  config: null,
  books: [],
  bookId: null,
  view: "chat",
  uploads: [],            // in-flight uploads {id, name, progress}
  pdfPage: 1,
  pdfBookId: null,
  figures: { bookId: null, items: [], shown: 40, from: "", to: "" },
  lightbox: { items: [], index: 0 },
  pending: new Set(),     // "bookId:kind" requests in flight
};

const VIEWS = ["chat", "summary", "topics", "keypoints", "figures"];

// ------------------------------------------------------------
// API
// ------------------------------------------------------------

async function api(path, { method = "GET", body } = {}) {
  const res = await fetch(`/api${path}`, {
    method,
    headers: body ? { "Content-Type": "application/json" } : undefined,
    body: body ? JSON.stringify(body) : undefined,
    credentials: "same-origin",
  });
  if (res.status === 401 && path !== "/login") {
    showLogin();
    throw new Error("Login required");
  }
  let data = null;
  try { data = await res.json(); } catch { /* empty body */ }
  if (!res.ok) {
    const detail = data && data.detail;
    throw new Error(typeof detail === "string" ? detail : `Request failed (${res.status})`);
  }
  return data;
}

// ------------------------------------------------------------
// Toasts
// ------------------------------------------------------------

function toast(message, kind = "info") {
  const node = el("div", { class: `toast ${kind === "error" ? "err" : ""}` },
    icon(kind === "error" ? "close" : "check"), message);
  $("#toasts").append(node);
  setTimeout(() => node.remove(), kind === "error" ? 6000 : 3200);
}

// ------------------------------------------------------------
// Markdown + math + clickable page citations
// ------------------------------------------------------------

marked.setOptions({ gfm: true, breaks: false });

const MATH_RE = /\$\$([\s\S]+?)\$\$|\\\[([\s\S]+?)\\\]|\\\(([\s\S]+?)\\\)|\$(?!\s)([^$\n]+?)(?<!\s)\$(?!\d)/g;
const CODE_SPLIT_RE = /(```[\s\S]*?```|`[^`\n]+`)/g;

function renderMarkdown(text) {
  const math = [];
  const protectedText = String(text).split(CODE_SPLIT_RE).map((part, i) => {
    if (i % 2 === 1) return part; // code: leave alone
    return part.replace(MATH_RE, (_, d1, d2, i1, i2) => {
      const display = d1 != null || d2 != null;
      math.push({ tex: d1 ?? d2 ?? i1 ?? i2, display });
      return `@@MATH${math.length - 1}@@`;
    });
  }).join("");

  let html = DOMPurify.sanitize(marked.parse(protectedText));
  html = html.replace(/@@MATH(\d+)@@/g, (_, n) => {
    const { tex, display } = math[Number(n)];
    try {
      return katex.renderToString(tex, { displayMode: display, throwOnError: false, output: "html" });
    } catch {
      return el("code", {}, tex).outerHTML;
    }
  });

  const root = el("div", { class: "prose", html });
  linkifyCitations(root);
  return root;
}

const CITE_RE = /\b(Pages?|pp?\.)\s*(\d{1,4})(?:\s*[-–—]\s*(\d{1,4}))?((?:\s*(?:,|and|&)\s*\d{1,4}(?:\s*[-–—]\s*\d{1,4})?)*)/gi;

function citeButton(label, page) {
  return el("button", { class: "cite", type: "button", "data-page": page, title: `Open page ${page}` }, label);
}

function linkifyCitations(root) {
  const walker = document.createTreeWalker(root, NodeFilter.SHOW_TEXT, {
    acceptNode(node) {
      return node.parentElement.closest("code, pre, .katex, a, button")
        ? NodeFilter.FILTER_REJECT : NodeFilter.FILTER_ACCEPT;
    },
  });
  const targets = [];
  while (walker.nextNode()) if (CITE_RE.test(walker.currentNode.nodeValue)) targets.push(walker.currentNode);

  for (const node of targets) {
    const text = node.nodeValue;
    const frag = document.createDocumentFragment();
    let last = 0;
    CITE_RE.lastIndex = 0;
    for (const m of text.matchAll(CITE_RE)) {
      frag.append(text.slice(last, m.index));
      const [, word, start, end, rest] = m;
      const label = end ? `${word.replace(/s$/i, "s")} ${start}–${end}` : `${word} ${start}`;
      frag.append(citeButton(label, start));
      if (rest) {
        for (const part of rest.split(/(\d{1,4}(?:\s*[-–—]\s*\d{1,4})?)/)) {
          const num = part.match(/^(\d{1,4})/);
          frag.append(num ? citeButton(part.replace(/\s*[-–—]\s*/, "–"), num[1]) : part);
        }
      }
      last = m.index + m[0].length;
    }
    frag.append(text.slice(last));
    node.replaceWith(frag);
  }
}

document.addEventListener("click", (e) => {
  const cite = e.target.closest("[data-page]");
  if (cite && state.bookId) {
    e.preventDefault();
    openPdf(Number(cite.dataset.page));
  }
});

// ------------------------------------------------------------
// Helpers
// ------------------------------------------------------------

const currentBook = () => state.books.find((b) => b.id === state.bookId) || null;

function timeAgo(ts) {
  const s = Math.max(1, Math.round((Date.now() - ts) / 1000));
  if (s < 60) return "just now";
  const m = Math.round(s / 60);
  if (m < 60) return `${m} min ago`;
  const h = Math.round(m / 60);
  if (h < 24) return `${h} h ago`;
  return new Date(ts).toLocaleDateString();
}

const SPINES = ["#1f5f5b", "#8a3b2e", "#2f4a7a", "#6b4f1d", "#4d3a6b", "#2d6a3e", "#7a2e52", "#3d5560"];
function spineColor(id) {
  let h = 0;
  for (const c of id) h = (h * 31 + c.charCodeAt(0)) >>> 0;
  return SPINES[h % SPINES.length];
}

function prettyName(name) {
  return name.replace(/\.pdf$/i, "").replace(/[_]+/g, " ").replace(/\s+/g, " ").trim();
}

function copyText(text, button) {
  navigator.clipboard?.writeText(text).then(() => {
    if (!button) return toast("Copied");
    const original = button.innerHTML;
    button.replaceChildren(icon("check"), "Copied");
    setTimeout(() => { button.innerHTML = original; }, 1500);
  }, () => toast("Couldn't copy", "error"));
}

function download(filename, text) {
  const url = URL.createObjectURL(new Blob([text], { type: "text/markdown" }));
  const a = el("a", { href: url, download: filename });
  document.body.append(a);
  a.click();
  a.remove();
  setTimeout(() => URL.revokeObjectURL(url), 1000);
}

// ------------------------------------------------------------
// Routing: #/b/<id>/<view>
// ------------------------------------------------------------

function navigate(bookId, view = "chat") {
  const target = bookId ? `#/b/${bookId}/${view}` : "#/";
  if (location.hash !== target) location.hash = target;
  else applyRoute();
}

function applyRoute() {
  const [, , id, view] = location.hash.split("/");
  const book = id && state.books.find((b) => b.id === id);
  const changedBook = (book ? book.id : null) !== state.bookId;
  state.bookId = book ? book.id : null;
  state.view = VIEWS.includes(view) ? view : "chat";
  if (changedBook && state.pdfBookId && state.pdfBookId !== state.bookId) closePdf();
  $("#app").classList.remove("nav-open");
  renderLibrary();
  renderTopbar();
  renderView();
}

window.addEventListener("hashchange", applyRoute);

// ------------------------------------------------------------
// Library (sidebar)
// ------------------------------------------------------------

function renderLibrary() {
  const list = $("#library");
  list.replaceChildren();

  for (const up of state.uploads) {
    list.append(el("li", { class: "book-item" },
      el("div", { class: "book-spine", style: "background: var(--line-strong)" }, "…"),
      el("div", { class: "book-meta" },
        el("div", { class: "book-name" }, prettyName(up.name)),
        el("div", { class: "book-sub" },
          `Uploading ${Math.round(up.progress * 100)}%`,
          el("span", { class: "mini-bar" }, el("i", { style: `width:${up.progress * 100}%` }))),
      ),
    ));
  }

  for (const book of state.books) {
    let sub;
    if (book.status === "ready") {
      const fig = book.figures_described;
      sub = el("div", { class: "book-sub" },
        `${book.pages ?? "?"} pages`, fig ? ` · figures ${fig.done}/${fig.total}` : "");
    } else if (book.status === "error") {
      sub = el("div", { class: "book-sub err" }, "Processing failed");
    } else {
      sub = el("div", { class: "book-sub" },
        book.status === "queued" ? "Queued" : `Processing ${Math.round(book.progress * 100)}%`,
        el("span", { class: "mini-bar" }, el("i", { style: `width:${book.progress * 100}%` })));
    }
    const name = prettyName(book.name);
    list.append(el("li", {
      class: `book-item ${book.id === state.bookId ? "active" : ""}`,
      tabindex: 0,
      title: book.name,
      onclick: () => navigate(book.id, book.id === state.bookId ? state.view : "chat"),
      onkeydown: (e) => { if (e.key === "Enter") navigate(book.id); },
    },
      el("div", { class: "book-spine", style: `background:${spineColor(book.id)}` }, name.charAt(0).toUpperCase()),
      el("div", { class: "book-meta" }, el("div", { class: "book-name" }, name), sub),
      book.status === "ready" || book.status === "error"
        ? el("button", {
          class: "book-del", "aria-label": `Remove ${name}`, title: "Remove from library",
          onclick: (e) => { e.stopPropagation(); deleteBook(book); },
        }, icon("trash"))
        : null,
    ));
  }

  if (!state.books.length && !state.uploads.length) {
    list.append(el("li", { class: "library-empty" }, "No books yet. Upload a PDF to start."));
  }
  $("#libraryCount").textContent = state.books.length || "";
}

async function refreshBooks() {
  try {
    state.books = await api("/books");
    setServerStatus(state.config?.llm_ready ? "ok" : "warn",
      state.config?.llm_ready ? "Connected" : "No API key on server");
  } catch (err) {
    if (err.message !== "Login required") setServerStatus("bad", "Server unreachable");
    return false;
  }
  return true;
}

function setServerStatus(kind, text) {
  const node = $("#serverStatus");
  node.className = `status-dot ${kind}`;
  $("em", node).textContent = text;
}

let pollTimer = null;
async function poll() {
  clearTimeout(pollTimer);
  const before = currentBook();
  const beforeStatus = before?.status;
  const beforeFigures = JSON.stringify(before?.figures_described ?? null);
  if (await refreshBooks()) {
    renderLibrary();
    const now = currentBook();
    if (state.bookId && !now) {
      navigate(null);
    } else if (now && now.status !== beforeStatus) {
      if (now.status === "ready" && beforeStatus) toast(`${prettyName(now.name)} is ready`);
      renderTopbar();
      renderView();
    } else if (now && now.status !== "ready" && now.status !== "error") {
      updateProcessing(now);
    } else if (now && JSON.stringify(now.figures_described ?? null) !== beforeFigures) {
      renderTopbar();
    }
  }
  const busy = state.books.some((b) => b.status === "queued" || b.status === "processing");
  pollTimer = setTimeout(poll, busy ? 2000 : 15000);
}

async function deleteBook(book) {
  if (!confirm(`Remove “${prettyName(book.name)}” from the library? Its index will be deleted too.`)) return;
  try {
    await api(`/books/${book.id}`, { method: "DELETE" });
  } catch (err) {
    return toast(err.message, "error");
  }
  for (const key of ["chat", "summary", "topics", "keypoints"]) store.remove(`${key}:${book.id}`);
  state.books = state.books.filter((b) => b.id !== book.id);
  toast("Book removed");
  if (state.bookId === book.id) navigate(null);
  else renderLibrary();
}

// ------------------------------------------------------------
// Upload
// ------------------------------------------------------------

function uploadFile(file) {
  if (!file) return;
  if (!/\.pdf$/i.test(file.name) && file.type !== "application/pdf") {
    return toast("Please choose a PDF file", "error");
  }
  const maxMb = state.config?.max_upload_mb ?? 200;
  if (file.size > maxMb * 1024 * 1024) {
    return toast(`That file is ${(file.size / 2 ** 20).toFixed(0)} MB. The limit is ${maxMb} MB.`, "error");
  }

  const up = { id: crypto.randomUUID?.() ?? String(Date.now()), name: file.name, progress: 0 };
  state.uploads.push(up);
  renderLibrary();

  const form = new FormData();
  form.append("file", file);
  const xhr = new XMLHttpRequest();
  xhr.open("POST", "/api/books");
  xhr.upload.onprogress = (e) => {
    if (!e.lengthComputable) return;
    up.progress = e.loaded / e.total;
    renderLibrary();
  };
  const done = () => {
    state.uploads = state.uploads.filter((u) => u !== up);
  };
  xhr.onload = async () => {
    done();
    let data = null;
    try { data = JSON.parse(xhr.responseText); } catch { /* not JSON */ }
    if (xhr.status === 401) { renderLibrary(); return showLogin(); }
    if (xhr.status >= 400 || !data) {
      renderLibrary();
      return toast(data?.detail || `Upload failed (${xhr.status})`, "error");
    }
    await refreshBooks();
    navigate(data.id, "chat");
    poll();
  };
  xhr.onerror = () => {
    done();
    renderLibrary();
    toast("Upload failed. Check your connection.", "error");
  };
  xhr.send(form);
}

$("#uploadBtn").addEventListener("click", () => $("#fileInput").click());
$("#fileInput").addEventListener("change", (e) => {
  uploadFile(e.target.files[0]);
  e.target.value = "";
});

// Drag & drop anywhere
let dragDepth = 0;
window.addEventListener("dragenter", (e) => {
  if (![...e.dataTransfer.types].includes("Files")) return;
  dragDepth++;
  $("#dropOverlay").hidden = false;
});
window.addEventListener("dragleave", () => {
  dragDepth = Math.max(0, dragDepth - 1);
  if (!dragDepth) $("#dropOverlay").hidden = true;
});
window.addEventListener("dragover", (e) => e.preventDefault());
window.addEventListener("drop", (e) => {
  e.preventDefault();
  dragDepth = 0;
  $("#dropOverlay").hidden = true;
  if (e.dataTransfer.files.length) uploadFile(e.dataTransfer.files[0]);
});

// ------------------------------------------------------------
// Top bar
// ------------------------------------------------------------

function renderTopbar() {
  const book = currentBook();
  const title = $("#bookTitle");
  const tabs = $("#tabs");
  const ready = book?.status === "ready";
  tabs.hidden = !ready;
  $("#togglePdf").hidden = !book;

  if (!book) {
    title.replaceChildren();
    return;
  }
  const fig = book.figures_described;
  title.replaceChildren(
    prettyName(book.name),
    el("small", {},
      [`${book.pages ?? "?"} pages`, ready ? `${book.chunks.toLocaleString()} passages indexed` : null,
        fig ? `describing figures ${fig.done}/${fig.total}` : null].filter(Boolean).join(" · ")),
  );
  title.title = book.name;
  for (const tab of tabs.querySelectorAll("button")) {
    tab.setAttribute("aria-selected", String(tab.dataset.view === state.view));
  }
}

$("#tabs").addEventListener("click", (e) => {
  const tab = e.target.closest("button[data-view]");
  if (tab) navigate(state.bookId, tab.dataset.view);
});

// ------------------------------------------------------------
// Views
// ------------------------------------------------------------

function renderView() {
  const view = $("#view");
  view.className = "view";
  view.replaceChildren();
  view.scrollTop = 0;
  const book = currentBook();

  if (!book) return renderWelcome(view);
  if (book.status === "error") return renderError(view, book);
  if (book.status !== "ready") return renderProcessing(view, book);

  if (state.view === "chat") renderChat(view, book);
  else if (state.view === "figures") renderFigures(view, book);
  else renderTool(view, book, state.view);
}

// ---------- welcome ----------

function renderWelcome(view) {
  const dz = el("div", {
    class: "dropzone", tabindex: 0, role: "button",
    onclick: () => $("#fileInput").click(),
    onkeydown: (e) => { if (e.key === "Enter" || e.key === " ") { e.preventDefault(); $("#fileInput").click(); } },
    ondragover: (e) => { e.preventDefault(); dz.classList.add("over"); },
    ondragleave: () => dz.classList.remove("over"),
  },
    el("div", { class: "dz-icon" }, icon("upload")),
    el("strong", {}, "Drop a textbook here, or click to browse"),
    el("span", {}, `PDF up to ${state.config?.max_upload_mb ?? 200} MB · 700+ page books are fine`),
  );

  const features = [
    ["chat", "Ask anything", "Answers grounded in your book, with page citations you can click."],
    ["summary", "Summaries", "The whole book, or one chapter in detail."],
    ["topics", "Topic outline", "Built from the book's real headings, in page order."],
    ["star", "Exam key points", "Definitions, formulas and rules worth remembering."],
    ["image", "Diagram search", "Figures are described by a vision model, so you can ask about them."],
  ];

  view.append(el("div", { class: "container welcome" },
    el("span", { class: "eyebrow" }, icon("sparkle"), "Free, open-weight models"),
    el("h1", { html: "Study your textbook<br>with a <em>tutor that cites pages</em>" }),
    el("p", { class: "lede" }, "Upload an engineering or science textbook. AwarePDF reads every page, diagrams included, then answers your questions and points you to the exact page."),
    dz,
    el("div", { class: "features" }, features.map(([ic, h, p]) =>
      el("div", { class: "feature" }, icon(ic), el("h3", {}, h), el("p", {}, p)))),
  ));
}

// ---------- processing ----------

const STEPS = [
  { label: "Upload received", until: 0 },
  { label: "Reading pages and layout", until: 0.8 },
  { label: "Extracting figures", until: 0.85 },
  { label: "Building the search index", until: 1 },
];

function renderProcessing(view, book) {
  const circumference = 2 * Math.PI * 58;
  view.append(el("div", { class: "container processing" },
    el("div", { class: "ring" },
      el("div", {
        html: `<svg viewBox="0 0 132 132"><circle class="track" cx="66" cy="66" r="58"/><circle class="fill" id="ringFill" cx="66" cy="66" r="58" stroke-dasharray="${circumference}" stroke-dashoffset="${circumference}"/></svg>`,
      }),
      el("div", { class: "pct", id: "ringPct" }),
    ),
    el("h2", {}, "Reading your book"),
    el("p", { class: "sub" }, `${book.pages ?? "?"} pages · usually about ${Math.max(1, Math.round((book.pages || 60) / 220))}–${Math.max(2, Math.round((book.pages || 60) / 120))} min. This only happens once.`),
    el("div", { class: "steps", id: "steps" }),
    el("div", { class: "msg", id: "procMsg" }),
    el("div", { class: "note" }, "You can leave this page. Processing continues on the server, and the book will be in your library when it's done."),
  ));
  updateProcessing(book);
}

function updateProcessing(book) {
  const fill = $("#ringFill");
  if (!fill) return;
  const circumference = 2 * Math.PI * 58;
  const p = book.progress || 0;
  fill.style.strokeDashoffset = String(circumference * (1 - p));
  $("#ringPct").replaceChildren(String(Math.round(p * 100)), el("small", {}, "%"));
  $("#procMsg").textContent = book.status === "queued" ? "Waiting for another book to finish…" : book.message || "";

  const steps = $("#steps");
  steps.replaceChildren();
  let active = false;
  STEPS.forEach((step, i) => {
    const done = i === 0 || p >= step.until;
    const now = !done && !active && book.status === "processing";
    if (now) active = true;
    steps.append(el("div", { class: `step ${done ? "done" : now ? "now" : ""}` },
      el("i", {}, done ? icon("check") : null), step.label));
  });
}

function renderError(view, book) {
  view.append(el("div", { class: "container" },
    el("div", { class: "error-card" },
      el("h2", {}, "This book couldn't be processed"),
      el("p", {}, book.message || "Unknown error"),
      el("button", { class: "btn", onclick: () => deleteBook(book) }, icon("trash"), "Remove it"),
    )));
}

// ---------- chat ----------

const SUGGESTIONS = [
  ["Overview", "What are the main topics covered in this book?"],
  ["Explain", "Explain the most important concept in chapter 1 in simple terms."],
  ["Formulas", "List the key formulas in chapter 2 and what each symbol means."],
  ["Diagrams", "Which diagrams in the book explain how the system works?"],
];

function chatKey(id) { return `chat:${id}`; }

function renderChat(view, book) {
  view.classList.add("chat-mode");
  const messages = store.get(chatKey(book.id), []);

  const scroller = el("div", { class: "messages", id: "messages" });
  const list = el("div", { class: "container", id: "messageList" });
  scroller.append(list);

  if (!messages.length) {
    list.append(el("div", { class: "chat-empty" },
      el("h2", {}, "What would you like to learn?"),
      el("p", {}, "Answers come only from this book. Click a highlighted page number to open that page."),
      el("div", { class: "suggestions" }, SUGGESTIONS.map(([tag, q]) =>
        el("button", { class: "suggestion", onclick: () => sendQuestion(q) }, el("small", {}, tag), q))),
    ));
  } else {
    messages.forEach((m) => list.append(renderMessage(m)));
  }
  if (state.pending.has(`${book.id}:chat`)) list.append(thinkingRow());

  const textarea = el("textarea", {
    id: "question", rows: 1, placeholder: "Ask about this book…", "aria-label": "Your question",
    maxlength: 2000,
  });
  const send = el("button", { class: "send", id: "sendBtn", "aria-label": "Send", disabled: true }, icon("send"));

  const resize = () => {
    textarea.style.height = "auto";
    textarea.style.height = `${Math.min(textarea.scrollHeight, 200)}px`;
    send.disabled = !textarea.value.trim() || state.pending.has(`${book.id}:chat`);
  };
  textarea.addEventListener("input", resize);
  textarea.addEventListener("keydown", (e) => {
    if (e.key === "Enter" && !e.shiftKey && !e.isComposing) {
      e.preventDefault();
      if (!send.disabled) sendQuestion(textarea.value);
    }
  });
  send.addEventListener("click", () => sendQuestion(textarea.value));

  const composer = el("div", { class: "composer-wrap" }, el("div", { class: "container" },
    el("div", { class: "composer" }, textarea, send),
    el("div", { class: "composer-hint" },
      el("span", { class: "kbd-hint", html: "<kbd>Enter</kbd> to send · <kbd>Shift</kbd>+<kbd>Enter</kbd> new line · <kbd>/</kbd> to focus" }),
      messages.length ? el("button", {
        onclick: () => {
          if (!confirm("Clear this conversation?")) return;
          store.remove(chatKey(book.id));
          renderView();
        },
      }, "Clear conversation") : el("span"),
    ),
  ));

  view.append(scroller, composer);
  requestAnimationFrame(() => {
    scroller.scrollTop = scroller.scrollHeight;
    if (matchMedia("(min-width: 861px)").matches) textarea.focus();
  });
}

function renderMessage(msg) {
  if (msg.role === "user") {
    return el("div", { class: "msg-row msg-user" }, el("div", { class: "bubble" }, msg.content));
  }
  if (msg.error) {
    return el("div", { class: "msg-row msg-ai" }, el("div", { class: "msg-error" }, msg.content));
  }

  const sources = msg.sources || [];
  const figures = sources.filter((s) => s.image_url);
  const row = el("div", { class: "msg-row msg-ai" },
    el("div", { class: "who" }, el("span", { class: "avatar" }, icon("sparkle")), "AwarePDF"),
    renderMarkdown(msg.content),
  );

  if (figures.length) {
    const items = figures.map((s) => ({ url: s.image_url, page: s.page }));
    row.append(el("div", { class: "figs-used" }, items.map((f, i) =>
      el("button", { onclick: () => openLightbox(items, i), title: `Figure on page ${f.page}` },
        el("img", { src: f.url, alt: `Figure from page ${f.page}`, loading: "lazy" }),
        el("span", {}, `p. ${f.page}`)))));
  }

  const copyBtn = el("button", { class: "btn ghost sm", onclick: () => copyText(msg.content, copyBtn) }, icon("copy"), "Copy");
  const tools = el("div", { class: "msg-tools" }, copyBtn);

  if (sources.length) {
    const details = el("details", { class: "sources" },
      el("summary", {}, icon("book"), `${sources.length} sources`),
      el("div", { class: "source-list" }, sources.map((s, i) => {
        const pages = s.page_end && s.page_end !== s.page ? `pp. ${s.page}–${s.page_end}` : `p. ${s.page}`;
        return el("button", { class: "source", "data-page": s.page, title: "Open this page" },
          el("b", {}, `Source ${i + 1}${s.content_type === "image_description" ? " · figure" : ""}`, el("em", {}, pages)),
          s.section ? el("span", { class: "sec" }, s.section) : null,
          el("span", { class: "pv" }, s.preview));
      })),
    );
    row.append(tools, details);
  } else {
    row.append(tools);
  }
  return row;
}

function thinkingRow() {
  return el("div", { class: "msg-row msg-ai", id: "thinking" },
    el("div", { class: "who" }, el("span", { class: "avatar" }, icon("sparkle")), "AwarePDF"),
    el("div", { class: "thinking" },
      el("span", { class: "dots" }, el("i"), el("i"), el("i")),
      el("span", { id: "thinkingText" }, "Searching the book…")));
}

async function sendQuestion(raw) {
  const question = String(raw || "").trim();
  const book = currentBook();
  if (!question || !book) return;
  const key = `${book.id}:chat`;
  if (state.pending.has(key)) return;

  const history = store.get(chatKey(book.id), []);
  const payloadHistory = history.filter((m) => !m.error).map(({ role, content }) => ({ role, content }));
  history.push({ role: "user", content: question });
  store.set(chatKey(book.id), history);
  state.pending.add(key);
  renderView();

  const stages = ["Searching the book…", "Ranking the best passages…", "Writing the answer…"];
  let stage = 0;
  const stageTimer = setInterval(() => {
    stage = Math.min(stage + 1, stages.length - 1);
    const t = $("#thinkingText");
    if (t) t.textContent = stages[stage];
  }, 1800);

  let reply;
  try {
    const result = await api(`/books/${book.id}/ask`, {
      method: "POST", body: { question, history: payloadHistory.slice(-8) },
    });
    reply = { role: "assistant", content: result.answer, sources: result.sources };
  } catch (err) {
    reply = { role: "assistant", content: err.message, error: true };
  } finally {
    clearInterval(stageTimer);
    state.pending.delete(key);
  }

  const updated = store.get(chatKey(book.id), []);
  updated.push(reply);
  store.set(chatKey(book.id), updated);

  if (state.bookId === book.id && state.view === "chat") {
    $("#thinking")?.remove();
    const list = $("#messageList");
    list.append(renderMessage(reply));
    const scroller = $("#messages");
    const replyNode = list.lastElementChild;
    scroller.scrollTop = Math.max(0, replyNode.offsetTop - 24);
    $("#question")?.dispatchEvent(new Event("input"));
  } else if (!reply.error) {
    toast(`Answer ready in ${prettyName(book.name)}`);
  }
}

// ---------- summary / topics / key points ----------

const TOOLS = {
  summary: {
    title: "Summary",
    lede: "A whole-book overview, or a detailed summary of one chapter or topic.",
    placeholder: "Optional focus, e.g. “Chapter 4” or “gradient descent”",
    button: "Summarize",
    focus: true,
  },
  topics: {
    title: "Topics",
    lede: "The book's chapters and sections as a clean outline. Click a page to jump there.",
    button: "Build outline",
    focus: false,
  },
  keypoints: {
    title: "Key points",
    lede: "Definitions, formulas and rules worth remembering for the exam.",
    placeholder: "Optional topic, e.g. “neural networks”",
    button: "Extract key points",
    focus: true,
  },
};

function renderTool(view, book, kind) {
  const tool = TOOLS[kind];
  const key = `${kind}:${book.id}`;
  const saved = store.get(key);
  const busy = state.pending.has(`${book.id}:${kind}`);

  const input = tool.focus
    ? el("input", { class: "field", id: "focusInput", placeholder: tool.placeholder, value: saved?.focus || "", maxlength: 300 })
    : null;
  const button = el("button", { class: "btn primary", type: "submit", disabled: busy },
    icon(saved ? "refresh" : "sparkle"), busy ? "Working…" : saved ? "Generate again" : tool.button);

  const form = el("form", {
    class: "tool-form",
    onsubmit: (e) => { e.preventDefault(); generate(book, kind, input ? input.value.trim() : ""); },
  }, input, button);

  const wrap = el("div", { class: "container tool" },
    el("div", { class: "tool-head" }, el("h2", {}, tool.title), el("p", {}, tool.lede)),
    form,
    el("div", { id: "toolResult" }),
  );
  view.append(wrap);
  renderToolResult(book, kind);
}

function renderToolResult(book, kind) {
  const slot = $("#toolResult");
  if (!slot) return;
  slot.replaceChildren();
  const saved = store.get(`${kind}:${book.id}`);

  if (state.pending.has(`${book.id}:${kind}`)) {
    const started = state.pending_started?.[`${book.id}:${kind}`] || Date.now();
    const note = el("div", { class: "skeleton-note" });
    const tick = () => { note.textContent = `Reading across the book… ${Math.round((Date.now() - started) / 1000)}s`; };
    tick();
    const timer = setInterval(() => { if (!note.isConnected) clearInterval(timer); else tick(); }, 1000);
    slot.append(el("div", { class: "result-card" },
      el("div", { class: "skeleton" }, Array.from({ length: 9 }, () => el("i"))), note));
    return;
  }
  if (!saved) return;

  const copyBtn = el("button", { class: "btn ghost sm", onclick: () => copyText(saved.content, copyBtn) }, icon("copy"), "Copy");
  slot.append(el("div", { class: "result-card" },
    el("div", { class: "result-bar" },
      el("span", {}, [saved.focus ? `Focus: ${saved.focus}` : "Whole book", timeAgo(saved.at)].join(" · ")),
      copyBtn,
      el("button", {
        class: "btn ghost sm",
        onclick: () => download(`${prettyName(book.name)} - ${TOOLS[kind].title}.md`, saved.content),
      }, icon("download"), "Download"),
    ),
    renderMarkdown(saved.content),
  ));
}

async function generate(book, kind, focus) {
  const pendingKey = `${book.id}:${kind}`;
  if (state.pending.has(pendingKey)) return;
  state.pending.add(pendingKey);
  state.pending_started = { ...(state.pending_started || {}), [pendingKey]: Date.now() };
  if (state.bookId === book.id && state.view === kind) renderView();

  try {
    const { content } = await api(`/books/${book.id}/${kind}`, { method: "POST", body: { focus: focus || null } });
    store.set(`${kind}:${book.id}`, { content, focus, at: Date.now() });
  } catch (err) {
    toast(err.message, "error");
  } finally {
    state.pending.delete(pendingKey);
  }
  if (state.bookId === book.id && state.view === kind) renderView();
  else toast(`${TOOLS[kind].title} ready for ${prettyName(book.name)}`);
}

// ---------- figures ----------

async function renderFigures(view, book) {
  const wrap = el("div", { class: "container" });
  view.append(el("div", { class: "figures" }, wrap));
  const fig = book.figures_described;

  const fromInput = el("input", { type: "number", min: 1, placeholder: "from", value: state.figures.from, "aria-label": "From page" });
  const toInput = el("input", { type: "number", min: 1, placeholder: "to", value: state.figures.to, "aria-label": "To page" });
  const onFilter = () => {
    state.figures.from = fromInput.value;
    state.figures.to = toInput.value;
    state.figures.shown = 40;
    drawGrid();
  };
  fromInput.addEventListener("input", onFilter);
  toInput.addEventListener("input", onFilter);

  const subtitle = el("p", {}, "Loading figures…");
  const grid = el("div");
  wrap.append(
    el("div", { class: "fig-toolbar" },
      el("div", {}, el("h2", {}, "Figures"), subtitle),
      el("label", { class: "fig-filter" }, "Pages", fromInput, "–", toInput),
    ),
    grid,
  );

  if (state.figures.bookId !== book.id) {
    try {
      state.figures = { bookId: book.id, items: await api(`/books/${book.id}/images`), shown: 40, from: "", to: "" };
      fromInput.value = "";
      toInput.value = "";
    } catch (err) {
      subtitle.textContent = err.message;
      return;
    }
  }

  function filtered() {
    const from = Number(state.figures.from) || 0;
    const to = Number(state.figures.to) || Infinity;
    return state.figures.items.filter((f) => f.page >= from && f.page <= to);
  }

  function drawGrid() {
    const items = filtered();
    const total = state.figures.items.length;
    subtitle.textContent = total
      ? `${total} figures extracted${fig ? ` · ${fig.done}/${fig.total} described so far, the rest are being made searchable` : ". The largest ones are searchable in Ask."}`
      : "";
    grid.replaceChildren();
    if (!total) {
      grid.append(el("p", { class: "center-msg" }, "No figures were extracted from this book."));
      return;
    }
    if (!items.length) {
      grid.append(el("p", { class: "center-msg" }, "No figures in that page range."));
      return;
    }
    const shown = items.slice(0, state.figures.shown);
    grid.append(el("div", { class: "fig-grid" }, shown.map((f, i) =>
      el("button", { class: "fig", onclick: () => openLightbox(items, i) },
        el("div", { class: "fig-img" }, el("img", { src: f.url, alt: `Figure on page ${f.page}`, loading: "lazy" })),
        el("span", {}, `Page ${f.page}`)))));
    if (items.length > shown.length) {
      grid.append(el("div", { class: "load-more" },
        el("button", {
          class: "btn",
          onclick: () => { state.figures.shown += 40; drawGrid(); },
        }, `Show more (${items.length - shown.length} left)`)));
    }
  }
  drawGrid();
}

// ------------------------------------------------------------
// Lightbox
// ------------------------------------------------------------

function openLightbox(items, index) {
  state.lightbox = { items, index };
  $("#lightbox").hidden = false;
  showLightboxItem();
}

function showLightboxItem() {
  const { items, index } = state.lightbox;
  const item = items[index];
  $("#lbImg").src = item.url;
  $("#lbImg").alt = `Figure on page ${item.page}`;
  $("#lbCaption").textContent = `Page ${item.page} · ${index + 1} of ${items.length}`;
  $("#lbPrev").hidden = items.length < 2;
  $("#lbNext").hidden = items.length < 2;
}

function stepLightbox(delta) {
  const { items } = state.lightbox;
  state.lightbox.index = (state.lightbox.index + delta + items.length) % items.length;
  showLightboxItem();
}

const closeLightbox = () => { $("#lightbox").hidden = true; };
$("#lbClose").addEventListener("click", closeLightbox);
$("#lbPrev").addEventListener("click", () => stepLightbox(-1));
$("#lbNext").addEventListener("click", () => stepLightbox(1));
$("#lightbox").addEventListener("click", (e) => { if (e.target.id === "lightbox") closeLightbox(); });
$("#lbOpenPage").addEventListener("click", () => {
  const item = state.lightbox.items[state.lightbox.index];
  closeLightbox();
  openPdf(item.page);
});

// ------------------------------------------------------------
// PDF panel
// ------------------------------------------------------------

function pdfUrl(bookId, page) {
  return `/api/books/${bookId}/file#page=${page}`;
}

function openPdf(page) {
  const book = currentBook();
  if (!book) return;
  const total = book.pages || Infinity;
  page = Math.min(Math.max(1, Number(page) || 1), total);
  state.pdfPage = page;

  const frame = $("#pdfFrame");
  const panel = $("#pdfPanel");
  const url = pdfUrl(book.id, page);
  // Built-in PDF viewers ignore fragment-only changes, so reload (the file is cached)
  frame.src = "about:blank";
  requestAnimationFrame(() => { frame.src = url; });
  state.pdfBookId = book.id;
  panel.hidden = false;
  $("#pdfPageInput").value = page;
  $("#pdfPageInput").max = book.pages || "";
  $("#pdfPageTotal").textContent = book.pages ? `of ${book.pages}` : "";
  $("#pdfOpenTab").href = url;
  $("#togglePdf").setAttribute("aria-pressed", "true");
}

function closePdf() {
  $("#pdfPanel").hidden = true;
  $("#pdfFrame").src = "about:blank";
  state.pdfBookId = null;
  $("#togglePdf").setAttribute("aria-pressed", "false");
}

$("#togglePdf").addEventListener("click", () => {
  if ($("#pdfPanel").hidden) openPdf(state.pdfPage || 1);
  else closePdf();
});
$("#pdfClose").addEventListener("click", closePdf);
$("#pdfPrev").addEventListener("click", () => openPdf(state.pdfPage - 1));
$("#pdfNext").addEventListener("click", () => openPdf(state.pdfPage + 1));
$("#pdfPageInput").addEventListener("change", (e) => openPdf(e.target.value));

// Resizable panel
(() => {
  const handle = $("#pdfResize");
  const saved = store.get("pdfWidth");
  if (saved) document.documentElement.style.setProperty("--pdf-w", `${saved}px`);
  handle.addEventListener("pointerdown", (e) => {
    e.preventDefault();
    handle.classList.add("dragging");
    document.body.classList.add("resizing");
    const move = (ev) => {
      const width = Math.min(window.innerWidth * 0.7, Math.max(320, window.innerWidth - ev.clientX));
      document.documentElement.style.setProperty("--pdf-w", `${width}px`);
      store.set("pdfWidth", Math.round(width));
    };
    const up = () => {
      handle.classList.remove("dragging");
      document.body.classList.remove("resizing");
      window.removeEventListener("pointermove", move);
      window.removeEventListener("pointerup", up);
    };
    window.addEventListener("pointermove", move);
    window.addEventListener("pointerup", up);
  });
})();

// ------------------------------------------------------------
// Theme, mobile nav, keyboard
// ------------------------------------------------------------

$("#themeToggle").addEventListener("click", () => {
  const root = document.documentElement;
  const isDark = root.dataset.theme
    ? root.dataset.theme === "dark"
    : matchMedia("(prefers-color-scheme: dark)").matches;
  root.dataset.theme = isDark ? "light" : "dark";
  try { localStorage.setItem("theme", root.dataset.theme); } catch { /* ignore */ }
});

$("#openSidebar").addEventListener("click", () => $("#app").classList.add("nav-open"));
$("#closeSidebar").addEventListener("click", () => $("#app").classList.remove("nav-open"));
$("#scrim").addEventListener("click", () => $("#app").classList.remove("nav-open"));

document.addEventListener("keydown", (e) => {
  const typing = e.target.closest("input, textarea, [contenteditable]");
  if (!$("#lightbox").hidden) {
    if (e.key === "Escape") closeLightbox();
    if (e.key === "ArrowLeft") stepLightbox(-1);
    if (e.key === "ArrowRight") stepLightbox(1);
    return;
  }
  if (e.key === "Escape") {
    if ($("#app").classList.contains("nav-open")) $("#app").classList.remove("nav-open");
    else if (!$("#pdfPanel").hidden && !typing) closePdf();
  }
  if (e.key === "/" && !typing) {
    const q = $("#question");
    if (q) { e.preventDefault(); q.focus(); }
  }
});

// ------------------------------------------------------------
// Login
// ------------------------------------------------------------

function showLogin() {
  $("#login").hidden = false;
  setTimeout(() => $("#loginPassword").focus(), 50);
}

$("#loginForm").addEventListener("submit", async (e) => {
  e.preventDefault();
  const err = $("#loginError");
  err.hidden = true;
  try {
    await api("/login", { method: "POST", body: { password: $("#loginPassword").value } });
  } catch (ex) {
    err.textContent = ex.message;
    err.hidden = false;
    return;
  }
  $("#login").hidden = true;
  $("#loginPassword").value = "";
  await start();
});

// ------------------------------------------------------------
// Boot
// ------------------------------------------------------------

async function start() {
  await refreshBooks();
  applyRoute();
  poll();
}

(async function boot() {
  try {
    state.config = await api("/config");
  } catch {
    setServerStatus("bad", "Server unreachable");
    renderLibrary();
    renderView();
    return;
  }
  document.title = state.config.title || "AwarePDF";
  if (state.config.auth_required && !state.config.authenticated) {
    renderLibrary();
    renderView();
    return showLogin();
  }
  if (!state.config.llm_ready) toast("The server has no GROQ_API_KEY, so answers won't work yet.", "error");
  await start();
})();
