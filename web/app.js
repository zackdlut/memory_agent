const $ = (sel) => document.querySelector(sel);
const $$ = (sel) => document.querySelectorAll(sel);

async function api(path, opts = {}) {
  // don't force a JSON content-type when sending FormData (let the browser set
  // the multipart boundary header itself)
  const isForm = opts.body instanceof FormData;
  const headers = isForm ? {} : { "Content-Type": "application/json" };
  const res = await fetch(path, {
    headers: { ...headers, ...(opts.headers || {}) },
    ...opts,
  });
  if (!res.ok) {
    const detail = await res.json().catch(() => ({}));
    throw new Error(detail.detail || res.statusText);
  }
  return res.json();
}

// ---------------------------------------------------------------- avatars
const ASSISTANT_NAME = "三叶虫";
// avatar colours live in CSS (.av-0..7 / theme vars) so they follow the theme
// strokes use currentColor so the SVG follows the active theme
const TRILO_SVG = `<svg viewBox="0 0 64 84" fill="none" xmlns="http://www.w3.org/2000/svg" aria-hidden="true">
  <path d="M32 5C46 5 55 18 55 40C55 62 45 79 32 79C19 79 9 62 9 40C9 18 18 5 32 5Z" fill="currentColor" fill-opacity="0.14" stroke="currentColor" stroke-width="3"/>
  <path d="M17 21C17 12.7 23.7 7 32 7C40.3 7 47 12.7 47 21C42.6 25 37 27.5 32 27.5C27 27.5 21.4 25 17 21Z" fill="currentColor" fill-opacity="0.26" stroke="currentColor" stroke-width="2.4"/>
  <path d="M22 33H42M21 41H43M21 49H43M22 57H42M24 65H40M27 72H37" stroke="currentColor" stroke-width="2.2" stroke-linecap="round" opacity="0.85"/>
  <line x1="32" y1="27" x2="32" y2="74" stroke="currentColor" stroke-width="2.2" opacity="0.7"/>
</svg>`;

function nameHash(s) {
  let h = 2166136261;
  for (const ch of s || "") {
    h ^= ch.codePointAt(0);
    h = Math.imul(h, 16777619);
  }
  return h >>> 0;
}
function avatarChar(name) {
  const t = (name || "").trim();
  if (!t) return "·";
  return Array.from(t)[0].toUpperCase();
}
function avatarHTML(name, size) {
  size = size || 34;
  if (name === ASSISTANT_NAME) {
    return `<span class="avatar avatar-assistant" style="--sz:${size}px" title="三叶虫">${TRILO_SVG}</span>`;
  }
  const idx = nameHash(name || "") % 8;
  return `<span class="avatar av-${idx}" style="--sz:${size}px" title="${esc(name || "")}">${esc(avatarChar(name))}</span>`;
}

// ---------------------------------------------------------------- tabs
$$(".tab").forEach((tab) => {
  tab.addEventListener("click", () => {
    $$(".tab").forEach((t) => t.classList.remove("active"));
    $$(".panel").forEach((p) => p.classList.remove("active"));
    tab.classList.add("active");
    $("#" + tab.dataset.tab).classList.add("active");
    if (tab.dataset.tab === "persona") loadPersonas();
    if (tab.dataset.tab === "self") loadSelf();
    if (tab.dataset.tab === "graph") loadGraph();
    if (tab.dataset.tab === "chat") loadSessions();
  });
});

// ---------------------------------------------------------------- stats
async function refreshStats() {
  try {
    const s = await api("/api/stats");
    $("#stats").innerHTML = `
      <div><b>${s.episodes}</b>情景记忆</div>
      <div><b>${s.persons}</b>人物</div>
      <div><b>${s.graph_nodes}</b>图谱节点</div>
      <div><b>${s.graph_edges}</b>关系</div>`;
  } catch (e) {
    $("#stats").innerHTML = `<span class="err">${e.message}</span>`;
  }
}

// ---------------------------------------------------------------- ingest
$("#ingest-btn").addEventListener("click", async () => {
  const text = $("#ingest-text").value.trim();
  if (!text) return;
  const btn = $("#ingest-btn");
  btn.disabled = true;
  $("#ingest-result").innerHTML = '<span class="spin">编码中（感知 → 抽取 → 写入 → 自进化）...</span>';
  try {
    const r = await api("/api/ingest", { method: "POST", body: JSON.stringify({ text }) });
    renderIngest(r);
    refreshStats();
  } catch (e) {
    $("#ingest-result").innerHTML = `<span class="err">出错：${e.message}</span>`;
  } finally {
    btn.disabled = false;
  }
});

function renderIngest(r) {
  const ents = r.entities
    .map(
      (e) => `<div class="kv"><b>${e.name}</b>
        ${e.traits.map((t) => `<span class="tag trait">${t}</span>`).join("")}
        ${e.preferences.map((p) => `<span class="tag pref">${p}</span>`).join("")}</div>`
    )
    .join("");
  const rels = r.relations
    .map((x) => `<span class="tag rel">${x.subject} ${x.relation} ${x.object}</span>`)
    .join("");
  const pats = r.behavior_patterns
    .map((p) => `<div class="kv">· <b>${p.person}</b>：${p.trigger ? `当「${p.trigger}」时，` : ""}${p.behavior}</div>`)
    .join("");
  const ev = r.evolution;
  $("#ingest-result").innerHTML = `
    <div class="kv"><span class="k">情景摘要</span> ${r.episode.summary}</div>
    <div class="kv"><span class="k">主题/情绪</span> ${r.episode.topic} · ${r.episode.emotion} (${r.episode.emotion_intensity})</div>
    <div class="kv"><span class="k">自进化</span> ${ev.action} · 权重 ${ev.weight} · 信号 ${JSON.stringify(ev.signals)}</div>
    <h3>抽取的人物</h3>${ents || '<span class="muted">无</span>'}
    <h3>关系</h3>${rels || '<span class="muted">无</span>'}
    <h3>行为模式</h3>${pats || '<span class="muted">无</span>'}`;
}

// ---------------------------------------------------------------- ask
$("#ask-btn").addEventListener("click", askNow);
$("#ask-input").addEventListener("keydown", (e) => { if (e.key === "Enter") askNow(); });

