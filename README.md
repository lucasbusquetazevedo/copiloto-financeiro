# Copiloto Financeiro

Assistente virtual para dúvidas e simulações financeiras básicas, combinando
IA generativa (interpretação de linguagem natural) com cálculo financeiro
determinístico (Python puro).

Projeto desenvolvido como desafio de trilha em IA Generativa, Prompt
Engineering e desenvolvimento de agentes.

## O que é real vs. o que é demonstrativo

Sendo direto sobre os limites do projeto:

| Componente | Real | Observação |
|---|---|---|
| Cálculo de financiamento (Tabela Price) | ✅ Real | Fórmula financeira padrão, testada |
| Cálculo de juros compostos | ✅ Real | Fórmula financeira padrão, testada |
| Respostas em linguagem natural | ✅ Real (com fallback) | Usa modelo generativo; se indisponível, cai para respostas locais pré-validadas |
| Persistência de contexto | ⚠️ Demonstrativa | Em memória, por sessão. Não sobrevive a restart — suficiente para demo, não para produção |
| Recomendação financeira | ❌ Não existe | O agente explica conceitos, não recomenda produtos específicos (ver `prompts/system_prompt.md`) |

Este NÃO é um produto de consultoria financeira real. É uma demonstração de
como estruturar um agente de IA generativa com guardrails para um domínio
onde erro numérico tem custo alto.

## Por que essa arquitetura

O maior risco de um agente financeiro construído sobre um LLM é a
alucinação de números — o modelo "inventar" uma parcela ou taxa de forma
plausível, mas errada. Por isso:

- **Todo cálculo é feito em Python determinístico** (`financas.py`), nunca
  pelo modelo de linguagem. O LLM só interpreta a pergunta e decide *quando*
  chamar a simulação — ele nunca calcula.
- **O FAQ tem fallback local.** Se a chamada ao modelo generativo falhar
  (sem rede, sem API key, rate limit), o sistema responde com conteúdo
  local pré-validado em vez de simplesmente quebrar.
- **O prompt do sistema é versionado separadamente**
  (`prompts/system_prompt.md`), não embutido direto no código — fica
  auditável e fácil de revisar isoladamente.

## Estrutura

```
copiloto-financeiro/
├── main.py                    # API FastAPI
├── financas.py                # Cálculos determinísticos (Price, juros compostos)
├── prompts/
│   └── system_prompt.md       # Prompt do sistema documentado
├── tests/
│   └── test_financas.py       # Testes das funções financeiras
└── requirements.txt
```

## Como rodar localmente

```bash
pip install -r requirements.txt
uvicorn main:app --reload
```

A API sobe em `http://localhost:8000`. Documentação automática (Swagger) em
`http://localhost:8000/docs`.

Para habilitar respostas via modelo generativo, definir a variável de
ambiente `ANTHROPIC_API_KEY`. Sem ela, o FAQ funciona normalmente em modo
local.

## Endpoints principais

- `POST /simular/financiamento` — simulação completa pelo Sistema Price
- `POST /simular/juros-compostos` — cálculo de montante com juros compostos
- `POST /faq` — pergunta em linguagem natural sobre conceitos financeiros
- `GET /sessao/{session_id}` — histórico de interações da sessão

## Rodando os testes

```bash
python3 tests/test_financas.py
```

## Próximos passos (fora do escopo deste MVP)

- Módulo de explicação de risco cruzando com o projeto de [detecção de
  anomalias em transações](https://github.com/lucasbusquetazevedo/deteccao-anomalias-transacoes):
  o agente reconhece perguntas sobre transação suspeita e explica, em
  linguagem simples, os sinais que um modelo de detecção de anomalias olha —
  sem prometer detecção real de fraude.
- Persistência de sessão em banco de dados para uso além de demonstração.
