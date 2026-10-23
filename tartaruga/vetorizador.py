"""
Vetorizador TF-IDF implementado do zero.

O computador não entende texto, só números. Este módulo resolve isso:
transforma uma frase num vetor numérico, de modo que frases parecidas
gerem vetores próximos no espaço.

A técnica usada é TF-IDF (Term Frequency - Inverse Document Frequency):

    TF  = quantas vezes a palavra aparece na frase (dividido pelo total)
          -> mede o quanto a palavra importa DENTRO daquela frase

    IDF = log((1 + N) / (1 + df)) + 1
          onde N = total de documentos e df = em quantos a palavra aparece
          -> mede o quanto a palavra é RARA no conjunto todo

    TF-IDF = TF * IDF

A intuição: uma palavra que aparece em todo lugar ("como", "python") carrega
pouca informação; uma que aparece em poucos documentos ("recursividade")
identifica bem o assunto. O IDF é justamente o peso que faz isso.

Nenhuma biblioteca externa é usada - apenas `math`, `re` e `unicodedata`.
"""

import math
import re
import unicodedata

# Palavras muito comuns do português, que aparecem em quase toda frase e
# portanto não ajudam a distinguir uma intenção de outra.
#
# DUAS EXCLUSÕES DELIBERADAS desta lista:
#
# 1. Palavras-chave de programação ("for", "in", "if") - são exatamente o
#    que queremos detectar numa dúvida técnica.
#
# 2. Palavras interrogativas ("que", "qual", "para", "quando", "por") -
#    estas aparecem em toda lista de stopwords pronta, mas aqui seriam um
#    erro. A tarefa não é descobrir o ASSUNTO do texto, e sim a INTENÇÃO:
#    "o que é", "qual a diferença", "para que serve" são as marcas mais
#    fortes de uma pergunta. Removê-las derrubou o recall de
#    duvida_programacao de 0.86 para 0.29 numa das medições.
#
# 3. "até" - marcador de despedida. Com ela na lista, as frases "até mais",
#    "até logo", "até breve" e "até a próxima" perdiam TODAS as palavras
#    (porque "mais", "logo" e "a" também saíam) e chegavam vazias ao
#    classificador, que se abstinha. Três erros de uma vez, todos pela
#    mesma causa.
#
# 4. "esta"/"estas" - aqui a causa é mais sutil. A remoção de acentos, que
#    serve para tratar "laço" e "laco" como a mesma palavra, também funde
#    o VERBO "está" com o PRONOME "esta". Como o pronome é stopword, a
#    pergunta "como você está" perdia o verbo e sobrava só "como" - que
#    aponta para dúvida de programação. Normalizar texto sempre custa
#    alguma informação; aqui o custo aparecia como erro de classificação.
#
# A lição vale para o relatório: lista de stopwords depende da tarefa,
# não existe uma lista universalmente correta.
STOPWORDS = {
    "a", "ao", "aos", "as", "com", "da", "das", "de", "do",
    "dos", "e", "ela", "elas", "ele", "eles", "em", "entre", "essa", "essas", "esse",
    "esses", "este", "estes", "eu", "isso", "isto", "já",
    "ja", "la", "lhe", "lo", "mas", "me", "mesmo", "meu", "minha", "muito",
    "na", "nas", "no", "nos", "num", "numa", "o", "os", "ou", "pela",
    "pelo", "se", "sem", "ser", "seu", "sua",
    "só", "so", "também", "tambem", "te", "tem", "ter", "teu", "tua", "um",
    "uma", "voce", "você", "vou", "à", "às", "é", "mais", "aqui",
    "ali", "dum", "pra", "pro", "sao", "sou", "somos", "era", "eram",
}

