#!/usr/bin/env python3
"""Replay a retained single-batch R10 archive into offline ranked timelines.

No runtime acquisition. Source archives are copied byte-for-byte. Absolute
integer timestamps are serialized as strings before browser JSON parsing.
"""
import argparse, collections, csv, hashlib, html, json, re, shutil, tarfile
from pathlib import Path
ASSETS = Path(__file__).with_name('ranked_timeline_assets')

def sha(p):
    h = hashlib.sha256()
    with Path(p).open('rb') as f:
        for block in iter(lambda: f.read(8 << 20), b''): h.update(block)
    return h.hexdigest()

def dump(p, data):
    p.write_text(json.dumps(data, ensure_ascii=False, indent=2) + '\n')

def safe(data):
    if isinstance(data, dict): return {k: safe(v) for k, v in data.items()}
    if isinstance(data, list): return [safe(v) for v in data]
    if isinstance(data, int) and not isinstance(data, bool) and abs(data) > 2**53 - 1: return str(data)
    return data

def payload(raw):
    match = re.search(r'<script[^>]*id=["\x27]page-payload["\x27][^>]*>(.*?)</script>', raw, re.S)
    if not match: raise ValueError('Missing retained page-payload')
    return json.loads(match[1]), match

def member(t, name):
    matches = [m for m in t.getmembers() if m.name.endswith('/' + name)]
    if len(matches) != 1 or not matches[0].isfile(): raise ValueError('Ambiguous archive member: ' + name)
    return t.extractfile(matches[0]).read()

def groups(rows, mode='sum'):
    buckets = collections.defaultdict(list)
    for row in rows: buckets[(row['phase'], row['stage'])].append(row)
    out = []
    for key, members in buckets.items():
        members.sort(key=lambda p: (-(int(p['e'])-int(p['b'])), p['process']))
        durations = [int(p['e'])-int(p['b']) for p in members]
        out.append(dict(key=' / '.join(key), members=[p['process'] for p in members],
                        score_ns=str(sum(durations) if mode == 'sum' else max(durations))))
    return sorted(out, key=lambda g: (-int(g['score_ns']), g['key']))

def write_rankings(out, ranks):
    for name, rows in ranks.items():
        with (out/f'ranking_{name}.csv').open('w', newline='') as f:
            writer = csv.writer(f); writer.writerow(['rank','key','score_ns','member_count','members_json'])
            for n,g in enumerate(rows,1): writer.writerow([n,g['key'],g['score_ns'],len(g['members']),json.dumps(g['members'])])

