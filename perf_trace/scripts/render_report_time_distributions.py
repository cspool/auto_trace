#!/usr/bin/env python3
"""Re-render report distribution figures from their retained source-derived geometry."""
from pathlib import Path
import argparse,hashlib,json,xml.etree.ElementTree as ET
from playwright.sync_api import sync_playwright
from capture_diagnostic_report_figures import high_svg

def main(root):
 folder=root/'analysis_reports/figures';mp=folder/'FIGURE_MANIFEST.json';manifest=json.loads(mp.read_text());count=0
 with sync_playwright() as pw:
  browser=pw.chromium.launch(headless=True,args=['--no-sandbox']);page=browser.new_page()
  for entry in manifest['figures']:
   data_path=folder/entry['geometry'];data=json.loads(data_path.read_text())
   if 'tracks' not in data:continue
   svg_path=folder/(entry['name']+'.svg');title=next(e.text for e in ET.parse(svg_path).iter() if e.tag.endswith('text')).replace('堆内时间线放大','最长过程区间放大');data['envelope']='rectangle'
   if data.get('focus_id'):
    focus=next(line for track in data['tracks'] for line in track['lines'] if line['id']==data['focus_id']);start=int(focus['begin_ns'])-int(data['origin_ns']);end=int(focus['end_ns'])-int(data['origin_ns']);pad=max(1,(end-start)//20);data['view']=[start-pad,end+pad];lo,hi=data['view'];focus.update(xf=(start-lo)/(hi-lo),xef=(end-lo)/(hi-lo));data['tracks']=[dict(track,lines=[focus]) for track in data['tracks'] if any(line['id']==focus['id'] for line in track['lines'])];data.update(row_height=205,folded=False,breaks=[],ticks=[{'fraction':i/5,'ns':lo+(hi-lo)*i/5} for i in range(6)],subtitle='只绘制选中最长实例的一个矩形，左右边界对应真实开始和结束。')
   else:data['subtitle']='每堆一个矩形，左边界为最早开始，右边界为最晚结束；不展开内部成员。'
   data_path.write_text(json.dumps(data,ensure_ascii=False,indent=2)+'\n');svg_path.write_text(high_svg(data,title));page.goto(svg_path.resolve().as_uri());page.locator('svg').screenshot(path=str(svg_path.with_suffix('.png')))
   for ext,key in [('svg','SVG_sha256'),('png','PNG_sha256')]:entry[key]=hashlib.sha256(svg_path.with_suffix('.'+ext).read_bytes()).hexdigest()
   count+=1
  browser.close()
 manifest['status']='generated_pending_visual_review';mp.write_text(json.dumps(manifest,ensure_ascii=False,indent=2)+'\n');print('Rectangular time-distribution figures:',count,flush=True)
if __name__=='__main__':
 p=argparse.ArgumentParser();p.add_argument('--root',type=Path,required=True);a=p.parse_args();main(a.root.resolve())
