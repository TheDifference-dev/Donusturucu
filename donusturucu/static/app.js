/* Dönüştürücü arayüzü — saf JavaScript, sunucu: /api/* */
"use strict";
const $ = (s, el = document) => el.querySelector(s);
const $$ = (s, el = document) => [...el.querySelectorAll(s)];
const h = (tag, attrs = {}, ...kids) => {
  const el = document.createElement(tag);
  for (const [k, v] of Object.entries(attrs || {})) {
    if (v === null || v === undefined || v === false) continue;
    if (k === "class") el.className = v;
    else if (k === "style" && typeof v === "object") Object.assign(el.style, v);
    else if (k.startsWith("on")) el.addEventListener(k.slice(2), v);
    else if (k === "html") el.innerHTML = v;
    else el.setAttribute(k, v === true ? "" : v);
  }
  for (const k of kids.flat()) if (k !== null && k !== undefined && k !== false) el.append(k.nodeType ? k : document.createTextNode(k));
  return el;
};
const fmtSize = (b) => b > 1048576 ? (b / 1048576).toFixed(1) + " MB" : Math.max(1, Math.round(b / 1024)) + " KB";
const store = {
  get(k, d) { try { const v = localStorage.getItem(k); return v === null ? d : JSON.parse(v); } catch { return d; } },
  set(k, v) { try { localStorage.setItem(k, JSON.stringify(v)); } catch {} },
};

let CAT = null, CATS = {}, S = null, CARRY = null;

