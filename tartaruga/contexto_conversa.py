"""Uso do contexto da conversa para desambiguar e resolver referências.

Regras de projeto (todas medidas e testadas):

- O contexto é SÓ o último tópico curado que a Tartaruga realmente explicou nesta sessão, até
  `JANELA_TURNOS` turnos atrás. Nada é inventado; "limpar conversa" esquece.
- O contexto não vira licença para tratar o dia a dia como programação: ele só DESTRAVA entradas da
  vizinhança do tópico recente (o próprio e os relacionados) e a evidência da etapa 1 continua
  valendo (>= 50% das palavras distintas da pergunta explicadas pela entrada; nota ponderada).
  "Como organizar uma lista de convidados?" depois de falar de listas continua sem resposta técnica.
- Referência ("isso", "dessa forma", "no exemplo anterior") SEM contexto recebe uma mensagem honesta,
  nunca um chute. COM contexto e sem candidata, a Tartaruga confirma o tópico recente com UMA opção.
"""
import re

from .conhecimento import EVIDENCIA_MINIMA_FORTE
from .sinonimos import SINONIMOS, TERMOS_AMBIGUOS, TERMOS_FORTES, TERMOS_POLISSEMICOS
from .vetorizador import STOPWORDS_BUSCA, remover_acentos, tokenizar

JANELA_TURNOS = 3
LIMIAR_CONTEXTO = 0.25
# Evidência mínima (fração das palavras distintas explicadas pela entrada) para o contexto DESTRAVAR
# uma entrada da vizinhança. Bem acima do 0,5 da etapa 1: o contexto sozinho não pode transformar
# "organizar uma lista de convidados" (2 de 3 palavras explicadas) em dúvida técnica.
EVIDENCIA_MINIMA_CONTEXTO = 0.8
MAX_PALAVRAS_REFERENCIA = 10      # uma frase longa com "isso" no meio não é só uma referência

_REFERENCIAS = re.compile(
    r"\b(?:isso|disso|nisso|nisto|disto|dessa forma|desta forma|desse jeito|deste jeito|dessa maneira|"
    r"desse modo|desse exemplo|deste exemplo|no exemplo anterior|do exemplo anterior|o exemplo anterior|"
    r"a mesma coisa|o mesmo|nele|nela)\b")


def _normal(texto: str) -> str:
    return re.sub(r"\s+", " ", re.sub(r"[^\w\s]", " ", remover_acentos(texto.lower()))).strip()


def tem_referencia(texto: str) -> bool:
    """A frase remete a algo já dito ("isso", "dessa forma", "no exemplo anterior")."""
    return bool(_REFERENCIAS.search(_normal(texto)))


# Verbos e palavras de PERGUNTA sem assunto próprio: "como funciona isso?", "o que acontece nisso?",
# "me explica isso melhor". Não contam como conteúdo novo.
_NEUTRAS = frozenset({
    "acontece", "aconteceu", "ocorre", "significa", "serve", "ajuda", "funcionam", "faz", "fazer",
    "faco", "usar", "uso", "explica", "explicar", "explique", "ensina", "ensinar", "mostra", "mostrar",
    "entender", "entendi", "saber", "detalhe", "detalhes", "mais", "melhor", "agora", "tambem", "ainda",
    "outra", "vez", "novo", "denovo", "pode", "poderia", "quero", "queria", "gostaria", "preciso",
})


# Verbos GENÉRICOS de pergunta ("isso ACEITA append?", "como ACESSAR uma chave nisso?", "isso pode
# RECEBER parâmetros?"): dizem o que se quer FAZER com o assunto, não qual é o assunto. Não valem como
# conteúdo novo nem contra a evidência da entrada. Ficam de fora de propósito os verbos que já são
# técnicos ou dizem o assunto (somar, ordenar, copiar, remover, adicionar, percorrer, criar...).
_VERBOS_GENERICOS = frozenset({
    "aceita", "aceitam", "aceitar", "acessa", "acessam", "acessar", "recebe", "recebem", "receber",
    "permite", "permitem", "permitir", "suporta", "suportam", "suportar", "aplica", "aplicam", "aplicar",
    "existe", "existem", "existir", "vale", "valem", "valer", "usa", "usam", "serve", "servem", "servir",
    "funcionam", "ajuda", "ajudam", "ajudar", "cabe", "cabem", "tem", "temos", "ter", "da", "dao", "dar",
    "pode", "podem", "poder", "deve", "devem", "dever", "consegue", "conseguem", "conseguir",
    "guarda", "guardam", "guardar",
})

