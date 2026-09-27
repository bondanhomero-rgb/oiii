"""Cliente da API + coleta, com um `request` falso no lugar do navegador (sem rede)."""

import json
from urllib.parse import urlparse

import pytest

from robo_pje.api import ClientePJe, ErroAPI
from robo_pje.canal import Canal
from robo_pje.coleta import coletar
from robo_pje.config import tribunal

NUMERO = "0000074-94.2010.5.02.0043"


class RespostaFalsa:
    def __init__(self, status, corpo, tipo="application/json"):
        self.status = status
        self.ok = 200 <= status < 300
        self._corpo = corpo
        self.headers = {"content-type": tipo}

    def json(self):
        return json.loads(self._corpo)

    def text(self):
        return self._corpo if isinstance(self._corpo, str) else self._corpo.decode()

    def body(self):
        return self._corpo if isinstance(self._corpo, bytes) else self._corpo.encode()


class TribunalFalso:
    """Imita as rotas da API do PJe e exige o cabeçalho de autenticação capturado."""

    def __init__(self):
        self.timeline = [
            {"id": 2, "data": "2026-09-10T10:00:00", "titulo": "Sentença", "documento": True},
            {"id": 1, "data": "2026-09-01T09:00:00", "titulo": "Conclusos para julgamento"},
        ]
        self.chamadas = []

    def get(self, url, headers=None, timeout=None):
        self.chamadas.append((url, dict(headers or {})))
        caminho = urlparse(url).path
        if caminho.startswith("/pje-consulta-api/api/processos/dadosbasicos/"):
            return RespostaFalsa(200, json.dumps([{"id": 2700398, "numero": NUMERO}]))
        if headers.get("authorization") != "Bearer tok":
            return RespostaFalsa(400, '{"codigoErro":"SJT-004","mensagem":"Token não informado"}')
        rotas = {
            "/pje-comum-api/api/processos/id/2700398": {"id": 2700398, "classeJudicial": "ATOrd"},
            "/pje-comum-api/api/processos/id/2700398/timeline": self.timeline,
            "/pje-comum-api/api/processos/id/2700398/partes": [{"nome": "Fulano"}],
        }
        if caminho in rotas:
            return RespostaFalsa(200, json.dumps(rotas[caminho]))
        if caminho.startswith("/pje-comum-api/api/processos/id/2700398/documentos/id/"):
            return RespostaFalsa(200, b"%PDF-1.4 falso", "application/pdf")
        return RespostaFalsa(400, '{"codigoErro":"ARQ-516","mensagem":"Erro de permissão"}')


@pytest.fixture
def ambiente(tmp_path):
    falso = TribunalFalso()
    cliente = ClientePJe(falso, tribunal("trt2"), {"authorization": "Bearer tok"}, pausa=0)
    return falso, cliente, Canal(tmp_path / "estado"), tmp_path


def test_envia_grau_e_autenticacao_em_toda_chamada(ambiente):
    falso, cliente, canal, pasta = ambiente
    coletar(cliente, [NUMERO], pasta / "saida", pasta / "hist", canal)
    assert falso.chamadas
    for url, cabecalhos in falso.chamadas:
        assert url.startswith("https://pje.trt2.jus.br/")
        assert cabecalhos["X-Grau-Instancia"] == "1"
        assert cabecalhos["authorization"] == "Bearer tok"


def test_primeira_coleta_grava_arquivos_e_linha_de_base(ambiente):
    falso, cliente, canal, pasta = ambiente
    [r] = coletar(cliente, [NUMERO], pasta / "saida", pasta / "hist", canal)
    assert r["id"] == 2700398 and r["primeira_coleta"] is True and r["novidades"] == []
    assert r["ultimos_eventos"][0] == {"data": "2026-09-10T10:00:00", "descricao": "Sentença", "documento": True}
    destino = pasta / "saida" / "trt2" / NUMERO
    for nome in ("capa.json", "timeline.json", "partes.json"):
        assert (destino / nome).exists()
    # expedientes deu erro de permissão: vira aviso, não derruba a coleta
    assert any(a.startswith("expedientes:") for a in r["avisos"])


def test_segunda_coleta_aponta_novidade_e_baixa_documento(ambiente):
    falso, cliente, canal, pasta = ambiente
    coletar(cliente, [NUMERO], pasta / "saida1", pasta / "hist", canal)
    falso.timeline.insert(0, {"id": 3, "data": "2026-09-20T15:00:00", "titulo": "Embargos de declaração",
                              "documento": True})
    [r] = coletar(cliente, [NUMERO], pasta / "saida2", pasta / "hist", canal, baixar_documentos_novos=True)
    assert r["primeira_coleta"] is False
    assert [n["descricao"] for n in r["novidades"]] == ["Embargos de declaração"]
    [arquivo] = r["documentos_baixados"]
    assert arquivo.endswith("3.pdf")
    assert open(arquivo, "rb").read().startswith(b"%PDF")


def test_sem_autenticacao_vira_erro_do_processo(ambiente):
    falso, _, canal, pasta = ambiente
    cliente = ClientePJe(falso, tribunal("trt2"), {}, pausa=0)
    [r] = coletar(cliente, [NUMERO], pasta / "saida", pasta / "hist", canal)
    assert "HTTP 400" in r["erro"] and "SJT-004" in r["erro"]


def test_captcha_e_reconhecido():
    class Captcha:
        def get(self, url, headers=None, timeout=None):
            return RespostaFalsa(200, '{"tokenDesafio":"x","imagem":"..."}')

    cliente = ClientePJe(Captcha(), tribunal("trt2"), {}, pausa=0)
    with pytest.raises(ErroAPI, match="captcha"):
        cliente.capa(1)


def test_parada_interrompe_coleta(ambiente):
    falso, cliente, canal, pasta = ambiente
    canal.pedir_parada()
    assert coletar(cliente, [NUMERO], pasta / "saida", pasta / "hist", canal) == []


def test_resposta_que_nao_e_json_vira_erro_legivel():
    class PaginaDeLogin:
        def get(self, url, headers=None, timeout=None):
            return RespostaFalsa(200, "<html>login</html>", "text/html")

    cliente = ClientePJe(PaginaDeLogin(), tribunal("trt2"), {}, pausa=0)
    with pytest.raises(ErroAPI, match="não é JSON"):
        cliente.capa(1)


def test_eventos_em_ordem_antiga_sao_reordenados(ambiente):
    falso, cliente, canal, pasta = ambiente
    falso.timeline.reverse()  # tribunal devolvendo do mais antigo para o mais novo
    [r] = coletar(cliente, [NUMERO], pasta / "saida", pasta / "hist", canal)
    assert r["ultimos_eventos"][0]["descricao"] == "Sentença"
