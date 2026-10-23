"""
Tartaruga - interface de texto.

Este arquivo cuida só da conversa com o usuário: mostrar, perguntar e ler.
Toda a inteligência está em `tartaruga/nucleo.py`.

Para rodar:

    python main.py
"""

import sys

# Precisa vir antes de qualquer saída na tela: quando empacotado, o programa
# pode ter sido chamado apenas para executar um trecho de código do usuário.
from tartaruga.ferramentas.executar import tratar_modo_executor

tratar_modo_executor()

from tartaruga.nucleo import Tartaruga  # noqa: E402

# ---------------------------------------------------------------------------
# Cores no terminal
# ---------------------------------------------------------------------------

class Cor:
    """Códigos ANSI para colorir a saída."""

    AZUL = "\033[94m"
    VERDE = "\033[92m"
    AMARELO = "\033[93m"
    VERMELHO = "\033[91m"
    CINZA = "\033[90m"
    NEGRITO = "\033[1m"
    FIM = "\033[0m"

    @classmethod
    def desativar(cls) -> None:
        """Zera todos os códigos, para terminais que não entendem ANSI."""
        for atributo in ("AZUL", "VERDE", "AMARELO", "VERMELHO", "CINZA", "NEGRITO", "FIM"):
            setattr(cls, atributo, "")


def preparar_terminal() -> None:
    """Liga o suporte a cores no Windows.

    O terminal do Windows entende ANSI, mas o modo precisa ser ativado via
    API. Se não der certo, seguimos sem cor: melhor texto limpo do que a tela
    poluída com códigos de escape soltos.
    """
    if sys.platform != "win32":
        return

    try:
        import ctypes

        kernel32 = ctypes.windll.kernel32
        # -11 = STD_OUTPUT_HANDLE, 7 = modo atual | ENABLE_VIRTUAL_TERMINAL_PROCESSING
        if kernel32.SetConsoleMode(kernel32.GetStdHandle(-11), 7) == 0:
            Cor.desativar()
    except Exception:
        Cor.desativar()


# ---------------------------------------------------------------------------
# Apresentação
# ---------------------------------------------------------------------------

BANNER = r"""
    _____          _
   |_   _|_ _ _ __| |_ __ _ _ __ _   _  __ _  __ _
     | |/ _` | '__| __/ _` | '__| | | |/ _` |/ _` |
     | | (_| | |  | || (_| | |  | |_| | (_| | (_| |
     |_|\__,_|_|   \__\__,_|_|   \__,_|\__, |\__,_|
                                       |___/
"""

AJUDA = """
Comandos:
  /ajuda       mostra esta mensagem
  /codigo      abre o modo de várias linhas para colar código
  /historico   mostra a conversa até agora
  /briefing    inicia o briefing de uma landing page
  /semantica   mostra o estado da compreensão semântica local
  /limpar      esquece a conversa da sessão atual
  /sair        encerra

Exemplos do que perguntar:
  como faço um laço for em python
  o que é uma list comprehension
  roda esse código
  pesquisa sobre fastapi na internet
  lista os arquivos
  quero uma landing page
"""


def imprimir_tartaruga(texto: str) -> None:
    # As respostas usam **negrito** e `código`, que a interface gráfica
    # converte em formatação. No terminal não há como formatar, então as
    # marcas são removidas em vez de aparecerem cruas.
    limpo = texto.replace("**", "")
    print(f"\n{Cor.VERDE}{Cor.NEGRITO}Tartaruga:{Cor.FIM} {limpo}\n")


def imprimir_aviso(texto: str) -> None:
    print(f"{Cor.AMARELO}{texto}{Cor.FIM}")


def imprimir_debug(intencao: str, confianca: float) -> None:
    """Mostra a decisão do classificador.

    Deixar isso visível é proposital: numa apresentação, é o que prova que
    existe um modelo decidindo, e não uma cadeia de ifs.
    """
    detalhe = f" | pontuação do classificador: {confianca:.0%}" if confianca > 0 else ""
    print(f"{Cor.CINZA}  [intenção: {intencao}{detalhe}]{Cor.FIM}")


# ---------------------------------------------------------------------------
# Entrada do usuário
# ---------------------------------------------------------------------------

