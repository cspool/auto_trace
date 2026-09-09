#!/usr/bin/env python3
from pathlib import Path
import json,hashlib
import pymupdf
from PIL import Image,ImageDraw
O=Path(__file__).resolve().parent;V=O/'validation';p=O/'Batch8_DP2_Scheduling_Report.pdf';doc=pymupdf.open(p);records=[];thumbs=[];tall_scheduling_pages=[]
for i,page in enumerate(doc):
 text=page.get_text();words=page.get_text('words');assert text.strip(),('empty page',i+1)
 outside=[w for w in words if w[0]<-1 or w[1]<-1 or w[2]>page.rect.width+1 or w[3]>page.rect.height+1];assert not outside,('clipped text outside page',i+1,outside[:2])
 records.append({'page':i+1,'width_pt':page.rect.width,'height_pt':page.rect.height,'text_characters':len(text),'words_outside_page':len(outside),'first_text':text[:100]})
 if 'How global Batch8' in text:
  assert page.rect.height>1500 and page.rect.width>1100,('scheduling figure was reduced to short paper',i+1)
  tall_scheduling_pages.append(i+1)
 pix=page.get_pixmap(matrix=pymupdf.Matrix(.40,.40),alpha=False);im=Image.frombytes('RGB',[pix.width,pix.height],pix.samples);thumbs.append(im)
 if 'How global Batch8' in text or 'folded client spans' in text or i==0:
  page.get_pixmap(matrix=pymupdf.Matrix(1.2,1.2),alpha=False).save(V/f'pdf_page_{i+1:02d}.png')
text='\n'.join(p.get_text() for p in doc)
for phrase in ['双卡','512','579.996','756','256','128','waiting','client_count','OOM','3582','6760','27 / 23','39 / 11']:
 assert phrase in text,('missing required PDF content',phrase)
assert len(tall_scheduling_pages)==1
width=max(im.width for im in thumbs);height=max(im.height for im in thumbs);sheet=Image.new('RGB',(width*3,height*((len(thumbs)+2)//3)),'#e5e7eb')
for i,im in enumerate(thumbs):sheet.paste(im,((i%3)*width,(i//3)*height))
sheet.save(V/'pdf_contact_sheet.png')
result={'status':'complete','pdf_sha256':hashlib.sha256(p.read_bytes()).hexdigest(),'pages':len(doc),'library_version':pymupdf.VersionBind,'all_pages_nonempty':True,'all_text_word_boxes_inside_page':True,'Chinese_text_extractable':True,'tall_scheduling_pages':tall_scheduling_pages,'page_records':records}
(O/'PDF_AUDIT.json').write_text(json.dumps(result,ensure_ascii=False,indent=2)+'\n');print('PDF_AUDIT_COMPLETE','pages',len(doc),'text_chars',len(text))
