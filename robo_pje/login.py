"""Login no PJe pela PDPJ (SSO): certificado no token via PJeOffice + código 2FA vindo do Claude.

Fluxo real observado no TRT (set/2026):
  1. {tribunal}/primeirograu/login.seam -> botão "Entrar com PDPJ" (#btnSsoPdpj)
  2. sso.cloud.pje.jus.br -> link "Seu certificado digital" (onclick="autenticar(...)").
     O site chama o PJeOffice em http://localhost:8800; o PJeOffice pede o PIN do token,
     assina o desafio e o formulário #kc-form-login é enviado sozinho.
  3. Tela do código do autenticador (2FA) -> o robô pede o código ao Claude pelo canal.
  4. Volta para o tribunal já logado.
"""

import time
import urllib.error
import urllib.request
from urllib.parse import urlparse

from .canal import Canal
from .config import Tribunal

SEL_BOTAO_PDPJ = "#btnSsoPdpj"
SEL_LINK_CERTIFICADO = "a[onclick^='autenticar(']"
# A tela do 2FA não pôde ser inspecionada sem login; seletores cobrem o padrão do Keycloak.
SEL_OTP = "input#otp, input[name='otp'], input[name='totp'], input[autocomplete='one-time-code']"
SEL_CONFIGURAR_OTP = "#kc-totp-secret-qr-code, #kc-totp-settings, input#userLabel"
SEL_ERRO = "#input-error, .alert-error, .alert-danger, .kc-feedback-text, .pf-c-alert__title"

URL_PJEOFFICE = "http://localhost:8800/pjeOffice/"


class ErroLogin(Exception):
    pass


def pjeoffice_disponivel(url: str = URL_PJEOFFICE, timeout: float = 3) -> bool:
    # Sem proxy: no Windows o urllib herdaria o proxy do sistema até para localhost.
    abridor = urllib.request.build_opener(urllib.request.ProxyHandler({}))
    try:
        abridor.open(url, timeout=timeout).close()
        return True
    except urllib.error.HTTPError:
        return True  # respondeu, então está rodando
    except (urllib.error.URLError, OSError):
        return False


def esta_logado(page, trib: Tribunal) -> bool:
    url = urlparse(page.url)
    if url.netloc != trib.host:
        return False
    return not any(p in url.path for p in ("login.seam", "authenticateSSO", "logarSC"))


def _visivel(page, seletor: str) -> bool:
    try:
        return page.locator(seletor).first.is_visible()
    except Exception:
        return False  # página no meio de uma navegação


def _texto_visivel(page, seletor: str) -> str:
    try:
        loc = page.locator(seletor).first
        return loc.inner_text(timeout=1000).strip() if loc.is_visible() else ""
    except Exception:
        return ""


def _proximo_estado(page, trib: Tribunal, canal: Canal, alertas: list, timeout: float,
                    aceitar_formulario: bool = False) -> str:
    limite = time.monotonic() + timeout
    while time.monotonic() < limite:
        if canal.parada_pedida():
            raise ErroLogin("Parada pedida.")
        if alertas:
            return "alerta"
        if _visivel(page, SEL_CONFIGURAR_OTP):
            return "configurar_otp"
        if _visivel(page, SEL_OTP):
            return "otp"
        if esta_logado(page, trib):
            return "logado"
        if aceitar_formulario and _visivel(page, SEL_LINK_CERTIFICADO):
            return "formulario"
        if not aceitar_formulario and _texto_visivel(page, SEL_ERRO):
            return "erro"
        page.wait_for_timeout(500)
    return "timeout"


