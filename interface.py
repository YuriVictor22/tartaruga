"""
Tartaruga - interface gráfica (PyQt6).

Janela nativa do sistema, sem navegador e sem servidor web.

Este arquivo cuida apenas da apresentação: desenhar, receber cliques e
mostrar resultados. Toda a inteligência continua em `tartaruga/nucleo.py`,
exatamente a mesma usada pela versão de terminal (`main.py`).

Para rodar:

    python interface.py
"""

import html
import re
import sys
import os

# Builds --windowed não têm streams de console. Bibliotecas do encoder
# podem escrever progresso mesmo sem barra explícita; mantenha streams válidos.
if sys.stdout is None:
    sys.stdout = open(os.devnull, "w", encoding="utf-8")
if sys.stderr is None:
    sys.stderr = open(os.devnull, "w", encoding="utf-8")

# ATENÇÃO: esta importação e esta chamada precisam vir ANTES de qualquer
# coisa do PyQt6. Quando empacotado, o programa pode ter sido chamado pelo
# próprio assistente apenas para executar um trecho de código do usuário -
# nesse caso ele roda o código, encerra, e nenhuma janela deve ser criada.
from tartaruga.ferramentas.executar import tratar_modo_executor

tratar_modo_executor()

from PyQt6.QtCore import Qt, QSize, QThread, QTimer, pyqtSignal  # noqa: E402
from PyQt6.QtGui import (  # noqa: E402
    QColor,
    QFont,
    QIcon,
    QKeySequence,
    QPainter,
    QPixmap,
    QShortcut,
    QTextCursor,
)
from PyQt6.QtWidgets import (  # noqa: E402
    QApplication,
    QDialog,
    QDialogButtonBox,
    QFrame,
    QFileDialog,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QInputDialog,
    QListWidget,
    QListWidgetItem,
    QMessageBox,
    QPlainTextEdit,
    QPushButton,
    QScrollArea,
    QSplitter,
    QTabWidget,
    QTextBrowser,
    QVBoxLayout,
    QWidget,
)

from tartaruga.caminhos import recurso  # noqa: E402
from tartaruga.backup import exportar as exportar_backup, restaurar as restaurar_backup  # noqa: E402
from tartaruga.briefing import CAMPOS  # noqa: E402
from tartaruga.configuracoes import Configuracoes  # noqa: E402
from tartaruga.diagnostico import coletar as coletar_diagnostico, formatar as formatar_diagnostico  # noqa: E402
from tartaruga.feedback import registrar as registrar_feedback  # noqa: E402
from tartaruga.ferramentas import llm, preview  # noqa: E402
from tartaruga.ferramentas.preview_documento import montar_documento  # noqa: E402
from tartaruga.nucleo import Tartaruga  # noqa: E402

# ---------------------------------------------------------------------------
# Paleta
#
# Visual escuro e discreto: preto quase puro, bordas quase invisíveis, cor usada
# com moderação e texto solto em vez de caixas pesadas. A estrutura continua:
# balão do usuário à direita, da Tartaruga à esquerda.
# ---------------------------------------------------------------------------

FUNDO = "#090b0a"
PAINEL = "#121513"
PAINEL_ELEVADO = "#181c19"
LATERAL = "#0d100e"
BORDA = "#283029"
BORDA_SUTIL = "#1c221e"
TEXTO = "#eef2ee"
TEXTO_FRACO = "#8c988f"
TEXTO_DESABILITADO = "#4a4a4f"
VERDE = "#57d68d"
VERDE_SUAVE = "#173323"
AZUL = "#79a9f5"
AMARELO = "#fbbf24"
VERMELHO = "#f87171"
FUNDO_CODIGO = "#000000"

# As mensagens não têm mais fundo nem borda desenhados (pedido do
# usuário: texto direto sobre o fundo do painel, sem caixa visível) - só a
# posição (esquerda/direita) e a cor do nome ainda distinguem quem falou.

# Largura do balão em relação ao visor. O espaço restante vira a "folga" que
# empurra o balão para um dos lados.
LARGURA_BALAO = 78

FONTE_CODIGO = "Consolas, 'Cascadia Mono', monospace"

ESTILO = f"""
QWidget {{
    background-color: {FUNDO};
    color: {TEXTO};
    font-family: 'Segoe UI', sans-serif;
    font-size: 14px;
}}
QFrame#barraLateral {{
    background-color: {LATERAL};
    border-right: 1px solid {BORDA_SUTIL};
}}
QFrame#areaPrincipal {{
    background-color: {FUNDO};
}}
QFrame#composer {{
    background-color: {PAINEL};
    border: 1px solid {BORDA};
    border-radius: 14px;
}}
QFrame#composer[comFoco="true"] {{
    border: 1px solid {AZUL};
}}
QLabel#secaoLateral {{
    color: {TEXTO_FRACO};
    font-size: 10px;
    font-weight: 700;
    letter-spacing: 1px;
}}
QPushButton#secaoCabecalho {{
    background-color: transparent;
    border: 1px solid transparent;
    border-radius: 6px;
    padding: 6px 4px;
    color: {TEXTO_FRACO};
    font-size: 10px;
    font-weight: 700;
    letter-spacing: 1px;
    text-align: left;
}}
QPushButton#secaoCabecalho:hover {{
    color: {TEXTO};
    background-color: {PAINEL_ELEVADO};
}}
QPushButton#secaoCabecalho:focus {{
    color: {TEXTO};
    border-color: {AZUL};
}}
QTextBrowser {{
    background-color: {FUNDO};
    border: none;
    padding: 6px;
}}
QLineEdit {{
    background-color: transparent;
    border: none;
    padding: 12px 14px;
    font-size: 14px;
}}
QLineEdit:focus {{
    border: none;
}}
QLineEdit:disabled {{
    color: {TEXTO_FRACO};
}}
QPushButton {{
    background-color: transparent;
    border: 1px solid {BORDA};
    border-radius: 8px;
    padding: 7px 13px;
    color: {TEXTO_FRACO};
    font-size: 12px;
}}
QPushButton:hover {{
    border: 1px solid #3a3a40;
    color: {TEXTO};
    background-color: {PAINEL};
}}
QPushButton:pressed {{
    background-color: {BORDA};
}}
QPushButton:disabled {{
    color: {TEXTO_DESABILITADO};
    border: 1px solid {BORDA_SUTIL};
}}
QPushButton#enviar {{
    background-color: {VERDE};
    color: #07110b;
    font-weight: 600;
    border: 1px solid transparent;
    border-radius: 10px;
    padding: 10px 17px;
}}
QPushButton#enviar:hover {{
    background-color: #75e3a2;
}}
QPushButton#enviar:focus {{
    border-color: {AZUL};
}}
QPushButton#navButton {{
    background-color: transparent;
    border: 1px solid transparent;
    border-radius: 8px;
    padding: 10px 12px;
    color: {TEXTO_FRACO};
    font-size: 13px;
    text-align: left;
}}
QPushButton#navButton:hover {{
    background-color: {PAINEL_ELEVADO};
    color: {TEXTO};
}}
QPushButton#navButton:focus {{
    border-color: {AZUL};
}}
QPushButton#navButton:disabled {{
    color: {TEXTO_DESABILITADO};
}}
QPushButton#enviar:disabled {{
    background-color: {BORDA};
    color: {TEXTO_FRACO};
}}
QPushButton#modoAtivo {{
    background-color: {VERDE_SUAVE};
    border: 1px solid #285f3c;
    color: {VERDE};
    border-radius: 8px;
    padding: 9px 11px;
    font-size: 12px;
    font-weight: 600;
    text-align: left;
}}
QPushButton#modoAtivo:focus {{
    border-color: {AZUL};
}}
QPushButton#modoInativo {{
    background-color: transparent;
    border: 1px solid transparent;
    color: {TEXTO_FRACO};
    border-radius: 8px;
    padding: 9px 11px;
    font-size: 12px;
    text-align: left;
}}
QPushButton#modoInativo:hover {{
    background-color: {PAINEL_ELEVADO};
    border: 1px solid transparent;
    color: {TEXTO};
}}
QPushButton#modoInativo:focus {{
    border-color: {AZUL};
}}
QPlainTextEdit {{
    background-color: {FUNDO_CODIGO};
    border: 1px solid {BORDA_SUTIL};
    border-radius: 10px;
    padding: 12px;
    font-family: {FONTE_CODIGO};
    font-size: 13px;
}}
QPlainTextEdit#campoMensagem {{
    background-color: transparent;
    border: none;
    border-radius: 0px;
    padding: 10px 14px;
    font-family: "Segoe UI";
    font-size: 14px;
}}
QPlainTextEdit#campoMensagem:disabled {{
    color: {TEXTO_FRACO};
}}
QScrollBar:vertical {{
    background: transparent;
    width: 8px;
}}
QScrollBar::handle:vertical {{
    background: {BORDA};
    border-radius: 4px;
    min-height: 30px;
}}
QScrollBar::handle:vertical:hover {{
    background: #3a3a40;
}}
QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {{
    height: 0px;
}}
QTabWidget::pane {{
    background-color: {FUNDO};
    border: 1px solid {BORDA};
    border-radius: 8px;
    top: -1px;
}}
QTabBar::tab {{
    background-color: transparent;
    color: {TEXTO_FRACO};
    padding: 7px 14px;
    border: 1px solid transparent;
    border-bottom: none;
    border-top-left-radius: 8px;
    border-top-right-radius: 8px;
    font-size: 12px;
}}
QTabBar::tab:selected {{
    color: {TEXTO};
    background-color: {PAINEL};
    border: 1px solid {BORDA};
    border-bottom: none;
}}
QTabBar::tab:hover:!selected {{
    color: {TEXTO};
}}
"""

# ---------------------------------------------------------------------------
# Formatação das mensagens
# ---------------------------------------------------------------------------

# Captura o MARCADOR de linguagem separado do código - antes o grupo único
# só reconhecia "python"/"py" como marcador válido, e qualquer outro
# (html, css, javascript) não era removido: a palavra ficava GRUDADA na
# primeira linha do código exibido na tela. O mesmo bug já tinha sido
# corrigido uma vez em `memoria.py::extrair_codigo_com_linguagem` (para a
# EXECUÇÃO de código) - esta é a correção equivalente para a EXIBIÇÃO, que
# nunca tinha recebido o mesmo tratamento e vazava "html"/"css" toda vez que
# a Tartaruga mostrava um template ou geração nessas linguagens - a maioria
# das respostas de geração de código, agora que os 33 templates existem.
PADRAO_CODIGO = re.compile(r"```(\w*)\s*\n?(.*?)```", re.DOTALL)

# Caractere que pisca no fim do texto enquanto a resposta "está sendo escrita".
CURSOR = "▌"

