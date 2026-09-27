import threading
import time

import pytest

from robo_pje.canal import Canal, CodigoInvalido


def test_status_sobe_seq_e_vai_para_o_log(tmp_path):
    canal = Canal(tmp_path)
    assert canal.ler_status()["etapa"] == "sem_execucao"
    a = canal.status("iniciando", "ok")
    b = canal.status("aguardando_2fa", "mande o código")
    assert b["seq"] == a["seq"] + 1
    assert canal.ler_status()["etapa"] == "aguardando_2fa"
    assert any("aguardando_2fa" in linha for linha in canal.ultimas_linhas_log())


def test_codigo_e_validado_e_normalizado(tmp_path):
    canal = Canal(tmp_path)
    for ruim in ("12345", "abcdef", "1234567", ""):
        with pytest.raises(CodigoInvalido):
            canal.enviar_otp(ruim)
    canal.enviar_otp(" 123 456 ")
    assert canal.esperar_otp(timeout=1) == "123456"
    assert not canal.arq_otp.exists(), "o código deve ser apagado assim que lido"


def test_codigo_entregue_por_outro_processo_chega_ao_robo(tmp_path):
    robo = Canal(tmp_path)
    claude = Canal(tmp_path)
    threading.Timer(0.3, claude.enviar_otp, args=("654321",)).start()
    assert robo.esperar_otp(timeout=5) == "654321"


def test_codigo_nao_aparece_no_log(tmp_path):
    canal = Canal(tmp_path)
    canal.enviar_otp("987654")
    canal.esperar_otp(timeout=1)
    canal.status("logado", "ok")
    assert "987654" not in canal.arq_log.read_text(encoding="utf-8")


def test_espera_do_codigo_expira(tmp_path):
    inicio = time.monotonic()
    assert Canal(tmp_path).esperar_otp(timeout=0.5) is None
    assert time.monotonic() - inicio < 2


def test_parada_interrompe_espera_do_codigo(tmp_path):
    canal = Canal(tmp_path)
    threading.Timer(0.2, canal.pedir_parada).start()
    assert canal.esperar_otp(timeout=5) is None
    canal.reiniciar()
    assert not canal.parada_pedida()


def test_aguardar_ignora_etapas_intermediarias(tmp_path):
    canal = Canal(tmp_path)
    base = canal.status("iniciando")["seq"]

    def robo():
        time.sleep(0.2)
        canal.status("abrindo_login")
        time.sleep(0.2)
        canal.status("aguardando_pin")

    threading.Thread(target=robo).start()
    resultado = canal.aguardar(base, timeout=5)
    assert resultado["etapa"] == "aguardando_pin"
    assert "timeout" not in resultado


def test_aguardar_devolve_status_no_timeout(tmp_path):
    canal = Canal(tmp_path)
    seq = canal.status("coletando", "1/3", atual=1, total=3)["seq"]
    resultado = canal.aguardar(seq, timeout=0.3)
    assert resultado["timeout"] is True
    assert resultado["etapa"] == "coletando"


def test_em_andamento_recente(tmp_path):
    canal = Canal(tmp_path)
    assert not canal.em_andamento_recente()
    canal.status("coletando")
    assert canal.em_andamento_recente()
    canal.status("concluido")
    assert not canal.em_andamento_recente()
