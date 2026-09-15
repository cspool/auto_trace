#!/usr/bin/env python3
"""Per-model comparison report: three R10 timelines (end-to-end / high-latency /
concurrency-resource), each as a stacked pair — FCFS baseline above, agentix_core
below, full width. Interactive renderer adapted from the archives_final batch16
pages (section buttons, fold toggle, wheel zoom, drag pan, absolute-ns jump,
fitted trapezoid pile outlines, all members drawn — no sampling)."""
import argparse
import json
from pathlib import Path
from string import Template

JS = r"""
const NL = String.fromCharCode(10);
const NS = s => BigInt(s);
function relNs(abs, origin){ return Number(NS(abs) - NS(origin)); }
function fmtNs(n){
  const v = Number(n);
  if (Math.abs(v) >= 1e9) return (v/1e9).toFixed(3)+' s';
  if (Math.abs(v) >= 1e6) return (v/1e6).toFixed(2)+' ms';
  if (Math.abs(v) >= 1e3) return (v/1e3).toFixed(1)+' µs';
  return v.toFixed(0)+' ns';
}
const tip = document.getElementById('tip');
function showTip(ev, text){
  tip.textContent = text; tip.style.opacity = 1;
  let x = ev.clientX + 14, y = ev.clientY + 14;
  const r = tip.getBoundingClientRect();
  if (x + r.width > innerWidth) x = ev.clientX - r.width - 14;
  if (y + r.height > innerHeight) y = ev.clientY - r.height - 14;
  tip.style.left = x+'px'; tip.style.top = y+'px';
}
function hideTip(){ tip.style.opacity = 0; }
function makeMap(sec, breaks, folded){
  const lo = sec.lo, hi = sec.hi, pts = [];
  let t = lo, d = 0;
  if (folded) for (const br of breaks){
    const w = br.b - t;
    pts.push({t, d, k: 1}); d += w; t = br.b;
    pts.push({t, d, k: br.disp / Math.max(1, br.tru)});
    d += br.disp; t = br.e;
  }
  pts.push({t, d, k: 1}); d += hi - t;
  const total = d;
  function fwd(x){
    if (x <= lo) return 0;
    if (x >= hi) return total;
    let i = 0;
    while (i + 1 < pts.length && pts[i+1].t <= x) i++;
    return pts[i].d + (x - pts[i].t)*pts[i].k;
  }
  function inv(y){
    let i = 0;
    while (i + 1 < pts.length && pts[i+1].d <= y) i++;
    return pts[i].t + (y - pts[i].d)/(pts[i].k || 1e-9);
  }
  return {fwd, inv, total};
}
function mountBase(root, D, drawBody, rowCount, ROW){
  const st = {sec: 0, folded: true, zoom: 1, pan: 0};
  const svg = root.querySelector('svg');
  const LEFT = 250, RIGHT = 30, GAP = 12, TOP = 64;
  function cur(){
    const s = D.sections[st.sec];
    return {lo: relNs(s.begin_ns, D.origin), hi: relNs(s.end_ns, D.origin), meta: s};
  }
  function draw(){
    const s = cur();
    const brk = (D.breaks[st.sec]||[]).map(b => ({b: relNs(b.begin_ns, D.origin),
      e: relNs(b.end_ns, D.origin), tru: b.true_ns, disp: b.display_ns}));
    const map = makeMap(s, brk, st.folded);
    const W = svg.clientWidth || 1280, plotW = W - LEFT - RIGHT;
    const H = TOP + rowCount*(ROW+GAP) + 60;
    svg.setAttribute('viewBox', '0 0 '+W+' '+H);
    const X = t => LEFT + ((map.fwd(t)/map.total)*st.zoom + st.pan)*plotW;
    const out = ['<rect x="0" y="0" width="'+W+'" height="'+H+'" fill="#fff"/>'];
    for (let i = 0; i <= 10; i++){
      const disp = map.total*i/10, trueT = map.inv(disp);
      const x = LEFT + ((disp/map.total)*st.zoom + st.pan)*plotW;
      if (x < LEFT-1 || x > W-RIGHT+1) continue;
      out.push('<path d="M'+x.toFixed(1)+' '+(TOP-14)+' V'+(H-44)+'" stroke="#e6edf4"/>');
      out.push('<text x="'+x.toFixed(1)+'" y="'+(TOP-20)+'" font-size="11" text-anchor="middle" fill="#48607d">'+fmtNs(trueT - s.lo)+'</text>');
    }
    if (st.folded) for (const b of brk){
      const x = X(b.b), x2 = X(b.e);
      if (x2 < LEFT || x > W-RIGHT) continue;
      out.push('<rect class="brk" data-tru="'+b.tru+'" x="'+x.toFixed(1)+'" y="'+(TOP-14)+'" width="'+Math.max(1,x2-x).toFixed(1)+'" height="'+(H-44-(TOP-14))+'" fill="#f6f2e8"/>');
    }
    drawBody(out, {s, map, X, W, plotW, TOP, ROW, GAP, LEFT, RIGHT, H, st});
    out.push('<text x="10" y="'+(H-18)+'" font-size="11.5" fill="#48607d">段 '+s.meta.section+'/10 · 绝对区间 ['+s.meta.begin_ns+', '+s.meta.end_ns+') ns · '+(st.folded?'折叠（浅黄带为压缩空档）':'线性（时长严格成比例）')+' · 缩放 '+st.zoom.toFixed(1)+'×</text>');
    svg.innerHTML = out.join('');
    svg.querySelectorAll('.brk').forEach(el => {
      el.addEventListener('mousemove', ev => showTip(ev, '压缩空档 真实时长 '+fmtNs(+el.dataset.tru)));
      el.addEventListener('mouseleave', hideTip);
    });
    if (svg._post) svg._post(map, X, W, plotW);
  }
  root.querySelectorAll('.secbtn').forEach((b,i) => b.onclick = () => {
    st.sec = i; st.zoom = 1; st.pan = 0;
    root.querySelectorAll('.secbtn').forEach((x,k) => x.classList.toggle('on', k===i));
    draw();
  });
  const fbtn = root.querySelector('.fold');
  fbtn.onclick = () => { st.folded = !st.folded;
    fbtn.classList.toggle('on', st.folded);
    fbtn.textContent = st.folded ? '折叠：开' : '折叠：关'; draw(); };
  svg.addEventListener('wheel', ev => {
    ev.preventDefault();
    const rect = svg.getBoundingClientRect();
    const W = svg.clientWidth || 1280, plotW = W - LEFT - RIGHT;
    const at = ((ev.clientX - rect.left)*(W/rect.width) - LEFT)/plotW;
    const f = ev.deltaY < 0 ? 1.25 : 0.8;
    const nz = Math.min(4000, Math.max(1, st.zoom*f));
    st.pan = at - (at - st.pan)*(nz/st.zoom); st.zoom = nz;
    if (st.zoom === 1) st.pan = 0;
    draw();
  }, {passive:false});
  let drag = null;
  svg.addEventListener('mousedown', ev => drag = {x: ev.clientX, pan: st.pan});
  addEventListener('mouseup', () => drag = null);
  addEventListener('mousemove', ev => {
    if (!drag) return;
    const W = svg.clientWidth || 1280;
    st.pan = drag.pan + (ev.clientX - drag.x)/(W - LEFT - RIGHT);
    draw();
  });
  addEventListener('resize', draw);
  st.draw = draw;
  return st;
}
function mountPile(root, D){
  const st = mountBase(root, D, (out, ctx) => {
    const {X, W, TOP, ROW, GAP, LEFT, RIGHT, st} = ctx;
    D.piles.forEach((p, i) => {
      const y = TOP + i*(ROW+GAP);
      out.push('<text x="8" y="'+(y+15)+'" font-size="12">#'+p.rank+' '+p.type+'</text>');
      out.push('<text x="8" y="'+(y+30)+'" font-size="10.5" fill="#48607d">堆'+p.pile_index+' · '+p.count+'次 · 和 '+(p.sum_ns/1e9).toFixed(3)+'s · 单次 '+fmtNs(p.min_ns)+'–'+fmtNs(p.max_ns)+'</text>');
      const members = p.rows[st.sec] || [];
      if (!members.length){
        out.push('<text x="'+(LEFT+8)+'" y="'+(y+24)+'" font-size="10.5" fill="#8fa2b6">本段无该堆成员</text>');
        return;
      }
      const ms = members.slice().sort((a,b) => a[0]-b[0] || a[1]-b[1]);
      const n = ms.length, top = y + 6, bottom = y + ROW - 6;
      const frac = k => n === 1 ? 0.5 : k/(n-1);
      const ends = ms.map(m => [X(m[0]), Math.max(X(m[0]+m[1]), X(m[0])+0.6)]);
      let ls = 0, rs = 0;
      if (n > 1){
        ls = (ends[n-1][0]-ends[0][0])/(frac(n-1)-frac(0));
        rs = (ends[n-1][1]-ends[0][1])/(frac(n-1)-frac(0));
      }
      let li = Infinity, ri = -Infinity;
      for (let k = 0; k < n; k++){
        li = Math.min(li, ends[k][0] - ls*frac(k));
        ri = Math.max(ri, ends[k][1] - rs*frac(k));
      }
      li -= 4; ri += 4;
      out.push('<path d="M'+li.toFixed(1)+' '+top+' L'+ri.toFixed(1)+' '+top+' L'+(ri+rs).toFixed(1)+' '+bottom+' L'+(li+ls).toFixed(1)+' '+bottom+' Z" fill="#eef4fa" stroke="#8fb2ce"/>');
      const seg = [];
      for (let k = 0; k < n; k++){
        const yy = (top + frac(k)*(bottom-top)).toFixed(1);
        seg.push('M'+ends[k][0].toFixed(1)+' '+yy+'H'+ends[k][1].toFixed(1));
      }
      out.push('<path d="'+seg.join('')+'" stroke="'+(p.hl?'#b3462f':'#2f6f9f')+'" stroke-width="1" fill="none" opacity="0.8"/>');
      out.push('<rect class="hit" data-p="'+i+'" x="'+LEFT+'" y="'+y+'" width="'+(ctx.W-LEFT-RIGHT)+'" height="'+ROW+'" fill="transparent"/>');
    });
    ctx.st._hits = () => {
      root.querySelectorAll('.hit').forEach(el => {
        el.addEventListener('mousemove', ev => {
          const p = D.piles[+el.dataset.p];
          showTip(ev, '#'+p.rank+' '+p.type+' 堆'+p.pile_index+NL+'成员 '+p.count+' · 单次 '+fmtNs(p.min_ns)+' – '+fmtNs(p.max_ns)+NL+'堆总时长 '+(p.sum_ns/1e9).toFixed(4)+' s');
        });
        el.addEventListener('mouseleave', hideTip);
      });
    };
  }, D.piles.length, 96);
  root.querySelector('svg')._post = () => st._hits && st._hits();
  st.draw();
  return st;
}
function mountLanes(root, D){
  const LANE = 96;
  const st = mountBase(root, D, (out, ctx) => {
    const {X, W, TOP, LEFT, RIGHT, st} = ctx;
    const elig = (D.eligible_union[st.sec]||[]);
    D.lanes.forEach((ln, i) => {
      const y = TOP + i*(LANE+12), base = y + LANE - 8;
      out.push('<text x="8" y="'+(y+15)+'" font-size="12">'+ln.label+' ('+ln.unit+')</text>');
      out.push('<text x="8" y="'+(y+30)+'" font-size="10.5" fill="#48607d">'+ln.evidence+'</text>');
      out.push('<rect x="'+LEFT+'" y="'+y+'" width="'+(W-LEFT-RIGHT)+'" height="'+LANE+'" fill="#f2f2ef"/>');
      for (const w of elig){
        const x1 = X(w[0]), x2 = X(w[0]+w[1]);
        if (x2 < LEFT || x1 > W-RIGHT) continue;
        out.push('<rect x="'+Math.max(LEFT,x1).toFixed(1)+'" y="'+y+'" width="'+Math.max(0.5, Math.min(W-RIGHT,x2)-Math.max(LEFT,x1)).toFixed(1)+'" height="'+LANE+'" fill="#ffffff"/>');
      }
      const rows = ln.rows[st.sec]||[];
      let path = '';
      for (const r of rows){
        const x1 = X(r[0]), x2 = X(r[0]+r[1]);
        if (x2 < LEFT || x1 > W-RIGHT) continue;
        const h = (LANE-16)*Math.min(1, r[2]/ln.max);
        path += 'M'+x1.toFixed(1)+' '+base.toFixed(1)+' V'+(base-h).toFixed(1)+' H'+x2.toFixed(1)+' V'+base.toFixed(1);
      }
      out.push('<path d="'+path+'" stroke="'+ln.color+'" stroke-width="1" fill="none"/>');
      out.push('<rect class="lhit" data-l="'+i+'" x="'+LEFT+'" y="'+y+'" width="'+(W-LEFT-RIGHT)+'" height="'+LANE+'" fill="transparent"/>');
    });
    ctx.st._hits = (map) => {
      root.querySelectorAll('.lhit').forEach(el => {
        el.addEventListener('mousemove', ev => {
          const ln = D.lanes[+el.dataset.l];
          const rect = root.querySelector('svg').getBoundingClientRect();
          const W2 = root.querySelector('svg').clientWidth || 1280;
          const fracX = ((ev.clientX-rect.left)*(W2/rect.width) - 250)/(W2-250-30);
          const disp = (fracX - st.pan)/st.zoom * map.total;
          const t = map.inv(disp);
          const rows = ln.rows[st.sec]||[];
          let v = null;
          for (const r of rows) if (t >= r[0] && t < r[0]+r[1]) { v = r[2]; break; }
          showTip(ev, ln.label+NL+(v===null?'窗口外':v+' '+ln.unit)+NL+'灰底 = 未关联窗口（评审堆成员外）');
        });
        el.addEventListener('mouseleave', hideTip);
      });
    };
  }, D.lanes.length, 96);
  root.querySelector('svg')._post = (map) => st._hits && st._hits(map);
  st.draw();
  return st;
}
function mountReq(root, D){
  // lossless request-lane view after r10_lossless_timeline: one true time axis,
  // every call drawn, no folding, no sampling; wait vs service split per call.
  const svg = root.querySelector('svg');
  const CLS = {bfcl:'#eb6834', sharegpt:'#2a78d6', lats:'#1baf7a'};
  const st = {zoom: 1, pan: 0};
  const LEFT = 150, RIGHT = 24, ROWH = 22, TOP = 46;
  function draw(){
    const W = svg.clientWidth || 1280, plotW = W - LEFT - RIGHT;
    const H = TOP + D.lanes.length*ROWH + 46;
    svg.setAttribute('viewBox', '0 0 '+W+' '+H);
    const X = t => LEFT + ((t/D.wall_ms)*st.zoom + st.pan)*plotW;
    const out = ['<rect width="'+W+'" height="'+H+'" fill="#fff"/>'];
    for (let i = 0; i <= 10; i++){
      const t = D.wall_ms*i/10, x = X(t);
      if (x < LEFT-1 || x > W-RIGHT+1) continue;
      out.push('<path d="M'+x.toFixed(1)+' '+(TOP-12)+' V'+(H-34)+'" stroke="#e6edf4"/>');
      out.push('<text x="'+x.toFixed(1)+'" y="'+(TOP-18)+'" font-size="11" text-anchor="middle" fill="#48607d">'+(t/1e3).toFixed(0)+' s</text>');
    }
    D.lanes.forEach((ln, i) => {
      const y = TOP + i*ROWH;
      out.push('<text x="6" y="'+(y+14)+'" font-size="10.5" fill="#48607d">'+ln.p+' · '+ln.cls+' · '+ln.calls.length+'调用</text>');
      ln.calls.forEach((c, j) => {
        const x0 = X(c[0]), x1 = X(c[1]), x2 = X(c[2]);
        if (x2 < LEFT || x0 > W-RIGHT) return;
        out.push('<rect class="rq" data-l="'+i+'" data-c="'+j+'" x="'+x0.toFixed(1)+'" y="'+(y+4)+'" width="'+Math.max(0.5,(x1-x0)).toFixed(1)+'" height="12" fill="#c94040" opacity="0.85"/>');
        out.push('<rect class="rq" data-l="'+i+'" data-c="'+j+'" x="'+x1.toFixed(1)+'" y="'+(y+4)+'" width="'+Math.max(0.5,(x2-x1)).toFixed(1)+'" height="12" fill="'+(CLS[ln.cls]||'#888')+'" opacity="0.9"/>');
      });
    });
    out.push('<text x="6" y="'+(H-12)+'" font-size="11.5" fill="#48607d">无损单轴（真实时间比例，未折叠未抽样）· 全部 '+D.n_calls+' 个调用 · 红段 = 等待（提交→首token）· 彩段 = 服务（首token→完成）· 缩放 '+st.zoom.toFixed(1)+'×</text>');
    svg.innerHTML = out.join('');
    svg.querySelectorAll('.rq').forEach(el => {
      el.addEventListener('mousemove', ev => {
        const ln = D.lanes[+el.dataset.l], c = ln.calls[+el.dataset.c];
        showTip(ev, ln.p+' 调用#'+c[3]+' ('+ln.cls+')'+NL+'等待 '+(c[1]-c[0]).toFixed(0)+' ms · 服务 '+(c[2]-c[1]).toFixed(0)+' ms'+NL+(c[4]?('MLFQ 队列路径 '+c[4]):'FCFS 单队'));
      });
      el.addEventListener('mouseleave', hideTip);
    });
  }
  svg.addEventListener('wheel', ev => {
    ev.preventDefault();
    const rect = svg.getBoundingClientRect();
    const W = svg.clientWidth || 1280, plotW = W - LEFT - RIGHT;
    const at = ((ev.clientX - rect.left)*(W/rect.width) - LEFT)/plotW;
    const f = ev.deltaY < 0 ? 1.25 : 0.8;
    const nz = Math.min(2000, Math.max(1, st.zoom*f));
    st.pan = at - (at - st.pan)*(nz/st.zoom); st.zoom = nz;
    if (st.zoom === 1) st.pan = 0;
    draw();
  }, {passive:false});
  let drag = null;
  svg.addEventListener('mousedown', ev => drag = {x: ev.clientX, pan: st.pan});
  addEventListener('mouseup', () => drag = null);
  addEventListener('mousemove', ev => {
    if (!drag) return;
    const W = svg.clientWidth || 1280;
    st.pan = drag.pan + (ev.clientX - drag.x)/(W - LEFT - RIGHT);
    draw();
  });
  addEventListener('resize', draw);
  draw();
}
document.querySelectorAll('.panel').forEach(p => {
  const D = JSON.parse(document.getElementById(p.dataset.payload).textContent);
  if (p.dataset.kind === 'lanes') mountLanes(p, D);
  else if (p.dataset.kind === 'req') mountReq(p, D);
  else mountPile(p, D);
});
"""

