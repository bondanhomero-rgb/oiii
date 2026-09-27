"""Linha de comando do robô. Rode sempre a partir da pasta do projeto: `python -m robo_pje <comando>`."""

import argparse
import json
import os
import sys
import time
import traceback
from datetime import datetime
from pathlib import Path

from .canal import Canal, CodigoInvalido
from .cnj import NumeroInvalido, normalizar, tribunal_do_numero


def _pasta_base(args) -> Path:
    return Path(args.pasta or os.environ.get("PJE_ROBO_DIR") or Path.cwd())


def _canal(args) -> Canal:
    return Canal(_pasta_base(args) / "estado")


def _imprimir(dados) -> None:
    print(json.dumps(dados, ensure_ascii=False, indent=2))


def ler_processos(args) -> list[str]:
    brutos = list(args.processo or [])
    arquivo = Path(args.arquivo) if args.arquivo else None
    if arquivo is None and not brutos and (_pasta_base(args) / "processos.txt").exists():
        arquivo = _pasta_base(args) / "processos.txt"
    if arquivo:
        for linha in arquivo.read_text(encoding="utf-8").splitlines():
            linha = linha.split("#")[0].strip()
            if linha:
                brutos.append(linha)
    return brutos


def agrupar_por_tribunal(numeros: list[str], tribunal_fixo: str | None) -> tuple[dict, list]:
    grupos: dict[str, list[str]] = {}
    recusados = []
    for bruto in numeros:
        try:
            numero = normalizar(bruto)
        except NumeroInvalido as e:
            recusados.append({"numero": bruto, "motivo": str(e)})
            continue
        sigla = tribunal_fixo or tribunal_do_numero(numero)
        if not sigla:
            recusados.append({"numero": numero, "motivo": "ainda não suportado (só TRT por enquanto)"})
            continue
        if numero not in grupos.setdefault(sigla.lower(), []):
            grupos[sigla.lower()].append(numero)
    return grupos, recusados


# ---------------- comandos rápidos (usados pelo Claude) ----------------

def cmd_status(args) -> int:
    canal = _canal(args)
    _imprimir({**canal.ler_status(), "log": canal.ultimas_linhas_log(args.linhas)})
    return 0


def cmd_aguardar(args) -> int:
    canal = _canal(args)
    dados = canal.aguardar(args.apos_seq, args.timeout)
    if dados.get("etapa") == "erro":
        dados["log"] = canal.ultimas_linhas_log(15)
    _imprimir(dados)
    return 0


def cmd_otp(args) -> int:
    try:
        _canal(args).enviar_otp(args.codigo)
    except CodigoInvalido as e:
        print(f"ERRO: {e}", file=sys.stderr)
        return 2
    print("Código entregue ao robô.")
    return 0


def cmd_parar(args) -> int:
    _canal(args).pedir_parada()
    print("Pedido de parada registrado; o robô encerra no próximo passo.")
    return 0


def cmd_verificar(args) -> int:
    from .login import pjeoffice_disponivel

    relatorio = {"python": sys.version.split()[0], "python_ok": sys.version_info >= (3, 10)}
    try:
        import playwright  # noqa: F401

        relatorio["playwright"] = "instalado"
    except ImportError:
        relatorio["playwright"] = "FALTANDO: rode  pip install -r requirements.txt"
    relatorio["pjeoffice_aberto"] = pjeoffice_disponivel()
    if not relatorio["pjeoffice_aberto"]:
        relatorio["dica_pjeoffice"] = "Abra o PJeOffice (ou PJeOffice Pro) e espete o token antes de rodar."
    relatorio["pasta"] = str(_pasta_base(args))
    _imprimir(relatorio)
    return 0 if relatorio["python_ok"] and relatorio["playwright"] == "instalado" else 1


# ---------------- comandos com navegador ----------------

