# Talaria

Pipeline de vídeo que transforma episódios de videocast em cortes verticais
para redes sociais.

Transforma um episódio de videocast em cortes verticais 9:16 (YouTube Shorts /
Instagram Reels), posts de citação para o feed, thumbnail e textos de
publicação — e publica tudo pelas APIs, numa agenda de datas.

## O que ele faz

```
ingest → episodio.json → brief --materiais → brief --cortes → curar
       → render/thumb → post → agenda → publish
```

O código prepara e executa; o julgamento editorial fica com quem opera. Os
comandos `brief` montam pacotes de leitura (prompt + metadados + transcrição)
para um modelo de linguagem consumir em sessão, e as decisões voltam como
arquivos JSON na pasta do episódio.

## Instalação

```bash
python3 -m venv .venv && . .venv/bin/activate
pip install -r requirements.txt
```

Precisa de `ffmpeg` e `ffprobe` no PATH.

## Uso

```bash
# 1) baixa o vídeo e converte a transcrição
python run.py ingest --projeto ep1 --src "<url ou arquivo>"

# 2) preencher projetos/ep1/episodio.json (template criado pelo ingest)
#    Temporada, episódio, empresa, cidade, convidados, links.
#    É a fonte da verdade — a transcrição erra nome próprio.

# 3) materiais: título, descrição e texto da thumb
python run.py brief --projeto ep1 --materiais

# 4) cortes: monta o pacote de curadoria
python run.py brief --projeto ep1 --cortes

# 5) acompanhar o estado da curadoria entre rodadas
python run.py curar --projeto ep1

# 6) quando fechar a meta, exportar momentos.json
python run.py curar --projeto ep1 --exportar

# 7) renderizar e gerar a thumbnail
python run.py render --projeto ep1
python run.py thumb  --projeto ep1

# 8) posts de citação para o feed
python run.py post --projeto ep1 --cortes 1,3
python run.py post --projeto ep1 --gerar

# 9) agendar e publicar
python run.py agenda  --projeto ep1
python run.py publish --projeto ep1
```

## Publicação

A agenda é `decisoes/calendario.json`:

```json
{
  "agenda": [
    {"data": "2026-01-12", "tipo": "corte", "slug": "corte1_exemplo"},
    {"data": "2026-01-13", "tipo": "post",  "slug": "corte1_exemplo"}
  ]
}
```

`tipo: "corte"` publica em YouTube Shorts e Instagram Reels; `tipo: "post"`
vai ao feed do Instagram (imagem única ou carrossel). Item atrasado continua
pendente, e o que já foi ao ar fica em `decisoes/publicado.json`, por peça
**e** plataforma — um corte cujo Reels falhou retenta só o Reels, sem
republicar o Short.

Antes de publicar, tudo é validado: arquivo renderizado, caption, título do
Short (≤100 caracteres), limites de legenda e credenciais. Qualquer pendência
aborta **antes** do primeiro upload.

**Credenciais:** copie `.env.example` para `.env` e preencha. O Instagram
exige conta Business (Creator não publica pela API) e não aceita upload
binário: ele busca a mídia numa URL pública, então o arquivo sobe para um
bucket compatível com S3, é publicado e removido em seguida. Para o YouTube,
rode uma vez `python scripts/youtube_auth.py <client_secret.json>`. O client
OAuth do Google Cloud Console precisa ser do tipo **Desktop**, não Web.

## Personalizar

Seis coisas são identidade de canal. As quatro primeiras vêm neutras neste
pacote; paleta e textos fixos vêm com valores de exemplo.

| O quê | Onde |
|---|---|
| Prompts de curadoria e redação | `prompts/*.md` |
| Template do post e logotipo | `assets/` |
| Nome do programa e perfil social | `NOME_PROGRAMA` e `CARD_ARROBA` em `talaria/config.py` |
| Fontes do render e do post | `assets/fonts/` |
| Paleta da thumb e dos cards | `THUMB_ORANGE`, `CARD_COR_ARROBA` e os `POST_COR_*` em `talaria/config.py` |
| Hashtags fixas e a chamada do episódio | `FIXAS` em `talaria/hashtags.py` e `PREFIXO_EPISODIO` em `talaria/caption.py` |

Os prompts são esqueletos: têm a estrutura e os placeholders que o código
espera, mas o critério editorial precisa ser escrito por quem conhece o
próprio canal. É a parte que mais afeta o resultado.

## Testes

```bash
python3 -m unittest discover -s tests -v
```

São 388 testes, sem dependência de rede: as chamadas de API (YouTube,
Instagram, S3) são mockadas. Rode dentro do venv.

## Notas

- Python 3.9+.
- `projetos/` é ignorado pelo git (vídeos não entram no repositório).
- O ffmpeg de algumas máquinas não tem `drawtext`; nesse caso o pipeline
  rasteriza as legendas em PNG e as sobrepõe com `overlay`, automaticamente.
- Código e documentação estão em português nesta fase; tradução para inglês
  está planejada — ver
  [`docs/specs/2026-09-21-phase-0-fork-and-debrand-design.md`](docs/specs/2026-09-21-phase-0-fork-and-debrand-design.md).
