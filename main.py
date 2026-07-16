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

from dotenv import load_dotenv
from fastapi import FastAPI, HTTPException

load_dotenv()  # carrega variáveis do .env em desenvolvimento local; em
                # produção (Render/Railway) as variáveis vêm do painel da
                # plataforma e este comando não tem efeito
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


RESPOSTA_REDIRECIONA_SIMULADOR = (
    "Não calculo valores diretamente por aqui, para evitar erro de estimativa. "
    "Use o simulador (/simular/financiamento ou /simular/juros-compostos) "
    "para ver a parcela, os juros totais e a evolução do saldo devedor com "
    "precisão."
)

_PALAVRAS_PEDIDO_DE_CALCULO = (
    "quanto fica", "quanto seria", "quanto ficaria", "qual o valor",
    "qual a parcela", "valor da parcela", "calcul",
)


def _parece_pedido_de_calculo(pergunta: str) -> bool:
    pergunta_lower = pergunta.lower()
    if any(c.isdigit() for c in pergunta_lower):
        return True
    return any(frase in pergunta_lower for frase in _PALAVRAS_PEDIDO_DE_CALCULO)


def _responder_faq_local(pergunta: str) -> Optional[str]:
    if _parece_pedido_de_calculo(pergunta):
        return RESPOSTA_REDIRECIONA_SIMULADOR

    pergunta_lower = pergunta.lower()
    for chave, resposta in FAQ_LOCAL.items():
        if chave in pergunta_lower:
            return resposta
    return None


def _responder_faq_gemini(pergunta: str) -> Optional[str]:
    """
    Usa a API gratuita do Google AI Studio (Gemini). Requer GEMINI_API_KEY.
    Retorna None se a chave não estiver configurada ou todas as tentativas
    falharem — quem chama trata o fallback.

    Tenta 2 modelos (o mais novo e um estável de reserva) com retry curto em
    cada um, porque erros 503 (servidor sobrecarregado) são comuns e
    geralmente passageiros — não devem derrubar a demo sem pelo menos
    tentar de novo.
    """
    api_key = os.environ.get("GEMINI_API_KEY")
    if not api_key:
        return None

    import time
    import requests

    system_prompt = open(
        os.path.join(os.path.dirname(__file__), "prompts", "system_prompt.md")
    ).read()
    body = {
        "system_instruction": {"parts": [{"text": system_prompt}]},
        "contents": [{"role": "user", "parts": [{"text": pergunta}]}],
    }

    modelos = ["gemini-flash-latest", "gemini-2.5-flash-lite"]
    tentativas_por_modelo = 2

    for modelo in modelos:
        url = f"https://generativelanguage.googleapis.com/v1beta/models/{modelo}:generateContent?key={api_key}"
        for tentativa in range(tentativas_por_modelo):
            try:
                resposta = requests.post(url, json=body, timeout=25)
                if resposta.status_code == 503:
                    time.sleep(1.5)
                    continue
                resposta.raise_for_status()
                dados = resposta.json()
                return dados["candidates"][0]["content"]["parts"][0]["text"]
            except Exception:
                time.sleep(0.5)
                continue

    return None


def _responder_faq_anthropic(pergunta: str) -> Optional[str]:
    """
    Usa a API paga da Anthropic (Claude). Requer ANTHROPIC_API_KEY.
    Alternativa ao Gemini, caso você queira comparar qualidade de resposta
    ou já tenha crédito disponível.
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


def _responder_faq_llm(pergunta: str, historico: list[dict]) -> Optional[str]:
    """
    Tenta responder via modelo generativo, na ordem: Gemini (gratuito) →
    Anthropic (pago, se configurado). Retorna None se nenhuma chave estiver
    disponível ou ambas as chamadas falharem — quem chama trata o fallback
    para o FAQ local.
    """
    resposta = _responder_faq_gemini(pergunta)
    if resposta is not None:
        return resposta
    return _responder_faq_anthropic(pergunta)


@app.post("/faq")
def responder_faq(req: PerguntaFaqRequest):
    session_id = _get_or_create_sessao(req.session_id)
    historico = SESSOES[session_id]

    resposta = _responder_faq_gemini(req.pergunta)
    origem = "gemini"

    if resposta is None:
        resposta = _responder_faq_anthropic(req.pergunta)
        origem = "anthropic"

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