def _com_navegador(args, canal: Canal, trabalho) -> int:
    from playwright.sync_api import sync_playwright

    from .login import ErroLogin
    from .navegador import CapturaAuth, abrir_contexto

    base = _pasta_base(args)
    contexto = None
    try:
        with sync_playwright() as p:
            contexto = abrir_contexto(p, base / "perfil", args.navegador, getattr(args, "oculto", False))
            captura = CapturaAuth()
            contexto.on("request", captura)
            page = contexto.pages[0] if contexto.pages else contexto.new_page()
            try:
                return trabalho(contexto, page, captura)
            except ErroLogin as e:
                _registrar_erro(page, canal, str(e))
                return 2
            except Exception as e:  # noqa: BLE001 - qualquer falha vira status de erro legível
                canal.log(traceback.format_exc())
                _registrar_erro(page, canal, f"Falha inesperada: {e}")
                return 1
            finally:
                try:
                    contexto.close()
                except Exception:
                    pass
    except Exception as e:  # falha ao abrir o navegador
        canal.log(traceback.format_exc())
        canal.status("erro", f"Não consegui abrir o navegador ({args.navegador}): {e}")
        return 1


def _registrar_erro(page, canal: Canal, mensagem: str) -> None:
    extra = {}
    try:
        destino = canal.pasta / "erro.png"
        page.screenshot(path=str(destino), full_page=True)
        extra["captura_de_tela"] = str(destino)
    except Exception:
        pass
    canal.status("erro", mensagem, **extra)


def cmd_executar(args) -> int:
    from .api import ClientePJe
    from .coleta import coletar, salvar_json
    from .config import tribunal
    from .login import fazer_login, preparar_api

    canal = _canal(args)
    if canal.em_andamento_recente() and not args.forcar:
        print("Já existe um robô rodando (veja `python -m robo_pje status`). Use --forcar se ele travou.",
              file=sys.stderr)
        return 3
    canal.reiniciar()

    if args.base_url and not args.tribunal:
        print("Com --base-url informe também --tribunal (um nome qualquer).", file=sys.stderr)
        return 2
    grupos, recusados = agrupar_por_tribunal(ler_processos(args), args.tribunal)
    so_login = not grupos
    if so_login:
        if not args.tribunal:
            print("Informe processos (--processo / --arquivo / processos.txt) ou ao menos --tribunal.",
                  file=sys.stderr)
            return 2
        grupos = {args.tribunal.lower(): []}

    base = _pasta_base(args)
    carimbo = datetime.now().strftime("%Y-%m-%d_%H%M%S")
    pasta_saida = base / "saida" / carimbo
    canal.status("iniciando", f"{sum(len(v) for v in grupos.values())} processo(s) em "
                              f"{', '.join(s.upper() for s in grupos)}", recusados=recusados)

    def trabalho(contexto, page, captura):
        resultados = []
        for sigla, numeros in grupos.items():
            trib = tribunal(sigla, args.grau, args.base_url)
            fazer_login(page, trib, canal, timeout_pin=args.timeout_pin, timeout_otp=args.timeout_2fa)
            if not numeros:
                continue
            cabecalhos = preparar_api(page, trib, captura, canal)
            cliente = ClientePJe(contexto.request, trib, cabecalhos, pausa=args.pausa)
            resultados += coletar(cliente, numeros, pasta_saida, base / "estado" / "historico", canal,
                                  baixar_documentos_novos=args.documentos_novos)
            if canal.parada_pedida():
                break

        if so_login:
            canal.status("concluido", "Login feito; nenhum processo pedido.")
            return 0
        resumo = {
            "gerado_em": datetime.now().isoformat(timespec="seconds"),
            "pasta": str(pasta_saida),
            "processos": resultados,
            "recusados": recusados,
        }
        salvar_json(pasta_saida / "resumo.json", resumo)
        com_novidade = sum(1 for r in resultados if r.get("novidades"))
        com_erro = sum(1 for r in resultados if r.get("erro"))
        etapa = "parado" if canal.parada_pedida() else "concluido"
        canal.status(etapa, f"{len(resultados)} processo(s) coletado(s); {com_novidade} com novidade; "
                            f"{com_erro} com erro.", resumo=str(pasta_saida / "resumo.json"))
        return 0

    return _com_navegador(args, canal, trabalho)