# ---------------------------------------------------------------------------
# Ritmo da animação de digitação
#
# O ritmo é dado pela VELOCIDADE (caracteres por quadro), com um TETO de
# duração para as respostas longas. As duas alternativas puras são piores:
#
#   Só velocidade fixa  -> a resposta sobre lógica de programação, com 1225
#                          caracteres, levaria mais de 17 segundos.
#   Só duração fixa     -> "Salvei em workspace/codigo.py" demoraria o mesmo
#                          que um texto vinte vezes maior, o que soa artificial.
#
# Combinando os dois, respostas curtas aparecem rápido e as longas ficam
# limitadas ao teto. Para diminuir a velocidade, aumente os dois valores.
# ---------------------------------------------------------------------------
INTERVALO_QUADRO_MS = 28
CARACTERES_POR_QUADRO = 2
DURACAO_MAXIMA_MS = 3600


def segmentar(texto: str) -> list[tuple[str, str, str]]:
    """Separa a resposta em blocos de texto e blocos de código.

    Esta separação é o que torna a animação de digitação possível. Revelar o
    HTML caractere a caractere quebraria as tags no meio - `<di`, `<pre` -
    e o resultado na tela seria lixo. Segmentando primeiro, revelamos apenas
    o CONTEÚDO de cada bloco, e as tags são sempre escritas inteiras.

    Devolve uma lista de trios (tipo, conteúdo, linguagem). Para tipo
    "texto", linguagem é sempre "". Para tipo "codigo", é o marcador do
    bloco markdown (html/css/python/...), ou "" se o bloco não tiver um.
    """
    segmentos: list[tuple[str, str, str]] = []
    posicao = 0

    for achado in PADRAO_CODIGO.finditer(texto):
        antes = texto[posicao:achado.start()]
        if antes.strip():
            segmentos.append(("texto", antes.strip(), ""))
        marcador = achado.group(1).strip().lower()
        segmentos.append(("codigo", achado.group(2).rstrip(), marcador))
        posicao = achado.end()

    restante = texto[posicao:]
    if restante.strip():
        segmentos.append(("texto", restante.strip(), ""))

    return segmentos


# Ênfase em markdown dentro do texto: **negrito** e `código`.
PADRAO_NEGRITO = re.compile(r"\*\*(.+?)\*\*", re.DOTALL)
PADRAO_CODIGO_INLINE = re.compile(r"`([^`\n]+?)`")


def _paragrafo(texto: str) -> str:
    """Escapa o texto, aplica ênfase e preserva as quebras de linha.

    A ordem é obrigatória: escapamos PRIMEIRO e só então inserimos as tags
    de formatação. Fazer o contrário permitiria que um texto com `<` gerasse
    HTML válido a partir do conteúdo - exatamente a brecha que o escape
    existe para fechar.

    O `_limpar_marcacao_aberta` no fim existe por causa da animação: enquanto
    o texto é revelado caractere a caractere, um `**` fica sem o par por
    alguns quadros e apareceria cru na tela.
    """
    escapado = html.escape(texto)
    escapado = PADRAO_NEGRITO.sub(r"<b>\1</b>", escapado)
    escapado = PADRAO_CODIGO_INLINE.sub(
        f'<code style="background-color:{FUNDO_CODIGO}; font-family:{FONTE_CODIGO};'
        r' font-size:12px;">\1</code>',
        escapado,
    )
    escapado = _limpar_marcacao_aberta(escapado)
    return f'<div style="margin-top:4px; margin-bottom:4px;">{escapado.replace(chr(10), "<br>")}</div>'


def _limpar_marcacao_aberta(texto: str) -> str:
    """Remove marcações de ênfase que ficaram sem o par de fechamento."""
    return texto.replace("**", "").replace("`", "")


def _bloco_codigo(codigo: str, linguagem: str = "") -> str:
    """Caixa de código com fundo escuro, fonte monoespaçada e um rótulo
    discreto da linguagem no topo.
    """
    escapado = html.escape(codigo)
    rotulo = (
        f'<div style="color:{TEXTO_FRACO}; font-size:11px; font-family:{FONTE_CODIGO};'
        f' padding-bottom:6px; text-transform:uppercase; letter-spacing:0.5px;">'
        f'{html.escape(linguagem)}</div>'
        if linguagem else ""
    )
    return (
        f'<div style="background-color:{FUNDO_CODIGO}; border:1px solid {BORDA_SUTIL};'
        f' border-radius:10px; padding:12px 14px; margin-top:8px; margin-bottom:8px;">'
        f'{rotulo}'
        f'<pre style="margin:0; font-family:{FONTE_CODIGO}; font-size:13px;'
        f' color:{TEXTO}; white-space:pre-wrap;">{escapado}</pre></div>'
    )


def segmentos_para_html(
    segmentos: list[tuple[str, str, str]],
    revelado: int,
    com_cursor: bool = False,
) -> str:
    """Monta o HTML mostrando apenas os primeiros `revelado` caracteres.

    Percorre os segmentos gastando o "orçamento" de caracteres revelados.
    Segmentos já ultrapassados aparecem inteiros; o segmento atual aparece
    cortado; os seguintes ainda não aparecem.

    Todo conteúdo passa por `html.escape`. Sem isso, um código contendo `<`
    ou `&` corromperia a formatação da página.
    """
    partes: list[str] = []
    restante = revelado

    for tipo, conteudo, linguagem in segmentos:
        if restante <= 0:
            break

        trecho = conteudo[:restante]
        restante -= len(trecho)

        # O cursor só entra no último bloco visível, e só enquanto ainda
        # falta texto por revelar.
        incompleto = restante <= 0 and len(trecho) < len(conteudo)
        if com_cursor and incompleto:
            trecho += CURSOR

        partes.append(
            _paragrafo(trecho) if tipo == "texto" else _bloco_codigo(trecho, linguagem)
        )

    return "".join(partes)


def _cor_qt(hexadecimal: str) -> QColor:
    """Converte um hex '#rrggbb' num QColor, para colorir itens de lista."""
    return QColor(hexadecimal)


def texto_para_html(texto: str) -> str:
    """Converte a resposta inteira em HTML, sem animação."""
    segmentos = segmentar(texto)
    total = sum(len(conteudo) for _, conteudo, _ in segmentos)
    return segmentos_para_html(segmentos, total)


# ---------------------------------------------------------------------------
# Execução em segundo plano
# ---------------------------------------------------------------------------

class Trabalhador(QThread):
    """Roda uma função pesada fora da thread da interface.

    Sem isto, a janela congelaria durante uma busca na web (que depende da
    rede) ou durante a execução de um código que leve os 5 segundos do
    timeout. O Windows chegaria a marcar o programa como "não respondendo".
    """

    concluido = pyqtSignal(object)
    falhou = pyqtSignal(str)

    def __init__(self, funcao) -> None:
        super().__init__()
        self._funcao = funcao

    def run(self) -> None:
        try:
            self.concluido.emit(self._funcao())
        except Exception as erro:
            self.falhou.emit(f"{type(erro).__name__}: {erro}")


# ---------------------------------------------------------------------------
# Diálogos
# ---------------------------------------------------------------------------

class DialogoCodigo(QDialog):
    """Caixa para colar código de várias linhas."""

    def __init__(self, pai: QWidget | None = None) -> None:
        super().__init__(pai)
        self.setWindowTitle("Colar código")
        self.setMinimumSize(560, 340)
        self.setStyleSheet(ESTILO)

        layout = QVBoxLayout(self)
        layout.setSpacing(12)

        instrucao = QLabel("Cole o código Python abaixo:")
        instrucao.setStyleSheet(f"color:{TEXTO_FRACO};")
        layout.addWidget(instrucao)

        self.editor = QPlainTextEdit()
        self.editor.setPlaceholderText("print('olá mundo')")
        layout.addWidget(self.editor)

        botoes = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel
        )
        botoes.button(QDialogButtonBox.StandardButton.Ok).setText("Guardar")
        botoes.button(QDialogButtonBox.StandardButton.Cancel).setText("Cancelar")
        botoes.accepted.connect(self.accept)
        botoes.rejected.connect(self.reject)
        layout.addWidget(botoes)

    def codigo(self) -> str:
        return self.editor.toPlainText().strip()


class DialogoConfirmarExecucao(QDialog):
    """Mostra o código e pede autorização antes de executar.

    Esta é a principal proteção do projeto: nenhum código roda sem que a
    pessoa veja exatamente o que vai ser executado. O botão de cancelar é o
    padrão, então um Enter distraído não executa nada.
    """

    def __init__(self, codigo: str, pai: QWidget | None = None) -> None:
        super().__init__(pai)
        self.setWindowTitle("Confirmar execução")
        self.setMinimumSize(560, 320)
        self.setStyleSheet(ESTILO)

        layout = QVBoxLayout(self)
        layout.setSpacing(12)

        aviso = QLabel("Este código será executado no seu computador:")
        aviso.setStyleSheet(f"color:{AMARELO}; font-weight:600;")
        layout.addWidget(aviso)

        visor = QPlainTextEdit()
        visor.setPlainText(codigo)
        visor.setReadOnly(True)
        layout.addWidget(visor)

        detalhe = QLabel("Processo separado, com limite de 5 segundos.")
        detalhe.setStyleSheet(f"color:{TEXTO_FRACO}; font-size:12px;")
        layout.addWidget(detalhe)

        botoes = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel
        )
        botoes.button(QDialogButtonBox.StandardButton.Ok).setText("Executar")
        botoes.button(QDialogButtonBox.StandardButton.Cancel).setText("Cancelar")
        # O foco começa em Cancelar: a ação destrutiva nunca é a padrão.
        botoes.button(QDialogButtonBox.StandardButton.Cancel).setDefault(True)
        botoes.accepted.connect(self.accept)
        botoes.rejected.connect(self.reject)
        layout.addWidget(botoes)


class DialogoVerCodigo(QDialog):
    """Mostra um código já listado na aba Execuções (somente leitura)."""

    def __init__(self, codigo: str, pai: QWidget | None = None) -> None:
        super().__init__(pai)
        self.setWindowTitle("Código")
        self.setMinimumSize(560, 340)
        self.setStyleSheet(ESTILO)

        layout = QVBoxLayout(self)
        visor = QPlainTextEdit()
        visor.setPlainText(codigo)
        visor.setReadOnly(True)
        layout.addWidget(visor)

        botoes = QDialogButtonBox(QDialogButtonBox.StandardButton.Close)
        botoes.button(QDialogButtonBox.StandardButton.Close).setText("Fechar")
        botoes.rejected.connect(self.reject)
        layout.addWidget(botoes)