async function askNow() {
  const query = $("#ask-input").value.trim();
  if (!query) return;
  $("#ask-answer").innerHTML = '<span class="spin">检索记忆并推理中...</span>';
  $("#ask-memories").innerHTML = "";
  try {
    const r = await api("/api/ask", { method: "POST", body: JSON.stringify({ query }) });
    $("#ask-answer").textContent = r.answer;
    $("#ask-memories").innerHTML = r.used_memories
      .map(
        (m) => `<div class="mem"><span class="src src-${m.source}">${m.source}</span>${m.text}
          <span class="score">score ${m.score}</span></div>`
      )
      .join("") || '<span class="muted">（未命中记忆）</span>';
  } catch (e) {
    $("#ask-answer").innerHTML = `<span class="err">出错：${e.message}</span>`;
  }
}

// ---------------------------------------------------------------- predict
$("#predict-btn").addEventListener("click", async () => {
  const person = $("#predict-person").value.trim();
  const situation = $("#predict-situation").value.trim();
  if (!person || !situation) return;
  $("#predict-result").innerHTML = '<span class="spin">基于人格 + 行为模式 + 情景召回预测中...</span>';
  try {
    const r = await api("/api/predict", {
      method: "POST",
      body: JSON.stringify({ person, situation }),
    });
    $("#predict-result").innerHTML = `
      <div class="kv"><span class="k">最可能行为</span> <b>${r.predicted_action}</b></div>
      <div class="kv"><span class="k">置信度</span> ${(r.confidence * 100).toFixed(0)}%
        <span class="bar" style="width:${Math.max(4, r.confidence * 160)}px"></span></div>
      <div class="kv"><span class="k">推理依据</span> ${r.reasoning}</div>
      <div class="kv"><span class="k">其他可能</span> ${r.alternatives.map((a) => `<span class="tag">${a}</span>`).join("") || "无"}</div>`;
  } catch (e) {
    $("#predict-result").innerHTML = `<span class="err">出错：${e.message}</span>`;
  }
});

// ---------------------------------------------------------------- persona
let activePerson = null;
let allPersonNames = [];
async function loadPersonas() {
  try {
    const list = await api("/api/persons");
    allPersonNames = list.map((p) => p.name);
    $("#persona-list").innerHTML = list.length
      ? list
          .map(
            (p) => `<div class="p-item ${p.name === activePerson ? "active" : ""}" data-name="${p.name}">
              ${avatarHTML(p.name, 32)}
              <div class="p-meta"><b>${esc(p.name)}</b><div class="muted">提及 ${p.mention_count} 次</div></div></div>`
          )
          .join("")
      : '<span class="muted">暂无人物，请先摄入对话</span>';
    $$("#persona-list .p-item").forEach((el) =>
      el.addEventListener("click", () => showPerson(el.dataset.name))
    );
  } catch (e) {
    $("#persona-list").innerHTML = `<span class="err">${e.message}</span>`;
  }
}

async function showPerson(name) {
  activePerson = name;
  $$("#persona-list .p-item").forEach((el) =>
    el.classList.toggle("active", el.dataset.name === name)
  );
  $("#persona-detail").innerHTML = '<span class="spin">加载中...</span>';
  try {
    const r = await api(`/api/person/${encodeURIComponent(name)}`);
    renderPersonDetail(r);
  } catch (e) {
    $("#persona-detail").innerHTML = `<span class="err">${e.message}</span>`;
  }
}

function renderPersonDetail(r) {
  const p = r.persona;
  const sortObj = (o) => Object.entries(o).sort((a, b) => b[1] - a[1]);
  const traits = sortObj(p.traits)
    .map(
      ([k, v]) =>
        `<span class="tag trait editable">${esc(k)} <small>${v}</small><button class="tag-x" data-kind="trait" data-key="${esc(
          k
        )}" title="删除">×</button></span>`
    )
    .join("");
  const prefs = sortObj(p.preferences)
    .map(
      ([k, v]) =>
        `<span class="tag pref editable">${esc(k)} <small>${v}</small><button class="tag-x" data-kind="pref" data-key="${esc(
          k
        )}" title="删除">×</button></span>`
    )
    .join("");
  const rels = r.graph.relations
    .map((x) => `<span class="tag rel">${esc(x.label)} ${esc(x.target)}</span>`)
    .join("");
  const pats = p.patterns
    .map(
      (x, i) =>
        `<div class="kv editable">· ${x.trigger ? `当「${esc(x.trigger)}」：` : ""}${esc(
          x.behavior
        )}<button class="tag-x" data-kind="pattern" data-idx="${i}" title="删除">×</button></div>`
    )
    .join("");
  const others = allPersonNames.filter((n) => n !== p.name);
  const mergeOptions = others
    .map((n) => `<option value="${esc(n)}">${esc(n)}</option>`)
    .join("");
  const mergeBlock = others.length
    ? `<div class="merge-row">
         <label class="muted">合并到</label>
         <select id="merge-target">${mergeOptions}</select>
         <button id="merge-btn" class="ghost-btn">合并</button>
       </div>`
    : "";

  $("#persona-detail").innerHTML = `
    <div class="detail-head">${avatarHTML(p.name, 48)}
      <div><h2>${esc(p.name)}</h2>
      ${p.aliases.length ? `<div class="muted">别名：${esc(p.aliases.join(", "))}</div>` : ""}</div>
    </div>
    <div class="summary-row">
      <p id="persona-summary" class="self-summary">${esc(p.summary) || '<span class="muted">（暂无摘要）</span>'}</p>
      <button id="edit-summary-btn" class="ghost-btn">编辑摘要</button>
    </div>
    <h3>特质</h3><div class="tag-wrap">${traits || '<span class="muted">无</span>'}</div>
    <h3>偏好</h3><div class="tag-wrap">${prefs || '<span class="muted">无</span>'}</div>
    <h3>关系</h3><div class="tag-wrap">${rels || '<span class="muted">无</span>'}</div>
    <h3>行为模式</h3>${pats || '<span class="muted">无</span>'}
    <div class="persona-actions">${mergeBlock}</div>`;

  bindPersonEditing(p);
}

async function patchPerson(name, body) {
  return api(`/api/person/${encodeURIComponent(name)}`, {
    method: "PATCH",
    body: JSON.stringify(body),
  });
}