def cmd_mapear(args) -> int:
    from .config import tribunal
    from .login import fazer_login
    from .navegador import RegistroChamadas

    canal = _canal(args)
    canal.reiniciar()
    args.oculto = False  # o usuário precisa ver e navegar
    trib = tribunal(args.tribunal, args.grau, args.base_url)
    arquivo = _pasta_base(args) / "saida" / f"mapa_api_{trib.sigla}.jsonl"
    arquivo.parent.mkdir(parents=True, exist_ok=True)

    def trabalho(contexto, page, captura):
        fazer_login(page, trib, canal, timeout_pin=args.timeout_pin, timeout_otp=args.timeout_2fa)
        contexto.on("response", RegistroChamadas(arquivo))
        page.goto(trib.url_painel, wait_until="domcontentloaded")
        canal.status("mapeando", "Navegue no PJe (abra processos, expedientes, documentos). "
                                 "Feche o navegador quando terminar.", arquivo=str(arquivo))
        limite = time.monotonic() + args.timeout
        while time.monotonic() < limite and not canal.parada_pedida():
            abertas = [pg for pg in contexto.pages if not pg.is_closed()]
            if not abertas:
                break
            try:
                abertas[0].wait_for_timeout(1000)
            except Exception:
                break  # navegador fechado pelo usuário
        canal.status("concluido", "Mapeamento encerrado.", arquivo=str(arquivo))
        return 0

    return _com_navegador(args, canal, trabalho)


# ---------------- argumentos ----------------

def _parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(prog="python -m robo_pje", description=__doc__)
    p.add_argument("--pasta", help="pasta de trabalho (padrão: atual ou PJE_ROBO_DIR)")
    sub = p.add_subparsers(dest="comando", required=True)

    def opcoes_navegador(sp):
        sp.add_argument("--grau", type=int, default=1, choices=[1, 2])
        sp.add_argument("--base-url", help="endereço de outro PJe (avançado)")
        sp.add_argument("--navegador", default="msedge", choices=["msedge", "chrome", "chromium"])
        sp.add_argument("--timeout-pin", type=float, default=180, help="segundos para digitar o PIN")
        sp.add_argument("--timeout-2fa", type=float, default=300, help="segundos para chegar o código 2FA")

    ex = sub.add_parser("executar", help="login + coleta dos processos")
    ex.add_argument("--processo", action="append", help="número CNJ (pode repetir)")
    ex.add_argument("--arquivo", help="arquivo com um número por linha (padrão: processos.txt)")
    ex.add_argument("--tribunal", help="ex.: trt2 (se omitido, sai do número do processo)")
    ex.add_argument("--oculto", action="store_true", help="navegador sem janela")
    ex.add_argument("--documentos-novos", action="store_true", help="baixa documentos das novidades")
    ex.add_argument("--pausa", type=float, default=1.0, help="segundos entre chamadas ao tribunal")
    ex.add_argument("--forcar", action="store_true", help="ignora robô anterior aparentemente ativo")
    opcoes_navegador(ex)
    ex.set_defaults(func=cmd_executar)

    mp = sub.add_parser("mapear", help="login e registro das rotas da API enquanto você navega")
    mp.add_argument("--tribunal", required=True)
    mp.add_argument("--timeout", type=float, default=900)
    opcoes_navegador(mp)
    mp.set_defaults(func=cmd_mapear)

    ot = sub.add_parser("otp", help="entrega o código do Google Authenticator ao robô")
    ot.add_argument("codigo")
    ot.set_defaults(func=cmd_otp)

    ag = sub.add_parser("aguardar", help="espera a próxima etapa que exige ação")
    ag.add_argument("--apos-seq", type=int, default=0)
    ag.add_argument("--timeout", type=float, default=100)
    ag.set_defaults(func=cmd_aguardar)

    st = sub.add_parser("status", help="mostra a etapa atual e o fim do log")
    st.add_argument("--linhas", type=int, default=10)
    st.set_defaults(func=cmd_status)

    sub.add_parser("parar", help="pede para o robô encerrar").set_defaults(func=cmd_parar)
    sub.add_parser("verificar", help="confere Python, Playwright e PJeOffice").set_defaults(func=cmd_verificar)
    return p


def main(argv: list[str] | None = None) -> int:
    for fluxo in (sys.stdout, sys.stderr):
        try:
            fluxo.reconfigure(encoding="utf-8")
        except (AttributeError, ValueError):
            pass
    args = _parser().parse_args(argv)
    return args.func(args)
