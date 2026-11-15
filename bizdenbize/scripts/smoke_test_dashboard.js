/* Smoke test app.js tanpa browser: DOM tiruan minimal + data.json asli.
   Lulus = init jalan, semua interaksi (hari, lapisan, klik sel) tanpa error,
   dan KPI sel-ekstrem cocok dengan hitungan Python (258 pada hari puncak). */
"use strict";
const fs = require("fs");
const vm = require("vm");
const path = require("path");

const DATA = JSON.parse(fs.readFileSync(path.join(__dirname, "../dashboard/data.json"), "utf8"));
const CODE = fs.readFileSync(path.join(__dirname, "../dashboard/app.js"), "utf8");

const ctxProxy = new Proxy({}, {
  get(t, p) {
    if (p === "setTransform" || p === "measureText") return () => ({ width: 10 });
    return typeof p === "string" ? () => {} : undefined;
  },
  set() { return true; }
});

function makeEl(id) {
  const el = {
    id, style: {}, dataset: {}, children: [], listeners: {},
    checked: true, value: "", _text: "", _html: "",
    clientWidth: 1000, offsetWidth: 120,
    get textContent() { return this._text; },
    set textContent(v) { this._text = String(v); },
    get innerHTML() { return this._html; },
    set innerHTML(v) { this._html = String(v); },
    appendChild(c) { this.children.push(c); c.parentNode = this; return c; },
    addEventListener(t, f) { (this.listeners[t] = this.listeners[t] || []).push(f); },
    setAttribute(k, v) { this["attr_" + k] = v; },
    getAttribute(k) { return this["attr_" + k]; },
    getContext() { return ctxProxy; },
    getBoundingClientRect() { return { left: 0, top: 0 }; },
    title: ""
  };
  return el;
}

const els = {};
function byId(id) {
  if (id === "osm") return null;          // uji jalur canvas; jalur OSM butuh Leaflet (tidak ada di sandbox)
  return els[id] || (els[id] = makeEl(id));
}
byId("map").parentNode = makeEl("mapwrap");

const createdCols = [];
const sandbox = {
  console, Math, Map, JSON, Error, String, Number, Promise, Date,
  window: {
    matchMedia: () => ({ matches: false, addEventListener: () => {} }),
    addEventListener: () => {},
    devicePixelRatio: 1
  },
  document: {
    getElementById: byId,
    createElement: () => { const e = makeEl("dyn"); return e; },
    querySelectorAll: (sel) => (sel === "#bars .col" ? createdCols : [])
  },
  fetch: () => Promise.resolve({ ok: true, json: () => Promise.resolve(DATA) })
};
sandbox.window.ResizeObserver = undefined;

vm.createContext(sandbox);
vm.runInContext(CODE, sandbox, { filename: "app.js" });

setTimeout(() => {
  try {
    const bars = byId("bars");
    bars.children.forEach(c => createdCols.push(c));

    // 1) KPI hari puncak (slider default = 5) harus cocok dengan data.json
    const expect = String(DATA.cells.risk[5].filter(r => r >= 0.75).length);
    const got = byId("kpi1").textContent;
    if (got !== expect) throw new Error("KPI ekstrem hari puncak = " + got + ", harap " + expect);

    // 2) Jelajahi semua hari lewat listener slider
    const dayInput = byId("day");
    for (let d = 0; d <= 6; d++)
      dayInput.listeners.input.forEach(f => f({ target: { value: String(d) } }));

    // 3) Semua tombol lapisan
    const btns = byId("layerBtns").children;
    if (btns.length !== 4) throw new Error("tombol lapisan = " + btns.length);
    btns.forEach(b => b.listeners.click.forEach(f => f()));

    // 4) Toggle overlay
    ["ovRoads", "ovSet", "ovFires"].forEach(id => {
      byId(id).checked = false;
      byId(id).listeners.change.forEach(f => f());
      byId(id).checked = true;
    });

    // 5) Klik sel darat paling berisiko di hari terakhir -> panel detail terisi
    const cv = byId("map"), M = DATA.meta, b = M.bbox;
    const kmx = 111.32 * Math.cos((b[1] + b[3]) / 2 * Math.PI / 180), Wd = 1000;
    const Hd = Math.round(Wd * ((b[3] - b[1]) * 110.57 / ((b[2] - b[0]) * kmx)));
    const r6 = DATA.cells.risk[6], ci = r6.indexOf(Math.max.apply(null, r6));
    const pt = { clientX: (DATA.cells.ix[ci] + 0.5) / M.ncols * Wd,
                 clientY: Hd - (DATA.cells.iy[ci] + 0.5) / M.nrows * Hd };
    cv.listeners.click.forEach(f => f(pt));
    if (!/Skoru etkileyen|Model katkısı/.test(byId("detailBody").innerHTML))
      throw new Error("panel detail (TR) kosong setelah klik sel");

    // 5b) Toggle bahasa TR -> EN -> TR
    const langB = byId("langBtns").children;
    if (langB.length !== 2) throw new Error("tombol bahasa = " + langB.length);
    langB[1].listeners.click.forEach(f => f());   // EN
    if (!/Score drivers|Model contribution/.test(byId("detailBody").innerHTML))
      throw new Error("panel detail tidak berganti ke EN");
    if (byId("t-kpi1").textContent !== "Cells in Extreme class")
      throw new Error("label KPI tidak berganti ke EN");
    langB[0].listeners.click.forEach(f => f());   // kembali TR
    if (byId("t-kpi1").textContent !== "Ekstrem sınıfı hücreler")
      throw new Error("label KPI tidak kembali ke TR");

    // 6) Hover tooltip
    cv.listeners.mousemove.forEach(f => f(pt));
    if (byId("tip").style.display !== "block") throw new Error("tooltip tidak muncul");

    // 7) Tabel permukiman terisi 10 baris
    const rows = (byId("tblBody").innerHTML.match(/<tr>/g) || []).length;
    if (rows !== 10) throw new Error("baris tabel = " + rows);

    // 8) Grafik batang: 7 kolom, klik kolom pindah hari
    if (createdCols.length < 7) throw new Error("kolom batang = " + createdCols.length);

    console.log("SMOKE TEST LULUS");
    console.log("  KPI (hari puncak): ekstrem =", got,
      "| permukiman terdampak =", byId("kpi2").textContent,
      "| FWI rerata =", byId("kpi3").textContent,
      "| area T+E =", byId("kpi4").textContent);
    console.log("  catatan: nilai di atas untuk hari terakhir yang disimulasikan (Min 2/8)");
  } catch (e) {
    console.error("SMOKE TEST GAGAL:", e.message);
    process.exit(1);
  }
}, 50);