class DialogoHistorico(QDialog):
    """Navega o histórico de conversas salvo — todos os dias, com busca.

    Diferente do que "mostra o histórico" faz no chat (que só recapitula a
    SESSÃO atual, em texto corrido), este diálogo enxerga TODOS os dias já
    salvos em `historico/*.json` e permite buscar uma palavra em todos eles
    de uma vez — útil para achar "aquela explicação de closures de semana
    passada" sem rolar a conversa inteira.
    """

    def __init__(self, memoria, pai: QWidget | None = None) -> None:
        super().__init__(pai)
        self.memoria = memoria
        self.setWindowTitle("Histórico de conversas")
        self.setMinimumSize(720, 520)
        self.setStyleSheet(ESTILO)

        layout = QVBoxLayout(self)
        layout.setSpacing(10)

        linha_busca = QHBoxLayout()
        self.campo_busca = QLineEdit()
        self.campo_busca.setPlaceholderText("Buscar em todo o histórico...")
        self.campo_busca.returnPressed.connect(self._buscar)
        linha_busca.addWidget(self.campo_busca)
        botao_buscar = QPushButton("Buscar")
        botao_buscar.clicked.connect(self._buscar)
        linha_busca.addWidget(botao_buscar)
        layout.addLayout(linha_busca)

        corpo = QHBoxLayout()
        corpo.setSpacing(10)

        coluna_dias = QVBoxLayout()
        rotulo_dias = QLabel("Dias salvos")
        rotulo_dias.setStyleSheet(f"color:{TEXTO_FRACO}; font-size:11px;")
        coluna_dias.addWidget(rotulo_dias)
        self.lista_dias = QListWidget()
        self.lista_dias.setMaximumWidth(180)
        self.lista_dias.itemClicked.connect(self._abrir_dia)
        coluna_dias.addWidget(self.lista_dias)
        corpo.addLayout(coluna_dias)

        self.visor = QTextBrowser()
        corpo.addWidget(self.visor, stretch=1)

        layout.addLayout(corpo, stretch=1)

        self._carregar_dias()

    def _carregar_dias(self) -> None:
        dias = self.memoria.listar_dias()
        if not dias:
            self.visor.setHtml(
                f'<div style="color:{TEXTO_FRACO};">Nenhuma conversa salva ainda.</div>'
            )
            return
        for caminho in dias:
            item = QListWidgetItem(caminho.stem.replace("conversa_", ""))
            item.setData(Qt.ItemDataRole.UserRole, caminho)
            self.lista_dias.addItem(item)
        # Abre o dia mais recente de cara, para não começar numa tela vazia.
        self.lista_dias.setCurrentRow(0)
        self._abrir_dia(self.lista_dias.item(0))

    def _abrir_dia(self, item: QListWidgetItem) -> None:
        caminho = item.data(Qt.ItemDataRole.UserRole)
        turnos = self.memoria.carregar_dia(caminho)
        self._exibir_turnos(turnos, titulo=f"Conversa de {item.text()}")

    def _buscar(self) -> None:
        termo = self.campo_busca.text().strip()
        if not termo:
            return
        resultados = self.memoria.buscar(termo)
        if not resultados:
            self.visor.setHtml(
                f'<div style="color:{TEXTO_FRACO};">Nada encontrado para '
                f'"{html.escape(termo)}".</div>'
            )
            return

        partes = [
            f'<div style="color:{TEXTO_FRACO}; margin-bottom:10px;">'
            f'{len(resultados)} resultado(s) para "{html.escape(termo)}":</div>'
        ]
        for dia, turno in resultados:
            cor = AZUL if turno.papel == "usuario" else VERDE
            nome = "Você" if turno.papel == "usuario" else "Tartaruga"
            trecho = turno.texto.replace("\n", " ")
            if len(trecho) > 160:
                trecho = trecho[:160].rstrip() + "..."
            partes.append(
                f'<div style="margin-bottom:10px;">'
                f'<span style="color:{TEXTO_FRACO}; font-size:11px;">{dia}</span> · '
                f'<span style="color:{cor}; font-weight:600;">{nome}</span><br>'
                f'{html.escape(trecho)}</div>'
            )
        self.visor.setHtml("".join(partes))

    def _exibir_turnos(self, turnos, titulo: str) -> None:
        if not turnos:
            self.visor.setHtml(
                f'<div style="color:{TEXTO_FRACO};">Conversa vazia.</div>'
            )
            return

        partes = [f'<div style="color:{TEXTO_FRACO}; margin-bottom:10px;">{titulo}</div>']
        for turno in turnos:
            cor = AZUL if turno.papel == "usuario" else VERDE
            nome = "Você" if turno.papel == "usuario" else "Tartaruga"
            hora = turno.hora[11:16] if len(turno.hora) >= 16 else ""
            partes.append(
                f'<div style="margin-bottom:10px;">'
                f'<span style="color:{TEXTO_FRACO}; font-size:11px;">[{hora}]</span> '
                f'<span style="color:{cor}; font-weight:600;">{nome}</span>'
                f'{texto_para_html(turno.texto)}</div>'
            )
        self.visor.setHtml("".join(partes))


# ---------------------------------------------------------------------------
# Seção recolhível da barra lateral
# ---------------------------------------------------------------------------

class SecaoRecolhivel(QWidget):
    """Cabeçalho clicável (nome + seta) que mostra/esconde um bloco de ações abaixo.

    Recolher só oculta (`setVisible`); os widgets do conteúdo nunca são removidos nem recriados, então
    reabrir sempre devolve exatamente o que estava lá - nenhuma função é perdida ou precisa ser reconstruída.
    Começa sempre ABERTA (nada fica escondido por padrão) e o estado vale só para esta sessão da janela -
    não é salvo em disco, para não haver uma seção "lembrada como fechada" de um jeito confuso na próxima vez.
    """

    def __init__(self, titulo: str, conteudo: QWidget, pai: QWidget | None = None) -> None:
        super().__init__(pai)
        self._titulo = titulo

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(4)

        self.botao_cabecalho = QPushButton()
        self.botao_cabecalho.setObjectName("secaoCabecalho")
        self.botao_cabecalho.setCursor(Qt.CursorShape.PointingHandCursor)
        self.botao_cabecalho.setCheckable(True)
        self.botao_cabecalho.setChecked(True)
        self.botao_cabecalho.clicked.connect(self._alternar)
        layout.addWidget(self.botao_cabecalho)

        self.conteudo = conteudo
        layout.addWidget(self.conteudo)

        self._atualizar()

    def _alternar(self) -> None:
        self.conteudo.setVisible(self.botao_cabecalho.isChecked())
        self._atualizar()

    def _atualizar(self) -> None:
        aberto = self.botao_cabecalho.isChecked()
        seta = "▾" if aberto else "▸"
        # QPushButton trata "&" como marcador de atalho (some da tela); "&&" é como se escreve um "&" literal.
        titulo_exibido = self._titulo.replace("&", "&&")
        self.botao_cabecalho.setText(f"{seta}  {titulo_exibido}")
        estado = "recolher" if aberto else "expandir"
        self.botao_cabecalho.setAccessibleName(f"Seção {self._titulo}, clique para {estado}")


ALTURA_MAXIMA_CAMPO = 120

# Preenchimento vertical de QPlainTextEdit#campoMensagem no QSS
# ("padding: 10px 14px" = 10px em cima + 10px embaixo) mais uma folga de
# segurança deliberada. O Qt não expõe o padding do QSS de volta para o
# código Python - os dois valores precisam ficar sincronizados manualmente
# se o QSS mudar.
#
# ACHADO (teste no Windows real): a versão anterior somava uma
# margem fixa de 16px - menor que o padding real (20px) e sem folga nenhuma -
# e o texto saía cortado/apertado, sobretudo com a escala de fonte do
# Windows. A folga aqui soma-se a uma altura de linha tirada da FONTE REAL do
# campo em tempo de execução (`blockBoundingRect`, em `_ajustar_altura`), não
# a um deslocamento fixo "no olho": continua certa se a fonte, o tamanho ou a
# escala do Windows mudarem, porque o termo que varia é medido, não chutado.
PADDING_VERTICAL_CAMPO = 10 + 10
FOLGA_SEGURANCA_CAMPO = 8

# Chão de segurança absoluto - a altura real vem de `blockBoundingRect` e é
# sempre maior que isto; existe só para nunca deixar o campo com altura
# zero/negativa se alguma métrica de fonte vier degenerada.
ALTURA_MINIMA_ABSOLUTA_CAMPO = 24

# Tamanho fixo (em pixels) do canvas onde cada ícone Unicode dos botões da
# lateral é redesenhado - ver `JanelaPrincipal._icone_botao`.
TAMANHO_ICONE_BOTAO = 18


class CampoMensagem(QPlainTextEdit):
    """Campo de mensagem: Enter envia, Shift+Enter quebra linha.

    Antes disso era um QLineEdit (uma linha só). Cresce com o conteúdo até um
    teto e, a partir daí, rola em vez de continuar crescendo - importante na
    janela mínima (920x620), onde um campo sem teto empurraria a conversa
    inteira para fora da tela.
    """

    enviar_solicitado = pyqtSignal()

    def __init__(self, pai: QWidget | None = None) -> None:
        super().__init__(pai)
        self.setObjectName("campoMensagem")
        self.setTabChangesFocus(True)
        self.setLineWrapMode(QPlainTextEdit.LineWrapMode.WidgetWidth)
        self.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded)
        self.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self._compondo_ime = False
        self.textChanged.connect(self._ajustar_altura)
        self._ajustar_altura()

    def inputMethodEvent(self, evento) -> None:
        # Enquanto um editor de método de entrada (IME) está compondo (ex.:
        # conversão de pinyin/kana), o Enter confirma a composição - não deve
        # também disparar o envio da mensagem. `preeditString()` não fica
        # vazio só durante essa composição.
        self._compondo_ime = bool(evento.preeditString())
        super().inputMethodEvent(evento)

    def keyPressEvent(self, evento) -> None:
        eh_enter = evento.key() in (Qt.Key.Key_Return, Qt.Key.Key_Enter)
        if eh_enter and not self._compondo_ime:
            if evento.modifiers() & Qt.KeyboardModifier.ShiftModifier:
                super().keyPressEvent(evento)  # deixa o Qt inserir a quebra de linha
            else:
                self.enviar_solicitado.emit()
            return
        super().keyPressEvent(evento)

    def focusInEvent(self, evento) -> None:
        super().focusInEvent(evento)
        self._marcar_composer_com_foco(True)

    def focusOutEvent(self, evento) -> None:
        super().focusOutEvent(evento)
        self._marcar_composer_com_foco(False)

    def _marcar_composer_com_foco(self, com_foco: bool) -> None:
        """Acende/apaga a borda azul do frame `#composer` (o pai deste campo).

        Uma borda direto no campo ficaria colada, em ângulo reto, dentro do
        cantos ARREDONDADOS do frame que já o envolve - por isso é o frame
        pai que ganha a borda, não o campo. QSS não tem um `:focus-within`
        (não existe nesse subconjunto do Qt), então o aviso é manual: uma
        propriedade dinâmica + `unpolish/polish` para o estilo ser
        reavaliado - o mesmo padrão já usado em `_atualizar_botoes_modo`
        para a troca de objectName dos pills de modo.
        """
        pai = self.parentWidget()
        if pai is None:
            return
        pai.setProperty("comFoco", com_foco)
        pai.style().unpolish(pai)
        pai.style().polish(pai)

    def _ajustar_altura(self) -> None:
        # `document().size().height()` NÃO é pixels aqui - o layout interno do
        # QPlainTextEdit (QPlainTextDocumentLayout) devolve só a contagem de
        # blocos nesse campo (1 bloco -> 1.0, 20 blocos -> 20.0), sem refletir
        # a altura real de cada linha. `blockBoundingRect` é que dá pixels de
        # verdade, e é o que soma corretamente linhas quebradas por largura.
        #
        # `frameWidth()` NÃO entra na conta: ele varia sozinho conforme a
        # barra de rolagem aparece/some (achado ao reproduzir - o mesmo campo,
        # sem nenhuma borda visível no QSS, reportou frameWidth 1 e depois 14
        # depois de UMA vez precisar rolar, e não voltou), o que fazia o campo
        # não encolher de volta ao mínimo depois de esvaziado. Uma constante
        # que reflete o padding real do QSS, mais uma folga de segurança
        # (`PADDING_VERTICAL_CAMPO` + `FOLGA_SEGURANCA_CAMPO`), é estável e
        # resolve isso sem depender de frameWidth().
        altura_texto = 0.0
        bloco = self.document().begin()
        while bloco.isValid():
            altura_texto += self.blockBoundingRect(bloco).height()
            bloco = bloco.next()
        altura = int(altura_texto) + PADDING_VERTICAL_CAMPO + FOLGA_SEGURANCA_CAMPO
        altura = max(ALTURA_MINIMA_ABSOLUTA_CAMPO, min(altura, ALTURA_MAXIMA_CAMPO))
        self.setFixedHeight(altura)


