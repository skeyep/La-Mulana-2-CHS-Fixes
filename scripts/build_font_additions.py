import os
"""Add only the missing CHS glyphs to the three existing TMP SDF atlases."""
import copy
import json
import math
from pathlib import Path
import numpy as np
from PIL import Image,ImageDraw,ImageFont
from scipy.ndimage import distance_transform_edt
import UnityPy
from UnityPy.helpers.TypeTreeGenerator import TypeTreeGenerator

ROOT=Path(__file__).resolve().parents[2]
GAME=Path(os.environ['LM2_GAME_DIR'])
OUT=ROOT/'build/lm2-text-patch'
FONT=Path('C:/Windows/Fonts/NotoSansSC-VF.ttf')
FONTS=[27627,27628,27629]

def node_for():
 g=TypeTreeGenerator('2017.2.2f1');g.load_local_game(str(GAME))
 return g,g.get_nodes_up('TextMeshPro.dll','TMPro.TMP_FontAsset')

def sdf_glyph(ch,size,pad):
 scale=4;f=ImageFont.truetype(str(FONT),size*scale)
 axes=f.get_variation_axes()
 f.set_variation_by_axes([400 if a['name']==b'Weight' else a['default'] for a in axes])
 # Pin wght=400; the installed variable font defaults to a much lighter weight.
 bbox=f.getbbox(ch,anchor='ls');w=bbox[2]-bbox[0];h=bbox[3]-bbox[1]
 im=Image.new('L',(w,h));ImageDraw.Draw(im).text((-bbox[0],-bbox[1]),ch,font=f,fill=255,anchor='ls')
 ink=im.getbbox();assert ink
 im=im.crop(ink);left=(bbox[0]+ink[0])/scale;top=-(bbox[1]+ink[1])/scale
 w=math.ceil(im.width/scale);h=math.ceil(im.height/scale)
 canvas=Image.new('L',((w+2*pad)*scale,(h+2*pad)*scale));canvas.paste(im,(pad*scale,pad*scale))
 mask=np.asarray(canvas)>127
 signed=(distance_transform_edt(mask)-distance_transform_edt(~mask))/scale
 alpha=np.clip(127.5+signed*255/(2*(pad+1)),0,255).astype('uint8')
 alpha=Image.fromarray(alpha).resize((w+2*pad,h+2*pad),Image.Resampling.LANCZOS)
 return alpha,{'id':ord(ch),'width':float(w),'height':float(h),'xOffset':left,'yOffset':top,'xAdvance':float(size),'scale':1.0}

def empty_slot(occupied,w,h):
 a=np.pad(occupied.astype('uint32'),((1,0),(1,0))).cumsum(0).cumsum(1)
 sums=a[h:,w:]-a[:-h,w:]-a[h:,:-w]+a[:-h,:-w]
 found=np.argwhere(sums==0)
 if not len(found):raise ValueError('No unused rectangle in original atlas')
 y,x=found[0];return int(x),int(y)

