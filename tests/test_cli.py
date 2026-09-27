import json
import threading

import pytest

from robo_pje.canal import Canal
from robo_pje.cli import agrupar_por_tribunal, main
from robo_pje.cnj import calcular_dv
from robo_pje.config import tribunal

TRT2 = "0000074-94.2010.5.02.0043"
TRT15 = f"0010001-{calcular_dv('0010001', '2025', '5', '15', '0001')}.2025.5.15.0001"
TJSP = f"1234567-{calcular_dv('1234567', '2024', '8', '26', '0100')}.2024.8.26.0100"


def test_agrupa_por_trt_e_recusa_o_resto():
    grupos, recusados = agrupar_por_tribunal([TRT2, TRT15, TJSP, "123", TRT2], None)
    assert grupos == {"trt2": [TRT2], "trt15": [TRT15]}
    motivos = {r["numero"]: r["motivo"] for r in recusados}
    assert "só TRT" in motivos[TJSP] and "20 dígitos" in motivos["123"]


def test_config_dos_trts():
    t = tribunal("TRT15", grau=2)
    assert t.base_url == "https://pje.trt15.jus.br"
    assert t.url_login == "https://pje.trt15.jus.br/segundograu/login.seam"
    with pytest.raises(ValueError):
        tribunal("trt25")
    with pytest.raises(ValueError):
        tribunal("tjsp")


def test_comando_otp_entrega_codigo(tmp_path, capsys):
    assert main(["--pasta", str(tmp_path), "otp", "123456"]) == 0
    assert Canal(tmp_path / "estado").esperar_otp(timeout=1) == "123456"
    assert main(["--pasta", str(tmp_path), "otp", "12a456"]) == 2
    assert "6 dígitos" in capsys.readouterr().err


def test_comando_aguardar_mostra_log_no_erro(tmp_path, capsys):
    canal = Canal(tmp_path / "estado")
    seq = canal.status("iniciando")["seq"]
    threading.Timer(0.2, canal.status, args=("erro", "PJeOffice fechado")).start()
    assert main(["--pasta", str(tmp_path), "aguardar", "--apos-seq", str(seq), "--timeout", "5"]) == 0
    saida = json.loads(capsys.readouterr().out)
    assert saida["etapa"] == "erro" and saida["mensagem"] == "PJeOffice fechado"
    assert any("PJeOffice fechado" in linha for linha in saida["log"])


def test_executar_recusa_segundo_robo(tmp_path, capsys):
    Canal(tmp_path / "estado").status("coletando", "1/5")
    assert main(["--pasta", str(tmp_path), "executar", "--processo", TRT2]) == 3
    assert "Já existe um robô" in capsys.readouterr().err


def test_executar_sem_nada_explica(tmp_path, capsys):
    assert main(["--pasta", str(tmp_path), "executar"]) == 2
    assert "Informe processos" in capsys.readouterr().err


def test_le_processos_txt(tmp_path):
    from argparse import Namespace

    from robo_pje.cli import ler_processos

    (tmp_path / "processos.txt").write_text(f"# comentário\n{TRT2}\n\n{TRT15}  # cliente X\n", encoding="utf-8")
    args = Namespace(pasta=str(tmp_path), processo=None, arquivo=None)
    assert ler_processos(args) == [TRT2, TRT15]
