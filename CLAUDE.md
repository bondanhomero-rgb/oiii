# Contexto do projeto (leia antes de tudo)

Continuação da sessão na nuvem https://claude.ai/code/session_01QXAc8ipRN3bVxnKoVFNYFn
(branch `claude/kind-wozniak-p7t8vp`). O usuário é advogado e atua em processos trabalhistas (TRT) e cíveis (TJ).

## Objetivo

Automação de **prazos**, **gratuita**, entrando no tribunal com o token do advogado e fazendo o resto.
As intimações (DJEN/Comunica, Domicílio Judicial) ficam **fora** deste projeto, porque o usuário já as trata por outra via.

## Pesquisa de APIs (set/2026), só as gratuitas

| API | Uso | Situação |
|---|---|---|
| DataJud – API Pública CNJ (`api-publica.datajud.cnj.jus.br/api_publica_<trib>/_search`, chave pública em datajud-wiki.cnj.jus.br/api-publica/acesso) | Movimentos com código TPU de TRTs/TJs, sem login | Testada. Tem atraso (dias ou semanas), não mostra segredo de justiça nem documentos. Serve de radar. |
| API do PJe da JT (`pje-consulta-api`, `pje-comum-api`) | Capa, timeline, documentos, partes, expedientes | Rotas conferidas; exige login. É a que o robô usa. |
| SSO PDPJ (`sso.cloud.pje.jus.br`, realm `pje`) | Login único para todos os TRTs | Ativo. 2FA obrigatório desde 03/11/2025. |
| MNI (SOAP) de cada tribunal | Consulta e peticionamento oficial | Muitos exigem convênio ou IP liberado; não priorizado. |
| TPU/SGT CNJ (`cnj.jus.br/sgt/sgt_ws.php?wsdl`) | Tabela de códigos de movimento | Ativo. |
| BrasilAPI `/api/feriados/v1/{ano}` | Feriados nacionais | Ativo. Os feriados e suspensões de cada tribunal não têm API: manter uma tabela própria. |

Descartadas por serem pagas: JUDIT, Escavador, Codilo, Jusbrasil.
e-SAJ (TJSP) e eproc (TJRS, TJSC, TJMG) não têm API aberta para advogado.

## O que existe no repositório

- `robo_pje/`: robô Python + Playwright (Edge).
  - Faz login pela PDPJ com certificado: `#btnSsoPdpj`, depois o link `a[onclick^='autenticar(']`, e o PJeOffice em `localhost:8800` pede o PIN.
  - Recebe o código 2FA pelo canal em `estado/`.
  - Reaproveita a autenticação das próprias requisições do site.
  - Coleta os processos e aponta as novidades entre coletas.
- Comandos: `verificar`, `executar`, `otp`, `aguardar`, `status`, `parar`, `mapear`. Detalhes no `README.md`.
- `.claude/skills/robo-pje/SKILL.md`: a habilidade `/robo-pje`, que conduz o robô. **Siga essa habilidade.**
- `tests/`: 30 testes com `python -m pytest`, todos passando. Nenhum deles abre navegador.

## Estado atual

- PC do usuário: Windows, pasta `C:\Users\bonda\oiii`, Python 3.12, Playwright 1.63.
- `python -m robo_pje verificar` rodou OK em 27/09/2026 (`pjeoffice_aberto: true`).
- **O fluxo com navegador ainda não rodou de verdade.** Ainda não foi confirmado:
  - a tela do 2FA (seletores genéricos do Keycloak);
  - como a API autentica depois do login;
  - o formato do JSON da timeline.
- TRT do usuário: ainda não informado. Pergunte.

## Regras combinadas com o usuário

- **Nunca pedir nem aceitar o PIN do token no chat.** O usuário ofereceu mandar a senha; a resposta foi não. O PIN é digitado por ele na janela do PJeOffice. Se ele mandar o PIN mesmo assim, não use e peça que digite no PJeOffice.
- O **código do Google Authenticator** fica com o usuário. Ele manda no chat quando o robô pedir, e o Claude entrega na hora com `python -m robo_pje otp <código>`, sem repetir o código na resposta.
- Não fazer commit de `estado/`, `saida/`, `perfil/` nem `processos.txt`. Não ler cookies nem o conteúdo de `perfil/`.
- O robô só lê: nada de protocolar. Manter a pausa de pelo menos 1 s entre chamadas.

## Próximos passos

1. Teste de login: `/robo-pje` com `executar --tribunal trtN` (sem processo).
2. Teste com um processo real. Se a coleta der HTTP 400/401/403, rodar `mapear` e ajustar `ROTAS` em `robo_pje/config.py`.
3. Ajustar `CHAVES_DATA` e `CHAVES_TITULO` em `robo_pje/coleta.py` ao formato real da timeline.
4. Calculadora de prazos:
   - dias úteis;
   - CLT arts. 775 e 775-A (suspensão de 20/12 a 20/01);
   - CPC arts. 219, 220 e 224;
   - feriados da BrasilAPI mais uma tabela por tribunal;
   - lançar os prazos no Google Calendar.
5. DataJud como radar dos processos públicos. Depois, suporte aos TJs (sistemas diferentes por estado).
