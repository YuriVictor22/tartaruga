"""
Gestor de diálogo - a peça que faltava entre "entender" e "responder".

Um sistema conversacional tem três camadas:

    1. COMPREENSÃO  -> o que o usuário quis dizer   (classificador.py)
    2. DIÁLOGO      -> o que fazer com isso, dado o que já aconteceu   <-- aqui
    3. RESPOSTA     -> como dizer                    (respostas.json)

Sem a camada do meio, o assistente vira uma função pura: mesma intenção,
mesma frase, sempre. Foi exatamente o que aconteceu num teste real - a
saudação devolveu, palavra por palavra, o mesmo texto da mensagem de
boas-vindas que ainda estava na tela. Nada estava tecnicamente errado, e
mesmo assim soava artificial.

Este módulo resolve isso guardando ESTADO (já cumprimentou? já listou o que
sabe fazer? que assuntos já explicou?) e escolhendo VARIANTES de resposta em
vez de um texto fixo.
"""

import json
import random
import re
from .interpretacao import Contexto
from .briefing import Briefing

from .caminhos import recurso

CAMINHO_PADRAO = recurso("dados", "respostas.json")

# ---------------------------------------------------------------------------
# Faixas de confiança - medidas EM RELAÇÃO AO ACASO, não em valor absoluto
#
# A primeira versão usava um limiar fixo (agir acima de 40%). Ele funcionou
# enquanto existiam 7 intenções e quebrou no dia em que passaram a ser 13:
# "olá", "oi", "obrigado" e "entendi" - as falas mais comuns que existem -
# passaram todas a cair em "não entendi".
#
# A causa é aritmética. O softmax distribui 100% entre TODAS as classes,
# então o piso do acaso é 1/n:
#
#     com  7 classes, o acaso é 14,3%  -> 29% é apenas 2x o acaso
#     com 13 classes, o acaso é  7,7%  -> 29% é quase 4x o acaso
#
# O mesmo 29% significa coisas muito diferentes nos dois casos. Por isso a
# faixa é calculada como razão sobre o acaso, e não como valor absoluto:
# assim o critério continua válido se novas intenções forem criadas.
#
# Lição para o relatório: limiar absoluto sobre saída de softmax é uma
# armadilha - ele embute silenciosamente o número de classes do dia em que
# foi calibrado.
# ---------------------------------------------------------------------------
FATOR_ALTA = 3.0    # 3x o acaso ou mais -> age direto
FATOR_MEDIA = 1.8   # entre 1.8x e 3x    -> age, mas com ressalva
# abaixo de FATOR_MEDIA: não age, pede esclarecimento

# Pergunta de sim ou não sobre capacidade: "você consegue...", "dá pra...".
# Merece uma resposta que COMECE com "consigo" - responder com um menu a
# quem perguntou "você consegue?" é ignorar a pergunta feita.
PADRAO_SIM_NAO = re.compile(
    r"\b(voce|vc)?\s*(consegue|sabe|pode|conseguiria|saberia)\b|\bda\s+(pra|para)\b",
    re.IGNORECASE,
)

