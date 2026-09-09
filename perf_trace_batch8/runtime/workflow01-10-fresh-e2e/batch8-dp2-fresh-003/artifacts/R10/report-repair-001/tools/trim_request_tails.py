#!/usr/bin/env python3
"""Clip only displayed client Request tails; preserve all source data and non-request events."""
from pathlib import Path
import csv,json,hashlib,html
ROOT=Path(__file__).resolve().parents[1];R09=ROOT.parent.parent/'R09/continuation_001';csv.field_size_limit(2**31-1)
def sha(p):
 h=hashlib.sha256()
 with p.open('rb') as f:
  for b in iter(lambda:f.read(8<<20),b''):h.update(b)
 return h.hexdigest()
def rows(n):
 with (R09/'tables'/(n+'.csv')).open() as f:return list(csv.DictReader(f))
qs=rows('request_timeline');ps=rows('process_timeline');ks=rows('kernel_timeline');ends={q['request_id']:int(q['begin_ns']) for q in qs}
for p in ps:
 req=p['request_id'];ends[req]=max(ends[req],int(p['end_ns']))
 for rr in json.loads(p['layer_forward_context']).values():
  for r in rr:ends[req]=max(ends[req],int(r['end_ns']))
 fields=json.loads(p['hip_runtime_context_schema']);endidx=fields.index('end_ns')
 for values in json.loads(p['hip_runtime_context']):ends[req]=max(ends[req],int(values[endidx]))
for k in ks:ends[k['request_id']]=max(ends[k['request_id']],int(k['end_ns']))
origin=min(int(q['begin_ns']) for q in qs);full_end=max(int(q['end_ns']) for q in qs);display_end=max(ends.values());scope={'source_origin_ns':str(origin),'source_request_envelope_end_ns':str(full_end),'display_end_ns':str(display_end),'original_envelope_duration_ns':str(full_end-origin),'display_envelope_duration_ns':str(display_end-origin),'omitted_global_tail_ns':str(full_end-display_end),'request_ends':{},'display_rule':'clip each Request at maximum end of retained process/kernel/HIP runtime/layer/forward context; keep source Request outcome unchanged','traced_scope':'all eight requests; declared first prefill/first decode process targets and their exact owned kernels/runtime/context','not_visualized':'later invocations outside the declared first-prefill/first-decode scope; their compute/queue/communication decomposition unavailable','sources':[{'path':str(R09/'tables'/(n+'.csv')),'sha256':sha(R09/'tables'/(n+'.csv'))} for n in ['request_timeline','process_timeline','kernel_timeline']]}
for q in qs:
 end=ends[q['request_id']];assert int(q['begin_ns'])<end<=int(q['end_ns']);scope['request_ends'][q['request_id']]={'display_end_ns':str(end),'source_end_ns':q['end_ns'],'source_begin_ns':q['begin_ns'],'omitted_tail_ns':str(int(q['end_ns'])-end),'display_duration_ns':str(end-int(q['begin_ns'])),'source_duration_ns':q['duration_ns'],'rank':q['rank']}
(ROOT/'REQUEST_VIEW_SCOPE.json').write_text(json.dumps(scope,ensure_ascii=False,indent=2)+'\n')
trs=''.join(f'<tr><td>Request {i+1} / rank{q["rank"]}</td><td>{int(q["duration_ns"])/1e9:.3f}</td><td>{int(scope["request_ends"][q["request_id"]]["display_duration_ns"])/1e9:.3f}</td><td>{int(scope["request_ends"][q["request_id"]]["omitted_tail_ns"])/1e9:.3f}</td></tr>' for i,q in enumerate(qs))
note='<section class="notice" id="traceScope"><h2>先读：追踪了什么，省略了什么</h2><p><strong>已追踪：</strong>8 个请求各自声明的首次 prefill/decode Process、严格归属 kernel、HIP Runtime，以及对应 layer/forward 上下文。完整是指这一声明目标范围。</p><p><strong>本页省略：</strong>每个请求最后一条上述细粒度记录之后的客户端等待尾部，以及未进入此追踪范围的后续执行。没有把省略时间解释为设备空闲；也没有将 Request 的真实完成时间提前。Request 长条现在仅显示保留的追踪视窗。</p><p><strong>整张图：</strong>原客户端包络 '+f'{(full_end-origin)/1e9:.3f}'+' s；显示 '+f'{(display_end-origin)/1e9:.3f}'+' s；尾部省略 <strong>'+f'{(full_end-display_end)/1e9:.3f}'+' s</strong>（'+f'{100*(full_end-display_end)/(full_end-origin):.2f}'+'%）。各请求省略时长互有重叠，不能相加作为整图省略时间。</p><table><thead><tr><th>请求 / rank</th><th>客户端真实总耗时 s</th><th>保留视窗 s</th><th>省略尾部 s</th></tr></thead><tbody>'+trs+'</tbody></table><p>精确纳秒和真实客户端完成时间保留在事件详情的 original / source_request_end_ns 中。<a href="../REQUEST_VIEW_SCOPE.json">裁剪范围、精确时间与源表 SHA-256</a></p></section>'
source=ROOT/'original/acceptance/E2E_PROCESS_TIMELINE_LOSSLESS.html';s=source.read_text();data=s.split('<script>const PAYLOAD=',1)[1].split(';</script>',1)[0]
s=s.replace('完整过程时间线 · 精确纳秒离线浏览','已追踪过程时间线 · 裁剪无 trace 尾部').replace('<main>','<main>'+note,1)
s=s.replace('<script>const PAYLOAD=', '<script>const REQUEST_VIEW_SCOPE='+json.dumps(scope,separators=(',',':'))+';</script><script>const PAYLOAD=',1)
needle=';(context?contexts:events).push(event);'
replacement=";if(kind==='request'){const cut=REQUEST_VIEW_SCOPE.request_ends[row.request_id];event.source_request_end_ns=event.end_ns;event.source_request_duration_ns=row.duration_ns;event.omitted_untraced_tail_ns=cut.omitted_tail_ns;event.display_interval_reason='Request display restricted to traced window; original client outcome preserved';event.end_ns=cut.display_end_ns;event.end=ns(cut.display_end_ns)-origin;event.event='Request traced window';}(context?contexts:events).push(event);"
assert needle in s;s=s.replace(needle,replacement,1)
old="const extent=[0n,req.reduce((v,r)=>ns(r.end_ns)>v?ns(r.end_ns):v,origin)-origin];";assert old in s;s=s.replace(old,"const extent=[0n,ns(REQUEST_VIEW_SCOPE.display_end_ns)-origin];",1)
assert s.split('<script>const PAYLOAD=',1)[1].split(';</script>',1)[0]==data
out=ROOT/'acceptance/E2E_PROCESS_TIMELINE_LOSSLESS.html';out.write_text(s)
# The revised human entry points open this clipped viewer by default.
for p,oldurl,newurl in [(ROOT/'index.html','original/acceptance/E2E_PROCESS_TIMELINE_LOSSLESS.html','acceptance/E2E_PROCESS_TIMELINE_LOSSLESS.html'),(ROOT/'acceptance/index.html','../original/acceptance/E2E_PROCESS_TIMELINE_LOSSLESS.html','E2E_PROCESS_TIMELINE_LOSSLESS.html')]:
 text=p.read_text().replace(oldurl,newurl).replace('全量精确时间线：8 请求 / 12,544 过程 / 23,660 唯一 kernel','已追踪范围精确时间线：已裁剪无 trace 的 Request 尾部');p.write_text(text)
