"""
Resolução de caminhos, funcionando tanto pelo código-fonte quanto no .exe.

Rodando pelo código-fonte, tudo mora na pasta do projeto e não há mistério.
Empacotado pelo PyInstaller, existem DOIS lugares diferentes, e confundi-los
é uma fonte clássica de bugs:

1. A pasta temporária do pacote (`sys._MEIPASS`). O PyInstaller extrai os
   arquivos embutidos ali ao abrir o programa e APAGA TUDO ao fechar. Serve
   para o que é somente leitura - no nosso caso, `dados/`.

2. A pasta onde o executável está. É o único lugar que persiste entre
   execuções. Serve para o que o programa escreve - `historico/` e
   `workspace/`.

Gravar no lugar 1 seria um bug silencioso: funcionaria durante o uso e o
usuário perderia todas as conversas ao fechar a janela.
"""

import sys
from pathlib import Path


def empacotado() -> bool:
    """Informa se estamos rodando dentro de um executável do PyInstaller."""
    return getattr(sys, "frozen", False)


def _raiz_fonte() -> Path:
    """Raiz do projeto quando rodando pelo código-fonte."""
    return Path(__file__).resolve().parent.parent


def recurso(*partes: str) -> Path:
    """Caminho de um arquivo somente leitura que acompanha o programa.

    Exemplo: `recurso("dados", "conhecimento.json")`
    """
    if empacotado():
        base = Path(getattr(sys, "_MEIPASS", Path(sys.executable).resolve().parent))
    else:
        base = _raiz_fonte()
    return base.joinpath(*partes)


def gravavel(*partes: str) -> Path:
    """Caminho de uma pasta onde o programa pode escrever e que persiste.

    Exemplo: `gravavel("historico")`
    """
    if empacotado():
        base = Path(sys.executable).resolve().parent
    else:
        base = _raiz_fonte()
    return base.joinpath(*partes)