async function api(path, body, method) {
  const r = await fetch(path, body === undefined ? { method: method || "GET" } : {
    method: method || "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(body) });
  let data = null;
  try { data = await r.json(); } catch { data = { error: "Sunucudan yanıt alınamadı." }; }
  if (!r.ok || (data && data.error)) throw new Error((data && data.error) || r.statusText);
  return data;
}

function upload(files, dataurls = [], onprog) {
  return new Promise((res, rej) => {
    const fd = new FormData();
    for (const f of files) fd.append("files", f, f.name);
    for (const d of dataurls) fd.append("dataurl", d);
    const x = new XMLHttpRequest();
    x.open("POST", "/api/upload");
    x.upload.onprogress = (e) => e.lengthComputable && onprog && onprog(e.loaded / e.total);
    x.onload = () => { try { const d = JSON.parse(x.responseText); x.status < 300 ? res(d) : rej(new Error(d.error || "Yükleme hatası")); } catch { rej(new Error("Yükleme hatası")); } };
    x.onerror = () => rej(new Error("Yükleme başarısız"));
    x.send(fd);
  });
}

function toast(msg, ms = 2600) {
  const t = $("#toast"); t.textContent = msg; t.hidden = false;
  clearTimeout(toast._t); toast._t = setTimeout(() => (t.hidden = true), ms);
}
function modal(content) {
  const m = $("#modal"); const b = $(".modal-body", m); b.innerHTML = ""; b.append(content); m.hidden = false;
  return () => (m.hidden = true);
}
$("#modal .modal-x").onclick = () => ($("#modal").hidden = true);
$("#modal").addEventListener("click", (e) => { if (e.target.id === "modal") $("#modal").hidden = true; });

/* ------------------------------------------------------------ tema */
function applyTheme() { const t = store.get("tema", "system"); if (t === "system") delete document.documentElement.dataset.theme; else document.documentElement.dataset.theme = t; }
applyTheme();

/* ------------------------------------------------------------ yönlendirme */
function go(hash) { if (location.hash === hash) route(); else location.hash = hash; }
window.addEventListener("hashchange", route);
document.addEventListener("click", (e) => { const n = e.target.closest("[data-nav]"); if (n) { e.preventDefault(); go("#/"); } });

async function init() {
  CAT = await api("/api/catalog");
  CAT.categories.forEach((c) => (CATS[c.id] = c));
  route();
  setInterval(() => fetch("/api/ping", { method: "POST" }).catch(() => {}), 20000);
  fetch("/api/ping", { method: "POST" }).catch(() => {});
}
function route() {
  const m = location.hash.match(/^#\/arac\/(\w+)/);
  if (m && CAT.tools.find((t) => t.id === m[1])) openTool(m[1]);
  else renderHome();
  window.scrollTo(0, 0);
}

/* ------------------------------------------------------------ ana sayfa */
let homeCat = "all";
function renderHome() {
  const v = $("#view"); v.innerHTML = ""; v.append($("#tpl-home").content.cloneNode(true));
  const cats = $("#cats");
  const mk = (id, title) => h("button", { class: "chip" + (homeCat === id ? " on" : ""), onclick: () => { homeCat = id; renderHome(); } }, title);
  cats.append(mk("all", "Tümü"), ...CAT.categories.map((c) => mk(c.id, c.title)));
  drawCards();
}
function drawCards() {
  const grid = $("#tools"); if (!grid) return;
  grid.innerHTML = "";
  const q = ($("#search").value || "").toLocaleLowerCase("tr").trim();
  const match = (t) => !q || (t.title + " " + t.desc + " " + t.accept.join(" ")).toLocaleLowerCase("tr").includes(q);
  for (const c of CAT.categories) {
    if (homeCat !== "all" && homeCat !== c.id) continue;
    const list = CAT.tools.filter((t) => t.cat === c.id && match(t));
    if (!list.length) continue;
    grid.append(h("h4", { class: "cat-title" }, c.title));
    for (const t of list) grid.append(card(t));
  }
  if (!grid.children.length) grid.append(h("p", { class: "hint" }, "Eşleşen araç yok."));
}
function card(t) {
  return h("button", { class: "card" + (t.cat === "media" ? " feature" : ""), onclick: () => go("#/arac/" + t.id) },
    h("div", { class: "badge", style: { background: CATS[t.cat].color } }, t.icon), h("h3", {}, t.title), h("p", {}, t.desc));
}
$("#search").addEventListener("input", () => { if (!$("#tools")) go("#/"); setTimeout(drawCards, 0); });

/* ------------------------------------------------------------ araç ekranı */
function openTool(id) {
  const tool = CAT.tools.find((t) => t.id === id);
  S = { tool, files: [], opts: {}, extra: {}, org: null, sel: new Set(), placer: null, fields: null, busy: false };
  for (const o of tool.opts) S.opts[o.key] = o.default;
  const v = $("#view"); v.innerHTML = "";
  v.append(
    h("div", { class: "tool-head" },
      h("button", { class: "back", onclick: () => go("#/") }, "← Araçlar"),
      h("div", { class: "badge", style: { background: CATS[tool.cat].color } }, tool.icon),
      h("div", {}, h("h2", {}, tool.title), h("p", {}, tool.desc))),
    h("div", { class: "layout" }, h("section", { id: "work" }), h("aside", { class: "side", id: "side" })));
  if (CARRY) { const c = CARRY; CARRY = null; addUploaded(c); }
  renderWork(); renderSide();
}

function accepts(t, ext) { return t.accept.includes((ext || "").toLowerCase()); }

function pickFiles(multi, accept, cb) {
  const i = h("input", { type: "file", accept: accept.map((e) => "." + e).join(","), multiple: multi || null, style: { display: "none" } });
  i.onchange = () => { cb([...i.files]); i.remove(); };
  document.body.append(i); i.click();
}

async function addFiles(list) {
  const t = S.tool;
  const ok = list.filter((f) => accepts(t, f.name.split(".").pop()));
  const bad = list.length - ok.length;
  if (bad) toast(`${bad} dosya bu araç için uygun değil (kabul edilen: ${t.accept.join(", ")})`, 4000);
  if (!ok.length) return;
  const files = t.multi ? ok : ok.slice(0, 1);
  const work = $("#work");
  const prog = h("div", { class: "panel" }, h("p", {}, "Yükleniyor…"), h("div", { class: "bar" }, h("i")));
  work.prepend(prog);
  try {
    const up = await upload(files, [], (p) => ($("i", prog).style.width = (p * 100).toFixed(0) + "%"));
    addUploaded(up);
  } catch (e) { toast(e.message, 5000); }
  prog.remove();
  renderWork(); renderSide();
}
function addUploaded(up) {
  if (!S.tool.multi) S.files = [];
  for (const f of up) {
    if (f.encrypted && S.tool.id !== "unlock") toast(`${f.name} parola korumalı — önce "PDF Kilidini Aç" aracını kullanın.`, 5000);
    S.files.push(f);
  }
  if (S.tool.exact_files) S.files = S.files.slice(-S.tool.exact_files);
  S.org = null; S.sel.clear(); S.placer = null; S.fields = null;
}

function dropZone(small) {
  const t = S.tool;
  const z = h("div", { class: "drop" },
    small ? null : h("div", { class: "big" }, "⬆"),
    h("p", {}, h("button", { class: "btn primary", onclick: () => pickFiles(t.multi, t.accept, addFiles) },
      t.multi ? "Dosyaları seç" : "Dosya seç"), "  ya da buraya sürükleyin"),
    h("p", { class: "hint" }, "Kabul edilen: " + t.accept.map((e) => e.toUpperCase()).join(", ")),
    t.camera ? h("p", {}, h("button", { class: "btn", onclick: openCamera }, "📷 Kamerayla çek")) : null,
    t.optional_files ? h("p", { class: "hint" }, "Dosya seçmeden de kullanabilirsiniz (sağdaki alanı doldurun).") : null);
  ["dragenter", "dragover"].forEach((ev) => z.addEventListener(ev, (e) => { e.preventDefault(); z.classList.add("over"); }));
  ["dragleave", "drop"].forEach((ev) => z.addEventListener(ev, (e) => { e.preventDefault(); z.classList.remove("over"); }));
  z.addEventListener("drop", (e) => addFiles([...e.dataTransfer.files]));
  return z;
}

function thumbURL(fid, n, w = 220) { return `/api/file/${fid}/page/${n}?w=${w}`; }

function fileRow(f, i, sortable) {
  const isImg = ["jpg", "jpeg", "png", "webp", "bmp", "gif", "tif", "tiff"].includes(f.ext);
  const row = h("div", { class: "file", draggable: sortable ? "true" : null },
    sortable ? h("span", { class: "handle", title: "Sürükleyerek sırala" }, "⋮⋮") : null,
    f.ext === "pdf" && f.pages ? h("img", { src: thumbURL(f.id, 0, 90), alt: "" }) : isImg ? h("img", { src: thumbURL(f.id, 0, 90), alt: "" }) : h("div", { class: "ph" }, f.ext.toUpperCase()),
    h("div", { class: "nm" }, S.tool.exact_files === 2 ? h("b", {}, i === 0 ? "1. (eski)  " : "2. (yeni)  ") : null, f.name,
      h("div", { class: "meta" }, fmtSize(f.size) + (f.pages ? ` · ${f.pages} sayfa` : ""))),
    h("button", { class: "x", title: "Kaldır", onclick: () => { S.files.splice(i, 1); S.org = null; S.placer = null; renderWork(); renderSide(); } }, "×"));
  if (sortable) {
    row.addEventListener("dragstart", (e) => { row.classList.add("drag"); e.dataTransfer.setData("text/plain", i); });
    row.addEventListener("dragend", () => row.classList.remove("drag"));
    row.addEventListener("dragover", (e) => e.preventDefault());
    row.addEventListener("drop", (e) => {
      e.preventDefault(); e.stopPropagation();
      const from = +e.dataTransfer.getData("text/plain"); if (Number.isNaN(from)) return;
      const [m] = S.files.splice(from, 1); S.files.splice(i, 0, m); renderWork();
    });
  }
  return row;
}

function renderWork() {
  const w = $("#work"); w.innerHTML = "";
  const t = S.tool;
  if (!S.files.length) { w.append(dropZone()); if (!t.optional_files) return; else return; }
  const ui = t.ui;
  if (ui === "organize") return renderOrganize(w);
  if (ui === "placer" || (ui === "forms" && S.opts.mode === "create")) return renderPlacer(w);
  const p = h("div", { class: "panel" });
  w.append(p);
  if (t.multi) p.append(h("div", { style: { display: "flex", gap: "8px", justifyContent: "space-between", alignItems: "center" } },
    h("b", {}, `${S.files.length} dosya`), h("button", { class: "btn sm", onclick: () => pickFiles(true, t.accept, addFiles) }, "+ Dosya ekle"),
  ));
  const list = h("div", { class: "files" });
  S.files.forEach((f, i) => list.append(fileRow(f, i, t.sortable)));
  p.append(list);
  if (t.sortable && S.files.length > 1) p.append(h("p", { class: "hint" }, "Sırayı değiştirmek için satırları sürükleyin."));
  if (t.page_pick || (t.preview && S.files[0].pages)) p.append(renderPagePick());
  if (ui === "forms") renderFormFill(p);
  if (t.camera) p.append(h("p", {}, h("button", { class: "btn sm", onclick: openCamera }, "📷 Kamerayla ekle")));
  const dz = dropZone(true); dz.style.marginTop = "14px"; dz.style.padding = "16px";
  if (t.multi) p.append(dz);
}

/* sayfa seçici (sayfaları kaldır / ayıkla / ayır önizleme) */
function renderPagePick() {
  const f = S.files[0]; const box = h("div", { class: "thumbs" });
  const pickable = !!S.tool.page_pick;
  for (let n = 0; n < f.pages; n++) {
    const th = h("div", { class: "thumb" + (S.sel.has(n) ? " sel" : "") }, h("img", { src: thumbURL(f.id, n), loading: "lazy", alt: "" }), h("div", { class: "n" }, n + 1));
    if (pickable) th.onclick = () => { S.sel.has(n) ? S.sel.delete(n) : S.sel.add(n); th.classList.toggle("sel"); S.opts.pages = toRanges([...S.sel]); const i = $(`[data-key="pages"]`); if (i) i.value = S.opts.pages; };
    box.append(th);
  }
  return h("div", {}, pickable ? h("p", { class: "hint", style: { marginTop: "14px" } }, "Sayfalara tıklayarak seçin.") : null, box);
}
function toRanges(arr) {
  const a = [...new Set(arr)].sort((x, y) => x - y).map((x) => x + 1); const out = [];
  for (let i = 0; i < a.length; i++) { let j = i; while (j + 1 < a.length && a[j + 1] === a[j] + 1) j++; out.push(i === j ? `${a[i]}` : `${a[i]}-${a[j]}`); i = j; }
  return out.join(", ");
}

/* ------------------------------------------------------------ PDF düzenle (sırala) */
const FCOL = ["#e5322d", "#2563eb", "#16a34a", "#f59e0b", "#9333ea", "#0f766e", "#db2777"];
function renderOrganize(w) {
  if (!S.org) S.org = S.files.flatMap((f, fi) => Array.from({ length: f.pages || 0 }, (_, p) => ({ f: fi, p, r: 0 })));
  const p = h("div", { class: "panel" });
  p.append(h("div", { class: "toolbar" },
    h("button", { class: "t", onclick: () => pickFiles(true, ["pdf"], addFiles) }, "+ PDF ekle"),
    h("button", { class: "t", onclick: () => { S.org.push({ blank: true }); renderWork(); } }, "+ Boş sayfa"),
    h("button", { class: "t", onclick: () => { S.org.forEach((x) => (x.r = ((x.r || 0) + 90) % 360)); renderWork(); } }, "⟳ Tümünü döndür"),
    h("button", { class: "t", onclick: () => { S.org.reverse(); renderWork(); } }, "⇅ Ters çevir"),
    h("button", { class: "t", onclick: () => { S.org = null; renderWork(); } }, "↺ Sıfırla"),
    h("span", { class: "hint" }, `${S.org.length} sayfa · sürükleyip bırakarak sıralayın`)));
  const box = h("div", { class: "thumbs" });
  S.org.forEach((it, i) => {
    const th = h("div", { class: "thumb" + (it.blank ? " blank" : ""), draggable: "true" },
      it.blank ? h("img", { alt: "" }) : h("img", { src: thumbURL(S.files[it.f].id, it.p), style: { transform: `rotate(${it.r || 0}deg) scale(${(it.r || 0) % 180 ? 0.75 : 1})` }, loading: "lazy", alt: "" }),
      !it.blank && S.files.length > 1 ? h("span", { class: "fl", style: { background: FCOL[it.f % FCOL.length] } }, it.f + 1) : null,
      h("div", { class: "n" }, it.blank ? `${i + 1} · boş` : `${i + 1}  (s.${it.p + 1})`),
      h("div", { class: "tools" },
        it.blank ? null : h("button", { title: "Döndür", onclick: (e) => { e.stopPropagation(); it.r = ((it.r || 0) + 90) % 360; renderWork(); } }, "⟳"),
        h("button", { title: "Kopyala", onclick: (e) => { e.stopPropagation(); S.org.splice(i + 1, 0, { ...it }); renderWork(); } }, "⧉"),
        h("button", { title: "Sil", onclick: (e) => { e.stopPropagation(); S.org.splice(i, 1); renderWork(); } }, "✕")));
    th.addEventListener("dragstart", (e) => e.dataTransfer.setData("text/plain", i));
    th.addEventListener("dragover", (e) => e.preventDefault());
    th.addEventListener("drop", (e) => { e.preventDefault(); const from = +e.dataTransfer.getData("text/plain"); const [m] = S.org.splice(from, 1); S.org.splice(i, 0, m); renderWork(); });
    box.append(th);
  });
  p.append(box);
  if (S.files.length > 1) p.append(h("p", { class: "hint" }, S.files.map((f, i) => `${i + 1}: ${f.name}`).join(" · ")));
  w.append(p);
}

/* ------------------------------------------------------------ form doldurma */
async function renderFormFill(p) {
  if (S.opts.mode !== "fill") { p.append(h("p", { class: "hint", style: { marginTop: "12px" } }, S.opts.mode === "detect" ? "Boşluk çizgileri (____), yatay çizgiler ve kutular form alanına çevrilecek." : "")); return; }
  const box = h("div", { class: "fieldlist", style: { marginTop: "14px" } }, h("p", { class: "hint" }, "Form alanları okunuyor…"));
  p.append(box);
  try {
    if (!S.fields) { S.fields = await api(`/api/file/${S.files[0].id}/fields`); S.opts.values = {}; S.fields.forEach((f) => (S.opts.values[f.name] = f.value)); }
    box.innerHTML = "";
    if (!S.fields.length) { box.append(h("p", { class: "err" }, "Bu PDF'te doldurulabilir alan yok. Sağdan 'Alanları otomatik algıla' ya da 'elle ekle' seçin.")); return; }
    for (const f of S.fields) {
      let inp;
      if (f.type === "CheckBox") inp = h("label", { class: "check" }, h("input", { type: "checkbox", checked: f.value && f.value !== "Off", onchange: (e) => (S.opts.values[f.name] = e.target.checked) }), f.name);
      else if (f.choices && f.choices.length) inp = h("select", { onchange: (e) => (S.opts.values[f.name] = e.target.value) }, ...f.choices.map((c) => h("option", { selected: c === f.value || null }, Array.isArray(c) ? c[1] : c)));
      else inp = h("input", { type: "text", value: f.value || "", oninput: (e) => (S.opts.values[f.name] = e.target.value) });
      box.append(h("div", { class: "opt" }, f.type === "CheckBox" ? null : h("label", { class: "l" }, `${f.name} (s.${f.page + 1})`), inp));
    }
  } catch (e) { box.innerHTML = ""; box.append(h("p", { class: "err" }, e.message)); }
}

/* ------------------------------------------------------------ yerleştirici (düzenle/imzala/karart/kırp/form) */
const TOOL_LABELS = { text: "T Metin", image: "🖼 Görsel", rect: "▭ Dikdörtgen", ellipse: "◯ Elips", line: "╱ Çizgi", highlight: "▌ Vurgula", whiteout: "▢ Beyaz örtü", ink: "✎ Kalem", signature: "✍ İmza", redact: "▇ Alan seç", crop: "⌗ Alan seç", field: "☐ Alan ekle" };
function renderPlacer(w) {
  const f = S.files[0];
  const tools = S.tool.ui === "forms" ? ["field"] : S.tool.tools;
  if (!S.placer) S.placer = { page: 0, items: [], mode: tools[0], color: S.tool.id === "sign" ? "#1a3a8a" : "#000000", size: 16, bold: false, width: 2, pending: null, fieldType: "text", allPages: false };
  const P = S.placer;
  if (!tools.includes(P.mode)) P.mode = tools[0];
  const tb = h("div", { class: "toolbar" });
  for (const t of tools) tb.append(h("button", { class: "t" + (P.mode === t ? " on" : ""), onclick: () => {
    P.mode = t;
    if (t === "image") pickFiles(false, ["png", "jpg", "jpeg", "webp", "gif"], async (fl) => { const up = await upload(fl); await setPending(up[0]); renderWork(); });
    else if (t === "signature") openSignature();
    else renderWork();
  } }, TOOL_LABELS[t]));
  if (["text", "rect", "ellipse", "line", "ink", "signature"].includes(P.mode) || P.mode === "highlight") tb.append(h("input", { type: "color", value: P.color, title: "Renk", oninput: (e) => (P.color = e.target.value) }));
  if (P.mode === "text") tb.append(h("input", { type: "number", value: P.size, min: 4, max: 200, title: "Yazı boyutu", oninput: (e) => (P.size = +e.target.value) }),
    h("label", { class: "check" }, h("input", { type: "checkbox", checked: P.bold || null, onchange: (e) => (P.bold = e.target.checked) }), "Kalın"));
  if (["rect", "ellipse", "line", "ink"].includes(P.mode)) tb.append(h("input", { type: "number", value: P.width, min: 0.5, max: 20, step: 0.5, title: "Çizgi kalınlığı", oninput: (e) => (P.width = +e.target.value) }));
  if (P.mode === "field") tb.append(h("select", { onchange: (e) => (P.fieldType = e.target.value) }, h("option", { value: "text" }, "Metin kutusu"), h("option", { value: "checkbox" }, "Onay kutusu"), h("option", { value: "combobox" }, "Açılır liste")));
  if (S.tool.id === "sign") tb.append(h("label", { class: "check" }, h("input", { type: "checkbox", checked: P.allPages || null, onchange: (e) => (P.allPages = e.target.checked) }), "Tüm sayfalara"));
  tb.append(h("button", { class: "t", title: "Geri al", onclick: () => { P.items.pop(); renderWork(); } }, "↶ Geri al"),
    h("button", { class: "t", onclick: () => { P.items = []; renderWork(); } }, "Temizle"));
  const hints = { text: "Metin eklemek için sayfaya tıklayın.", image: "Görseli seçtikten sonra sayfaya tıklayın.", signature: "İmzanızı oluşturun, sonra sayfada yerine tıklayın.", ink: "Fareyle sayfaya çizin.", crop: "Kırpılacak alanı fareyle sürükleyerek seçin.", redact: "Karartılacak alanları sürükleyerek seçin (aramayla birlikte kullanılabilir).", field: "Form alanı için sayfada dikdörtgen çizin." };
  const pw = f.sizes[P.page][0], ph = f.sizes[P.page][1];
  const wrap = h("div", { class: "stage-wrap" });
  const avail = Math.min(900, Math.max(320, ($("#work").clientWidth || 800) - 70));
  const scale = avail / pw;
  const stage = h("div", { class: "stage", style: { width: pw * scale + "px", height: ph * scale + "px" } },
    h("img", { class: "pg", src: thumbURL(f.id, P.page, Math.round(pw * scale * (window.devicePixelRatio || 1))), width: Math.round(pw * scale), height: Math.round(ph * scale), alt: "", draggable: "false" }));
  const svg = document.createElementNS("http://www.w3.org/2000/svg", "svg");
  svg.setAttribute("width", pw * scale); svg.setAttribute("height", ph * scale);
  Object.assign(svg.style, { position: "absolute", inset: 0, pointerEvents: "none" });
  stage.append(svg);
  wrap.append(stage);
  P.items.filter((it) => it.page === P.page || it.all_pages).forEach((it) => drawItem(stage, svg, it, scale));
  stageEvents(stage, svg, scale, pw, ph);
  const panel = h("div", { class: "panel" }, tb, h("p", { class: "hint" }, hints[P.mode] || "Sürükleyerek şekil çizin."), wrap,
    h("div", { class: "pager" },
      h("button", { class: "btn sm", disabled: P.page === 0 || null, onclick: () => { P.page--; renderWork(); } }, "‹ Önceki"),
      h("span", {}, `Sayfa ${P.page + 1} / ${f.pages}`),
      h("button", { class: "btn sm", disabled: P.page >= f.pages - 1 || null, onclick: () => { P.page++; renderWork(); } }, "Sonraki ›")),
    h("p", { class: "hint" }, `${P.items.length} öğe eklendi.`));
  w.append(panel);
}

async function setPending(up) {
  const img = new Image(); img.src = thumbURL(up.id, 0, 400);
  await img.decode().catch(() => {});
  S.placer.pending = { id: up.id, aspect: img.naturalHeight && img.naturalWidth ? img.naturalHeight / img.naturalWidth : 0.4 };
  toast("Şimdi sayfada yerleştirmek istediğiniz yere tıklayın.");
}

function drawItem(stage, svg, it, sc) {
  const P = S.placer;
  if (it.type === "ink" || it.type === "line") {
    const el = document.createElementNS("http://www.w3.org/2000/svg", it.type === "ink" ? "polyline" : "line");
    if (it.type === "ink") el.setAttribute("points", it.points.map(([x, y]) => `${x * sc},${y * sc}`).join(" "));
    else { el.setAttribute("x1", it.x * sc); el.setAttribute("y1", it.y * sc); el.setAttribute("x2", it.x2 * sc); el.setAttribute("y2", it.y2 * sc); }
    el.setAttribute("stroke", it.color); el.setAttribute("stroke-width", it.width * sc); el.setAttribute("fill", "none"); el.setAttribute("stroke-linecap", "round"); el.setAttribute("stroke-linejoin", "round");
    svg.append(el); return;
  }
  const d = h("div", { class: "item " + it.type, style: { left: it.x * sc + "px", top: it.y * sc + "px", width: it.w * sc + "px", height: it.h * sc + "px" } });
  if (it.type === "text") {
    const ta = h("textarea", { style: { fontSize: it.size * sc + "px", color: it.color, fontWeight: it.bold ? "700" : "400" } });
    ta.value = it.text;
    ta.oninput = () => { it.text = ta.value; const lines = ta.value.split("\n").length; it.h = lines * it.size * 1.3; d.style.height = it.h * sc + "px"; };
    ta.onmousedown = (e) => e.stopPropagation();
    d.append(ta);
    if (it._new) { delete it._new; setTimeout(() => { ta.focus(); ta.select(); }, 30); }
  } else if (it.type === "image" || it.type === "signature") d.append(h("img", { src: thumbURL(it.image_id, 0, 400), alt: "" }));
  else if (it.type === "rect") Object.assign(d.style, { border: `${Math.max(1, it.width * sc)}px solid ${it.color}` });
  else if (it.type === "ellipse") Object.assign(d.style, { border: `${Math.max(1, it.width * sc)}px solid ${it.color}`, borderRadius: "50%" });
  else if (it.type === "highlight") Object.assign(d.style, { background: "rgba(255,235,59,.45)" });
  else if (it.type === "whiteout") Object.assign(d.style, { background: "#fff", outline: "1px dashed #999" });
  else if (it.type === "field") d.append(h("span", { class: "hint", style: { fontSize: "11px" } }, it.field_type === "checkbox" ? "☐" : it.field_type === "combobox" ? "▾ liste" : "metin"));
  d.append(h("button", { class: "del", title: "Sil", onmousedown: (e) => e.stopPropagation(), onclick: () => { P.items.splice(P.items.indexOf(it), 1); renderWork(); } }, "×"));
  const rs = h("div", { class: "rs" }); d.append(rs);
  // taşı
  d.addEventListener("pointerdown", (e) => {
    if (e.target === rs || e.target.classList.contains("del")) return;
    e.stopPropagation(); e.preventDefault(); const sx = e.clientX, sy = e.clientY, ox = it.x, oy = it.y;
    const mv = (ev) => { it.x = ox + (ev.clientX - sx) / sc; it.y = oy + (ev.clientY - sy) / sc; d.style.left = it.x * sc + "px"; d.style.top = it.y * sc + "px"; };
    const up = () => { removeEventListener("pointermove", mv); removeEventListener("pointerup", up); };
    addEventListener("pointermove", mv); addEventListener("pointerup", up);
  });
  // boyutlandır
  rs.addEventListener("pointerdown", (e) => {
    e.stopPropagation(); e.preventDefault(); const sx = e.clientX, sy = e.clientY, ow = it.w, oh = it.h; const keep = it.type === "image" || it.type === "signature";
    const mv = (ev) => { it.w = Math.max(8, ow + (ev.clientX - sx) / sc); it.h = keep ? it.w * (oh / ow) : Math.max(6, oh + (ev.clientY - sy) / sc);
      if (it.type === "text") { it.size = Math.max(4, it.h / Math.max(1, it.text.split("\n").length) / 1.3); $("textarea", d).style.fontSize = it.size * sc + "px"; }
      d.style.width = it.w * sc + "px"; d.style.height = it.h * sc + "px"; };
    const up = () => { removeEventListener("pointermove", mv); removeEventListener("pointerup", up); };
    addEventListener("pointermove", mv); addEventListener("pointerup", up);
  });
  stage.append(d);
}

function stageEvents(stage, svg, sc, pw, ph) {
  const P = S.placer;
  const pos = (e) => { const r = stage.getBoundingClientRect(); return [Math.min(pw, Math.max(0, (e.clientX - r.left) / sc)), Math.min(ph, Math.max(0, (e.clientY - r.top) / sc))]; };
  stage.addEventListener("pointerdown", (e) => {
    if (e.target.closest(".item")) return;
    e.preventDefault();
    const [x, y] = pos(e); const m = P.mode;
    if (m === "text") { P.items.push({ type: "text", page: P.page, x, y, w: 180, h: P.size * 1.3, text: "Metin", size: P.size, color: P.color, bold: P.bold, _new: true }); return renderWork(); }
    if (m === "image" || m === "signature") {
      if (!P.pending) { toast(m === "signature" ? "Önce imzanızı oluşturun." : "Önce bir görsel seçin."); return m === "signature" ? openSignature() : null; }
      const wpt = m === "signature" ? 150 : 180;
      P.items.push({ type: m, page: P.page, x, y, w: wpt, h: wpt * P.pending.aspect, image_id: P.pending.id, all_pages: m === "signature" && P.allPages });
      return renderWork();
    }
    if (m === "ink") {
      const it = { type: "ink", page: P.page, points: [[x, y]], color: P.color, width: P.width };
      const pl = document.createElementNS("http://www.w3.org/2000/svg", "polyline");
      pl.setAttribute("stroke", P.color); pl.setAttribute("stroke-width", P.width * sc); pl.setAttribute("fill", "none"); pl.setAttribute("stroke-linecap", "round"); svg.append(pl);
      const mv = (ev) => { it.points.push(pos(ev)); pl.setAttribute("points", it.points.map(([a, b]) => `${a * sc},${b * sc}`).join(" ")); };
      const up = () => { removeEventListener("pointermove", mv); removeEventListener("pointerup", up); if (it.points.length > 1) P.items.push(it); renderWork(); };
      addEventListener("pointermove", mv); addEventListener("pointerup", up); return;
    }
    // sürükleyerek dikdörtgen / çizgi
    const ghost = h("div", { class: "item " + (m === "crop" ? "crop" : m === "redact" ? "redact" : ""), style: { left: x * sc + "px", top: y * sc + "px", width: 0, height: 0, borderColor: "var(--accent)" } });
    stage.append(ghost);
    let x2 = x, y2 = y;
    const mv = (ev) => { [x2, y2] = pos(ev); Object.assign(ghost.style, { left: Math.min(x, x2) * sc + "px", top: Math.min(y, y2) * sc + "px", width: Math.abs(x2 - x) * sc + "px", height: Math.abs(y2 - y) * sc + "px" }); };
    const up = () => {
      removeEventListener("pointermove", mv); removeEventListener("pointerup", up); ghost.remove();
      if (m === "line") { if (Math.hypot(x2 - x, y2 - y) > 3) P.items.push({ type: "line", page: P.page, x, y, x2, y2, color: P.color, width: P.width }); return renderWork(); }
      const r = { x: Math.min(x, x2), y: Math.min(y, y2), w: Math.abs(x2 - x), h: Math.abs(y2 - y) };
      if (r.w < 4 || r.h < 4) { if (m === "field") Object.assign(r, { w: P.fieldType === "checkbox" ? 14 : 160, h: 14 + (P.fieldType === "checkbox" ? 0 : 6) }); else return; }
      if (m === "crop") P.items = P.items.filter((i) => i.type !== "crop");
      P.items.push({ type: m, page: P.page, ...r, color: P.color, width: P.width, field_type: P.fieldType });
      renderWork();
    };
    addEventListener("pointermove", mv); addEventListener("pointerup", up);
  });
}

/* imza oluşturucu */
function openSignature() {
  let tab = "draw";
  const body = h("div", {});
  const render = () => {
    body.innerHTML = "";
    body.append(h("h3", { style: { margin: "0 0 4px" } }, "İmzanızı oluşturun"),
      h("div", { class: "tabs" }, ...[["draw", "Çiz"], ["type", "Yaz"], ["upload", "Görsel yükle"]].map(([k, l]) => h("button", { class: "chip" + (tab === k ? " on" : ""), onclick: () => { tab = k; render(); } }, l))));
    const color = h("input", { type: "color", value: S.placer.color });
    if (tab === "draw") {
      const c = h("canvas", { class: "sigpad", width: 1200, height: 400 }); const ctx = c.getContext("2d");
      ctx.lineCap = "round"; ctx.lineJoin = "round"; ctx.lineWidth = 7; let drawing = false, any = false;
      const p = (e) => { const r = c.getBoundingClientRect(); return [(e.clientX - r.left) * c.width / r.width, (e.clientY - r.top) * c.height / r.height]; };
      c.onpointerdown = (e) => { drawing = true; any = true; ctx.strokeStyle = color.value; ctx.beginPath(); ctx.moveTo(...p(e)); c.setPointerCapture(e.pointerId); };
      c.onpointermove = (e) => { if (drawing) { ctx.lineTo(...p(e)); ctx.stroke(); } };
      c.onpointerup = () => (drawing = false);
      body.append(c, h("div", { class: "toolbar", style: { marginTop: "10px" } }, "Renk:", color,
        h("button", { class: "btn sm", onclick: () => { ctx.clearRect(0, 0, c.width, c.height); any = false; } }, "Temizle"),
        h("button", { class: "btn primary", onclick: () => any ? useSig(trimCanvas(c)) : toast("Önce imza çizin.") }, "Kullan")));
    } else if (tab === "type") {
      const name = h("input", { type: "text", placeholder: "Adınız Soyadınız", style: { width: "100%", padding: "10px", fontSize: "18px" } });
      const fonts = ["'Brush Script MT', cursive", "'Segoe Script', cursive", "'Lucida Handwriting', cursive", "'Snell Roundhand', cursive", "cursive", "Georgia, serif"];
      const list = h("div", { class: "fieldlist", style: { marginTop: "10px" } });
      const draw = () => { list.innerHTML = ""; for (const fnt of fonts) list.append(h("button", { class: "btn", style: { fontFamily: fnt, fontSize: "30px", color: color.value, justifyContent: "flex-start" }, onclick: () => {
        if (!name.value.trim()) return toast("Adınızı yazın.");
        const c = document.createElement("canvas"); c.width = 1200; c.height = 300; const x = c.getContext("2d"); x.fillStyle = color.value; x.font = `140px ${fnt}`; x.textBaseline = "middle"; x.fillText(name.value, 20, 150); useSig(trimCanvas(c));
      } }, name.value || "Adınız Soyadınız")); };
      name.oninput = draw; color.oninput = draw; draw();
      body.append(name, h("div", { class: "toolbar", style: { marginTop: "8px" } }, "Renk:", color), list);
    } else {
      body.append(h("p", {}, "PNG (şeffaf arka planlı) ya da JPG imza görseli seçin."), h("button", { class: "btn primary", onclick: () => pickFiles(false, ["png", "jpg", "jpeg", "webp"], async (fl) => { const up = await upload(fl); await setPending(up[0]); $("#modal").hidden = true; renderWork(); }) }, "Görsel seç"));
    }
  };
  render(); modal(body);
}
function trimCanvas(c) {
  const ctx = c.getContext("2d"); const d = ctx.getImageData(0, 0, c.width, c.height).data;
  let x0 = c.width, y0 = c.height, x1 = 0, y1 = 0;
  for (let y = 0; y < c.height; y += 2) for (let x = 0; x < c.width; x += 2) if (d[(y * c.width + x) * 4 + 3] > 10) { x0 = Math.min(x0, x); y0 = Math.min(y0, y); x1 = Math.max(x1, x); y1 = Math.max(y1, y); }
  if (x1 <= x0) return c.toDataURL("image/png");
  const pad = 10; const o = document.createElement("canvas"); o.width = x1 - x0 + pad * 2; o.height = y1 - y0 + pad * 2;
  o.getContext("2d").drawImage(c, x0 - pad, y0 - pad, o.width, o.height, 0, 0, o.width, o.height);
  return o.toDataURL("image/png");
}
async function useSig(dataurl) {
  const up = await upload([], ["imza.png|" + dataurl]);
  await setPending(up[0]); S.placer.mode = "signature"; $("#modal").hidden = true; renderWork();
}

/* kamera (PDF'e tara) */
async function openCamera() {
  const shots = [];
  const video = h("video", { class: "cam", autoplay: true, playsinline: true });
  const count = h("span", { class: "hint" }, "0 sayfa");
  const body = h("div", {}, h("h3", { style: { margin: "0 0 10px" } }, "Kamerayla tara"), video,
    h("div", { class: "toolbar", style: { marginTop: "10px" } },
      h("button", { class: "btn primary", onclick: () => { const c = document.createElement("canvas"); c.width = video.videoWidth; c.height = video.videoHeight; c.getContext("2d").drawImage(video, 0, 0); shots.push(c.toDataURL("image/jpeg", 0.92)); count.textContent = shots.length + " sayfa"; toast("Sayfa eklendi"); } }, "📸 Çek"),
      count,
      h("button", { class: "btn", onclick: async () => { stop(); $("#modal").hidden = true; if (shots.length) { const up = await upload([], shots.map((s, i) => `tarama_${i + 1}.jpg|${s}`)); addUploaded(up); renderWork(); renderSide(); } } }, "Bitti")));
  let stream = null; const stop = () => stream && stream.getTracks().forEach((t) => t.stop());
  modal(body);
  $("#modal .modal-x").addEventListener("click", stop, { once: true });
  try { stream = await navigator.mediaDevices.getUserMedia({ video: { facingMode: "environment", width: { ideal: 1920 } } }); video.srcObject = stream; }
  catch (e) { body.append(h("p", { class: "err" }, "Kamera açılamadı: " + e.message + ". Telefon fotoğraflarını dosya olarak da ekleyebilirsiniz.")); }
}

/* ------------------------------------------------------------ seçenekler paneli */
function visible(o) { if (!o.show_if) return true; return Object.entries(o.show_if).every(([k, vals]) => vals.map(String).includes(String(S.opts[k]))); }
function renderSide() {
  const side = $("#side"); side.innerHTML = "";
  const t = S.tool;
  const p = h("div", { class: "panel" }, h("h3", { style: { margin: "0 0 12px" } }, "Seçenekler"));
  const box = h("div", { class: "opts" });
  for (const o of t.opts) {
    if (!visible(o)) continue;
    box.append(optInput(o));
  }
  if (t.wm_image && S.opts.kind === "image") {
    box.append(h("div", { class: "opt" }, h("label", { class: "l" }, "Filigran görseli"),
      h("button", { class: "btn sm", onclick: () => pickFiles(false, ["png", "jpg", "jpeg", "webp"], async (fl) => { const up = await upload(fl); S.extra.image = up[0].id; S.extra._imgname = up[0].name; renderSide(); }) }, S.extra.image ? "✓ " + S.extra._imgname : "Görsel seç")));
  }
  if (!t.opts.length && !t.wm_image) box.append(h("p", { class: "hint" }, t.ui === "placer" ? "Soldaki sayfada araçları kullanın." : "Bu araç için ek ayar gerekmiyor."));
  if (t.needs === "office") box.append(h("p", { class: "hint" }, "Microsoft Office (Windows) ya da LibreOffice kullanılır."));
  p.append(box);
  const can = S.files.length > 0 || t.optional_files;
  const runBtn = h("button", { class: "btn primary big", disabled: !can || null, onclick: runTool }, t.title.replace(/^PDF'i |^PDF /, "") + " →");
  if (t.exact_files && S.files.length !== t.exact_files) { runBtn.disabled = true; p.append(h("p", { class: "hint" }, `${t.exact_files} dosya seçin.`)); }
  side.append(p, runBtn);
}
function optInput(o) {
  const set = (v, rerender) => { S.opts[o.key] = v; if (rerender) { renderSide(); if (S.tool.ui === "forms" && o.key === "mode") { S.placer = null; renderWork(); } } };
  const hasDeps = S.tool.opts.some((x) => x.show_if && o.key in x.show_if) || (S.tool.wm_image && o.key === "kind") || (S.tool.ui === "forms");
  const wrap = h("div", { class: "opt" });
  const label = h("label", { class: "l" }, o.label);
  const v = S.opts[o.key];
  if (o.type === "checkbox") { wrap.append(h("label", { class: "check" }, h("input", { type: "checkbox", checked: !!v || null, onchange: (e) => set(e.target.checked, hasDeps) }), o.label)); }
  else if (o.type === "select") wrap.append(label, h("select", { "data-key": o.key, onchange: (e) => set(e.target.value, hasDeps) }, ...o.choices.map(([k, l]) => h("option", { value: k, selected: String(k) === String(v) || null }, l))));
  else if (o.type === "radio") wrap.append(label, h("div", { class: "radio" }, ...o.choices.map(([k, l]) => h("label", {}, h("input", { type: "radio", name: o.key, value: k, checked: String(k) === String(v) || null, onchange: () => set(k, hasDeps) }), l))));
  else if (o.type === "position") wrap.append(label, h("div", { class: "posgrid" }, ...o.choices.map(([k, l]) => h("button", { class: String(k) === String(v) ? "on" : "", title: l, onclick: () => set(k, true) }, ""))));
  else if (o.type === "range") { const out = h("span", { class: "hint" }, ` ${v}`); wrap.append(h("label", { class: "l" }, o.label, out), h("input", { type: "range", min: o.min || 0, max: o.max || 100, value: v, style: { width: "100%" }, oninput: (e) => { set(+e.target.value); out.textContent = " " + e.target.value; } })); }
  else if (o.type === "textarea") { const ta = h("textarea", { "data-key": o.key, oninput: (e) => { set(e.target.value); } }); ta.value = v || ""; wrap.append(label, ta); }
  else if (o.type === "color") wrap.append(label, h("input", { type: "color", value: v, oninput: (e) => set(e.target.value) }));
  else wrap.append(label, h("input", { type: o.type === "number" ? "number" : o.type === "password" ? "password" : "text", "data-key": o.key, value: v ?? "", placeholder: o.placeholder || null, min: o.min ?? null, max: o.max ?? null, step: o.step ?? null,
    oninput: (e) => { set(e.target.value); if (o.key === "pages" && S.tool.page_pick) syncSel(e.target.value); } }));
  if (o.help) wrap.append(h("div", { class: "help" }, o.help));
  return wrap;
}
function syncSel(txt) {
  const f = S.files[0]; if (!f) return; S.sel.clear();
  for (const part of txt.split(/[,;\s]+/)) { const m = part.match(/^(\d*)-(\d*)$/); if (m) { const a = +(m[1] || 1), b = +(m[2] || f.pages); for (let i = a; i <= b; i++) S.sel.add(i - 1); } else if (/^\d+$/.test(part)) S.sel.add(+part - 1); }
  $$(".thumbs .thumb").forEach((t, i) => t.classList.toggle("sel", S.sel.has(i)));
}

/* ------------------------------------------------------------ çalıştır */
async function runTool() {
  const t = S.tool;
  const opts = { ...S.opts };
  const extra = {};
  if (S.extra.image) extra.image = S.extra.image;
  if (t.ui === "organize") opts.layout = S.org;
  if (S.placer) {
    const items = S.placer.items.map(({ _new, ...it }) => it);
    for (const it of items) if (it.image_id) extra[it.image_id] = it.image_id;
    if (t.id === "crop") { const c = items.find((i) => i.type === "crop"); if (c) { opts.box = { x0: c.x, y0: c.y, x1: c.x + c.w, y1: c.y + c.h }; if (opts.which === "all") opts.which = "all"; } }
    else opts.items = items;
  }
  const w = $("#work"), side = $("#side");
  const prev = [...w.childNodes]; const prevSide = [...side.childNodes];
  w.innerHTML = ""; side.innerHTML = "";
  const started = Date.now();
  const timer = h("span", { class: "hint" }, "");
  const iv = setInterval(() => (timer.textContent = `${Math.round((Date.now() - started) / 1000)} sn`), 1000);
  w.append(h("div", { class: "panel busy" }, h("div", { class: "spin" }), h("b", {}, "İşleniyor…"), timer,
    h("p", { class: "hint" }, t.cat === "media" || t.id === "ocr" || t.cat === "ai" ? "Büyük dosyalarda birkaç dakika sürebilir." : "")));
  try {
    const res = await api(`/api/run/${t.id}`, { file_ids: S.files.map((f) => f.id), opts, extra });
    clearInterval(iv); renderResult(res);
  } catch (e) {
    clearInterval(iv);
    w.innerHTML = ""; prev.forEach((n) => w.append(n)); side.innerHTML = ""; prevSide.forEach((n) => side.append(n));
    w.prepend(h("div", { class: "err", style: { marginBottom: "12px" } }, "⚠ " + e.message));
  }
}

function renderResult(res) {
  const t = S.tool;
  const w = $("#work"); w.innerHTML = "";
  const files = res.files || [];
  const zip = files.find((f) => f.ext === "zip");
  const list = h("div", { class: "outfiles" });
  for (const f of files) {
    const viewable = ["pdf", "html", "txt", "md", "png", "jpg"].includes(f.ext);
    list.append(h("div", { class: "file" }, h("div", { class: "ph" }, f.ext.toUpperCase()),
      h("div", { class: "nm" }, f.name, h("div", { class: "meta" }, fmtSize(f.size))),
      viewable ? h("a", { class: "btn sm", href: `/api/download/${f.id}?inline=1`, target: "_blank" }, "Aç") : null,
      h("button", { class: "btn sm", onclick: async () => { try { const r = await api(`/api/save/${f.id}`, { reveal: true }); toast("Kaydedildi: " + r.path, 4500); } catch (e) { toast(e.message); } } }, "Klasöre kaydet"),
      h("a", { class: "btn sm primary", href: `/api/download/${f.id}` }, "İndir")));
  }
  const main = files[0];
  const panel = h("div", { class: "panel result" },
    h("div", { class: "ok" }, "✅"), h("h2", { style: { margin: "4px 0" } }, "Tamamlandı"),
    h("p", { class: "hint" }, `${res.seconds} saniyede işlendi · ${files.length} dosya`),
    main ? h("a", { class: "btn primary big", style: { maxWidth: "420px" }, href: `/api/download/${(zip || main).id}` }, zip ? "Tümünü indir (ZIP)" : `${main.name} indir`) : null,
    res.note ? h("div", { class: "note" }, res.note) : null,
    res.text ? h("div", {}, h("div", { class: "textout" }, res.text), h("button", { class: "btn sm", onclick: () => navigator.clipboard.writeText(res.text).then(() => toast("Kopyalandı")) }, "Metni kopyala")) : null,
    res.html ? h("iframe", { class: "report", srcdoc: res.html, sandbox: "" }) : null,
    list);
  // iş akışı: çıktıyı başka araçla işle
  const pdfs = files.filter((f) => f.ext !== "zip" && f.ext !== "html");
  if (pdfs.length) {
    const ext = pdfs[0].ext;
    const nexts = CAT.tools.filter((x) => x.id !== t.id && accepts(x, ext) && x.cat !== "media");
    if (nexts.length) panel.append(h("div", { class: "next" }, h("b", {}, "Sonucu başka bir araçla işle:"),
      h("div", { class: "chips" }, ...nexts.map((x) => h("button", { class: "chip", onclick: () => { CARRY = pdfs.filter((f) => accepts(x, f.ext)); go("#/arac/" + x.id); } }, x.icon + " " + x.title)))));
  }
  panel.append(h("p", { style: { marginTop: "18px" } }, h("button", { class: "btn", onclick: () => openTool(t.id) }, "↺ Yeni işlem"), " ",
    h("button", { class: "btn", onclick: () => api("/api/open-folder", {}) }, "📂 Kayıt klasörünü aç")));
  w.append(panel);
  $("#side").innerHTML = "";
  $("#side").append(h("div", { class: "panel" }, h("p", { class: "hint", style: { margin: 0 } }, "İpucu: 'Klasöre kaydet' dosyayı Ayarlar'da seçtiğiniz klasöre kopyalar ve klasörü açar.")));
}

/* ------------------------------------------------------------ ayarlar */
$("#btn-settings").onclick = async () => {
  const body = h("div", {}, h("h3", { style: { marginTop: 0 } }, "Ayarlar"), h("p", { class: "hint" }, "Yükleniyor…"));
  modal(body);
  let st;
  try { st = await api("/api/status"); } catch (e) { body.append(h("p", { class: "err" }, e.message)); return; }
  const row = (k, ok, extra) => h("div", { class: "status-row" }, h("span", {}, k), h("span", { class: ok ? "yes" : "no" }, ok ? "✓ var" : extra || "yok"));
  const key = h("input", { type: "password", placeholder: st.claude_anahtari ? "•••••••• (kayıtlı)" : "sk-ant-…", style: { width: "100%", padding: "8px" } });
  const dir = h("input", { type: "text", value: st.cikti_klasoru, style: { width: "100%", padding: "8px" } });
  const theme = h("select", { onchange: (e) => { store.set("tema", e.target.value); applyTheme(); } }, ...[["system", "Sistem"], ["light", "Açık"], ["dark", "Koyu"]].map(([k, l]) => h("option", { value: k, selected: store.get("tema", "system") === k || null }, l)));
  body.innerHTML = "";
  body.append(h("h3", { style: { marginTop: 0 } }, "Ayarlar"),
    h("h4", {}, "Bileşenler"),
    row("Video → ses (ffmpeg)", st.ffmpeg), row("Microsoft Office", st.ms_office, "yok (Windows'ta Office ile dönüştürülür)"),
    row("LibreOffice", st.libreoffice, "yok (isteğe bağlı)"), row("Chrome / Edge (HTML→PDF)", st.tarayici),
    row("Ghostscript (tam PDF/A)", st.ghostscript, "yok (isteğe bağlı)"),
    row("OCR dilleri", st.ocr_dilleri.length > 0, "ilk kullanımda iner"), row("Claude API anahtarı", st.claude_anahtari, "yok (özet/çeviri için isteğe bağlı)"),
    h("p", { class: "hint" }, `Sistem: ${st.isletim_sistemi}`),
    h("h4", {}, "Kayıt klasörü"), dir,
    h("h4", {}, "Claude API anahtarı"), h("p", { class: "hint", style: { marginTop: 0 } }, "Özetleyici ve çeviri için Claude kullanılır. Anahtar yalnızca bu bilgisayarda saklanır: " + st.ayar_klasoru), key,
    h("h4", {}, "Tema"), theme,
    h("p", { style: { marginTop: "16px", display: "flex", gap: "8px" } },
      h("button", { class: "btn primary", onclick: async () => {
        const d = { output_dir: dir.value.trim() }; if (key.value.trim()) d.anthropic_api_key = key.value.trim();
        try { await api("/api/settings", d); toast("Kaydedildi"); $("#modal").hidden = true; } catch (e) { toast(e.message); }
      } }, "Kaydet"),
      h("button", { class: "btn", onclick: () => api("/api/open-folder", {}) }, "📂 Kayıt klasörünü aç")));
};

init().catch((e) => { $("#view").innerHTML = ""; $("#view").append(h("p", { class: "err" }, "Uygulama başlatılamadı: " + e.message)); });
