# Pipeline de conteúdo GTA VI — versão R$0

1 vídeo longo + até 8 shorts/dia (começando em 5 shorts, ver a limitação de
cota do YouTube abaixo), rodando sozinho no GitHub Actions — não precisa de
VPS, servidor pago nem PC ligado. Toda peça do stack é gratuita e sem
cartão de crédito.

**Contexto de hoje (06/11/2026):** faltam ~13 dias pro lançamento
(19/11/2026). A pré-carga do jogo libera em 10/11/2026 e a Rockstar está
postando novidade quase todo dia em rockstargames.com/VI — ou seja, é
literalmente o pico da janela de hype. Vale subir isso no ar o quanto
antes, mas sem pular a parte de aprovação diária (ver abaixo).

| Etapa | Ferramenta | Custo |
|---|---|---|
| Roteiro (LLM) | Groq API (console.groq.com) | grátis, 14.400 req/dia, sem cartão |
| Voz (TTS) | `edge-tts` (usa o serviço do Microsoft Edge) | grátis, sem chave |
| Montagem de vídeo | `ffmpeg` + `Pillow` (já vem no runner do GitHub) | grátis |
| Upload | YouTube Data API v3 | grátis (com limite de cota, ver abaixo) |
| "Servidor" | GitHub Actions (schedule) | grátis (repo privado: 2.000 min/mês) |

CapCut Pro não entra aqui (sem API pública, preso ao seu PC). Ele continua
útil se algum dia você quiser editar algo à mão à parte, mas não é o motor
do automático.

## A pegadinha que muda o volume: cota grátis do YouTube

A YouTube Data API dá 10.000 unidades/dia de graça, e cada upload custa
1.600 unidades → só dá pra automatizar **6 vídeos/dia** de graça
(10.000 ÷ 1.600 ≈ 6,25). Por isso o padrão do projeto é
`SHORTS_PER_DAY = 5` (1 longo + 5 shorts = 6 uploads).

Duas saídas, sem gastar nada:
1. Peça aumento de cota no Google Cloud Console (YouTube Data API v3 →
   Quotas). É grátis e a aprovação é por caso de uso, não por pagamento —
   mas não é instantânea nem garantida, então já peça hoje mesmo.
2. Enquanto isso, gere os shorts extras normalmente pelo pipeline (eles
   ficam prontos como .mp4 no fim do `publish.py --all`) e suba os que
   passarem de 6 **manualmente** pelo site/app do YouTube — upload manual
   não consome a cota da API.

## Fluxo diário

```
06:00 (BRT)  generate.yml  -> Groq gera o lote do dia (1 longo + 5 shorts)
                              usando só knowledge_base.json como fonte de
                              fatos (trava contra alucinar "leak" falso)
                           -> commita review/<data>.md no repo

[você abre review/<data>.md — dá pra editar direto pelo site do GitHub,
 sem precisar clonar nada — troca "Status: PENDENTE" por "Status: APROVADO"
 e commita. ~5-10 min, uma vez por dia, não vídeo por vídeo.]

09:00–19:00  publish.yml (roda a cada ~2h, espaçado)
                           -> edge-tts narra frase a frase
                           -> ffmpeg monta o vídeo (imagem + legenda + voz)
                           -> agenda upload no YouTube
                           -> commita o item como "Publicado: sim"
```

## Por que Groq e não Gemini

Testei o Gemini primeiro (é o que a conversa original previa). Criei o
projeto no Google Cloud e a chave normalmente, mas toda chamada real de
geração voltava `403 PERMISSION_DENIED`: *"The Gemini API free tier is
not available for this project. To use the Gemini API, please set up
billing..."* — ou seja, pra esse projeto novo o Google está exigindo
cartão cadastrado mesmo pro nível grátis, provavelmente por ser uma conta
nova. Eu não cadastro cartão em nome de ninguém (regra fixa), então troquei
pro Groq, que tem tier grátis real (14.400 requisições/dia, 30.000
tokens/min) sem pedir cartão em etapa nenhuma. Se um dia você quiser voltar
pro Gemini, o jeito seria cadastrar um cartão você mesmo no Cloud Console
— o uso dentro da cota grátis continuaria sem cobrança, mas isso é decisão
sua, não algo que eu faço.

