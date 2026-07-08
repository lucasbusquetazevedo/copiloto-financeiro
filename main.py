"""
Copiloto Financeiro — API principal.

Arquitetura (e por quê):
- Cálculo financeiro é 100% determinístico (financas.py). O LLM nunca gera número.
- O FAQ tenta usar um modelo generativo; se a chamada falhar (sem API key, rede
  fora, rate limit), cai automaticam"mente para respostas locais pré-validadas.
  Isso existe especificamente para não deixar uma demo ao vivo quebrar por
  causa de rede.
- Contexto de conversa fica em memória, por session_id. Suficiente para uma
  demo; não é para produção (não sobrevive a restart, não escala).
"""

import os
import uuid
from typing import Optional

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

from financas import tabela_price, juros_compostos

app = FastAPI(title="Copiloto Financeiro", version="0.1.0")

# CORS liberado para facilitar integração com o frontend (Lovable) durante o
# desenvolvimento. Antes de ir para produção de verdade, restringir a origem.
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

# ---------------------------------------------------------------------------
# Contexto de sessão (em memória — ver aviso no docstring do módulo)
# ---------------------------------------------------------------------------
SESSOES: dict[str, list[dict]] = {}

FAQ_LOCAL = {
    "financiamento": (
        "Financiamento é quando você toma um valor emprestado para comprar "
        "algo (geralmente imóvel ou veículo) e paga de volta em parcelas, com "
        "juros. O sistema mais comum no Brasil é o Price, onde a parcela é "
        "fixa do início ao fim, mas a proporção entre juros e amortização "
        "muda mês a mês."
    ),
    "juros compostos": (
        "Juros compostos são juros sobre juros: a cada período, o rendimento "
        "anterior passa a fazer parte do valor que rende no período seguinte. "
        "É por isso que o crescimento acelera com o tempo, diferente dos "
        "juros simples."
    ),
    "cartao de credito": (
        "O cartão de crédito rotativo é a linha de crédito mais cara do "
        "mercado brasileiro. Se você paga só o mínimo da fatura, o restante "
        "entra no rotativo e passa a render juros muito altos sobre o saldo "
        "devedor — por isso costuma ser a última opção, não a primeira."
    ),
}


class SimulacaoFinanciamentoRequest(BaseModel):
    valor: float
    taxa_mensal: float
    parcelas: int
    session_id: Optional[str] = None


class JurosCompostosRequest(BaseModel):
    principal: float
    taxa_mensal: float
    meses: int
    session_id: Optional[str] = None


class PerguntaFaqRequest(BaseModel):
    pergunta: str
    session_id: Optional[str] = None


def _get_or_create_sessao(session_id: Optional[str]) -> str:
    if session_id and session_id in SESSOES:
        return session_id
    novo_id = session_id or str(uuid.uuid4())
    SESSOES.setdefault(novo_id, [])
    return novo_id


def _registrar_interacao(session_id: str, tipo: str, payload: dict) -> None:
    SESSOES[session_id].append({"tipo": tipo, "dados": payload})


@app.get("/")
def raiz():
    return {"status": "ok", "servico": "Copiloto Financeiro"}


@app.post("/simular/financiamento")
def simular_financiamento(req: SimulacaoFinanciamentoRequest):
    try:
        resultado = tabela_price(req.valor, req.taxa_mensal, req.parcelas)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))

    session_id = _get_or_create_sessao(req.session_id)
    _registrar_interacao(session_id, "simulacao_financiamento", {
        "valor": req.valor, "parcelas": req.parcelas, "resultado_parcela": resultado.valor_parcela
    })

    return {"session_id": session_id, "resultado": resultado}


@app.post("/simular/juros-compostos")
def simular_juros_compostos(req: JurosCompostosRequest):
    try:
        resultado = juros_compostos(req.principal, req.taxa_mensal, req.meses)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))

    session_id = _get_or_create_sessao(req.session_id)
    _registrar_interacao(session_id, "simulacao_juros_compostos", resultado)

    return {"session_id": session_id, "resultado": resultado}


def _responder_faq_local(pergunta: str) -> Optional[str]:
    pergunta_lower = pergunta.lower()
    for chave, resposta in FAQ_LOCAL.items():
        if chave in pergunta_lower:
            return resposta
    return None


def _responder_faq_llm(pergunta: str, historico: list[dict]) -> Optional[str]:
    """
    Tenta responder via modelo generativo. Retorna None se não houver API key
    configurada ou se a chamada falhar — quem chama essa função trata o
    fallback para o FAQ local.
    """
    api_key = os.environ.get("ANTHROPIC_API_KEY")
    if not api_key:
        return None

    try:
        import anthropic

        client = anthropic.Anthropic(api_key=api_key)
        system_prompt = open(
            os.path.join(os.path.dirname(__file__), "prompts", "system_prompt.md")
        ).read()

        resposta = client.messages.create(
            model="claude-sonnet-4-6",
            max_tokens=400,
            system=system_prompt,
            messages=[{"role": "user", "content": pergunta}],
        )
        return resposta.content[0].text
    except Exception:
        return None


@app.post("/faq")
def responder_faq(req: PerguntaFaqRequest):
    session_id = _get_or_create_sessao(req.session_id)
    historico = SESSOES[session_id]

    resposta = _responder_faq_llm(req.pergunta, historico)
    origem = "llm"

    if resposta is None:
        resposta = _responder_faq_local(req.pergunta)
        origem = "faq_local"

    if resposta is None:
        resposta = (
            "Não tenho uma resposta confiável para essa pergunta ainda. "
            "Posso te ajudar com dúvidas sobre financiamento, juros compostos "
            "ou cartão de crédito."
        )
        origem = "fallback_generico"

    _registrar_interacao(session_id, "faq", {"pergunta": req.pergunta, "origem": origem})

    return {"session_id": session_id, "resposta": resposta, "origem": origem}


@app.get("/sessao/{session_id}")
def ver_sessao(session_id: str):
    if session_id not in SESSOES:
        raise HTTPException(status_code=404, detail="sessão não encontrada")
    return {"session_id": session_id, "historico": SESSOES[session_id]}