# ---------------------------------------------------------------------------
# Janela principal
# ---------------------------------------------------------------------------

class JanelaPrincipal(QWidget):
    """A janela do assistente."""

    def __init__(self, assistente: Tartaruga) -> None:
        super().__init__()
        self.assistente = assistente
        self.trabalhador: Trabalhador | None = None

        # Mensagens já exibidas, em HTML. O visor é remontado a partir desta
        # lista sempre que algo novo chega - ver `_acrescentar`.
        self._mensagens: list[str] = []

        # Estado da animação de digitação (ver `_animar_resposta`).
        self._temporizador = QTimer(self)
        self._temporizador.timeout.connect(self._quadro_animacao)
        self._anim_etiqueta = ""
        self._anim_segmentos: list[tuple[str, str, str]] = []
        self._anim_total = 0
        self._anim_revelado = 0
        self._anim_passo = 1
        self._anim_ao_terminar = None

        # Posição da mensagem animada dentro de `_mensagens`. Guardamos o
        # índice, e não usamos "a última", porque um aviso pode ser exibido
        # enquanto a resposta ainda está sendo escrita - e aí o quadro
        # seguinte sobrescreveria o aviso em vez da própria resposta.
        self._anim_indice = -1

        # Registro de execuções da sessão, para o painel lateral.
        self._execucoes: list[dict] = []

        # Texto CRU (não o HTML renderizado - preserva quebras de linha de
        # verdade) da última resposta completa da Tartaruga, para "Copiar
        # última resposta". `None` até a primeira resposta existir.
        self._ultima_resposta_tartaruga: str | None = None

        self.setWindowTitle("Tartaruga — Assistente de programação")
        self.setMinimumSize(920, 620)
        self.resize(1120, 760)
        self.setStyleSheet(ESTILO)
        self._definir_icone()

        self._montar_layout()
        self._mostrar_boas_vindas()

        # Ctrl+Shift+C, não Ctrl+C: esse já é a cópia normal de texto
        # selecionado nos campos (QLineEdit/QPlainTextEdit/QTextBrowser) -
        # um atalho global não pode roubar esse comportamento nativo.
        self._atalho_copiar_resposta = QShortcut(QKeySequence("Ctrl+Shift+C"), self)
        self._atalho_copiar_resposta.activated.connect(self.copiar_ultima_resposta)

    # -- construção da tela ------------------------------------------------

    def _definir_icone(self) -> None:
        caminho = recurso("Logo", "logo_tartaruga.png")
        if caminho.exists():
            self.setWindowIcon(QIcon(str(caminho)))

    def _montar_layout(self) -> None:
        raiz = QHBoxLayout(self)
        raiz.setContentsMargins(0, 0, 0, 0)
        raiz.setSpacing(0)

        self.barra_lateral = self._montar_barra_lateral()
        raiz.addWidget(self.barra_lateral)

        principal = QFrame()
        principal.setObjectName("areaPrincipal")
        layout = QVBoxLayout(principal)
        layout.setContentsMargins(28, 22, 28, 22)
        layout.setSpacing(14)
        layout.addLayout(self._montar_cabecalho())

        # QSplitter em vez de layout fixo: o painel de execução divide o
        # espaço com a conversa quando visível, e o usuário pode arrastar a
        # divisória. Ele começa OCULTO (ver `_montar_painel_execucao`) porque
        # a maioria das sessões não vai rodar código o tempo todo - mostrar
        # um painel vazio por padrão seria ruído visual sem propósito.
        self.divisor = QSplitter(Qt.Orientation.Horizontal)
        self.divisor.setChildrenCollapsible(False)

        self.conversa = QTextBrowser()
        self.conversa.setAccessibleName("Mensagens da conversa")
        self.conversa.setAccessibleDescription("Histórico de mensagens entre você e a Tartaruga")
        self.conversa.setOpenExternalLinks(True)
        self.divisor.addWidget(self.conversa)

        self.painel_execucao = self._montar_painel_execucao()
        self.divisor.addWidget(self.painel_execucao)

        # `setSizes()` sozinho não é confiável aqui: chamado antes do widget
        # estar de fato exibido, o Qt recalcula os tamanhos no primeiro
        # evento de show/resize a partir do `sizeHint()` dos filhos e
        # DESCARTA o valor pedido — um teste real mostrou o painel abrindo
        # maior que a conversa, o oposto do pretendido. `setVisible(False)`
        # é a forma robusta de começar fechado: um widget invisível não
        # ocupa espaço no splitter, ponto final, sem depender de timing.
        self.painel_execucao.setVisible(False)

        layout.addWidget(self.divisor, stretch=1)

        self.rotulo_estado = QLabel("")
        self.rotulo_estado.setStyleSheet(f"color:{TEXTO_FRACO}; font-size:12px;")
        linha_estado = QHBoxLayout()
        linha_estado.addWidget(self.rotulo_estado, stretch=1)
        # Só aparece quando a última resposta trouxe HTML/CSS/JS gerado
        # (dado estruturado em `Resposta.visualizacao`, não scraping do balão).
        self._visualizacao_atual = None
        self.botao_visualizar = QPushButton("▶  Visualizar")
        self.botao_visualizar.setAccessibleName("Visualizar o código gerado no painel Preview")
        self.botao_visualizar.clicked.connect(self.visualizar_ultima_geracao)
        self.botao_visualizar.setVisible(False)
        linha_estado.addWidget(self.botao_visualizar)
        layout.addLayout(linha_estado)

        layout.addLayout(self._montar_entrada())
        raiz.addWidget(principal, stretch=1)

    def _montar_barra_lateral(self) -> QFrame:
        """Agrupa identidade, ferramentas e modelo sem disputar espaço com o chat."""
        lateral = QFrame()
        lateral.setObjectName("barraLateral")
        lateral.setFixedWidth(232)
        layout = QVBoxLayout(lateral)
        layout.setContentsMargins(18, 22, 18, 20)
        layout.setSpacing(8)

        marca = QHBoxLayout()
        marca.setSpacing(10)
        caminho_logo = recurso("Logo", "logo_tartaruga.png")
        if caminho_logo.exists():
            imagem = QLabel()
            imagem.setFixedSize(38, 38)
            imagem.setPixmap(QPixmap(str(caminho_logo)).scaled(
                38, 38, Qt.AspectRatioMode.KeepAspectRatio,
                Qt.TransformationMode.SmoothTransformation,
            ))
            marca.addWidget(imagem)
        nome = QLabel("Tartaruga")
        nome.setFont(QFont("Segoe UI", 15, QFont.Weight.Bold))
        nome.setStyleSheet(f"color:{TEXTO};")
        marca.addWidget(nome)
        marca.addStretch()
        layout.addLayout(marca)

        descricao = QLabel("Assistente local de programação")
        descricao.setStyleSheet(f"color:{TEXTO_FRACO}; font-size:11px;")
        layout.addWidget(descricao)
        layout.addSpacing(14)

        conteudo_acoes = QWidget()
        acoes = QVBoxLayout(conteudo_acoes)
        acoes.setContentsMargins(0, 0, 4, 0)
        acoes.setSpacing(6)
        acoes.addWidget(self._secao_ferramentas())
        acoes.addWidget(self._secao_sessao_e_dados())
        acoes.addWidget(self._secao_briefing())
        acoes.addStretch()
        rolagem = QScrollArea()
        rolagem.setWidgetResizable(True)
        rolagem.setFrameShape(QFrame.Shape.NoFrame)
        rolagem.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        rolagem.setWidget(conteudo_acoes)
        rolagem.setAccessibleName("Ferramentas, sessão e briefing")
        layout.addWidget(rolagem, stretch=1)
        layout.addWidget(self._rotulo_secao("MODELO DE RESPOSTA"))
        layout.addLayout(self._montar_seletor_modo())
        layout.addSpacing(14)

        privacidade = QLabel("● Processamento local\nSeus chats ficam neste computador")
        privacidade.setWordWrap(True)
        privacidade.setStyleSheet(f"color:{TEXTO_FRACO}; font-size:10px; line-height:1.4;")
        layout.addWidget(privacidade)
        return lateral

    @staticmethod
    def _rotulo_secao(texto: str) -> QLabel:
        rotulo = QLabel(texto)
        rotulo.setObjectName("secaoLateral")
        return rotulo

    def _montar_painel_execucao(self) -> QWidget:
        """Painel lateral com abas: histórico de execuções e preview ao vivo.

        Separado da conversa de propósito - a conversa é sequencial e mistura
        explicações com execuções/visualizações; este painel reúne isso à
        parte, fácil de revisar sem rolar por trás de texto explicativo.

        As duas abas dividem o mesmo widget em vez de competir por um
        segundo QSplitter.
        """
        painel = QWidget()
        painel.setMinimumWidth(280)
        layout = QVBoxLayout(painel)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        self.abas_execucao_preview = QTabWidget()
        self.abas_execucao_preview.addTab(self._montar_aba_execucoes(), "Execuções")
        self._indice_aba_preview = self.abas_execucao_preview.addTab(
            self._montar_aba_preview_inicial(), "Preview"
        )
        self.abas_execucao_preview.currentChanged.connect(self._ao_trocar_aba_painel)
        layout.addWidget(self.abas_execucao_preview, stretch=1)

        return painel

    def _montar_aba_execucoes(self) -> QWidget:
        """Conteúdo da aba "Execuções": um registro de todo código já
        executado na sessão (mesmo conteúdo de antes da divisão em abas)."""
        aba = QWidget()
        layout = QVBoxLayout(aba)
        layout.setContentsMargins(10, 10, 10, 10)
        layout.setSpacing(8)

        self.lista_execucoes = QListWidget()
        self.lista_execucoes.setWordWrap(True)
        self.lista_execucoes.setStyleSheet(
            f"QListWidget {{ background-color:{PAINEL}; border:1px solid {BORDA};"
            f" border-radius:8px; }}"
            f"QListWidget::item {{ padding:8px; border-bottom:1px solid {BORDA}; }}"
        )
        self.lista_execucoes.itemActivated.connect(self._abrir_codigo_do_item)
        layout.addWidget(self.lista_execucoes, stretch=1)

        rotulo_vazio = QLabel("Nenhum código gerado ou executado ainda nesta sessão.")
        rotulo_vazio.setWordWrap(True)
        rotulo_vazio.setStyleSheet(f"color:{TEXTO_FRACO}; font-size:12px;")
        rotulo_vazio.setVisible(True)
        self._rotulo_execucoes_vazio = rotulo_vazio
        layout.addWidget(rotulo_vazio)

        return aba

    def _montar_aba_preview_inicial(self) -> QWidget:
        """Conteúdo inicial da aba "Preview": só um texto de estado.

        A QWebEngineView de verdade só é criada na primeira vez que o
        usuário abre esta aba - ver `_ao_trocar_aba_painel`. Importar
        PyQt6.QtWebEngineWidgets custa uma DLL pesada (Chromium embutido);
        quem nunca abre esta aba não deve pagar esse custo, mesmo com a
        dependência opcional instalada.
        """
        aba = QWidget()
        layout = QVBoxLayout(aba)
        layout.setContentsMargins(10, 10, 10, 10)
        layout.setSpacing(8)

        self._rotulo_preview_estado = QLabel(self._texto_estado_preview_inicial())
        self._rotulo_preview_estado.setWordWrap(True)
        self._rotulo_preview_estado.setStyleSheet(f"color:{TEXTO_FRACO}; font-size:12px;")
        layout.addWidget(self._rotulo_preview_estado)
        # Sem addStretch() aqui de propósito: se a view real for criada
        # depois (ver `_ao_trocar_aba_painel`), ela precisa ficar logo
        # abaixo do rótulo com stretch=1, e um stretch fixo já presente
        # entraria entre os dois.

        self._preview_view = None
        self._preview_carregado = False
        return aba

    @staticmethod
    def _texto_estado_preview_inicial() -> str:
        if preview.disponivel():
            return (
                "Nenhum código para visualizar ainda. Peça um trecho de "
                "HTML, CSS ou JavaScript na conversa - quando a Tartaruga "
                "responder, use a ação de visualizar para renderizar aqui."
            )
        return (
            "Preview ao vivo é um recurso opcional (requer PyQt6-WebEngine, "
            "não instalado neste build).\nInstale as dependências de "
            "requirements-preview.txt para ativá-lo."
        )

    def _ao_trocar_aba_painel(self, indice: int) -> None:
        """Cria a QWebEngineView de verdade só na primeira troca para a aba
        Preview (import tardio genuíno - ver `_montar_aba_preview_inicial`).
        """
        if indice == self._indice_aba_preview:
            self._garantir_view_preview()

    def _garantir_view_preview(self) -> bool:
        """Cria a view na primeira necessidade. Devolve se ela existe."""
        if not self._preview_carregado:
            self._preview_carregado = True
            if not preview.disponivel():
                return False  # o texto de estado já explica o motivo
            self._preview_view = preview.criar_view()
            aba = self.abas_execucao_preview.widget(self._indice_aba_preview)
            self._rotulo_preview_estado.setVisible(False)
            aba.layout().addWidget(self._preview_view, stretch=1)
        return self._preview_view is not None

    def visualizar_ultima_geracao(self) -> None:
        """Abre o painel na aba Preview e renderiza o último HTML/CSS/JS gerado."""
        if self._visualizacao_atual is None:
            return
        linguagem, codigo, padrao = self._visualizacao_atual
        if not self.painel_execucao.isVisible():
            self._toggle_painel_execucao()
        self.abas_execucao_preview.setCurrentIndex(self._indice_aba_preview)
        if not self._garantir_view_preview():
            return  # sem WebEngine: a aba já mostra como ativar
        try:
            documento = montar_documento(codigo, linguagem, padrao)
        except ValueError as erro:
            self.mostrar_aviso(f"Não consegui montar o preview: {erro}", VERMELHO)
            return
        if not preview.responde(self._preview_view):
            # Renderizador preso (ex.: loop infinito no código anterior):
            # descarta a view e cria outra - carregar um documento novo na
            # mesma view não recupera uma página travada.
            self._recriar_view_preview()
            self.mostrar_aviso("O preview anterior travou e foi reiniciado.", AMARELO)
        preview.renderizar(self._preview_view, documento)

    def _descartar_view_preview(self) -> None:
        """Destrói a view e volta ao estado de criação tardia."""
        if self._preview_view is None:
            return
        aba = self.abas_execucao_preview.widget(self._indice_aba_preview)
        aba.layout().removeWidget(self._preview_view)
        preview.descartar(self._preview_view)
        self._preview_view = None
        self._preview_carregado = False
        self._rotulo_preview_estado.setVisible(True)

    def _recriar_view_preview(self) -> None:
        aba = self.abas_execucao_preview.widget(self._indice_aba_preview)
        antiga = self._preview_view
        aba.layout().removeWidget(antiga)
        preview.descartar(antiga)
        self._preview_view = preview.criar_view()
        aba.layout().addWidget(self._preview_view, stretch=1)

    def _montar_cabecalho(self) -> QHBoxLayout:
        linha = QHBoxLayout()
        linha.setSpacing(12)

        textos = QVBoxLayout()
        textos.setSpacing(3)

        titulo = QLabel("Conversa")
        titulo.setFont(QFont("Segoe UI", 18, QFont.Weight.DemiBold))
        titulo.setStyleSheet(f"color:{TEXTO};")
        textos.addWidget(titulo)

        self.rotulo_contador_mensagens = QLabel(self._texto_contador_mensagens())
        self.rotulo_contador_mensagens.setStyleSheet(f"color:{TEXTO_FRACO}; font-size:12px;")
        textos.addWidget(self.rotulo_contador_mensagens)

        linha.addLayout(textos)
        linha.addStretch()
        return linha

    def _texto_contador_mensagens(self) -> str:
        """Quantas mensagens já foram trocadas NESTA conversa - dado que muda
        a cada envio, ao contrário de "tópicos locais"/"termos reconhecidos"
        (fixos, do aplicativo inteiro, e por isso pouco informativos aqui).

        Não repete o que já aparece na lateral (marca, modo ativo, ferramentas):
        é o único lugar da tela que mostra este número.
        """
        total = len(self.assistente.memoria)
        if total == 0:
            return "Nova conversa"
        if total == 1:
            return "1 mensagem nesta conversa"
        return f"{total} mensagens nesta conversa"

    def _atualizar_contador_mensagens(self) -> None:
        self.rotulo_contador_mensagens.setText(self._texto_contador_mensagens())

    @staticmethod
    def _icone_botao(glifo: str) -> QIcon:
        """Desenha um glifo Unicode centralizado num canvas de tamanho fixo.

        Os botões da lateral usam símbolos soltos ("＋", "▷", "◷", "⚙", "ⓘ"...)
        com larguras e alturas naturais bem diferentes entre si na fonte do
        sistema - colocá-los direto no texto do botão (como era antes)
        deixava cada um alinhado e espaçado de um jeito diferente, remendado
        à mão com espaços extras (o "?" e o "×" já precisavam de contagens de
        espaço diferentes para ficarem visualmente parecidos). Desenhando
        cada glifo centralizado num quadrado do MESMO tamanho, o alinhamento
        e o espaçamento com o texto passam a ser cuidados pelo próprio QStyle
        do Qt (ícone + texto de um QPushButton), de forma igual para todos.

        Não depende de uma fonte de ícones externa: usa `QApplication.font()`
        - a mesma fonte que o resto do aplicativo já usa - só redesenhada
        nesse tamanho fixo. Também não é uma imagem fixa: se o tamanho da
        fonte do app mudar (tela de Configurações), o próximo desenho já sai
        no tamanho novo, porque é gerado sob demanda, não guardado num
        arquivo.
        """
        tamanho = TAMANHO_ICONE_BOTAO
        fonte = QFont(QApplication.font())
        fonte.setPointSize(max(9, int(tamanho * 0.62)))

        def desenhar(cor: str) -> QPixmap:
            pixmap = QPixmap(tamanho, tamanho)
            pixmap.fill(Qt.GlobalColor.transparent)
            pintor = QPainter(pixmap)
            pintor.setRenderHint(QPainter.RenderHint.Antialiasing)
            pintor.setRenderHint(QPainter.RenderHint.TextAntialiasing)
            pintor.setFont(fonte)
            pintor.setPen(QColor(cor))
            pintor.drawText(pixmap.rect(), Qt.AlignmentFlag.AlignCenter, glifo)
            pintor.end()
            return pixmap

        icone = QIcon()
        icone.addPixmap(desenhar(TEXTO_FRACO), QIcon.Mode.Normal)
        icone.addPixmap(desenhar(TEXTO_DESABILITADO), QIcon.Mode.Disabled)
        return icone

    @staticmethod
    def _criar_botao(glifo: str | None, rotulo: str, acao) -> QPushButton:
        """Um botão de navegação isolado, no padrão usado pela lateral.

        Extraído de `_botoes()` (que só monta uma coluna deles) para que um
        botão que precisa de uma referência própria depois de criado - caso
        de "Copiar última resposta", habilitado/desabilitado dinamicamente -
        não precise duplicar essa configuração.
        """
        botao = QPushButton(rotulo)
        botao.setObjectName("navButton")
        botao.setCursor(Qt.CursorShape.PointingHandCursor)
        botao.setMinimumHeight(38)
        if glifo is not None:
            botao.setIcon(JanelaPrincipal._icone_botao(glifo))
            botao.setIconSize(QSize(TAMANHO_ICONE_BOTAO, TAMANHO_ICONE_BOTAO))
        botao.clicked.connect(acao)
        return botao

    @staticmethod
    def _botoes(especificacoes) -> QWidget:
        """Uma coluna de botões de navegação, pronta para entrar dentro de uma `SecaoRecolhivel`.

        Cada especificação é (glifo, rótulo, ação); `glifo` pode ser `None`
        para um botão só com texto (caso do briefing, que não tem ícone).
        """
        conteudo = QWidget()
        linha = QVBoxLayout(conteudo)
        linha.setContentsMargins(0, 0, 0, 0)
        linha.setSpacing(3)
        for glifo, rotulo, acao in especificacoes:
            linha.addWidget(JanelaPrincipal._criar_botao(glifo, rotulo, acao))
        return conteudo

    def _secao_ferramentas(self) -> SecaoRecolhivel:
        """As ações usadas com mais frequência durante a própria conversa."""
        conteudo = self._botoes((
            ("＋", "Colar código", self.abrir_dialogo_codigo),
            ("▷", "Execuções", self._toggle_painel_execucao),
            ("◷", "Histórico", self.abrir_dialogo_historico),
            ("?", "Ajuda", self.mostrar_ajuda),
            ("×", "Limpar conversa", self.limpar_conversa),
        ))
        self.botao_copiar_resposta = self._criar_botao(
            "⧉", "Copiar última resposta", self.copiar_ultima_resposta
        )
        self.botao_copiar_resposta.setEnabled(False)  # nada para copiar até a primeira resposta
        self.botao_copiar_resposta.setToolTip(
            "Copia a última resposta completa da Tartaruga (Ctrl+Shift+C)"
        )
        conteudo.layout().addWidget(self.botao_copiar_resposta)
        return SecaoRecolhivel("FERRAMENTAS", conteudo, self)

    def _secao_sessao_e_dados(self) -> SecaoRecolhivel:
        """Backup, preferências e gestão do que a Tartaruga aprendeu - consultadas com menos frequência."""
        conteudo = self._botoes((
            ("⇧", "Exportar dados", self.exportar_dados),
            ("⇩", "Importar dados", self.importar_dados),
            ("⚙", "Configurações", self.editar_configuracoes),
            ("ⓘ", "Diagnóstico", self.mostrar_diagnostico),
            ("▣", "Projetos", self.mostrar_projetos),
            ("!", "Resposta incorreta", self.registrar_resposta_incorreta),
            ("◆", "Conhecimento", self.gerenciar_conhecimento),
        ))
        return SecaoRecolhivel("SESSÃO & DADOS", conteudo, self)

    def _secao_briefing(self) -> SecaoRecolhivel:
        return SecaoRecolhivel("BRIEFING", self._montar_acoes_briefing(), self)

    def mostrar_diagnostico(self) -> None:
        QMessageBox.information(
            self, "Diagnóstico da Tartaruga",
            formatar_diagnostico(coletar_diagnostico(self.assistente)),
        )

    def mostrar_projetos(self) -> None:
        projetos = self.assistente.projetos.listar()
        if not projetos:
            QMessageBox.information(self, "Projetos", "Nenhum projeto de landing page criado.")
            return
        linhas = []
        for projeto in projetos:
            linhas.append(
                f"{projeto.nome}\nID: {projeto.id}\n"
                f"Arquivos: {', '.join(projeto.arquivos) or 'nenhum'}\n"
                f"Publicação: {projeto.publicacao.get('status', 'não publicada')}"
            )
        QMessageBox.information(self, "Projetos de landing page", "\n\n".join(linhas))

    def registrar_resposta_incorreta(self) -> None:
        usuario = next((t for t in reversed(self.assistente.memoria.turnos) if t.papel == "usuario"), None)
        tartaruga = next((t for t in reversed(self.assistente.memoria.turnos) if t.papel == "tartaruga"), None)
        if usuario is None or tartaruga is None:
            self.mostrar_aviso("Ainda não há uma resposta para avaliar.")
            return
        esperado, ok = QInputDialog.getItem(
            self, "Resposta incorreta", "O que você esperava?",
            ["explicação", "geração de código", "briefing", "execução", "arquivo", "pesquisa", "outra coisa"],
            0, False,
        )
        if ok:
            registrar_feedback(usuario.texto, tartaruga.intencao or "desconhecido", esperado)
            self.mostrar_aviso("Falha registrada localmente com dados pessoais ocultados.")

    def gerenciar_conhecimento(self) -> None:
        fontes = self.assistente.aprendiz.listar_fontes()
        if not fontes:
            QMessageBox.information(self, "Conhecimento aprendido", "A base aprendida está vazia.")
            return
        rotulos = [f"{f['titulo']} — {f['dominio']} ({f['data']})" for f in fontes]
        escolhido, ok = QInputDialog.getItem(self, "Conhecimento aprendido", "Entrada:", rotulos, 0, False)
        if not ok:
            return
        indice = rotulos.index(escolhido)
        fonte = fontes[indice]
        acao, ok = QInputDialog.getItem(
            self, "Gerenciar entrada", f"Fonte: {fonte['url']}\nAção:",
            ["Somente visualizar", "Marcar como incorreta", "Excluir"], 0, False,
        )
        if not ok or acao == "Somente visualizar":
            return
        if acao == "Marcar como incorreta":
            self.assistente.aprendiz.marcar_incorreta(fonte["id"])
            self.assistente.base.recarregar()
            self.mostrar_aviso("Entrada desativada para revisão.")
        elif QMessageBox.question(
            self, "Excluir conhecimento", "Excluir permanentemente esta entrada?",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No,
        ) == QMessageBox.StandardButton.Yes:
            self.assistente.aprendiz.remover(fonte["id"])
            self.assistente.base.recarregar()
            self.mostrar_aviso("Entrada excluída.")

    def editar_configuracoes(self) -> None:
        atual = Configuracoes.carregar()
        modos = list(self.assistente.MODOS)
        modo, ok = QInputDialog.getItem(
            self, "Configurações", "Modo inicial:", modos,
            modos.index(atual.modo_inicial), False,
        )
        if not ok:
            return
        fonte, ok = QInputDialog.getInt(
            self, "Configurações", "Tamanho da fonte:",
            atual.tamanho_fonte, 10, 24,
        )
        if not ok:
            return
        atual.modo_inicial = modo
        atual.tamanho_fonte = fonte
        atual.retomar_conversa = QMessageBox.question(
            self, "Configurações", "Retomar automaticamente a última conversa ao abrir?",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.Yes if atual.retomar_conversa else QMessageBox.StandardButton.No,
        ) == QMessageBox.StandardButton.Yes
        atual.semantica_ativa = QMessageBox.question(
            self, "Configurações", "Ativar compreensão semântica local quando disponível?",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.Yes if atual.semantica_ativa else QMessageBox.StandardButton.No,
        ) == QMessageBox.StandardButton.Yes
        atual.salvar()
        self.assistente.modo = modo
        self._atualizar_botoes_modo()
        QApplication.instance().setFont(QFont("Segoe UI", fonte))
        self.mostrar_aviso("Configurações salvas.")

    def _montar_acoes_briefing(self) -> QWidget:
        return self._botoes((
            (None, "Continuar", lambda: self.enviar_texto("retomar briefing")),
            (None, "Pausar", lambda: self.enviar_texto("pausar briefing")),
            (None, "Corrigir resposta", self.corrigir_briefing),
            (None, "Cancelar", lambda: self.enviar_texto("cancelar briefing")),
        ))

    def corrigir_briefing(self) -> None:
        opcoes = [rotulo for rotulo, _, _ in CAMPOS.values()]
        rotulo, ok = QInputDialog.getItem(self, "Corrigir briefing", "Campo:", opcoes, 0, False)
        if not ok:
            return
        valor, ok = QInputDialog.getText(self, "Corrigir briefing", "Novo valor:")
        if ok and valor.strip():
            self.enviar_texto(f"corrigir {rotulo} para {valor.strip()}")

    def exportar_dados(self) -> None:
        caminho, _ = QFileDialog.getSaveFileName(
            self, "Exportar dados", "backup-tartaruga.zip", "Backup Tartaruga (*.zip)"
        )
        if not caminho:
            return
        try:
            manifesto = exportar_backup(caminho)
            self.mostrar_aviso(f"Backup criado com {len(manifesto['itens'])} arquivos.")
        except (OSError, ValueError) as erro:
            self.mostrar_aviso(f"Não foi possível exportar: {erro}", VERMELHO)

    def importar_dados(self) -> None:
        caminho, _ = QFileDialog.getOpenFileName(
            self, "Importar dados", "", "Backup Tartaruga (*.zip)"
        )
        if not caminho:
            return
        if QMessageBox.question(
            self, "Importar dados", "Restaurar este backup? Arquivos com o mesmo nome serão substituídos.",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No,
        ) != QMessageBox.StandardButton.Yes:
            return
        try:
            resultado = restaurar_backup(caminho)
            self.mostrar_aviso(
                f"{resultado['itens']} arquivos restaurados. Reinicie a Tartaruga para recarregar todos os dados."
            )
        except (OSError, ValueError) as erro:
            self.mostrar_aviso(f"Backup recusado: {erro}", VERMELHO)

    def _montar_entrada(self) -> QVBoxLayout:
        """Barra inferior: campo de texto em cima, seletor de modo embaixo.

        Duas linhas, não uma - colocar os pills de modo na mesma linha do
        campo+botão disputaria espaço horizontal e ficaria apertado.
        """
        container = QVBoxLayout()
        container.setSpacing(7)

        composer = QFrame()
        composer.setObjectName("composer")
        linha_campo = QHBoxLayout(composer)
        linha_campo.setContentsMargins(5, 4, 5, 4)
        linha_campo.setSpacing(8)

        self.campo = CampoMensagem()
        self.campo.setPlaceholderText("Pergunte algo sobre programação...")
        self.campo.setAccessibleName("Mensagem")
        self.campo.setAccessibleDescription("Digite uma pergunta ou instrução para a Tartaruga")
        self.campo.enviar_solicitado.connect(self.enviar)
        linha_campo.addWidget(self.campo)

        self.botao_enviar = QPushButton("Enviar  →")
        self.botao_enviar.setAccessibleName("Enviar mensagem")
        self.botao_enviar.setObjectName("enviar")
        self.botao_enviar.clicked.connect(self.enviar)
        linha_campo.addWidget(self.botao_enviar, 0, Qt.AlignmentFlag.AlignBottom)

        container.addWidget(composer)
        dica = QLabel("Enter para enviar  ·  Shift+Enter para nova linha  ·  cole código pelo menu lateral")
        dica.setStyleSheet(f"color:{TEXTO_FRACO}; font-size:10px; padding-left:6px;")
        container.addWidget(dica)
        return container

    def _montar_seletor_modo(self) -> QVBoxLayout:
        """Pills para escolher QUEM responde: só a Tartaruga, só o modelo
        local, ou os dois juntos (padrão) - pedido explicitamente para
        comparação acadêmica ("o que minha base faz sozinha vs. o que o
        LLM faz sozinho vs. o híbrido").

        Não afeta ferramentas (executar código, arquivos, busca, histórico)
        nem conversa fixa - só como dúvidas de programação e pedidos de
        geração de código são respondidos. Ver `Tartaruga.MODOS` no núcleo.
        """
        linha = QVBoxLayout()
        linha.setSpacing(3)

        self.botoes_modo: dict[str, QPushButton] = {}
        for chave, rotulo_texto in (
            ("tartaruga", "Tartaruga"),
            ("hibrido", "Tartaruga + Phi-4-mini"),
            ("phi4mini", "Phi-4-mini"),
        ):
            botao = QPushButton(rotulo_texto)
            botao.setCheckable(True)
            botao.setCursor(Qt.CursorShape.PointingHandCursor)
            botao.setMinimumHeight(36)
            botao.clicked.connect(lambda _checked, c=chave: self._selecionar_modo(c))
            linha.addWidget(botao)
            self.botoes_modo[chave] = botao

        self._atualizar_botoes_modo()
        return linha

        return linha

    # -- exibição ----------------------------------------------------------

    def _acrescentar(self, html_conteudo: str) -> None:
        """Adiciona uma mensagem à conversa e rola até o fim.

        O documento inteiro é remontado a cada mensagem, em vez de usar
        `insertHtml`. Motivo: o Qt MESCLA no mesmo bloco de texto o HTML
        inserido em chamadas consecutivas, então as `<div>` não quebravam
        linha e o nome de quem falava aparecia grudado no fim da mensagem
        anterior ("...registradas.Você").

        Remontar custa mais que inserir, mas numa conversa de dezenas de
        mensagens a diferença é imperceptível - e a estrutura fica correta.
        """
        self._mensagens.append(html_conteudo)
        self._renderizar()
        self._atualizar_contador_mensagens()

    def _renderizar(self) -> None:
        """Escreve todas as mensagens no visor, mantendo a rolagem no lugar.

        A rolagem só desce automaticamente se o usuário já estava no fim. Se
        ele subiu para reler algo enquanto a resposta é digitada, puxá-lo de
        volta para baixo a cada quadro seria irritante.
        """
        barra = self.conversa.verticalScrollBar()
        estava_no_fim = barra.value() >= barra.maximum() - 40
        posicao_anterior = barra.value()

        self.conversa.setHtml(
            f'<body style="color:{TEXTO};">{"".join(self._mensagens)}</body>'
        )

        if estava_no_fim:
            self.conversa.moveCursor(QTextCursor.MoveOperation.End)
            barra.setValue(barra.maximum())
        else:
            barra.setValue(min(posicao_anterior, barra.maximum()))

    # -- animação de digitação ---------------------------------------------

    def _balao_animado(self, revelado: int, com_cursor: bool) -> str:
        """Monta o balão da Tartaruga com o texto parcialmente revelado."""
        corpo = segmentos_para_html(self._anim_segmentos, revelado, com_cursor=com_cursor)
        return self._balao(
            "Tartaruga", VERDE, corpo, lado="esquerda", extra=self._anim_etiqueta
        )

    def _animar_resposta(self, etiqueta: str, texto: str, ao_terminar=None) -> None:
        """Revela a resposta progressivamente, como se estivesse sendo escrita.

        `ao_terminar` é chamado quando a animação acaba. Serve para adiar
        ações que não podem atropelar o texto - notadamente o diálogo de
        confirmação de execução, que abriria por cima da resposta ainda
        sendo digitada.
        """
        self._finalizar_animacao()

        segmentos = segmentar(texto)
        total = sum(len(conteudo) for _, conteudo, _ in segmentos)

        self._anim_etiqueta = etiqueta
        self._anim_segmentos = segmentos
        self._anim_total = total
        self._anim_revelado = 0
        self._anim_ao_terminar = ao_terminar

        if total == 0:
            self._acrescentar(self._balao_animado(0, com_cursor=False))
            self._anim_segmentos = []
            self._anim_ao_terminar = None
            if ao_terminar:
                ao_terminar()
            return

        # Ritmo normal, acelerado apenas o necessário para o texto caber no
        # teto de duração. A divisão é para cima, para nunca estourar o teto.
        quadros_maximos = max(1, DURACAO_MAXIMA_MS // INTERVALO_QUADRO_MS)
        passo_minimo = (total + quadros_maximos - 1) // quadros_maximos
        self._anim_passo = max(CARACTERES_POR_QUADRO, passo_minimo)

        self._anim_indice = len(self._mensagens)
        self._mensagens.append("")
        # A resposta já foi registrada em `memoria` (o núcleo faz isso antes
        # de devolver o resultado ao chamador) - é seguro contar agora, sem
        # esperar o fim da animação de digitação.
        self._atualizar_contador_mensagens()
        self._temporizador.start(INTERVALO_QUADRO_MS)
        self._quadro_animacao()

    def _quadro_animacao(self) -> None:
        """Desenha um quadro da animação."""
        self._anim_revelado = min(self._anim_revelado + self._anim_passo, self._anim_total)
        terminou = self._anim_revelado >= self._anim_total

        self._mensagens[self._anim_indice] = self._balao_animado(
            self._anim_revelado, com_cursor=not terminou
        )
        self._renderizar()

        if terminou:
            self._concluir_animacao()

    def _finalizar_animacao(self) -> None:
        """Mostra a resposta inteira de uma vez, interrompendo a animação.

        Chamado quando o usuário envia outra mensagem sem esperar: quem já
        quer continuar não deve ficar preso ao efeito visual.
        """
        if not self._temporizador.isActive():
            return

        self._anim_revelado = self._anim_total
        self._mensagens[self._anim_indice] = self._balao_animado(
            self._anim_total, com_cursor=False
        )
        self._renderizar()
        self._concluir_animacao()

    def _concluir_animacao(self) -> None:
        """Encerra o temporizador e dispara a ação pendente, se houver."""
        self._temporizador.stop()
        self._anim_segmentos = []
        self._anim_indice = -1

        acao = self._anim_ao_terminar
        self._anim_ao_terminar = None
        if acao:
            acao()

    def _descartar_animacao(self) -> None:
        """Aborta a animação sem exibir o resto nem disparar a ação pendente.

        Usado quando a conversa é apagada: não faz sentido continuar
        escrevendo uma mensagem que deixou de existir.
        """
        self._temporizador.stop()
        self._anim_segmentos = []
        self._anim_indice = -1
        self._anim_ao_terminar = None

    @staticmethod
    def _balao(nome: str, cor_nome: str, corpo: str, lado: str, extra: str = "") -> str:
        """Monta um balão de conversa alinhado à esquerda ou à direita.

        O alinhamento é feito com uma TABELA de duas células: uma contém o
        balão e a outra é uma folga vazia. Invertendo a ordem das células,
        o balão vai para um lado ou para o outro.

        Parece rústico, mas é o único jeito confiável: o motor de texto rico
        do Qt (QTextDocument) implementa um subconjunto pequeno de CSS, e
        nele não funcionam nem `float`, nem `margin-left:auto`, nem
        `border-radius` - os recursos que resolveriam isso num navegador.
        Tabela é o que ele renderiza de forma previsível.
        """
        folga = 100 - LARGURA_BALAO

        celula_balao = (
            f'<td width="{LARGURA_BALAO}%" '
            f'style="padding:10px;">'
            f'<div style="margin-bottom:3px;">'
            f'<span style="color:{cor_nome}; font-weight:700;">{nome}</span>{extra}'
            f'</div>'
            f'{corpo}'
            f'</td>'
        )
        celula_folga = f'<td width="{folga}%"></td>'

        celulas = (
            celula_folga + celula_balao
            if lado == "direita"
            else celula_balao + celula_folga
        )

        return (
            f'<table width="100%" cellspacing="0" cellpadding="6" '
            f'style="margin-top:10px;"><tr>{celulas}</tr></table>'
        )

    def mostrar_usuario(self, texto: str) -> None:
        self._acrescentar(
            self._balao("Você", AZUL, texto_para_html(texto), lado="direita")
        )

    def mostrar_tartaruga(
        self,
        texto: str,
        intencao: str = "",
        confianca: float = 0.0,
        animar: bool = True,
        ao_terminar=None,
    ) -> None:
        self._ultima_resposta_tartaruga = texto
        self.botao_copiar_resposta.setEnabled(True)

        etiqueta = ""
        if intencao:
            cor = VERDE if confianca >= 0.40 else AMARELO
            etiqueta = (
                f'<span style="color:{TEXTO_FRACO}; font-size:11px;">'
                f'&nbsp;·&nbsp;<span style="color:{cor};">{html.escape(intencao)}</span>'
                + (f'&nbsp;· pontuação {confianca:.0%}' if confianca > 0 else '')
                + '</span>'
            )

        if animar:
            self._animar_resposta(etiqueta, texto, ao_terminar)
        else:
            self._acrescentar(
                self._balao("Tartaruga", VERDE, texto_para_html(texto),
                            lado="esquerda", extra=etiqueta)
            )
            if ao_terminar:
                ao_terminar()

    def mostrar_aviso(self, texto: str, cor: str = TEXTO_FRACO) -> None:
        self._acrescentar(
            f'<div style="margin-top:10px; margin-bottom:2px; color:{cor};'
            f' font-size:12px;">{html.escape(texto)}</div>'
        )

    def copiar_ultima_resposta(self) -> None:
        """Copia a última resposta completa da Tartaruga para a área de transferência.

        Sem caixa modal: o retorno é o mesmo aviso não-modal usado no resto
        do app (`mostrar_aviso`), que qualquer leitor de tela já anuncia
        junto com o restante da conversa. Não faz nada quando ainda não há
        resposta - o botão fica desabilitado nesse caso, mas o atalho de
        teclado (Ctrl+Shift+C) não passa por ele, então a checagem aqui é
        quem garante que não há cópia (nem aviso) sem conteúdo.
        """
        if self._ultima_resposta_tartaruga is None:
            return
        QApplication.clipboard().setText(self._ultima_resposta_tartaruga)
        self.mostrar_aviso("Última resposta copiada.")

    def _mostrar_boas_vindas(self) -> None:
        aviso = None
        if len(self.assistente.memoria) > 0:
            quantidade = len(self.assistente.memoria)
            aviso = lambda: self.mostrar_aviso(  # noqa: E731
                f"Conversa anterior retomada ({quantidade} mensagens)."
            )

        self.mostrar_tartaruga(
            "Olá! Sou a Tartaruga, uma assistente de programação com núcleo próprio.\n\n"
            "Posso responder dúvidas de programação, executar código Python, "
            "pesquisar na internet e trabalhar com arquivos.\n\n"
            "Experimente: \"o que é uma list comprehension?\"",
            ao_terminar=aviso,
        )

    # -- ações -------------------------------------------------------------

    def _ocupado(self, ocupado: bool, mensagem: str = "") -> None:
        """Bloqueia a entrada enquanto algo roda em segundo plano."""
        self.campo.setEnabled(not ocupado)
        self.botao_enviar.setEnabled(not ocupado)
        for botao in self.botoes_modo.values():
            botao.setEnabled(not ocupado)
        self.rotulo_estado.setText(mensagem)
        if not ocupado:
            self.campo.setFocus()

    def enviar(self) -> None:
        texto = self.campo.toPlainText().strip()
        if texto:
            self.campo.clear()
            self.enviar_texto(texto)

    def enviar_texto(self, texto: str) -> None:
        """Envia uma frase ao núcleo, processando fora da thread da interface."""
        if self.trabalhador is not None and self.trabalhador.isRunning():
            return

        # Quem já quer continuar não deve ficar preso ao efeito visual.
        self._finalizar_animacao()

        self.mostrar_usuario(texto)
        self._ocupado(True, "Pensando...")

        self.trabalhador = Trabalhador(lambda: self.assistente.responder(texto))
        self.trabalhador.concluido.connect(self._receber_resposta)
        self.trabalhador.falhou.connect(self._receber_falha)
        self.trabalhador.start()

    def _receber_resposta(self, resposta) -> None:
        self._ocupado(False)
        self._visualizacao_atual = getattr(resposta, "visualizacao", None)
        self.botao_visualizar.setVisible(self._visualizacao_atual is not None)
        if self._visualizacao_atual is not None:
            self._registrar_geracao(self._visualizacao_atual[0], self._visualizacao_atual[1])

        # O diálogo de confirmação e o encerramento só acontecem DEPOIS que a
        # resposta terminou de ser escrita - abrir uma janela por cima de um
        # texto ainda aparecendo seria confuso.
        seguinte = None
        if resposta.codigo_pendente:
            seguinte = lambda: self._pedir_confirmacao(resposta.codigo_pendente)  # noqa: E731
        elif resposta.encerrar:
            seguinte = self.close

        self.mostrar_tartaruga(
            resposta.texto,
            resposta.intencao,
            resposta.confianca,
            ao_terminar=seguinte,
        )

    def _receber_falha(self, mensagem: str) -> None:
        self._ocupado(False)
        self.mostrar_aviso(f"Algo deu errado: {mensagem}", VERMELHO)

    def _pedir_confirmacao(self, codigo: str) -> None:
        dialogo = DialogoConfirmarExecucao(codigo, self)
        if dialogo.exec() != QDialog.DialogCode.Accepted:
            self.mostrar_aviso("Execução cancelada.")
            return

        self._ocupado(True, "Executando...")
        # `_info` em vez do método simples: devolve (sucesso, texto) sem
        # exigir que o painel de execução adivinhe o resultado inspecionando
        # a string da resposta - ver o comentário em nucleo.py.
        self.trabalhador = Trabalhador(
            lambda: self.assistente.executar_codigo_confirmado_info(codigo)
        )
        self.trabalhador.concluido.connect(lambda r: self._receber_execucao(codigo, r))
        self.trabalhador.falhou.connect(self._receber_falha)
        self.trabalhador.start()

    def _receber_execucao(self, codigo: str, resultado: tuple[bool, str]) -> None:
        self._ocupado(False)
        sucesso, saida = resultado
        self.mostrar_tartaruga(saida)
        self._registrar_execucao(codigo, sucesso, saida)

    def _registrar_execucao(self, codigo: str, sucesso: bool, saida: str) -> None:
        """Acrescenta uma linha ao painel de execução lateral.

        Guarda o registro completo em `_execucoes` (não só na lista visual)
        para eventualmente reaproveitar - por exemplo, se um dia quisermos
        exportar o histórico de execuções, os dados já estão estruturados.
        """
        from datetime import datetime

        hora = datetime.now().strftime("%H:%M:%S")
        primeira_linha = codigo.strip().split("\n", 1)[0][:60]
        self._execucoes.append({
            "hora": hora, "codigo": codigo, "sucesso": sucesso, "saida": saida,
        })

        cor = VERDE if sucesso else VERMELHO
        simbolo = "✓" if sucesso else "✗"
        item = QListWidgetItem(f"{simbolo} [{hora}]  {primeira_linha}")
        item.setForeground(_cor_qt(cor))
        item.setToolTip(saida[:400])
        self.lista_execucoes.addItem(item)
        self.lista_execucoes.scrollToBottom()
        self._rotulo_execucoes_vazio.setVisible(False)

    def _registrar_geracao(self, linguagem: str, codigo: str) -> None:
        """Lista na aba "Execuções" um código GERADO (HTML/CSS/JS).

        Nada é executado: esse código só é visualizado. Ainda assim a pessoa
        espera achá-lo aqui, então entra como "gerado", com o código completo
        guardado no item (duplo clique abre o texto).
        """
        from datetime import datetime

        hora = datetime.now().strftime("%H:%M:%S")
        primeira_linha = codigo.strip().split("\n", 1)[0][:60]
        self._execucoes.append({
            "hora": hora, "codigo": codigo, "sucesso": None,
            "saida": "", "linguagem": linguagem,
        })

        item = QListWidgetItem(f"◆ [{hora}]  {linguagem.upper()} gerado — {primeira_linha}")
        item.setForeground(_cor_qt(AZUL))
        item.setToolTip(codigo[:400])
        item.setData(Qt.ItemDataRole.UserRole, codigo)
        self.lista_execucoes.addItem(item)
        self.lista_execucoes.scrollToBottom()
        self._rotulo_execucoes_vazio.setVisible(False)

    def _abrir_codigo_do_item(self, item: QListWidgetItem) -> None:
        codigo = item.data(Qt.ItemDataRole.UserRole)
        if codigo:
            DialogoVerCodigo(codigo, self).exec()

    def _toggle_painel_execucao(self) -> None:
        """Abre ou fecha o painel de execução, mostrando/ocultando o widget.

        Ocultar via `setVisible` (não `setSizes`) é o que garante que o
        painel realmente saia do layout quando fechado - ver o comentário
        em `_montar_layout`.
        """
        aberto = self.painel_execucao.isVisible()
        self.painel_execucao.setVisible(not aberto)
        if not aberto:
            largura_total = self.divisor.width() or self.width()
            self.divisor.setSizes([largura_total - 320, 320])

    # -- seletor de modo -----------------------------------------------

    NOMES_MODO = {
        "tartaruga": "Tartaruga",
        "hibrido": "Tartaruga + Phi-4-mini",
        "phi4mini": "Phi-4-mini",
    }

    def _selecionar_modo(self, modo: str) -> None:
        """Troca `self.assistente.modo` e avisa na conversa - a mudança é
        importante o bastante para não passar em silêncio (a próxima
        resposta pode ter vindo de um lugar bem diferente do esperado).
        """
        if self.trabalhador is not None and self.trabalhador.isRunning():
            return
        if modo == self.assistente.modo:
            return  # já é o modo ativo - clicar de novo não faz nada

        self.assistente.modo = modo
        self._atualizar_botoes_modo()

        aviso = f"Modo alterado: {self.NOMES_MODO[modo]}."
        if modo != "tartaruga" and not llm.disponivel():
            aviso += " (o Ollama não está rodando agora - vou avisar quando isso importar.)"
        self.mostrar_aviso(aviso)

    def _atualizar_botoes_modo(self) -> None:
        """Redesenha os pills conforme o modo ativo.

        Trocar o `objectName` (para escolher entre os dois estilos QSS já
        definidos) exige forçar o Qt a reavaliar o estilo do widget - ele
        não faz isso sozinho quando o objectName muda em tempo de execução.
        """
        for chave, botao in self.botoes_modo.items():
            ativo = chave == self.assistente.modo
            botao.setChecked(ativo)
            botao.setObjectName("modoAtivo" if ativo else "modoInativo")
            botao.style().unpolish(botao)
            botao.style().polish(botao)

    def abrir_dialogo_codigo(self) -> None:
        dialogo = DialogoCodigo(self)
        if dialogo.exec() != QDialog.DialogCode.Accepted:
            return

        codigo = dialogo.codigo()
        if not codigo:
            return

        self.assistente.memoria.adicionar("usuario", f"```python\n{codigo}\n```")
        self.mostrar_usuario(f"```python\n{codigo}\n```")
        self.mostrar_aviso('Código guardado. Peça "roda isso" para executar.')

    def abrir_dialogo_historico(self) -> None:
        """Abre o navegador de histórico completo (todos os dias, com busca).

        Separado do "mostra o histórico" que se digita no chat: aquele
        recapitula só a sessão atual, em texto corrido; este enxerga tudo
        que já foi salvo em disco e permite buscar.
        """
        dialogo = DialogoHistorico(self.assistente.memoria, self)
        dialogo.exec()

    def mostrar_ajuda(self) -> None:
        self.mostrar_tartaruga(
            "O que eu sei fazer:\n\n"
            "• Dúvidas de programação — \"o que é uma lista?\"\n"
            "• Executar código Python — \"roda esse código\"\n"
            "• Pesquisar na internet — \"pesquisa sobre Django na internet\"\n"
            "• Arquivos — \"lista os arquivos\", \"salva isso em teste.py\"\n"
            "• Histórico — \"mostra o histórico\"\n\n"
            "• Briefing de landing page — \"quero uma landing page\"\n"
            "• Compreensão semântica local — consulte \"/semantica\"\n"
            "  Corrigir: \"corrigir público para estudantes\". Retomar: \"retomar briefing\".\n\n"
            "A etiqueta ao lado do meu nome mostra a intenção que detectei e "
            "a pontuação do classificador quando aplicável. Decisões por regras e "
            "pedidos de esclarecimento não recebem uma porcentagem de certeza."
        )

    def limpar_conversa(self) -> None:
        resposta = QMessageBox.question(
            self,
            "Limpar conversa",
            "Apagar o histórico desta sessão?\nAs conversas já salvas em disco permanecem.",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No,
        )
        if resposta == QMessageBox.StandardButton.Yes:
            self._descartar_animacao()
            self.assistente.memoria.limpar()
            self.assistente.dialogo.limpar()
            self._mensagens.clear()
            self.conversa.clear()
            self._execucoes.clear()
            self.lista_execucoes.clear()
            self._rotulo_execucoes_vazio.setVisible(True)
            # O preview pertence à conversa apagada: esquece o código
            # guardado, esconde o botão e DESCARTA a view. Só esvaziar o
            # conteúdo não basta: uma página em loop infinito continuaria
            # rodando (achado em revisão, reproduzido com o
            # WebEngine real). Descartar encerra o renderizador; a view é
            # recriada sob demanda na próxima visualização.
            self._visualizacao_atual = None
            self.botao_visualizar.setVisible(False)
            self._descartar_view_preview()
            self._mostrar_boas_vindas()

    # -- encerramento ------------------------------------------------------

    def closeEvent(self, evento) -> None:
        """Garante que a conversa seja salva ao fechar a janela."""
        self._descartar_animacao()
        try:
            self.assistente.memoria.salvar()
        except OSError:
            pass
        evento.accept()


# ---------------------------------------------------------------------------
# Ponto de entrada
# ---------------------------------------------------------------------------

def main() -> int:
    # Precisa vir ANTES da QApplication existir. Sem isso, o import tardio
    # de PyQt6.QtWebEngineWidgets feito só quando o usuário abre a aba
    # "Preview" (ver tartaruga/ferramentas/preview.py::criar_view() e
    # _montar_aba_preview_inicial() abaixo) falha com ImportError, mesmo
    # com a dependência opcional instalada - confirmado reproduzindo o erro
    # antes de adicionar esta linha. Setar a flag aqui não tem custo pra
    # quem não usa preview: é só um sinalizador do Qt, não importa nada
    # pesado.
    QApplication.setAttribute(Qt.ApplicationAttribute.AA_ShareOpenGLContexts)
    aplicacao = QApplication(sys.argv)
    aplicacao.setApplicationName("Tartaruga")
    configuracoes = Configuracoes.carregar()
    aplicacao.setFont(QFont("Segoe UI", configuracoes.tamanho_fonte))
    os.environ["TARTARUGA_SEMANTICA"] = "1" if configuracoes.semantica_ativa else "0"

    try:
        assistente = Tartaruga(retomar_conversa=configuracoes.retomar_conversa)
        assistente.modo = configuracoes.modo_inicial
    except (FileNotFoundError, ValueError) as erro:
        QMessageBox.critical(
            None,
            "Erro ao iniciar",
            f"Não foi possível carregar os dados da Tartaruga:\n\n{erro}",
        )
        return 1

    janela = JanelaPrincipal(assistente)
    janela.show()
    return aplicacao.exec()


if __name__ == "__main__":
    sys.exit(main())