function bindPersonEditing(p) {
  $$("#persona-detail .tag-x").forEach((btn) =>
    btn.addEventListener("click", async () => {
      const kind = btn.dataset.kind;
      const body = {};
      if (kind === "trait") body.remove_traits = [btn.dataset.key];
      else if (kind === "pref") body.remove_preferences = [btn.dataset.key];
      else if (kind === "pattern") body.remove_pattern_indices = [Number(btn.dataset.idx)];
      try {
        const r = await patchPerson(p.name, body);
        renderPersonDetail(r);
      } catch (e) {
        alert("删除失败：" + e.message);
      }
    })
  );

  const editBtn = $("#edit-summary-btn");
  if (editBtn) {
    editBtn.addEventListener("click", () => {
      const cur = p.summary || "";
      const box = $("#persona-summary");
      box.outerHTML = `<textarea id="summary-edit" class="summary-edit" rows="3">${esc(cur)}</textarea>`;
      editBtn.textContent = "保存";
      editBtn.id = "save-summary-btn";
      $("#save-summary-btn").addEventListener("click", async () => {
        const val = $("#summary-edit").value.trim();
        try {
          const r = await patchPerson(p.name, { summary: val });
          renderPersonDetail(r);
        } catch (e) {
          alert("保存失败：" + e.message);
        }
      });
    });
  }

  const mergeBtn = $("#merge-btn");
  if (mergeBtn) {
    mergeBtn.addEventListener("click", async () => {
      const target = $("#merge-target").value;
      if (!target || target === p.name) return;
      if (!confirm(`确定把「${p.name}」合并进「${target}」吗？此操作不可撤销。`)) return;
      try {
        await api("/api/person/merge", {
          method: "POST",
          body: JSON.stringify({ source: p.name, target }),
        });
        activePerson = target;
        await loadPersonas();
        showPerson(target);
      } catch (e) {
        alert("合并失败：" + e.message);
      }
    });
  }
}

// ---------------------------------------------------------------- self
async function loadSelf() {
  const box = $("#self-detail");
  box.innerHTML = '<span class="spin">加载中…</span>';
  try {
    const r = await api("/api/self");
    const p = r.profile;
    const sortObj = (o) => Object.entries(o).sort((a, b) => b[1] - a[1]);
    const traits = sortObj(p.traits)
      .map(([k, v]) => `<span class="tag trait">${esc(k)} <small>${v}</small></span>`)
      .join("");
    const prefs = sortObj(p.preferences)
      .map(([k, v]) => `<span class="tag pref">${esc(k)} <small>${v}</small></span>`)
      .join("");
    const exps = (p.experiences || [])
      .slice()
      .reverse()
      .slice(0, 12)
      .map(
        (e) => `<div class="kv">· ${esc(e.summary)}
          ${e.person ? `<span class="tag rel">${esc(e.person)}</span>` : ""}
          ${e.emotion && e.emotion !== "neutral" ? `<span class="tag">${esc(e.emotion)}</span>` : ""}</div>`
      )
      .join("");
    const known = (r.known_people || [])
      .map(
        (k) => `<div class="kv">· <b>${esc(k.name)}</b>
          <span class="muted">${esc(k.relationship)}</span></div>`
      )
      .join("");
    box.classList.remove("muted");
    box.innerHTML = `
      <div class="detail-head">${avatarHTML(ASSISTANT_NAME, 52)}
        <div><h2>${esc(p.name)}</h2>
        <div class="muted">${esc(p.role)}</div></div>
      </div>
      <p class="self-summary">${esc(p.summary)}</p>
      <div class="kv muted">已互动 ${p.interaction_count} 次</div>
      <h3>进化中的特质</h3>${traits || '<span class="muted">无</span>'}
      <h3>偏好 / 态度</h3>${prefs || '<span class="muted">还没形成</span>'}
      <h3>三叶虫的自我记忆</h3>${exps || '<span class="muted">还没有记下感受，聊几句吧</span>'}
      <h3>认识的人</h3>${known || '<span class="muted">还没认识谁</span>'}`;
  } catch (e) {
    box.innerHTML = `<span class="err">${e.message}</span>`;
  }
}

// ---------------------------------------------------------------- graph
let network = null;
let nodesDS = null;
let edgesDS = null;
let baseNodes = {};
let baseEdges = {};
let highlightActive = false;
let physicsOn = true;

const GROUP_SHAPE = {
  assistant: "star",
  person: "dot",
  trait: "triangle",
  preference: "diamond",
  entity: "square",
};
const GROUP_LABEL = {
  assistant: "三叶虫",
  person: "人物",
  trait: "特质",
  preference: "偏好",
  entity: "实体",
};

// resolved once per render so the graph follows the active theme
let gTheme = null;
function cssVar(name) {
  return getComputedStyle(document.documentElement).getPropertyValue(name).trim();
}
function readGraphTheme() {
  return {
    assistant: cssVar("--g-assistant"),
    assistantDeep: cssVar("--g-assistant-deep"),
    person: cssVar("--g-person"),
    personDeep: cssVar("--g-person-deep"),
    trait: cssVar("--g-trait"),
    traitDeep: cssVar("--g-trait-deep"),
    pref: cssVar("--g-pref"),
    prefDeep: cssVar("--g-pref-deep"),
    entity: cssVar("--g-entity"),
    entityDeep: cssVar("--g-entity-deep"),
    font: cssVar("--g-font"),
    stroke: cssVar("--g-stroke"),
    edgeRelation: cssVar("--g-edge-relation"),
    edgeTrait: cssVar("--g-edge-trait"),
    edgePref: cssVar("--g-edge-pref"),
    edgeSelf: cssVar("--g-edge-self"),
    dimBg: cssVar("--g-node-dim-bg"),
    dimBorder: cssVar("--g-node-dim-border"),
    dimFont: cssVar("--g-node-dim-font"),
    edgeDim: cssVar("--g-edge-dim"),
  };
}
function groupColor(group) {
  if (group === "assistant") return [gTheme.assistant, gTheme.assistantDeep];
  if (group === "person") return [gTheme.person, gTheme.personDeep];
  if (group === "trait") return [gTheme.trait, gTheme.traitDeep];
  if (group === "preference") return [gTheme.pref, gTheme.prefDeep];
  return [gTheme.entity, gTheme.entityDeep];
}

function edgeColor(e) {
  if (e.kind === "trait") return { hi: gTheme.edgeTrait, txt: gTheme.traitDeep };
  if (e.kind === "preference") return { hi: gTheme.edgePref, txt: gTheme.prefDeep };
  if (e.kind === "relation" && (e.label || "").includes("认识"))
    return { hi: gTheme.edgeSelf, txt: gTheme.assistantDeep };
  return { hi: gTheme.edgeRelation, txt: gTheme.personDeep };
}

