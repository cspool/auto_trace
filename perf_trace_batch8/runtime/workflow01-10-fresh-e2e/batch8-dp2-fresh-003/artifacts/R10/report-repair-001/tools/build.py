#!/usr/bin/env python3
"""Presentation-only revision of sealed R10 HTML, preserving every embedded data byte."""
from pathlib import Path
import json,hashlib,shutil,sys,datetime,time
ROOT=Path(__file__).resolve().parents[1];SOURCE=ROOT.parent/'continuation_001';TOOLS=ROOT/'tools'
def sha(p):
 h=hashlib.sha256()
 with Path(p).open('rb') as f:
  for b in iter(lambda:f.read(8<<20),b''):h.update(b)
 return h.hexdigest()
def record(p):return {'path':str(p),'size':p.stat().st_size,'sha256':sha(p)}
def dump(p,x):p.write_text(json.dumps(x,ensure_ascii=False,indent=2)+'\n')
def main():
 start=time.time();audit=json.loads((SOURCE/'R10_COMPLETION_AUDIT.json').read_text());assert audit['status']=='complete' and audit['coverage_target_met'] and audit['all_eight_requests_have_exact_trace_coverage']
 manifest=json.loads((SOURCE/'artifact_manifest.json').read_text());inputs=[]
 for x in manifest['files']:
  p=Path(x['path']);assert p.is_file() and p.stat().st_size==x['size'] and sha(p)==x['sha256'],p
  inputs.append(x)
 print('SEALED_R10_INPUTS_VERIFIED',len(inputs),flush=True)
 original=ROOT/'original';accept=ROOT/'acceptance';assert not accept.exists(),'Retain earlier candidate before rebuilding'
 
 if not original.exists():shutil.copytree(SOURCE,original)
 else:
  for x in inputs:assert sha(original/Path(x['path']).relative_to(SOURCE))==x['sha256']
 accept.mkdir()
 css=(TOOLS/'ranked.css').read_text();code=(TOOLS/'ranked.js').read_text()+'\n'+(TOOLS/'group_band.js').read_text();viewer=(SOURCE/'tools/revision_001/viewer.js').read_text();base_viewer=viewer[:viewer.index('(async()=>{try{const tables=await loadTables();')]
 boot="""(async()=>{try{const tables=await loadTables();window.TABLES=tables;const matrix=coverage(tables);if(matrix.length!==8)throw Error('Eight-request coverage gate');if(PAYLOAD.mode==='hardware')hardwareRanked(tables);else concurrencyRanked(tables);text($('loading'),'完整离线数据已加载；排名只控制展示，源记录全部保留。');window.PAGE_READY=true;RANKED.ready=true;}catch(error){text($('loading'),'页面错误：'+error.message);window.PAGE_ERROR=error.message;throw error;}})();"""
 outputs=[]
 for name in ['HIGH_LATENCY_PROCESS_HARDWARE_TIMELINE.html','CONCURRENCY_UTILIZATION.html']:
  before=(SOURCE/'acceptance'/name).read_text();prefix,payload_and_tail=before.split('<script>const PAYLOAD=',1);encoded=payload_and_tail.split(';</script>',1)[0];payload=json.loads(encoded)
  prefix=prefix.replace('</style>',css+'</style>').replace('<a href="index.html">验收入口</a>','<a href="index.html">排名时间线入口</a> · <a href="../original/acceptance/index.html">原始完整 R10</a>')
  intro='<section class="rank-intro"><h2>排名时间线 · 折叠梯形分组修订 5</h2><p>默认前 20 项/组，可定位任意排名或显示全部。高延迟、并发和原始采样的分组使用梯形时间带：每条横线保留一个 Process 的真实起止；可展开为每行 36 px，点击横线定位实例。高延迟组可切换所有组内实例；可放大、平移、精确纳秒跳转，点击查看源记录。排名不删减数据，原始完整 R10 另行保留。</p><p>所有横轴来自 R07 观测。蓝色为观测过程；双卡并发是 R07 派生计数；绿色点为原始利用率；紫色斜纹为未知；黄色虚线框为 R08 重放/静态硬件旁证。后者不代表 R07 实测利用率、根因或加速比。</p></section><div id="rankedRoot"></div>'
  pos=prefix.index('<section><h2>八请求覆盖率');prefix=prefix[:pos]+intro+prefix[pos:]
  if payload['mode']=='concurrency':
   begin=prefix.index('<section><p id="liveState">');end=prefix.index('<section><h2>精确源记录与证据',begin);prefix=prefix[:begin]+prefix[end:]
  result=prefix+'<script>const PAYLOAD='+encoded+';</script><script>'+base_viewer+'\n'+code+'\n'+boot+'</script></html>\n'
  out=accept/name;out.write_text(result)
  assert result.split('<script>const PAYLOAD=',1)[1].split(';</script>',1)[0]==encoded
  outputs.append({'before':record(SOURCE/'acceptance'/name),'after':record(out),'payload_sha256':hashlib.sha256(encoded.encode()).hexdigest(),'payload_bytes_unchanged':True,'embedded_table_row_counts':{n:t['row_count'] for n,t in payload['tables'].items()}})
  print('PAGE_BUILT',name,out.stat().st_size,flush=True)
 links=[('acceptance/HIGH_LATENCY_PROCESS_HARDWARE_TIMELINE.html','高延迟过程与硬件：排名时间线'),('acceptance/CONCURRENCY_UTILIZATION.html','双卡并发、原始利用率、未知间隙：排名时间线'),('original/acceptance/index.html','原始完整 R10 验收入口（字节不变）'),('original/acceptance/E2E_PROCESS_TIMELINE_LOSSLESS.html','全量精确时间线：8 请求 / 12,544 过程 / 23,660 唯一 kernel'),('original/acceptance/E2E_PROCESS_TIMELINE.full.perfetto.json','完整离线 Perfetto JSON'),('validation/REVISION_AUDIT.json','本次独立展示修订审计'),('validation/BROWSER_AUDIT.json','离线交互与截图检查'),('BUILD_MANIFEST.json','输入、输出与数据字节保留清单')]
 style=(SOURCE/'tools/revision_001/viewer.css').read_text()+css
 index='<!doctype html><html lang="zh-CN"><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>R10 排名时间线报告</title><style>'+style+'</style><header><h1>R10：高延迟、硬件与双卡证据时间线</h1></header><main><section><p>同一已封存 Batch8 DP2 观测样例；8 个请求均有首个 prefill/decode 过程 trace，rank0→DCU0，rank1→DCU1。此次仅修订展示，不进行新测量。</p><p>分组主图使用梯形时间带：每个 Process 是一条真实起止横线，左侧开始轴和右侧结束轴分别标真实时间，再连接端点成轮廓（横线长度不表示时长）；长间隔可折叠，// 标记压缩位置；可展开每段真实起止/间隔/压缩比例，取消折叠回到原始时间。可逐行展开并点击定位。轮廓填充只表示分组，不能解释为连续执行。每类默认展示前 20 项/组。高延迟按可比较过程组的观测时长总和排序；双卡并发按请求/阶段的 selected-kernel 忙碌并集排序；原始采样按组内最长可用过程窗口排序；未知缺口按原始未观测时长排序。可在页面选择全部或定位任意排名，完整数据均保留。</p><ul>'+''.join('<li><a href="'+url+'">'+label+'</a></li>' for url,label in links)+'</ul><p>解压整个 ZIP 后直接打开 index.html。各分析 HTML 自带全部数据，无需服务或联网；建议桌面浏览器。滚轮缩放、拖动平移，点击矩形或原始点查看源记录。</p><p class="notice">R08 重放属性是旁证；不进入观测延迟排名。未知缺口不是零利用率；selected kernel 间隔不是设备空闲。跨设备时钟误差无获准上界，同轴展示不证明细粒度同步。</p><p>原始验收与本次展示审计分开保存，原始 R10 页面、清单、数据与审计字节不变。</p></section></main></html>\n'
 (ROOT/'index.html').write_text(index);(accept/'index.html').write_text(index.replace('href="','href="../'))
 receipt={'revision':'report-repair-001/candidate-005-folded-trapezoid-full-overview','kind':'authorized_presentation_only','utc':datetime.datetime.now(datetime.timezone.utc).isoformat(),'status':'built_pending_browser_and_independent_audit','argv':sys.argv,'cpu_only':True,'source_artifact_manifest':record(SOURCE/'artifact_manifest.json'),'source_sealed_inputs':inputs,'page_revisions':outputs,'top20_is_reversible_view_selection_only':True,'complete_payloads_retained':True,'original_bundle_copied_byte_for_byte':True,'cross_device_clock_bound_promoted':False,'replay_timing_used_for_ranking':False,'tools':[record(x) for x in sorted(TOOLS.iterdir()) if x.is_file()],'elapsed_seconds':time.time()-start}
 dump(ROOT/'BUILD_MANIFEST.json',receipt);print('BUILD_COMPLETE',receipt['elapsed_seconds'],flush=True)
if __name__=='__main__':main()
