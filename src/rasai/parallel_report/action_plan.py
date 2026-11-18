"""Operational action plan; exact canonical IDs, no title-based deduplication."""
from collections import Counter
import json
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
                    items.append('<li>'+text(public_value(item.get('dimension'),'dimension'))+' · Ganho esperado na fonte: '+text(public_value(item.get('expected_gain'),'expected_gain'))+'</li>')
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


def _persisted_json(value, expected):
    if isinstance(value, expected):
        return value
    if isinstance(value, str) and len(value) <= 2_000_000:
        try:
            parsed = json.loads(value)
            return parsed if isinstance(parsed, expected) else None
        except (ValueError, TypeError):
            pass
    return None


def strategic_context(rows, governance):
    """Advisory synthesis already persisted in audit.db; no fresh AI or HTML import."""
    runs = rows(['directed_analysis_runs'])
    if not runs:
        return '<h2>Síntese estratégica</h2><p>N/D — análise direcionada não materializada para esta auditoria.</p>'
    run = runs[0]
    status = str(run.get('status') or 'N/D').upper()
    html = '<h2>Síntese estratégica persistida</h2>' + kv([
        ('Estado da análise', public_value(status,'status')), ('Provedor persistido', run.get('provider')),
        ('Modelo persistido', run.get('model'))])
    if status in {'DISABLED', 'NOT_REQUESTED', 'FAILED', 'BLOCKED'}:
        return html + '<p>A síntese estratégica não está disponível neste estado. As ações técnicas seguem no inventário, sem interpretação inventada.</p>'
    summary = _persisted_json(run.get('strategic_summary_json'), dict)
    roadmap = _persisted_json(run.get('roadmap_json'), list)
    if summary is None:
        html += '<p>N/D — narrativa estratégica não disponível em formato verificável.</p>'
    else:
        for label, key in (
                ('Pontos fortes', 'strengths'), ('Fragilidades', 'fragilities'),
                ('Riscos', 'risks'), ('Oportunidades', 'opportunities'),
                ('Evidência insuficiente', 'insufficient_evidence')):
            items = summary.get(key)
            if isinstance(items, list) and items:
                html += '<h3>' + text(label) + '</h3><ul>'
                html += ''.join('<li>' + text(item) + '</li>' for item in items[:30])
                html += '</ul>'
        if isinstance(summary.get('plan_overview'), str) and summary['plan_overview']:
            html += '<p><strong>Encadeamento registrado:</strong> ' + text(summary['plan_overview']) + '</p>'
    html += '<h2>Fases do roteiro persistido</h2>'
    if not roadmap:
        return html + '<p>N/D — sequência de fases não disponível; nenhuma ordem foi inferida.</p>'
    by_id = {str(row.get('action_id')): row for row in rows(['directed_analysis_actions'])
             if row.get('action_id') is not None}
    html += '<p>Fases são síntese consultiva; somente decisões vinculadas autorizam ações do plano do cliente.</p>'
    for index, phase in enumerate(roadmap):
        if not isinstance(phase, dict):
            continue
        raw_ids = phase.get('action_ids')
        ids = [str(x) for x in raw_ids if str(x) in by_id] if isinstance(raw_ids, list) else []
        matched = [by_id[x] for x in dict.fromkeys(ids)]
        accepted = sum(governance.disposition('directed_analysis_actions', a) == 'Aceita pela governança'
                       for a in matched)
        undecided = sum(governance.disposition('directed_analysis_actions', a)
                        not in {'Aceita pela governança', 'Excluída do plano do cliente'}
                        for a in matched)
        rejected = len(matched) - accepted - undecided
        html += ('<details><summary>' + text(phase.get('phase') or f'Fase {index + 1}')
                 + '</summary>' + kv([
                     ('Objetivo registrado', phase.get('objective')),
                     ('Ações com ID persistido vinculado', len(matched)),
                     ('Aceitas pela governança', accepted),
                     ('Sem decisão ou pendentes', undecided),
                     ('Rejeitadas / fora do plano', rejected)])
                 + '</details>')
    return html