def build(archive, full_archive, out):
    out.mkdir(parents=True, exist_ok=True); (out/'original').mkdir(exist_ok=True)
    sources = []
    for path in (archive, full_archive):
        digest = sha(path)
        sidecar = Path(str(path)+'.sha256')
        if sidecar.exists() and sidecar.read_text().split()[0] != digest: raise ValueError('Archive sidecar hash mismatch')
        shutil.copy2(path, out/'original'/path.name)
        sources.append(dict(name=path.name, sha256=digest, size=path.stat().st_size))
    with tarfile.open(archive) as t:
        highraw = member(t,'HIGH_LATENCY_PROCESS_HARDWARE_TIMELINE.html').decode()
        conraw = member(t,'CONCURRENCY_UTILIZATION.html').decode()
        e2eraw = member(t,'E2E_PROCESS_TIMELINE.html').decode()
        H,_ = payload(highraw); C,_ = payload(conraw); E,_ = payload(e2eraw)
        original_manifest = json.loads(member(t,'offline_acceptance_manifest.json'))
    counts = collections.Counter(r['g'] for r in E['rows'])
    if counts['request'] != 1: raise ValueError('This adapter requires one retained request')
    proc = [r for r in E['rows'] if r['g']=='process']
    forwards = [r for r in E['rows'] if r['g']=='forward']
    pmap = {p['process']:p for p in proc}
    assert len(pmap)==len(proc) and len(H['kernels'])==counts['strict_owned_kernel']
    for h in H['processes']:
        p=pmap[h['process']]; assert (p['b'],p['e'])==(h['b'],h['e'])
    assert H['samples']==C['samples']
    begin,end=E['begin'],E['end']; cut=max(r['e'] for r in E['rows'] if r['g']!='request')
    assert begin < cut <= end
    device=H['device']['physical_device_id']
    scope=dict(origin_ns=str(begin),original_request_end_ns=str(end),display_end_ns=str(cut),
               original_span_ns=str(end-begin),display_span_ns=str(cut-begin),omitted_tail_ns=str(end-cut),
               counts=dict(counts),physical_device_id=device,
               traced='retained R07: request anchors, 29 forwards with layer envelopes, HIPTX Process, HIP runtime, strictly owned HIP kernels, aligned SE samples',
               omission='Request-only tail is excluded from the default display; source completion stays intact. Interior gaps remain on the true clock. No other-device evidence, full-device kernel census, or sampling call endpoints are present in this retained payload.',
               formal_r10_regeneration=False,original_acceptance_untouched=True)
    source_info=dict(archives=sources,source_manifest=original_manifest,scope=scope)
    dump(out/'SOURCE_AND_SCOPE.json',source_info)
    attachments=collections.defaultdict(set)
    for a in H['attachments']: attachments[a['process_range']].add(a['matched_kernel_family'])
    hardware_proc=[p for p in proc if any(h['event_id']==p['event'] and h['stage']==p['stage'] and h['matched_kernel_family'] in attachments[p['process']] for h in H['hardware'])]
    ranks={'high':groups(H['processes']), 'hardware':groups(hardware_proc), 'raw':groups(proc,'max')}
    fg=[]
    for f in forwards:
        members=[p['process'] for p in proc if p['forward']==f['forward']]
        segments=[r for r in C['kernel_concurrency'] if r['n']>0 and r['b']<f['e'] and r['e']>f['b']]
        busy=sum(min(r['e'],f['e'])-max(r['b'],f['b']) for r in segments)
        overlap=sum(min(r['e'],f['e'])-max(r['b'],f['b']) for r in segments if r['n']>1)
        fg.append(dict(key='forward '+f['forward']+' / '+f['phase'],forward=f,members=members,score_ns=str(busy),overlap_ns=str(overlap),peak=max([r['n'] for r in segments] or [0])))
    ranks['concurrency']=sorted(fg,key=lambda g:(-int(g['score_ns']),g['key']))
    ss=sorted(enumerate(C['samples']),key=lambda x:x[1]['t'])
    intervals=[dict(key=f'sample {a[0]} → {b[0]}',members=[a[0],b[0]],b=str(a[1]['t']),e=str(b[1]['t']),score_ns=str(b[1]['t']-a[1]['t'])) for a,b in zip(ss,ss[1:]) if b[1]['t']>a[1]['t']]
    ranks['unknown']=sorted(intervals,key=lambda g:(-int(g['score_ns']),g['key']))
    launch=[]
    for k,ms in __import__('itertools').groupby(sorted(C['gaps'],key=lambda r:(r['stage'],r['kind'])),key=lambda r:(r['stage'],r['kind'])):
        ms=sorted(ms,key=lambda r:(-r['duration'],r['id']))
        launch.append(dict(key=' / '.join(k),members=[r['id'] for r in ms],score_ns=str(ms[0]['duration'])))
    ranks['launch']=sorted(launch,key=lambda g:(-int(g['score_ns']),g['key']))
    dump(out/'RANKINGS.json',ranks);write_rankings(out,ranks)
    scope_html=f'''<section class="scope" id="trace-scope"><h2>先看采集范围与省略范围</h2><p>本例是单 batch、1 个 Request、物理 DCU{device}；29 次 forward（6 次 prefill chunk、23 次 decode）、17,168 个 Process、428,023 条 HIP runtime、29,964 个唯一严格归属 kernel。两种 kernel 轨道展示同一批事件，不可重复计数。完整时间线共 507,005 条区间。</p><p>原 Request {((end-begin)/1e9):.9f} s；默认保留 {((cut-begin)/1e9):.9f} s；省略末尾仅有 Request、没有后续 Process/runtime/kernel 等 trace 的 <strong>{end-cut:,} ns（{(end-cut)/1e6:.6f} ms，{(end-cut)/(end-begin)*100:.4f}%）</strong>。原始结束点 {end} ns 和完整归档仍保留；内部无事件间隔不删除。边界不等同于所有设备活动均被采集。</p><p>R07 观测时间和原始 SE 采样点在同一轴；R08 硬件计数是重放投影属性，单列展示，不拼接其重放时间轴。FX 流量为推断下界；没有验证的 HBM/DRAM、实际 occupancy 和其他设备信息标为 unavailable。采样点之间没有连续观测，不连线、不补零；缺少采样调用起止字段，不能把相邻点间距判定为停采时长。</p><p>这是已封存 20260806 记录的展示补充，没有重新运行模型或生成新的性能测量。前 20 是可切换的导航窗口；全部组、实例和源数据保留。</p></section>'''
    nav='<nav><a href="index.html">报告入口</a><a href="HIGH_LATENCY_PROCESS_HARDWARE_TIMELINE.html">高延迟与硬件</a><a href="CONCURRENCY_UTILIZATION.html">并发 / 利用率 / 未知间隔</a><a href="E2E_PROCESS_TIMELINE_LOSSLESS.html">完整过程时间线</a><a href="SOURCE_AND_SCOPE.json">来源与省略量</a></nav>'
    css=(ASSETS/'ranked.css').read_text()
    js='\n'.join((ASSETS/n).read_text() for n in ['single_batch_boot.js','timeline_core.js','group_band.js','single_batch_views.js'])
    for mode,title,name,data in [('high','高延迟 Process 与硬件证据','HIGH_LATENCY_PROCESS_HARDWARE_TIMELINE.html',dict(high=H)),('concurrency','设备内并发、原始利用率与未知间隔','CONCURRENCY_UTILIZATION.html',dict(concurrency=C,kernels=H['kernels'],device=H['device']))]:
        D=dict(mode=mode,scope=scope,provenance=sources,processes=proc,forwards=forwards,rankings={k:v for k,v in ranks.items() if (k in ('high','hardware'))==(mode=='high')},**data)
        data_json=json.dumps(safe(D),ensure_ascii=False,separators=(',',':')).replace('<','\\u003c')
        (out/name).write_text(f'<!doctype html><html lang="zh-CN"><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>{title}</title><style>{css}</style><main><h1>Perf Trace · {title}</h1>{nav}{scope_html}<div id="rankedRoot"></div><section id="details"><h2>源记录与证据详情</h2><pre id="detailText">点击矩形、原始点、组内横线或源表记录。</pre></section></main><script type="application/json" id="page-payload">{data_json}</script><script>{js}</script></html>')
    # Keep the complete, audited replay002 trace; change only presentation of its Request tail.
    with tarfile.open(full_archive) as t:
        raw=member(t,'E2E_PROCESS_TIMELINE_LOSSLESS.html').decode(); B,match=payload(raw)
        assert len(B['rows'])==len(E['rows']) and int(B['origin_ns'])==begin
        origin=int(B['origin_ns'])
        for a,b in zip(E['rows'],B['rows']):
            assert (a['g'],a['b'],a['e'])==(b['g'],origin+b['b'],origin+b['e'])
        trace=member(t,'E2E_PROCESS_TIMELINE.full.perfetto.json')
        (out/'E2E_PROCESS_TIMELINE.full.perfetto.json').write_bytes(trace)
        dump(out/'original_full_timeline_manifest.json',json.loads(member(t,'full_timeline_manifest.json')))
    del trace,e2eraw,E
    raw=raw[:match.start(1)]+json.dumps(safe(B),ensure_ascii=False,separators=(',',':')).replace('<','\\u003c')+raw[match.end(1):]
    patch=f"\nconst VIEW_SCOPE={json.dumps(scope)};const originalDisplayEnd=D.end;D.end={cut-begin};for(const r of D.rows)if(r.g==='request'){{r.original_display_end=r.e;r.e=D.end;r.display_end_ns=VIEW_SCOPE.display_end_ns;}}\n"
    hook="const D=JSON.parse(document.getElementById('page-payload').textContent);"
    assert raw.count(hook)==1;raw=raw.replace(hook,hook+patch)
    raw=raw.replace('found.slice(0,200).map(h=>exact(h.r))','found.map(h=>exact(h.r))').replace('truncated:found.length>200','truncated:false')
    raw=raw.replace('labelWidth=170,laneHeight=15','labelWidth=210,laneHeight=36')
    raw=raw.replace('<main>','<main>'+nav+scope_html,1)
    # An absolute integer-ns jump supplements the original relative-ms inputs.
    ui='<div class="controls"><label>绝对 ns 开始 <input id="absolute-b"></label><label>结束 <input id="absolute-e"></label><button id="absolute-go">精确 ns 跳转</button><span id="absolute-state"></span></div>'
    raw=raw.replace('<canvas',ui+'<canvas',1)
    extra="""window.SINGLE_FULL={scope:VIEW_SCOPE,rows:D.rows,setView,get view(){return [lo,hi]},get hits(){return hits},exact};
 document.getElementById('absolute-b').value=D.origin_ns;document.getElementById('absolute-e').value=VIEW_SCOPE.display_end_ns;
 document.getElementById('absolute-go').onclick=()=>{try{const a=BigInt(document.getElementById('absolute-b').value)-BigInt(D.origin_ns),b=BigInt(document.getElementById('absolute-e').value)-BigInt(D.origin_ns);if(a<0n||b>BigInt(D.end)||b<=a)throw Error('Range outside the displayed traced window');setView(Number(a),Number(b));document.getElementById('absolute-state').textContent=String(b-a)+' ns';}catch(e){document.getElementById('absolute-state').textContent=e.message;}};
"""
    raw=raw.replace('window.addEventListener(\'resize\',schedule);',extra+"window.addEventListener('resize',schedule);")
    (out/'E2E_PROCESS_TIMELINE_LOSSLESS.html').write_text(raw)
    stats=dict(counts=dict(counts),high_groups=len(ranks['high']),high_processes=len(H['processes']),forward_groups=len(fg),raw_process_groups=len(ranks['raw']),samples=len(C['samples']),ineligible_samples=sum(not r['eligible'] for r in C['samples']),sample_intervals=len(intervals),launch_gaps=len(C['gaps']),launch_groups=len(launch),kernel_peak=max(r['n'] for r in C['kernel_concurrency']),queue_peak=max(r['n'] for r in C['queue_concurrency']),hardware_rows=len(H['hardware']),hardware_processes=len(hardware_proc),hardware_groups=len(ranks['hardware']),high_top20_members=sum(len(g['members']) for g in ranks['high'][:20]))
    dump(out/'BUILD_MANIFEST.json',dict(version=1,formal_r10_regeneration=False,original_acceptance_untouched=True,scope=scope,stats=stats,sources=sources,full_trace_sha256=sha(out/'E2E_PROCESS_TIMELINE.full.perfetto.json'),generator_sha256=sha(__file__),assets={p.name:sha(p) for p in sorted(ASSETS.iterdir()) if p.is_file()}))
    (out/'index.html').write_text(f'<!doctype html><html lang="zh-CN"><meta charset="utf-8"><title>Perf Trace 单 batch R10 时间线报告</title><style>{css}</style><main><h1>Perf Trace · 单 batch R10 时间线报告</h1>{nav}{scope_html}<section><h2>浏览顺序</h2><p><a href="HIGH_LATENCY_PROCESS_HARDWARE_TIMELINE.html">高延迟 Process 与硬件时间线</a>：128 条已标记实例，按 phase + stage 分组；组内可逐条切换，梯形与真实时间线相互定位。</p><p><a href="CONCURRENCY_UTILIZATION.html">并发、原始利用率、未知采样间隔及 launch gap</a>：DCU1 kernel 峰值 2、queue 峰值 1；各类前 20 导航，可查看任意排名。</p><p><a href="E2E_PROCESS_TIMELINE_LOSSLESS.html">完整过程时间线 · 精确纳秒离线浏览</a>：507,005 个区间、原有 top10 配色、全部矩形标签、源记录与绝对 ns 跳转。保留源记录数量，Request 仅裁去未 trace 尾部。</p><p><a href="E2E_PROCESS_TIMELINE.full.perfetto.json">完整 Perfetto JSON</a> · <a href="RANKINGS.json">全部分组排名</a> · <a href="BUILD_MANIFEST.json">构建清单</a></p></section><section><h2>本例边界</h2><p>kernel 重叠并不代表双卡或多请求调度，也不代表已实现吞吐收益。硬件重放值不作为 R07 延迟轴。相邻采样点之间的空白不等同于零利用率、GPU idle 或停采证据。原封存归档完整保存在 original/，可独立校验和恢复。</p></section></main></html>')
    print(json.dumps(stats,ensure_ascii=False,indent=2),flush=True)

if __name__=='__main__':
    a=argparse.ArgumentParser(description=__doc__)
    a.add_argument('--source-archive',type=Path,required=True);a.add_argument('--full-archive',type=Path,required=True);a.add_argument('--output-dir',type=Path,required=True)
    args=a.parse_args();build(args.source_archive,args.full_archive,args.output_dir)
