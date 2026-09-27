"""Canal entre o robô (processo em segundo plano) e o Claude, por arquivos na pasta de estado.

- status.json: etapa atual do robô, com um contador `seq` que sobe a cada mudança.
- otp.txt: código 2FA entregue pelo Claude (`python -m robo_pje otp 123456`);
  o robô lê e apaga na hora. O código nunca vai para o log.
- parar: pedido de parada (`python -m robo_pje parar`).
- robo.log: log legível do que o robô fez.
"""

import json
import os
import re
import time
from datetime import datetime
from pathlib import Path

# Etapas em que o Claude precisa agir ou avisar o usuário.
ETAPAS_ACIONAVEIS = {
    "aguardando_pin", "aguardando_2fa", "2fa_recusado", "logado", "mapeando",
    "concluido", "erro", "parado",
}
ETAPAS_FINAIS = {"concluido", "erro", "parado"}


class CodigoInvalido(ValueError):
    pass


def _agora() -> str:
    return datetime.now().isoformat(timespec="seconds")


def _com_retentativa(funcao, tentativas: int = 20):
    # No Windows, ler/substituir um arquivo aberto por outro processo dá PermissionError por instantes.
    for i in range(tentativas):
        try:
            return funcao()
        except PermissionError:
            if i == tentativas - 1:
                raise
            time.sleep(0.05)


class Canal:
    def __init__(self, pasta: Path | str, eco: bool = False):
        self.pasta = Path(pasta)
        self.eco = eco  # também mostra cada etapa na tela (uso manual no Prompt de Comando)
        self.pasta.mkdir(parents=True, exist_ok=True)
        self.arq_status = self.pasta / "status.json"
        self.arq_otp = self.pasta / "otp.txt"
        self.arq_parar = self.pasta / "parar"
        self.arq_log = self.pasta / "robo.log"

    # ---------- status ----------

    def ler_status(self) -> dict:
        try:
            texto = _com_retentativa(lambda: self.arq_status.read_text(encoding="utf-8"))
            return json.loads(texto)
        except (FileNotFoundError, json.JSONDecodeError):
            return {"seq": 0, "etapa": "sem_execucao", "mensagem": "O robô ainda não rodou."}

    def status(self, etapa: str, mensagem: str = "", **extra) -> dict:
        dados = {
            "seq": int(self.ler_status().get("seq", 0)) + 1,
            "etapa": etapa,
            "mensagem": mensagem,
            "atualizado_em": _agora(),
            "pid": os.getpid(),
            **extra,
        }
        self._gravar_atomico(self.arq_status, json.dumps(dados, ensure_ascii=False, indent=2))
        self.log(f"[{etapa}] {mensagem}")
        if self.eco:
            print(f"[{etapa}] {mensagem}", flush=True)
            if etapa in ("aguardando_2fa", "2fa_recusado"):
                print("    -> em outra janela, na pasta oiii:  python -m robo_pje otp SEU_CODIGO", flush=True)
        return dados

    def aguardar(self, apos_seq: int, timeout: float, intervalo: float = 0.5) -> dict:
        """Espera uma etapa acionável com seq > apos_seq. No timeout devolve o status atual."""
        limite = time.monotonic() + timeout
        while True:
            atual = self.ler_status()
            if atual.get("seq", 0) > apos_seq and atual.get("etapa") in ETAPAS_ACIONAVEIS:
                return atual
            if time.monotonic() >= limite:
                return {**atual, "timeout": True}
            time.sleep(intervalo)

    def em_andamento_recente(self, minutos: float = 15) -> bool:
        atual = self.ler_status()
        if atual.get("etapa") in ETAPAS_FINAIS | {"sem_execucao"}:
            return False
        try:
            quando = datetime.fromisoformat(atual["atualizado_em"])
        except (KeyError, ValueError):
            return False
        return (datetime.now() - quando).total_seconds() < minutos * 60

    # ---------- código 2FA ----------

    @staticmethod
    def validar_codigo(codigo: str) -> str:
        limpo = re.sub(r"\s", "", str(codigo))
        if not re.fullmatch(r"\d{6}", limpo):
            raise CodigoInvalido("O código do autenticador tem 6 dígitos (ex.: 123456).")
        return limpo

    def enviar_otp(self, codigo: str) -> None:
        self._gravar_atomico(self.arq_otp, self.validar_codigo(codigo), privado=True)

    def descartar_otp(self) -> None:
        self.arq_otp.unlink(missing_ok=True)

    def esperar_otp(self, timeout: float, intervalo: float = 0.3) -> str | None:
        limite = time.monotonic() + timeout
        while time.monotonic() < limite:
            if self.parada_pedida():
                return None
            if self.arq_otp.exists():
                try:
                    codigo = _com_retentativa(lambda: self.arq_otp.read_text(encoding="utf-8")).strip()
                finally:
                    self.descartar_otp()
                try:
                    return self.validar_codigo(codigo)
                except CodigoInvalido:
                    self.log("Código 2FA em formato inválido descartado.")
            time.sleep(intervalo)
        return None

    # ---------- parada ----------

    def pedir_parada(self) -> None:
        self.arq_parar.write_text(_agora(), encoding="utf-8")

    def parada_pedida(self) -> bool:
        return self.arq_parar.exists()

    def reiniciar(self) -> None:
        """Limpa sobras de uma execução anterior (pedido de parada, código antigo)."""
        self.arq_parar.unlink(missing_ok=True)
        self.descartar_otp()

    # ---------- log ----------

    def log(self, mensagem: str) -> None:
        with open(self.arq_log, "a", encoding="utf-8") as f:
            f.write(f"{_agora()} {mensagem}\n")

    def ultimas_linhas_log(self, n: int = 20) -> list[str]:
        try:
            return self.arq_log.read_text(encoding="utf-8").splitlines()[-n:]
        except FileNotFoundError:
            return []

    # ---------- util ----------

    def _gravar_atomico(self, destino: Path, conteudo: str, privado: bool = False) -> None:
        tmp = destino.with_name(f".{destino.name}.{os.getpid()}.tmp")
        tmp.write_text(conteudo, encoding="utf-8")
        if privado:
            try:
                os.chmod(tmp, 0o600)
            except OSError:
                pass
        _com_retentativa(lambda: os.replace(tmp, destino))