# Verbos que FAZEM a pergunta ("isso aceita...", "isso permite...", "isso pode..."). Dos genéricos, ficam de
# fora "tem", "dá", "cabe", "vale": "isso tem nome" é afirmação do dia a dia, não pergunta ao assunto.
_VERBOS_DE_PERGUNTA = frozenset({
    "aceita", "aceitam", "aceitar", "permite", "permitem", "permitir", "suporta", "suportam", "suportar",
    "pode", "podem", "poder", "consegue", "conseguem", "conseguir", "funciona", "funcionam", "serve", "servem",
    "ajuda", "ajudam", "recebe", "recebem", "receber", "acessa", "acessam", "acessar", "existe", "existem",
})
_INICIO_DE_PERGUNTA = re.compile(
    r"^(?:e )?(?:como|o que|oque|qual|quais|onde|quando|por que|porque|quem|quanto|quantos|quantas|para que|"
    r"existe|tem como|posso|pode|da para|d[aá] pra)\b")


def forma_de_pergunta(texto: str) -> bool:
    """A frase PERGUNTA algo ao assunto: tem "?", começa como pergunta ou usa um verbo de pergunta
    ("isso aceita append", "isso permite get"). "isso é um objeto" e "isso tem nome" são afirmações do dia
    a dia: só uma pergunta pode ser resolvida pelo contexto técnico (a confirmação de referência pura, que
    apenas PERGUNTA de volta, não depende disto)."""
    normal = _normal(texto)
    return ("?" in texto or bool(_INICIO_DE_PERGUNTA.match(normal))
            or any(p in _VERBOS_DE_PERGUNTA for p in normal.split()))


def _sem_verbos_genericos(consulta: str) -> str:
    return " ".join(p for p in consulta.split() if p not in _VERBOS_GENERICOS)


def referencia_pura(texto: str) -> bool:
    """A frase SÓ retoma o que foi dito: tirando as referências, as stopwords e os verbos neutros de
    pergunta, não sobra palavra de conteúdo. "isso é um absurdo", "isso serve para lista de compras?",
    "nele tem açúcar?" trazem assunto novo (não são referência ao tópico técnico); "e isso?",
    "como funciona isso?", "o que acontece nisso?" são referência pura."""
    if not tem_referencia(texto):
        return False
    restantes = [p for p in sem_referencias(texto).split()
                 if p not in STOPWORDS_BUSCA and p not in _NEUTRAS and p not in _VERBOS_GENERICOS]
    return not restantes


def sem_referencias(texto: str) -> str:
    """A frase sem as palavras de referência (que não dizem nada sobre o ASSUNTO)."""
    return re.sub(r"\s+", " ", _REFERENCIAS.sub(" ", _normal(texto))).strip()


def topico_recente(bot):
    """A entrada CURADA explicada há pouco nesta sessão, ou None (nunca inventa)."""
    dialogo = bot.dialogo
    identificador = dialogo.ultimo_topico
    if not identificador or dialogo.turnos - dialogo.turno_do_topico > JANELA_TURNOS:
        return None
    return next((e for e in bot.base.entradas
                 if e["id"] == identificador and not e.get("aprendido")), None)


def vizinhanca(bot, entrada) -> set[str]:
    """O tópico recente e sua FAMÍLIA (só conteúdo curado): os mais próximos no espaço vetorial e as
    entradas que dividem uma palavra do título ("Listas", "Ordenar listas", "Somar itens de uma lista")."""
    ids = {entrada["id"]}
    ids.update(r.identificador for r in bot.base.relacionados(entrada["id"], 3) if not r.aprendido)
    palavras = set(tokenizar(entrada["titulo"], STOPWORDS_BUSCA))
    if palavras:
        ids.update(e["id"] for e in bot.base.entradas
                   if not e.get("aprendido") and palavras & set(tokenizar(e["titulo"], STOPWORDS_BUSCA)))
    return ids


