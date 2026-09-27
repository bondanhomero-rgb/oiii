"""Coleta por processo: capa, partes, movimentações/documentos (timeline), expedientes e novidades."""

import hashlib
import json
from pathlib import Path

from .api import ClientePJe, ErroAPI
from .canal import Canal

CHAVES_DATA = ("data", "dataJuntada", "dataHora", "dataInclusao", "dataAtualizacao")
CHAVES_TITULO = ("titulo", "descricao", "tipo", "nome", "movimento")
EXTENSOES = {"application/pdf": ".pdf", "text/html": ".html", "text/plain": ".txt"}


def salvar_json(caminho: Path, dados) -> None:
    caminho.parent.mkdir(parents=True, exist_ok=True)
    caminho.write_text(json.dumps(dados, ensure_ascii=False, indent=2), encoding="utf-8")


def _primeiro(evento: dict, chaves) -> str | None:
    for chave in chaves:
        valor = evento.get(chave)
        if valor not in (None, ""):
            return str(valor)
    return None


def resumir_evento(evento) -> dict:
    if not isinstance(evento, dict):
        return {"descricao": str(evento)[:200]}
    return {
        "data": _primeiro(evento, CHAVES_DATA),
        "descricao": _primeiro(evento, CHAVES_TITULO),
        "documento": eh_documento(evento),
    }


def eh_documento(evento) -> bool:
    return isinstance(evento, dict) and bool(evento.get("documento") or evento.get("idUnicoDocumento"))


def mais_recentes_primeiro(eventos: list) -> list:
    """Ordena por data (texto ISO) decrescente; sem data reconhecível, mantém a ordem do tribunal."""
    datas = [_primeiro(e, CHAVES_DATA) if isinstance(e, dict) else None for e in eventos]
    if not all(datas):
        return list(eventos)
    return [e for _, e in sorted(zip(datas, eventos), key=lambda par: par[0], reverse=True)]


def _impressao(evento) -> str:
    return hashlib.sha1(json.dumps(evento, sort_keys=True, ensure_ascii=False).encode()).hexdigest()


def separar_novidades(arquivo_historico: Path, eventos: list) -> tuple[list, bool]:
    """Compara com a coleta anterior. Na primeira coleta só grava a base (nenhuma novidade)."""
    anteriores = None
    if arquivo_historico.exists():
        anteriores = set(json.loads(arquivo_historico.read_text(encoding="utf-8")))
    atuais = [_impressao(e) for e in eventos]
    salvar_json(arquivo_historico, atuais)
    if anteriores is None:
        return [], True
    return [e for e, h in zip(eventos, atuais) if h not in anteriores], False


def coletar_processo(cliente: ClientePJe, numero: str, pasta: Path, pasta_historico: Path,
                     baixar_documentos_novos: bool = False) -> dict:
    sigla = cliente.trib.sigla
    item: dict = {"numero": numero, "tribunal": sigla, "grau": cliente.trib.grau, "avisos": []}
    try:
        id_processo = cliente.id_do_processo(numero)
        item["id"] = id_processo
        capa = cliente.capa(id_processo)
        salvar_json(pasta / "capa.json", capa)
        timeline = cliente.timeline(id_processo)
        salvar_json(pasta / "timeline.json", timeline)
    except ErroAPI as e:
        item["erro"] = str(e)
        return item

    for nome, funcao in (("partes", cliente.partes), ("expedientes", cliente.expedientes)):
        try:
            salvar_json(pasta / f"{nome}.json", funcao(id_processo))
        except ErroAPI as e:
            item["avisos"].append(f"{nome}: {e}")

    eventos = mais_recentes_primeiro(timeline if isinstance(timeline, list) else [])
    novos, primeira = separar_novidades(pasta_historico / sigla / f"{numero}.json", eventos)
    item.update(
        total_eventos=len(eventos),
        primeira_coleta=primeira,
        novidades=[resumir_evento(e) for e in novos],
        ultimos_eventos=[resumir_evento(e) for e in eventos[:5]],
    )

    if baixar_documentos_novos:
        item["documentos_baixados"] = []
        for evento in novos:
            if not eh_documento(evento) or evento.get("id") is None:
                continue
            try:
                conteudo, tipo = cliente.documento(id_processo, evento["id"])
            except ErroAPI as e:
                item["avisos"].append(f"documento {evento['id']}: {e}")
                continue
            extensao = EXTENSOES.get(tipo.split(";")[0].strip(), ".bin")
            destino = pasta / "documentos" / f"{evento['id']}{extensao}"
            destino.parent.mkdir(parents=True, exist_ok=True)
            destino.write_bytes(conteudo)
            item["documentos_baixados"].append(str(destino))
    return item


def coletar(cliente: ClientePJe, numeros: list[str], pasta_saida: Path, pasta_historico: Path,
            canal: Canal, baixar_documentos_novos: bool = False) -> list[dict]:
    resultados = []
    for i, numero in enumerate(numeros, 1):
        if canal.parada_pedida():
            canal.log("Parada pedida; coleta interrompida.")
            break
        canal.status("coletando", f"{cliente.trib.sigla.upper()} {i}/{len(numeros)}: {numero}",
                     atual=i, total=len(numeros))
        pasta = pasta_saida / cliente.trib.sigla / numero
        resultados.append(coletar_processo(cliente, numero, pasta, pasta_historico, baixar_documentos_novos))
    return resultados
