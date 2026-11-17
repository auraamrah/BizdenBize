// Real map: Leaflet + CARTO basemaps, with the BizdenBize model grid drawn on top.
// Leaflet is loaded as a classic script (assets/vendor/leaflet) and exposed as window.L.
import { CONFIG } from './config.js';
import { LEVEL_COLOR, LEVEL_ORDER, levelKey } from './data.js';
import { NO_DATA } from './risk.js';

const L = window.L;
const CARTO = 'https://basemaps.cartocdn.com/rastertiles';
const ATTR = '&copy; <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a> contributors, &copy; <a href="https://carto.com/attributions">CARTO</a>';

function hexToRgb(h) { const n = parseInt(h.slice(1), 16); return [(n >> 16) & 255, (n >> 8) & 255, n & 255]; }
const CLASS_RGB = LEVEL_ORDER.map(k => hexToRgb(LEVEL_COLOR[k]));
function ramp(stops, v) {
  for (let i = 1; i < stops.length; i++) {
    if (v <= stops[i][0]) {
      const [a, ca] = stops[i - 1], [b, cb] = stops[i], t = (v - a) / (b - a || 1);
      return ca.map((c, j) => Math.round(c + (cb[j] - c) * t));
    }
  }
  return stops.at(-1)[1];
}
const SCORE_STOPS = [[0, hexToRgb('#22c55e')], [0.3, hexToRgb('#eab308')], [0.55, hexToRgb('#f97316')], [0.75, hexToRgb('#ef4444')], [1, hexToRgb('#7f1d1d')]];
const FWI_STOPS = [[0, [255, 247, 188]], [5.2, [254, 196, 79]], [11.2, [254, 153, 41]], [21.3, [217, 95, 14]], [38, [153, 52, 4]], [80, [80, 20, 4]]];

const mercY = lat => Math.log(Math.tan(Math.PI / 4 + (lat * Math.PI) / 360));
const overlayCache = new Map();

// Render one day of the grid into a Web-Mercator-correct image (one rectangle per 0.05° cell).
function renderGrid(ds, day, mode, showLow, dark) {
  const key = `${ds.id}|${day}|${mode}|${showLow}|${dark}`;
  if (overlayCache.has(key)) return overlayCache.get(key);
  const m = ds.meta, PX = 6;
  const W = m.ncols * PX;
  const y0 = mercY(ds.south), y1 = mercY(ds.north);
  const lonSpanRad = ((ds.east - ds.west) * Math.PI) / 180;
  const H = Math.round(W * (y1 - y0) / lonSpanRad);
  const rowY = iy => Math.round(((y1 - mercY(ds.south + iy * m.cell)) / (y1 - y0)) * H);
  const cvs = document.createElement('canvas'); cvs.width = W; cvs.height = H;
  const ctx = cvs.getContext('2d');
  const img = ctx.createImageData(W, H), px = img.data;
  const lowA = dark ? 0.16 : 0.12;
  for (let iy = 0; iy < m.nrows; iy++) {
    const top = rowY(iy + 1), bot = rowY(iy);
    for (let ix = 0; ix < m.ncols; ix++) {
      const k = iy * m.ncols + ix, c = ds.klass[day][k];
      if (c === NO_DATA) continue;
      let rgb, a;
      if (mode === 'class') {
        if (c === 0 && !showLow) continue;
        rgb = CLASS_RGB[c]; a = [lowA, 0.55, 0.68, 0.8][c];
      } else if (mode === 'score') {
        const v = ds.risk[day][k] / 250;
        if (v < 0.05 && !showLow) continue;
        rgb = ramp(SCORE_STOPS, v); a = 0.2 + 0.6 * Math.min(1, v / 0.6);
      } else {
        const f = ds.fwi[day][k] / 2;
        rgb = ramp(FWI_STOPS, f); a = 0.25 + 0.5 * Math.min(1, f / 30);
      }
      const A = Math.round(a * 255);
      for (let y = top; y < bot; y++) {
        let o = (y * W + ix * PX) * 4;
        for (let x = 0; x < PX; x++, o += 4) { px[o] = rgb[0]; px[o + 1] = rgb[1]; px[o + 2] = rgb[2]; px[o + 3] = A; }
      }
    }
  }
  ctx.putImageData(img, 0, 0);
  const url = cvs.toDataURL('image/png');
  overlayCache.set(key, url);
  return url;
}

