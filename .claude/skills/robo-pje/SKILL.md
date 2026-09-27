---
name: robo-pje
description: Robô que entra no PJe da Justiça do Trabalho (TRT1 a TRT24) com o token do advogado (PJeOffice + PIN), recebe pelo chat o código de 6 dígitos do Google Authenticator e puxa capa, movimentações, expedientes e documentos dos processos. Use quando o usuário digitar /robo-pje ou pedir para "entrar no PJe", "entrar no TRT", "puxar os processos do tribunal", "ver os andamentos no PJe", "rodar o robô", "baixar movimentações" ou "mapear a API do PJe".
---

# Robô PJe (token + 2FA pelo chat)

O robô roda **no computador do usuário**, onde estão o token (certificado A3) e o PJeOffice.
Ele trabalha em segundo plano e conversa com você por arquivos em `estado/`. Você:
1. inicia o robô;
2. fica esperando as etapas com `aguardar`;
3. pede ao usuário o que o robô precisa (PIN no PJeOffice, código do autenticador);
4. entrega o código com `otp`;
5. apresenta o resultado.

Todos os comandos rodam **a partir da raiz deste repositório**. No Windows, se `python` não
existir, use `py -3` no lugar.

## 0. Pré-requisitos (sempre rode primeiro)

```bash
python -m robo_pje verificar
```

- `playwright` faltando → rode `pip install -r requirements.txt` (confirme com o usuário antes).
- `pjeoffice_aberto: false` → peça ao usuário para abrir o PJeOffice e espetar o token, e rode `verificar` de novo.
- Se você estiver numa sessão na nuvem (sem PJeOffice/token, Linux), **pare**. Explique que o robô só funciona no PC do usuário.

## 1. O que coletar

Pergunte (se o usuário não disse):
- **Processos**: números CNJ no chat, ou use o `processos.txt` (um por linha). O TRT sai do próprio número (J=5).
- **Grau**: 1º (padrão) ou 2º (`--grau 2`).
- **Baixar documentos das novidades?** Se sim, use `--documentos-novos`.

Só com `--tribunal trtN` e sem processos, o robô apenas faz o login (serve para testar).

## 2. Iniciar

Anote o `seq` atual:

```bash
python -m robo_pje status
```

Depois inicie o robô **em segundo plano** (Bash com `run_in_background: true`):

```bash
python -m robo_pje executar --processo 0000074-94.2010.5.02.0043 --processo <outro>
# ou: python -m robo_pje executar            (usa processos.txt)
```

## 3. Laço de espera

Repita até chegar numa etapa final (`concluido`, `erro`, `parado`), sempre passando o último `seq` visto:

```bash
python -m robo_pje aguardar --apos-seq <seq>
```

| etapa | o que fazer |
|---|---|
| `aguardando_pin` | Diga: "Digite o PIN do token na janela do PJeOffice, no computador." **Nunca peça o PIN no chat.** Se o usuário mandar o PIN no chat, não use: peça que digite no PJeOffice. |
| `aguardando_2fa` | Peça: "Me mande agora o código de 6 dígitos do Google Authenticator (conta PDPJ/PJe)." |
| `2fa_recusado` | Mostre a mensagem e peça um código **novo** (espere o número trocar no app). |
| `logado` | Avise rapidamente que o login deu certo e continue aguardando. |
| `timeout: true` | Nada mudou ainda; se a etapa for `coletando`, informe o progresso (`atual/total`) e continue. |
| `mapeando` | Diga ao usuário para navegar no PJe (abrir processos, expedientes) e fechar o navegador ao terminar. |
| `concluido` | Leia o arquivo em `resumo` e apresente o resultado (seção 4). |
| `erro` | Mostre a `mensagem` e as linhas de `log`; veja a tabela da seção 5. Se houver `captura_de_tela`, cite o caminho. |
| `parado` | Confirme que o robô parou. |

### Quando o usuário mandar o código do autenticador

**Entregue imediatamente, antes de qualquer outra coisa.** O código vale uns 30 segundos:

```bash
python -m robo_pje otp 123456
```

- Não repita o código na resposta e não o grave em nenhum outro lugar.
- Se o comando disser que o formato é inválido, peça os 6 dígitos de novo.
- Depois volte ao `aguardar`.

## 4. Apresentar o resultado

O `resumo.json` tem, por processo: `numero`, `tribunal`, `id`, `total_eventos`, `novidades`
(eventos novos desde a coleta anterior), `ultimos_eventos`, `avisos`, `erro` e `documentos_baixados`.

- Na **primeira coleta** de um processo (`primeira_coleta: true`) não há novidades. É a linha de base; mostre os `ultimos_eventos`.
- Monte uma tabela curta: processo | novidades (data + descrição) | observações.
- Diga onde ficaram os arquivos (`saida/<data>/<trt>/<processo>/`: `capa.json`, `timeline.json`, `partes.json`, `expedientes.json`, `documentos/`).
- Se `descricao` vier vazia em tudo, o formato da timeline mudou: abra um `timeline.json`, veja os nomes dos campos e ajuste `CHAVES_DATA` e `CHAVES_TITULO` em `robo_pje/coleta.py`.

## 5. Problemas comuns

| mensagem | causa provável / ação |
|---|---|
| PJeOffice não está aberto | Abrir o PJeOffice com o token espetado; rodar de novo. |
| Aviso do site: "Não foi possível encontrar o PJe Office" | O navegador não alcançou o PJeOffice. Se o Edge/Chrome perguntou sobre acessar "dispositivos da rede local", clicar em **Permitir**. |
| Tempo esgotado no login | O PIN não foi digitado a tempo, ou o PJeOffice pediu para autorizar o servidor. Rodar de novo com o usuário olhando o PC. |
| CONFIGURAR o autenticador | O 2FA ainda não foi configurado nessa conta; o usuário faz isso uma vez manualmente. |
| HTTP 400/401/403 na coleta | A sessão não foi reconhecida pela API. Rode `python -m robo_pje mapear --tribunal trtN`; o usuário navega e o arquivo `saida/mapa_api_trtN.jsonl` mostra as rotas reais. Ajuste `ROTAS` em `robo_pje/config.py`. |
| processo não encontrado no 1º grau | Tente `--grau 2`. |
| Já existe um robô rodando | Veja `status`. Se travou, `python -m robo_pje parar` e depois `executar --forcar`. |

Para cancelar a qualquer momento: `python -m robo_pje parar`.

## Regras

- Um robô por vez. Não diminua `--pausa` abaixo de 1 segundo (não sobrecarregar o tribunal).
- Nunca leia, imprima ou copie cookies, tokens ou o conteúdo de `perfil/`.
- `estado/`, `saida/` e `perfil/` têm dados de processos e da sessão: nunca faça commit deles (já estão no `.gitignore`).
- O robô só lê. Ele não protocola nada.
