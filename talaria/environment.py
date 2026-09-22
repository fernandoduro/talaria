"""Carrega o `.env` para dentro do environment do processo.

Os módulos de publicação leem credencial de `os.environ`, mas quem write o
`.env` é o gestor num editor — sem esta ponte o arquivo fica preenchido e o
`publish` reclama de variável não definida, que é o error mais confuso possível
(a response está no arquivo aberto na tela).

É um parser mínimo de propósito: o `.env` tem uma dúzia de lines
`CHAVE=valor` escritas à mão. Não interpola `${OUTRA}`, não expande `~`, não
lê multilinha — cada uma dessas seria uma regra a mais para o gestor lembrar
ao colar um token, e nenhuma delas apareceu em uso.
"""
from __future__ import annotations

import os

# A raiz do repo, dois níveis acima deste arquivo (talaria/environment.py).
DEFAULT_PATH = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                      ".env")


def _clean_value(value: str) -> str:
    """Tira espaço das pontas e um par de aspas, se houver.

    Colar de um console traz aspas junto com frequência, e um token entre
    aspas falha na API com "credencial inválida" — error que não aponta para
    o par de aspas como causa.
    """
    value = value.strip()
    if len(value) >= 2 and value[0] == value[-1] and value[0] in "\"'":
        value = value[1:-1]
    return value


def load(path: str = None) -> int:
    """Põe no environment o que estiver no `.env`. Devolve quantas entraram.

    O que já está no environment VENCE o arquivo: `IG_PAGE_TOKEN=x python run.py`
    precisa sobrepor, que é como se testa outra credencial sem editar nada.

    Arquivo ausente não é error — quem só renderiza clip nunca criou um.
    Variável declarada e vazia também não entra: "não configurada" é o state
    honesto, e uma string vazia faria a checagem de credencial passar para a
    API recusar depois, com mensagem pior.
    """
    path = path or DEFAULT_PATH
    if not os.path.exists(path):
        return 0

    added = 0
    with open(path, encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            if line.startswith("export "):
                line = line[len("export "):]
            key, value = line.split("=", 1)   # '=' no valor fica no valor
            key = key.strip()
            value = _clean_value(value)
            if not key or not value or key in os.environ:
                continue
            os.environ[key] = value
            added += 1
    return added
