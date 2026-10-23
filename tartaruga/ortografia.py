"""Tolerância a erros de digitação em termos técnicos conhecidos ("flexbos", "dicionaro", "cosnt", "awiat").

Estratégia conservadora, sem lista de trocas prontas:

* só a palavra que a base NÃO conhece pode ser corrigida (tudo o que aparece em qualquer texto da base é "conhecido");
* o candidato vem do VOCABULÁRIO TÉCNICO da base (títulos, perguntas, símbolos de código, sinais técnicos), tem a mesma
  letra inicial, comprimento parecido e distância de edição pequena (1 troca/omissão/inserção/transposição; 2 só em
  palavras longas), e precisa ser ÚNICO (empate = não corrige);
* a frase corrigida só vale se a busca na base a RESOLVE (a busca já exige evidência forte) e a original não resolvia;
* palavras curtas (< 5 letras) nunca são corrigidas;
* palavras VÁLIDAS do português a uma edição de um termo técnico (lista gerada com o corretor do Windows) nunca são
  corrigidas: "lambada" é português, não erro de "lambda". Sem essa lista a correção fica desligada.

Assim uma frase do dia a dia ("listra de zebra") continua sendo dia a dia: a correção só existe se a base responde
à versão corrigida com a mesma exigência de uma pergunta digitada certa.
"""
import re

from .caminhos import recurso
from .contexto_conversa import simbolos_do_topico
from .sinonimos import TERMOS_AMBIGUOS, TERMOS_FORTES, TERMOS_POLISSEMICOS
from .vetorizador import STOPWORDS_BUSCA, remover_acentos, tokenizar

TAMANHO_MINIMO = 5
TAMANHO_LONGO = 9          # a partir daqui, até 2 edições


def distancia(a: str, b: str, limite: int) -> int:
    """Damerau-Levenshtein (transposição de vizinhas conta 1), cortada em limite+1."""
    if abs(len(a) - len(b)) > limite:
        return limite + 1
    anterior2, anterior = None, list(range(len(b) + 1))
    for i, ca in enumerate(a, 1):
        atual = [i]
        for j, cb in enumerate(b, 1):
            custo = 0 if ca == cb else 1
            valor = min(anterior[j] + 1, atual[j - 1] + 1, anterior[j - 1] + custo)
            if anterior2 is not None and i > 1 and j > 1 and ca == b[j - 2] and a[i - 2] == cb:
                valor = min(valor, anterior2[j - 2] + 1)
            atual.append(valor)
        anterior2, anterior = anterior, atual
        if min(atual) > limite:
            return limite + 1
    return anterior[-1]


ARQUIVO_PROTECAO = "palavras_validas_vizinhas.txt"


def palavras_validas_vizinhas() -> frozenset[str]:
    """Palavras VÁLIDAS do português a uma edição de um termo técnico ("lambada" x "lambda"); nunca são corrigidas.

    Vem de dados/palavras_validas_vizinhas.txt (gerado com o corretor ortográfico do
    Windows). Sem o arquivo a lista é None: a correção fica DESLIGADA (falha para o lado seguro).
    """
    global _PROTECAO
    if _PROTECAO is None:
        caminho = recurso("dados", ARQUIVO_PROTECAO)
        try:
            _PROTECAO = frozenset(caminho.read_text(encoding="utf-8").split())
        except OSError:
            _PROTECAO = frozenset({"<ausente>"})            # marca "ausente" sem recomputar a cada frase
    return _PROTECAO


_PROTECAO: frozenset[str] | None = None


def protecao_disponivel() -> bool:
    return "<ausente>" not in palavras_validas_vizinhas()


def _palavras(texto: str) -> set[str]:
    return set(tokenizar(texto, set()))


def _vocabularios(base) -> tuple[frozenset[str], frozenset[str]]:
    """(conhecidas, técnicas) da base curada; recalculado se a base mudar de tamanho."""
    chave = len(base.entradas)
    cache = getattr(base, "_vocabulario_ortografia", None)
    if cache and cache[0] == chave:
        return cache[1], cache[2]
    conhecidas: set[str] = set()
    tecnicas: set[str] = set(TERMOS_FORTES) | set(TERMOS_AMBIGUOS) | set(TERMOS_POLISSEMICOS)
    for entrada in base.entradas:
        if entrada.get("aprendido"):
            continue
        conhecidas |= _palavras(" ".join([entrada["titulo"], entrada.get("resposta", ""), entrada.get("codigo", "")]
                                         + list(entrada.get("perguntas", []))))
        tecnicas |= _palavras(entrada["titulo"] + " " + " ".join(entrada.get("perguntas", [])))
        tecnicas |= simbolos_do_topico(entrada)
    conhecidas |= tecnicas
    tecnicas = {t for t in tecnicas if len(t) >= TAMANHO_MINIMO and t not in STOPWORDS_BUSCA}
    resultado = (frozenset(conhecidas), frozenset(tecnicas))
    base._vocabulario_ortografia = (chave, *resultado)
    return resultado


def _candidato(palavra: str, tecnicas: frozenset[str]) -> str | None:
    limite = 2 if len(palavra) >= TAMANHO_LONGO else 1
    melhores: list[tuple[int, str]] = []
    for termo in tecnicas:
        if termo[0] != palavra[0] or abs(len(termo) - len(palavra)) > limite:
            continue
        d = distancia(palavra, termo, limite)
        if 0 < d <= limite:
            melhores.append((d, termo))
    if not melhores:
        return None
    melhores.sort()
    if len(melhores) > 1 and melhores[0][0] == melhores[1][0]:
        return None                           # empate: não adivinha
    return melhores[0][1]


def corrigir(base, texto: str) -> str | None:
    """A frase com as palavras desconhecidas trocadas pelo termo técnico mais próximo, ou None.

    Devolve None se nada foi corrigido ou se a versão corrigida não é resolvida pela base (o chamador então segue
    com a frase original). A original já deve ter sido tentada e falhado: aqui só se decide se a correção resolve.
    """
    if not protecao_disponivel():
        return None
    protegidas = palavras_validas_vizinhas()
    conhecidas, tecnicas = _vocabularios(base)
    trocas: dict[str, str] = {}
    for palavra in re.findall(r"[\wÀ-ÿ]+", texto):
        norm = remover_acentos(palavra.lower())
        if len(norm) < TAMANHO_MINIMO or norm in STOPWORDS_BUSCA or norm in trocas or norm in protegidas:
            continue
        if norm in conhecidas or any(t in conhecidas for t in tokenizar(norm, set())):
            continue                          # a base guarda as palavras no singular ("condicionais" -> "condicionai")
        candidato = _candidato(norm, tecnicas)
        if candidato:
            trocas[norm] = candidato
    if not trocas:
        return None

    def trocar(m):
        norm = remover_acentos(m.group(0).lower())
        return trocas.get(norm, m.group(0))

    corrigida = re.sub(r"[\wÀ-ÿ]+", trocar, texto)
    return corrigida if base.buscar(corrigida) is not None else None
