"""Operational action plan; exact canonical IDs, no title-based deduplication."""
from collections import Counter
from .components import text, kv, chip, origin, table, technical_link
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


def technical_reference(href):
    if not href:
        return ''
    return '<details class="in"><summary>Referência técnica persistida</summary><p>' + technical_link(href) + '</p></details>'


def grouped_actions(rows):
    groups={}
    for index,row in enumerate(rows):
        key=('canonical',row['action_id']) if row.get('action_id') else ('unidentified',index)
        groups.setdefault(key,[]).append(row)
    rank={'CRITICAL':0,'HIGH':1,'MEDIUM':2,'LOW':3}
    return sorted(groups.values(),key=lambda group:(rank.get(group[0].get('priority'),4),str(group[0].get('action_id',''))))


def render_plan(rows, timezone_name, governance):
    groups=grouped_actions(rows(['directed_analysis_actions']))
    priorities=Counter(group[0].get('priority') for group in groups)
    html='<h2>Visão geral</h2>'+origin('Calculado no relatório')
    html+=kv([('Ações (ocorrências)',sum(map(len,groups))),('Ações distintas por ID',sum(bool(g[0].get('action_id')) for g in groups)),('Ocorrências sem ID',sum(not g[0].get('action_id') for g in groups)),('Crítica',priorities['CRITICAL']),('Alta',priorities['HIGH']),('Média',priorities['MEDIUM']),('Baixa',priorities['LOW']),('Sem prioridade',priorities[None]+priorities['']),('Origem explicitamente IA de conteúdo',sum(g[0].get('source_kind')=='CONTENT_AI' for g in groups))])
    html+='<p class="rf">Contagens de apresentação por action_id; não há deduplicação por título. Ocorrências sem ID permanecem separadas, sem afirmar identidade distinta. Origens de IA não explícitas não são inferidas. Prioridades não reconhecidas permanecem no detalhe.</p>'
    decisions = rows(['recommendation_governance'])
    html += kv([('Decisões aceitas', sum(d.get('decision') == 'ACCEPTED' for d in decisions) if decisions else None),
                ('Decisões rejeitadas', sum(d.get('decision') == 'REJECTED' for d in decisions) if decisions else None)])
    html += '<p>Os IDs contam o inventário técnico. Apenas a decisão vinculada identifica uma ação aceita. Itens excluídos permanecem no detalhe técnico.</p>'
    # Governance is a decision boundary, not a priority or source-kind heuristic.
    # Technical recommendations without a decision remain consultable but never
    # appear under the client's approved execution plan.
    accepted = [g for g in groups if governance.disposition('directed_analysis_actions', g[0]) == 'Aceita pela governança']
    undecided = [g for g in groups if not governance.excluded('directed_analysis_actions', g[0])
                 and governance.disposition('directed_analysis_actions', g[0]) != 'Aceita pela governança']
    excluded = [g for g in groups if governance.excluded('directed_analysis_actions', g[0])]

    def action_section(section_groups, heading, explanation, offset):
        result = '<h2>' + heading + '</h2><p>' + explanation + '</p>'
        if not section_groups:
            return result + '<p>Nenhum registro nesta classe de governança.</p>'
        executive = [{**group[0], 'occurrences': len(group), '_ref': f'#action-card-{offset + index}',
                      'governance': governance.disposition('directed_analysis_actions', group[0])}
                     for index, group in enumerate(section_groups)]
        result += table('Ações distintas e ocorrências', executive,
                        [('priority','Prioridade'),('title','Ação'),('occurrences','Ocorrências'),
                         ('governance','Governança'),('primary_objective','Objetivo'),
                         ('effort','Esforço'),('confidence','Confiança'),('source_kind','Origem')],
                        timezone_name)
        for index, group in enumerate(section_groups):
            row = group[0]
            result += f'<details id="action-card-{offset + index}"><summary>{chip(row.get("priority"),"priority")} {text(row.get("title"))} ({len(group)})</summary>'
            result += '<p><strong>Governança:</strong> ' + text(governance.disposition('directed_analysis_actions', row)) + '</p>'
            for occurrence in group:
                for key, label in [('reason','Por que importa / justificativa técnica'),
                                   ('affected_dimensions_json','Dimensões afetadas'),
                                   ('confidence_rationale','Justificativa da confiança'),
                                   ('implementation_guidance_json','Como fazer'),
                                   ('validation_steps_json','Como validar')]:
                    result += '<h3>' + label + '</h3>' + content(occurrence.get(key), key)
                result += technical_reference(occurrence.get('_ref'))
            result += '</details>'
        return result

    html += action_section(accepted, 'Plano aprovado pela governança',
                           'Somente ações com decisão ACCEPTED inequívoca e alvo do cliente. Prioridade não é aprovação.', 0)
    html += action_section(undecided, 'Recomendações técnicas sem aprovação',
                           'Itens ainda não autorizados para execução. Exigem decisão do responsável antes de integrar o plano.', len(accepted))
    html += '<h2>Decisões rejeitadas ou fora do escopo do cliente</h2>'
    html += kv([('Ações direcionadas excluídas da execução', len(excluded))])
    html += '<p>Os registros rejeitados ou internos continuam no inventário técnico sanitizado e na matriz de governança, sem cartões executáveis.</p>'
    corrections=[r for r in rows(['improvement_intelligence_recommendations']) if not governance.excluded('improvement_intelligence_recommendations', r)]
    for row in corrections:
        row['governance'] = governance.disposition('improvement_intelligence_recommendations', row)
    approved_corrections = [r for r in corrections if r['governance'] == 'Aceita pela governança']
    pending_corrections = [r for r in corrections if r['governance'] != 'Aceita pela governança']
    html += '<h2>Correções técnicas aceitas pela governança</h2>'
    html += (table('Correções aprovadas', approved_corrections,
                   [('severity','Criticidade'),('title','Título'),('selector','Elemento'),('governance','Governança')], timezone_name)
             if approved_corrections else '<p>Nenhuma correção técnica aprovada nesta classe.</p>')
    html += '<h2>Correções técnicas sem aprovação</h2>'
    html += (table('Propostas técnicas para decisão', pending_corrections,
                   [('severity','Criticidade'),('domain','Domínio'),('title','Título'),
                    ('selector','Elemento'),('source','Origem'),('governance','Governança')], timezone_name)
             if pending_corrections else '<p>Nenhuma proposta pendente nesta classe.</p>')
    for row in corrections:
        html+='<details><summary>'+chip(row.get('severity'),'severity')+' '+text(row.get('title'))+'</summary>'+origin('IA sugeriu' if row.get('source')=='AI' else 'Proposta persistida')+'<p>'+text('Aceita pela governança; publicação depende de validação humana.' if row['governance']=='Aceita pela governança' else 'Sugestão não aprovada')+'</p>'
        for key,label in [('recommendation','Recomendação'),('rationale','Justificativa técnica'),('verification','Verificação')]:
            html+='<h3>'+label+'</h3>'+content(row.get(key))
        for key,label in [('original_html','Atual'),('suggested_html','Sugerido'),('suggested_text','Texto sugerido')]:
            if row.get(key) is not None:
                html+='<h3>'+label+'</h3><pre>'+text(row[key])+'</pre>'
        html+=technical_reference(row.get('_ref'))+'</details>'
    html+='<h2>Textos sugeridos por IA</h2><p class="callout w">Cada texto conserva sua própria decisão de governança. Mesmo uma sugestão aceita exige revisão editorial, jurídica e de compliance antes da publicação.</p>'
    for row in rows(['content_remediation_suggestions']):
        if governance.excluded('content_remediation_suggestions', row):
            continue
        html+='<details><summary>'+text(row.get('objective'))+' '+origin('IA sugeriu')+'</summary>'
        html+=kv([('Local',row.get('target_location')),('Confiança autodeclarada — não estatística',public_value(row.get('confidence'),'confidence')),('Modelo',row.get('model')),('Nota de revisão',row.get('review_note')),('Decisão de governança', governance.disposition('content_remediation_suggestions', row)),('Revisão humana','Obrigatória antes da publicação')])
        html+='<h3>Texto proposto</h3><pre>'+text(row.get('proposed_text'))+'</pre>'+technical_reference(row.get('_ref'))+'</details>'
    return html