# Palavras que montam a PERGUNTA sem dizer nada sobre o ASSUNTO dela.
#
# Elas são mantidas na classificação de intenção (onde marcam que a frase é
# uma dúvida) mas precisam sair na BUSCA da base de conhecimento. Motivo
# concreto, encontrado nos testes: "me explica o que é computação quântica"
# casava com "me explica o que é um laço aninhado" a 63% de similaridade,
# porque as duas frases compartilham todo o arcabouço da pergunta. O
# assistente respondia sobre laços a uma pergunta de física.
#
# Removendo estas palavras, sobra só o tópico - e aí "computação quântica"
# não casa com nada, que é a resposta correta.
INTERROGATIVAS = {
    "que", "qual", "quais", "quando", "onde", "quem", "como", "para", "por",
    "porque", "explica", "explique", "explicar", "ensina", "ensinar",
    "serve", "funciona", "faco", "faço", "fazer", "faz", "usar", "uso",
    "significa", "sobre",
}

# Palavras de enchimento do português: não dizem nada do assunto e, ao entrarem
# na conta, derrubam a COBERTURA da pergunta ("executar um bloco enquanto ALGO
# for verdadeiro" ficava com metade das palavras "desconhecidas"). Só a busca
# na base as descarta; a classificação de intenção continua como estava.
ENCHIMENTO = {"algo", "cada", "todo", "toda", "todos", "todas", "deixar"}

# Conjunto usado na busca por similaridade (conhecimento.py).
STOPWORDS_BUSCA = STOPWORDS | INTERROGATIVAS | ENCHIMENTO

# Captura letras, números e underscore. Depois de remover os acentos, todo
# token vira ASCII, então este padrão cobre tanto português quanto código.
PADRAO_TOKEN = re.compile(r"[a-z0-9_]+")

# ---------------------------------------------------------------------------
# Operadores: a pontuação que, em programação, é palavra
#
# O padrão acima aceita só letras e números - e descarta silenciosamente
# todo o resto. Para texto comum isso é correto; para texto sobre código,
# é perder informação essencial.
#
# Encontrado num teste real: a pergunta "por que devo usar === em vez de =="
# não encontrava nada. Os dois operadores, que SÃO o assunto da pergunta,
# sumiam na tokenização, e sobravam apenas "devo" e "vez".
#
# A solução é traduzir cada operador para um token de palavra antes de
# tokenizar. A ordem importa: os mais longos primeiro, senão "===" seria
# consumido como "==" seguido de "=".
# ---------------------------------------------------------------------------
OPERADORES = [
    ("===", " igualdade_estrita "),
    ("!==", " diferenca_estrita "),
    ("==", " igualdade "),
    ("!=", " diferente "),
    ("=>", " arrow "),
    ("->", " seta "),
    ("&&", " e_logico "),
    ("||", " ou_logico "),
    (">=", " maior_igual "),
    ("<=", " menor_igual "),
    ("**", " potencia "),
    ("//", " divisao_inteira "),
]


def traduzir_operadores(texto: str) -> str:
    """Substitui operadores por tokens de palavra, para não se perderem."""
    for simbolo, palavra in OPERADORES:
        texto = texto.replace(simbolo, palavra)
    return texto


# ---------------------------------------------------------------------------
# Contrações informais: a mesma palavra, escrita colada
#
# "oque" (sem espaço) é como boa parte das pessoas digita "o que" no
# celular - talvez mais comum na prática do que a forma com espaço. Sem
# tratamento, "oque" vira UM token desconhecido, e o "que" que ele contém -
# um dos marcadores mais fortes de pergunta que o sistema tem - some por
# completo.
#
# Encontrado num teste real: "oque você faz?" foi classificado como
# gerar_codigo (sem "que", sobrou só "faz", uma palavra fraca demais para
# decidir sozinha), e "oque é python?" - uma pergunta que a base curada
# responde bem quando escrita com espaço - caiu na recusa total. A mesma
# pergunta com espaço funcionava perfeitamente; só a forma de digitar mudava
# o resultado, o que não devia acontecer.
#
# `\b` (borda de palavra) evita casar "oque" dentro de outra palavra -
# nenhuma palavra comum do português contém "oque" como substring contígua
# (ao contrário do que se poderia temer com "porque", que tem um "r" no meio).
CONTRACOES = [
    (re.compile(r"\boque\b"), "o que"),
    (re.compile(r"\boq\b"), "o que"),
]