def render_plan(rows, timezone_name, governance):
    if not rows(['directed_analysis_runs', 'directed_analysis_actions',
                 'recommendations', 'improvement_intelligence_recommendations',
                 'content_remediation_suggestions', 'recommendation_governance',
                 'remediation_groups']):
        partial = any(r.get('processing_status') == 'PARTIAL_RETRYABLE'
                      for r in rows(['audit_fulfillment_contracts']))
        heading = ('Plano de ação não produzido nesta auditoria parcial' if partial
                   else 'Plano de ação não materializado nas fontes disponíveis')
        return ('<h2>' + heading + '</h2>'
                '<p class="callout w">Não há ações propostas ou aprovadas registradas. '
                'Os estados e motivos comprovados das análises constam na situação '
                'da execução. Achados técnicos são material informativo para '
                'análise; não autorizam execução nem estabelecem prioridades.</p>'
                + kv([('Ações propostas registradas', 0), ('Ações aprovadas registradas', 0)])
                + '<details><summary>Como interpretar aprovação e ausência de plano</summary>'
                '<p>Recomendações e textos sugeridos precisam de decisão de governança '
                'vinculada para integrar o plano aprovado. Não executado, não configurado '
                'e não aprovado são condições distintas. Nenhuma decisão foi inferida. '
                'O inventário técnico integral permanece acessível nesta apresentação.</p></details>')
    groups=grouped_actions(rows(['directed_analysis_actions']))
    priorities=Counter(group[0].get('priority') for group in groups)
    html = '<h2>Causas-raiz e prioridades do motor</h2>'
    root_groups = rows(['remediation_groups'])
    html += '<p class="rf">Prioridade do motor (P1/P2, score): classificação persistida dos grupos; não é a prioridade das ações do plano direcionado e não implica aprovação da governança.</p>'
    if root_groups:
        ordered = sorted(root_groups,
                         key=lambda item: (-float(item.get('priority_score') or 0),
                                           str(item.get('group_id') or '')))
        html += table('Grupos por causa-raiz', ordered, [
            ('rule_id', 'Regra'), ('root_cause', 'Causa-raiz'),
            ('priority_class', 'Prioridade do motor'), ('priority_score', 'Score de prioridade'),
            ('severity', 'Severidade'), ('impact', 'Impacto'), ('effort', 'Esforço'),
            ('affected_findings', 'Achados afetados')
        ], timezone_name)
        for group in ordered:
            affected = group.get('affected_findings')
            if isinstance(affected, str):
                try:
                    affected = json.loads(affected)
                except (TypeError, ValueError):
                    affected = [affected]
            html += ('<details><summary>' + text(group.get('rule_id')) + ' · ' +
                     text(group.get('root_cause')) + '</summary>')
            html += kv([('Prioridade do motor', group.get('priority_class')),
                        ('Pontuação de prioridade', group.get('priority_score')),
                        ('Severidade', group.get('severity')),
                        ('Impacto', group.get('impact')), ('Esforço', group.get('effort'))])
            html += '<h3>Todos os achados afetados</h3>' + content(affected)
            html += technical_reference(group.get('_ref')) + '</details>'
    else:
        html += '<p>Nenhum grupo de remediação persistido nesta auditoria.</p>'
    action_occurrences = rows(['directed_analysis_actions'])
    title_groups = {}
    for row in action_occurrences:
        title_groups.setdefault(str(row.get('title') or 'Título não registrado'), []).append(row)
    html += '<details><summary>Ocorrências por título do plano direcionado (' + (
        str(len(action_occurrences)) + ' ocorrências / ' + str(len(title_groups)) +
        ' títulos)</summary>')
    html += '<p class="rf">Prioridade do plano direcionado (Alta/Média/Baixa): hierarquia independente da prioridade do motor. Todas as ocorrências são preservadas, sem fusão por título.</p>'
    for title, entries in sorted(title_groups.items()):
        html += '<details><summary>' + text(title) + ' · ' + str(len(entries)) + ' ocorrência(s)</summary>'
        html += table('Registros integrais por título: ' + title, entries, [
            ('action_id', 'ID'), ('title', 'Título'), ('priority', 'Prioridade do plano direcionado'),
            ('source_id', 'Origem'), ('effort', 'Esforço'), ('_ref', 'Detalhe persistido')
        ], timezone_name)
        html += '</details>'
    html += '</details>'
    html += '<h2>Visão geral</h2>'+origin('Calculado no relatório')
    html+=kv([('Ações (ocorrências)',sum(map(len,groups))),('Ações distintas por ID',sum(bool(g[0].get('action_id')) for g in groups)),('Ocorrências sem ID',sum(not g[0].get('action_id') for g in groups)),('Crítica',priorities['CRITICAL']),('Alta',priorities['HIGH']),('Média',priorities['MEDIUM']),('Baixa',priorities['LOW']),('Sem prioridade',priorities[None]+priorities['']),('Origem explicitamente IA de conteúdo',sum(g[0].get('source_kind')=='CONTENT_AI' for g in groups))])
    html+='<p class="rf">Contagens de apresentação por action_id; não há deduplicação por título. Ocorrências sem ID permanecem separadas, sem afirmar identidade distinta. Origens de IA não explícitas não são inferidas. Prioridades não reconhecidas permanecem no detalhe.</p>'
    decisions = rows(['recommendation_governance'])
    html += kv([('Decisões aceitas', sum(d.get('decision') == 'ACCEPTED' for d in decisions) if decisions else None),
                ('Decisões rejeitadas', sum(d.get('decision') == 'REJECTED' for d in decisions) if decisions else None)])
    html += '<p>Os IDs contam o inventário técnico. Apenas a decisão vinculada identifica uma ação aceita. Itens excluídos permanecem no detalhe técnico.</p>'
    html += strategic_context(rows, governance)
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
                           'Somente ações expressamente aceitas pela governança e direcionadas ao cliente. Prioridade não equivale a aprovação.', 0)
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