function styleNode(n) {
  const [color, dark] = groupColor(n.group);
  const shape = GROUP_SHAPE[n.group] || GROUP_SHAPE.entity;
  const isAssistant = n.group === "assistant";
  const isPerson = n.group === "person";
  const size = isAssistant
    ? 36
    : isPerson
    ? 14 + Math.min(22, (n.count || 1) * 2)
    : 11;
  return {
    id: n.id,
    label: n.label,
    group: n.group,
    shape,
    size,
    color: {
      background: color,
      border: dark,
      highlight: { background: color, border: gTheme.font },
      hover: { background: color, border: gTheme.font },
    },
    borderWidth: isAssistant ? 3 : 1.5,
    borderWidthSelected: 3,
    font: {
      color: gTheme.font,
      face: "Noto Sans SC",
      size: isAssistant ? 16 : isPerson ? 13 : 11,
      strokeWidth: isAssistant || isPerson ? 4 : 3,
      strokeColor: gTheme.stroke,
    },
    shadow: isAssistant
      ? { enabled: true, color: gTheme.assistant, size: 22, x: 0, y: 0 }
      : { enabled: false },
    title: `${n.label} · ${GROUP_LABEL[n.group] || "实体"}${n.count ? "（出现 " + n.count + " 次）" : ""}`,
  };
}

function styleEdge(e, i) {
  const c = edgeColor(e);
  return {
    id: "e" + i,
    from: e.from,
    to: e.to,
    label: e.label || "",
    arrows: { to: { enabled: true, scaleFactor: 0.5, type: "arrow" } },
    color: { color: c.hi, opacity: 0.55, highlight: c.hi, hover: c.hi },
    width: Math.max(1, Math.min(5, e.weight || 1)),
    selectionWidth: (w) => w + 1.5,
    smooth: { enabled: true, type: "dynamic", roundness: 0.5 },
    font: {
      color: c.txt,
      size: 10,
      face: "Space Mono",
      strokeWidth: 4,
      strokeColor: gTheme.stroke,
      align: "horizontal",
    },
    title: `${e.label || "关系"}（权重 ${Math.round((e.weight || 1) * 100) / 100}）`,
  };
}

function sizeGraphCanvas() {
  const stage = document.querySelector(".graph-stage");
  if (!stage || !stage.offsetParent) return; // only when the graph tab is visible
  const top = stage.getBoundingClientRect().top;
  stage.style.height = Math.max(380, window.innerHeight - top - 18) + "px";
  if (network) network.redraw();
}
window.addEventListener("resize", sizeGraphCanvas);

function highlightNeighbourhood(nodeId) {
  const connected = new Set(network.getConnectedNodes(nodeId));
  connected.add(nodeId);
  nodesDS.update(
    Object.values(baseNodes).map((n) =>
      connected.has(n.id)
        ? { id: n.id, color: n.color, font: n.font }
        : {
            id: n.id,
            color: { background: gTheme.dimBg, border: gTheme.dimBorder },
            font: { ...n.font, color: gTheme.dimFont, strokeColor: gTheme.dimBg },
          }
    )
  );
  const connEdges = new Set(network.getConnectedEdges(nodeId));
  edgesDS.update(
    Object.values(baseEdges).map((e) =>
      connEdges.has(e.id)
        ? { id: e.id, color: e.color, font: e.font, width: e.width }
        : {
            id: e.id,
            color: { color: gTheme.edgeDim, opacity: 1 },
            font: { color: "rgba(0,0,0,0)", strokeColor: "rgba(0,0,0,0)" },
          }
    )
  );
  highlightActive = true;
}

function resetHighlight() {
  if (!highlightActive) return;
  nodesDS.update(Object.values(baseNodes).map((n) => ({ id: n.id, color: n.color, font: n.font })));
  edgesDS.update(
    Object.values(baseEdges).map((e) => ({ id: e.id, color: e.color, font: e.font, width: e.width }))
  );
  highlightActive = false;
}

async function loadGraph() {
  try {
    sizeGraphCanvas();
    gTheme = readGraphTheme();
    const g = await api("/api/graph");
    const nodes = g.nodes.map(styleNode);
    const edges = g.edges.map(styleEdge);
    nodesDS = new vis.DataSet(nodes);
    edgesDS = new vis.DataSet(edges);
    baseNodes = {};
    nodes.forEach((n) => (baseNodes[n.id] = n));
    baseEdges = {};
    edges.forEach((e) => (baseEdges[e.id] = e));

    const container = $("#graph-canvas");
    physicsOn = true;
    network = new vis.Network(
      container,
      { nodes: nodesDS, edges: edgesDS },
      {
        autoResize: true,
        nodes: { shadow: { enabled: false } },
        edges: { hoverWidth: 0.6 },
        physics: {
          enabled: true,
          solver: "forceAtlas2Based",
          forceAtlas2Based: {
            gravitationalConstant: -46,
            centralGravity: 0.012,
            springLength: 120,
            springConstant: 0.08,
            damping: 0.55,
            avoidOverlap: 0.6,
          },
          stabilization: { iterations: 240, fit: true },
        },
        interaction: {
          hover: true,
          tooltipDelay: 120,
          hideEdgesOnDrag: true,
          navigationButtons: false,
          keyboard: false,
        },
      }
    );

    network.on("hoverNode", (p) => highlightNeighbourhood(p.node));
    network.on("blurNode", () => resetHighlight());
    network.on("click", (p) => {
      if (p.nodes && p.nodes.length) highlightNeighbourhood(p.nodes[0]);
      else resetHighlight();
    });

    const cnt = $("#graph-count");
    if (cnt) cnt.textContent = `${g.nodes.length} 节点 · ${g.edges.length} 关系`;

    sizeGraphCanvas();
    network.once("stabilizationIterationsDone", () => {
      network.setOptions({ physics: { enabled: false } });
      physicsOn = false;
      syncPhysicsBtn();
      network.fit({ animation: { duration: 700, easingFunction: "easeInOutCubic" } });
    });
  } catch (e) {
    $("#graph-canvas").innerHTML = `<span class="err">${e.message}</span>`;
  }
}

function syncPhysicsBtn() {
  const b = $("#graph-physics");
  if (b) b.textContent = physicsOn ? "冻结" : "运行";
}

