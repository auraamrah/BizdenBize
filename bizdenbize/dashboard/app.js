/* FireBridge dashboard — Tahap/Aşama 1–4, whole Türkiye (pilot data.pilot.json still loads) — TR/EN bilingual */
(function () {
  "use strict";

  // ---------------------------------------------------------------- i18n --
  var I18N = {
    tr: {
      title: "FireBridge — Orman Yangını Risk Panosu",
      badge: "MODEL · 2021 GERİYE DÖNÜK TAHMİN",
      sub: "#BizdenBize · COP31 Climate Tech Creathon · Tüm Türkiye · " +
           "Aşama 1–4: 5 km grid, yangın hava koşulları (FWI), insan erişimi " +
           "(yollar & yerleşimler) ve yangın geçmişi",
      kpi1: "Ekstrem sınıfı hücreler", kpi2: "Ekstrem bölgeye yakın yerleşimler (≤5 km)",
      kpi3: "Bölge ortalama FWI", kpi4: "Yüksek + Ekstrem alan",
      kpi4s: "tüm kara hücrelerine oranı",
      same: "dünle aynı", vsYest: "düne göre", none: "yok", max: "maksimum",
      roads: "Yollar", set: "Yerleşimler", fires: "Yangın geçmişi", day: "Gün",
      dtitle: "Hücre detayı",
      dhint: "Aşama 2 özelliklerini görmek için haritada bir hücreye tıklayın: " +
             "FWI, yola & yerleşime uzaklık, bitki örtüsü ve skoru etkileyen faktörler.",
      btitle: "Günlere göre risk sınıfı dağılımı",
      bsub: "Sınıf başına hücre sayısı · sütun üstündeki sayı = Ekstrem hücre · " +
            "güne geçmek için sütuna tıklayın",
      ttitle: "En riskli yerleşimler —",
      tsub: "Her yerleşimin 10 km yarıçapındaki hücrelerin ortalama skoru",
      th: ["Yerleşim", "Sınıf", "Skor", "Ekstrem hücre ≤5 km"],
      f1: "<b>Veri kaynakları (üretim sürümü):</b> EFFIS/Copernicus — Fire Weather " +
          "Index · OpenStreetMap — yollar & yerleşimler · OGM / EFFIS Burnt Area — yangın geçmişi.",
      f2: "<b>Skor yöntemi:</b> tüm Türkiye'de (0,05° hücreler) VIIRS sıcak noktalarıyla eğitilmiş LightGBM — " +
          "FWI ve alt endeksler, yollara & yerleşimlere uzaklık, OSM arazi örtüsü ve hücre yangın geçmişi. " +
          "Olasılık, 2021 Haziran–Eylül dağılımına göre 0–1 skora çevrilir (üst %20 / %5 / %1).",
      f3: "<b>Not:</b> 27 Tem – 2 Ağu 2021 haftası geriye dönük tahmindir (model 2022–2025 ile eğitildi, 2021'i görmedi). " +
          "Yükseklik ve eğim henüz yok; yangın geçmişi üçgenleri yaklaşık konumdur.",
      classes: ["Düşük", "Orta", "Yüksek", "Ekstrem"],
      lc: ["Orman", "Maki/çalılık", "Tarım", "Yerleşim", "Çayır/çıplak alan"],
      days: ["Pzt 27/7", "Sal 28/7", "Çar 29/7", "Per 30/7", "Cum 31/7", "Cmt 1/8", "Paz 2/8"],
      layers: { risk: "Risk (sınıf)", fwi: "FWI", droad: "Yola uzaklık", dset: "Yerleşime uzaklık" },
      legRisk: "▲ yangın geçmişi · ● yerleşim",
      legFwi: "yangın hava tehlike endeksi (koyu = daha tehlikeli)",
      legDist: "koyu = daha yakın (insan kaynaklı tutuşma maruziyeti daha yüksek)",
      km: "km", score: "skor", road: "yol", settle: "yerleşim",
      clickDetail: "detay için tıklayın", burned: "ha yandı",
      approx: "yaklaşık konum — demo",
      zoomTR: "Türkiye", zoomPilot: "Pilot bölge", shape: ["■ Kare", "● Daire"],
      rows: ["Risk skoru", "Bugünkü FWI", "Son 3 gün ort. FWI", "Yola uzaklık",
             "Yerleşime uzaklık", "Arazi örtüsü", "Yükseklik", "Koordinat"],
      compass: ["K", "D"],
      spark: "7 günlük risk skoru", contrib: "Skoru etkileyen faktörler",
      factors: ["Hava & kuraklık", "Yola yakınlık", "Yerleşime yakınlık",
                "Bitki örtüsü yakıtı", "Eğim"],
      mcontrib: "Model katkısı (SHAP, hafta ortalaması)",
      mfactors: ["Hava & kuraklık", "İnsan erişimi", "Yangın geçmişi", "Arazi örtüsü"],
      mfactorsAll: ["Hava & kuraklık", "İnsan erişimi", "Yangın geçmişi", "Arazi örtüsü & arazi"],
      liveBadge: "CANLI TAHMİN", active: "Aktif yangın noktası (FIRMS)", agri: "muhtemelen tarımsal yakma",
      loadfail: "Veri yüklenemedi"
    },
    en: {
      title: "FireBridge — Forest Fire Risk Dashboard",
      badge: "MODEL · 2021 HINDCAST",
      sub: "#BizdenBize · COP31 Climate Tech Creathon · All of Türkiye · " +
           "Stage 1–4: 5 km grid, fire weather (FWI), human access " +
           "(roads & settlements) and fire history",
      kpi1: "Cells in Extreme class", kpi2: "Settlements near extreme zone (≤5 km)",
      kpi3: "Region mean FWI", kpi4: "High + Extreme area",
      kpi4s: "share of all land cells",
      same: "same as yesterday", vsYest: "vs yesterday", none: "none", max: "maximum",
      roads: "Roads", set: "Settlements", fires: "Fire history", day: "Day",
      dtitle: "Cell detail",
      dhint: "Click a cell on the map to see its Stage 2 features: " +
             "FWI, distance to roads & settlements, vegetation, and the drivers of its score.",
      btitle: "Risk class distribution by day",
      bsub: "Cell count per class · number above each bar = Extreme cells · " +
            "click a bar to switch day",
      ttitle: "Highest-risk settlements —",
      tsub: "Mean score of cells within a 10 km radius of each settlement",
      th: ["Settlement", "Class", "Score", "Extreme cells ≤5 km"],
      f1: "<b>Data sources (production version):</b> EFFIS/Copernicus — Fire Weather " +
          "Index · OpenStreetMap — roads & settlements · OGM / EFFIS Burnt Area — fire history.",
      f2: "<b>Scoring method:</b> LightGBM trained on VIIRS hotspots across all of Türkiye (0.05° cells) — " +
          "FWI and sub-indices, distance to roads & settlements, OSM land cover and cell fire history. " +
          "Probabilities are mapped to a 0–1 score against the Jun–Sep 2021 distribution (top 20% / 5% / 1%).",
      f3: "<b>Note:</b> the week 27 Jul – 2 Aug 2021 is a hindcast (model trained on 2022–2025, never saw 2021). " +
          "Elevation and slope are not available yet; fire-history triangles are approximate locations.",
      classes: ["Low", "Moderate", "High", "Extreme"],
      lc: ["Forest", "Maquis/shrubland", "Agriculture", "Settlement", "Grassland/bare"],
      days: ["Mon 27/7", "Tue 28/7", "Wed 29/7", "Thu 30/7", "Fri 31/7", "Sat 1/8", "Sun 2/8"],
      layers: { risk: "Risk (class)", fwi: "FWI", droad: "Distance to road", dset: "Distance to settlement" },
      legRisk: "▲ fire history · ● settlement",
      legFwi: "fire weather danger index (darker = more dangerous)",
      legDist: "darker = closer (higher human-ignition exposure)",
      km: "km", score: "score", road: "road", settle: "settlement",
      clickDetail: "click for details", burned: "ha burned",
      approx: "approximate location — demo",
      zoomTR: "Türkiye", zoomPilot: "Pilot area", shape: ["■ Squares", "● Circles"],
      rows: ["Risk score", "FWI today", "3-day mean FWI", "Distance to road",
             "Distance to settlement", "Land cover", "Elevation", "Coordinates"],
      compass: ["N", "E"],
      spark: "7-day risk score", contrib: "Score drivers",
      factors: ["Weather & drought", "Road proximity", "Settlement proximity",
                "Vegetation fuel", "Slope"],
      mcontrib: "Model contribution (SHAP, week mean)",
      mfactors: ["Weather & drought", "Human access", "Fire history", "Land cover"],
      mfactorsAll: ["Weather & drought", "Human access", "Fire history", "Land cover & terrain"],
      liveBadge: "LIVE FORECAST", active: "Active fire hotspot (FIRMS)", agri: "likely agricultural burning",
      loadfail: "Failed to load data"
    }
  };

  var lang = "tr";
  try { var sv = localStorage.getItem("fb-lang"); if (sv === "en" || sv === "tr") lang = sv; } catch (e) {}
  function T() { return I18N[lang]; }

  // --------------------------------------------------------------- state --
  var D = null, day = 5, layer = "risk", selected = -1;
  var cellIndex = null, setNear = [];
  var mq = window.matchMedia("(prefers-color-scheme: dark)");

  var ICONS = ["✓", "!", "▲", "‼"];
  var FUEL = [1.0, 0.8, 0.55, 0.15, 0.5];
  var RISK_COLORS = ["#0ca30c", "#fab219", "#ec835a", "#d03b3b"];
  var PAL = {
    light: { sea: "#ededea", road: "#898781", ink: "#0b0b0b", ink2: "#52514e", ring: "#fcfcfb",
             fwi: ["#f09c6b", "#eb6834", "#c24e1f", "#8f3918", "#5f2510"],
             dist: ["#86b6ef", "#3987e5", "#256abf", "#184f95", "#0d366b"] },
    dark:  { sea: "#111113", road: "#898781", ink: "#f0efec", ink2: "#c3c2b7", ring: "#1a1a19",
             fwi: ["#f9c4a5", "#ed9663", "#e06027", "#b84a1f", "#8f3918"],
             dist: ["#cde2fb", "#9ec5f4", "#5598e7", "#2a78d6", "#184f95"] }
  };
  function pal() { return mq.matches ? PAL.dark : PAL.light; }

  function classOf(r) { return r >= 0.75 ? 3 : r >= 0.55 ? 2 : r >= 0.3 ? 1 : 0; }
  function fwiBin(v) { return v < 40 ? 0 : v < 48 ? 1 : v < 56 ? 2 : v < 64 ? 3 : 4; }
  function distBin(km) { return km < 2 ? 4 : km < 5 ? 3 : km < 10 ? 2 : km < 20 ? 1 : 0; }

  var LAYERS = {
    risk:  function (i) { return RISK_COLORS[classOf(D.cells.risk[day][i])]; },
    fwi:   function (i) { return pal().fwi[fwiBin(D.cells.fwi[day][i])]; },
    droad: function (i) { return pal().dist[distBin(D.cells.dist_road[i])]; },
    dset:  function (i) { return pal().dist[distBin(D.cells.dist_set[i])]; }
  };

  var KMX = 111.32 * Math.cos(36.8 * Math.PI / 180), KMY = 110.57;   // KMX reset to the bbox centre in init()
  function lonOf(i) { return D.meta.bbox[0] + (D.cells.ix[i] + 0.5) * D.meta.cell; }
  function latOf(i) { return D.meta.bbox[1] + (D.cells.iy[i] + 0.5) * D.meta.cell; }

  var cv, ctx, W = 0, H = 0;
  function X(lon) { return (lon - D.meta.bbox[0]) / (D.meta.bbox[2] - D.meta.bbox[0]) * W; }
  function Y(lat) { return (1 - (lat - D.meta.bbox[1]) / (D.meta.bbox[3] - D.meta.bbox[1])) * H; }

  function sizeCanvas() {
    var w = cv.parentNode.clientWidth;
    var h = Math.round(w * ((D.meta.bbox[3] - D.meta.bbox[1]) * KMY /
                            ((D.meta.bbox[2] - D.meta.bbox[0]) * KMX)));
    var dpr = window.devicePixelRatio || 1;
    W = w; H = h;
    cv.width = Math.round(w * dpr); cv.height = Math.round(h * dpr);
    cv.style.height = h + "px";
    ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
  }

  // ----------------------------------------------------------------- map --
  function draw() {
    if (lmap) { drawLeaflet(); return; }
    var p = pal(), n = D.cells.ix.length;
    var cw = W / D.meta.ncols, ch = H / D.meta.nrows, g = Math.min(1, cw * 0.08);
    ctx.clearRect(0, 0, W, H);
    ctx.fillStyle = p.sea; ctx.fillRect(0, 0, W, H);

    var fn = LAYERS[layer];
    for (var i = 0; i < n; i++) {
      var x = D.cells.ix[i] * cw, y = H - (D.cells.iy[i] + 1) * ch;
      ctx.fillStyle = fn(i);
      ctx.fillRect(x + g / 2, y + g / 2, cw - g, ch - g);
    }

    if (document.getElementById("ovRoads").checked) {
      ctx.strokeStyle = p.road; ctx.lineWidth = 1.5; ctx.lineJoin = "round";
      D.roads.forEach(function (line) {
        ctx.beginPath();
        line.forEach(function (pt, k) {
          var px = X(pt[0]), py = Y(pt[1]);
          if (k === 0) ctx.moveTo(px, py); else ctx.lineTo(px, py);
        });
        ctx.stroke();
      });
    }

    if (document.getElementById("ovFires").checked && D.active_fires) {
      D.active_fires.forEach(function (a) {
        ctx.beginPath(); ctx.arc(X(a[0]), Y(a[1]), a[3] ? 3 : 2, 0, 2 * Math.PI);
        ctx.fillStyle = a[3] ? "#ff6a00" : "rgba(255,160,60,.6)"; ctx.fill();
      });
    }
    if (document.getElementById("ovFires").checked) {
      D.fires.forEach(function (f) {
        var px = X(f[1]), py = Y(f[2]), s = 4 + Math.sqrt(f[4]) / 28;
        ctx.beginPath();
        ctx.moveTo(px, py - s); ctx.lineTo(px + s * 0.9, py + s * 0.75);
        ctx.lineTo(px - s * 0.9, py + s * 0.75); ctx.closePath();
        ctx.fillStyle = "rgba(208,59,59,.18)"; ctx.fill();
        ctx.strokeStyle = "#d03b3b"; ctx.lineWidth = 2; ctx.stroke();
      });
    }

    if (document.getElementById("ovSet").checked) {
      ctx.font = "10.5px system-ui, sans-serif"; ctx.textBaseline = "middle";
      D.settlements.forEach(function (s) {
        var px = X(s[1]), py = Y(s[2]), r = s[3] >= 100000 ? 4 : 3;
        ctx.beginPath(); ctx.arc(px, py, r, 0, 7);
        ctx.fillStyle = p.ink; ctx.fill();
        ctx.strokeStyle = p.ring; ctx.lineWidth = 1.5; ctx.stroke();
        if (s[3] >= 60000) { ctx.fillStyle = p.ink2; ctx.fillText(s[0], px + 7, py); }
      });
    }

    if (selected >= 0) {
      var sx = D.cells.ix[selected] * cw, sy = H - (D.cells.iy[selected] + 1) * ch;
      ctx.strokeStyle = p.ink; ctx.lineWidth = 2;
      ctx.strokeRect(sx + 1, sy + 1, cw - 2, ch - 2);
    }
  }

  // ----------------------------------------- zoomable map (Leaflet + OSM) --
  // Used when the page has #osm and Leaflet loaded; otherwise the canvas map above.
  var lmap = null, lcells = [], lRoads = null, lSet = null, lSetSmall = null, lFires = null, lCellGroup = null;
  var SMALL_TOWN_ZOOM = 8;                          // towns < 50k only appear once zoomed in
  var TR_BOUNDS = [[35.8, 25.6], [42.2, 44.9]];   // whole Türkiye
  var CIRCLE_M = 2400;                             // ~half a 0.05° cell (4.5 x 5.5 km)
  var shape = "square";
  try { if (localStorage.getItem("fb-shape") === "circle") shape = "circle"; } catch (e) {}

  function cellBounds(i) {
    var x0 = D.meta.bbox[0] + D.cells.ix[i] * D.meta.cell;
    var y0 = D.meta.bbox[1] + D.cells.iy[i] * D.meta.cell;
    return [[y0, x0], [y0 + D.meta.cell, x0 + D.meta.cell]];
  }
  function pilotBounds() {
    var b = D.meta.pilot_bbox || D.meta.bbox;
    return [[b[1], b[0]], [b[3], b[2]]];
  }

  // one shared canvas renderer: separate canvases stack, and the top one swallows clicks/hovers
  function buildCells() {
    if (lCellGroup) lCellGroup.remove();
    lcells = D.cells.ix.map(function (_, i) {
      var b = cellBounds(i);
      var opts = { stroke: false, fillOpacity: 0.62 };
      var shp = shape === "circle"
        ? L.circle([(b[0][0] + b[1][0]) / 2, (b[0][1] + b[1][1]) / 2], L.extend({ radius: CIRCLE_M }, opts))
        : L.rectangle(b, opts);
      return shp.bindTooltip(function () { return cellTip(i); }, { sticky: true })
        .on("click", function () { selected = (i === selected) ? -1 : i; draw(); renderDetail(); });
    });
    lCellGroup = L.layerGroup(lcells).addTo(lmap);
    lCellGroup.eachLayer(function (l) { l.bringToBack(); });   // keep roads/towns above the cells
  }

  function initLeaflet() {
    var p = pal();
    lmap = L.map("osm", { preferCanvas: true, minZoom: 5, zoomSnap: 0.25,
                          maxBounds: [[33.5, 22], [44.5, 48]], maxBoundsViscosity: 0.8 });
    // town labels only once zoomed in enough to read them
    var labelToggle = function () {
      lmap.getContainer().classList.toggle("lowzoom", lmap.getZoom() < 7);
    };
    lmap.on("zoomend", labelToggle);
    L.tileLayer("https://tile.openstreetmap.org/{z}/{x}/{y}.png", {
      maxZoom: 15,
      attribution: '&copy; <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a>'
    }).addTo(lmap);
    lmap.fitBounds(D.meta.coverage === "turkiye" ? TR_BOUNDS : pilotBounds());
    labelToggle();

    // pilot area outline (the original Antalya–Muğla study box)
    L.rectangle(pilotBounds(), { color: p.ink2, weight: 1.5, dashArray: "5 5", fill: false,
                                 interactive: false }).addTo(lmap);

    buildCells();

    lRoads = L.layerGroup(D.roads.map(function (line) {
      return L.polyline(line.map(function (pt) { return [pt[1], pt[0]]; }),
                        { color: p.road, weight: 1.5, interactive: false });
    }));
    var townMarker = function (s) {
      var m = L.circleMarker([s[2], s[1]], { radius: s[3] >= 100000 ? 5 : 3.5, color: p.ring, weight: 1.5,
                                             fillColor: p.ink, fillOpacity: 1 });
      return s[3] >= 60000 ? m.bindTooltip(s[0], { permanent: true, direction: "right", className: "lbl" })
                           : m.bindTooltip(s[0]);
    };
    lSet = L.layerGroup(D.settlements.filter(function (s) { return s[3] >= 50000; }).map(townMarker));
    lSetSmall = L.layerGroup(D.settlements.filter(function (s) { return s[3] < 50000; }).map(townMarker));
    lmap.on("zoomend", function () { drawLeaflet(); });
    lFires = L.layerGroup(D.fires.map(function (f) {
      var s = Math.round(10 + Math.sqrt(f[4]) / 20);
      return L.marker([f[2], f[1]], { icon: L.divIcon({
        className: "", iconSize: [s, s],
        html: '<div style="color:#d03b3b;font-size:' + s + 'px;line-height:1;text-shadow:0 0 2px #fff">▲</div>' }) })
        .bindTooltip(function () { return fireTip(f); });
    }).concat((D.active_fires || []).map(function (a) {
      return L.circleMarker([a[1], a[0]], { radius: a[3] ? 4 : 3, stroke: false,
                                            fillColor: a[3] ? "#ff6a00" : "#ffa03c", fillOpacity: a[3] ? 0.95 : 0.6 })
        .bindTooltip(function () { return "<b>" + T().active + "</b> · " + a[2] +
                                          (a[3] ? "" : "<br><i>" + T().agri + "</i>"); });
    })));

    var Zoom = L.Control.extend({
      onAdd: function () {
        var box = L.DomUtil.create("div", "leaflet-bar zoomto");
        [["zTR", function () { lmap.fitBounds(TR_BOUNDS); }],
         ["zPilot", function () { lmap.fitBounds(pilotBounds()); }],
         ["zShape", function () {
           shape = shape === "circle" ? "square" : "circle";
           try { localStorage.setItem("fb-shape", shape); } catch (e) {}
           buildCells(); draw(); setShapeLabel();
         }]].forEach(function (z) {
          var a = L.DomUtil.create("a", "", box);
          a.id = "t-" + z[0]; a.href = "#"; a.setAttribute("role", "button");
          L.DomEvent.on(a, "click", function (e) { L.DomEvent.preventDefault(e); z[1](); });
        });
        L.DomEvent.disableClickPropagation(box);
        return box;
      }
    });
    new Zoom({ position: "topleft" }).addTo(lmap);
  }

  // the button names the shape you switch *to*
  function setShapeLabel() {
    document.getElementById("t-zShape").textContent = T().shape[shape === "circle" ? 0 : 1];
  }

  function drawLeaflet() {
    var fn = LAYERS[layer], ink = pal().ink;
    lcells.forEach(function (r, i) {
      r.setStyle({ fillColor: fn(i), stroke: i === selected, color: ink, weight: 2 });
    });
    [[lRoads, "ovRoads"], [lSet, "ovSet"], [lFires, "ovFires"]].forEach(function (g) {
      if (document.getElementById(g[1]).checked) g[0].addTo(lmap); else g[0].remove();
    });
    if (document.getElementById("ovSet").checked && lmap.getZoom() >= SMALL_TOWN_ZOOM) lSetSmall.addTo(lmap);
    else lSetSmall.remove();
  }

  // -------------------------------------------------------------- legend --
  function renderLegend() {
    function it(c, t) { return '<span class="it"><span class="sw" style="background:' + c + '"></span>' + t + "</span>"; }
    var t = T(), html;
    if (layer === "risk") {
      html = RISK_COLORS.map(function (c, k) { return it(c, ICONS[k] + " " + t.classes[k]); }).join("") +
             '<span class="it">' + t.legRisk + "</span>";
    } else if (layer === "fwi") {
      var lbl = ["< 40", "40–48", "48–56", "56–64", "≥ 64"];
      html = pal().fwi.map(function (c, k) { return it(c, lbl[k]); }).join("") +
             '<span class="it">' + t.legFwi + "</span>";
    } else {
      var dl = ["> 20 km", "10–20", "5–10", "2–5", "< 2 km"];
      html = pal().dist.map(function (c, k) { return it(c, dl[k]); }).join("") +
             '<span class="it">' + t.legDist + "</span>";
    }
    document.getElementById("legend").innerHTML = html;
  }

  // ----------------------------------------------------------------- KPI --
  function counts(d) {
    var c = [0, 0, 0, 0], r = D.cells.risk[d];
    for (var i = 0; i < r.length; i++) c[classOf(r[i])]++;
    return c;
  }
  function renderKPIs() {
    var t = T(), n = D.cells.ix.length, c = counts(day);
    document.getElementById("kpi1").textContent = c[3];
    var s1 = "";
    if (day > 0) {
      var dd = c[3] - counts(day - 1)[3];
      s1 = dd === 0 ? t.same
         : '<span class="' + (dd > 0 ? "delta-up" : "delta-dn") + '">' +
           (dd > 0 ? "▲ +" : "▼ ") + dd + "</span> " + t.vsYest;
    }
    document.getElementById("kpi1s").innerHTML = s1;

    var aff = [];
    setNear.forEach(function (sn, si) {
      for (var k = 0; k < sn.c5.length; k++)
        if (D.cells.risk[day][sn.c5[k]] >= 0.75) { aff.push(D.settlements[si][0]); break; }
    });
    document.getElementById("kpi2").textContent = aff.length;
    document.getElementById("kpi2s").textContent =
      aff.length ? aff.slice(0, 3).join(", ") + (aff.length > 3 ? ", …" : "") : t.none;

    var f = D.cells.fwi[day], sum = 0, mx = 0;
    for (var i = 0; i < f.length; i++) { sum += f[i]; if (f[i] > mx) mx = f[i]; }
    document.getElementById("kpi3").textContent = (sum / n).toFixed(1);
    document.getElementById("kpi3s").textContent = t.max + " " + mx.toFixed(1);
    document.getElementById("kpi4").textContent = (100 * (c[2] + c[3]) / n).toFixed(0) + "%";
  }

  // ---------------------------------------------------------------- bars --
  function renderBars() {
    var t = T(), bars = document.getElementById("bars");
    bars.innerHTML = "";
    var n = D.cells.ix.length, HPX = 150;
    t.days.forEach(function (_, d) {
      var c = counts(d), col = document.createElement("div");
      col.className = "col"; col.setAttribute("role", "button");
      col.setAttribute("aria-pressed", d === day ? "true" : "false");
      col.title = t.days[d] + " — " +
        c.map(function (v, k) { return t.classes[k] + " " + v; }).join(", ");
      c.forEach(function (v, k) {
        if (!v) return;
        var s = document.createElement("div");
        s.className = "seg-b";
        s.style.height = Math.max(2, v / n * HPX) + "px";
        s.style.background = RISK_COLORS[k];
        col.appendChild(s);
      });
      var tp = document.createElement("div");
      tp.className = "top"; tp.textContent = c[3];
      col.appendChild(tp);
      col.addEventListener("click", function () { setDay(d); });
      bars.appendChild(col);
    });
    document.getElementById("barsX").innerHTML =
      t.days.map(function (d) { return "<span>" + d.split(" ")[1] + "</span>"; }).join("");
    document.getElementById("barsLegend").innerHTML = RISK_COLORS.map(function (c, k) {
      return '<span class="it"><span class="sw" style="background:' + c + '"></span>' +
             ICONS[k] + " " + t.classes[k] + "</span>";
    }).join("");
  }

  // --------------------------------------------------------------- table --
  function renderTable() {
    var t = T();
    var rows = D.settlements.map(function (s, si) {
      var c10 = setNear[si].c10, sum = 0, ext = 0, k;
      for (k = 0; k < c10.length; k++) sum += D.cells.risk[day][c10[k]];
      for (k = 0; k < setNear[si].c5.length; k++)
        if (D.cells.risk[day][setNear[si].c5[k]] >= 0.75) ext++;
      return { name: s[0], score: c10.length ? sum / c10.length : 0, ext: ext };
    }).sort(function (a, b) { return b.score - a.score; }).slice(0, 10);

    document.getElementById("tblDay").textContent = t.days[day];
    document.getElementById("tblBody").innerHTML = rows.map(function (r) {
      var k = classOf(r.score);
      return "<tr><td>" + r.name + '</td><td><span class="chip' + (k === 1 ? " k1" : "") +
        '" style="background:' + RISK_COLORS[k] + '">' + ICONS[k] + " " + t.classes[k] +
        "</span></td><td>" + r.score.toFixed(2) + "</td><td>" + r.ext + "</td></tr>";
    }).join("");
  }

  // -------------------------------------------------------------- detail --
  function fwiLag3(i, d) {
    if (d === 0) return D.cells.fwi[0][i];
    var lo = Math.max(0, d - 3), s = 0;
    for (var k = lo; k < d; k++) s += D.cells.fwi[k][i];
    return s / (d - lo);
  }
  function renderDetail() {
    var el = document.getElementById("detailBody");
    if (selected < 0) { el.innerHTML = ""; return; }
    var t = T(), i = selected, c = D.cells, k = classOf(c.risk[day][i]);
    var lag = fwiLag3(i, day);
    // real model contributions (SHAP group shares) when exported, else the demo heuristic
    var parts = c.shap ? c.shap.map(function (g) { return g[i]; }) : [
      4.4 * c.fwi[day][i] / 100 + 1.6 * lag / 100,
      1.5 * Math.exp(-c.dist_road[i] / 3),
      1.2 * Math.exp(-c.dist_set[i] / 6),
      1.3 * FUEL[c.landcover[i]],
      0.5 * (c.slope[i] || 0)
    ];
    var fnames = c.shap ? t.mfactors : t.factors;
    var tot = parts.reduce(function (a, p) { return a + p; }, 0);

    var pts = t.days.map(function (_, d) {
      return [8 + d * (180 / 6), 46 - c.risk[d][i] * 40];
    });
    var line = pts.map(function (p, j) { return (j ? "L" : "M") + p[0].toFixed(1) + " " + p[1].toFixed(1); }).join(" ");
    var vals = [
      c.risk[day][i].toFixed(2) + " (" + t.days[day] + ")",
      c.fwi[day][i].toFixed(1), lag.toFixed(1),
      c.dist_road[i].toFixed(1) + " " + t.km,
      c.dist_set[i].toFixed(1) + " " + t.km,
      t.lc[c.landcover[i]], c.elev[i] == null ? "–" : c.elev[i] + " m",
      latOf(i).toFixed(2) + "°" + t.compass[0] + ", " +
        lonOf(i).toFixed(2) + "°" + t.compass[1]
    ];

    el.innerHTML =
      '<p style="margin:8px 0 2px"><span class="chip' + (k === 1 ? " k1" : "") +
      '" style="background:' + RISK_COLORS[k] + '">' + ICONS[k] + " " + t.classes[k] + "</span></p>" +
      "<table>" + t.rows.map(function (r, j) {
        return "<tr><td>" + r + "</td><td>" + vals[j] + "</td></tr>";
      }).join("") + "</table>" +
      '<div style="font-size:12px;color:var(--ink-2);margin-top:8px">' + t.spark + "</div>" +
      '<svg viewBox="0 0 196 52" style="width:100%;height:52px" role="img" aria-label="' + t.spark + '">' +
      '<path d="' + line + '" fill="none" stroke="var(--series-1)" stroke-width="2"/>' +
      '<circle cx="' + pts[day][0] + '" cy="' + pts[day][1] + '" r="4" fill="var(--series-1)"/></svg>' +
      '<div class="contrib"><div style="font-size:12px;color:var(--ink-2)">' + (c.shap ? t.mcontrib : t.contrib) + "</div>" +
      parts.map(function (p, j) {
        var pc = Math.round(100 * p / (tot || 1));
        return '<div class="row"><span class="nm">' + fnames[j] + '</span>' +
               '<span class="bar"><i style="width:' + pc + '%"></i></span>' +
               '<span class="pv">' + pc + "%</span></div>";
      }).join("") + "</div>";
  }

  // ------------------------------------------------------ map interaction --
  function cellAt(px, py) {
    var ix = Math.floor(px / W * D.meta.ncols);
    var iy = D.meta.nrows - 1 - Math.floor(py / H * D.meta.nrows);
    var idx = cellIndex.get(iy * D.meta.ncols + ix);
    return idx === undefined ? -1 : idx;
  }
  function fireAt(px, py) {
    for (var k = 0; k < D.fires.length; k++) {
      var f = D.fires[k], s = Math.max(9, 4 + Math.sqrt(f[4]) / 28);
      if (Math.abs(px - X(f[1])) < s && Math.abs(py - Y(f[2])) < s) return f;
    }
    return null;
  }
  function fireTip(f) {
    var t = T();
    return "<b>▲ " + f[0] + "</b><br>±" + f[4].toLocaleString(lang) +
           " " + t.burned + " (" + f[3] + ")<br><i>" + t.approx + "</i>";
  }
  function cellTip(i) {
    var t = T(), k = classOf(D.cells.risk[day][i]);
    return "<b>" + ICONS[k] + " " + t.classes[k] + "</b> · " + t.score + " " +
      D.cells.risk[day][i].toFixed(2) +
      "<br>FWI " + D.cells.fwi[day][i].toFixed(1) +
      " · " + t.lc[D.cells.landcover[i]] +
      "<br>" + t.road + " " + D.cells.dist_road[i].toFixed(1) +
      " " + t.km + " · " + t.settle + " " + D.cells.dist_set[i].toFixed(1) + " " + t.km +
      "<br><i>" + t.clickDetail + "</i>";
  }
  function onMove(e) {
    var r = cv.getBoundingClientRect();
    var px = e.clientX - r.left, py = e.clientY - r.top;
    var tip = document.getElementById("tip"), html = "";
    var f = document.getElementById("ovFires").checked ? fireAt(px, py) : null;
    if (f) {
      html = fireTip(f);
    } else {
      var i = cellAt(px, py);
      if (i >= 0) html = cellTip(i);
    }
    if (!html) { tip.style.display = "none"; return; }
    tip.innerHTML = html; tip.style.display = "block";
    var tw = tip.offsetWidth;
    tip.style.left = Math.min(px + 14, W - tw - 4) + "px";
    tip.style.top = (py + 14) + "px";
  }
  function onClick(e) {
    var r = cv.getBoundingClientRect();
    var i = cellAt(e.clientX - r.left, e.clientY - r.top);
    selected = (i === selected) ? -1 : i;
    draw(); renderDetail();
  }

  // ------------------------------------------------------------ controls --
  function setDay(d) {
    day = d;
    document.getElementById("day").value = String(d);
    document.getElementById("dayLbl").textContent = T().days[d];
    draw(); renderKPIs(); renderTable(); renderDetail();
    var cols = document.querySelectorAll("#bars .col");
    cols.forEach(function (c, k) { c.setAttribute("aria-pressed", k === d ? "true" : "false"); });
  }
  function setLayer(l) {
    layer = l;
    document.querySelectorAll("#layerBtns .seg").forEach(function (b) {
      b.setAttribute("aria-pressed", b.dataset.layer === l ? "true" : "false");
    });
    draw(); renderLegend();
  }
  function applyLang() {
    var t = T();
    try { localStorage.setItem("fb-lang", lang); } catch (e) {}
    try { document.documentElement.lang = lang; } catch (e) {}
    var set = function (id, v) { document.getElementById(id).textContent = v; };
    set("t-title", t.title); set("t-badge", t.badge); set("t-sub", t.sub);
    set("t-kpi1", t.kpi1); set("t-kpi2", t.kpi2); set("t-kpi3", t.kpi3);
    set("t-kpi4", t.kpi4); set("t-kpi4s", t.kpi4s);
    set("t-roads", t.roads); set("t-set", t.set); set("t-fires", t.fires);
    set("t-day", t.day); set("t-dtitle", t.dtitle); set("t-dhint", t.dhint);
    set("t-btitle", t.btitle); set("t-bsub", t.bsub);
    set("t-ttitle", t.ttitle); set("t-tsub", t.tsub);
    t.th.forEach(function (h, j) { set("th" + (j + 1), h); });
    if (lmap) { set("t-zTR", t.zoomTR); set("t-zPilot", t.zoomPilot); setShapeLabel(); }
    document.getElementById("t-f1").innerHTML = t.f1;
    document.getElementById("t-f2").innerHTML = t.f2;
    document.getElementById("t-f3").innerHTML = t.f3;
    document.querySelectorAll("#langBtns .seg").forEach(function (b) {
      b.setAttribute("aria-pressed", b.dataset.lang === lang ? "true" : "false");
    });
    document.querySelectorAll("#layerBtns .seg").forEach(function (b) {
      b.textContent = t.layers[b.dataset.layer];
    });
    renderLegend(); renderBars(); setDay(day);
  }

  // ---------------------------------------------------------------- init --
  var GROUP_INDEX = { cuaca: 0, manusia: 1, histori: 2, lingkungan: 3 };
  function applyMeta() {
    var m = D.meta, names = { tr: ["Paz", "Pzt", "Sal", "Çar", "Per", "Cum", "Cmt"],
                              en: ["Sun", "Mon", "Tue", "Wed", "Thu", "Fri", "Sat"] };
    ["tr", "en"].forEach(function (l) {
      var t = I18N[l];
      t.days = m.dates.map(function (iso) {
        var d = new Date(iso + "T12:00:00");
        return names[l][d.getDay()] + " " + d.getDate() + "/" + (d.getMonth() + 1);
      });
      if (m.mode === "live") t.badge = t.liveBadge + " · " + String(m.generated_at).replace("T", " ");
      if (m.groups) t.mfactors = m.groups.map(function (g) { return t.mfactorsAll[GROUP_INDEX[g]]; });
    });
    if (m.mode === "live") day = 0;
    if (day >= m.dates.length) day = m.dates.length - 1;
  }

  function init(data) {
    D = data;
    if (D.meta.dates) applyMeta();
    cv = document.getElementById("map"); ctx = cv.getContext("2d");

    KMX = 111.32 * Math.cos((D.meta.bbox[1] + D.meta.bbox[3]) / 2 * Math.PI / 180);
    cellIndex = new Map();
    for (var i = 0; i < D.cells.ix.length; i++)
      cellIndex.set(D.cells.iy[i] * D.meta.ncols + D.cells.ix[i], i);

    setNear = D.settlements.map(function (s) {
      // only scan the grid window within 10 km (whole-country grids have ~30k cells)
      var c5 = [], c10 = [], b = D.meta.bbox, cs = D.meta.cell;
      var rx = Math.ceil(10 / (KMX * cs)) + 1, ry = Math.ceil(10 / (KMY * cs)) + 1;
      var cx = Math.floor((s[1] - b[0]) / cs), cy = Math.floor((s[2] - b[1]) / cs), near = [];
      for (var gy = cy - ry; gy <= cy + ry; gy++)
        for (var gx = cx - rx; gx <= cx + rx; gx++) {
          if (gx < 0 || gy < 0 || gx >= D.meta.ncols || gy >= D.meta.nrows) continue;
          var hit = cellIndex.get(gy * D.meta.ncols + gx);
          if (hit !== undefined) near.push(hit);
        }
      for (var q = 0; q < near.length; q++) {
        var j = near[q];
        var dx = (lonOf(j) - s[1]) * KMX, dy = (latOf(j) - s[2]) * KMY;
        var dd = Math.hypot(dx, dy);
        if (dd <= 5) c5.push(j);
        if (dd <= 10) c10.push(j);
      }
      return { c5: c5, c10: c10 };
    });

    var lb = document.getElementById("langBtns");
    ["tr", "en"].forEach(function (l) {
      var b = document.createElement("button");
      b.className = "seg"; b.dataset.lang = l; b.textContent = l.toUpperCase();
      b.addEventListener("click", function () { lang = l; applyLang(); });
      lb.appendChild(b);
    });

    var btns = document.getElementById("layerBtns");
    Object.keys(LAYERS).forEach(function (l) {
      var b = document.createElement("button");
      b.className = "seg"; b.dataset.layer = l;
      b.setAttribute("aria-pressed", l === layer ? "true" : "false");
      b.addEventListener("click", function () { setLayer(l); });
      btns.appendChild(b);
    });

    document.getElementById("day").addEventListener("input", function (e) {
      setDay(+e.target.value);
    });
    ["ovRoads", "ovSet", "ovFires"].forEach(function (id) {
      document.getElementById(id).addEventListener("change", draw);
    });

    document.getElementById("loading").style.display = "none";
    document.getElementById("app").style.display = "block";

    var osm = document.getElementById("osm");
    var reflow;
    if (osm && window.L) {               // zoomable map: Leaflet loaded from the CDN
      initLeaflet();
      reflow = function () { lmap.invalidateSize(); };
    } else {                             // offline / no #osm: static canvas map
      if (osm) osm.style.display = "none";
      cv.style.display = "block";
      cv.addEventListener("mousemove", onMove);
      cv.addEventListener("mouseleave", function () {
        document.getElementById("tip").style.display = "none";
      });
      cv.addEventListener("click", onClick);
      reflow = function () { sizeCanvas(); draw(); };
      sizeCanvas();
    }
    if (window.ResizeObserver) new ResizeObserver(reflow).observe(cv.parentNode);
    window.addEventListener("resize", reflow);
    var onMode = function () { draw(); renderLegend(); };
    if (mq.addEventListener) mq.addEventListener("change", onMode);

    applyLang();
  }

  fetch(/[?&]live(=|&|$)/.test(location.search) ? "data.live.json" : "data.json")
    .then(function (r) { if (!r.ok) throw new Error("HTTP " + r.status); return r.json(); })
    .then(init)
    .catch(function (e) {
      document.getElementById("loading").textContent =
        I18N.tr.loadfail + " / " + I18N.en.loadfail + ": " + e.message;
    });
})();