def fazer_login(page, trib: Tribunal, canal: Canal, timeout_pin: float = 180,
                timeout_otp: float = 300, max_tentativas_2fa: int = 3,
                checar_pjeoffice: bool = True) -> None:
    from playwright.sync_api import TimeoutError as PlaywrightTimeout

    alertas: list[str] = []

    def ao_abrir_dialogo(dialogo):
        alertas.append(dialogo.message)
        dialogo.accept()

    page.on("dialog", ao_abrir_dialogo)
    try:
        canal.status("abrindo_login", f"Abrindo {trib.url_login}")
        page.goto(trib.url_login, wait_until="domcontentloaded")
        if esta_logado(page, trib):
            canal.status("logado", f"{trib.sigla.upper()}: sessão ainda ativa, sem PIN nem 2FA.")
            return

        if _visivel(page, SEL_BOTAO_PDPJ):
            page.click(SEL_BOTAO_PDPJ)
        estado = _proximo_estado(page, trib, canal, alertas, 60, aceitar_formulario=True)

        if estado == "formulario":
            if checar_pjeoffice and not pjeoffice_disponivel():
                raise ErroLogin("O PJeOffice não está aberto neste computador. Abra o PJeOffice "
                                "(com o token espetado) e rode de novo.")
            canal.status("aguardando_pin",
                         "Digite o PIN do token na janela do PJeOffice, no computador.")
            page.click(SEL_LINK_CERTIFICADO)
            estado = _proximo_estado(page, trib, canal, alertas, timeout_pin)

        tentativa = 0
        erro_anterior = ""
        while estado == "otp":
            tentativa += 1
            if tentativa > max_tentativas_2fa:
                raise ErroLogin(f"Código 2FA recusado {max_tentativas_2fa} vezes. Última mensagem: {erro_anterior}")
            canal.descartar_otp()  # nunca usa um código que chegou antes da pergunta
            if tentativa == 1:
                canal.status("aguardando_2fa", "Mande o código de 6 dígitos do Google Authenticator.")
            else:
                canal.status("2fa_recusado", f"O tribunal recusou o código ({erro_anterior}). Mande um código novo.",
                             tentativa=tentativa)
            codigo = canal.esperar_otp(timeout_otp)
            if not codigo:
                raise ErroLogin("Parada pedida." if canal.parada_pedida()
                                else "Tempo esgotado esperando o código do autenticador.")
            canal.log("Código 2FA recebido; enviando ao tribunal.")
            campo = page.locator(SEL_OTP).first
            campo.fill(codigo)
            try:
                # Espera a página sair da tela do código antes de reavaliar (senão lê a tela antiga).
                with page.expect_navigation(wait_until="domcontentloaded", timeout=60_000):
                    campo.press("Enter")
            except PlaywrightTimeout:
                canal.log("A tela do código não navegou em 60 s; reavaliando a página.")
            estado = _proximo_estado(page, trib, canal, alertas, 60)
            if estado == "otp":
                erro_anterior = _texto_visivel(page, SEL_ERRO) or "código inválido ou expirado"

        if estado == "logado":
            canal.status("logado", f"{trib.sigla.upper()}: login feito.")
            return
        if estado == "alerta":
            raise ErroLogin(f"Aviso do site durante o login: {alertas[-1]} "
                            "(confira se o PJeOffice está aberto e o token espetado).")
        if estado == "configurar_otp":
            raise ErroLogin("O tribunal está pedindo para CONFIGURAR o autenticador (QR code). "
                            "Faça essa configuração uma vez manualmente no navegador e rode de novo.")
        if estado == "erro":
            raise ErroLogin(f"O login pela PDPJ retornou erro: {_texto_visivel(page, SEL_ERRO)}")
        raise ErroLogin(f"Tempo esgotado no login (última página: {page.url.split('?')[0]}). "
                        "Se o PJeOffice pediu o PIN, confira se foi digitado.")
    finally:
        page.remove_listener("dialog", ao_abrir_dialogo)


def preparar_api(page, trib: Tribunal, captura, canal: Canal, timeout: float = 30) -> dict[str, str]:
    """Abre o painel do PJe para o próprio site chamar a API, e pega a autenticação dessas chamadas."""
    if not captura.de(trib.host):
        page.goto(trib.url_painel, wait_until="domcontentloaded")
        limite = time.monotonic() + timeout
        while not captura.de(trib.host) and time.monotonic() < limite:
            page.wait_for_timeout(500)
    cabecalhos = captura.de(trib.host)
    if not cabecalhos:
        canal.log("Aviso: o site não mandou cabeçalho de autenticação; seguindo só com os cookies da sessão.")
    return cabecalhos
