"""Operational action plan; exact canonical IDs, no title-based deduplication."""
from collections import Counter
from .components import text, kv, chip, origin, table
from .presentation_labels import public_value


def content(value, field=None):
    if value is None or value == []:
        return '<p>N/D — conteúdo não persistido.</p>'
    if isinstance(value,list):
        if field=='affected_dimensions_json':
            items=[]
            for item in value:
                if isinstance(item,dict) and set(item)<={'dimension','expected_gain'}:
                    items.append('<li title="'+text(item)+'">'+text(public_value(item.get('dimension'),'dimension'))+' · Ganho esperado na fonte: '+text(public_value(item.get('expected_gain'),'expected_gain'))+'</li>')
                else:
                    items.append('<li>'+text(item)+'</li>')
            return '<ul>'+''.join(items)+'</ul>'
        return '<ul>'+''.join('<li>'+text(item)+'</li>' for item in value)+'</ul>'
    return '<p>'+text(value)+'</p>'


def grouped_actions(rows):
    groups={}
    for index,row in enumerate(rows):
        key=('canonical',row['action_id']) if row.get('action_id') else ('unidentified',index)
        groups.setdefault(key,[]).append(row)
    rank={'CRITICAL':0,'HIGH':1,'MEDIUM':2,'LOW':3}
    return sorted(groups.values(),key=lambda group:(rank.get(group[0].get('priority'),4),str(group[0].get('action_id',''))))


def render_plan(rows, timezone_name):
    groups=grouped_actions(rows(['directed_analysis_actions']))
    priorities=Counter(group[0].get('priority') for group in groups)
    html='<h2>Visão geral</h2>'+origin('Calculado no relatório')
    html+=kv([('Ações (ocorrências)',sum(map(len,groups))),('Ações distintas por ID',sum(bool(g[0].get('action_id')) for g in groups)),('Ocorrências sem ID',sum(not g[0].get('action_id') for g in groups)),('Crítica',priorities['CRITICAL']),('Alta',priorities['HIGH']),('Média',priorities['MEDIUM']),('Baixa',priorities['LOW']),('Sem prioridade',priorities[None]+priorities['']),('Origem explicitamente IA de conteúdo',sum(g[0].get('source_kind')=='CONTENT_AI' for g in groups))])
    html+='<p class="rf">Contagens de apresentação por action_id; não há deduplicação por título. Ocorrências sem ID permanecem separadas, sem afirmar identidade distinta. Origens de IA não explícitas não são inferidas. Prioridades não reconhecidas permanecem no detalhe.</p>'
    executive=[]
    for index,group in enumerate(groups):
        row=group[0]
        executive.append({**row,'occurrences':len(group),'_ref':f'#action-card-{index}'})
    html+='<h2>Ações por prioridade</h2>'+table('Ações distintas e ocorrências',executive,[('priority','Prioridade'),('title','Ação'),('occurrences','Ocorrências'),('primary_objective','Objetivo'),('effort','Esforço'),('confidence','Confiança'),('source_kind','Origem'),('_ref','Cartão')],timezone_name)
    html+='<h2>Cartões de ação</h2>'
    for index,group in enumerate(groups):
        row=group[0]
        html+=f'<details id="action-card-{index}"><summary>{chip(row.get("priority"),"priority")} {text(row.get("title"))} ({len(group)})</summary>'
        for occurrence in group:
            for key,label in [('reason','Por que importa / justificativa técnica'),('affected_dimensions_json','Dimensões afetadas'),('confidence_rationale','Justificativa da confiança'),('implementation_guidance_json','Como fazer'),('validation_steps_json','Como validar')]:
                html+='<h3>'+label+'</h3>'+content(occurrence.get(key),key)
            html+=f'<a href="{text(occurrence.get("_ref"))}">Evidências e origem persistida</a>'
        html+='</details>'
    corrections=rows(['improvement_intelligence_recommendations'])
    html+='<h2>Correções técnicas propostas (código)</h2>'+table('Correções propostas',corrections,[('severity','Criticidade'),('domain','Domínio'),('title','Título'),('selector','Elemento'),('source','Origem'),('_ref','Fonte')],timezone_name)
    for row in corrections:
        html+='<details><summary>'+chip(row.get('severity'),'severity')+' '+text(row.get('title'))+'</summary>'+origin('IA sugeriu' if row.get('source')=='AI' else 'Proposta persistida')+'<p>Sugestão não aprovada</p>'
        for key,label in [('recommendation','Recomendação'),('rationale','Justificativa técnica'),('verification','Verificação')]:
            html+='<h3>'+label+'</h3>'+content(row.get(key))
        for key,label in [('original_html','Atual'),('suggested_html','Sugerido'),('suggested_text','Texto sugerido')]:
            if row.get(key) is not None:
                html+='<h3>'+label+'</h3><pre>'+text(row[key])+'</pre>'
        html+=f'<a href="{text(row.get("_ref"))}">Evidências e origem persistida</a></details>'
    html+='<h2>Textos sugeridos por IA</h2><p class="callout w">Propostas de conteúdo; não aprovadas. Exigem revisão editorial, jurídica e de compliance antes de publicar.</p>'
    for row in rows(['content_remediation_suggestions']):
        html+='<details><summary>'+text(row.get('objective'))+' '+origin('IA sugeriu')+'</summary>'
        html+=kv([('Local',row.get('target_location')),('Confiança autodeclarada — não estatística',public_value(row.get('confidence'),'confidence')),('Modelo',row.get('model')),('Nota de revisão',row.get('review_note')),('Revisão humana','Sugestão não aprovada')])
        html+='<h3>Texto proposto</h3><pre>'+text(row.get('proposed_text'))+f'</pre><a href="{text(row.get("_ref"))}">Evidências e origem persistida</a></details>'
    return html
