"""從 data/facilities.json 生成 map.html（獨立示意地圖原型）。

座標來源：每站的 point，與 solver/planner.py 計算 walk_min 時用的是同一組座標。
地圖只做示意，不代表實際地理距離；比例與方位皆為版面需要而調整。

執行：python3 scripts/build_map.py
輸出：map.html（單檔、內嵌資料、開檔即用，不需 serve.py）
"""

from __future__ import annotations

import json
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DATA = ROOT / "data" / "facilities.json"
OUT = ROOT / "map.html"

TEMPLATE = """<!DOCTYPE html>
<html lang="zh-Hant">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>InclusiveGo 感官示意地圖 | 海洋公園</title>
<style>
  :root{
    --ink:#1c2b28; --muted:#5f6f6a; --line:#d6e3de;
    --green:#036356; --green-soft:#e7f0ed;
    --cream:#f8f6f1;
    --l1:#2e7d5b; --l3:#d08d28; --l5:#b8433a;
  }
  *{box-sizing:border-box}
  body{margin:0;background:var(--cream);color:var(--ink);
    font:15px/1.65 "Noto Sans TC","PingFang TC","Hiragino Sans GB",system-ui,sans-serif}
  header{padding:22px 28px 16px;border-bottom:1px solid var(--line);background:#fff}
  h1{margin:0 0 4px;font-size:19px;letter-spacing:.02em}
  .sub{color:var(--muted);font-size:13px}
  .wrap{display:grid;grid-template-columns:minmax(0,1fr) 360px;gap:0;
    max-width:1240px;margin:0 auto;background:#fff;min-height:calc(100vh - 92px)}
  .mapbox{padding:18px 20px 28px;border-right:1px solid var(--line);position:relative}
  .controls{display:flex;flex-wrap:wrap;gap:8px;margin-bottom:14px}
  .chip{border:1px solid var(--line);background:#fff;color:var(--ink);border-radius:999px;
    padding:5px 13px;font-size:13px;cursor:pointer;transition:.15s}
  .chip:hover{border-color:var(--green)}
  .chip.on{background:var(--green);color:#fff;border-color:var(--green)}
  .chip.ghost{background:transparent;border-style:dashed}
  .chip.ghost.on{background:var(--green);border:1px solid var(--green);color:#fff}
  svg{width:100%;height:auto;display:block}
  .node{cursor:pointer}
  .node circle{transition:.15s}
  .node:hover circle{stroke-width:4}
  .node.selected circle{stroke:#111;stroke-width:4}
  .node text{font-size:11.5px;fill:var(--ink);pointer-events:none}
  .zoneband{fill:#f0f4f2}
  .zoneband.alt{fill:#f6f8f6}
  .zonelabel{font-size:12px;fill:#7d8c87;letter-spacing:.14em}
  .route{fill:none;stroke:var(--green);stroke-width:2.4;stroke-dasharray:7 6;opacity:.85}
  .stepn{font-size:10px;fill:#fff}
  aside{padding:20px 22px 28px;overflow-y:auto}
  .panel-empty{color:var(--muted);font-size:13.5px;line-height:1.8}
  h2{font-size:15px;margin:0 0 2px}
  .meta{color:var(--muted);font-size:12.5px;margin-bottom:12px}
  table{border-collapse:collapse;width:100%;font-size:13px;margin:10px 0 14px}
  th,td{border-bottom:1px solid var(--line);padding:6px 4px;text-align:left}
  th{color:var(--muted);font-weight:500;font-size:12px}
  td.num{text-align:right;font-variant-numeric:tabular-nums}
  .bar{display:inline-block;height:8px;border-radius:3px;vertical-align:middle;margin-left:6px}
  .pill{display:inline-block;border:1px dashed #b9c8c2;color:var(--muted);
    border-radius:999px;padding:1px 8px;font-size:11.5px}
  .story{font-size:13px;color:#3a4a45;background:var(--green-soft);
    border-left:3px solid var(--green);padding:9px 12px;border-radius:0 6px 6px 0;margin:10px 0}
  .story b{display:block;color:var(--green);font-size:12px;margin-bottom:2px}
  .legend{display:flex;gap:14px;align-items:center;color:var(--muted);font-size:12px;margin-top:4px}
  .dot{width:10px;height:10px;border-radius:50%;display:inline-block;margin-right:5px;vertical-align:-1px}
  footer{color:var(--muted);font-size:12px;padding:14px 28px 26px;border-top:1px solid var(--line);background:#fff}
  @media (max-width:900px){.wrap{grid-template-columns:1fr}.mapbox{border-right:0;border-bottom:1px solid var(--line)}}
</style>
</head>
<body>
<header>
  <h1>InclusiveGo 感官示意地圖</h1>
  <div class="sub">17 個站點 · 四區 · 感官值 1–5，數值越低越適合感官敏感旅客。點擊站點查看細節。</div>
</header>

<div class="wrap">
  <div class="mapbox">
    <div class="controls" id="dims"></div>
    <div class="controls">
      <button class="chip ghost" id="routeBtn">顯示建議動線</button>
      <button class="chip ghost" id="fiveBtn">只顯示 5 級</button>
    </div>
    <svg id="map" viewBox="0 0 1180 1660" role="img" aria-label="海洋公園四區低密度示意地圖"></svg>
    <div class="legend">
      <span><i class="dot" style="background:var(--l1)"></i>1–2 低</span>
      <span><i class="dot" style="background:var(--l3)"></i>3 中</span>
      <span><i class="dot" style="background:var(--l5)"></i>4–5 高</span>
      <span>虛線＝按分區順序的示意動線，非實際步行路徑</span>
    </div>
  </div>
  <aside id="panel">
    <div class="panel-empty">
      點選任一站點，這裡會顯示該站的八維感官值、停留時間、步行分鐘、無障礙五欄與現場描述。<br><br>
      切換上方維度，可看出同一組站點在不同觸發條件下的差異——例如「聲音」多為 5 級、「人群」則分散在 1 與 5。
    </div>
  </aside>
</div>

<footer>
  資料來源：<code>data/facilities.json</code>（<code>point</code> 與 <code>walk_min</code> 同源）。此圖為版面示意，未按實際地理比例或方位；無障礙五欄目前皆為「未確認」，非「可通行」。
</footer>

<script>
const STATIONS = __DATA__;

const DIMS = [
  ["sound","聲音"],["light","光線"],["crowd","人群"],["enclosed","封閉感"],
  ["smell","氣味"],["cold","低溫"],["wet","濕滑"],["motion","動態"]
];
const ZONE_ORDER = ["正門外","夢幻水都","亞洲動物天地","威威天地"];
const LEVEL_NAME = {1:"低",2:"偏低",3:"中",4:"偏高",5:"高"};
const ACCESS_LABEL = {
  step_free:"無梯級通道", quiet_room:"安靜空間", queue_required:"需排隊",
  exit_ease:"離場容易度", staff_interaction:"職員互動"
};

let dim = "sound";
let onlyFive = false;
let showRoute = false;
let selected = null;

const svg = document.getElementById("map");

// 分區帶狀佈局：原座標的區間距離（海濱↔入口近 500px）在示意圖上沒有意義，
// 改為每區按站數分配高度、彼此只留 18 單位間隙；區內相對位置保留，等比壓縮。
const LAYOUT = (()=>{
  const out = {};
  let y = 30;
  // 依原始座標的南北向排序：山上的威威天地在上，入口的正門外在下
  const zoneByY = ZONE_ORDER
    .filter(z=>STATIONS.some(s=>s.zone===z))
    .map(z=>({z, y: Math.min(...STATIONS.filter(s=>s.zone===z).map(s=>s.point.y))}))
    .sort((a,b)=>a.y-b.y)
    .map(o=>o.z);
  zoneByY.forEach(zone=>{
    const pts = STATIONS.filter(s=>s.zone===zone);
    const minY = Math.min(...pts.map(p=>p.point.y));
    const maxY = Math.max(...pts.map(p=>p.point.y));
    const span = Math.max(maxY - minY, 60);
    const height = Math.max(126, pts.length * 34 + 58);
    out[zone] = {top:y, height, minY, span, scale:(height - 58) / span};
    y += height + 18;
  });
  out.__viewH = y + 20;
  return out;
})();

const gutterX = 176;
const gutterFont = 12.5;

function fy(s){
  const L = LAYOUT[s.zone];
  return L.top + 30 + (s.point.y - L.minY) * L.scale;
}
const panel = document.getElementById("panel");
const NS = "http://www.w3.org/2000/svg";

function colorFor(v){ return v >= 4 ? "var(--l5)" : v >= 3 ? "var(--l3)" : "var(--l1)"; }

function el(tag, attrs){
  const n = document.createElementNS(NS, tag);
  for (const k in attrs) n.setAttribute(k, attrs[k]);
  return n;
}

function drawDims(){
  const box = document.getElementById("dims");
  box.innerHTML = "";
  const all = [["all","全部站點"], ...DIMS];
  all.forEach(([key,label])=>{
    const b = document.createElement("button");
    b.className = "chip" + (key === (dim || "all") ? " on" : "");
    b.textContent = label;
    b.onclick = () => { dim = key === "all" ? null : key; drawDims(); render(); };
    box.appendChild(b);
  });
}

function render(){
  svg.innerHTML = "";
  svg.setAttribute("viewBox", `0 0 1180 ${LAYOUT.__viewH}`);

  // 區域色帶（帶狀佈局）
  ZONE_ORDER.forEach((zone, i)=>{
    const L = LAYOUT[zone];
    if (!L) return;
    const g = el("g", {});
    g.appendChild(el("rect", {x:150, y:L.top, width:860, height:L.height,
      rx:18, class:"zoneband" + (i%2 ? " alt":"")}));
    const t = el("text", {x:990, y:L.top+22, class:"zonelabel", "text-anchor":"end"});
    t.textContent = zone;
    g.appendChild(t);
    const shown = STATIONS.filter(s=>s.zone===zone && visible(s)).length;
    if (!shown) {
      const none = el("text", {x:580, y:L.top + L.height/2, "text-anchor":"middle",
        style:"font-size:12.5px;fill:#9aa8a3"});
      none.textContent = onlyFive ? "本區八維皆 ≤ 3，無 5 級站" : "此條件下本區無站點";
      g.appendChild(none);
    }
    svg.appendChild(g);
  });

  // 動線：同區內按 walk_min 排序，還原沿動線的實際先後
  const routeStations = ZONE_ORDER.flatMap(z =>
    STATIONS.filter(s=>s.zone===z && visible(s))
      .sort((a,b)=>a.walk_min-b.walk_min)
  );
  if (showRoute){
    const d = routeStations.map((s,i)=>
      (i? "L":"M") + s.point.x + " " + fy(s)
    ).join(" ");
    svg.appendChild(el("path", {d, class:"route"}));
    routeStations.forEach((s,i)=>{
      const g = el("g", {});
      const cy = fy(s) - 18;
      g.appendChild(el("circle", {cx:s.point.x+18, cy, r:9, fill:"#036356"}));
      const t = el("text", {x:s.point.x+18, y:cy+3.5, "text-anchor":"middle", class:"stepn"});
      t.textContent = (i+1);
      g.appendChild(t);
      svg.appendChild(g);
    });
  }

  // 站點
  STATIONS.forEach(s=>{
    if (!visible(s)) return;
    const v = valueOf(s);
    const g = el("g", {class:"node" + (selected === s.id ? " selected":""),
      "data-id": s.id});
    const cy = fy(s);
    g.appendChild(el("circle", {cx:s.point.x, cy, r:16,
      fill: colorFor(v), stroke:"#fff", "stroke-width":2}));
    const val = el("text", {x:s.point.x, y:cy+4.5, "text-anchor":"middle",
      style:"font-size:12px;fill:#fff;font-weight:600"});
    val.textContent = v;
    g.appendChild(val);
    g.appendChild(el("title", {})).textContent = s.name + "｜" + s.zone;
    g.onclick = () => { selected = s.id; render(); renderPanel(s); };
    svg.appendChild(g);
  });

  // 左側標籤：貼近站點自身高度，過近時向下錯開（最小 16px），引線連回站點
  ZONE_ORDER.forEach(zone=>{
    const b = LAYOUT[zone];
    if (!b) return;
    const pts = STATIONS.filter(s=>s.zone===zone && visible(s))
      .sort((a,c)=>a.point.y-c.point.y);
    if (!pts.length) return;
    let ly = b.top + 40;
    const rows = pts.map(st=>{
      ly = Math.max(fy(st), ly);
      const row = {st, ly};
      ly += 20;
      return row;
    });
    const overflow = rows[rows.length-1].ly - (b.bottom - 12);
    if (overflow > 0) rows.forEach(r=>{ r.ly -= overflow; });

    rows.forEach(({st, ly})=>{
      const tw = st.name.length * gutterFont;
      svg.appendChild(el("line", {x1:gutterX+tw+5, y1:ly-4, x2:st.point.x-16, y2:fy(st),
        stroke:"#c6d4cf", "stroke-width":1}));
      const t = el("text", {x:gutterX, y:ly, style:`font-size:${gutterFont}px;fill:#25332f`});
      t.textContent = st.name;
      svg.appendChild(t);
    });
  });
}

function valueOf(s){
  return dim ? s.sensory[dim] : Math.max(...Object.values(s.sensory));
}

function visible(s){
  return !onlyFive || valueOf(s) >= 4;
}

function bar(v){
  const w = v * 14;
  return `<span class="bar" style="width:${w}px;background:${v>=4?"var(--l5)":v>=3?"var(--l3)":"var(--l1)"}"></span>`;
}

function renderPanel(s){
  const rows = DIMS.map(([k,label])=>
    `<tr><td>${label}</td><td class="num">${s.sensory[k]}　${LEVEL_NAME[s.sensory[k]]}${bar(s.sensory[k])}</td></tr>`
  ).join("");

  const accessRows = Object.keys(ACCESS_LABEL).map(k=>{
    const val = s.access ? s.access[k] : null;
    return `<tr><td>${ACCESS_LABEL[k]}</td><td><span class="pill">${val === null ? "未確認" : val}</span></td></tr>`;
  }).join("");

  panel.innerHTML = `
    <h2>${s.name}</h2>
    <div class="meta">${s.zone} · 停留 ${s.duration.min}–${s.duration.max} 分鐘${s.duration.approx ? "（約）":""} · 園內累計步行 ${s.walk_min} 分鐘</div>
    <table><tbody>${rows}</tbody></table>
    <div class="story"><b>我會經歷什麼</b>${s.story.experience}</div>
    <div class="story"><b>可以先準備</b>${s.story.prep}</div>
    <table><thead><tr><th>無障礙資訊</th><th>狀態</th></tr></thead><tbody>${accessRows}</tbody></table>
    <div class="meta">無障礙五欄尚未現場採集，一律顯示「未確認」。這裡的「未確認」不是「可通行」。</div>
  `;
}

document.getElementById("routeBtn").onclick = (e)=>{
  showRoute = !showRoute;
  e.currentTarget.classList.toggle("on", showRoute);
  e.currentTarget.textContent = showRoute ? "隱藏建議動線" : "顯示建議動線";
  render();
};

document.getElementById("fiveBtn").onclick = (e)=>{
  onlyFive = !onlyFive;
  e.currentTarget.classList.toggle("on", onlyFive);
  render();
};

drawDims();
render();
</script>
</body>
</html>
"""


def main() -> None:
    payload = json.loads(DATA.read_text(encoding="utf-8"))
    stations = payload["facilities"]
    slim = [
        {
            "id": s["id"],
            "name": s["name"],
            "zone": s["zone"],
            "duration": s["duration"],
            "sensory": s["sensory"],
            "story": s.get("story", {}),
            "point": s["point"],
            "access": s.get("access", {}),
            "walk_min": s.get("walk_min", 0),
        }
        for s in stations
    ]
    data_js = json.dumps(slim, ensure_ascii=False, separators=(",", ":"))
    OUT.write_text(TEMPLATE.replace("__DATA__", data_js), encoding="utf-8")
    print(f"已寫入 {OUT.relative_to(ROOT)}：{len(slim)} 站，{OUT.stat().st_size} bytes")


if __name__ == "__main__":
    main()