# Companion explanation also shows only the retained request windows.
width=1360;left=200;plot=1110;x=lambda t:left+(int(t)-origin)/(display_end-origin)*plot
svg=[f'<svg viewBox="0 0 {width} 760" role="img" aria-label="裁剪无 trace 尾部后的八请求时间线" xmlns="http://www.w3.org/2000/svg"><rect width="1360" height="760" fill="#0b1728"/>']
for sec in [0,25,50,75,100,125,150,175]:
 xx=x(origin+sec*10**9);svg.append(f'<path d="M{xx:.3f} 35V720" stroke="#31435b"/><text x="{xx:.3f}" y="25" fill="#bfd1e8">{sec} s</text>')
for i,q in enumerate(qs):
 r=scope['request_ends'][q['request_id']];y=55+i*80;b=int(q['begin_ns']);e=int(r['display_end_ns']);svg.append(f'<text x="8" y="{y+18}" fill="#dce9f8">Request {i+1} / rank{q["rank"]}</text><text x="8" y="{y+40}" fill="#cbb7e4">省略 {int(r["omitted_tail_ns"])/1e9:.3f} s</text><rect x="{x(b):.4f}" y="{y}" width="{x(e)-x(b):.4f}" height="20" fill="#586579"/>')
 for p in ps:
  if p['request_id']==q['request_id']:svg.append(f'<rect x="{x(p["begin_ns"]):.5f}" y="{y+32}" width="{max(.4,x(p["end_ns"])-x(p["begin_ns"])):.5f}" height="15" fill="#68b9ff"/>')
svg.append('</svg>');style=(ROOT/'original/tools/revision_001/viewer.css').read_text();page='<!doctype html><html lang="zh-CN"><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>Request 尾部裁剪与追踪范围</title><style>'+style+'</style><header><a href="index.html">排名时间线入口</a><h1>Request 尾部裁剪与追踪范围</h1></header><main>'+note+'<section><p>下图已移除无细粒度 trace 的尾部。灰条=保留的 Request 追踪视窗；蓝线=原始 Process。灰条内部的空隙也不能解释为 GPU 空闲。细线最小显示 0.4 px；精确区间可在交互时间线核对。</p>'+''.join(svg)+'<p><a href="E2E_PROCESS_TIMELINE_LOSSLESS.html">打开裁剪后的精确交互时间线</a></p></section></main></html>\n';(ROOT/'acceptance/REQUEST_COVERAGE.html').write_text(page)
receipt={'status':'built_pending_browser_and_independent_scope_audit','source_page_sha256':sha(source),'output_page_sha256':sha(out),'embedded_payload_sha256':hashlib.sha256(data.encode()).hexdigest(),'payload_unchanged':True,'request_view_scope_sha256':sha(ROOT/'REQUEST_VIEW_SCOPE.json'),'script_sha256':sha(Path(__file__))}
(ROOT/'validation/REQUEST_TRIM_BUILD.json').write_text(json.dumps(receipt,indent=2)+'\n');print('TRIM_BUILT',scope['original_envelope_duration_ns'],scope['display_envelope_duration_ns'],scope['omitted_global_tail_ns'])
