"""Abertura do navegador (perfil persistente) e captura da autenticação usada pelo próprio site."""

import os
from pathlib import Path
from urllib.parse import urlparse

from .config import PREFIXOS_API

# Cabeçalhos que o site do PJe manda para a própria API e que o robô reaproveita.
# Ficam só em memória: nunca são gravados em disco nem no log.
CABECALHOS_AUTH = ("authorization", "x-xsrf-token")


def abrir_contexto(playwright, pasta_perfil: Path, navegador: str, oculto: bool):
    """Abre Edge/Chrome com um perfil próprio do robô, que guarda a sessão entre execuções."""
    pasta_perfil.mkdir(parents=True, exist_ok=True)
    opcoes = {
        "user_data_dir": str(pasta_perfil),
        "headless": oculto,
        "accept_downloads": True,
        "no_viewport": True,
    }
    executavel = os.environ.get("PJE_ROBO_NAVEGADOR_EXE")
    if executavel:
        opcoes["executable_path"] = executavel
    elif navegador in ("msedge", "chrome"):
        opcoes["channel"] = navegador
    contexto = playwright.chromium.launch_persistent_context(**opcoes)
    try:
        # O login por certificado faz o site falar com o PJeOffice em localhost:8800.
        # Navegadores recentes pedem permissão de "rede local"; concede quando o Playwright suporta.
        contexto.grant_permissions(["local-network-access"])
    except Exception:
        pass
    return contexto


class CapturaAuth:
    """Observa as requisições do site para a API do PJe e guarda os cabeçalhos de autenticação por host."""

    def __init__(self):
        self._por_host: dict[str, dict[str, str]] = {}

    def __call__(self, request) -> None:
        url = urlparse(request.url)
        if not url.path.startswith(PREFIXOS_API):
            return
        cabecalhos = request.headers
        achados = {k: cabecalhos[k] for k in CABECALHOS_AUTH if cabecalhos.get(k)}
        if achados:
            self._por_host.setdefault(url.netloc, {}).update(achados)

    def de(self, host: str) -> dict[str, str]:
        return dict(self._por_host.get(host, {}))


class RegistroChamadas:
    """Para o modo `mapear`: anota método, rota e status das chamadas à API (sem cabeçalhos nem corpo)."""

    def __init__(self, arquivo: Path):
        self.arquivo = arquivo
        self.vistos: set[tuple[str, str, int]] = set()

    def __call__(self, response) -> None:
        import json
        import re

        url = urlparse(response.url)
        if not url.path.startswith(PREFIXOS_API):
            return
        rota = re.sub(r"/\d+(?=/|$)", "/{n}", url.path)
        rota = re.sub(r"\d{7}-\d{2}\.\d{4}\.\d\.\d{2}\.\d{4}", "{numero}", rota)
        chave = (response.request.method, rota, response.status)
        if chave in self.vistos:
            return
        self.vistos.add(chave)
        parametros = sorted({p.split("=")[0] for p in url.query.split("&") if p})
        with open(self.arquivo, "a", encoding="utf-8") as f:
            f.write(json.dumps({"metodo": chave[0], "rota": rota, "parametros": parametros,
                                "status": chave[2], "host": url.netloc}, ensure_ascii=False) + "\n")