def main():
 OUT.mkdir(parents=True,exist_ok=True);env=UnityPy.load(str(GAME/'LaMulana2_Data/resources.assets'));objs={o.path_id:o for o in env.objects};gen,node=node_for()
 rows=json.loads((OUT/'rows.json').read_text(encoding='utf-8'));chars=set(''.join(x['after'] for x in rows))-{ '\n','\r','\t'};report=[]
 preview=[];expected_trees={};expected_atlases={}
 for fid in FONTS:
  obj=objs[fid];tree=obj.read_typetree(nodes=node);glyphs=tree['m_glyphInfoList'];ids={q['id'] for q in glyphs};missing=sorted(ch for ch in chars if ord(ch) not in ids)
  tid=tree['atlas']['m_PathID'];tex=objs[tid].read();assert tex.m_TextureFormat==1 and tex.m_MipCount==1
  rgba=tex.image.convert('RGBA');alpha=rgba.getchannel('A');base=np.asarray(alpha).copy();occupied=base>0;pad=int(tree['m_fontInfo']['Padding']);size=round(tree['m_fontInfo']['PointSize']);placements=[]
  # Respect glyph boxes and padding even where SDF pixels happen to be zero.
  for q in glyphs:
   if q['width']<=0 or q['height']<=0:continue
   x=max(0,math.floor(q['x'])-pad-1);y=max(0,math.floor(q['y'])-pad-1)
   occupied[y:min(tex.m_Height,y+math.ceil(q['height'])+2*pad+2),x:min(tex.m_Width,x+math.ceil(q['width'])+2*pad+2)]=True
  for ch in missing:
   tile,q=sdf_glyph(ch,size,pad);x,y=empty_slot(occupied,tile.width,tile.height)
   assert not np.any(base[y:y+tile.height,x:x+tile.width])
   alpha.paste(tile,(x,y));occupied[y:y+tile.height,x:x+tile.width]=True
   # TMP's glyph y is measured from the top of the atlas, matching decoded PIL pixels.
   q['x']=float(x+pad);q['y']=float(y+pad);glyphs.append(q)
   placements.append({'char':ch,'rect':[x,y,tile.width,tile.height],'glyph':q})
   # 0.5 SDF contour is a useful font-shape preview, not a game screenshot.
   ink=np.asarray(tile)>=128;preview.append((fid,ch,Image.fromarray((ink*255).astype('uint8'))))
  tree['m_fontInfo']['CharacterCount']=len(glyphs);obj.save_typetree(tree,nodes=node)
  expected_trees[fid]=copy.deepcopy(tree);expected_atlases[tid]=np.asarray(alpha).copy()
  # Keep the original 2048px dimensions and all existing pixels. Embed this changed A8 atlas locally.
  tex.m_StreamData.path='';tex.m_StreamData.offset=0;tex.m_StreamData.size=0
  tex.image_data=np.asarray(alpha)[::-1].tobytes();tex.m_CompleteImageSize=len(tex.image_data);tex.save()
  report.append({'font_path_id':fid,'name':tree['m_Name'],'atlas_path_id':tid,'new_chars':missing,'point_size':size,'placements':placements,'old_pixels_preserved':True})
 file=next(v for v in env.files.values() if v.name.endswith('resources.assets'));(OUT/'resources.assets').write_bytes(file.save())
 # Read the serialized output with the same schemas; compare every unrelated object directly.
 check=UnityPy.load(str(OUT/'resources.assets'));cb={o.path_id:o for o in check.objects};changed={r['font_path_id'] for r in report}|{r['atlas_path_id'] for r in report};assert set(cb)==set(objs)
 for pid,o in objs.items():
  if pid not in changed:assert o.get_raw_data()==cb[pid].get_raw_data(),pid
 for r in report:
  t=cb[r['font_path_id']].read_typetree(nodes=node);assert t==expected_trees[r['font_path_id']]
  assert chars<={chr(q['id']) for q in t['m_glyphInfoList']}
  arr=np.asarray(cb[r['atlas_path_id']].read().image.getchannel('A'));assert np.array_equal(arr,expected_atlases[r['atlas_path_id']])
 out={'fonts':report,'changed_objects':sorted(changed),'unrelated_objects_unchanged':len(objs)-len(changed),'all_selected_text_characters_covered':True,'glyph_source':str(FONT),'license':'SIL Open Font License 1.1'}
 (OUT/'font-additions.json').write_text(json.dumps(out,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
 label=ImageFont.truetype('C:/Windows/Fonts/msyh.ttc',18);canvas=Image.new('RGB',(7*140,3*135),'#242833');d=ImageDraw.Draw(canvas)
 for n,(fid,ch,im) in enumerate(preview):
  x=(n%7)*140;y=(n//7)*135;d.text((x+8,y+4),f'{fid} {ch}',font=label,fill='white');im=im.resize((im.width*2,im.height*2),Image.Resampling.NEAREST);canvas.paste(Image.merge('RGB',(im,im,im)),(x+5,y+35))
 canvas.save(OUT/'font-preview.jpg',quality=95)
 print(json.dumps({k:v for k,v in out.items() if k!='fonts'},ensure_ascii=False))

if __name__=='__main__':main()