def normalizar_contracoes(texto: str) -> str:
    """Expande contrações informais comuns antes da tokenização."""
    for padrao, expansao in CONTRACOES:
        texto = padrao.sub(expansao, texto)
    return texto


def singularizar(palavra: str) -> str:
    """Remove o 's' final, aproximando plural e singular.

    É um radicalizador (stemmer) deliberadamente ingênuo. "variáveis" vira
    "variávei", que não é palavra nenhuma - e isso NÃO É PROBLEMA, porque a
    mesma regra é aplicada ao índice e à consulta. O que importa não é o
    resultado ser uma palavra correta, e sim as duas formas convergirem para
    a mesma coisa.

    Motivo de existir: "me explica closures" não encontrava a entrada sobre
    "closure". A pergunta e a resposta falavam do mesmo assunto e não se
    reconheciam por causa de uma letra.

    Conservador de propósito: preserva palavras curtas ("js", "css") e as
    terminadas em "ss", onde o "s" não marca plural.
    """
    if len(palavra) > 3 and palavra.endswith("s") and not palavra.endswith("ss"):
        return palavra[:-1]
    return palavra


def remover_acentos(texto: str) -> str:
    """Converte 'função' em 'funcao'.

    Normaliza para NFD, o que separa a letra base do seu acento, e descarta
    os caracteres da categoria Mn (Mark, nonspacing) - ou seja, os acentos.
    Isso faz com que 'laço' e 'laco' sejam tratados como a mesma palavra.
    """
    decomposto = unicodedata.normalize("NFD", texto)
    return "".join(c for c in decomposto if unicodedata.category(c) != "Mn")


def tokenizar(texto: str, stopwords: set[str] | None = None) -> list[str]:
    """Quebra uma frase na lista de palavras que a representam.

    Etapas: minúsculas -> sem acentos -> só letras/números -> sem stopwords.

    O conjunto de stopwords é um PARÂMETRO porque as duas tarefas do projeto
    precisam de listas diferentes: a classificação de intenção usa `STOPWORDS`
    (preservando as palavras interrogativas) e a busca na base usa
    `STOPWORDS_BUSCA` (descartando-as). Ver o comentário em INTERROGATIVAS.

    Se a remoção esvaziar a lista (por exemplo na frase "e o que é isso"),
    devolvemos os tokens originais. É melhor trabalhar com palavras fracas do
    que com um vetor vazio, que não classificaria nada.
    """
    if stopwords is None:
        stopwords = STOPWORDS

    # Ordem: contrações ("oque" -> "o que") e operadores viram palavras
    # ANTES de qualquer outra coisa, senão o padrão de tokens os descartaria
    # ou os trataria como uma palavra desconhecida só.
    texto_limpo = remover_acentos(
        traduzir_operadores(normalizar_contracoes(texto.lower()))
    )
    tokens = PADRAO_TOKEN.findall(texto_limpo)

    # A filtragem de stopwords usa a palavra original; a singularização vem
    # depois, para que "os" e "as" continuem sendo reconhecidas como
    # stopwords em vez de virarem "o" e "a".
    filtrados = [singularizar(t) for t in tokens if t not in stopwords]
    return filtrados if filtrados else [singularizar(t) for t in tokens]


def normalizar(vetor: dict[str, float]) -> dict[str, float]:
    """Deixa o vetor com comprimento 1 (normalização L2).

    Por que isso importa: sem normalizar, uma frase longa teria vetor "maior"
    que uma curta só por ser longa, e a comparação ficaria injusta. Depois de
    normalizar, o que resta é apenas a DIREÇÃO do vetor - ou seja, o assunto.

    Bônus: com os dois vetores normalizados, a similaridade de cosseno vira
    um simples produto escalar (ver `similaridade_cosseno`).
    """
    norma = math.sqrt(sum(valor * valor for valor in vetor.values()))
    if norma == 0:
        return dict(vetor)
    return {termo: valor / norma for termo, valor in vetor.items()}


