"""
Execução de código Python.

Esta é a ferramenta mais poderosa - e por isso a mais cuidadosa - do projeto.

Medidas de segurança adotadas:

1. PROCESSO SEPARADO. O código roda num `subprocess` próprio, não dentro da
   Tartaruga. Se ele travar ou quebrar, o assistente continua de pé.

2. TEMPO LIMITE. Após 5 segundos o processo é encerrado. Isso impede que um
   laço infinito (`while True:`) congele a aplicação.

3. DIRETÓRIO DE TRABALHO. O código inicia em `workspace/`. Caminhos relativos
   simples partem dali, mas isso não impede acesso a outras pastas.

4. CONFIRMAÇÃO DO USUÁRIO. Antes de qualquer execução, a interface mostra o
   código e pede autorização explícita. Esta regra vive em `nucleo.py`,
   pois é uma decisão de interação, não de execução.

Vale registrar no relatório: isto NÃO é um sandbox de verdade. O código
executado tem os mesmos poderes do usuário que rodou a Tartaruga. A proteção
real aqui é o passo 4 - ninguém roda nada sem ver antes.
"""

import subprocess
import sys
import tempfile
from dataclasses import dataclass
from pathlib import Path


from ..caminhos import gravavel

WORKSPACE = gravavel("workspace")

TEMPO_LIMITE_PADRAO = 5

# ---------------------------------------------------------------------------
# Modo executor - a peça que faz a execução de código funcionar no .exe
# ---------------------------------------------------------------------------
#
# PROBLEMA: fora do empacotamento, `sys.executable` é o python.exe, e rodar o
# código do usuário é só chamá-lo com o arquivo. Dentro de um .exe gerado pelo
# PyInstaller, `sys.executable` passa a ser O PRÓPRIO EXECUTÁVEL - chamá-lo
# abriria outra janela do assistente em vez de rodar o código.
#
# SOLUÇÃO: o .exe já carrega um interpretador Python embutido. Ensinamos o
# programa a se comportar como executor quando recebe esta flag: ele roda o
# arquivo indicado, imprime a saída e encerra, sem abrir interface nenhuma.
# O assistente então chama a si mesmo, e todo o isolamento continua igual -
# processo separado, timeout de 5 segundos, saída capturada.
FLAG_EXECUTOR = "--executar-arquivo"


def tratar_modo_executor() -> None:
    """Se o programa foi chamado como executor, roda o arquivo e encerra.

    Precisa ser a PRIMEIRA coisa executada pelo ponto de entrada, antes de
    qualquer janela ser criada.
    """
    if len(sys.argv) < 3 or sys.argv[1] != FLAG_EXECUTOR:
        return

    caminho = Path(sys.argv[2])
    try:
        # "utf-8-sig" descarta a marca de ordem de bytes (BOM) se ela existir.
        # O `compile` rejeita um arquivo que comece com ela, e vários editores
        # do Windows gravam BOM por padrão. Ler assim aceita os dois formatos.
        codigo = caminho.read_text(encoding="utf-8-sig")
    except OSError as erro:
        print(f"Não foi possível ler o código: {erro}", file=sys.stderr)
        sys.exit(1)

    # O nome "<seu código>" aparece no traceback no lugar do arquivo
    # temporário, que não diria nada para quem está aprendendo.
    try:
        exec(compile(codigo, "<seu código>", "exec"), {"__name__": "__main__"})
    except SystemExit:
        raise
    except BaseException:
        import traceback

        tipo, valor, tb = sys.exc_info()
        # tb.tb_next descarta o quadro desta própria função, deixando no
        # traceback apenas as linhas do código do usuário.
        traceback.print_exception(tipo, valor, tb.tb_next if tb else None)
        sys.exit(1)

    sys.exit(0)


def _comando_execucao(caminho_script: Path) -> list[str]:
    """Monta a linha de comando que roda o script, empacotado ou não."""
    if getattr(sys, "frozen", False):
        return [sys.executable, FLAG_EXECUTOR, str(caminho_script)]
    return [sys.executable, str(caminho_script)]


@dataclass
class ResultadoExecucao:
    """O que aconteceu ao rodar o código."""

    sucesso: bool
    saida: str
    erro: str
    expirou: bool = False

    @property
    def vazio(self) -> bool:
        """True quando o código rodou sem erro mas não imprimiu nada."""
        return self.sucesso and not self.saida.strip()


