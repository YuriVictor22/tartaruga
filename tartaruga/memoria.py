"""
Memória da conversa: histórico em sessão e persistência em disco.

Faz três coisas:

1. Guarda cada turno da conversa (quem falou, o quê, quando).
2. Salva em JSON para que a conversa continue de onde parou na próxima vez.
3. Serve de CONTEXTO: guarda o último bloco de código mencionado, para que o
   usuário possa dizer "roda isso aí" sem precisar colar o código de novo.

O item 3 é o que diferencia um histórico decorativo de um histórico útil.
"""

import json
import re
from dataclasses import asdict, dataclass, field
from datetime import datetime
from pathlib import Path
from uuid import uuid4

from .caminhos import gravavel
from .persistencia import gravar_json_atomico

# Pasta de escrita: precisa persistir depois que o programa fecha, então fica
# ao lado do executável e nunca na pasta temporária do pacote.
PASTA_HISTORICO = gravavel("historico")

# Captura blocos de código em markdown: ```python ... ```, ```javascript ... ```
# ou ``` ... ``` sem marcador. O marcador (grupo 1) é capturado separado do
# código (grupo 2) - antes eram fundidos num só grupo que só reconhecia
# "python"/"py" como marcador válido. Qualquer outro marcador (javascript,
# html, css) não era removido: a palavra ficava GRUDADA na primeira linha do
# "código" extraído. Um teste real expôs isso: pedir para rodar um exemplo
# de JavaScript preparava para executar a palavra "javascript" solta antes
# do código de verdade - o "código a executar" começava mentindo sobre o
# que era.
PADRAO_BLOCO_CODIGO = re.compile(r"```(\w*)\s*\n?(.*?)```", re.DOTALL)

# Marcadores que correspondem a Python. Qualquer outro (javascript, js, html,
# css, ou nenhum marcador vindo de fonte não confiável) é tratado como
# "não sei que linguagem é" e NÃO é executado sem confirmação extra - ver
# `nucleo.py::_executar_codigo`.
MARCADORES_PYTHON = {"python", "py", ""}


@dataclass
class Turno:
    """Uma fala da conversa."""

    papel: str  # "usuario" ou "tartaruga"
    texto: str
    hora: str = field(default_factory=lambda: datetime.now().isoformat(timespec="seconds"))
    intencao: str | None = None
    confianca: float | None = None
    codigo: str | None = None
    linguagem: str | None = None
    briefing: dict | None = None


