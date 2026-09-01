#!/usr/bin/env python3
"""Build a self-contained R10 report for the sealed R09 observed subset."""

from __future__ import annotations

import argparse
import csv
import hashlib
import html
import json
import os
import re
import shutil
import time
from collections import Counter, defaultdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable


RUN_ID = "batch8-dp2-fresh-003"
LINEAGE_ID = RUN_ID
TRACE_PROFILE_SHA256 = "3b4c952063f48ae662b48b5ce9d8fd76e0ac4d74e170bdb1839ae8b1aaa23cce"
RUN_ROOT = Path(
    "/public/home/tangyu408/Qwen_DCU_Worker_0/perf_trace_batch8/runtime/"
    f"workflow01-10-fresh-e2e/{RUN_ID}"
)
R09_ROOT = RUN_ROOT / "artifacts/R09/degraded_observed_subset_001"
R09_ANALYSIS = R09_ROOT / "analysis/fresh_e2e_analysis.json"
R09_COMPLETE = R09_ROOT / "R09_DEGRADED_ANALYSIS_COMPLETE.json"
R09_LINEAGE = R09_ROOT / "lineage/R09_SOURCE_LINEAGE.json"
R08_HANDOFF = RUN_ROOT / "artifacts/R08/observed_subset_replay_001/normalized_003/R08_DEGRADED_HANDOFF.json"
R07_LINEAGE = RUN_ROOT / "artifacts/R07/recovery/db_first_postprocess_001/lineage/DB_FIRST_R07_SOURCE_LINEAGE.json"

TABLE_ROOT = R09_ROOT / "analysis/tables"
REQUEST_TABLE = TABLE_ROOT / "request_timeline.csv"
PROCESS_TABLE = TABLE_ROOT / "process_timeline.csv"
KERNEL_TABLE = TABLE_ROOT / "kernel_timeline.csv"
LIVE_TABLE = TABLE_ROOT / "live_utilization_aligned.csv"
PROCESS_LIVE_TABLE = TABLE_ROOT / "process_live_utilization.csv"
KERNEL_CONCURRENCY_TABLE = TABLE_ROOT / "kernel_concurrency.csv"
QUEUE_CONCURRENCY_TABLE = TABLE_ROOT / "queue_concurrency.csv"
LAUNCH_GAPS_TABLE = TABLE_ROOT / "launch_gaps.csv"
HIGH_TABLE = TABLE_ROOT / "high_latency_processes.csv"
TRAFFIC_TABLE = TABLE_ROOT / "traffic_resource_attachment.csv"
OPPORTUNITY_TABLE = TABLE_ROOT / "opportunity_candidates.csv"


