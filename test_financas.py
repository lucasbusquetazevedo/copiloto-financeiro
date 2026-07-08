import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from financas import tabela_price, juros_compostos


def test_tabela_price_parcela_fixa():
    resultado = tabela_price(valor_financiado=10000, taxa_mensal=0.015, n_parcelas=12)
    parcelas = [p.parcela for p in resultado.parcelas]
    # todas as parcelas devem ser iguais (característica do sistema Price)
    assert len(set(parcelas)) == 1
    assert resultado.n_parcelas == 12


def test_tabela_price_saldo_zera_no_final():
    resultado = tabela_price(valor_financiado=5000, taxa_mensal=0.02, n_parcelas=6)
    assert resultado.parcelas[-1].saldo_devedor == 0.0


def test_tabela_price_sem_juros():
    resultado = tabela_price(valor_financiado=1200, taxa_mensal=0.0, n_parcelas=12)
    assert resultado.valor_parcela == 100.0
    assert resultado.total_juros == 0.0


def test_tabela_price_valida_entrada():
    try:
        tabela_price(valor_financiado=-100, taxa_mensal=0.01, n_parcelas=12)
        assert False, "deveria ter lançado ValueError"
    except ValueError:
        pass


def test_juros_compostos():
    resultado = juros_compostos(principal=1000, taxa_mensal=0.01, n_meses=12)
    assert resultado["montante_final"] > 1000
    assert round(resultado["rendimento"], 2) == round(resultado["montante_final"] - 1000, 2)


if __name__ == "__main__":
    test_tabela_price_parcela_fixa()
    test_tabela_price_saldo_zera_no_final()
    test_tabela_price_sem_juros()
    test_tabela_price_valida_entrada()
    test_juros_compostos()
    print("Todos os testes passaram.")