def ler_bloco_codigo() -> str:
    """Lê várias linhas até o usuário digitar FIM numa linha sozinha."""
    print(f"{Cor.CINZA}  Cole o código e digite FIM numa linha vazia para terminar.{Cor.FIM}")
    linhas: list[str] = []
    while True:
        try:
            linha = input(f"{Cor.CINZA}  | {Cor.FIM}")
        except (EOFError, KeyboardInterrupt):
            break
        if linha.strip().upper() == "FIM":
            break
        linhas.append(linha)
    return "\n".join(linhas)


def confirmar(pergunta: str) -> bool:
    """Pergunta sim ou não. Qualquer coisa diferente de 's' conta como não.

    A postura é conservadora de propósito: na dúvida, não executa.
    """
    try:
        resposta = input(f"{Cor.AMARELO}{pergunta} (s/n) {Cor.FIM}").strip().lower()
    except (EOFError, KeyboardInterrupt):
        return False
    return resposta in ("s", "sim", "y", "yes")


# ---------------------------------------------------------------------------
# Laço principal
# ---------------------------------------------------------------------------

def main() -> int:
    preparar_terminal()

    print(f"{Cor.VERDE}{BANNER}{Cor.FIM}")
    print(f"  {Cor.NEGRITO}Assistente de programação com núcleo próprio{Cor.FIM}")
    print(f"  {Cor.CINZA}Projeto de Análise e Desenvolvimento de Sistemas{Cor.FIM}")

    try:
        assistente = Tartaruga()
    except FileNotFoundError as erro:
        print(f"\n{Cor.VERMELHO}Erro ao iniciar: {erro}{Cor.FIM}")
        print("Verifique se a pasta dados/ está no lugar.")
        return 1

    print(f"  {Cor.CINZA}{len(assistente.base)} tópicos na base | "
          f"{len(assistente.classificador.vocabulario)} palavras aprendidas{Cor.FIM}")

    if len(assistente.memoria) > 0:
        print(f"  {Cor.CINZA}Conversa anterior retomada "
              f"({len(assistente.memoria)} mensagens).{Cor.FIM}")

    print(f"\n  Digite {Cor.NEGRITO}/ajuda{Cor.FIM} para ver os comandos.\n")

    while True:
        try:
            # O lstrip do ﻿ remove a marca de ordem de bytes (BOM) que
            # aparece quando a entrada vem de um arquivo UTF-8 redirecionado
            # em vez do teclado. Sem isso, a primeira palavra chegaria com um
            # caractere invisível grudado e não casaria com nada.
            entrada = input(f"{Cor.AZUL}{Cor.NEGRITO}Você:{Cor.FIM} ").lstrip("﻿").strip()
        except (EOFError, KeyboardInterrupt):
            print()
            imprimir_tartaruga("Até mais!")
            break

        if not entrada:
            continue

        # --- comandos da interface (não passam pelo classificador) ---
        comando = entrada.lower()

        if comando in ("/sair", "/quit", "/exit"):
            imprimir_tartaruga("Até mais! Nossa conversa fica salva em historico/.")
            break

        if comando == "/ajuda":
            print(AJUDA)
            continue

        if comando == "/limpar":
            assistente.memoria.limpar()
            assistente.dialogo.limpar()
            imprimir_aviso("  Histórico da sessão apagado.")
            continue

        if comando == "/historico":
            entrada = "mostra o histórico"

        if comando == "/codigo":
            codigo = ler_bloco_codigo()
            if not codigo.strip():
                imprimir_aviso("  Nenhum código recebido.")
                continue
            # Registrar como bloco markdown faz a memória reconhecê-lo,
            # permitindo dizer "roda isso" logo em seguida.
            assistente.memoria.adicionar("usuario", f"```python\n{codigo}\n```")
            imprimir_aviso("  Código guardado. Diga \"roda isso\" para executar.")
            continue

        # --- conversa normal ---
        resposta = assistente.responder(entrada)
        imprimir_debug(resposta.intencao, resposta.confianca)
        imprimir_tartaruga(resposta.texto)

        # --- execução de código, sempre com confirmação explícita ---
        if resposta.codigo_pendente:
            print(f"{Cor.CINZA}{'─' * 60}{Cor.FIM}")
            print(resposta.codigo_pendente)
            print(f"{Cor.CINZA}{'─' * 60}{Cor.FIM}")

            if confirmar("Posso executar este código?"):
                saida = assistente.executar_codigo_confirmado(resposta.codigo_pendente)
                imprimir_tartaruga(saida)
            else:
                imprimir_aviso("  Execução cancelada.\n")

        if resposta.encerrar:
            break

    assistente.memoria.salvar()
    return 0


if __name__ == "__main__":
    sys.exit(main())
