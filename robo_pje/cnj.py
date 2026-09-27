"""Número único de processo (CNJ, Resolução 65/2008): validação e tribunal de origem."""

import re


class NumeroInvalido(ValueError):
    pass


def calcular_dv(sequencial: str, ano: str, justica: str, tribunal: str, origem: str) -> str:
    resto = int(f"{sequencial}{ano}{justica}{tribunal}{origem}00") % 97
    return f"{98 - resto:02d}"


def normalizar(numero: str) -> str:
    """Devolve o número no formato NNNNNNN-DD.AAAA.J.TR.OOOO, conferindo o dígito verificador."""
    digitos = re.sub(r"\D", "", numero or "")
    if len(digitos) != 20:
        raise NumeroInvalido(f"{numero!r}: o número CNJ tem 20 dígitos")
    seq, dv, ano, j, tr, orig = (
        digitos[0:7], digitos[7:9], digitos[9:13], digitos[13], digitos[14:16], digitos[16:20]
    )
    esperado = calcular_dv(seq, ano, j, tr, orig)
    if dv != esperado:
        raise NumeroInvalido(f"{numero!r}: dígito verificador {dv} não confere (esperado {esperado})")
    return f"{seq}-{dv}.{ano}.{j}.{tr}.{orig}"


def tribunal_do_numero(numero: str) -> str | None:
    """'trtN' para processos da Justiça do Trabalho (J=5); None para os demais ramos."""
    digitos = re.sub(r"\D", "", numero)
    if len(digitos) == 20 and digitos[13] == "5" and digitos[14:16] != "00":
        return f"trt{int(digitos[14:16])}"
    return None
