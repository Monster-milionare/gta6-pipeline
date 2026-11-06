# Pipeline de conteudo GTA VI - versao R$0

1 video longo + ate 8 shorts/dia (comecando em 5 shorts, ver a limitacao de
cota do YouTube abaixo), rodando sozinho no GitHub Actions - nao precisa de
VPS, servidor pago nem PC ligado. Toda peca do stack e gratuita e sem
cartao de credito.

**Contexto de hoje (06/11/2026):** faltam ~13 dias pro lancamento
(19/11/2026). A pre-carga do jogo libera em 10/11/2026 e a Rockstar esta
postando novidade quase todo dia em rockstargames.com/VI - ou seja, e
literalmente o pico da janela de hype. Vale subir isso no ar o quanto
antes, mas sem pular a parte de aprovacao diaria (ver abaixo).

| Etapa | Ferramenta | Custo |
|---|---|---|
| Roteiro (LLM) | Groq API (console.groq.com) | gratis, 14.400 req/dia, sem cartao |
| Voz (TTS) | `edge-tts` (usa o servico do Microsoft Edge) | gratis, sem chave |
| Montagem de video | `ffmpeg` + `Pillow` (ja vem no runner do GitHub) | gratis |
| Upload | YouTube Data API v3 | gratis (com limite de cota, ver abaixo) |
| "Servidor" | GitHub Actions (schedule) | gratis (repo privado: 2.000 min/mes) |

CapCut Pro nao entra aqui (sem API publica, preso ao seu PC). Ele continua
util se algum dia voce quiser editar algo a mao a parte, mas nao e o motor
do automatico.

## A pegadinha que muda o volume: cota gratis do YouTube

A YouTube Data API da 10.000 unidades/dia de graca, e cada upload custa
1.600 unidades -> so da pra automatizar **6 videos/dia** de graca
(10.000 / 1.600 ~= 6,25). Por isso o padrao do projeto e
`SHORTS_PER_DAY = 5` (1 longo + 5 shorts = 6 uploads).

Duas saidas, sem gastar nada:
1. Peca aumento de cota no Google Cloud Console (YouTube Data API v3 ->
   Quotas). E gratis e a aprovacao e por caso de uso, nao por pagamento -
   mas nao e instantanea nem garantida, entao ja peca hoje mesmo.
2. Enquanto isso, gere os shorts extras normalmente pelo pipeline (eles
   ficam prontos como .mp4 no fim do `publish.py --all`) e suba os que
   passarem de 6 **manualmente** pelo site/app do YouTube - upload manual
   nao consome a cota da API.

## Fluxo diario

```
06:00 (BRT)  generate.yml  -> Groq gera o lote do dia (1 longo + 5 shorts)
                              usando so knowledge_base.json como fonte de
                              fatos (trava contra alucinar "leak" falso)
                           -> commita review/<data>.md no repo

[voce abre review/<data>.md - da pra editar direto pelo site do GitHub,
 sem precisar clonar nada - troca "Status: PENDENTE" por "Status: APROVADO"
 e commita. ~5-10 min, uma vez por dia, nao video por video.]

09:00-19:00  publish.yml (roda a cada ~2h, espacado)
                           -> edge-tts narra frase a frase
                           -> ffmpeg monta o video (imagem + legenda + voz)
                           -> agenda upload no YouTube
                           -> commita o item como "Publicado: sim"
```

## Por que Groq e nao Gemini

Testei o Gemini primeiro (e o que a conversa original previa). Criei o
projeto no Google Cloud e a chave normalmente, mas toda chamada real de
geracao voltava `403 PERMISSION_DENIED`: *"The Gemini API free tier is
not available for this project. To use the Gemini API, please set up
billing..."* - ou seja, pra esse projeto novo o Google esta exigindo
cartao cadastrado mesmo pro nivel gratis, provavelmente por ser uma conta
nova. Eu nao cadastro cartao em nome de ninguem (regra fixa), entao troquei
pro Groq, que tem tier gratis real (14.400 requisicoes/dia, 30.000
tokens/min) sem pedir cartao em etapa nenhuma. Se um dia voce quiser voltar
pro Gemini, o jeito seria cadastrar um cartao voce mesmo no Cloud Console
- o uso dentro da cota gratis continuaria sem cobranca, mas isso e decisao
sua, nao algo que eu faco.

## Setup (uma vez so) - da pra terminar hoje

1. **Groq**: crie uma conta gratis em https://console.groq.com (da pra
   entrar direto com a conta Google, sem senha nova) e gere uma chave em
   https://console.groq.com/keys - nao pede cartao em etapa nenhuma.