def candidatas_contextuais(bot, texto: str, ids: set[str] | None,
                           evidencia_minima: float = EVIDENCIA_MINIMA_FORTE):
    """Entradas curadas que EXPLICAM as palavras da pergunta (evidência da etapa 1), restritas
    aos `ids` quando informados. Sem `ids`, qualquer entrada curada que passe na evidência."""
    consulta = sem_referencias(texto)
    if tem_referencia(texto):
        consulta = _sem_verbos_genericos(consulta)          # só em frases com referência
    if not consulta:
        return []
    achados = bot.base.buscar_varios(
        consulta, quantidade=len(bot.base.entradas), limiar=LIMIAR_CONTEXTO,
        ponderar_cobertura=True, evidencia_minima=evidencia_minima, apenas_curado=True)
    return [r for r in achados if ids is None or r.identificador in ids]


_ELIPTICA = re.compile(
    r"^(?:(?:beleza|blz|ok|certo|entao|hum|ah|show|legal|tudo bem)\s+)*e\s+(?:o|a|os|as|um|uma)?\s*(?P<resto>[a-z0-9_ ]+?)\s*$")


def eliptica(texto: str) -> str | None:
    """"e o finally?", "beleza, e o get?": pergunta curta que retoma o assunto sem dizer "isso". Devolve só o
    que foi perguntado ("finally") ou None. Exige "?" e no máximo 3 palavras depois do "e"."""
    if "?" not in texto:
        return None
    achou = _ELIPTICA.match(_normal(texto))
    if not achou or len(achou.group("resto").split()) > 3:
        return None
    resto = achou.group("resto")
    if tem_referencia(resto) or _INICIO_DE_PERGUNTA.match(resto):
        return None                # "e isso?" é referência pura; "e como somar?" já é uma pergunta completa
    return resto


_LINGUAGENS_NOMEADAS = frozenset({"javascript", "python", "css", "html", "js"})


def _nomeia_o_assunto(bot, texto: str, resultado) -> bool:
    """A frase mostra que o assunto da entrada é DE FATO o pedido: (a) alguma palavra dela aparece no TÍTULO
    da entrada ("funciona com dicionário" nomeia "Dicionários"), ou (b) a entrada explica pelo menos DUAS
    palavras distintas ("pares de chave e valor"). Uma palavra só, achada por acaso numa pergunta da entrada
    ("acessar a casa" x "casas decimais" de f-string), não basta."""
    palavras = set(tokenizar(_sem_verbos_genericos(sem_referencias(texto)), STOPWORDS_BUSCA)) - _LINGUAGENS_NOMEADAS
    if palavras & set(tokenizar(resultado.titulo, STOPWORDS_BUSCA)):
        return True
    posicao = next((i for i, e in enumerate(bot.base.entradas) if e["id"] == resultado.identificador), None)
    if posicao is None:
        return False
    termos = bot.base._termos_por_entrada[posicao]
    explicadas = sum(1 for w in palavras
                     if w in termos or any(s in termos for s in SINONIMOS.get(w, ())))
    return explicadas >= 2


_CRASES = re.compile(r"`([^`]+)`")
_ATRIBUTO = re.compile(r"\.([A-Za-z_][A-Za-z0-9_]*)")
_CHAMADA = re.compile(r"\b([A-Za-z_][A-Za-z0-9_]*)\(")


def _tokens_simples(texto: str) -> set[str]:
    """Palavras normalizadas (minúsculas, sem acento, singular) de 3+ letras."""
    return {p for p in tokenizar(texto, set()) if len(p) >= 3}


_PALAVRA_CHAVE = re.compile(
    r"(?m)^\s*(?:}\s*)?(if|elif|else|for|while|try|except|finally|catch|with|def|class|import|from|return|raise|yield|"
    r"async|await|switch|case|function)\b")