$("#graph-fit")?.addEventListener("click", () => network && network.fit({ animation: true }));
$("#graph-relayout")?.addEventListener("click", () => {
  if (!network) return;
  physicsOn = true;
  syncPhysicsBtn();
  network.setOptions({ physics: { enabled: true } });
  network.stabilize(200);
  network.once("stabilizationIterationsDone", () => {
    network.setOptions({ physics: { enabled: false } });
    physicsOn = false;
    syncPhysicsBtn();
    network.fit({ animation: true });
  });
});
$("#graph-physics")?.addEventListener("click", () => {
  if (!network) return;
  physicsOn = !physicsOn;
  network.setOptions({ physics: { enabled: physicsOn } });
  syncPhysicsBtn();
});

// ---------------------------------------------------------------- chat
let currentSession = null;
let currentPerson = null;

function esc(s) {
  return (s || "").replace(/[&<>]/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;" }[c]));
}

async function loadSessions() {
  try {
    const list = await api("/api/chat/sessions");
    const el = $("#session-list");
    el.innerHTML = list.length
      ? list
          .map(
            (s) => `<div class="session-item ${s.id === currentSession ? "active" : ""}" data-id="${s.id}">
              <button class="del" data-del="${s.id}" title="删除">✕</button>
              <div class="session-row">
                ${avatarHTML(s.person || s.title, 32)}
                <div class="session-text">
                  <div class="title">${esc(s.person || s.title)}</div>
                  <div class="last">${esc(s.last_message) || "（新会话）"}</div>
                </div>
              </div>
            </div>`
          )
          .join("")
      : '<span class="muted">还没有会话，点击上方新建</span>';
    $$("#session-list .session-item").forEach((it) =>
      it.addEventListener("click", (e) => {
        if (e.target.dataset.del) return;
        openSession(it.dataset.id);
      })
    );
    $$("#session-list .del").forEach((b) =>
      b.addEventListener("click", async (e) => {
        e.stopPropagation();
        await api(`/api/chat/session/${b.dataset.del}`, { method: "DELETE" });
        if (currentSession === b.dataset.del) {
          currentSession = null;
          $("#chat-window").classList.add("hidden");
          $("#chat-empty").classList.remove("hidden");
        }
        loadSessions();
      })
    );
  } catch (e) {
    $("#session-list").innerHTML = `<span class="err">${e.message}</span>`;
  }
}

$("#new-chat-btn").addEventListener("click", async () => {
  try {
    const r = await api("/api/chat/session", { method: "POST" });
    await loadSessions();
    await openSession(r.session_id);
  } catch (e) {
    alert("新建失败：" + e.message);
  }
});

function setChatEnabled(on) {
  $("#chat-input").disabled = !on;
  $("#chat-send").disabled = !on;
  const mic = $("#chat-mic");
  if (mic) mic.disabled = !on || !voiceSupported;
}

// ---------------------------------------------------------------- TTS
// resolves when the utterance finishes (or immediately when TTS is off/unsupported)
// so the hands-free loop can wait for 三叶虫 to stop talking before listening again.
function speak(text) {
  return new Promise((resolve) => {
    if (!$("#tts-toggle") || !$("#tts-toggle").checked) return resolve();
    if (!("speechSynthesis" in window) || !text) return resolve();
    try {
      window.speechSynthesis.cancel();
      const u = new SpeechSynthesisUtterance(text);
      u.lang = "zh-CN";
      const zh = (window.speechSynthesis.getVoices() || []).find((v) =>
        (v.lang || "").toLowerCase().startsWith("zh")
      );
      if (zh) u.voice = zh;
      let done = false;
      const finish = () => {
        if (done) return;
        done = true;
        resolve();
      };
      u.onend = finish;
      u.onerror = finish;
      // safety net: some browsers never fire onend for long text
      const guard = setTimeout(finish, Math.max(4000, text.length * 220));
      const clearGuard = () => clearTimeout(guard);
      u.addEventListener("end", clearGuard);
      u.addEventListener("error", clearGuard);
      window.speechSynthesis.speak(u);
    } catch (e) {
      resolve();
    }
  });
}

async function openSession(id) {
  currentSession = id;
  currentPerson = null;
  $("#chat-empty").classList.add("hidden");
  $("#chat-window").classList.remove("hidden");
  $$("#session-list .session-item").forEach((el) =>
    el.classList.toggle("active", el.dataset.id === id)
  );
  resetSidePanel();
  if (conversing) stopConversation();
  clearVoiceUI();
  try {
    const detail = await api(`/api/chat/session/${id}`);
    currentPerson = detail.session.person || null;
    renderMessages(detail.messages);
    setChatEnabled(true);
    if (detail.session.person) $("#side-person").textContent = detail.session.person;
    $("#chat-input").focus();
  } catch (e) {
    $("#chat-messages").innerHTML = `<span class="err">${e.message}</span>`;
  }
}

function fmtTime(ts) {
  if (!ts) return "";
  const d = new Date(ts * 1000);
  if (isNaN(d.getTime())) return "";
  return d.toLocaleTimeString("zh-CN", { hour: "2-digit", minute: "2-digit" });
}

function bubbleHTML(role, content, typing = false, ts = null) {
  const isA = role === "assistant";
  const who = isA ? ASSISTANT_NAME : currentPerson || "我";
  const av = avatarHTML(who, 30);
  const time = ts ? `<time class="msg-time">${fmtTime(ts)}</time>` : "";
  const body = typing
    ? `<span class="typing-dots" aria-label="三叶虫正在思考"><i></i><i></i><i></i></span>`
    : esc(content);
  return `<div class="msg ${role}${typing ? " typing" : ""}">
    ${av}
    <div class="msg-col">
      <div class="msg-meta"><span class="who">${esc(who)}</span>${time}</div>
      <div class="bubble ${role}">${body}</div>
    </div>
  </div>`;
}

// keep the view pinned to the latest message, even while the LLM streams in
function scrollToBottom(box, smooth = true) {
  box.scrollTo({ top: box.scrollHeight, behavior: smooth ? "smooth" : "auto" });
}

function renderMessages(msgs) {
  const box = $("#chat-messages");
  box.innerHTML = msgs
    .map((m) => bubbleHTML(m.role, m.content, false, m.created_at))
    .join("");
  scrollToBottom(box, false);
}

function appendBubble(role, content, typing = false) {
  const box = $("#chat-messages");
  const tmp = document.createElement("div");
  const ts = typing ? null : Date.now() / 1000;
  tmp.innerHTML = bubbleHTML(role, content, typing, ts).trim();
  const div = tmp.firstElementChild;
  box.appendChild(div);
  scrollToBottom(box);
  return div;
}

async function sendChat() {
  const input = $("#chat-input");
  const text = input.value.trim();
  if (!text || !currentSession) return;
  input.value = "";
  appendBubble("user", text);
  setChatEnabled(false);
  const typing = appendBubble("assistant", "", true);
  try {
    const r = await api("/api/chat/message", {
      method: "POST",
      body: JSON.stringify({ session_id: currentSession, message: text }),
    });
    typing.remove();
    if (r.person) currentPerson = r.person;
    appendBubble("assistant", r.reply);
    speak(r.reply);
    if (r.person) $("#side-person").textContent = r.person;
    renderSide(r);
    refreshStats();
    loadSessions();
  } catch (e) {
    typing.remove();
    appendBubble("assistant", "（出错了：" + e.message + "）");
  } finally {
    setChatEnabled(true);
    input.focus();
  }
}

$("#chat-send").addEventListener("click", sendChat);
$("#chat-input").addEventListener("keydown", (e) => {
  if (e.key === "Enter") sendChat();
});

// ---------------------------------------------------------------- voice
const voiceSupported =
  !!navigator.mediaDevices &&
  !!navigator.mediaDevices.getUserMedia &&
  typeof window.MediaRecorder !== "undefined";

let mediaRecorder = null;
let recordChunks = [];
let recording = false;

// --- hands-free continuous conversation state ---
let conversing = false; // hands-free loop is active
let loopPaused = false; // paused while waiting for identity confirm
let hfStream = null; // persistent mic stream for the whole loop
let hfCtx = null; // AudioContext used for energy-based VAD
let hfAnalyser = null;
let hfSource = null;
let hfRecorder = null;
let hfChunks = [];
let vadTimer = null;
let hfState = null; // { hasSpoken, startAt, lastVoiceAt }

// VAD / utterance tuning (browser-side, energy based)
const VAD_START_RMS = 0.025; // RMS above this counts as speech
const VAD_SILENCE_MS = 900; // trailing silence that ends an utterance
const VAD_MAX_MS = 15000; // hard cap on a single utterance
const VAD_MIN_SPEECH_MS = 300; // shorter clips are discarded as noise
const VAD_IDLE_RESET_MS = 20000; // recycle recorder if nobody speaks

function getMicConstraints() {
  // browser DSP noticeably improves Whisper accuracy and kills TTS echo
  return {
    echoCancellation: true,
    noiseSuppression: true,
    autoGainControl: true,
    channelCount: 1,
  };
}

function pickMimeType() {
  if (typeof MediaRecorder === "undefined" || !MediaRecorder.isTypeSupported) return "";
  const cands = ["audio/webm;codecs=opus", "audio/webm", "audio/ogg;codecs=opus"];
  for (const c of cands) {
    if (MediaRecorder.isTypeSupported(c)) return c;
  }
  return "";
}

function newRecorder(stream) {
  const mime = pickMimeType();
  try {
    return mime
      ? new MediaRecorder(stream, { mimeType: mime, audioBitsPerSecond: 32000 })
      : new MediaRecorder(stream);
  } catch (e) {
    return new MediaRecorder(stream);
  }
}

function isHandsFree() {
  const t = $("#handsfree-toggle");
  return !!(t && t.checked);
}

function voiceStatus(text) {
  const el = $("#voice-status");
  if (!el) return;
  if (!text) {
    el.classList.add("hidden");
    el.textContent = "";
  } else {
    el.classList.remove("hidden");
    el.textContent = text;
  }
}

function clearVoiceUI() {
  const c = $("#voice-confirm");
  if (c) {
    c.classList.add("hidden");
    c.innerHTML = "";
  }
  voiceStatus("");
}

// shared rendering for a /api/chat/voice response; returns the stage + reply so
// callers (single-shot vs hands-free loop) can decide what to do next.
function applyVoiceResponse(r) {
  if (!r.identified && !r.person) {
    // identity stage: show transcript + confirm bar, do not bind yet
    if (r.transcript) $("#chat-input").value = r.transcript;
    appendBubble("assistant", r.reply);
    renderVoiceConfirm(r);
    return { stage: "identity", reply: r.reply };
  }
  // active stage: full message round-trip
  if (r.transcript) appendBubble("user", r.transcript);
  if (r.person) currentPerson = r.person;
  appendBubble("assistant", r.reply);
  if (r.person) $("#side-person").textContent = r.person;
  renderSide(r);
  refreshStats();
  loadSessions();
  return { stage: "active", reply: r.reply };
}

async function postVoice(blob) {
  const fd = new FormData();
  fd.append("session_id", currentSession);
  fd.append("audio", blob, "voice.webm");
  return api("/api/chat/voice", { method: "POST", body: fd });
}

// ---------------------------------------------------------- mic entry point
function onMicClick() {
  if (!voiceSupported) {
    alert("当前浏览器不支持录音（需要 MediaRecorder + 麦克风权限）。");
    return;
  }
  if (!currentSession) return;
  if (isHandsFree()) {
    if (conversing) stopConversation();
    else startConversation();
  } else {
    toggleRecording();
  }
}

// ---------------------------------------------------- single-shot recording
async function toggleRecording() {
  if (recording) {
    stopRecording();
    return;
  }
  try {
    const stream = await navigator.mediaDevices.getUserMedia({ audio: getMicConstraints() });
    recordChunks = [];
    mediaRecorder = newRecorder(stream);
    mediaRecorder.ondataavailable = (e) => {
      if (e.data && e.data.size > 0) recordChunks.push(e.data);
    };
    mediaRecorder.onstop = async () => {
      stream.getTracks().forEach((t) => t.stop());
      const blob = new Blob(recordChunks, { type: mediaRecorder.mimeType || "audio/webm" });
      if (blob.size < 1200) {
        // too short / empty -> don't bother the recogniser
        voiceStatus("");
        return;
      }
      await uploadVoice(blob);
    };
    mediaRecorder.start();
    recording = true;
    $("#chat-mic").classList.add("recording");
    $("#chat-mic").textContent = "■";
    voiceStatus("聆听中… 再按一下麦克风结束");
  } catch (e) {
    alert("无法访问麦克风：" + e.message);
  }
}

function stopRecording() {
  if (mediaRecorder && recording) {
    recording = false;
    $("#chat-mic").classList.remove("recording");
    $("#chat-mic").textContent = "🎙";
    voiceStatus("识别中…");
    try {
      mediaRecorder.stop();
    } catch (e) {}
  }
}

async function uploadVoice(blob) {
  if (!currentSession) return;
  setChatEnabled(false);
  try {
    const r = await postVoice(blob);
    voiceStatus("");
    const res = applyVoiceResponse(r);
    speak(res.reply);
  } catch (e) {
    voiceStatus("");
    appendBubble("assistant", "（语音出错了：" + e.message + "）");
  } finally {
    setChatEnabled(true);
  }
}

// --------------------------------------------- hands-free conversation loop
async function startConversation() {
  try {
    hfStream = await navigator.mediaDevices.getUserMedia({ audio: getMicConstraints() });
  } catch (e) {
    alert("无法访问麦克风：" + e.message);
    return;
  }
  const AC = window.AudioContext || window.webkitAudioContext;
  if (!AC) {
    hfStream.getTracks().forEach((t) => t.stop());
    hfStream = null;
    alert("当前浏览器不支持连续对话所需的音频分析（AudioContext）。");
    return;
  }
  try {
    hfCtx = new AC();
    hfSource = hfCtx.createMediaStreamSource(hfStream);
    hfAnalyser = hfCtx.createAnalyser();
    hfAnalyser.fftSize = 2048;
    hfSource.connect(hfAnalyser);
  } catch (e) {
    teardownAudio();
    alert("无法初始化音频分析：" + e.message);
    return;
  }
  conversing = true;
  loopPaused = false;
  $("#chat-mic").classList.add("recording");
  $("#chat-mic").textContent = "■";
  listenOnce();
}

function teardownAudio() {
  if (vadTimer) {
    clearInterval(vadTimer);
    vadTimer = null;
  }
  if (hfStream) {
    hfStream.getTracks().forEach((t) => t.stop());
    hfStream = null;
  }
  if (hfCtx) {
    try {
      hfCtx.close();
    } catch (e) {}
    hfCtx = null;
  }
  hfAnalyser = null;
  hfSource = null;
}

function stopConversation() {
  conversing = false;
  loopPaused = false;
  if (vadTimer) {
    clearInterval(vadTimer);
    vadTimer = null;
  }
  if (hfRecorder) {
    try {
      hfRecorder.onstop = null;
      if (hfRecorder.state !== "inactive") hfRecorder.stop();
    } catch (e) {}
    hfRecorder = null;
  }
  teardownAudio();
  $("#chat-mic").classList.remove("recording");
  $("#chat-mic").textContent = "🎙";
  voiceStatus("");
}

function listenOnce() {
  if (!conversing || loopPaused || !hfStream) return;
  hfChunks = [];
  hfRecorder = newRecorder(hfStream);
  hfRecorder.ondataavailable = (e) => {
    if (e.data && e.data.size > 0) hfChunks.push(e.data);
  };
  hfRecorder.onstop = onUtteranceStop;
  const startAt = Date.now();
  hfState = { hasSpoken: false, startAt, lastVoiceAt: startAt };
  try {
    hfRecorder.start();
  } catch (e) {
    return;
  }
  voiceStatus("聆听中…说话即可（点麦克风结束）");

  const buf = new Uint8Array(hfAnalyser ? hfAnalyser.fftSize : 0);
  vadTimer = setInterval(() => {
    if (!conversing || !hfAnalyser) return;
    const now = Date.now();
    hfAnalyser.getByteTimeDomainData(buf);
    let sum = 0;
    for (let i = 0; i < buf.length; i++) {
      const v = (buf[i] - 128) / 128;
      sum += v * v;
    }
    const rms = Math.sqrt(sum / buf.length);
    if (rms > VAD_START_RMS) {
      if (!hfState.hasSpoken) voiceStatus("录音中…");
      hfState.hasSpoken = true;
      hfState.lastVoiceAt = now;
    }
    const elapsed = now - hfState.startAt;
    const silence = now - hfState.lastVoiceAt;
    if (hfState.hasSpoken && silence > VAD_SILENCE_MS) return finishUtterance();
    if (elapsed > VAD_MAX_MS) return finishUtterance();
    // nobody spoke for a long time -> recycle so the blob never balloons
    if (!hfState.hasSpoken && elapsed > VAD_IDLE_RESET_MS) return finishUtterance();
  }, 100);
}

function finishUtterance() {
  if (vadTimer) {
    clearInterval(vadTimer);
    vadTimer = null;
  }
  try {
    if (hfRecorder && hfRecorder.state !== "inactive") hfRecorder.stop();
  } catch (e) {}
}

async function onUtteranceStop() {
  const spoke = hfState && hfState.hasSpoken;
  const dur = hfState ? Date.now() - hfState.startAt : 0;
  const mime = (hfRecorder && hfRecorder.mimeType) || "audio/webm";
  const blob = new Blob(hfChunks, { type: mime });
  hfRecorder = null;
  if (!conversing) return;
  if (!spoke || dur < VAD_MIN_SPEECH_MS || blob.size < 1200) {
    // silence / noise -> just keep listening
    if (conversing && !loopPaused) listenOnce();
    return;
  }
  await processLoopBlob(blob);
}

async function processLoopBlob(blob) {
  setChatEnabled(false);
  voiceStatus("识别中…");
  let stage = "active";
  let reply = "";
  try {
    const r = await postVoice(blob);
    const res = applyVoiceResponse(r);
    stage = res.stage;
    reply = res.reply;
  } catch (e) {
    appendBubble("assistant", "（语音出错了：" + e.message + "）");
    setChatEnabled(true);
    voiceStatus("");
    if (conversing && !loopPaused) listenOnce();
    return;
  }
  setChatEnabled(true);
  voiceStatus("三叶虫回复中…");
  await speak(reply); // don't record while 三叶虫 is talking (avoids echo)
  voiceStatus("");
  if (stage === "identity") {
    // wait for the user to confirm who they are before resuming the loop
    loopPaused = true;
    voiceStatus("请确认身份后继续对话…");
    return;
  }
  if (conversing && !loopPaused) listenOnce();
}

function renderVoiceConfirm(r) {
  const box = $("#voice-confirm");
  if (!box) return;
  const sugg = r.voice_suggestions || [];
  const top = sugg[0];
  const chips = sugg
    .map(
      (s) =>
        `<button class="vc-chip" data-person="${esc(s.person)}">${esc(s.person)}${
          s.source === "voiceprint" ? ` <small>声纹 ${(s.score * 100).toFixed(0)}%</small>` : " <small>听写</small>"
        }</button>`
    )
    .join("");
  box.innerHTML = `
    <div class="vc-title">${top ? "听声音你是不是 <b>" + esc(top.person) + "</b>？" : "你是谁呀？"}</div>
    <div class="vc-chips">${chips}</div>
    <div class="vc-manual">
      <input id="vc-name" type="text" placeholder="都不是？输入你的名字" value="${esc(r.transcript ? "" : "")}" />
      <button id="vc-confirm" class="primary">确认身份</button>
    </div>`;
  box.classList.remove("hidden");
  $$("#voice-confirm .vc-chip").forEach((b) =>
    b.addEventListener("click", () => confirmVoice(b.dataset.person))
  );
  $("#vc-confirm").addEventListener("click", () => {
    const name = $("#vc-name").value.trim();
    if (name) confirmVoice(name);
  });
}

async function confirmVoice(person) {
  if (!currentSession || !person) return;
  clearVoiceUI();
  setChatEnabled(false);
  let reply = "";
  try {
    const r = await api("/api/chat/voice/confirm", {
      method: "POST",
      body: JSON.stringify({ session_id: currentSession, person }),
    });
    if (r.person) currentPerson = r.person;
    appendBubble("assistant", r.reply);
    reply = r.reply;
    if (r.person) $("#side-person").textContent = r.person;
    renderSide(r);
    $("#chat-input").value = "";
    refreshStats();
    loadSessions();
  } catch (e) {
    appendBubble("assistant", "（确认身份出错了：" + e.message + "）");
  } finally {
    setChatEnabled(true);
  }
  await speak(reply);
  // identity settled -> resume the hands-free loop if it was paused for this
  if (conversing) {
    loopPaused = false;
    listenOnce();
  }
}

$("#chat-mic").addEventListener("click", onMicClick);
// turning the hands-free switch off mid-conversation should end the loop
$("#handsfree-toggle")?.addEventListener("change", () => {
  if (!isHandsFree() && conversing) stopConversation();
});
// warm up voice list for TTS (some browsers populate asynchronously)
if ("speechSynthesis" in window) {
  window.speechSynthesis.onvoiceschanged = () => window.speechSynthesis.getVoices();
}

function resetSidePanel() {
  $("#side-person").textContent = "…";
  $("#side-understanding").innerHTML = '<span class="muted">开始聊天后这里会实时更新</span>';
  $("#side-prediction").innerHTML = '<span class="muted">—</span>';
  $("#side-memories").innerHTML = '<span class="muted">—</span>';
}

function renderSide(r) {
  const u = r.understanding;
  if (u) {
    const traits = u.traits
      .slice(0, 8)
      .map((t) => `<span class="tag trait">${esc(t.name)} <small>${t.weight}</small></span>`)
      .join("");
    const prefs = u.preferences
      .slice(0, 8)
      .map((t) => `<span class="tag pref">${esc(t.name)} <small>${t.weight}</small></span>`)
      .join("");
    const rels = (u.relations || [])
      .slice(0, 6)
      .map((x) => `<span class="tag rel">${esc(x.label)} ${esc(x.target)}</span>`)
      .join("");
    const pats = (u.patterns || [])
      .slice(0, 5)
      .map((p) => `<div class="kv">· ${p.trigger ? "当「" + esc(p.trigger) + "」：" : ""}${esc(p.behavior)}</div>`)
      .join("");
    const mutual = (u.mutual_acquaintances || [])
      .map((m) => `<span class="tag rel">${esc(m)}</span>`)
      .join("");
    const selfRel = u.assistant_relationship
      ? `<div class="side-card" style="margin-bottom:10px">
           <div class="kv"><span class="k">三叶虫与TA</span> ${esc(u.assistant_relationship)}</div>
           ${mutual ? '<div class="kv"><span class="k">共同认识</span> ' + mutual + "</div>" : ""}
         </div>`
      : "";
    $("#side-understanding").innerHTML = `
      <div class="side-person-head">${avatarHTML(u.name, 30)}<b>${esc(u.name)}</b></div>
      ${selfRel}
      <div class="kv muted">已提及 ${u.mention_count} 次</div>
      <h4 style="margin:8px 0 4px">特质</h4>${traits || '<span class="muted">暂无</span>'}
      <h4 style="margin:8px 0 4px">偏好</h4>${prefs || '<span class="muted">暂无</span>'}
      <h4 style="margin:8px 0 4px">关系</h4>${rels || '<span class="muted">暂无</span>'}
      ${pats ? '<h4 style="margin:8px 0 4px">行为模式</h4>' + pats : ""}`;
  }

  const p = r.prediction;
  if (p) {
    $("#side-prediction").innerHTML = `
      <div class="kv"><b>${esc(p.predicted_action)}</b></div>
      <div class="conf-bar-wrap"><div class="conf-bar" style="width:${Math.round(p.confidence * 100)}%"></div></div>
      <div class="kv muted">置信度 ${(p.confidence * 100).toFixed(0)}%</div>
      <div class="kv">${esc(p.reasoning)}</div>`;
  } else {
    $("#side-prediction").innerHTML = '<span class="muted">—</span>';
  }

  const mems = r.used_memories || [];
  $("#side-memories").innerHTML = mems.length
    ? mems
        .map(
          (m) => `<div class="mem"><span class="src src-${m.source}">${m.source}</span>${esc(m.text)}</div>`
        )
        .join("")
    : '<span class="muted">本轮未命中已有记忆</span>';
}

// ---------------------------------------------------------------- theme
const THEME_KEY = "trilobite-theme";
const THEMES = ["parchment", "midnight", "abyss"];
function applyTheme(name, persist) {
  const theme = THEMES.includes(name) ? name : "parchment";
  document.documentElement.dataset.theme = theme;
  // keep color-scheme in sync so browser auto-dark mode doesn't override us
  document.documentElement.style.colorScheme = theme === "parchment" ? "light" : "dark";
  if (persist) {
    try {
      localStorage.setItem(THEME_KEY, theme);
    } catch (e) {}
  }
  const sel = $("#theme-select");
  if (sel) sel.value = theme;
  // graph colours are baked into vis-network data -> re-render if it exists
  if (network) loadGraph();
}
function initTheme() {
  let saved = "parchment";
  try {
    saved = localStorage.getItem(THEME_KEY) || "parchment";
  } catch (e) {}
  applyTheme(saved, false);
  const sel = $("#theme-select");
  if (sel) sel.addEventListener("change", () => applyTheme(sel.value, true));
}

initTheme();
refreshStats();
loadSelf();
loadSessions();