def similaridade_cosseno(vetor_a: dict[str, float], vetor_b: dict[str, float]) -> float:
    """Mede o quanto dois vetores apontam para a mesma direção.

    Retorna um número entre 0 e 1 (os valores TF-IDF nunca são negativos):
        1.0 -> frases sobre exatamente o mesmo assunto
        0.0 -> nenhuma palavra em comum

    Como os vetores já vêm normalizados, o cosseno é o produto escalar.
    Percorremos o menor dos dois dicionários por eficiência: termos que
    existem só num deles contribuem com zero e podem ser ignorados.
    """
    if len(vetor_a) > len(vetor_b):
        vetor_a, vetor_b = vetor_b, vetor_a
    return sum(valor * vetor_b.get(termo, 0.0) for termo, valor in vetor_a.items())


class Vetorizador:
    """Aprende o vocabulário de um conjunto de textos e os converte em vetores.

    Uso:
        v = Vetorizador()
        v.ajustar(["como criar uma lista", "como criar uma funcao"])
        vetor = v.transformar("criar lista")

    O método `ajustar` corresponde à fase de TREINO: é onde o IDF de cada
    palavra é calculado. O `transformar` é a fase de USO.
    """

    def __init__(self, stopwords: set[str] | None = None) -> None:
        # Guardar o conjunto aqui garante que treino e uso apliquem
        # exatamente a mesma filtragem. Se as duas fases divergissem, o
        # vocabulário aprendido não bateria com o das consultas.
        self.stopwords = STOPWORDS if stopwords is None else stopwords
        self.idf: dict[str, float] = {}
        self.n_documentos: int = 0
        self.ajustado: bool = False

    def ajustar(self, documentos: list[str]) -> "Vetorizador":
        """Calcula o IDF de cada palavra a partir do conjunto de documentos."""
        self.n_documentos = len(documentos)

        # Em quantos documentos distintos cada termo aparece.
        # Usamos set() porque o que importa aqui é a PRESENÇA, não a
        # quantidade de repetições dentro do mesmo documento.
        frequencia_documento: dict[str, int] = {}
        for documento in documentos:
            for termo in set(tokenizar(documento, self.stopwords)):
                frequencia_documento[termo] = frequencia_documento.get(termo, 0) + 1

        # O "+1" no numerador e no denominador é suavização: evita divisão por
        # zero e impede que um termo presente em todos os documentos zere o IDF.
        self.idf = {
            termo: math.log((1 + self.n_documentos) / (1 + df)) + 1.0
            for termo, df in frequencia_documento.items()
        }
        self.ajustado = True
        return self

    def transformar(self, texto: str) -> dict[str, float]:
        """Converte um texto no seu vetor TF-IDF normalizado.

        O vetor é representado como dicionário {termo: peso} em vez de uma
        lista com uma posição por palavra do vocabulário. Como cada frase usa
        pouquíssimas das palavras existentes, guardar só as presentes economiza
        muita memória - é a chamada representação esparsa.
        """
        if not self.ajustado:
            raise RuntimeError(
                "O vetorizador precisa ser treinado com ajustar() antes de transformar()."
            )

        tokens = tokenizar(texto, self.stopwords)
        if not tokens:
            return {}

        contagem: dict[str, int] = {}
        for token in tokens:
            contagem[token] = contagem.get(token, 0) + 1

        total_tokens = len(tokens)
        vetor: dict[str, float] = {}
        for termo, quantidade in contagem.items():
            peso_idf = self.idf.get(termo)
            if peso_idf is None:
                # Palavra nunca vista no treino: não temos IDF para ela, então
                # é ignorada. Esta é uma limitação conhecida do modelo e está
                # documentada no README.
                continue
            tf = quantidade / total_tokens
            vetor[termo] = tf * peso_idf

        return normalizar(vetor)

    def ajustar_transformar(self, documentos: list[str]) -> list[dict[str, float]]:
        """Atalho: treina com os documentos e já devolve os vetores deles."""
        self.ajustar(documentos)
        return [self.transformar(documento) for documento in documentos]
