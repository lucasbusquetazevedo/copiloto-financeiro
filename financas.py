"""
Módulo de cálculos financeiros determinísticos.

Por que separado do resto: o LLM nunca deve fazer contas. Ele só interpreta a
pergunta do usuário, extrai os parâmetros (valor, taxa, prazo) e chama estas
funções. O número que aparece pro usuário sempre vem daqui, nunca do modelo de
linguagem. Isso evita o erro mais comum em agentes financeiros: alucinação de
valores numéricos.
"""

from dataclasses import dataclass, field


@dataclass
class ParcelaPrice:
    numero: int
    parcela: float
    juros: float
    amortizacao: float
    saldo_devedor: float


@dataclass
class ResultadoFinanciamento:
    valor_financiado: float
    taxa_mensal: float
    n_parcelas: int
    valor_parcela: float
    total_pago: float
    total_juros: float
    parcelas: list = field(default_factory=list)


def tabela_price(valor_financiado: float, taxa_mensal: float, n_parcelas: int) -> ResultadoFinanciamento:
    """
    Calcula financiamento pelo Sistema Price (parcelas fixas).

    valor_financiado: valor a ser financiado (PV)
    taxa_mensal: taxa de juros ao mês, em decimal (ex: 0.015 para 1,5% a.m.)
    n_parcelas: número de parcelas mensais

    Fórmula: PMT = PV * i / (1 - (1 + i)^-n)
    """
    if valor_financiado <= 0:
        raise ValueError("valor_financiado deve ser maior que zero")
    if n_parcelas <= 0:
        raise ValueError("n_parcelas deve ser maior que zero")
    if taxa_mensal < 0:
        raise ValueError("taxa_mensal não pode ser negativa")

    if taxa_mensal == 0:
        # caso sem juros: parcela é só o valor dividido igualmente
        parcela = valor_financiado / n_parcelas
    else:
        i = taxa_mensal
        parcela = valor_financiado * i / (1 - (1 + i) ** -n_parcelas)

    saldo = valor_financiado
    parcelas = []
    total_pago = 0.0

    for numero in range(1, n_parcelas + 1):
        juros_mes = saldo * taxa_mensal
        amortizacao = parcela - juros_mes
        saldo = max(saldo - amortizacao, 0.0)
        total_pago += parcela

        parcelas.append(
            ParcelaPrice(
                numero=numero,
                parcela=round(parcela, 2),
                juros=round(juros_mes, 2),
                amortizacao=round(amortizacao, 2),
                saldo_devedor=round(saldo, 2),
            )
        )

    total_juros = total_pago - valor_financiado

    return ResultadoFinanciamento(
        valor_financiado=round(valor_financiado, 2),
        taxa_mensal=taxa_mensal,
        n_parcelas=n_parcelas,
        valor_parcela=round(parcela, 2),
        total_pago=round(total_pago, 2),
        total_juros=round(total_juros, 2),
        parcelas=parcelas,
    )


def juros_compostos(principal: float, taxa_mensal: float, n_meses: int) -> dict:
    """
    Calcula o montante final de um valor aplicado a juros compostos.
    Usado no FAQ para explicar conceito, não é o simulador principal do MVP.
    """
    if principal <= 0 or n_meses <= 0 or taxa_mensal < 0:
        raise ValueError("parâmetros inválidos")

    montante = principal * (1 + taxa_mensal) ** n_meses
    return {
        "principal": round(principal, 2),
        "taxa_mensal": taxa_mensal,
        "n_meses": n_meses,
        "montante_final": round(montante, 2),
        "rendimento": round(montante - principal, 2),
    }
