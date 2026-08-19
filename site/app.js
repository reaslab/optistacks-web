const state = {
  manifest: null,
  subjectId: null,
  domainMeta: null,
  data: null,
  flat: [],
  byId: new Map(),
  parents: new Map(),
  selected: null,
  expanded: new Set(),
  domainCache: new Map(),
  payloadCache: new Map(),
  payloadRequests: new Map(),
  loadingNodes: new Set(),
  domainLoadToken: 0,
  navigationToken: 0,
  qualityIssues: [],
  qualityTarget: null,
  historyFilter: "all",
  layoutBeforeAnnotation: null,
  statementLimits: new Map(),
};

const QUALITY_STORAGE_KEY = "optistacks-quality-review-v1";
const LAYOUT_STORAGE_KEY = "optistacks-layout-v1";
const PANE_LABELS = { library: "domains", directory: "outline", detail: "content" };
const STATEMENT_PAGE_SIZE = 24;
const LEGACY_DOMAIN_ROUTES = {
  derivative_free_optimization: {
    domain_id: "specialized_continuous_methods",
    default_node_id: "A07.C01",
  },
  manifold_optimization: {
    domain_id: "specialized_continuous_methods",
    default_node_id: "A07.C02",
  },
  distributed_optimization: {
    domain_id: "specialized_continuous_methods",
    default_node_id: "A07.C03",
  },
};
const QUALITY_TYPES = {
  statement: [
    ["natural_language", "Natural-language wording"],
    ["mathematical_correctness", "Mathematical correctness"],
    ["missing_assumption", "Missing or incorrect assumption"],
    ["latex_rendering", "Formula or rendering problem"],
    ["statement_placement", "Wrong topic placement"],
    ["duplicate_statement", "Duplicate statement"],
    ["evidence_source", "Evidence or source problem"],
    ["other", "Other statement issue"],
  ],
  topic: [
    ["directory_split", "Topic should be split differently"],
    ["directory_merge", "Topics should be merged"],
    ["hierarchy_placement", "Wrong parent or hierarchy"],
    ["topic_naming", "Topic naming problem"],
    ["missing_topic", "Missing topic or branch"],
    ["duplicate_topic", "Duplicate topic"],
    ["other", "Other directory issue"],
  ],
};

const $ = (selector) => document.querySelector(selector);
const esc = (value = "") => String(value).replace(/[&<>'"]/g, char => ({
  "&": "&amp;", "<": "&lt;", ">": "&gt;", "'": "&#39;", '"': "&quot;"
}[char]));
const formatNumber = value => new Intl.NumberFormat("en-US").format(value || 0);
const titleCase = value => String(value || "").replaceAll("_", " ");