# ---------------------------------------------------------------------------
# Sobre QUAL capacidade a pergunta é
#
# Saber que a frase é do tipo "capacidades" não basta. Num teste real, a
# pergunta "você consegue codar?" recebeu a resposta sobre CONVERSAR - porque
# havia um texto único para toda pergunta de sim ou não. Estava certo para a
# intenção e errado para a pergunta.
#
# Aqui identificamos o assunto específico, para que cada pergunta receba a
# resposta que lhe cabe.
#
# Cada assunto tem palavras FORTES (peso 2) - que só fazem sentido nesse
# assunto - e FRACAS (peso 1) - que aparecem como detalhe de outros pedidos
# também. Nomes de linguagem são o caso claro: "python" aparece tanto em
# "quais linguagens você conhece" (é sobre linguagens) quanto em "consegue
# criar um jogo em python" (é sobre CRIAR - "python" é só o detalhe de qual
# linguagem). Um teste real expôs isso: "consegue criar o jogo da velha em
# python?" detectava "linguagens" em vez de "programar", porque "python"
# vencia "criar" só por estar primeiro na lista de verificação - a mesma
# armadilha de peso já corrigida uma vez em `geracao.py::PADROES_HTML`.
# ---------------------------------------------------------------------------
ASSUNTOS_CAPACIDADE: list[tuple[str, set[str], set[str]]] = [
    ("linguagens", {"linguagem", "linguagens"}, {
        "python", "java", "javascript", "js", "c", "cpp", "csharp", "php",
        "ruby", "go", "rust", "kotlin", "swift", "html", "css", "sql",
        "typescript",
    }),
    ("executar", {"executar", "executa", "rodar", "roda", "compilar"}, {"testar"}),
    ("pesquisar", {"pesquisar", "pesquisa", "buscar", "busca"}, {
        "procurar", "procura", "internet", "web", "google", "online",
    }),
    ("arquivos", {"arquivo", "arquivos", "pasta"}, {"salvar", "salva", "gravar"}),
    ("conversar", {"conversar", "conversa", "conversando", "papo", "dialogar"}, {
        "falar", "bater", "responder",
    }),
    ("programar", {
        "codar", "programar", "programa", "codificar", "desenvolver", "criar", "gerar",
    }, {"escrever", "fazer"}),
    ("llm", {"phi", "ollama", "llm"}, {"modelo", "ia", "inteligencia"}),
]


def _normalizar_palavras(palavras: set[str]) -> set[str]:
    """Aplica às palavras-chave a MESMA normalização que o tokenizador usa.

    Sem isto, a comparação falha de um jeito difícil de enxergar: o
    tokenizador singulariza "linguagens" para "linguagen", que não estava
    escrito em lugar nenhum da lista acima, e a detecção não achava nada.

    A lição vale além deste arquivo: quando dois pedaços do sistema comparam
    texto, os dois precisam normalizar do mesmo jeito - e a forma segura de
    garantir isso é derivar um do outro, nunca manter duas listas paralelas.
    """
    from .vetorizador import singularizar

    return {singularizar(p) for p in palavras}


ASSUNTOS_NORMALIZADOS = [
    (assunto, _normalizar_palavras(fortes), _normalizar_palavras(fracas))
    for assunto, fortes, fracas in ASSUNTOS_CAPACIDADE
]


def detectar_assunto_capacidade(texto: str) -> str | None:
    """Descobre sobre qual capacidade a pergunta fala, ou None se for genérica.

    Pontua cada assunto (fortes valem 2, fracas valem 1) e devolve o de
    maior pontuação. Em caso de empate de verdade, vence o primeiro da lista.
    """
    from .vetorizador import tokenizar

    presentes = set(tokenizar(texto, stopwords=set()))

    melhor_assunto = None
    melhor_pontuacao = 0
    for assunto, fortes, fracas in ASSUNTOS_NORMALIZADOS:
        pontuacao = 2 * len(presentes & fortes) + len(presentes & fracas)
        if pontuacao > melhor_pontuacao:
            melhor_assunto, melhor_pontuacao = assunto, pontuacao

    return melhor_assunto