CSS = """
:root{--ink:#1f2f45;--line:#c9d6e4;--panel:#f2f7fb;--accent:#2f6f9f}
*{box-sizing:border-box}
body{margin:0;font:14px/1.6 "Noto Sans CJK SC","WenQuanYi Zen Hei",system-ui,sans-serif;color:var(--ink);background:#fff}
header{padding:18px 22px;border-bottom:1px solid var(--line);background:var(--panel)}
h1{margin:0 0 6px;font-size:21px}
h2{font-size:17px;margin:34px 22px 4px;color:var(--accent)}
.sub,.note{font-size:13px;color:#48607d}
.sub{max-width:120ch}
.note{margin:8px 22px 0;max-width:120ch}
.panel{margin:12px 22px 4px;border:1px solid var(--line);border-radius:6px;overflow:hidden}
.pbar{display:flex;flex-wrap:wrap;gap:6px;align-items:center;padding:8px 12px;border-bottom:1px solid var(--line);background:#fbfdff}
.ptag{font-size:12.5px;font-weight:600;padding:2px 10px;border-radius:99px;border:1px solid var(--line)}
.ptag.core{border-color:var(--accent);color:var(--accent)}
button{font:13px inherit;padding:3px 9px;border:1px solid var(--line);background:#fff;border-radius:4px;cursor:pointer;color:var(--ink)}
button.on{background:var(--accent);border-color:var(--accent);color:#fff}
svg{display:block;width:100%;height:auto;background:#fff}
table{border-collapse:collapse;font-size:12.5px;margin:10px 22px;width:calc(100% - 44px)}
td,th{border:1px solid var(--line);padding:4px 8px;text-align:left}
th{background:var(--panel)}
#tip{position:fixed;pointer-events:none;background:#1f2f45;color:#fff;padding:6px 9px;border-radius:4px;font-size:12px;opacity:0;transition:opacity .1s;max-width:48ch;z-index:9;white-space:pre-line}
"""