## Setup (uma vez só) — dá pra terminar hoje

1. **Groq**: crie uma conta grátis em https://console.groq.com (dá pra
   entrar direto com a conta Google, sem senha nova) e gere uma chave em
   https://console.groq.com/keys — não pede cartão em etapa nenhuma.
2. **YouTube**: no Google Cloud Console, crie um projeto, ative a
   "YouTube Data API v3" e crie uma credencial OAuth tipo "Desktop app" →
   baixe como `client_secret.json` na pasta do projeto.
3. **Autorize uma vez, na sua máquina** (o GitHub Actions não tem
   navegador pra fazer isso):
   ```bash
   pip install -r requirements.txt
   cp knowledge_base.example.json knowledge_base.json   # já vem preenchido com fatos de 06/11/2026 — confira rockstargames.com/VI antes de usar, pode ter saído novidade
   echo "GROQ_API_KEY=sua_chave" > .env
   python -c "from upload import _get_credentials; _get_credentials()"
   ```
   Isso abre o navegador, você autoriza com a conta do canal, e gera
   `token.json` na pasta.
4. **Suba o projeto pro GitHub** como repositório **privado** (2.000
   min/mês grátis dá folga pro seu volume; público seria ilimitado mas
   deixaria roteiros/config visíveis a qualquer um).
5. **Cadastre os Secrets** do repositório (Settings → Secrets and
   variables → Actions):
   - `GROQ_API_KEY`
   - `YOUTUBE_CLIENT_SECRET_JSON` → cole o conteúdo inteiro do
     `client_secret.json`
   - `YOUTUBE_TOKEN_JSON` → cole o conteúdo inteiro do `token.json`
     gerado no passo 3
   - (opcional) `SMTP_HOST`, `SMTP_USER`, `SMTP_PASSWORD`,
     `NOTIFY_TO_EMAIL` se quiser aviso por e-mail
6. Suba também `knowledge_base.json` preenchido (ele não tem segredo, só
   fatos públicos dos trailers) e uma pasta `assets/broll_oficial/` com
   screenshots dos trailers/Extended Look/Launch Trailer oficiais (frame
   de vídeo oficial pausado e capturado, ou imagens de rockstargames.com/VI
   — nunca imagem gerada por IA fingindo ser cena do jogo).
7. Os dois workflows em `.github/workflows/` já ficam agendados sozinhos
   a partir do primeiro push. Pra testar sem esperar o horário, use
   "Run workflow" manualmente na aba **Actions** do GitHub.

## knowledge_base.json — a trava anti-alucinação

Esse arquivo é onde **você** cola fatos confirmados oficialmente
(rockstargames.com/VI, newswire da Rockstar/Take-Two, Netflix — nunca
leak). O prompt em `script_generator.py` instrui o modelo a usar *somente*
isso como fonte de fatos sobre o jogo. Sem essa trava, o risco é o modelo
"inventar" um detalhe plausível que parece vazamento real — que foi
exatamente o gatilho da notificação extrajudicial da Take-Two contra
outros criadores. Nessa reta final pré-lançamento a Rockstar está postando
quase todo dia, então vale conferir rockstargames.com/VI antes de cada
lote e atualizar o arquivo.

## Onde entra o checkpoint humano sem virar teatro

`generate.py` gera o lote inteiro do dia de uma vez (1 roteiro longo + N de
shorts) num único arquivo Markdown. Você não aprova vídeo por vídeo ao
longo do dia — abre esse arquivo uma vez, edita o que achar errado ou fora
de tom (dá pra fazer isso direto no editor web do GitHub, celular
inclusive), e muda o Status pra APROVADO. `publish.py` sempre relê o
arquivo antes de processar cada item, então qualquer edição sua é
respeitada automaticamente.