function renderLatex(value, display = false) {
  const raw = String(value || "").trim();
  if (!raw) return "";
  const hasDelimiters = /\\\(|\\\[|\$\$|\\begin\s*\{/.test(raw);
  if (hasDelimiters) return esc(raw);
  const looksLikeLatex = /\\[A-Za-z]+|[_^][{A-Za-z0-9\\]|[{}]/.test(raw);
  if (!looksLikeLatex) return esc(raw);
  return esc(display ? `\\[${raw}\\]` : `\\(${raw}\\)`);
}

function toast(message) {
  const element = $("#toast");
  element.textContent = message;
  element.classList.add("show");
  clearTimeout(toast.timer);
  toast.timer = setTimeout(() => element.classList.remove("show"), 1800);
}

async function fetchManifest() {
  if (state.manifest) return state.manifest;
  const response = await fetch("data/manifest.json", { cache: "no-store" });
  if (!response.ok) throw new Error(`manifest: HTTP ${response.status}`);
  state.manifest = await response.json();
  return state.manifest;
}

async function bootstrap() {
  try {
    await fetchManifest();
    loadQualityIssues();
    loadLayout();
    $("#total-statements").textContent = formatNumber(state.manifest.totals.statements);
    state.subjectId = state.manifest.subject_domains?.[0]?.id || null;
    renderDomainNav();
    bindEvents();
    const route = parseRoute();
    await loadDomain(route.domain || state.manifest.domains[0].id, route.node);
  } catch (error) {
    $("#tree-view").innerHTML = `<div class="empty-statements"><b>Site data could not be loaded</b><span>${esc(error.message)}</span><br><br><span>Open this site through a local HTTP server rather than directly from the file system.</span></div>`;
  }
}

function bindEvents() {
  document.addEventListener("keydown", event => {
    if (event.key === "Escape") {
      if (state.qualityTarget) closeQualityDialog();
      else if (document.body.classList.contains("quality-panel-open")) closeQualityDrawer();
    }
  });
  $("#collapse-button").addEventListener("click", () => {
    state.expanded.clear();
    if (state.data?.roots?.[0]) state.expanded.add(state.data.roots[0].topic_id);
    renderBrowser();
    toast("Topic outline collapsed");
  });
  $("#toggle-library-pane").addEventListener("click", () => togglePane("library"));
  $("#toggle-directory-pane").addEventListener("click", () => togglePane("directory"));
  $("#toggle-detail-pane").addEventListener("click", () => togglePane("detail"));
  bindPaneResizers();
  window.addEventListener("hashchange", async () => {
    const route = parseRoute();
    if (route.domain && route.domain !== state.domainMeta?.id) await loadDomain(route.domain, route.node, false);
    else if (route.node) await navigateToNode(route.node, false, true);
  });
  $("#quality-queue-button").addEventListener("click", openQualityDrawer);
  $("#quality-panel-close").addEventListener("click", closeQualityDrawer);
  $("#quality-export-button").addEventListener("click", exportQualityIssues);
  document.querySelectorAll("[data-history-filter]").forEach(button => button.addEventListener("click", () => {
    state.historyFilter = button.dataset.historyFilter;
    renderQualityQueue();
  }));
  $("#quality-form-close").addEventListener("click", closeQualityDialog);
  $("#quality-cancel-button").addEventListener("click", closeQualityDialog);
  $("#quality-form").addEventListener("submit", submitQualityIssue);
}

function loadLayout() {
  let layout = {};
  try {
    layout = JSON.parse(localStorage.getItem(LAYOUT_STORAGE_KEY) || "{}");
  } catch { /* keep defaults */ }
  const widths = [
    ["libraryWidth", "--library-width", 180, 420],
    ["directoryWidth", "--directory-width", 280, 720],
    ["qualityWidth", "--quality-width", 320, 640],
  ];
  widths.forEach(([key, property, minimum, maximum]) => {
    const value = Number(layout[key]);
    if (Number.isFinite(value) && value >= minimum && value <= maximum) {
      document.documentElement.style.setProperty(property, `${value}px`);
    }
  });
  document.body.classList.toggle("library-hidden", Boolean(layout.libraryHidden));
  document.body.classList.toggle("directory-hidden", Boolean(layout.directoryHidden));
  document.body.classList.toggle("detail-hidden", Boolean(layout.detailHidden));
  if (layout.directoryHidden && layout.detailHidden) document.body.classList.remove("detail-hidden");
  updateLayoutControls();
}

function saveLayout() {
  const style = getComputedStyle(document.documentElement);
  const pixels = property => Math.round(parseFloat(style.getPropertyValue(property)) || 0);
  localStorage.setItem(LAYOUT_STORAGE_KEY, JSON.stringify({
    libraryWidth: pixels("--library-width"),
    directoryWidth: pixels("--directory-width"),
    qualityWidth: pixels("--quality-width"),
    libraryHidden: document.body.classList.contains("library-hidden"),
    directoryHidden: document.body.classList.contains("directory-hidden"),
    detailHidden: document.body.classList.contains("detail-hidden"),
  }));
}

function updateLayoutControls() {
  ["library", "directory", "detail"].forEach(name => {
    const visible = !document.body.classList.contains(`${name}-hidden`);
    const button = $(`#toggle-${name}-pane`);
    button.classList.toggle("active", visible);
    button.setAttribute("aria-pressed", String(visible));
    button.title = `${visible ? "Hide" : "Show"} ${PANE_LABELS[name]}`;
  });
}

function setPaneHidden(name, hidden, persist = true) {
  if ((name === "directory" || name === "detail") && hidden) {
    const counterpart = name === "directory" ? "detail" : "directory";
    if (document.body.classList.contains(`${counterpart}-hidden`)) {
      toast("Keep either Outline or Content visible");
      return;
    }
  }
  document.body.classList.toggle(`${name}-hidden`, hidden);
  updateLayoutControls();
  if (persist) saveLayout();
}

function togglePane(name) {
  setPaneHidden(name, !document.body.classList.contains(`${name}-hidden`));
}

function bindPaneResizers() {
  const bind = (selector, widthProperty, calculate, minimum, maximum) => {
    const resizer = $(selector);
    resizer.addEventListener("pointerdown", event => {
      if (event.button !== 0) return;
      event.preventDefault();
      resizer.setPointerCapture(event.pointerId);
      resizer.classList.add("dragging");
      document.body.classList.add("resizing");
      const move = moveEvent => {
        const value = Math.max(minimum, Math.min(maximum(), calculate(moveEvent)));
        document.documentElement.style.setProperty(widthProperty, `${Math.round(value)}px`);
      };
      const finish = () => {
        resizer.classList.remove("dragging");
        document.body.classList.remove("resizing");
        resizer.removeEventListener("pointermove", move);
        resizer.removeEventListener("pointerup", finish);
        resizer.removeEventListener("pointercancel", finish);
        saveLayout();
      };
      resizer.addEventListener("pointermove", move);
      resizer.addEventListener("pointerup", finish);
      resizer.addEventListener("pointercancel", finish);
    });
  };
  bind("#library-resizer", "--library-width", event => event.clientX, 180, () => Math.min(420, window.innerWidth - 720));
  bind("#directory-resizer", "--directory-width", event => event.clientX - $(".workspace").getBoundingClientRect().left, 280, () => Math.max(300, $(".workspace").clientWidth - 340));
  bind("#quality-resizer", "--quality-width", event => window.innerWidth - event.clientX, 320, () => Math.min(640, window.innerWidth - 620));
}

function parseRoute() {
  const raw = decodeURIComponent(location.hash.slice(1));
  const [domain, ...node] = raw.split("/");
  return resolveLegacyRoute(domain, node.join("/") || null);
}

function resolveLegacyRoute(domainId, nodeId = null) {
  const route = state.manifest?.legacy_domain_routes?.[domainId]
    || LEGACY_DOMAIN_ROUTES[domainId];
  const domain = route?.domain_id || domainId;
  const requestedNode = nodeId || route?.default_node_id || null;
  const redirectedNode = state.manifest?.node_redirects?.[domain]?.[requestedNode]
    || requestedNode;
  return { domain, node: redirectedNode };
}

function versionedDataUrl(path) {
  const url = new URL(path, location.href);
  url.searchParams.set("v", state.manifest.built_at);
  return url;
}

async function fetchPayload(path) {
  const key = versionedDataUrl(path).href;
  if (state.payloadCache.has(key)) return state.payloadCache.get(key);
  if (state.payloadRequests.has(key)) return state.payloadRequests.get(key);
  const request = fetch(key, { cache: "force-cache" }).then(async response => {
    if (!response.ok) throw new Error(`${path}: HTTP ${response.status}`);
    const payload = await response.json();
    state.payloadCache.set(key, payload);
    return payload;
  }).finally(() => state.payloadRequests.delete(key));
  state.payloadRequests.set(key, request);
  return request;
}

function domainNavigationItems() {
  const items = state.manifest.domains.map(domain => ({ ...domain, navigation_kind: "domain" }));
  (state.manifest.navigation_shortcuts || []).forEach(shortcut => {
    const position = Math.max(0, Math.min(items.length, Number(shortcut.position || items.length + 1) - 1));
    items.splice(position, 0, { ...shortcut, navigation_kind: "shortcut" });
  });
  return items;
}

function navigationItem(itemId) {
  return domainNavigationItems().find(item => item.id === itemId) || null;
}

function subjectDomains() {
  return state.manifest.subject_domains || [];
}

function activeSubjectDomain() {
  return subjectDomains().find(subject => subject.id === state.subjectId) || subjectDomains()[0] || null;
}

function inferSubjectDomain(collectionId, resolvedDomainId = collectionId) {
  return subjectDomains().find(subject => (
    subject.items.includes(collectionId) || subject.items.includes(resolvedDomainId)
  )) || null;
}

function activeNavigationShortcut() {
  if (!state.selected || !state.domainMeta) return null;
  const pathIds = new Set((state.byId.get(state.selected)?.path || []).map(node => node.topic_id));
  return (state.manifest.navigation_shortcuts || []).find(shortcut => (
    shortcut.domain_id === state.domainMeta.id && pathIds.has(shortcut.default_node_id)
  )) || null;
}

function renderDomainNav() {
  const activeShortcut = activeNavigationShortcut();
  const activeAccent = activeShortcut?.accent || state.domainMeta?.accent || "#2563eb";
  document.documentElement.style.setProperty("--accent", activeAccent);
  document.documentElement.style.setProperty("--accent-soft", `${activeAccent}24`);
  $("#directory-title").textContent = activeShortcut?.short_name || state.domainMeta?.short_name || "Knowledge outline";
  const subject = activeSubjectDomain();
  const items = (subject?.items || []).map(navigationItem).filter(Boolean);
  $("#domain-count").textContent = formatNumber(items.length);
  $("#subject-domain-selector").innerHTML = subjectDomains().map(item => (
    `<option value="${esc(item.id)}" ${item.id === subject?.id ? "selected" : ""}>${esc(item.short_name)}</option>`
  )).join("");
  $("#subject-domain-selector").onchange = () => loadSubjectDomain($("#subject-domain-selector").value);
  $("#domain-nav").innerHTML = items.length ? items.map(item => {
    const isShortcut = item.navigation_kind === "shortcut";
    const active = isShortcut
      ? activeShortcut?.id === item.id
      : item.id === state.domainMeta?.id && !activeShortcut;
    return `
    <button class="domain-button ${active ? "active" : ""}" data-domain="${esc(item.id)}" ${isShortcut ? `data-node="${esc(item.default_node_id)}"` : ""} style="--domain-accent:${item.accent}">
      <span class="domain-swatch"></span>
      <span><b>${esc(item.short_name)}</b><small>${formatNumber(item.stats.topics)} topics · ${formatNumber(item.stats.chapters)} chapters</small></span>
      <em>${formatNumber(item.stats.statements)}</em>
    </button>`;
  }).join("") : `<div class="domain-empty">No subject domains have been published in this major domain yet.</div>`;
  document.querySelectorAll("[data-domain]").forEach(button => button.addEventListener("click", () => loadDomain(button.dataset.domain, button.dataset.node || null)));
  requestAnimationFrame(() => $("#domain-nav .active")?.scrollIntoView({ behavior: "smooth", block: "nearest", inline: "nearest" }));
}

function loadSubjectDomain(subjectId) {
  const subject = subjectDomains().find(item => item.id === subjectId) || subjectDomains()[0];
  if (!subject) return;
  state.subjectId = subject.id;
  renderDomainNav();
}

async function loadDomain(domainId, requestedNode = null, updateRoute = true) {
  const requestedCollectionId = domainId;
  const resolvedRoute = resolveLegacyRoute(domainId, requestedNode);
  domainId = resolvedRoute.domain;
  requestedNode = resolvedRoute.node;
  const subject = inferSubjectDomain(requestedCollectionId, domainId);
  if (subject) state.subjectId = subject.id;
  const loadToken = ++state.domainLoadToken;
  const navigationToken = ++state.navigationToken;
  const meta = state.manifest.domains.find(item => item.id === domainId) || state.manifest.domains[0];
  state.domainMeta = meta;
  document.documentElement.style.setProperty("--accent", meta.accent);
  document.documentElement.style.setProperty("--accent-soft", `${meta.accent}24`);
  renderDomainNav();
  $("#directory-title").textContent = meta.short_name;
  $("#tree-view").innerHTML = `<div class="loading-state"><span></span><p>Loading ${esc(meta.short_name)}…</p></div>`;
  try {
    let data = state.domainCache.get(meta.id);
    if (!data) {
      data = await fetchPayload(meta.data_url);
      state.domainCache.set(meta.id, data);
    }
    if (loadToken !== state.domainLoadToken || navigationToken !== state.navigationToken) return;
    state.data = data;
    indexTree();
    state.expanded.clear();
    const root = data.roots[0];
    state.expanded.add(root.topic_id);
    renderBrowser();
    if (requestedNode) await ensureRouteLoaded(requestedNode);
    if (loadToken !== state.domainLoadToken || navigationToken !== state.navigationToken) return;
    const target = requestedNode && state.byId.has(requestedNode) ? requestedNode : root.topic_id;
    selectNode(target, updateRoute);
    if (requestedNode) focusTreeNode(target);
  } catch (error) {
    if (loadToken !== state.domainLoadToken || navigationToken !== state.navigationToken) return;
    $("#tree-view").innerHTML = `<div class="empty-statements"><b>Could not load ${esc(meta.short_name)}</b><span>${esc(error.message)}</span></div>`;
  }
}

function indexTree() {
  state.flat = [];
  state.byId = new Map();
  state.parents = new Map();
  const walk = (node, parent = null, path = []) => {
    const entry = { node, parent, path: [...path, node] };
    state.flat.push(entry);
    state.byId.set(node.topic_id, entry);
    if (parent) state.parents.set(node.topic_id, parent.topic_id);
    (node.children || []).forEach(child => walk(child, node, entry.path));
  };
  state.data.roots.forEach(root => walk(root));
}

function renderBrowser() {
  renderTree();
}

function renderTree() {
  const view = $("#tree-view");
  view.innerHTML = `<ul class="tree-root">${state.data.roots.map(renderTreeNode).join("")}</ul>`;
  bindTreeEvents(view);
}

function renderTreeNode(node) {
  const hasChildren = (node.children || []).length > 0 || Boolean(node.shard_url);
  const open = state.expanded.has(node.topic_id);
  const loading = state.loadingNodes.has(node.topic_id);
  return `<li class="tree-node" data-node-shell="${esc(node.topic_id)}">
    <div class="tree-row ${state.selected === node.topic_id ? "selected" : ""}" data-select-node="${esc(node.topic_id)}" ${loading ? 'aria-busy="true"' : ""}>
      <button class="tree-toggle ${loading ? "loading" : hasChildren ? (open ? "open" : "") : "leaf"}" data-toggle-node="${esc(node.topic_id)}" aria-label="${loading ? "Loading" : open ? "Collapse" : "Expand"}" ${loading ? "disabled" : ""}></button>
      <span class="tree-label"><b title="${esc(node.title)}">${esc(node.title)}</b></span>
      ${node.descendant_statement_count ? `<span class="tree-count">${formatNumber(node.descendant_statement_count)}</span>` : ""}
    </div>
    ${hasChildren && open ? `<ul class="tree-children">${node.children.map(renderTreeNode).join("")}</ul>` : ""}
  </li>`;
}

function bindTreeEvents(root) {
  root.querySelectorAll("[data-toggle-node]").forEach(button => button.addEventListener("click", async event => {
    event.stopPropagation();
    const id = button.dataset.toggleNode;
    if (state.expanded.has(id)) {
      state.expanded.delete(id);
      renderTree();
      return;
    }
    try {
      await ensureRouteLoaded(id);
      state.expanded.add(id);
      renderTree();
    } catch (error) {
      toast(`Could not load topic: ${error.message}`);
    }
  }));
  root.querySelectorAll("[data-select-node]").forEach(row => row.addEventListener("click", async event => {
    if (event.target.closest("[data-toggle-node]")) return;
    await navigateToNode(row.dataset.selectNode);
  }));
}

async function ensureChapterLoaded(chapterId) {
  const entry = state.byId.get(chapterId);
  const chapter = entry?.node;
  if (!chapter?.shard_url || chapter.lazy_loaded) return;
  const domainData = state.data;
  const shardUrl = chapter.shard_url;
  state.loadingNodes.add(chapterId);
  if (state.data === domainData) renderTree();
  try {
    const payload = await fetchPayload(shardUrl);
    if (payload.chapter_id !== chapterId || payload.root?.topic_id !== chapterId) {
      throw new Error(`Unexpected chapter payload for ${chapterId}`);
    }
    Object.assign(chapter, payload.root, {
      shard_url: shardUrl,
      lazy_content: false,
      lazy_loaded: true,
    });
    if (state.data === domainData) indexTree();
  } finally {
    state.loadingNodes.delete(chapterId);
  }
}

async function ensureRouteLoaded(nodeId) {
  const direct = state.byId.get(nodeId)?.node;
  if (direct?.shard_url && !direct.lazy_loaded) {
    await ensureChapterLoaded(nodeId);
    return;
  }
  if (direct) return;
  const chapterId = state.data?.node_routes?.[nodeId];
  if (chapterId) await ensureChapterLoaded(chapterId);
}

async function navigateToNode(nodeId, updateRoute = true, focusTree = false) {
  nodeId = state.manifest?.node_redirects?.[state.domainMeta?.id]?.[nodeId] || nodeId;
  const navigationToken = ++state.navigationToken;
  try {
    await ensureRouteLoaded(nodeId);
    if (navigationToken !== state.navigationToken) return;
    if (!state.byId.has(nodeId)) return;
    selectNode(nodeId, updateRoute);
    if (focusTree) focusTreeNode(nodeId);
  } catch (error) {
    toast(`Could not load topic: ${error.message}`);
  }
}

function focusTreeNode(nodeId) {
  requestAnimationFrame(() => {
    const shell = [...document.querySelectorAll("[data-node-shell]")].find(item => item.dataset.nodeShell === nodeId);
    if (!shell) return;
    shell.scrollIntoView({ behavior: "smooth", block: "center" });
    shell.classList.add("nav-target");
    setTimeout(() => shell.classList.remove("nav-target"), 1150);
  });
}

function revealPath(nodeId) {
  let current = nodeId;
  while (current) { state.expanded.add(current); current = state.parents.get(current); }
}

function selectNode(nodeId, updateRoute = true) {
  if (!state.byId.has(nodeId)) return;
  state.selected = nodeId;
  revealPath(nodeId);
  if (updateRoute) history.pushState(null, "", `#${state.domainMeta.id}/${encodeURIComponent(nodeId)}`);
  renderDetail(nodeId);
  renderTree();
  renderDomainNav();
}

function renderDetail(nodeId) {
  const entry = state.byId.get(nodeId);
  if (!entry) return;
  const node = entry.node;
  const allStatements = node.knowledge_statements || [];
  const statementLimit = state.statementLimits.get(nodeId) || STATEMENT_PAGE_SIZE;
  const statements = allStatements.slice(0, statementLimit);
  const hasMoreStatements = statements.length < allStatements.length;
  const path = entry.path.map(item => `<span>${esc(item.title)}</span>`).join("<i>/</i>");
  const witnesses = node.top_down_textbook_witnesses || [];
  const relationships = renderTopicRelationships(entry);
  $("#detail-panel").innerHTML = `
    <header class="topic-hero">
      <div class="breadcrumbs">${path}</div>
      <h2>${esc(node.title)}</h2>
      <p class="topic-role">${esc(node.top_down_role || "This node organizes the knowledge topics below it.")}</p>
      <div class="topic-actions"><button class="review-button" type="button" data-quality-target-type="topic" data-quality-target-id="${esc(node.topic_id)}">Report topic issue</button></div>
    </header>
    <div class="detail-body">
      ${relationships}
      <div class="section-heading"><h3>Knowledge statements</h3><span>${statements.length} / ${allStatements.length} records</span></div>
      ${statements.length ? `<div class="statement-list">${statements.map((statement, index) => renderStatement(statement, index)).join("")}</div>` : `
        <div class="empty-statements"><b>${allStatements.length ? "No statements match this filter" : "Structural topic"}</b><span>${allStatements.length ? "Choose another statement type above." : `Concrete knowledge is stored in ${formatNumber(node.descendant_statement_count)} descendant statements.`}</span></div>`}
      ${hasMoreStatements ? `<button class="load-more-statements" type="button" data-load-more-statements="${esc(nodeId)}">Show ${Math.min(STATEMENT_PAGE_SIZE, allStatements.length - statements.length)} more statements</button>` : ""}
      ${witnesses.length ? `<section class="witness-section"><div class="section-heading"><h3>Source references</h3><span>${witnesses.length} references</span></div><div class="source-list">${witnesses.map(renderWitness).join("")}</div></section>` : ""}
    </div>`;
  $("#detail-panel").scrollTop = 0;
  $("#detail-panel").querySelectorAll("[data-related-node]").forEach(button => {
    button.addEventListener("click", () => navigateToNode(button.dataset.relatedNode, true, true));
  });
  $("#detail-panel").querySelectorAll("[data-prerequisite-node]").forEach(link => {
    link.addEventListener("click", event => {
      event.preventDefault();
      const nodeId = link.dataset.prerequisiteNode;
      const domainId = link.dataset.prerequisiteDomain;
      if (domainId === state.domainMeta.id) {
        navigateToNode(nodeId, true, true);
      } else {
        loadDomain(domainId, nodeId);
      }
    });
  });
  $("#detail-panel").querySelectorAll("[data-quality-target-type]").forEach(button => {
    button.addEventListener("click", event => {
      event.preventDefault();
      event.stopPropagation();
      openQualityDialog(button.dataset.qualityTargetType, button.dataset.qualityTargetId);
    });
  });
  $("#detail-panel").querySelector("[data-load-more-statements]")?.addEventListener("click", () => {
    state.statementLimits.set(nodeId, statementLimit + STATEMENT_PAGE_SIZE);
    renderDetail(nodeId);
  });
  typesetMath($("#detail-panel"));
}

function renderTopicRelationships(entry) {
  const parent = entry.parent;
  const children = entry.node.children || [];
  if (!parent && !children.length) return "";
  const groups = [];
  if (parent) {
    groups.push(`
      <section class="relation-group parent-relation">
        <div class="relation-heading"><h3>Parent topic</h3></div>
        <button class="relation-card" type="button" data-related-node="${esc(parent.topic_id)}">
          <b>${esc(parent.title)}</b><span aria-hidden="true">↑</span>
        </button>
      </section>`);
  }
  if (children.length) {
    groups.push(`
      <section class="relation-group child-relations">
        <div class="relation-heading"><h3>Child topics</h3><small>${children.length}</small></div>
        <div class="relation-list">
          ${children.map(child => `
            <button class="relation-card" type="button" data-related-node="${esc(child.topic_id)}">
              <b>${esc(child.title)}</b><span aria-hidden="true">→</span>
            </button>`).join("")}
        </div>
      </section>`);
  }
  return `<div class="topic-relations">${groups.join("")}</div>`;
}

function arrayValues(value) {
  if (Array.isArray(value)) return value.filter(item => item !== null && item !== undefined && String(item).trim());
  if (value === null || value === undefined || String(value).trim() === "") return [];
  return [value];
}

function renderStatementSource(source) {
  const title = source.source_title || source.source_id || source.source_graph_id || "Source evidence";
  const locator = source.locator || source.source_locator || "No item-level locator supplied";
  const itemId = source.source_item_id || source.statement_id || "";
  const grounding = source.fulltext_span_verified === true
    ? "full-text span verified"
    : source.fulltext_span_verified === false
      ? "extraction grounded; full-text span not verified"
      : "grounding status not recorded";
  return `<div class="statement-source-item">
    <b>${esc(title)}</b>
    <span>${esc(locator)}</span>
    <small>${itemId ? `<code>${esc(itemId)}</code> · ` : ""}${esc(grounding)}</small>
  </div>`;
}

function renderVariantDimensions(dimensions) {
  if (!dimensions || typeof dimensions !== "object" || Array.isArray(dimensions)) return "";
  const groups = Object.entries(dimensions).filter(([, value]) => arrayValues(value).length);
  if (!groups.length) return "";
  return `<div class="meta-block full"><label>Variant regime</label><div class="variant-grid">${groups.map(([key, values]) => `
    <section><b>${esc(titleCase(key))}</b><ul>${arrayValues(values).map(value => `<li>${esc(value)}</li>`).join("")}</ul></section>`).join("")}</div></div>`;
}

function renderStatement(statement, index) {
  const assumptions = statement.assumptions_latex || [];
  const notation = statement.notation || [];
  const conclusion = statement.conclusion && typeof statement.conclusion === "object" && !Array.isArray(statement.conclusion)
    ? statement.conclusion
    : {};
  const conclusionLatex = statement.conclusion_latex || conclusion.conclusion_latex || "";
  const sources = statement.source_refs?.length ? statement.source_refs : (statement.source_witnesses || []);
  const boundaryNotes = arrayValues(statement.boundary_notes);
  const equivalentFormulations = arrayValues(statement.equivalent_formulations_latex);
  const relations = arrayValues(statement.relations);
  const rateClass = conclusion.rate_class && !["none", "not applicable"].includes(String(conclusion.rate_class).toLowerCase())
    ? conclusion.rate_class
    : "";
  const badges = [
    statement.content_kind ? { value: statement.content_kind, kind: "kind" } : null,
    rateClass ? { value: rateClass, kind: "rate" } : null,
    statement.intermediate_metadata?.partial_run ? { value: "partial run", kind: "partial" } : null,
  ].filter(Boolean);
  return `<details class="statement-card" id="stmt-${esc(statement.id)}" ${index === 0 ? "open" : ""}>
    <summary>
      <b>${esc(statement.title || statement.statement_title || "Untitled statement")}</b>
      <span class="statement-badges">${badges.map(badge => `<em class="statement-badge ${badge.kind}">${esc(titleCase(badge.value))}</em>`).join("")}</span>
    </summary>
    <div class="statement-content">
      <div class="statement-tools"><button class="review-button" type="button" data-quality-target-type="statement" data-quality-target-id="${esc(statement.id)}">Report statement issue</button></div>
      ${statement.statement_plain ? `<p class="plain-statement">${esc(statement.statement_plain)}</p>` : ""}
      ${statement.statement_latex ? `<div class="formal-block">${renderLatex(statement.statement_latex, true)}</div>` : ""}
      <div class="statement-meta">
        ${assumptions.length ? `<div class="meta-block full"><label>Assumptions</label><ul class="latex-list">${assumptions.map(value => `<li>${renderLatex(value)}</li>`).join("")}</ul></div>` : ""}
        ${conclusionLatex ? `<div class="meta-block full"><label>Conclusion</label><div class="latex-value">${renderLatex(conclusionLatex)}</div></div>` : ""}
        ${conclusion.target ? `<div class="meta-block full"><label>Convergence target</label><p>${esc(conclusion.target)}</p></div>` : ""}
        ${arrayValues(conclusion.convergence_objects).length ? `<div class="meta-block full"><label>Convergence objects</label><ul>${arrayValues(conclusion.convergence_objects).map(value => `<li>${esc(value)}</li>`).join("")}</ul></div>` : ""}
        ${conclusion.nonasymptotic_bound_latex ? `<div class="meta-block full"><label>Nonasymptotic bound</label><div class="latex-value">${renderLatex(conclusion.nonasymptotic_bound_latex)}</div></div>` : ""}
        ${conclusion.epsilon_complexity_latex ? `<div class="meta-block full"><label>Epsilon complexity</label><div class="latex-value">${renderLatex(conclusion.epsilon_complexity_latex)}</div></div>` : ""}
        ${["sequence_scope", "topology_or_mode", "probability_mode", "locality", "rate_class"].map(key => conclusion[key] ? `<div class="meta-block"><label>${esc(titleCase(key))}</label><p>${esc(titleCase(conclusion[key]))}</p></div>` : "").join("")}
        ${renderVariantDimensions(statement.variant_dimensions)}
        ${equivalentFormulations.length ? `<div class="meta-block full"><label>Equivalent formulations</label><ul class="latex-list">${equivalentFormulations.map(value => `<li>${renderLatex(value)}</li>`).join("")}</ul></div>` : ""}
        ${boundaryNotes.length ? `<div class="meta-block full boundary-block"><label>Boundary and limitation notes</label><ul>${boundaryNotes.map(value => `<li>${esc(value)}</li>`).join("")}</ul></div>` : ""}
        ${relations.length ? `<div class="meta-block full"><label>Variant relations</label><div class="variant-relations">${relations.map(relation => `<p><b>${esc(titleCase(relation.relation || "related"))}</b> <code>${esc(relation.target_variant_id || relation.target_local_variant_id || "")}</code>${relation.rationale ? `<span>${esc(relation.rationale)}</span>` : ""}</p>`).join("")}</div></div>` : ""}
        ${statement.intermediate_metadata?.reason ? `<div class="meta-block full"><label>Deferred reason</label><p>${esc(statement.intermediate_metadata.reason)}</p></div>` : ""}
        ${statement.intermediate_metadata?.review_comment ? `<div class="meta-block full"><label>Review comment</label><p>${esc(statement.intermediate_metadata.review_comment)}</p></div>` : ""}
        ${statement.prerequisite_node_ids?.length ? `<div class="meta-block full"><label>Prerequisites</label><p class="prerequisite-links">${statement.prerequisite_node_ids.map(renderPrerequisite).join("<span>·</span>")}</p></div>` : ""}
        ${notation.length ? `<div class="meta-block full"><label>Notation</label><ul class="latex-list">${notation.map(item => `<li><span class="notation-symbol">${renderLatex(item.symbol_latex)}</span><span>— ${esc(item.meaning)}</span></li>`).join("")}</ul></div>` : ""}
        ${sources.length ? `<div class="meta-block full"><label>Statement evidence</label><div class="statement-source-list">${sources.map(renderStatementSource).join("")}</div></div>` : ""}
        <div class="meta-block full"><label>Statement ID</label><p><code>${esc(statement.id)}</code></p></div>
      </div>
    </div>
  </details>`;
}

function renderPrerequisite(nodeId) {
  const prefix = String(nodeId).split(".")[0];
  const domainByPrefix = {
    A02: "convex_analysis",
    A03: "variational_analysis",
    A04: "nonlinear_programming",
    A05: "first_order_methods",
    A06: "nonsmooth_optimization",
    A07: "specialized_continuous_methods",
    A08: "convex_programming",
    A09: "linear_programming",
    A10: "conic_optimization",
    A11: "quadratic_optimization",
    A12: "integer_mixed_integer_optimization",
    A13: "combinatorial_optimization",
    A14: "constraint_logic_optimization",
    A15: "global_optimization",
    A16: "optimization_under_uncertainty",
  };
  const domainId = domainByPrefix[prefix];
  if (!domainId) return `<code>${esc(nodeId)}</code>`;
  const href = `#${domainId}/${encodeURIComponent(nodeId)}`;
  return `<a href="${esc(href)}" data-prerequisite-node="${esc(nodeId)}" data-prerequisite-domain="${esc(domainId)}" title="Open prerequisite">${esc(nodeId)}</a>`;
}

function renderWitness(witness) {
  const title = witness.source_title || witness.source_query || witness.source_graph_id || "Source witness";
  const locator = witness.locator || witness.source_locator || witness.matched_excerpt || "No locator supplied";
  const status = witness.locator_traceability?.status || witness.evidence_role || witness.validation_scope || "";
  return `<div class="source-item"><b>${esc(title)}</b><span>${esc(locator)}${status ? ` · ${esc(status)}` : ""}</span></div>`;
}

function typesetMath(container) {
  if (!window.MathJax?.typesetPromise) return;
  window.MathJax.typesetPromise([container]).catch(() => {});
}

function loadQualityIssues() {
  try {
    const stored = JSON.parse(localStorage.getItem(QUALITY_STORAGE_KEY) || "[]");
    let migrated = false;
    state.qualityIssues = Array.isArray(stored) ? stored.map(issue => {
      const route = resolveLegacyRoute(issue.domain_id, issue.topic_id);
      if (route.domain === issue.domain_id && route.node === issue.topic_id) return issue;
      migrated = true;
      const updated = { ...issue, domain_id: route.domain, topic_id: route.node };
      if (issue.target_type === "topic" && issue.target_id === issue.topic_id) {
        updated.target_id = route.node;
      }
      updated.page_hash = route.node
        ? `#${route.domain}/${encodeURIComponent(route.node)}`
        : `#${route.domain}`;
      return updated;
    }) : [];
    if (migrated) localStorage.setItem(QUALITY_STORAGE_KEY, JSON.stringify(state.qualityIssues));
  } catch {
    state.qualityIssues = [];
  }
  updateQualityCount();
}

function saveQualityIssues() {
  localStorage.setItem(QUALITY_STORAGE_KEY, JSON.stringify(state.qualityIssues));
  updateQualityCount();
}

function updateQualityCount() {
  const issues = state.qualityIssues;
  const openCount = issues.filter(issue => issue.status !== "resolved").length;
  const resolvedCount = issues.length - openCount;
  $("#quality-open-count").textContent = formatNumber(issues.length);
  $("#history-total-count").textContent = formatNumber(issues.length);
  $("#history-open-count").textContent = formatNumber(openCount);
  $("#history-resolved-count").textContent = formatNumber(resolvedCount);
}

function openQualityDialog(targetType, targetId) {
  const entry = state.byId.get(state.selected);
  if (!entry) return;
  let target;
  if (targetType === "topic") {
    const topicEntry = state.byId.get(targetId);
    if (!topicEntry) return;
    target = {
      target_type: "topic",
      target_id: targetId,
      target_title: topicEntry.node.title,
      topic_id: targetId,
      path: topicEntry.path.map(item => item.title),
      snapshot: {
        display_number: topicEntry.node.display_number,
        top_down_role: topicEntry.node.top_down_role,
        child_topic_ids: (topicEntry.node.children || []).map(child => child.topic_id),
        child_titles: (topicEntry.node.children || []).map(child => child.title),
      },
    };
  } else {
    const statement = (entry.node.knowledge_statements || []).find(item => item.id === targetId);
    if (!statement) return;
    target = {
      target_type: "statement",
      target_id: targetId,
      target_title: statement.title,
      topic_id: entry.node.topic_id,
      path: entry.path.map(item => item.title),
      snapshot: {
        statement_plain: statement.statement_plain,
        statement_latex: statement.statement_latex,
        assumptions_latex: statement.assumptions_latex || [],
        conclusion_latex: statement.conclusion_latex,
        prerequisite_node_ids: statement.prerequisite_node_ids || [],
        pipeline_stage: statement.intermediate_metadata?.stage || "official_tree",
      },
    };
  }
  state.qualityTarget = { ...target, domain_id: state.domainMeta.id };
  $("#quality-target").innerHTML = `<b>${esc(target.target_title)}</b><span>${esc(target.path.join(" / "))}</span>`;
  $("#quality-issue-type").innerHTML = QUALITY_TYPES[targetType].map(([value, label]) => `<option value="${value}">${esc(label)}</option>`).join("");
  $("#quality-severity").value = "medium";
  $("#quality-note").value = "";
  state.layoutBeforeAnnotation = {
    libraryHidden: document.body.classList.contains("library-hidden"),
  };
  setPaneHidden("library", true, false);
  openQualityPanel("form");
  setTimeout(() => $("#quality-note").focus(), 20);
}

function closeQualityDialog() {
  state.qualityTarget = null;
  closeQualityPanel();
  restoreLayoutAfterAnnotation();
}

function submitQualityIssue(event) {
  event.preventDefault();
  if (!state.qualityTarget) return;
  const note = $("#quality-note").value.trim();
  if (!note) return;
  const issueId = globalThis.crypto?.randomUUID?.() || `${Date.now()}-${Math.random().toString(16).slice(2)}`;
  state.qualityIssues.unshift({
    schema_version: "optistacks-quality-issue-v1",
    issue_id: `QC-${issueId}`,
    status: "open",
    severity: $("#quality-severity").value,
    issue_type: $("#quality-issue-type").value,
    note,
    created_at: new Date().toISOString(),
    page_hash: location.hash,
    ...state.qualityTarget,
  });
  saveQualityIssues();
  closeQualityDialog();
  toast("Correction submitted and added to your history");
}

function openQualityDrawer() {
  if (state.qualityTarget) {
    closeQualityDialog();
    return;
  }
  renderQualityQueue();
  if (document.body.classList.contains("quality-panel-open") && !$("#quality-queue-view").hidden) {
    closeQualityDrawer();
    return;
  }
  openQualityPanel("queue");
}

function closeQualityDrawer() {
  if (state.qualityTarget) {
    closeQualityDialog();
    return;
  }
  closeQualityPanel();
}

function openQualityPanel(view) {
  const showForm = view === "form";
  $("#quality-queue-view").hidden = showForm;
  $("#quality-form-view").hidden = !showForm;
  document.body.classList.add("quality-panel-open");
  $("#quality-panel").setAttribute("aria-hidden", "false");
  $("#quality-queue-button").setAttribute("aria-pressed", "true");
}

function closeQualityPanel() {
  document.body.classList.remove("quality-panel-open");
  $("#quality-panel").setAttribute("aria-hidden", "true");
  $("#quality-queue-button").setAttribute("aria-pressed", "false");
}

function restoreLayoutAfterAnnotation() {
  if (!state.layoutBeforeAnnotation) return;
  setPaneHidden("library", state.layoutBeforeAnnotation.libraryHidden, false);
  state.layoutBeforeAnnotation = null;
}

function renderQualityQueue() {
  const allIssues = state.qualityIssues;
  const issues = allIssues.filter(issue => {
    if (state.historyFilter === "open") return issue.status !== "resolved";
    if (state.historyFilter === "resolved") return issue.status === "resolved";
    return true;
  });
  updateQualityCount();
  document.querySelectorAll("[data-history-filter]").forEach(button => {
    const active = button.dataset.historyFilter === state.historyFilter;
    button.classList.toggle("active", active);
    button.setAttribute("aria-pressed", String(active));
  });
  const filterLabels = { all: "All submissions", open: "Open submissions", resolved: "Resolved submissions" };
  $("#history-result-label").textContent = `${filterLabels[state.historyFilter]} · ${formatNumber(issues.length)}`;
  $("#quality-issue-list").innerHTML = issues.length ? issues.map(issue => `
    <article class="quality-issue-card ${issue.status === "resolved" ? "resolved" : ""}">
      <div class="quality-issue-top"><span class="severity-badge">${esc(issue.severity)} priority</span><span class="submission-status ${issue.status === "resolved" ? "resolved" : "open"}">${issue.status === "resolved" ? "Resolved" : "Open"}</span></div>
      <h3>${esc(issue.target_title)}</h3>
      <div class="quality-issue-meta"><span>${esc(titleCase(issue.issue_type))}</span><time datetime="${esc(issue.created_at)}">${esc(formatSubmissionDate(issue.created_at))}</time></div>
      <p>${esc(issue.note)}</p>
      <div class="quality-card-actions">
        <button type="button" data-quality-goto="${esc(issue.issue_id)}">Open target</button>
        <button type="button" data-quality-toggle="${esc(issue.issue_id)}">${issue.status === "resolved" ? "Mark open" : "Mark resolved"}</button>
      </div>
    </article>`).join("") : `<div class="quality-empty"><b>No ${state.historyFilter === "all" ? "" : `${esc(state.historyFilter)} `}submissions yet.</b><br>Use “Report topic issue” or “Report statement issue” while exploring the atlas.</div>`;
  $("#quality-issue-list").querySelectorAll("[data-quality-goto]").forEach(button => {
    button.addEventListener("click", () => navigateToQualityTarget(button.dataset.qualityGoto));
  });
  $("#quality-issue-list").querySelectorAll("[data-quality-toggle]").forEach(button => {
    button.addEventListener("click", () => toggleQualityIssue(button.dataset.qualityToggle));
  });
}

function formatSubmissionDate(value) {
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return "Date unavailable";
  return date.toLocaleString("en-US", { month: "short", day: "numeric", year: "numeric", hour: "2-digit", minute: "2-digit" });
}

function toggleQualityIssue(issueId) {
  const issue = state.qualityIssues.find(item => item.issue_id === issueId);
  if (!issue) return;
  issue.status = issue.status === "resolved" ? "open" : "resolved";
  issue.updated_at = new Date().toISOString();
  saveQualityIssues();
  renderQualityQueue();
}

async function navigateToQualityTarget(issueId) {
  const issue = state.qualityIssues.find(item => item.issue_id === issueId);
  if (!issue) return;
  closeQualityDrawer();
  if (issue.domain_id !== state.domainMeta.id) await loadDomain(issue.domain_id, issue.topic_id);
  else await navigateToNode(issue.topic_id, true, true);
  renderBrowser();
  if (issue.target_type === "statement") {
    setTimeout(() => document.getElementById(`stmt-${issue.target_id}`)?.scrollIntoView({ behavior: "smooth", block: "center" }), 80);
  }
}

function exportQualityIssues() {
  const issues = state.qualityIssues;
  const packet = {
    schema_version: "optistacks-quality-review-packet-v1",
    exported_at: new Date().toISOString(),
    summary: {
      total: issues.length,
      open: issues.filter(issue => issue.status !== "resolved").length,
      resolved: issues.filter(issue => issue.status === "resolved").length,
    },
    site_build: state.manifest?.built_at,
    issues,
  };
  const blob = new Blob([JSON.stringify(packet, null, 2) + "\n"], { type: "application/json" });
  const url = URL.createObjectURL(blob);
  const link = document.createElement("a");
  link.href = url;
  link.download = `reasatlas-quality-review-${new Date().toISOString().slice(0, 10)}.json`;
  link.click();
  URL.revokeObjectURL(url);
  toast("Quality review JSON exported");
}

bootstrap();