def require(condition: bool, message: str) -> None:
    if not condition:
        raise RuntimeError(message)


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(8 * 1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def canonical_sha256(value: Any) -> str:
    raw = json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode()
    return hashlib.sha256(raw).hexdigest()


def file_record(path: Path, role: str | None = None, content_type: str | None = None) -> dict[str, Any]:
    result = {
        "path": str(path),
        "size_bytes": path.stat().st_size,
        "sha256": sha256_file(path),
    }
    if role:
        result["logical_role"] = role
    if content_type:
        result["content_type"] = content_type
    return result


def write_text_atomic(path: Path, producer) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    require(not path.exists(), f"immutable output exists: {path}")
    temporary = path.with_name(f".{path.name}.partial.{os.getpid()}")
    with temporary.open("x", encoding="utf-8", newline="\n") as handle:
        producer(handle)
        handle.flush()
        os.fsync(handle.fileno())
    os.replace(temporary, path)


def write_json_atomic(path: Path, value: Any, compact: bool = False) -> None:
    def producer(handle):
        if compact:
            json.dump(value, handle, ensure_ascii=False, separators=(",", ":"))
        else:
            json.dump(value, handle, ensure_ascii=False, indent=2, sort_keys=True)
        handle.write("\n")

    write_text_atomic(path, producer)


def read_csv(path: Path) -> list[dict[str, str]]:
    with path.open(newline="", encoding="utf-8") as handle:
        return list(csv.DictReader(handle))


def js_json(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, separators=(",", ":")).replace("</", "<\\/")


def stable_lane(value: str, base: int) -> int:
    return base + int(hashlib.sha256(value.encode()).hexdigest()[:8], 16) % 100000


def html_shell(title: str, body: str, script: str, metadata: dict[str, Any]) -> str:
    return f"""<!doctype html>
<html lang="zh-CN"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>{html.escape(title)}</title>
<style>
:root{{--bg:#10151d;--panel:#18212d;--fg:#edf3fa;--muted:#aab8c8;--line:#33455a;--obs:#55b8ff;--live:#61d095;--replay:#d7aefb;--derived:#ffca70;--missing:#ff7f7f}}
*{{box-sizing:border-box}} body{{margin:0;background:var(--bg);color:var(--fg);font:14px/1.45 system-ui,sans-serif}}
header,main{{max-width:1600px;margin:auto;padding:18px}} h1,h2{{margin:.2em 0 .6em}} a{{color:#8fd2ff}} .panel{{background:var(--panel);border:1px solid var(--line);border-radius:8px;padding:14px;margin:12px 0}}
.legend{{display:flex;flex-wrap:wrap;gap:10px}} .badge{{border:1px solid var(--line);padding:4px 8px;border-radius:5px}} .obs{{border-left:8px solid var(--obs)}} .live{{border-left:8px double var(--live)}} .replay{{border-left:8px dashed var(--replay)}} .derived{{border-left:8px dotted var(--derived)}} .missing{{border-left:8px solid var(--missing);background:repeating-linear-gradient(135deg,transparent,transparent 5px,#4b2525 5px,#4b2525 8px)}}
button,input,select{{background:#0d141c;color:var(--fg);border:1px solid var(--line);border-radius:4px;padding:6px}} button{{cursor:pointer}} canvas{{width:100%;background:#0b1017;border:1px solid var(--line)}}
table{{border-collapse:collapse;width:100%}} th,td{{border:1px solid var(--line);padding:5px;vertical-align:top}} th{{position:sticky;top:0;background:#223043}} .scroll{{overflow:auto;max-height:70vh}} pre{{white-space:pre-wrap;word-break:break-word}} .warn{{color:#ffd2d2}}
</style><script id="report-meta" type="application/json">{js_json(metadata)}</script></head>
<body><header><h1>{html.escape(title)}</h1><div class="legend">
<span class="badge obs">observed R07 timing</span><span class="badge live">observed live utilization</span>
<span class="badge replay">replay_projected R08 attributes</span><span class="badge derived">derived analysis</span>
<span class="badge missing">unavailable / unknown</span></div></header><main>{body}</main><script>{script}</script></body></html>"""


def seal_unit(root: Path, output: Path, role: str, metadata: dict[str, Any]) -> dict[str, Any]:
    record = {"schema_version": 1, "status": "complete", "role": role, **file_record(output), **metadata}
    marker = root / "recovery/units" / f"{output.name}.complete.json"
    write_json_atomic(marker, record)
    record["unit_marker_path"] = str(marker)
    record["unit_marker_sha256"] = sha256_file(marker)
    return record


def build_timeline_events(
    requests: list[dict[str, str]], processes: list[dict[str, str]], kernels: list[dict[str, str]]
) -> tuple[int, list[dict[str, Any]], list[dict[str, Any]]]:
    origin = min(
        [int(row["begin_ns"]) for row in requests]
        + [int(row["begin_ns"]) for row in processes]
        + [int(row["begin_ns"]) for row in kernels]
    )
    logical = []
    display = []
    for row in requests:
        event = {
            "id": row["range_id"], "kind": "request", "name": f"request marker {row['request_id']}",
            "track": f"request/rank{row['dp_rank']}/gpu{row['native_device']}",
            "begin_offset_ns": int(row["begin_ns"]) - origin, "end_offset_ns": int(row["end_ns"]) - origin,
            "begin_ns": row["begin_ns"], "end_ns": row["end_ns"], "duration_ns": int(row["duration_ns"]),
            "request_id": row["request_id"], "phase": "", "layer": "", "family": "request_marker",
            "rank": row["dp_rank"], "device": row["native_device"], "queue": "", "owner": "",
            "evidence": "observed_r07_timing", "availability": row["availability_state"],
        }
        logical.append(event); display.append(event)
    for row in processes:
        event = {
            "id": row["process_range_id"], "kind": "process", "name": f"{row['process_id']} / {row['fragment_id']}",
            "track": f"process/rank{row['dp_rank']}/{row['process_id']}",
            "begin_offset_ns": int(row["begin_ns"]) - origin, "end_offset_ns": int(row["end_ns"]) - origin,
            "begin_ns": row["begin_ns"], "end_ns": row["end_ns"], "duration_ns": int(row["duration_ns"]),
            "request_id": row["request_id"], "phase": row["phase"], "layer": row["layer_idx"],
            "family": row["aggregation_key"], "rank": row["dp_rank"], "device": row["native_device"],
            "queue": "", "owner": row["canonical_target_id"], "evidence": "observed_r07_timing",
            "availability": row["availability_state"],
        }
        logical.append(event); display.append(event)
    for row in kernels:
        base = {
            "id": row["kernel_instance_id"], "kind": "kernel", "name": row["native_kernel_name"],
            "begin_offset_ns": int(row["begin_ns"]) - origin, "end_offset_ns": int(row["end_ns"]) - origin,
            "begin_ns": row["begin_ns"], "end_ns": row["end_ns"], "duration_ns": int(row["duration_ns"]),
            "request_id": row["request_id"], "phase": "", "layer": row["layer_idx"],
            "family": row["kernel_family"], "rank": row["dp_rank"], "device": row["native_device"],
            "queue": f"{row['queue_id']}:{row['stream_id']}", "owner": row["owner_process_range_id"],
            "evidence": "observed_r07_timing", "availability": row["availability_state"],
        }
        logical.append({**base, "track": f"strict-owned/rank{row['dp_rank']}/{row['process_id']}"})
        display.append({**base, "id": base["id"] + ":strict", "display_copy": "strict_owned_kernel", "track": f"strict-owned/rank{row['dp_rank']}/{row['process_id']}"})
        display.append({**base, "id": base["id"] + ":queue", "display_copy": "gpu_queue", "track": f"gpu-queue/gpu{row['native_device']}/q{row['queue_id']}:s{row['stream_id']}"})
    display.sort(key=lambda event: (event["begin_offset_ns"], event["end_offset_ns"], event["track"], event["id"]))
    logical.sort(key=lambda event: (event["begin_offset_ns"], event["end_offset_ns"], event["kind"], event["id"]))
    return origin, logical, display


def perfetto_event(event: dict[str, Any]) -> dict[str, Any]:
    if event["kind"] == "request":
        pid = 1000 + int(event["rank"])
    elif event["kind"] == "process":
        pid = 2000 + int(event["rank"])
    elif event.get("display_copy") == "gpu_queue":
        pid = 4000 + int(event["device"])
    else:
        pid = 3000 + int(event["rank"])
    return {
        "name": event["name"], "cat": f"{event['kind']}|{event['evidence']}", "ph": "X",
        "ts": event["begin_offset_ns"] / 1000.0, "dur": event["duration_ns"] / 1000.0,
        "pid": pid, "tid": stable_lane(event["track"], 1),
        "args": {
            "event_id": event["id"], "track": event["track"], "absolute_begin_ns": event["begin_ns"],
            "absolute_end_ns": event["end_ns"], "begin_offset_ns": str(event["begin_offset_ns"]),
            "end_offset_ns": str(event["end_offset_ns"]), "request_id": event["request_id"],
            "rank": event["rank"], "native_device": event["device"], "family": event["family"],
            "owner": event["owner"], "queue": event["queue"], "evidence": event["evidence"],
            "display_copy": event.get("display_copy", "logical"),
        },
    }


def build_perfetto(path: Path, origin: int, display: list[dict[str, Any]], counts: dict[str, int]) -> None:
    payload = {
        "displayTimeUnit": "ns",
        "metadata": {
            "schema_version": 1, "runtime_run_id": RUN_ID, "lineage_id": LINEAGE_ID,
            "evidence_status": "degraded_R07_observed_subset", "clock_origin_ns": str(origin),
            "timestamp_transport": "relative_microseconds_for_trace_event_viewer_with_exact_absolute_and_offset_ns_strings_in_args",
            "complete_declared_target_timeline": False, "complete_observed_subset_timeline": True,
            "sampling_performed": False, "event_counts": counts,
        },
        "traceEvents": [perfetto_event(event) for event in display],
    }
    write_json_atomic(path, payload, compact=True)


def build_overview(path: Path, requests: list[dict[str, str]], counts: dict[str, int]) -> None:
    grouped: dict[str, list[dict[str, str]]] = defaultdict(list)
    for row in requests:
        grouped[row["request_id"]].append(row)
    cards = []
    for request_id, rows in sorted(grouped.items(), key=lambda pair: int(pair[1][0]["measured_request_ordinal"])):
        cards.append({
            "request_id": request_id, "ordinal": int(rows[0]["measured_request_ordinal"]), "marker_rows": len(rows),
            "begin_ns": str(min(int(row["begin_ns"]) for row in rows)),
            "end_ns": str(max(int(row["end_ns"]) for row in rows)),
            "ranks": sorted({int(row["dp_rank"]) for row in rows}),
        })
    metadata = {"page_role": "timeline_overview", "event_counts": counts, "observed_request_identity_count": 5, "declared_request_count": 8, "sampling_performed": False}
    body = """<section class="panel warn"><b>证据边界：</b>R07 只观测到 5/8 个请求身份；320 行是重复的 layer-scope request marker，不是 320 个独立请求。此页展示完整已观测子集，不代表完整声明目标。</section>
<section class="panel"><h2>完整事件分母</h2><div id="counts"></div></section><section class="panel"><h2>请求身份</h2><div id="cards"></div></section>
<section class="panel"><a href="E2E_PROCESS_TIMELINE_LOSSLESS.html">打开无损交互时间线</a> · <a href="E2E_PROCESS_TIMELINE.full.perfetto.json">下载完整 Perfetto JSON</a></section>"""
    script = f"""const META={js_json(metadata)},CARDS={js_json(cards)};
counts.textContent=JSON.stringify(META.event_counts,null,2); cards.innerHTML='';
for(let ordinal=1;ordinal<=8;ordinal++){{const x=CARDS.find(v=>v.ordinal===ordinal),d=document.createElement('div');d.className='panel '+(x?'obs':'missing');d.textContent=x?`req ${{ordinal}} | ${{x.request_id}} | marker rows=${{x.marker_rows}} | ranks=${{x.ranks}}`:`req ${{ordinal}} | unavailable: R07 marker identity missing`;cards.appendChild(d)}}"""
    write_text_atomic(path, lambda handle: handle.write(html_shell("R10 E2E Process Timeline Overview", body, script, metadata)))


def build_lossless(path: Path, origin: int, display: list[dict[str, Any]], counts: dict[str, int]) -> None:
    metadata = {
        "page_role": "lossless_timeline", "clock_origin_ns": str(origin), "embedded_event_count": len(display),
        "event_counts": counts, "minimum_viewport_ns": 1, "history_capacity": 200,
        "sampling_performed": False, "event_budget_used": False, "absolute_ns_transport": "decimal_string",
    }
    body = """<section class="panel warn">全量已观测子集；kernel 以 strict-owner 与 GPU queue 两个展示副本出现，二者是同一 observed interval，不可相加。</section>
<section class="panel"><input id="filter" size="55" placeholder="process/event/layer/phase/family/track 全文筛选"><button id="fit">fit filtered</button><button id="zin">放大</button><button id="zout">缩小</button><button id="back">后退</button><button id="forward">前进</button><button id="reset">重置</button><br>
<input id="jumpBegin" size="24" placeholder="absolute begin_ns"><input id="jumpEnd" size="24" placeholder="absolute end_ns"><button id="jump">精确跳转</button><button id="list">列出当前视窗全部事件</button><span id="state"></span></section>
<canvas id="timeline" width="1500" height="900"></canvas><section class="panel"><h2>选择/视窗结果（不设条数上限）</h2><pre id="details"></pre></section>"""
    script = f"""const ORIGIN=BigInt('{origin}'),EVENTS={js_json(display)};const C=timeline.getContext('2d');
const COLORS={{request:'#55b8ff',process:'#ffca70',kernel:'#d7aefb'}};let allL=Math.min(...EVENTS.map(e=>e.begin_offset_ns)),allR=Math.max(...EVENTS.map(e=>e.end_offset_ns)),L=allL,R=allR;
let hist=[[L,R]],hi=0,drag=null;const tracks=[...new Set(EVENTS.map(e=>e.track))].sort(),ti=new Map(tracks.map((x,i)=>[x,i]));
function matching(e){{const q=filter.value.toLowerCase();return !q||JSON.stringify(e).toLowerCase().includes(q)}}
function push(l,r){{if(r-l<1)r=l+1;L=l;R=r;hist=hist.slice(0,hi+1);hist.push([L,R]);if(hist.length>200)hist.shift();hi=hist.length-1;draw()}}
function draw(){{C.clearRect(0,0,timeline.width,timeline.height);const span=Math.max(1,R-L),lane=Math.max(4,(timeline.height-25)/tracks.length);let visible=0;
 C.font='10px sans-serif';for(const e of EVENTS){{if(!matching(e)||e.end_offset_ns<L||e.begin_offset_ns>R)continue;visible++;const x=(e.begin_offset_ns-L)/span*timeline.width,w=Math.max(1,(e.end_offset_ns-e.begin_offset_ns)/span*timeline.width),y=20+ti.get(e.track)*lane;C.fillStyle=COLORS[e.kind]||'#ff7f7f';C.globalAlpha=e.display_copy==='gpu_queue'?.48:.82;C.fillRect(x,y,w,Math.max(2,lane-1));}}C.globalAlpha=1;state.textContent=` viewport=${{Math.round(L)}}..${{Math.round(R)}} ns | visible=${{visible}} | events=${{EVENTS.length}} | history=${{hi+1}}/${{hist.length}}`;}}
function centered(f){{const m=(L+R)/2,s=(R-L)*f;push(m-s/2,m+s/2)}} zin.onclick=()=>centered(.5);zout.onclick=()=>centered(2);reset.onclick=()=>push(allL,allR);fit.onclick=()=>{{const a=EVENTS.filter(matching);if(a.length)push(Math.min(...a.map(e=>e.begin_offset_ns)),Math.max(...a.map(e=>e.end_offset_ns)))}};
back.onclick=()=>{{if(hi>0){{hi--;[L,R]=hist[hi];draw()}}}};forward.onclick=()=>{{if(hi+1<hist.length){{hi++;[L,R]=hist[hi];draw()}}}};filter.oninput=draw;
jump.onclick=()=>{{try{{push(Number(BigInt(jumpBegin.value)-ORIGIN),Number(BigInt(jumpEnd.value)-ORIGIN))}}catch(e){{details.textContent='invalid integer nanoseconds'}}}};
list.onclick=()=>{{details.textContent=EVENTS.filter(e=>matching(e)&&e.end_offset_ns>=L&&e.begin_offset_ns<=R).map(e=>JSON.stringify(e)).join('\n')}};
timeline.onwheel=e=>{{e.preventDefault();const x=e.offsetX/timeline.clientWidth,m=L+x*(R-L),f=e.deltaY>0?1.4:.7;push(m-(m-L)*f,m+(R-m)*f)}};
timeline.onmousedown=e=>drag={{x:e.offsetX,l:L,r:R,shift:e.shiftKey}};timeline.onmousemove=e=>{{if(!drag||drag.shift)return;const d=(e.offsetX-drag.x)/timeline.clientWidth*(drag.r-drag.l);L=drag.l-d;R=drag.r-d;draw()}};
timeline.onmouseup=e=>{{if(!drag)return;if(drag.shift){{const a=Math.min(drag.x,e.offsetX)/timeline.clientWidth,b=Math.max(drag.x,e.offsetX)/timeline.clientWidth;push(drag.l+a*(drag.r-drag.l),drag.l+b*(drag.r-drag.l))}}else push(L,R);drag=null}};
timeline.onclick=e=>{{const span=R-L,lo=L+e.offsetX/timeline.clientWidth*span,hi=lo+span/timeline.clientWidth;details.textContent=EVENTS.filter(x=>matching(x)&&x.end_offset_ns>=lo&&x.begin_offset_ns<=hi).map(x=>JSON.stringify(x)).join('\n')}};draw();"""
    write_text_atomic(path, lambda handle: handle.write(html_shell("R10 Lossless E2E Process Timeline", body, script, metadata)))


def build_high_latency(
    path: Path,
    high_rows: list[dict[str, str]],
    traffic_rows: list[dict[str, str]],
    opportunity_rows: list[dict[str, str]],
) -> None:
    high_ids = {row["process_range_id"] for row in high_rows}
    resources: dict[str, dict[str, Any]] = defaultdict(lambda: {"available": {}, "unavailable": 0, "captures": set()})
    for row in traffic_rows:
        pid = row["process_range_id"]
        if pid not in high_ids:
            continue
        if row["metric_value"]:
            resources[pid]["available"].setdefault(row["metric_name"], []).append(float(row["metric_value"]))
            resources[pid]["captures"].add(row["physical_capture_id"])
        else:
            resources[pid]["unavailable"] += 1
    opportunities = {row["process_range_id"]: row for row in opportunity_rows if row["process_range_id"]}
    payload = []
    for row in high_rows:
        resource = resources[row["process_range_id"]]
        metrics = {name: {"min": min(values), "max": max(values)} for name, values in resource["available"].items()}
        opp = opportunities[row["process_range_id"]]
        payload.append({
            "process_range_id": row["process_range_id"], "request_id": row["request_id"], "rank": row["dp_rank"],
            "device": row["native_device"], "phase": row["phase"], "process": row["process_id"],
            "fragment": row["fragment_id"], "duration_ns": int(row["duration_ns"]),
            "global_threshold_ns": int(row["global_p95_threshold_ns"]), "peer_threshold_ns": int(row["peer_group_p95_threshold_ns"]),
            "global_flag": row["global_p95_or_tie"], "peer_flag": row["peer_group_p95_or_tie"],
            "resource_metrics": metrics, "physical_capture_ids": sorted(resource["captures"]),
            "unavailable_attachment_rows": resource["unavailable"], "candidate_state": opp["candidate_state"],
            "candidate_reason": opp["availability_reason"], "live_state": opp["live_utilization_state"],
            "live_value": opp["live_se_active_cu_pct_mean"],
        })
    metadata = {"page_role": "high_latency_hardware", "high_latency_row_count": len(payload), "top_n_truncation_performed": False, "R08_timing_used_as_latency": False}
    body = """<section class="panel warn">完整 p95+ties 分类，无 Top-N。R08 值是共享的 replay_projected 属性，只提供调查线索；不证明因果、根因或加速收益。</section>
<section class="panel"><input id="filter" size="60" placeholder="全文筛选"><span id="summary"></span></section><section class="scroll"><table><thead><tr><th>process</th><th>observed duration / thresholds</th><th>observed live</th><th>replay_projected attributes</th><th>derived opportunity</th></tr></thead><tbody id="rows"></tbody></table></section>"""
    script = f"""const DATA={js_json(payload)};function render(){{const q=filter.value.toLowerCase(),a=DATA.filter(x=>!q||JSON.stringify(x).toLowerCase().includes(q));rows.innerHTML='';for(const x of a){{const tr=document.createElement('tr');const cells=[`${{x.process}}/${{x.fragment}}<br>${{x.request_id}} rank${{x.rank}} gpu${{x.device}}`,`duration=${{x.duration_ns}}<br>global p95=${{x.global_threshold_ns}} (${{x.global_flag}})<br>peer p95=${{x.peer_threshold_ns}} (${{x.peer_flag}})`,`state=${{x.live_state}}<br>SE active CU mean=${{x.live_value||'unavailable'}}`,JSON.stringify(x.resource_metrics)+'<br>shared captures='+x.physical_capture_ids.join(',')+'<br>unavailable rows='+x.unavailable_attachment_rows,`${{x.candidate_state}}<br>${{x.candidate_reason}}<br>hypothesis only`];for(const c of cells){{const td=document.createElement('td');td.innerHTML=c;tr.appendChild(td)}}rows.appendChild(tr)}}summary.textContent=` shown=${{a.length}} / complete=${{DATA.length}}`;}}filter.oninput=render;render();"""
    write_text_atomic(path, lambda handle: handle.write(html_shell("R10 High-Latency Process + Hardware Timeline", body, script, metadata)))


def write_concurrency_html(
    path: Path,
    trace_origin: int,
    kernel_concurrency: list[dict[str, str]],
    queue_concurrency: list[dict[str, str]],
    launch_gaps: list[dict[str, str]],
    process_live: list[dict[str, str]],
) -> dict[str, int]:
    derived = {
        "kernel_concurrency": [{"b": row["begin_ns"], "e": row["end_ns"], "n": row["active_kernel_count"], "r": row["dp_rank"], "d": row["native_device"], "a": row["availability_state"]} for row in kernel_concurrency],
        "queue_concurrency": [{"b": row["begin_ns"], "e": row["end_ns"], "q": row["active_queue_count"], "k": row["active_kernel_count"], "r": row["dp_rank"], "d": row["native_device"], "a": row["availability_state"]} for row in queue_concurrency],
        "launch_gaps": [{"b": row["previous_end_ns"], "e": row["next_begin_ns"], "gap": row["gap_ns"], "overlap": row["overlap_ns"], "r": row["dp_rank"], "d": row["native_device"]} for row in launch_gaps],
        "process_live": [{"id": row["process_range_id"], "b": row["process_begin_realtime_ns"], "e": row["process_end_realtime_ns"], "v": row["se_active_cu_pct_mean"], "a": row["availability_state"], "d": row["native_device"]} for row in process_live],
    }
    metadata = {
        "page_role": "concurrency_utilization", "trace_origin_ns": str(trace_origin),
        "live_sample_count": 2357298, "live_gap_count": 374, "live_anchor_count": 2,
        "kernel_concurrency_row_count": len(kernel_concurrency), "queue_concurrency_row_count": len(queue_concurrency),
        "launch_gap_row_count": len(launch_gaps), "process_live_row_count": len(process_live),
        "sampling_performed": False, "imputation_performed": False,
    }
    prefix_body = """<section class="panel warn">全部 raw live samples/gaps/anchors 内嵌；无重采样、插值或零填充。跨设备并发因缺少独立时钟对齐证明而保持 unavailable。</section>
<section class="panel"><select id="device"><option value="all">GPU 0+1</option><option value="0">GPU 0</option><option value="1">GPU 1</option></select><button id="zin">放大</button><button id="zout">缩小</button><button id="reset">重置</button><button id="list">列出视窗内全部 raw samples</button><span id="state"></span></section>
<canvas id="chart" width="1500" height="620"></canvas><section class="panel"><pre id="details"></pre></section>"""
    prefix_script = f"const META={js_json(metadata)},DERIVED={js_json(derived)},SAMPLES=["
    suffix_script = """
const C=chart.getContext('2d');let allL=Infinity,allR=-Infinity;for(const x of SAMPLES){if(x[0]<allL)allL=x[0];if(x[0]>allR)allR=x[0]}let L=allL,R=allR,drag=null;
function chosen(x){return device.value==='all'||String(x[2])===device.value}function draw(){C.clearRect(0,0,chart.width,chart.height);const bins=Array.from({length:chart.width},()=>[0,0]);let visible=0;for(const x of SAMPLES){if(!chosen(x)||x[0]<L||x[0]>R)continue;visible++;const i=Math.max(0,Math.min(chart.width-1,Math.floor((x[0]-L)/(R-L||1)*chart.width)));bins[i][0]+=x[1];bins[i][1]++}C.strokeStyle='#61d095';C.beginPath();for(let i=0;i<bins.length;i++){if(!bins[i][1])continue;const y=590-(bins[i][0]/bins[i][1])/100*560;if(i===0)C.moveTo(i,y);else C.lineTo(i,y)}C.stroke();C.fillStyle='rgba(255,127,127,.25)';for(const g of GAPS){if(device.value!=='all'&&String(g[2])!==device.value)continue;const b=Math.max(L,g[0]),e=Math.min(R,g[1]);if(e>b)C.fillRect((b-L)/(R-L)*chart.width,20,(e-b)/(R-L)*chart.width,570)}state.textContent=` viewport offset=${Math.round(L)}..${Math.round(R)} ns | raw visible=${visible} | total=${SAMPLES.length} | gaps=${GAPS.length}`}
function zoom(f){const m=(L+R)/2,s=Math.max(1,(R-L)*f);L=m-s/2;R=m+s/2;draw()} zin.onclick=()=>zoom(.5);zout.onclick=()=>zoom(2);reset.onclick=()=>{L=allL;R=allR;draw()};device.onchange=draw;
chart.onwheel=e=>{e.preventDefault();const p=e.offsetX/chart.clientWidth,m=L+p*(R-L),f=e.deltaY>0?1.4:.7;L=m-(m-L)*f;R=m+(R-m)*f;draw()};chart.onmousedown=e=>drag={x:e.offsetX,l:L,r:R};chart.onmousemove=e=>{if(!drag)return;const d=(e.offsetX-drag.x)/chart.clientWidth*(drag.r-drag.l);L=drag.l-d;R=drag.r-d;draw()};chart.onmouseup=()=>drag=null;
list.onclick=()=>{details.textContent=SAMPLES.filter(x=>chosen(x)&&x[0]>=L&&x[0]<=R).map(x=>JSON.stringify({midpoint_offset_ns:x[0],se_active_cu_pct:x[1],device:x[2],sequence:x[3],call_latency_ns:x[4],uncertainty_ns:x[5],timing_eligible:!!x[6]})).join('\n')};draw();"""
    gap_rows = []
    anchors = []
    sample_count = 0

    def producer(handle):
        nonlocal sample_count
        # Write the page shell manually because the 2.35M sample payload is streamed.
        shell = html_shell("R10 Concurrency + Live Utilization", prefix_body, "__STREAM_SCRIPT__", metadata)
        before, after = shell.split("__STREAM_SCRIPT__", 1)
        handle.write(before)
        handle.write(prefix_script)
        first = True
        with LIVE_TABLE.open(newline="", encoding="utf-8") as source:
            reader = csv.DictReader(source)
            for row in reader:
                if row["record_kind"] == "sample":
                    offset = int(row["midpoint_realtime_ns"]) - trace_origin
                    compact = [offset, float(row["se_active_cu_pct"]), int(row["native_device"]), int(row["sequence"]), int(row["call_latency_ns"]), int(row["alignment_uncertainty_ns"]), 1 if row["timing_eligible"] == "True" else 0]
                    if not first:
                        handle.write(",")
                    handle.write(js_json(compact)); first = False; sample_count += 1
                elif row["record_kind"] == "gap":
                    gap_rows.append([int(row["begin_monotonic_ns"]), int(row["end_monotonic_ns"]), int(row["native_device"]), int(row["unobserved_gap_ns"]), row["previous_sequence"], row["next_sequence"]])
                else:
                    anchors.append({key: row[key] for key in row})
        anchor_by_kind = {row["anchor_kind"]: row for row in anchors}
        start_anchor, end_anchor = anchor_by_kind["start"], anchor_by_kind["end"]
        start_mono = int(start_anchor["midpoint_monotonic_ns"])
        start_real = int(start_anchor["midpoint_realtime_ns"])
        delta_mono = int(end_anchor["midpoint_monotonic_ns"]) - start_mono
        delta_real = int(end_anchor["midpoint_realtime_ns"]) - start_real
        require(delta_mono > 0 and delta_real > 0, "invalid live clock anchors")
        def realtime_offset(monotonic_ns: int) -> int:
            numerator = (monotonic_ns - start_mono) * delta_real
            return start_real + (numerator + delta_mono // 2) // delta_mono - trace_origin
        aligned_gaps = [
            [realtime_offset(row[0]), realtime_offset(row[1]), *row[2:]]
            for row in gap_rows
        ]
        handle.write(f"];const GAPS={js_json(aligned_gaps)},ANCHORS={js_json(anchors)};")
        handle.write(suffix_script)
        handle.write(after)

    write_text_atomic(path, producer)
    require(sample_count == 2357298 and len(gap_rows) == 374 and len(anchors) == 2, "concurrency live payload denominator drift")
    return {"samples": sample_count, "gaps": len(gap_rows), "anchors": len(anchors)}


def build_index(path: Path, records: dict[str, dict[str, Any]], counts: dict[str, int]) -> None:
    metadata = {"page_role": "single_entry_index", "evidence_status": "degraded_R07_observed_subset", "event_counts": counts, "browser_runtime_audit_available": False}
    body = """<section class="panel warn"><b>结论边界：</b>报告完整覆盖 R07 已观测子集，但 R07 仅覆盖声明目标的 31.25%，所以不是严格 R09/R10 完成。浏览器运行验收因本机没有浏览器二进制而不可用；静态、哈希和事件守恒审计仍执行。</section>
<section class="panel"><h2>离线入口</h2><ul>
<li><a href="E2E_PROCESS_TIMELINE.html">E2E_PROCESS_TIMELINE.html</a></li><li><a href="E2E_PROCESS_TIMELINE_LOSSLESS.html">E2E_PROCESS_TIMELINE_LOSSLESS.html</a></li>
<li><a href="HIGH_LATENCY_PROCESS_HARDWARE_TIMELINE.html">HIGH_LATENCY_PROCESS_HARDWARE_TIMELINE.html</a></li><li><a href="CONCURRENCY_UTILIZATION.html">CONCURRENCY_UTILIZATION.html</a></li>
<li><a href="E2E_PROCESS_TIMELINE.full.perfetto.json">完整 Perfetto JSON</a></li><li><a href="full_timeline_manifest.json">full_timeline_manifest.json</a></li>
<li><a href="offline_acceptance_manifest.json">offline_acceptance_manifest.json</a></li><li><a href="../R10_SOURCE_LINEAGE.json">R10_SOURCE_LINEAGE.json</a></li><li><a href="../R10_COMPLETION_AUDIT.json">R10_COMPLETION_AUDIT.json</a></li></ul></section>
<section class="panel"><h2>数据语义</h2><pre id="summary"></pre></section>"""
    script = f"summary.textContent=JSON.stringify({js_json({'counts': counts, 'files': records, 'coverage': {'requests':'5/8 identities','process_markers':'3920/12544','targets':'4240/13568','target_fraction':0.3125}})},null,2);"
    write_text_atomic(path, lambda handle: handle.write(html_shell("R10 Offline Acceptance Index (Degraded Observed Subset)", body, script, metadata)))


FORBIDDEN = [
    re.compile(pattern, re.I)
    for pattern in [r"https?://", r"\bfetch\s*\(", r"XMLHttpRequest", r"WebSocket", r"EventSource", r"serviceWorker", r"<script[^>]+src=", r"<link[^>]+href="]
]


def static_page_audit(paths: Iterable[Path]) -> dict[str, Any]:
    results = []
    for path in paths:
        text = path.read_text(encoding="utf-8")
        hits = [pattern.pattern for pattern in FORBIDDEN if pattern.search(text)]
        results.append({"path": str(path), "size_bytes": path.stat().st_size, "sha256": sha256_file(path), "forbidden_pattern_hits": hits})
        require(not hits, f"offline boundary violation: {path}: {hits}")
    return {"status": "complete", "pages": results, "attempted_network_requests": 0, "static_no_remote_reference_gate": True}


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--artifact-root", required=True, type=Path)
    args = parser.parse_args()
    root = args.artifact_root.resolve()
    require(root == Path(__file__).resolve().parents[1], "artifact root/tool location mismatch")
    acceptance = root / "acceptance"
    acceptance.mkdir(parents=True, exist_ok=True)
    require(not (root / "R10_BUILDER_COMPLETE.json").exists(), "immutable R10 builder output exists")
    started = time.monotonic()
    for path in [R09_ANALYSIS, R09_COMPLETE, R09_LINEAGE, R08_HANDOFF, R07_LINEAGE, REQUEST_TABLE, PROCESS_TABLE, KERNEL_TABLE, LIVE_TABLE, PROCESS_LIVE_TABLE, KERNEL_CONCURRENCY_TABLE, QUEUE_CONCURRENCY_TABLE, LAUNCH_GAPS_TABLE, HIGH_TABLE, TRAFFIC_TABLE, OPPORTUNITY_TABLE]:
        require(path.is_file(), f"missing R10 source: {path}")
    analysis = json.loads(R09_ANALYSIS.read_text(encoding="utf-8"))
    complete = json.loads(R09_COMPLETE.read_text(encoding="utf-8"))
    require(complete["status"] == "complete" and complete["strict_R10_authorized"] is False, "R09 degraded gate drift")
    require(analysis["complete_observed_subset_timeline"] is True and analysis["complete_timeline"] is False, "R09 timeline boundary drift")
    requests, processes, kernels = read_csv(REQUEST_TABLE), read_csv(PROCESS_TABLE), read_csv(KERNEL_TABLE)
    origin, logical, display = build_timeline_events(requests, processes, kernels)
    counts = {
        "request_timeline_rows": len(requests), "process_timeline_rows": len(processes),
        "kernel_timeline_rows": len(kernels), "strict_owned_kernel_display_events": len(kernels),
        "gpu_queue_kernel_display_events": len(kernels),
        "formula": len(requests) + len(processes) + 2 * len(kernels),
        "actual_display_event_count": len(display), "logical_event_count": len(logical),
    }
    require(counts["formula"] == counts["actual_display_event_count"] == 17280, "R10 event formula drift")
    unit_records: dict[str, dict[str, Any]] = {}
    perfetto = acceptance / "E2E_PROCESS_TIMELINE.full.perfetto.json"
    build_perfetto(perfetto, origin, display, counts)
    unit_records[perfetto.name] = seal_unit(root, perfetto, "full_perfetto_trace", {"event_count": len(display)})
    overview = acceptance / "E2E_PROCESS_TIMELINE.html"
    build_overview(overview, requests, counts)
    unit_records[overview.name] = seal_unit(root, overview, "timeline_overview", {"event_denominator": len(display)})
    lossless = acceptance / "E2E_PROCESS_TIMELINE_LOSSLESS.html"
    build_lossless(lossless, origin, display, counts)
    unit_records[lossless.name] = seal_unit(root, lossless, "lossless_timeline", {"embedded_event_count": len(display), "minimum_viewport_ns": 1})
    high_rows, traffic_rows, opportunity_rows = read_csv(HIGH_TABLE), read_csv(TRAFFIC_TABLE), read_csv(OPPORTUNITY_TABLE)
    high_page = acceptance / "HIGH_LATENCY_PROCESS_HARDWARE_TIMELINE.html"
    build_high_latency(high_page, high_rows, traffic_rows, opportunity_rows)
    unit_records[high_page.name] = seal_unit(root, high_page, "high_latency_hardware", {"high_latency_row_count": len(high_rows), "top_n_truncation_performed": False})
    kernel_concurrency, queue_concurrency = read_csv(KERNEL_CONCURRENCY_TABLE), read_csv(QUEUE_CONCURRENCY_TABLE)
    launch_gaps, process_live = read_csv(LAUNCH_GAPS_TABLE), read_csv(PROCESS_LIVE_TABLE)
    concurrency_page = acceptance / "CONCURRENCY_UTILIZATION.html"
    live_counts = write_concurrency_html(concurrency_page, origin, kernel_concurrency, queue_concurrency, launch_gaps, process_live)
    unit_records[concurrency_page.name] = seal_unit(root, concurrency_page, "concurrency_utilization", live_counts)
    print("R10 visualization units complete", flush=True)

    timeline_manifest = {
        "schema_version": 1,
        "renderer_algorithm_version": "degraded-observed-subset-r10-v1",
        "status": "complete",
        "evidence_status": "degraded_R07_observed_subset",
        "runtime_run_id": RUN_ID,
        "lineage_id": LINEAGE_ID,
        "trace_profile_sha256": TRACE_PROFILE_SHA256,
        "R09_analysis": file_record(R09_ANALYSIS),
        "ordered_R09_tables": analysis["ordered_tables"],
        "event_counts": counts,
        "event_count_formula": "request_timeline + process_timeline + 2*kernel_timeline",
        "kernel_display_copy_semantics": "paired presentation copies of one observed interval; nonadditive",
        "clock_origin_ns": str(origin),
        "browser_coordinate_transport": "integer nanosecond offsets from decimal-string absolute origin",
        "minimum_viewport_ns": 1,
        "complete_timeline": False,
        "complete_observed_subset_timeline": True,
        "complete_declared_target_timeline": False,
        "sampling_performed": False,
        "formal_r09_r10_regeneration": False,
        "top_n_truncation_performed": False,
        "fixed_event_budget_used": False,
        "R08_replay_time_used_as_latency": False,
        "presentation_units": unit_records,
        "live_utilization": {**live_counts, "imputation_performed": False},
    }
    timeline_manifest_path = acceptance / "full_timeline_manifest.json"
    write_json_atomic(timeline_manifest_path, timeline_manifest)

    # Build the single entry before the offline manifest so it is part of the
    # statically audited, hash-sealed presentation payload.
    index = acceptance / "index.html"
    build_index(index, unit_records, counts)
    unit_records[index.name] = seal_unit(root, index, "single_entry_index", {"navigation_target_count": 9})

    browser_candidates = {name: shutil.which(name) for name in ["chromium", "chromium-browser", "google-chrome", "firefox"]}
    browser_capability = {
        "schema_version": 1, "status": "unavailable", "browser_candidates": browser_candidates,
        "browser_runtime_found": False, "network_denied_browser_execution_performed": False,
        "reason": "no local browser binary; dynamic network installation forbidden by offline acceptance boundary",
    }
    browser_capability_path = root / "validation/browser_capability.json"
    write_json_atomic(browser_capability_path, browser_capability)
    page_paths = [index, overview, lossless, high_page, concurrency_page]
    static_audit = static_page_audit(page_paths)
    static_audit_path = root / "validation/static_offline_audit.json"
    write_json_atomic(static_audit_path, static_audit)
    offline_manifest = {
        "schema_version": 1, "status": "complete_with_browser_runtime_unavailable",
        "evidence_status": "degraded_R07_observed_subset", "runtime_run_id": RUN_ID, "lineage_id": LINEAGE_ID,
        "presentation_payload": [file_record(path, content_type="text/html") for path in page_paths]
        + [file_record(perfetto, content_type="application/json"), file_record(timeline_manifest_path, content_type="application/json")],
        "navigation_entry": "index.html",
        "lossless_event_count": len(display), "perfetto_event_count": len(display),
        "event_formula": counts, "live_payload_counts": live_counts,
        "sampling_performed": False, "top_n_truncation_performed": False,
        "static_offline_audit": file_record(static_audit_path),
        "browser_capability": file_record(browser_capability_path),
        "network_denied_browser_execution_performed": False,
        "strict_offline_acceptance_complete": False,
        "attempted_network_requests": 0,
    }
    offline_manifest_path = acceptance / "offline_acceptance_manifest.json"
    write_json_atomic(offline_manifest_path, offline_manifest)

    source_lineage = {
        "schema_version": 1, "status": "complete", "evidence_status": "degraded_R07_observed_subset",
        "runtime_run_id": RUN_ID, "lineage_id": LINEAGE_ID, "trace_profile_sha256": TRACE_PROFILE_SHA256,
        "R07_source_lineage": file_record(R07_LINEAGE), "R08_degraded_handoff": file_record(R08_HANDOFF),
        "R09_degraded_complete": file_record(R09_COMPLETE), "R09_analysis": file_record(R09_ANALYSIS),
        "full_timeline_manifest": file_record(timeline_manifest_path),
        "offline_acceptance_manifest": file_record(offline_manifest_path),
        "presentation_units": unit_records,
        "strict_R10_handoff_created": False, "strict_offline_acceptance_complete": False,
        "model_execution_performed": False, "gpu_dcu_execution_performed": False,
        "profiler_execution_performed": False, "trace_collection_performed": False,
        "pmc_collection_performed": False, "external_network_access_performed": False,
    }
    lineage_path = root / "R10_SOURCE_LINEAGE.json"
    write_json_atomic(lineage_path, source_lineage)
    business_paths = [index, overview, lossless, perfetto, timeline_manifest_path, high_page, concurrency_page, offline_manifest_path, lineage_path]
    artifact_manifest = {
        "schema_version": 1, "status": "complete", "artifact_scope": "R10_degraded_observed_subset_report",
        "runtime_run_id": RUN_ID, "lineage_id": LINEAGE_ID,
        "strict_scheduler_handoff_included": False,
        "artifacts": [file_record(path) for path in business_paths],
        "validation_inputs": [file_record(static_audit_path), file_record(browser_capability_path)],
    }
    artifact_manifest_path = root / "artifact_manifest.json"
    write_json_atomic(artifact_manifest_path, artifact_manifest)
    marker = {
        "schema_version": 1, "status": "builder_complete_pending_independent_audit",
        "finished_utc": utc_now(), "elapsed_seconds": time.monotonic() - started,
        "evidence_status": "degraded_R07_observed_subset", "event_count": len(display),
        "live_sample_count": live_counts["samples"], "presentation_unit_count": len(unit_records),
        "full_timeline_manifest": file_record(timeline_manifest_path),
        "offline_acceptance_manifest": file_record(offline_manifest_path),
        "source_lineage": file_record(lineage_path), "artifact_manifest": file_record(artifact_manifest_path),
        "strict_R10_handoff_created": False, "strict_offline_acceptance_complete": False,
        "dcu_accessed": False,
    }
    write_json_atomic(root / "R10_BUILDER_COMPLETE.json", marker)
    print(json.dumps(marker, sort_keys=True), flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