# Erros comuns de quem está aprendendo, traduzidos para linguagem clara.
EXPLICACOES = {
    "SyntaxError": "Erro de sintaxe: há algo escrito de forma que o Python não entende. Verifique dois-pontos, parênteses e aspas.",
    "IndentationError": "Erro de indentação: o recuo das linhas está inconsistente. Dentro de um if/for/def, use sempre o mesmo número de espaços.",
    "NameError": "Você usou um nome que não existe. Verifique se a variável foi criada antes e se o nome está escrito igual.",
    "TypeError": "Operação entre tipos incompatíveis - por exemplo, somar um texto com um número. Use int() ou str() para converter.",
    "ValueError": "O valor tem o tipo certo mas o conteúdo é inválido - como int('abc'), que não dá para converter.",
    "ZeroDivisionError": "Divisão por zero. Verifique o divisor antes de dividir.",
    "IndexError": "Índice fora da lista. Lembre que a primeira posição é 0 e a última é len(lista) - 1.",
    "KeyError": "Essa chave não existe no dicionário. Use .get(chave) para evitar o erro quando a chave pode faltar.",
    "AttributeError": "Esse objeto não tem esse atributo ou método. Confira o tipo do objeto e a grafia do método.",
    "ModuleNotFoundError": "Biblioteca não instalada ou nome errado no import. Instale com: pip install <nome>",
    "ImportError": "Não foi possível importar. Confira o nome do módulo e se ele está instalado.",
    "EOFError": (
        "Este código usa input() para pedir algo digitado, mas o ambiente onde a "
        "Tartaruga executa código não tem entrada interativa disponível — não é um "
        "erro no código em si. Para testar de verdade, salve com \"salva isso em "
        "nome.py\" e rode pelo terminal (python nome.py), onde input() funciona "
        "normalmente."
    ),
}


def explicar_erro(texto_erro: str) -> str | None:
    """Encontra o tipo do erro na mensagem e devolve uma explicação em português."""
    for tipo, explicacao in EXPLICACOES.items():
        if tipo in texto_erro:
            return explicacao
    return None


def limpar_traceback(texto_erro: str, caminho_temporario: Path) -> str:
    """Troca o caminho do arquivo temporário por um rótulo legível.

    O traceback traz algo como `...\\workspace\\tmp60s1ara1.py`, um nome
    gerado que não significa nada para quem está aprendendo e ainda sugere
    que o erro está num arquivo estranho, e não no código que a pessoa
    acabou de escrever. Substituímos pelo rótulo "<seu código>".
    """
    return texto_erro.replace(str(caminho_temporario), "<seu código>")


def executar_python(
    codigo: str,
    tempo_limite: int = TEMPO_LIMITE_PADRAO,
) -> ResultadoExecucao:
    """Roda um trecho de código Python e devolve a saída.

    O código é gravado num arquivo temporário e executado pelo mesmo
    interpretador que roda a Tartaruga (`sys.executable`), garantindo que
    seja a mesma versão do Python.
    """
    WORKSPACE.mkdir(parents=True, exist_ok=True)

    # delete=False porque no Windows um arquivo aberto não pode ser executado
    # por outro processo; fechamos primeiro e removemos no final.
    with tempfile.NamedTemporaryFile(
        mode="w",
        suffix=".py",
        delete=False,
        encoding="utf-8",
        dir=WORKSPACE,
    ) as arquivo:
        arquivo.write(codigo)
        caminho_temporario = Path(arquivo.name)

    try:
        processo = subprocess.run(
            _comando_execucao(caminho_temporario),
            capture_output=True,
            text=True,
            timeout=tempo_limite,
            cwd=WORKSPACE,
            encoding="utf-8",
            errors="replace",
            # Sem esta flag, cada execução piscaria uma janela preta de
            # console na frente da interface gráfica no Windows.
            creationflags=subprocess.CREATE_NO_WINDOW if sys.platform == "win32" else 0,
        )
        return ResultadoExecucao(
            sucesso=processo.returncode == 0,
            saida=processo.stdout,
            erro=limpar_traceback(processo.stderr, caminho_temporario),
        )

    except subprocess.TimeoutExpired:
        return ResultadoExecucao(
            sucesso=False,
            saida="",
            erro=(
                f"A execução passou de {tempo_limite} segundos e foi interrompida. "
                "A causa mais comum é um laço que nunca termina."
            ),
            expirou=True,
        )

    except OSError as erro:
        return ResultadoExecucao(
            sucesso=False,
            saida="",
            erro=f"Não foi possível executar o código: {erro}",
        )

    finally:
        caminho_temporario.unlink(missing_ok=True)