export function createMap(el, { dark = false, interactive = true, onClick } = {}) {
  const map = L.map(el, {
    preferCanvas: true, zoomControl: interactive, attributionControl: true,
    dragging: interactive, scrollWheelZoom: interactive ? 'center' : false, doubleClickZoom: interactive,
    boxZoom: interactive, keyboard: interactive, touchZoom: interactive, minZoom: 5, maxZoom: 13, worldCopyJump: false,
  });
  map.attributionControl.setPrefix(false);
  map.setView([39, 35], 6); // initial view over Türkiye; layers need a view before they're added
  map.createPane('risk'); map.getPane('risk').style.zIndex = 350;
  map.createPane('labels'); map.getPane('labels').style.zIndex = 420; map.getPane('labels').style.pointerEvents = 'none';
  map.createPane('points'); map.getPane('points').style.zIndex = 450;
  const renderer = L.canvas({ pane: 'points', padding: 0.3 });

  let base = null, labels = null, overlay = null, isDark = dark;
  const groups = { towns: L.layerGroup(), townsSmall: L.layerGroup(), fires: L.layerGroup(), reports: L.layerGroup(), sel: L.layerGroup() };
  Object.values(groups).forEach(g => g.addTo(map));

  function tiles(style, pane) {
    return L.tileLayer(`${CARTO}/${style}/{z}/{x}/{y}{r}.png?key=${encodeURIComponent(CONFIG.CARTO_KEY)}`, {
      attribution: ATTR, maxZoom: 19, pane, detectRetina: false, crossOrigin: true,
    });
  }
  function setTheme(d) {
    isDark = d;
    if (base) map.removeLayer(base);
    if (labels) { map.removeLayer(labels); labels = null; }
    if (d) {
      base = tiles('dark_all', 'tilePane').addTo(map);
    } else {
      // labels drawn above the risk colours so town names stay readable
      base = tiles('voyager_nolabels', 'tilePane').addTo(map);
      labels = tiles('voyager_only_labels', 'labels').addTo(map);
    }
  }
  setTheme(dark);

  if (onClick) map.on('click', e => onClick(e.latlng));

  const api = {
    map,
    setTheme(d) { setTheme(d); },
    fit(ds) { map.fitBounds([[ds.south, ds.west], [ds.north, ds.east]], { padding: [8, 8] }); },
    setRisk(ds, day, { mode = 'class', showLow = false, attribution = '' } = {}) {
      const url = renderGrid(ds, day, mode, showLow, isDark);
      const bounds = [[ds.south, ds.west], [ds.north, ds.east]];
      if (overlay) overlay.setUrl(url);
      else overlay = L.imageOverlay(url, bounds, { pane: 'risk', className: 'risk-overlay', interactive: false, attribution }).addTo(map);
    },
    setTowns(ds, day, onPick, label) {
      groups.towns.clearLayers(); groups.townsSmall.clearLayers();
      for (const s of ds.settlements) {
        const k = levelKey(s.mean[day]);
        const big = s.pop >= 100000;
        const mk = L.circleMarker([s.lat, s.lon], {
          renderer, radius: big ? 5 : 3.5, weight: 1.5, color: isDark ? '#0f141d' : '#ffffff', fillColor: LEVEL_COLOR[k], fillOpacity: 1,
        }).bindTooltip(label(s, k), { direction: 'top', offset: [0, -4] });
        if (onPick) mk.on('click', e => { L.DomEvent.stopPropagation(e); onPick(s); });
        mk.addTo(big ? groups.towns : groups.townsSmall);
      }
      const sync = () => { if (map.getZoom() >= 8) groups.townsSmall.addTo(map); else map.removeLayer(groups.townsSmall); };
      map.off('zoomend', sync); map.on('zoomend', sync); sync();
    },
    showTowns(v) { [groups.towns, groups.townsSmall].forEach(g => (v ? g.addTo(map) : map.removeLayer(g))); if (v && map.getZoom() < 8) map.removeLayer(groups.townsSmall); },
    setFires(fires, popup) {
      groups.fires.clearLayers();
      for (const [lon, lat, date] of fires) {
        L.circleMarker([lat, lon], { renderer, radius: 4.5, weight: 2, color: 'rgba(255,59,48,.45)', fillColor: '#ff3b30', fillOpacity: 1 })
          .bindTooltip(popup(date)).addTo(groups.fires);
      }
    },
    showFires(v) { v ? groups.fires.addTo(map) : map.removeLayer(groups.fires); },
    setReports(items, { onPick, color, label }) {
      groups.reports.clearLayers();
      const out = {};
      for (const r of items) {
        if (r.lat == null) continue;
        const mk = L.circleMarker([r.lat, r.lon], {
          renderer, radius: 6 + Math.round(r.priority / 18), weight: 3, color: isDark ? '#0f141d' : '#ffffff', fillColor: color(r), fillOpacity: 0.95,
        }).bindTooltip(label(r), { direction: 'top' });
        if (onPick) mk.on('click', e => { L.DomEvent.stopPropagation(e); onPick(r); });
        // camera view cone from the verifier (GeoJSON [lon, lat] ring), shown for green uploads
        if (r.verifier?.fov_cone) L.polygon(r.verifier.fov_cone.map(([lo, la]) => [la, lo]), { renderer, color: '#f97316', weight: 1, fillOpacity: 0.15, interactive: false }).addTo(groups.reports);
        mk.addTo(groups.reports); out[r.id] = mk;
      }
      return out;
    },
    select(lat, lon, { zoom } = {}) {
      groups.sel.clearLayers();
      if (lat == null) return;
      L.circleMarker([lat, lon], { renderer, radius: 11, weight: 4, color: isDark ? '#e8ecf3' : '#21293a', fill: false }).addTo(groups.sel);
      if (zoom) map.flyTo([lat, lon], zoom, { duration: 0.6 });
    },
    invalidate() { map.invalidateSize(); },
    destroy() { map.remove(); },
  };
  return api;
}