2. **YouTube**: no Google Cloud Console, crie um projeto, ative a
   "YouTube Data API v3" e crie uma credencial OAuth tipo "Desktop app" ->
   baixe como `client_secret.json` na pasta do projeto.
3. **Autorize uma vez, na sua maquina** (o GitHub Actions nao tem
   navegador pra fazer isso):
   ```bash
   pip install -r requirements.txt
   cp knowledge_base.example.json knowledge_base.json   # ja vem preenchido com fatos de 06/11/2026 - confira rockstargames.com/VI antes de usar, pode ter saido novidade
   echo "GROQ_API_KEY=sua_chave" > .env
   python -c "from upload import _get_credentials; _get_credentials()"
   ```
   Isso abre o navegador, voce autoriza com a conta do canal, e gera
   `token.json` na pasta.
4. **Suba o projeto pro GitHub** como repositorio **privado** (2.000
   min/mes gratis da folga pro seu volume; publico seria ilimitado mas
   deixaria roteiros/config visiveis a qualquer um).
5. **Cadastre os Secrets** do repositorio (Settings -> Secrets and
   variables -> Actions):
   - `GROQ_API_KEY`
   - `YOUTUBE_CLIENT_SECRET_JSON` -> cole o conteudo inteiro do
     `client_secret.json`
   - `YOUTUBE_TOKEN_JSON` -> cole o conteudo inteiro do `token.json`
     gerado no passo 3
   - (opcional) `SMTP_HOST`, `SMTP_USER`, `SMTP_PASSWORD`,
     `NOTIFY_TO_EMAIL` se quiser aviso por e-mail
6. Suba tambem `knowledge_base.json` preenchido (ele nao tem segredo, so
   fatos publicos dos trailers) e uma pasta `assets/broll_oficial/` com
   screenshots dos trailers/Extended Look/Launch Trailer oficiais (frame
   de video oficial pausado e capturado, ou imagens de rockstargames.com/VI
   - nunca imagem gerada por IA fingindo ser cena do jogo).
7. Os dois workflows em `.github/workflows/` ja ficam agendados sozinhos
   a partir do primeiro push. Pra testar sem esperar o horario, use
   "Run workflow" manualmente na aba **Actions** do GitHub.

## knowledge_base.json - a trava anti-alucinacao

Esse arquivo e onde **voce** cola fatos confirmados oficialmente
(rockstargames.com/VI, newswire da Rockstar/Take-Two, Netflix - nunca
leak). O prompt em `script_generator.py` instrui o modelo a usar *somente*
isso como fonte de fatos sobre o jogo. Sem essa trava, o risco e o modelo
"inventar" um detalhe plausivel que parece vazamento real - que foi
exatamente o gatilho da notificacao extrajudicial da Take-Two contra
outros criadores. Nessa reta final pre-lancamento a Rockstar esta postando
quase todo dia, entao vale conferir rockstargames.com/VI antes de cada
lote e atualizar o arquivo.

## Onde entra o checkpoint humano sem virar teatro

`generate.py` gera o lote inteiro do dia de uma vez (1 roteiro longo + N de
shorts) num unico arquivo Markdown. Voce nao aprova video por video ao
longo do dia - abre esse arquivo uma vez, edita o que achar errado ou fora
de tom (da pra fazer isso direto no editor web do GitHub, celular
inclusive), e muda o Status pra APROVADO. `publish.py` sempre rele o
arquivo antes de processar cada item, entao qualquer edicao sua e
respeitada automaticamente.

## Rodando local (sem esperar o cron), pra testar hoje mesmo

```bash
pip install -r requirements.txt
sudo apt-get install -y ffmpeg   # se nao tiver
cp knowledge_base.example.json knowledge_base.json   # confira/preencha antes
python generate.py
# edite review/<data>.md se quiser, troque Status pra APROVADO
python approve.py <data>
python publish.py --all   # gera e faz upload de tudo que estiver aprovado
```

## Sobre o volume e o risco de banimento (recapitulando)

Ficamos em 1 longo + 5-8 shorts/dia porque 15 shorts + 3 longos/dia era
quase o retrato exato do que o sistema anti-spam do YouTube (S-CTS) usa
pra agrupar e banir canais em massa: alta frequencia nao-humana + mesmo
padrao semantico. O design daqui (roteiro variado por angulo, trava contra
alucinacao, narracao real, checkpoint humano diario) existe pra ficar do
lado "canal automatizado com direcao humana" e nao "cluster de spam".
