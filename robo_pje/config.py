"""Endereços dos tribunais e rotas da API do PJe (Justiça do Trabalho)."""

import re
from dataclasses import dataclass
from urllib.parse import urlparse

# Rotas da API do PJe usadas na coleta. A existência de cada uma foi conferida
# (respondem "precisa de login", e não "API inexistente"); o formato exato das
# respostas só se confirma no primeiro uso logado. Se o tribunal mudar algo,
# rode `python -m robo_pje mapear` e ajuste aqui.
ROTAS = {
    "dados_basicos": "/pje-consulta-api/api/processos/dadosbasicos/{numero}",
    "capa": "/pje-comum-api/api/processos/id/{id}",
    "partes": "/pje-comum-api/api/processos/id/{id}/partes",
    "timeline": "/pje-comum-api/api/processos/id/{id}/timeline?buscarMovimentos=true&buscarDocumentos=true",
    "expedientes": "/pje-comum-api/api/processos/id/{id}/expedientes",
    "documento": "/pje-comum-api/api/processos/id/{id}/documentos/id/{doc_id}/conteudo",
}

# Chamadas do próprio site do PJe que carregam a autenticação que o robô reaproveita.
PREFIXOS_API = ("/pje-comum-api/", "/pje-seguranca/", "/pje-consulta-api/")

CAMINHO_GRAU = {1: "primeirograu", 2: "segundograu"}


@dataclass(frozen=True)
class Tribunal:
    sigla: str
    base_url: str
    grau: int = 1

    @property
    def host(self) -> str:
        return urlparse(self.base_url).netloc

    @property
    def url_login(self) -> str:
        return f"{self.base_url}/{CAMINHO_GRAU[self.grau]}/login.seam"

    @property
    def url_painel(self) -> str:
        return f"{self.base_url}/pjekz/"


def tribunal(sigla: str, grau: int = 1, base_url: str | None = None) -> Tribunal:
    if grau not in CAMINHO_GRAU:
        raise ValueError(f"Grau inválido: {grau} (use 1 ou 2)")
    sigla = sigla.lower().strip()
    if base_url:
        return Tribunal(sigla, base_url.rstrip("/"), grau)
    m = re.fullmatch(r"trt(\d{1,2})", sigla)
    if not m or not 1 <= int(m[1]) <= 24:
        raise ValueError(
            f"Tribunal não suportado: {sigla!r}. Por enquanto só TRT1 a TRT24 "
            "(PJe da Justiça do Trabalho); para outro PJe use --base-url."
        )
    return Tribunal(f"trt{int(m[1])}", f"https://pje.trt{int(m[1])}.jus.br", grau)
