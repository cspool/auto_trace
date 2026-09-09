#!/usr/bin/env python3
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
req=rows('request_timeline');ps=rows('process_timeline');ks=rows('kernel_timeline');out=[]
for q in req:
 pp=[p for p in ps if p['request_id']==q['request_id']];kk=[k for k in ks if k['request_id']==q['request_id']];pe=max(int(p['end_ns']) for p in pp);ke=max(int(k['end_ns']) for k in kk);b=int(q['begin_ns']);e=int(q['end_ns']);last=max(pe,ke)
 out.append({'request_id':q['request_id'],'ordinal':int(q['measured_request_ordinal']),'rank':q['rank'],'request_begin_ns':str(b),'request_end_ns':str(e),'request_duration_ns':str(e-b),'last_selected_process_end_ns':str(pe),'last_selected_kernel_end_ns':str(ke),'tail_after_last_selected_process_or_kernel_ns':str(e-last),'last_process_offset_ns':str(pe-b),'http_status':q['http_status'],'completion_tokens':q['completion_tokens'],'selected_process_count':len(pp),'selected_kernel_count':len(kk)})
report={'scope':'R09 declared first-prefill/first-decode universe; Request is client outstanding interval, not continuous device execution','sources':[{'path':str(R09/'tables'/(n+'.csv')),'sha256':sha(R09/'tables'/(n+'.csv'))} for n in ['request_timeline','process_timeline','kernel_timeline']],'requests':out,'tail_breakdown':'unavailable: cannot assign remaining request time to compute/queue/communication from this selected process timeline'}
(ROOT/'REQUEST_COVERAGE.json').write_text(json.dumps(report,ensure_ascii=False,indent=2)+'\n')
origin=min(int(q['begin_ns']) for q in req);extent=max(int(q['end_ns']) for q in req)-origin;width=1360;left=200;plot=1110
x=lambda t:left+(int(t)-origin)/extent*plot
svg=[f'<svg viewBox="0 0 {width} 780" role="img" aria-label="八请求完整客户端区间与已纳入的过程追踪范围" xmlns="http://www.w3.org/2000/svg"><defs><pattern id="unknown" width="8" height="8" patternUnits="userSpaceOnUse"><path d="M0 8L8 0" stroke="#bc9fdf" stroke-width="1"/></pattern></defs><rect width="1360" height="780" fill="#0b1728"/>']
for s in [0,100,200,300,400,500,600,700]:
 xx=left+s*1e9/extent*plot;svg.append(f'<path d="M{xx:.3f} 40V740" stroke="#31435b"/><text x="{xx:.3f}" y="26" fill="#bfd1e8" font-size="15">{s} s</text>')
for i,(q,r) in enumerate(zip(req,out)):
 y=60+i*82;b=int(q['begin_ns']);e=int(q['end_ns']);last=max(int(r['last_selected_process_end_ns']),int(r['last_selected_kernel_end_ns']));svg.append(f'<text x="8" y="{y+20}" fill="#dce9f8" font-size="16">Request {i+1} · rank{q["rank"]}</text><text x="8" y="{y+44}" fill="#afc4dc" font-size="13">客户端 {(e-b)/1e9:.3f} s</text><rect x="{x(b):.3f}" y="{y}" width="{x(e)-x(b):.3f}" height="25" fill="#586579"/><rect x="{x(last):.3f}" y="{y}" width="{x(e)-x(last):.3f}" height="25" fill="url(#unknown)"/>')
 for p in ps:
  if p['request_id']==q['request_id']:
   xx=x(p['begin_ns']);ww=x(p['end_ns'])-xx;svg.append(f'<rect x="{xx:.5f}" y="{y+37}" width="{max(.4,ww):.5f}" height="15" fill="#68b9ff"/>')
 svg.append(f'<text x="{x(last)+8:.3f}" y="{y+52}" fill="#d4b8f0" font-size="13">最后已纳入过程/kernel 后 {(e-last)/1e9:.3f} s：缺少该范围的细粒度分解</text>')
svg.append('</svg>')
style=(ROOT/'original/tools/revision_001/viewer.css').read_text()
intro='''<p>Request 长条来自 R07 客户端请求结果，表示从发出请求到收到最终响应；不是 GPU 持续执行状态。八个请求均 HTTP 200，输出 1024 token。</p><p>当前“完整过程时间线”完整覆盖的是 R06/R09 声明的每请求首次 prefill/decode 目标，并非每个请求全生命周期的所有步骤。后续执行没有进入本页细粒度展示；不能仅据页面空白断言没有执行，也不能据此判断原始采集库是否另有未归属记录。</p><p>例如 Request 1：总耗时 666.191 s，最后已纳入 Process 在请求开始后 49.299 s 结束，之后 616.892 s 无对应的过程/kernel 分解。现有展示无法确定这段时间分别用于计算、排队或通信。</p><p class="notice">灰条=客户端未完成区间；蓝色细线=已纳入的实际 Process；斜纹=最后已纳入 Process/kernel 之后尚未完成的时间，不能解读为 GPU 空闲或持续忙碌。细线最小显示宽度 0.4 px 仅用于可见性，精确区间保留在原始时间线。</p>'''
header='<tr><th>请求 / rank</th><th>客户端总耗时 s</th><th>最后 Process 结束（请求相对）s</th><th>后续未细分时长 s</th><th>HTTP / 输出 token</th></tr>'
trs=''.join(f'<tr><td>{i+1} / {r["rank"]}</td><td>{int(r["request_duration_ns"])/1e9:.3f}</td><td>{int(r["last_process_offset_ns"])/1e9:.3f}</td><td>{int(r["tail_after_last_selected_process_or_kernel_ns"])/1e9:.3f}</td><td>{r["http_status"]} / {r["completion_tokens"]}</td></tr>' for i,r in enumerate(out))
page='<!doctype html><html lang="zh-CN"><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>为什么 Request 后半段仍然很长</title><style>'+style+'</style><header><a href="index.html">排名时间线入口</a><h1>Request 未完成区间与过程追踪覆盖范围</h1></header><main><section>'+intro+''.join(svg)+'</section><section><table><thead>'+header+'</thead><tbody>'+trs+'</tbody></table><p><a href="../REQUEST_COVERAGE.json">全部精确时间、来源表及 SHA-256</a> · <a href="../original/acceptance/E2E_PROCESS_TIMELINE_LOSSLESS.html">原始完整时间线（声明目标范围）</a></p></section></main></html>\n'
(ROOT/'acceptance/REQUEST_COVERAGE.html').write_text(page)
for p,prefix in [(ROOT/'index.html','acceptance/'),(ROOT/'acceptance/index.html','')]:
 s=p.read_text();s=s.replace('<ul>','<ul><li><a href="'+prefix+'REQUEST_COVERAGE.html">为什么 Request 后半段仍然很长：时间范围与证据解释</a></li>',1);p.write_text(s)
print('REQUEST_SCOPE_EXPLANATION_WRITTEN',len(out))