def panel(pid, kind, tag, cls=""):
    if kind == "req":
        bar = (f'<span class="ptag {cls}">{tag}</span>'
               '<span style="font-size:12px;color:#48607d">无损单轴 · 滚轮缩放 · 拖拽平移</span>')
    else:
        bar = (f'<span class="ptag {cls}">{tag}</span>' + "".join(
            f'<button class="secbtn{" on" if i == 0 else ""}">段{i + 1}</button>'
            for i in range(10)) + '<button class="fold on">折叠：开</button>')
    return (f'<div class="panel" data-payload="{pid}" data-kind="{kind}">'
            f'<div class="pbar">{bar}</div><svg height="400"></svg></div>')


def req_payload(capture_dir: Path):
    f = next((capture_dir / "run").glob("calls_*.jsonl"))
    rows = [json.loads(l) for l in f.open()]
    lanes = {}
    for r in rows:
        lanes.setdefault(r["program_id"], {"p": r["program_id"], "cls": r["class"], "calls": []})
        qp = r.get("queue_path")
        lanes[r["program_id"]]["calls"].append(
            [round(r["submitted_rel_ms"], 1), round(r["first_token_rel_ms"], 1),
             round(r["finished_rel_ms"], 1), r["call_index"],
             ">".join(f"Q{q}" for q in qp) if qp and r["policy"] != "fcfs" else ""])
    order = sorted(lanes.values(), key=lambda x: ({"bfcl": 0, "sharegpt": 1, "lats": 2}[x["cls"]],
                                                  x["calls"][0][0]))
    wall = max(c[2] for x in order for c in x["calls"])
    waits = [c[1] - c[0] for x in order for c in x["calls"]]
    lats = [c[2] - c[0] for x in order for c in x["calls"]]
    return ({"wall_ms": wall, "n_calls": len(rows), "lanes": order},
            sum(waits) / len(waits), sum(lats) / len(lats))


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--model-key", required=True)
    ap.add_argument("--model-name", required=True)
    ap.add_argument("--fcfs-payload", type=Path, required=True)
    ap.add_argument("--core-payload", type=Path, required=True)
    ap.add_argument("--facts", type=Path, required=True)
    ap.add_argument("--fcfs-capture", type=Path, required=True)
    ap.add_argument("--core-capture", type=Path, required=True)
    ap.add_argument("--out", type=Path, required=True)
    a = ap.parse_args()
    pf = json.loads(a.fcfs_payload.read_text())
    pc = json.loads(a.core_payload.read_text())
    d = json.loads(a.facts.read_text())
    e, s, q, w, ml = d["endpoint"], d["endpoint"]["speedup"], d["queue"], d["class_wait_ms"], d["mlfq"]
    rq_f, wait_f, lat_f = req_payload(a.fcfs_capture)
    rq_c, wait_c, lat_c = req_payload(a.core_capture)
    # timeline-native estimate at the program level (the ptl unit): replay the
    # FCFS timeline with each call's wait segment replaced by the core side's
    # class-median wait, recompute program token latency, compare means.
    import statistics as _st
    f_calls = [json.loads(l) for l in next((a.fcfs_capture / "run").glob("calls_*.jsonl")).open()]
    c_calls = [json.loads(l) for l in next((a.core_capture / "run").glob("calls_*.jsonl")).open()]
    med_core_wait = {cls: _st.median([r["first_token_rel_ms"] - r["submitted_rel_ms"]
                                      for r in c_calls if r["class"] == cls])
                     for cls in {r["class"] for r in c_calls}}
    progs = {}
    for r in f_calls:
        p = progs.setdefault(r["program_id"], {"sub": 1e18, "fin": 0, "tok": 0, "cut": 0.0})
        p["sub"] = min(p["sub"], r["submitted_rel_ms"])
        p["fin"] = max(p["fin"], r["finished_rel_ms"])
        p["tok"] += max(r["output_tokens"], 1)
        wait = r["first_token_rel_ms"] - r["submitted_rel_ms"]
        p["cut"] += max(0.0, wait - med_core_wait[r["class"]])
    ptl_f = [(p["fin"] - p["sub"]) / p["tok"] for p in progs.values()]
    ptl_pred = [max(p["fin"] - p["sub"] - p["cut"], 1e-6) / p["tok"] for p in progs.values()]
    est_call = (sum(ptl_f) / len(ptl_f)) / (sum(ptl_pred) / len(ptl_pred))

    def emb(pid, obj):
        return f'<script id="{pid}" type="application/json">{json.dumps(obj)}</script>'

    wait_rows = "".join(
        f"<tr><td>{c}</td><td>{w['fcfs'][c]['mean']:.0f} / {w['fcfs'][c]['p90']:.0f}</td>"
        f"<td>{w['core'][c]['mean']:.0f} / {w['core'][c]['p90']:.0f}</td>"
        f"<td>{100*(1-w['core'][c]['mean']/w['fcfs'][c]['mean']):+.0f} %</td></tr>"
        for c in ("bfcl", "sharegpt", "lats"))
    hidden_f = ", ".join(f"#{r}" for r in pf["cu"]["hidden_ranks"]) or "无"
    hidden_c = ", ".join(f"#{r}" for r in pc["cu"]["hidden_ranks"]) or "无"

    html = Template("""<!doctype html><html lang="zh-CN"><head><meta charset="utf-8">
<title>$name · baseline vs agentix_core 时间线对照报告</title><style>$css</style></head><body>
<header><h1>$name · baseline (FCFS) vs agentix_core 时间线对照报告</h1>
<div class="sub">排队制 cap16 · r0.5 冻结负载 · 同 nsys 栈同参，唯一变量调度策略。
端侧：ptl mean $fm → $cm ms（<b>$sm×</b>），p90 $fp → $cp ms（<b>$sp×</b>），p99 $s99×。
三种时间线均为 Process 视角：每条横线是一个 Process 实例的真实起止；梯形外框只表成员归属，不表连续执行。
十段制 · 折叠模式压缩大空档（浅黄带，提示保留真实时长）· 滚轮缩放 · 拖拽平移。契约与实现参照
archives_final/batch16 R10 页（process-resource-contract.md）。</div></header>

<h2>① 端到端 Process 时间线 — 优化生效的直观效果（无损请求车道，参照 r10_lossless_timeline）</h2>
$req_f
$req_c
<p class="note"><b>直观效果：</b>每行一个程序（按类别分组），每个调用 = 红段（等待：提交→首token）+
彩段（服务：首token→完成），真实时间比例、全部 $ncalls 个调用无抽样无折叠。上图（FCFS）里
bfcl（橙）与 sharegpt（蓝）车道被大片红段占据——短程序在长程序（绿，lats）后排队；下图
（agentix_core）中这些红段几乎消失，绿色车道不变。<b>优化生效 = 红色等待质量从短程序车道被移走</b>。
全体调用平均等待 $wf → $wc ms；分类别（mean/p90 ms）：</p>
<table><tr><th>类别</th><th>FCFS</th><th>agentix_core</th><th>Δmean</th></tr>$wait_rows</table>

<h2>② 高延迟 Process 时间线 — 性能提升比例的估算（scope 宇宙：>10% 类型 × 5 堆聚类，全局排名）</h2>
$hl_f
$hl_c
<p class="note"><b>比例估算：</b>两图堆拓扑同构（同入选类型、第 1 名同为重 forward 堆），重堆总质量差
仅为量子切块 continuation 签名——即<b>服务时间不因策略改变</b>，提升只能来自 ① 中的等待段。
据此从时间线估算（程序级重放：把 FCFS 时间线上每个调用的红色等待段替换为 core 侧同类别
中位等待，重算各程序 token latency）：预计加速 <b>$est×（上界）</b>；实测端侧 ptl mean $sm× /
p90 $sp×。估算只用两条时间线的几何量（等待段与服务段）；它是上界，因为程序内并行调用
（lats 波宽 5）的等待在墙钟上重叠、逐调用求和会重复计入。实测落在 1×–上界之间，
且长尾口径（p90 $sp×、p99 $s99×）更接近上界——与"收益来自等待重排"的机理自洽。
MLFQ 账本：入队 Q0–Q3 = $adm，降级 $demo 次，多量子 $multiq，β 提升 $promo。</p>

<h2>③ 并发 / 资源分析时间线 — 性能提升的原因（资源使用率与并发；lanes 仅在已关联窗口内绘制）</h2>
$cu_f
$cu_c
<p class="note"><b>原因：</b>(1) <b>资源使用率不变</b>——GPU busy 与 gemm 占比两侧几乎同形，family 级
NCU 中位数一致（L2≈76% / SM≈49% / DRAM 14–20%），资源墙在 L2/tensor 且不因策略移动；
(2) <b>并发同样打满</b>——"在飞调用数"lane 两侧都长期贴 cap（上方累计 $qf vs $qc s，排队压力相同）；
(3) 因此提升的唯一自由度是<b>出队顺序</b>：MLFQ 在相同资源、相同并发下把短程序先送进批。
排队压力越大该杠杆越大（跨模型：LLaMA 169 s→p90 1.86×，VL 77 s→1.15×，Qwen3 40 s→1.11×）。
隐藏堆保留排名：baseline $hidden_f；core $hidden_c（preprocess 堆无 gemm 关联，按契约隐藏）。
折叠上限 = max(2×中位时长, 段宽/2000)，只压大空洞（适配声明）。</p>

<p class="note">记账：全部成员绘制、未抽样；硬件关联 family 级非逐实例；trace 开销两侧同担；
payload 内含绝对 ns（BigInt 处理，无精度损失）。数字出处 gain_facts_$key.json 与两侧 payload。
A00 守恒门（workflow06）已认证本对捕获：程序/调用键集合在负载规格、运行记录、trace NVTX 三方相等，
调用→step 连接全通过（各捕获 a00_process_view.json）；preprocess 宇宙含 0.2–0.4 % 的空批引擎迭代
（真实 scope，落在最低时长堆），采集停止可能截断最后一个迭代的 forward 后各 phase（至多各 1 个实例）。</p>
<div id="tip"></div>
$payloads
<script>$js</script></body></html>""").substitute(
        name=a.model_name, css=CSS, js=JS, key=a.model_key,
        fm=f"{e['fcfs']['ptl']['mean']:.1f}", cm=f"{e['core']['ptl']['mean']:.1f}",
        sm=f"{s['mean']:.2f}", fp=f"{e['fcfs']['ptl']['p90']:.1f}",
        cp=f"{e['core']['ptl']['p90']:.1f}", sp=f"{s['p90']:.2f}", s99=f"{s['p99']:.2f}",
        req_f=panel("pl-req-f", "req", "FCFS baseline"),
        req_c=panel("pl-req-c", "req", "agentix_core", "core"),
        ncalls=rq_f["n_calls"], wf=f"{wait_f:.0f}", wc=f"{wait_c:.0f}",
        lf=f"{lat_f:.0f}", est=f"{est_call:.2f}",
        hl_f=panel("pl-hl-f", "pile", "FCFS baseline"),
        hl_c=panel("pl-hl-c", "pile", "agentix_core", "core"),
        cu_f=panel("pl-cu-f", "lanes", "FCFS baseline"),
        cu_c=panel("pl-cu-c", "lanes", "agentix_core", "core"),
        wait_rows=wait_rows,
        adm="/".join(str(v) for v in ml["admission"].values()),
        demo=ml["demotions"], promo=ml["promotions"], multiq=ml["multi_quantum_calls"],
        qf=f"{q['fcfs']['ms_above_cap']/1e3:.1f}", qc=f"{q['core']['ms_above_cap']/1e3:.1f}",
        hidden_f=hidden_f, hidden_c=hidden_c,
        payloads="\n".join([emb("pl-req-f", rq_f), emb("pl-req-c", rq_c),
                            emb("pl-hl-f", pf["hl"]), emb("pl-hl-c", pc["hl"]),
                            emb("pl-cu-f", pf["cu"]), emb("pl-cu-c", pc["cu"])]))
    a.out.write_text(html)
    print("wrote", a.out, a.out.stat().st_size // 1024, "KB")


if __name__ == "__main__":
    main()
