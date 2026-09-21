# Prompts

Prompts do pipeline, versionados para evoluírem com histórico.

- `materiais.md` — título, descrição do YouTube e texto de thumb
- `cortes.md` — seleção de trechos para Reels/Shorts
- `posts.md` — escolha das citações para os posts de Instagram

Os comandos `brief --materiais` e `brief --cortes` montam o pacote de leitura
(prompt + metadados do episódio + transcrição) que o modelo consome em sessão.
O `post --cortes` faz o mesmo com `posts.md`, entregando a fala dos cortes já
aprovados em vez da transcrição inteira.

## Placeholders

O `brief` substitui estes marcadores antes de entregar o pacote:

| Marcador | Onde | Conteúdo |
|---|---|---|
| `{{METADADOS}}` | `materiais.md`, `posts.md` | metadados do `episodio.json` |
| `{{TRANSCRICAO}}` | `materiais.md`, `cortes.md` | transcrição com `[mm:ss]` por segmento |
| `{{CURADORIA}}` | `cortes.md` | estado da rodada: aprovados, rejeitados, motivos, vagas |
| `{{CORTES}}` | `posts.md` | fala literal de cada corte aprovado que foi selecionado |

## Sobre estes arquivos

Os prompts deste pacote são **esqueletos genéricos**: eles têm a estrutura e os
placeholders que o código espera, mas não trazem critério editorial pronto.
Cada canal precisa escrever o próprio — o que torna um corte bom, que tipo de
citação funciona no feed, qual o tom da descrição. É esse conteúdo que faz a
diferença no resultado, e ele se constrói com o uso.

Ao ajustar um prompt, commite a mudança separadamente e registre o motivo na
mensagem: o histórico é o que permite correlacionar mudança de prompt com
mudança de resultado.
