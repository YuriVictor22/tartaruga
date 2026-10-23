"""Vocabulário de paráfrases de programação para a BUSCA na base de conhecimento.

A base é escrita com poucas formulações por assunto ("como percorrer uma
lista"). Quem pergunta "como visitar cada elemento de uma coleção" fala do
mesmo assunto com outras palavras, e um índice lexical não sabe disso: a
cobertura cai e a base nem chega a comparar.

Este arquivo lista, por CONCEITO, palavras que as pessoas usam no lugar das que
a base usa. Regras de projeto:

- É só vocabulário de programação (não de português geral): "visitar" só
  significa percorrer aqui porque o contexto é código.
- EXPANDE a consulta (acrescenta os termos canônicos), nunca troca nem apaga o
  que a pessoa escreveu, então uma pergunta que já funcionava não piora.
- Vale só para a busca na base. O classificador de intenção não o usa: mexer
  nele exige nova medição.
- Não é lista de frases de teste. Cada linha é uma família de palavras; frases
  novas continuam dependendo de medição em casos reservados.
- Chaves e valores são escritos em português comum; a normalização (minúsculas,
  sem acento, singular) é aplicada aqui, com o mesmo tokenizador da busca.
"""
import re

from .vetorizador import tokenizar

# palavra que a pessoa pode usar -> palavras que a base usa para o conceito
_BRUTO: dict[str, tuple[str, ...]] = {
    # laços e coleções
    "visitar": ("percorrer", "for"),
    "iterar": ("percorrer", "for"),
    "varrer": ("percorrer", "for"),
    "colecao": ("lista",),
    "sequencia": ("lista",),
    "vetor": ("lista",),
    "array": ("lista",),
    "elemento": ("item",),
    # dicionários
    "associar": ("chave", "valor", "dicionario"),
    "associacao": ("chave", "valor", "dicionario"),
    "mapa": ("chave", "valor", "dicionario"),
    "mapear": ("chave", "valor", "dicionario"),
    # erros
    "excecao": ("erro", "except"),
    "falha": ("erro", "except"),
    "quebrar": ("erro",),
    "proteger": ("except",),
    # remover repetidos
    "repetido": ("duplicado",),
    "duplicata": ("duplicado",),
    "tirar": ("remover",),
    "eliminar": ("remover",),
    # funções e rotinas
    "rotina": ("funcao",),
    "procedimento": ("funcao",),
    "subrotina": ("funcao",),
    "parametro": ("funcao",),
    "argumento": ("funcao",),
    # texto e arquivos
    "documento": ("arquivo",),
    "concatenar": ("juntar", "fstring"),
    "interpolar": ("fstring",),
    "trecho": ("fatiamento",),
    "pedaco": ("fatiamento",),
    "fatia": ("fatiamento",),
    # operações comuns
    "acrescentar": ("append", "adicionar"),
    "inserir": ("append", "adicionar"),
    "adiciono": ("adicionar", "append"),
    "adiciona": ("adicionar", "append"),
    "adicione": ("adicionar", "append"),
    "incluir": ("append", "adicionar"),
    "organizar": ("ordenar",),
    "classificar": ("ordenar",),
    "quantidade": ("len", "tamanho"),
    "contar": ("len", "tamanho"),
    # web
    "celular": ("responsivo", "mobile"),
    "mobile": ("responsivo",),
    "adaptar": ("responsivo",),
    "adaptado": ("responsivo",),
    "adaptavel": ("responsivo",),
    "clique": ("evento",),
    "reagir": ("evento",),
    "aguardar": ("await", "async"),
    "assincrono": ("async",),
}


def _normalizar(palavra: str) -> str:
    tokens = tokenizar(palavra, stopwords=set())
    return tokens[0] if tokens else ""


SINONIMOS: dict[str, tuple[str, ...]] = {}
for _chave, _valores in _BRUTO.items():
    _k = _normalizar(_chave)
    _v = tuple(t for t in (_normalizar(x) for x in _valores) if t)
    if _k and _v:
        SINONIMOS[_k] = _v


def expandir(tokens: list[str]) -> list[str]:
    """Termos extras (sem repetir os já presentes) para acrescentar à consulta."""
    presentes = set(tokens)
    extras: list[str] = []
    for token in tokens:
        for candidato in SINONIMOS.get(token, ()):
            if candidato not in presentes and candidato not in extras:
                extras.append(candidato)
    return extras


# ---------------------------------------------------------------------------
# Contexto técnico: sinais FORTES x termos conceituais AMBÍGUOS
# ---------------------------------------------------------------------------
# Um termo do dia a dia que também é conceito de código ("lista", "arquivo",
# "item", "chave", "valor", "ordem", "texto", "erro", "site", "página") NUNCA
# conta como sinal: "lista de compras" e "proteger um arquivo importante" não
# são dúvidas de programação.
#
# Dos termos que sobram, separamos dois níveis:
#  - FORTES: sintaxe, tecnologia e palavras-chave que quase só existem em
#    programação ("python", "for", "append", "css", "try"). UM basta.
#  - AMBÍGUOS: conceitos que têm outro sentido comum ("função" do gerente,
#    "classe" de viagem, "programa" do evento, "atributo" de uma pessoa,
#    "evento" social). Sozinhos não bastam: exigem COMBINAÇÃO de pelo menos
#    dois e continuam sujeitos à penalização por palavras desconhecidas.
_FORTES_BRUTO = (
    # linguagens e tecnologias
    "python", "javascript", "js", "css", "html", "json", "sql", "api", "dom",
    "pip", "venv", "node", "http",
    # palavras-chave e construções de sintaxe sem uso corrente fora de código
    "try", "except", "elif", "def", "lambda", "async", "await", "append", "len",
    "enumerate", "fstring", "comprehension", "hoisting", "callback", "promise",
    "closure", "arrow", "pseudocodigo",
    # tipos em inglês
    "dict", "str", "int", "boolean",
    # web
    "flexbox", "onclick", "stylesheet",
)