class Memoria:
    """Histórico da conversa, com persistência e contexto."""

    def __init__(self, pasta: Path | None = None) -> None:
        self.pasta = pasta or PASTA_HISTORICO
        self.pasta.mkdir(parents=True, exist_ok=True)
        self.turnos: list[Turno] = []
        self.caminho_sessao: Path | None = None

    # ------------------------------------------------------------------
    # Registro
    # ------------------------------------------------------------------

    def adicionar(
        self,
        papel: str,
        texto: str,
        intencao: str | None = None,
        confianca: float | None = None,
        codigo: str | None = None,
        briefing: dict | None = None,
    ) -> Turno:
        """Registra um turno. Se `codigo` não vier, tenta extraí-lo do texto."""
        linguagem = None
        if codigo is None:
            achado = self.extrair_codigo_com_linguagem(texto)
            if achado:
                codigo, linguagem = achado

        turno = Turno(
            papel=papel,
            texto=texto,
            intencao=intencao,
            confianca=confianca,
            codigo=codigo,
            linguagem=linguagem,
            briefing=briefing,
        )
        self.turnos.append(turno)
        return turno

    def limpar(self) -> None:
        """Inicia uma sessão vazia; o arquivo anterior permanece intacto."""
        self.turnos = []
        self.caminho_sessao = None

    # ------------------------------------------------------------------
    # Contexto
    # ------------------------------------------------------------------

    @staticmethod
    def extrair_codigo(texto: str) -> str | None:
        """Extrai o primeiro bloco de código markdown do texto, se houver.

        Devolve só o código, sem a linguagem — mantido para quem já usa
        assim (salvar em arquivo, por exemplo, aceita qualquer linguagem).
        Para decidir se é seguro EXECUTAR, use `extrair_codigo_com_linguagem`.
        """
        resultado = Memoria.extrair_codigo_com_linguagem(texto)
        return resultado[0] if resultado else None

    @staticmethod
    def extrair_codigo_com_linguagem(texto: str) -> tuple[str, str] | None:
        """Extrai o bloco de código E o marcador de linguagem, normalizado.

        A linguagem devolvida é "python" para marcador python/py/vazio, ou o
        marcador em si (javascript, html, css...) caso contrário. Quem for
        EXECUTAR o código precisa distinguir os dois casos — rodar
        JavaScript como se fosse Python silenciosamente é o tipo de erro que
        parece ter funcionado até dar uma mensagem sem sentido nenhuma.
        """
        achado = PADRAO_BLOCO_CODIGO.search(texto)
        if not achado:
            return None

        codigo = achado.group(2).strip()
        if not codigo:
            return None

        marcador = achado.group(1).strip().lower()
        linguagem = "python" if marcador in MARCADORES_PYTHON else marcador
        return codigo, linguagem

    def ultimo_codigo(self) -> str | None:
        """Devolve o bloco de código mais recente mencionado na conversa.

        É o que permite entender "roda isso aí": percorremos o histórico de
        trás para frente até achar um turno que carregue código.
        """
        achado = self.ultimo_codigo_com_linguagem()
        return achado[0] if achado else None

    def ultimo_codigo_com_linguagem(self) -> tuple[str, str] | None:
        """Como `ultimo_codigo`, mas também devolve a linguagem do bloco.

        Turnos antigos, salvos antes desta versão, não têm `linguagem`
        gravada — nesse caso presumimos Python, que era o único caso
        tratado até aqui, para não quebrar conversas já salvas em disco.
        """
        for turno in reversed(self.turnos):
            if turno.codigo:
                return turno.codigo, (turno.linguagem or "python")
        return None

    def ultimos(self, quantidade: int = 10) -> list[Turno]:
        """Os N turnos mais recentes, do mais antigo para o mais novo."""
        return self.turnos[-quantidade:]

    # ------------------------------------------------------------------
    # Persistência
    # ------------------------------------------------------------------

    def _novo_caminho_sessao(self) -> Path:
        instante = datetime.now().strftime("%Y-%m-%d_%H%M%S_%f")
        return self.pasta / f"conversa_{instante}_{uuid4().hex[:8]}.json"

    def salvar(self) -> Path:
        """Grava a conversa do dia em JSON."""
        caminho = self.caminho_sessao or self._novo_caminho_sessao()
        dados = [asdict(turno) for turno in self.turnos]
        gravar_json_atomico(caminho, dados)
        self.caminho_sessao = caminho
        return caminho

    def carregar_ultima(self) -> bool:
        """Retoma a conversa mais recente salva em disco.

        Retorna True se encontrou e carregou algo. Falhas de leitura (arquivo
        corrompido, por exemplo) não derrubam o programa: apenas começamos uma
        conversa nova.
        """
        arquivos = sorted(self.pasta.glob("conversa_*.json"))
        if not arquivos:
            return False

        try:
            with open(arquivos[-1], encoding="utf-8") as arquivo:
                dados = json.load(arquivo)
            turnos = [Turno(**registro) for registro in dados]
        except (json.JSONDecodeError, OSError, TypeError):
            return False

        self.turnos = turnos
        self.caminho_sessao = arquivos[-1]
        return bool(self.turnos)

    # ------------------------------------------------------------------
    # Histórico multi-dia (usado pela busca e pelo painel de histórico)
    #
    # `ultimos()` e `carregar_ultima()` só enxergam a SESSÃO atual ou o
    # último dia salvo. Estes métodos abaixo olham para TODOS os dias já
    # gravados em disco, sem alterar `self.turnos` — é leitura pura, então a
    # conversa em andamento nunca é afetada por uma consulta ao passado.
    # ------------------------------------------------------------------

    def listar_dias(self) -> list[Path]:
        """Arquivos de conversa salvos, do mais recente para o mais antigo."""
        return sorted(self.pasta.glob("conversa_*.json"), reverse=True)

    @staticmethod
    def carregar_dia(caminho: Path) -> list[Turno]:
        """Lê um arquivo de conversa salvo, sem tocar na sessão atual.

        Arquivo corrompido ou ilegível devolve lista vazia — nunca derruba
        quem está só tentando revisar o passado.
        """
        try:
            with open(caminho, encoding="utf-8") as arquivo:
                dados = json.load(arquivo)
            return [Turno(**registro) for registro in dados]
        except (json.JSONDecodeError, OSError, TypeError):
            return []

    def buscar(self, termo: str, limite: int = 50) -> list[tuple[str, Turno]]:
        """Procura um texto em TODAS as conversas salvas, não só na de hoje.

        Devolve pares (nome_do_dia, turno), do mais recente para o mais
        antigo, parando em `limite` resultados — sem isso, um termo comum
        varreria meses de histórico e devolveria uma lista impraticável.
        """
        termo_normalizado = termo.strip().lower()
        if not termo_normalizado:
            return []

        resultados: list[tuple[str, Turno]] = []
        for caminho in self.listar_dias():
            for turno in self.carregar_dia(caminho):
                if termo_normalizado in turno.texto.lower():
                    resultados.append((caminho.stem.replace("conversa_", ""), turno))
                    if len(resultados) >= limite:
                        return resultados
        return resultados

    def __len__(self) -> int:
        return len(self.turnos)