class GestorDialogo:
    """Guarda o estado da conversa e escolhe como responder."""

    def __init__(self, caminho=None) -> None:
        self.contexto = Contexto()
        self.briefing = Briefing()
        self.caminho = caminho or CAMINHO_PADRAO
        with open(self.caminho, encoding="utf-8") as arquivo:
            self.respostas: dict = json.load(arquivo)

        # Última variante usada de cada chave, para não repetir em seguida.
        self._ultima_escolha: dict[str, str] = {}

        # --- estado da conversa ---
        self.ja_cumprimentou = False
        self.ja_listou_capacidades = False
        self.ja_falou_do_projeto = False
        self.topicos_explicados: list[str] = []
        self.ultimo_topico: str | None = None
        self.historico_topicos: list[tuple[str, int]] = []   # (id, turno) de cada explicação, para comparar os recentes
        self.turno_do_topico = 0          # em que turno o último tópico foi explicado (recência do contexto)
        self.turnos = 0

    # ------------------------------------------------------------------
    # Escolha de variantes
    # ------------------------------------------------------------------

    def escolher(self, chave: str, **formatacao) -> str:
        """Devolve uma variante da chave, evitando repetir a anterior.

        A repetição é o que mais denuncia um robô. Sorteamos entre as
        variantes, descartando a última usada - assim duas respostas
        seguidas nunca são idênticas, mas o texto continua sendo escrito
        por uma pessoa, e não gerado aleatoriamente.
        """
        from .geracao import total_padroes
        formatacao.setdefault("padroes", total_padroes())
        variantes = self.respostas.get(chave)
        if not variantes:
            return ""

        disponiveis = variantes
        if len(variantes) > 1:
            anterior = self._ultima_escolha.get(chave)
            disponiveis = [v for v in variantes if v != anterior] or variantes

        escolhida = random.choice(disponiveis)
        self._ultima_escolha[chave] = escolhida

        return escolhida.format(**formatacao) if formatacao else escolhida

    def descrever(self, intencao: str) -> str:
        """Nome legível de uma intenção, para usar numa pergunta de confirmação."""
        return self.respostas.get("descricoes", {}).get(intencao, "algo que não reconheci")

    # ------------------------------------------------------------------
    # Faixas de confiança
    # ------------------------------------------------------------------

    @staticmethod
    def faixa(confianca: float, total_classes: int) -> str:
        """Classifica a confiança em 'alta', 'media' ou 'baixa'.

        `total_classes` é necessário porque a referência é o acaso (1/n),
        e não um valor fixo - ver o comentário sobre FATOR_ALTA no topo.
        """
        if total_classes <= 0 or confianca <= 0:
            return "baixa"

        acaso = 1.0 / total_classes
        razao = confianca / acaso

        if razao >= FATOR_ALTA:
            return "alta"
        if razao >= FATOR_MEDIA:
            return "media"
        return "baixa"

    def confirmar(self, intencao: str) -> str:
        """Frase que confirma o entendimento, usada na faixa média."""
        return self.escolher("confirmar_intencao", descricao=self.descrever(intencao))

    # ------------------------------------------------------------------
    # Perguntas de sim ou não
    # ------------------------------------------------------------------

    @staticmethod
    def e_pergunta_sim_nao(texto: str) -> bool:
        """Detecta 'você consegue...?', 'dá pra...?' e semelhantes."""
        return bool(PADRAO_SIM_NAO.search(texto))

    @staticmethod
    def assunto_da_capacidade(texto: str) -> str | None:
        """Sobre qual capacidade específica a pergunta fala."""
        return detectar_assunto_capacidade(texto)

    # ------------------------------------------------------------------
    # Estado
    # ------------------------------------------------------------------

    def registrar_turno(self) -> None:
        self.turnos += 1

    def registrar_topico(self, identificador: str) -> None:
        """Anota que um assunto já foi explicado nesta conversa."""
        self.ultimo_topico = identificador
        self.turno_do_topico = self.turnos
        self.historico_topicos = (self.historico_topicos + [(identificador, self.turnos)])[-8:]
        if identificador not in self.topicos_explicados:
            self.topicos_explicados.append(identificador)

    def ja_explicou(self, identificador: str) -> bool:
        return identificador in self.topicos_explicados

    def limpar(self) -> None:
        """Zera o estado, mantendo os textos carregados."""
        self.contexto.limpar()
        self.briefing = Briefing()
        self._ultima_escolha.clear()
        self.ja_cumprimentou = False
        self.ja_listou_capacidades = False
        self.ja_falou_do_projeto = False
        self.topicos_explicados = []
        self.ultimo_topico = None
        self.historico_topicos = []
        self.turno_do_topico = 0
        self.turnos = 0