def simbolos_do_topico(entrada) -> set[str]:
    """Símbolos TÉCNICOS do conteúdo: nomes de métodos/funções do código (".get", "sorted(") e trechos entre
    crases da resposta ("`sort()`", "`set`"). Nomes de variáveis de EXEMPLO ("nome", "valor", "item") não
    são símbolos: só o que é inequivocamente API."""
    codigo = entrada.get("codigo", "")
    simbolos = _tokens_simples(" ".join(_ATRIBUTO.findall(codigo) + _CHAMADA.findall(codigo)
                                        + _PALAVRA_CHAVE.findall(codigo)))       # "finally:" / "else:" também são API
    for trecho in _CRASES.findall(entrada.get("resposta", "")):
        simbolos |= _tokens_simples(trecho)
    return simbolos


def vocabulario_do_topico(entrada) -> set[str]:
    """Tudo o que o tópico diz: as perguntas, a resposta e o código (normalizado, singular)."""
    texto = " ".join(entrada.get("perguntas", [])) + " " + entrada.get("resposta", "") + " " + entrada.get("codigo", "")
    return _tokens_simples(texto)


def _entradas_da_vizinhanca(bot, recente):
    """O tópico recente primeiro e depois os vizinhos (só curado), na ordem da base."""
    ids = vizinhanca(bot, recente) - {recente["id"]}
    return [recente] + [e for e in bot.base.entradas if e["id"] in ids]      # `vizinhanca` já só tem curado


def _como_escritas(texto: str, palavras: set[str]) -> list[str]:
    """As palavras normalizadas do reconhecimento na FORMA em que a pessoa as escreveu ("items", não "item")."""
    escritas = {}
    for palavra in sem_referencias(texto).split():
        normalizada = tokenizar(palavra, set())
        if normalizada:
            escritas.setdefault(normalizada[0], palavra)
    return [escritas.get(p, p) for p in sorted(palavras)]


def _conteudo_do_topico(bot, texto: str, recente):
    """Referência a algo que o PRÓPRIO tópico recente contém ("isso permite get?", "isso pode ter métodos?"):
    todas as palavras da frase (sem referência e sem verbos genéricos) estão no vocabulário do tópico e ao menos
    uma é SÍMBOLO técnico (código/crases) ou termo técnico catalogado. Só o tópico recente, só com referência."""
    consulta = _sem_verbos_genericos(sem_referencias(texto))
    palavras = {p for p in tokenizar(consulta, set()) if p not in STOPWORDS_BUSCA} if consulta else set()
    vocabulario = vocabulario_do_topico(recente)
    if not all(p in vocabulario or any(s in vocabulario for s in SINONIMOS.get(p, ())) for p in palavras):
        return None
    simbolos = simbolos_do_topico(recente)
    tecnicos = TERMOS_FORTES | TERMOS_AMBIGUOS | TERMOS_POLISSEMICOS
    if not any(p in simbolos or p in tecnicos for p in palavras):
        return None
    return palavras


def _com_abertura(bot, abertura: str, resultado) -> str:
    return abertura + "\n\n" + bot._formatar_conhecimento(resultado)


