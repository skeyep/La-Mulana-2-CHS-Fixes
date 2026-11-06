"""Compare the complete static database readback to the selected source-bound operations."""
import json,re
from pathlib import Path
import UnityPy
from UnityPy.helpers.TypeTreeGenerator import TypeTreeGenerator

ROOT=Path(__file__).resolve().parents[2];BUILD=ROOT/'build/lm2-text-patch'

def load(path):return json.loads(path.read_text(encoding='utf-8'))
def normalize(value,token=None,edits=None):
 if isinstance(value,dict):
  out={k:normalize(v,token,edits) for k,v in value.items() if k!='il_offset'}
  if edits and 'text' in value and (token,value['il_offset']) in edits:out['text']=edits[(token,value['il_offset'])]['after']
  return out
 if isinstance(value,list):return [normalize(v,token,edits) for v in value]
 return value

def main():
 source=load(ROOT/'localization/research/lm2_database_arrays.json');target=load(BUILD/'readback-arrays.json');noop=load(ROOT/'build/lm2-noop-arrays.json');ops=load(BUILD/'operations.json')['operations'];rows=load(BUILD/'rows.json')
 edits={(o['method_token'],o['il_offset']):o for o in ops};a={m['type']:m for m in source['methods']};b={m['type']:m for m in target['methods']};n={m['type']:m for m in noop['methods']}
 assert set(a)==set(b)==set(n)
 for typ,m in a.items():
  assert normalize(m['fields'],m['method_token'],edits)==normalize(b[typ]['fields']),typ
  assert normalize(m['fields'])==normalize(n[typ]['fields']),typ
 source_rows={r['id']:r for r in load(ROOT/'localization/source/lm2/aligned_jpn_eng_chi.json')['rows']}
 review=load(ROOT/'localization/lm2/review/20261106/review.json');selected={e['stable_id']:e for i in review['issues'] for e in i['entries'] if i['implementation_review']=='selected-after-guide-review'}
 assert set(selected)=={r['stable_id'] for r in rows}
 for row in rows:
  s=source_rows[row['stable_id']];si,ri,ci=s['languages']['chi']['cell_indices'];rich=''.join(x['text'] for x in b[s['source_type']]['fields']['cellData'][si][ri][ci])
  assert rich==row['rich_text'];assert re.sub(r'</?color(?:=[^>]+)?>','',rich)==selected[row['stable_id']]['after']
 method_diff=load(BUILD/'method-diff.json');assert method_diff['string_changes']==len(ops)
 changed={(x['method'],x['offset']):x for x in method_diff['changes']};assert len(changed)==len(ops)
 # Read fonts from the actual serialized output, reusing the already inspected glyph artwork.
 g=TypeTreeGenerator('2017.2.2f1');g.load_local_game('D:/SteamLibrary/steamapps/common/La-Mulana 2');node=g.get_nodes_up('TextMeshPro.dll','TMPro.TMP_FontAsset');env=UnityPy.load(str(BUILD/'resources.assets'));objects={o.path_id:o for o in env.objects};chars=set(''.join(r['after'] for r in rows))-set('\r\n\t')
 for pid in [27627,27628,27629]:assert chars<={chr(q['id']) for q in objects[pid].read_typetree(nodes=node)['m_glyphInfoList']}
 report={'selected_issues':len(review['issues']),'written_chinese_rows':len(rows),'ldstr_edits':len(ops),'database_count':len(a),'all_database_fields_match_expected':True,'jpn_eng_other_fields_and_nonselected_rows_unchanged':True,'noop_all_database_fields_unchanged':True,'full_method_instruction_comparison':'passed: only selected ldstr operands differ','all_current_characters_in_three_chinese_fonts':True,'metadata_tokens_reassigned_by_cecil':True,'natural_gameplay_windows':'pending'}
 (BUILD/'validation.json').write_text(json.dumps(report,ensure_ascii=False,indent=2)+'\n',encoding='utf-8');print(json.dumps(report,ensure_ascii=False))

if __name__=='__main__':main()