# Palavras que TAMBÉM são sintaxe/tecnologia, mas têm uso corrente fora dela:
# "for" (se ele FOR ao mercado), "print" (print da página), "string" (de guitarra),
# "input", "range", "list", "array", "grid", "float", "slice", "debug", "if",
# "else", "while", "zip", "div". Sozinhas NÃO liberam oferta; a resposta direta
# continua possível (com a penalização por palavras desconhecidas), o que preserva
# "como usar for". Para oferecer, combinam com outro termo técnico (ver
# `sinal_tecnico`).
_POLISSEMICOS_BRUTO = (
    "for", "while", "if", "else", "print", "input", "range", "string", "array",
    "list", "float", "grid", "slice", "debug", "zip", "div",
)

_AMBIGUOS_BRUTO = (
    "codigo", "programa", "programacao", "programar", "script", "algoritmo",
    "funcao", "variavel", "constante", "parametro", "argumento", "laco", "loop",
    "condicional", "classe", "objeto", "metodo", "atributo", "heranca",
    "polimorfismo", "recursao", "recursividade", "escopo", "compilador",
    "interpretador", "tupla", "dicionario", "inteiro", "import", "biblioteca",
    "modulo", "framework", "sintaxe", "bug", "excecao", "exception",
    "fatiamento", "formulario", "evento", "semantica", "acessibilidade",
    "propriedade", "seletor", "responsivo", "mobile", "landing", "web",
    "frontend", "backend", "tag", "return", "set",
)

TERMOS_FORTES: frozenset[str] = frozenset(t for t in (_normalizar(x) for x in _FORTES_BRUTO) if t)
TERMOS_POLISSEMICOS: frozenset[str] = frozenset(
    t for t in (_normalizar(x) for x in _POLISSEMICOS_BRUTO) if t) - TERMOS_FORTES
TERMOS_AMBIGUOS: frozenset[str] = frozenset(
    t for t in (_normalizar(x) for x in _AMBIGUOS_BRUTO) if t) - TERMOS_FORTES - TERMOS_POLISSEMICOS

# Mínimo de sinais fracos DISTINTOS (conceitos ambíguos + polissêmicos), escritos pela
# pessoa, para valer como contexto combinado.
MINIMO_AMBIGUOS = 2


# Termos que só são técnicos na forma ORIGINAL de acrônimo: "DOM" (Document Object
# Model) é técnico; "dom" (talento, título, "Dom Pedro") é português comum. A busca
# continua casando pelo token normalizado, mas o SINAL técnico só vale se a pessoa
# escreveu em maiúsculas.
_ACRONIMOS_BRUTO = ("dom",)
TERMOS_SO_ACRONIMO: frozenset[str] = frozenset(t for t in (_normalizar(x) for x in _ACRONIMOS_BRUTO) if t)


def tokens_do_sinal(tokens: list[str], texto: str | None) -> list[str]:
    """Os tokens que podem contar como SINAL: tira os que só valem em maiúsculas
    ("dom") quando a frase original não os traz como acrônimo ("DOM")."""
    if not TERMOS_SO_ACRONIMO:
        return tokens
    maiusculas = {_normalizar(m) for m in re.findall(r"(?<![A-Za-zÀ-ÿ])[A-ZÀ-Ý]{2,}(?![A-Za-zÀ-ÿ])", texto or "")}
    return [t for t in tokens if t not in TERMOS_SO_ACRONIMO or t in maiusculas]


def termos_ambiguos(tokens: list[str]) -> set[str]:
    """Os sinais FRACOS distintos que a pessoa escreveu: conceitos ambíguos
    ("função", "classe") e palavras de sintaxe polissêmicas ("for", "print")."""
    return {t for t in tokens if t in TERMOS_AMBIGUOS or t in TERMOS_POLISSEMICOS}


def sinal_tecnico(tokens: list[str]) -> str:
    """Nível do sinal técnico ESCRITO pela pessoa (sinônimo nunca conta):
    'forte'       - um termo inequívoco (python, css, append, try...);
    'combinado'   - >= 2 sinais fracos distintos (ambíguos/polissêmicos);
    'polissemico' - só UM polissêmico ("como usar for"): permite resposta direta bem
                    reconhecida, nunca oferta;
    'nenhum'      - o resto (inclusive um único conceito ambíguo)."""
    if any(t in TERMOS_FORTES for t in tokens):
        return "forte"
    fracos = termos_ambiguos(tokens)
    if len(fracos) >= MINIMO_AMBIGUOS:
        return "combinado"
    if fracos and fracos <= TERMOS_POLISSEMICOS:
        return "polissemico"
    return "nenhum"


def tem_contexto_tecnico(tokens: list[str]) -> bool:
    """Compatibilidade: True se o sinal é forte, combinado ou polissêmico."""
    return sinal_tecnico(tokens) != "nenhum"
