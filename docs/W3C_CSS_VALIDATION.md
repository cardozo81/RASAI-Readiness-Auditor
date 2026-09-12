# W3C CSS Validation no RASAi

## Objetivo

O RASAi integra o **W3C CSS Validation Service** como evidência complementar de conformidade CSS por URL. A integração pertence à família de Web Quality/Standards, com relação **3/5** com Search & AI Readiness. Ela não altera `SARI-001` nem `SCORE-GEO-004`.

O RASAi não cria um “W3C CSS Score”. Ele preserva o resultado de validade e as contagens emitidas pela própria fonte.

## Referências oficiais

- serviço: https://jigsaw.w3.org/css-validator/
- API programática SOAP 1.2: https://jigsaw.w3.org/css-validator/api.html
- manual/parâmetros: https://jigsaw.w3.org/css-validator/manual.html

A documentação pública do W3C pede que automações que validem um conjunto de documentos aguardem **pelo menos 1 segundo entre requests** ao serviço público. O runtime do RASAi aplica esse throttling.

## Controle

```text
RASAI_W3C_CSS_VALIDATOR=true|false
```

Default: `true`.

O serviço não exige credencial nem possui cobrança de provider. Por isso fica habilitado por padrão, podendo ser desligado explicitamente pelo usuário.

Limites compartilhados com os demais validadores desta família:

```text
RASAI_STANDARDS_MAX_URLS=10
RASAI_STANDARDS_TIMEOUT_SECONDS=20
```

`RASAI_STANDARDS_MAX_URLS=0` permite todo o universo auditado, mas não é recomendado para uso indiscriminado do endpoint público. Para SaaS em escala, uma instância controlada/self-host deve ser preferida quando operacionalmente viável.

## Método

Para cada URL dentro do orçamento:

1. o RASAi chama o endpoint oficial por URI;
2. solicita `output=soap12`;
3. usa o perfil `css3` exposto pelo serviço;
4. usa `warning=0` para limitar ruído;
5. aguarda pelo menos 1 segundo antes da próxima URL;
6. interpreta `validity`, `errorcount`, `warningcount`, `csslevel`, `checkedby` e data quando presentes.

A observação persistida usa:

```text
metric_id = w3c_css_conformance
scope = URL
source = W3C CSS Validation Service
methodology = W3C CSS Validator SOAP 1.2; profile=css3; warning=0
```

Estados:

- `PASS`: o serviço retornou `validity=true`;
- `FAIL`: o serviço retornou `validity=false`;
- `ERROR`: falha de transporte, HTTP ou resposta SOAP não determinável;
- `DISABLED`: toggle explicitamente desligado;
- `NO_DATA`: serviço habilitado, mas nenhuma URL aplicável foi submetida.

## Fronteiras metodológicas

Validação CSS mede conformidade sintática/semântica segundo a implementação e o perfil do validador. Ela não mede, isoladamente:

- compatibilidade real entre todos os browsers;
- acessibilidade;
- experiência de usuário;
- Core Web Vitals;
- indexabilidade;
- elegibilidade para Search ou AI retrieval.

Por isso o dado aparece em `standards.html` como evidência complementar e permanece fora do cálculo automático de SARI.

## SaaS

No SaaS, `w3c_css_validator` é uma escolha não secreta do `AuditJob`. O worker não precisa de credencial. Ainda assim há impacto operacional:

- egress;
- latência mínima adicional pelo throttling de 1 s entre URLs;
- dependência da disponibilidade do serviço público;
- possibilidade de rate limiting;
- envio da URL alvo ao validador externo.

O endpoint público deve ser tratado como recurso comunitário, não como infraestrutura ilimitada para alta escala.