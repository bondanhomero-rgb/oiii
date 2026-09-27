import pytest

from robo_pje.cnj import NumeroInvalido, calcular_dv, normalizar, tribunal_do_numero

# Número real do TRT2, aceito pela API pública do PJe.
VALIDO_TRT2 = "0000074-94.2010.5.02.0043"


def test_numero_real_do_trt2_confere():
    assert normalizar(VALIDO_TRT2) == VALIDO_TRT2
    assert normalizar("00000749420105020043") == VALIDO_TRT2
    assert tribunal_do_numero(VALIDO_TRT2) == "trt2"


def test_digito_errado_e_recusado():
    with pytest.raises(NumeroInvalido, match="dígito verificador"):
        normalizar("0000074-95.2010.5.02.0043")


def test_tamanho_errado_e_recusado():
    with pytest.raises(NumeroInvalido, match="20 dígitos"):
        normalizar("123")


def test_justica_estadual_nao_e_trt():
    dv = calcular_dv("1234567", "2024", "8", "26", "0100")
    numero = normalizar(f"1234567-{dv}.2024.8.26.0100")
    assert tribunal_do_numero(numero) is None


def test_trt_de_dois_digitos():
    dv = calcular_dv("0010001", "2025", "5", "15", "0001")
    assert tribunal_do_numero(f"0010001-{dv}.2025.5.15.0001") == "trt15"