## Rodando local (sem esperar o cron), pra testar hoje mesmo

```bash
pip install -r requirements.txt
sudo apt-get install -y ffmpeg   # se não tiver
cp knowledge_base.example.json knowledge_base.json   # confira/preencha antes
python generate.py
# edite review/<data>.md se quiser, troque Status pra APROVADO
python approve.py <data>
python publish.py --all   # gera e faz upload de tudo que estiver aprovado
```

## Humanização: voz, mascote animado e pedido de like/inscrição

Atualização pós-rebrand (GTA VI Brasil) pra parecer menos "robótico" e dar
uma identidade mais forte de apresentador de verdade:

- **Voz**: trocado o default de `pt-BR-AntonioNeural` (voz neural
  "clássica") pra `pt-BR-MacerioMultilingualNeural` (geração mais nova,
  mais natural). `tts.py` tenta essa voz primeiro e cai pra
  `AntonioNeural` automaticamente se ela algum dia sumir do catálogo do
  edge-tts — nunca trava o pipeline por causa de nome de voz. Cada frase
  também ganha uma pequena variação aleatória de `rate`/`pitch` e uma
  pausa curta no fim (`PAUSA_ENTRE_FRASES_SEC`), porque narração 100%
  no mesmo tom/ritmo é um dos motivos mais comuns de voz sintética soar
  robótica.
- **Mascote "falando" de verdade**: antes a pose da boca só trocava 1x
  por frase inteira. Agora `render.py` gera vários sub-quadros por frase
  (a cada ~0,28s, ver `MOUTH_FRAME_SEC`) alternando as poses
  `falando_a`/`falando_b`, concatenados num mini-clipe via ffmpeg — dá
  sensação de boca mexendo continuamente em vez de 1 pose travada.
- **Pedido de like/inscrição**: no fim de todo vídeo, `publish.py`
  acrescenta uma frase fixa (sorteada entre algumas variações, pra não
  soar repetitivo pra quem assiste vários vídeos seguidos) pedindo like
  e inscrição — e isso é programático, não depende do LLM lembrar de
  pedir isso no roteiro. Nessa frase o mascote troca pra uma 4ª pose
  nova (`apontando.png`, braço levantado apontando pro canto superior
  direito) e a tela desenha um gráfico "CURTA E SE INSCREVA" ancorado
  exatamente na ponta do dedo (ver `_draw_cta_grafico` em `render.py`) —
  sem usar o logo oficial do YouTube, só formas geométricas originais.

## Thumbnail customizada

`gerar_thumbnail.py` gera uma capa 1280x720 pra cada vídeo (mascote
grande + texto de 3-5 palavras de impacto + tarja de marca), seguindo o
estudo de thumbnails da vidIQ (2026, ~500 vídeos "breakout" em 30
nichos): rosto/personagem ocupando boa parte do quadro, alto contraste,
texto curto, e nada importante no canto inferior-direito (onde o
YouTube sobrepõe a duração do vídeo). `publish.py` chama isso e depois
`upload.set_thumbnail()` — tudo embrulhado em try/except, porque canais
que ainda não verificaram telefone no YouTube levam 403 nessa chamada
("doesn't have permissions to upload and set custom video thumbnails")
até fazerem a verificação; isso nunca derruba a publicação do vídeo em
si, só pula a thumbnail customizada daquele vídeo específico.

## Como o canal fica sempre com conteúdo novo (notícias, easter eggs)

`knowledge_base.json` ganhou uma chave `eventos_proximos` — é onde
entram fatos novos confirmados (anúncios de eventos, novidades da
Rockstar) que ainda não estavam no arquivo original, pra virarem roteiro
sem depender do LLM "adivinhar" nada. Primeiro item já adicionado: o
**"Grand Theft Auto VI: The Festival"** (21/11/2026, Mana Wynwood,
Miami, parceria com a PlayStation, line-up com Travis Scott, Cardi B,
Metro Boomin e outros — 2 dias *depois* do lançamento do jogo, não
antes).