def resolver_com_contexto(bot, texto: str, apenas_resolucao: bool = False):
    """Devolve (texto, intencao) ou None. Chamado quando a pergunta ficou sem resposta direta."""
    recente = topico_recente(bot)
    resto = eliptica(texto)
    if resto is not None:
        texto = resto + "?"        # "e o finally?" pergunta por "finally" ao assunto recente
    referencia = (tem_referencia(texto) and len(_normal(texto).split()) <= MAX_PALAVRAS_REFERENCIA) or resto is not None
    pura = referencia and referencia_pura(texto)

    if recente is None:
        if pura:
            return ("Não sei a que você se refere: ainda não falamos de nenhum assunto por aqui. "
                    "Sobre o que você quer saber?"), "esclarecimento"
        return None

    pergunta = forma_de_pergunta(texto)

    # 1) O contexto destrava as entradas da VIZINHANÇA do tópico recente (só para PERGUNTAS).
    candidatas = candidatas_contextuais(bot, texto, vizinhanca(bot, recente), EVIDENCIA_MINIMA_CONTEXTO) if pergunta else []
    if candidatas:
        alvo = candidatas[0]
        abertura = (f"Como estávamos falando de **{recente['titulo']}**, entendi que você quer saber "
                    f"sobre **{alvo.titulo}**.")
        return _com_abertura(bot, abertura, alvo), "duvida_programacao"

    if not referencia:
        return None

    # 2) Referência que nomeia OUTRO assunto ("dessa forma funciona com dicionário?"): responde o
    #    assunto nomeado, ligando ao que vimos.
    outras = [r for r in candidatas_contextuais(bot, texto, None, EVIDENCIA_MINIMA_CONTEXTO)
              if _nomeia_o_assunto(bot, texto, r)] if pergunta else []
    if outras:
        abertura = f"Ligando ao que vimos (**{recente['titulo']}**), você está perguntando de **{outras[0].titulo}**."
        return _com_abertura(bot, abertura, outras[0]), "duvida_programacao"

    # 2b) Referência a algo que o CONTEÚDO do tópico recente (ou de um vizinho dele) contém ("isso permite get?",
    #     "isso permite pop?"): símbolo do código ou termo técnico presente no conteúdo da entrada, com todas as
    #     demais palavras também explicadas por ELA. O próprio tópico tem prioridade; depois, os vizinhos.
    if pergunta:
        for entrada in _entradas_da_vizinhanca(bot, recente):
            palavras = _conteudo_do_topico(bot, texto, entrada)
            if not palavras:
                continue
            exibidas = ", ".join(f"`{p}`" for p in _como_escritas(texto, palavras))
            if entrada["id"] == recente["id"]:
                abertura = f"Sim, isso faz parte de **{recente['titulo']}** ({exibidas}). Vale rever o assunto:"
            else:
                abertura = (f"Como estávamos falando de **{recente['titulo']}**: {exibidas} faz parte de "
                            f"**{entrada['titulo']}**.")
            from .conhecimento import Resultado
            resultado = Resultado(entrada["id"], entrada["titulo"], entrada["resposta"], entrada.get("codigo", ""), 0)
            return _com_abertura(bot, abertura, resultado), "duvida_programacao"

    if apenas_resolucao:
        return None

    # 3) Referência PURA ("e isso?"): confirma o tópico recente com UMA opção, sem inventar mais.
    #    Com conteúdo novo na frase ("isso é um absurdo", "nele tem açúcar?") NÃO há confirmação: a
    #    frase segue o fluxo normal, sem transformar o dia a dia em oferta técnica.
    if not pura:
        return None
    titulo = recente["titulo"]
    bot.dialogo.contexto.opcoes_semanticas = [("conhecimento:" + recente["id"], titulo)]
    bot.dialogo.contexto.consulta_opcoes = ""          # confirmação: não é para lembrar a frase "isso"
    return ("\n".join([
        f"Estávamos falando de **{titulo}**. É sobre isso que você quer saber mais?",
        "",
        f"1. {titulo}",
        "",
        'Responda "sim" para eu continuar nesse assunto, ou "não" se for outro.',
    ])), "esclarecimento"


def resolver_referencia_contextual(bot, texto: str):
    """Frase com referência + tópico recente: resolve (resposta contextual válida) ou, se a referência é PURA,
    confirma o tópico recente. Roda ANTES do classificador, que às vezes leva a referência a outra intenção
    ("isso suporta extend?" e "faz desse jeito suporta" -> capacidades). Sem tópico recente NÃO age: a
    mensagem honesta ("ainda não falamos de nenhum assunto") continua no caminho de incerteza.
    Devolve (texto, intencao) ou None."""
    if eliptica(texto) is None and (not tem_referencia(texto) or len(_normal(texto).split()) > MAX_PALAVRAS_REFERENCIA):
        return None
    if topico_recente(bot) is None:
        return None
    return resolver_com_contexto(bot, texto)


def escolher_pelo_contexto(bot, opcoes):
    """Entre opções de esclarecimento [(chave, titulo)], devolve a ÚNICA que está na vizinhança do
    tópico recente (para responder sem perguntar), ou None se não houver contexto ou houver dúvida."""
    recente = topico_recente(bot)
    if recente is None or len(opcoes) < 2:
        return None
    ids = vizinhanca(bot, recente)
    dentro = [(chave, titulo) for chave, titulo in opcoes if chave.removeprefix("conhecimento:") in ids]
    return (dentro[0], recente) if len(dentro) == 1 else None
