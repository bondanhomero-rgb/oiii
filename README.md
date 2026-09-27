# Robô PJe (TRT) — token + código do autenticador pelo chat

O robô entra no PJe da Justiça do Trabalho (TRT1 a TRT24) com o **seu token** e puxa, de cada
processo, a capa, as partes, as movimentações/documentos (timeline) e os expedientes. Ele
também aponta **o que é novo desde a última coleta**. É gratuito: usa só o login do advogado,
sem nenhuma API paga.

Você ativa pelo Claude Code com a habilidade **`/robo-pje`**. O Claude conduz o robô e, quando o
tribunal pede o 2FA, te pede o código do Google Authenticator no chat.

```
/robo-pje ──► robô abre o PJe (Edge) ──► "Entrar com PDPJ" ──► "Seu certificado digital"
                                                                    │
            você digita o PIN na janela do PJeOffice (no PC) ◄──────┘
                                                                    │
            Claude: "me mande o código de 6 dígitos" ◄── tela do 2FA┘
            você manda "123456" ──► Claude entrega ao robô ──► logado
                                                                    │
            robô usa a API do PJe com a sua sessão ──► saida/<data>/resumo.json
```

- **PIN do token:** é digitado por você na janela do PJeOffice. Nunca passa pelo chat.
- **Código do autenticador:** você manda no chat. O robô lê, apaga na hora e nunca grava no log.
- **Sessão:** o robô guarda a sessão num perfil próprio do navegador (`perfil/`). Enquanto a sessão
  da PDPJ estiver ativa, as próximas execuções nem pedem PIN/2FA. Um login vale para todos os
  TRTs, porque o SSO é o mesmo.

## Instalação (no seu PC com Windows, uma vez)

1. Instale o Python 3.10+ (python.org, marque "Add to PATH").
2. Na pasta deste repositório:
   ```
   pip install -r requirements.txt
   ```
   Usa o **Microsoft Edge** que já vem no Windows, sem baixar navegador extra. Para usar o Chrome, passe `--navegador chrome`.
3. Deixe o **PJeOffice** (ou PJeOffice Pro) aberto e o token espetado.
4. Confira:
   ```
   python -m robo_pje verificar
   ```

## Uso pelo Claude (recomendado)

Abra esta pasta no **Claude Code no seu PC** (app desktop, aba Code, ou `claude` no terminal) e digite:

```
/robo-pje puxar os processos do processos.txt
```

Ou liste os números no chat. A habilidade está em `.claude/skills/robo-pje/SKILL.md`.

> A habilidade precisa rodar **no PC onde estão o token e o PJeOffice**. Numa sessão do
> Claude na nuvem ela não funciona, porque o token físico não está lá.

## Uso manual (sem o Claude)

```
copy processos.exemplo.txt processos.txt        (edite com seus números)
python -m robo_pje executar                     (roda em uma janela)
python -m robo_pje otp 123456                   (em outra janela, quando pedir o 2FA)
python -m robo_pje status                       (acompanhar)
```

Outros comandos:

| comando | para quê |
|---|---|
| `executar --processo N --processo M` | Processos direto na linha de comando. |
| `executar --tribunal trt2` | Só faz o login (teste). |
| `executar --documentos-novos` | Também baixa os documentos que apareceram desde a última coleta. |
| `executar --grau 2` | 2º grau. |
| `mapear --tribunal trt2` | Faz o login, você navega no PJe, e ele anota as rotas da API que o site usa (`saida/mapa_api_trt2.jsonl`). Sem tokens e sem conteúdo. |
| `parar` | Pede para o robô encerrar. |

## Saída

```
saida/2026-09-27_101500/
  resumo.json                       ← por processo: novidades, últimos eventos, avisos, erros
  trt2/0000074-94.2010.5.02.0043/
    capa.json  partes.json  timeline.json  expedientes.json  documentos/
estado/                             ← status.json, robo.log, histórico para detectar novidades
```

Na **primeira** coleta de cada processo não há "novidades": ela vira a linha de base.

## O que foi verificado e o que falta confirmar

**Confirmado contra o site real do TRT2 (set/2026):**
- o botão `#btnSsoPdpj`;
- a tela da PDPJ com o link "Seu certificado digital";
- o formulário `#kc-form-login` e o uso do PJeOffice em `localhost:8800`;
- que as rotas usadas (capa, timeline, documentos, partes, expedientes) existem e exigem login;
- que a rota de dados básicos (número → id) é pública.

**Testado automaticamente (`python -m pytest`, 29 testes):**
- o canal Claude↔robô (entrega do código, expiração, parada, código fora do log);
- o número CNJ;
- o cliente da API e a detecção de novidades, com um tribunal falso.

**Só se confirma no primeiro uso real, no seu PC** (não dá para testar sem o seu token e o seu 2FA):
- a tela do código 2FA: os seletores seguem o padrão do Keycloak usado pela PDPJ;
- como o site autentica as chamadas da API depois do login. O robô copia isso das requisições do próprio site; se não bastar, rode `mapear`;
- o formato exato do JSON da timeline: o `resumo.json` lê os campos de forma tolerante, e os arquivos brutos são sempre salvos.

Se algo falhar, o robô grava `estado/erro.png` (captura da tela) e `estado/robo.log`, e o Claude mostra os dois.

## Segurança

- `estado/`, `saida/`, `perfil/` e `processos.txt` estão no `.gitignore`: têm dados de processos e da sessão.
- Os cabeçalhos de autenticação ficam só em memória, enquanto o robô roda.
- O robô **só lê**: não protocola, não assina documento, não ciencia intimação.
- Há uma pausa de 1 s entre chamadas para não sobrecarregar o tribunal.

## Limites atuais

- Só **PJe da Justiça do Trabalho**. TJs usam sistemas diferentes (PJe estadual, e-SAJ, eproc, Projudi) e ficam para uma próxima etapa.
- Não calcula prazos ainda. O `resumo.json` com as novidades é a entrada para a calculadora de prazos (dias úteis, CLT arts. 775 e 775-A, feriados).
