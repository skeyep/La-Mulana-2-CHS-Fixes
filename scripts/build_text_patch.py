"""Bind selected LM2 Chinese text to the original CIL string operands and colour triples."""
import json
import re
from pathlib import Path

ROOT=Path(__file__).resolve().parents[2]
OUT=ROOT/'build/lm2-text-patch'
WHITE='#FFFFFFFF'
# Meaning-based ranges when a corrected noun or clue no longer matches the old Chinese spelling.
MAP={
 '巨大的龙':'巨龙','地':'大地','大火':'火焰','狂风':'风','大海':'大海','邪恶的怪物':'邪恶怪物',
 '公会认证':'妖精公会通行证','阿尔塞达娜':'阿尔赛达纳','高天原庙':'高天原神宫',
 '涅莫亚的毛皮':'涅墨亚的毛皮','斯威布踏古':'斯维普达格','死者之门':'亡灵之门','娜迦':'迦利耶',
 '节德':'节德柱','缺席':'缺','过度使用的力量':'过强的力量','与血染的杀意':'染血的杀意',
 '封印':'印记','拉展示的咒语':'表示拉的言语','水晶金字塔':'金字塔水晶',
}

def dump(path,obj):
 path.parent.mkdir(parents=True,exist_ok=True)
 path.write_text(json.dumps(obj,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')

def ranges_for(issue,e,row):
 original=row['languages']['chi']['text'];before=e['before'];after=e['after'];spans=[];pos=0
 for m in re.finditer(r'<color=(#[A-Fa-f0-9]+)>(.*?)</color>',original,re.S):
  color,text=m.groups()
  if color.upper()!=WHITE and text and issue['id']!='P44':
   target=text if text in after else MAP.get(text)
   if issue['id']=='U11' and text=='地':target='大地'
   if not target or target not in after:raise ValueError((issue['id'],e['stable_id'],text,target))
   # Preserve which repeat was emphasised when wording survives; corrected words use the first occurrence.
   rank=before[:pos].count(text) if target==text else 0
   starts=[x.start() for x in re.finditer(re.escape(target),after)]
   start=starts[min(rank,len(starts)-1)];spans.append((start,start+len(target),color.upper(),target))
  pos+=len(text)
 if issue['id']=='P44':
  # JP has three mantra-bearing highlights: mother, fulfil, missing. Keep each independently visible.
  spans=[(after.index(t),after.index(t)+len(t),c,t) for t,c in [('密米尔之泉','#7AA9FFFF'),('神酒','#4FFD84FF'),('母亲','#7AA9FFFF'),('实现','#7AA9FFFF'),('缺','#7AA9FFFF')]]
 spans.sort();last=0
 for a,b,c,t in spans:
  if a<last:raise ValueError(('Overlapping colour ranges',e['stable_id']))
  last=b
 return spans

def main():
 review=json.loads((ROOT/'localization/lm2/review/20261106/review.json').read_text(encoding='utf-8'))
 source=json.loads((ROOT/'localization/source/lm2/aligned_jpn_eng_chi.json').read_text(encoding='utf-8'))
 by={r['id']:r for r in source['rows']};operations=[];rows=[]
 assert review.get('implementation_authorization'), 'Record user authorization before creating patch inputs'
 for issue in review['issues']:
  if issue.get('implementation_review')!='selected-after-guide-review':continue
  for e in issue['entries']:
   row=by[e['stable_id']];fragments=row['languages']['chi']['fragments'];after=e['after'];n=len(fragments)
   assert n%3==0 and e['before']==row['languages']['chi']['plain_text']
   spans=ranges_for(issue,e,row);segments=[];last=0
   for a,b,color,text in spans:
    if a>last:segments.append((WHITE,after[last:a]))
    segments.append((color,after[a:b]));last=b
   if last<len(after):segments.append((WHITE,after[last:]))
   new=[];at=0
   for group in range(n//3):
    a,b,c=fragments[3*group:3*group+3]
    if at<len(segments) and 'string_token' in b:
     color,text=segments[at];at+=1
    else:color,text=WHITE,''
    values=[f'<color={color}>',text,'</color>']
    for f,value in zip([a,b,c],values):
     if f['text']!=value:
      assert 'string_token' in f,(e['stable_id'],group,f,value)
      operations.append({'stable_id':e['stable_id'],'method_token':row['source_method_token'],'il_offset':f['il_offset'],'before':f['text'],'after':value})
    new.extend(values)
   assert at==len(segments),(e['stable_id'],len(segments),n//3,at)
   rich=''.join(new);plain=re.sub(r'</?color(?:=[^>]+)?>','',rich)
   assert plain==after and re.findall(r'<(?!/?color(?:=|>))[^>]+>',plain)==re.findall(r'<(?!/?color(?:=|>))[^>]+>',e['before'])
   rows.append({'issue_id':issue['id'],'stable_id':e['stable_id'],'before':e['before'],'after':after,'rich_text':rich,'colour_ranges':[{'text':t,'color':c,'start':a,'end':b} for a,b,c,t in spans],'fragment_count':n})
 assert len({(x['method_token'],x['il_offset']) for x in operations})==len(operations)
 dump(OUT/'operations.json',{'source':review['source'],'operations':operations})
 dump(OUT/'rows.json',rows)
 print(json.dumps({'selected_issues':len({r['issue_id'] for r in rows}),'rows':len(rows),'ldstr_edits':len(operations),'colour_rows':sum(bool(r['colour_ranges']) for r in rows)},ensure_ascii=False))

if __name__=='__main__':main()
