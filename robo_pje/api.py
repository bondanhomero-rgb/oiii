"""Cliente da API do PJe, usando a sessão do navegador já logado."""

import time

from .config import ROTAS, Tribunal


class ErroAPI(Exception):
    def __init__(self, status: int, detalhe: str, url: str):
        super().__init__(f"HTTP {status} em {url.split('?')[0]}: {detalhe}")
        self.status = status


class ClientePJe:
    def __init__(self, request, trib: Tribunal, cabecalhos_auth: dict[str, str], pausa: float = 1.0):
        # `request` é o BrowserContext.request do Playwright: compartilha os cookies da sessão.
        self.request = request
        self.trib = trib
        self.cabecalhos = {
            "Accept": "application/json, text/plain, */*",
            "X-Grau-Instancia": str(trib.grau),
            **cabecalhos_auth,
        }
        self.pausa = pausa  # intervalo entre chamadas, para não sobrecarregar o tribunal

    def _get(self, rota: str, binario: bool = False, **params):
        url = self.trib.base_url + ROTAS[rota].format(**params)
        resp = self.request.get(url, headers=self.cabecalhos, timeout=60_000)
        time.sleep(self.pausa)
        if not resp.ok:
            raise ErroAPI(resp.status, resp.text()[:300], url)
        if binario:
            return resp.body(), resp.headers.get("content-type", "")
        try:
            dados = resp.json()
        except ValueError:
            raise ErroAPI(resp.status, "resposta não é JSON (sessão expirada ou página de login?)", url) from None
        if isinstance(dados, dict) and "tokenDesafio" in dados:
            raise ErroAPI(resp.status, "o tribunal pediu captcha (sessão não reconhecida)", url)
        return dados

    def id_do_processo(self, numero: str) -> int:
        dados = self._get("dados_basicos", numero=numero)
        itens = dados if isinstance(dados, list) else [dados]
        if not itens or not isinstance(itens[0], dict) or "id" not in itens[0]:
            raise ErroAPI(404, f"processo não encontrado no {self.trib.grau}º grau", numero)
        return itens[0]["id"]

    def capa(self, id_processo: int):
        return self._get("capa", id=id_processo)

    def partes(self, id_processo: int):
        return self._get("partes", id=id_processo)

    def timeline(self, id_processo: int):
        return self._get("timeline", id=id_processo)

    def expedientes(self, id_processo: int):
        return self._get("expedientes", id=id_processo)

    def documento(self, id_processo: int, id_documento) -> tuple[bytes, str]:
        return self._get("documento", binario=True, id=id_processo, doc_id=id_documento)