Importante ser honesto sobre o limite técnico aqui: dava pra pensar em
um scraper automático de rockstargames.com/VI rodando dentro do GitHub
Actions, mas o site é renderizado em JavaScript (Next.js) — não dá pra
raspar com `requests` puro, e botar Playwright/navegador headless no CI
só pra isso gastaria minutos extras da cota grátis de Actions (2.000
min/mês), o que vai na contramão do objetivo de R$0. Por isso, por
enquanto, o jeito é **eu (Claude) ir conferindo a página oficial
periodicamente e adicionando fatos novos confirmados em
`eventos_proximos`** conforme a Rockstar for postando — início de lote
diário é um bom momento pra isso, já que de qualquer forma você passa o
olho no `review/<data>.md` antes de aprovar.

## Estratégia de crescimento (pesquisa + meta de inscritos)

Duas pesquisas de mercado (2026) orientam as mudanças acima e o que
ainda falta ajustar:

- **Metricool, "2026 YouTube Study"** (799.718 vídeos / 71.177 contas
  analisadas): títulos mais curtos performam melhor — por isso
  `script_generator.py` agora exige título com até 60 caracteres e
  instrui o modelo a abrir com o gancho mais forte do roteiro na
  primeira frase, nunca com introdução genérica. O estudo também aponta
  algo em torno de ~35 shorts/mês como uma faixa de frequência mais
  saudável pra engajamento/retenção de audiência — bem abaixo do volume
  atual daqui (`SHORTS_PER_DAY = 5` × 30 ≈ 150/mês). **Isso não foi
  mudado automaticamente**: o volume atual é pautado pela cota grátis da
  YouTube Data API (10.000 unidades/dia ÷ 1.600 por upload ≈ 6/dia), não
  por uma escolha deliberada de frequência — ajustar isso é uma decisão
  sua (pedir aumento de cota reduz a pressão, mas publicar menos/dia
  seria uma troca editorial, não técnica).
- **vidIQ, "2026 thumbnail study"** (~500 vídeos "breakout" em 30
  nichos): base do design de `gerar_thumbnail.py` (ver seção acima).

**Sobre a meta de 100 mil inscritos antes do lançamento (19/11/2026) e 1
milhão depois**: vou ser direto em vez de prometer algo que não dá pra
garantir. O canal começou com uma base muito pequena de inscritos e
restam poucos dias até o lançamento — 100 mil inscritos orgânicos nesse
intervalo, sem qualquer impulsionamento pago (que eu não posso fazer em
seu nome de qualquer forma), é uma meta extremamente agressiva pelos
padrões normais de crescimento de canal novo no YouTube, mesmo num nicho
em pico de hype. 1 milhão depois do lançamento é mais plausível num
horizonte mais longo se o canal sustentar qualidade e constância durante
a onda de busca/sugestão que um lançamento AAA desse porte costuma gerar
— mas também não é algo que dá pra garantir.

O compromisso real é: puxar toda alavanca legítima e de custo zero que
essas pesquisas apontam (voz mais humana, mascote animado, CTA
consistente, thumbnail de alto contraste, título curto com gancho forte,
conteúdo sempre atualizado com fatos novos/eventos) e ser transparente
sobre o que está dando certo ou não — em vez de inflar expectativa sobre
um número de inscritos que depende de fatores fora do controle de
qualquer pipeline automatizado (alcance orgânico do YouTube, concorrência
de outros canais fazendo a mesma cobertura, timing do algoritmo).

## Sobre o volume e o risco de banimento (recapitulando)

Ficamos em 1 longo + 5-8 shorts/dia porque 15 shorts + 3 longos/dia era
quase o retrato exato do que o sistema anti-spam do YouTube (S-CTS) usa
pra agrupar e banir canais em massa: alta frequência não-humana + mesmo
padrão semântico. O design daqui (roteiro variado por ângulo, trava contra
alucinação, narração real, checkpoint humano diário) existe pra ficar do
lado "canal automatizado com direção humana" e não "cluster de spam".
