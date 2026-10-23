"""
Leitura e escrita de arquivos, restritas a uma pasta segura.

Toda operação acontece dentro de `workspace/`, na raiz do projeto. A função
`_resolver` é a guardiã dessa regra: ela transforma o caminho pedido em um
caminho absoluto e confere se ele realmente está dentro do workspace.

Isso bloqueia o ataque clássico de travessia de diretório, em que um caminho
como `../../Windows/System32/algo` escaparia da pasta pretendida. Como
`resolve()` já elimina os `..`, basta verificar o resultado final.
"""

from pathlib import Path

from ..caminhos import gravavel

# Os arquivos do usuário precisam sobreviver ao fechamento do programa, então
# ficam ao lado do executável quando empacotado.
WORKSPACE = gravavel("workspace")

# Limite de tamanho para não despejar um arquivo gigante no terminal.
LIMITE_LEITURA = 20_000


class ErroDeCaminho(Exception):
    """O caminho pedido está fora da pasta permitida."""


def _resolver(caminho: str) -> Path:
    """Converte o caminho pedido em absoluto e garante que fique no workspace."""
    WORKSPACE.mkdir(parents=True, exist_ok=True)
    alvo = (WORKSPACE / caminho).resolve()

    # Path.is_relative_to existe a partir do Python 3.9.
    if not alvo.is_relative_to(WORKSPACE.resolve()):
        raise ErroDeCaminho(
            f"Acesso negado: '{caminho}' está fora da pasta workspace/. "
            "Por segurança, a Tartaruga só mexe em arquivos dentro dela."
        )
    return alvo


def listar(subpasta: str = ".") -> list[str]:
    """Lista os arquivos e pastas do workspace.

    Pastas aparecem com uma barra no final, para ficarem visualmente distintas.
    """
    alvo = _resolver(subpasta)
    if not alvo.exists():
        return []

    itens: list[str] = []
    for item in sorted(alvo.iterdir()):
        itens.append(f"{item.name}/" if item.is_dir() else item.name)
    return itens


def ler(caminho: str) -> str:
    """Lê um arquivo de texto do workspace."""
    alvo = _resolver(caminho)

    if not alvo.exists():
        raise FileNotFoundError(f"O arquivo '{caminho}' não existe no workspace.")
    if alvo.is_dir():
        raise IsADirectoryError(f"'{caminho}' é uma pasta, não um arquivo.")

    conteudo = alvo.read_text(encoding="utf-8", errors="replace")

    if len(conteudo) > LIMITE_LEITURA:
        return (
            conteudo[:LIMITE_LEITURA]
            + f"\n\n[... arquivo cortado em {LIMITE_LEITURA} caracteres ...]"
        )
    return conteudo


def escrever(caminho: str, conteudo: str) -> Path:
    """Grava um arquivo de texto no workspace, criando as pastas necessárias."""
    alvo = _resolver(caminho)
    alvo.parent.mkdir(parents=True, exist_ok=True)
    alvo.write_text(conteudo, encoding="utf-8")
    return alvo


def existe(caminho: str) -> bool:
    """Informa se o caminho existe dentro do workspace."""
    try:
        return _resolver(caminho).exists()
    except ErroDeCaminho:
        return False
