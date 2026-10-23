"""
Dispatcher da geração de código: decide O QUE montar e COM QUAIS parâmetros.

O fluxo de "cria um formulário de login em html":

    1. detectar a LINGUAGEM        -> html
    2. detectar o PADRÃO           -> formulario
    3. extrair os PARÂMETROS       -> campos=["usuario", "senha"]
    4. chamar o gerador certo      -> geradores.html.formulario(campos=...)

Cada etapa usa contagem de palavras-chave, no mesmo espírito de
`dialogo.py::detectar_assunto_capacidade` — sem aprendizado de máquina aqui,
porque a tarefa é pequena o bastante para regras claras funcionarem bem, e
regras são mais fáceis de auditar que um classificador para algo que decide
QUE CÓDIGO SERÁ ESCRITO.

Se nada bater com confiança suficiente, `gerar()` devolve None — e o núcleo
trata isso como "não sei montar isso", nunca como "vou tentar mesmo assim".
"""

import re
from dataclasses import dataclass

from .geradores import css, html, javascript
from .vetorizador import remover_acentos as _sem_acentos, singularizar, tokenizar
from .interpretacao import normalizar_prosa

# ---------------------------------------------------------------------------
# Detecção de linguagem
# ---------------------------------------------------------------------------

PALAVRAS_HTML = {"html"}
PALAVRAS_CSS = {"css", "estilo", "estilizado", "estilizar"}
PALAVRAS_JAVASCRIPT = {"javascript", "js"}

# Padrões que, na ausência de "html"/"css"/"javascript" explícito, têm uma
# linguagem óbvia.
PADROES_SO_HTML = {
    "landing",
    "pagina", "formulario", "navbar", "card", "lista", "tabela",
    "modal", "tabs", "accordion", "breadcrumb", "dropdown",
}
PADROES_SO_CSS = {
    "flexbox", "grid", "centralizar", "variaveis", "responsivo",
    "sombra", "transicao", "animacao",
}
_VERBO_GERACAO = re.compile(r"\b(?:crie|cria|criar|gere|gera|gerar|monte|monta|desenvolva|faca)\b")
# Etapa 1 aplicada à GERAÇÃO: um padrão de HTML/CSS reconhecido só por uma palavra ambígua/cotidiana ("responsivo",
# "lista", "tabela", "página", "formulário"...) não basta sozinho — mesma lógica de TERMOS_AMBIGUOS/TERMOS_FORTES já
# usada na busca da base (sinonimos.py): sozinho, exige uma ÂNCORA (verbo de geração, a palavra da linguagem escrita
# pela pessoa, ou um tópico técnico recém-explicado). "flexbox" e "grid" são os únicos artefatos sem outro sentido
# corrente, então dispensam âncora — ver a revisão que confirmou isso com os conjuntos negativos da Etapa 1.
ARTEFATOS_SEM_VERBO = {"flexbox", "grid"}
# Os nomes de padrão de JavaScript (debounce, curry, singleton...) não
# colidem com nenhum nome de HTML/CSS, então não precisam de uma lista "só
# JS" separada — ver a checagem em `_detectar_linguagem`.
# "botao" existe em HTML e CSS — decidido por contexto, ver `_detectar_linguagem`.


def _detectar_linguagem(
    texto_normalizado: str,
    padrao_html: str | None,
    padrao_css: str | None,
    padrao_js: str | None,
) -> str | None:
    """Decide entre HTML, CSS e JavaScript.

    Ordem de decisão: palavra explícita e sem ambiguidade > padrão de
    JavaScript (nomes exclusivos, então um achado já decide) > padrão que só
    existe em HTML ou CSS > pistas de estilo (cor, borda...) para o caso
    ambíguo "botão" > None (ambíguo demais ou nenhum padrão reconhecido).
    """
    tem_html = any(p in texto_normalizado for p in PALAVRAS_HTML)
    tem_css = any(p in texto_normalizado for p in PALAVRAS_CSS)
    tem_js = any(p in texto_normalizado for p in PALAVRAS_JAVASCRIPT)

    marcadas = {
        linguagem
        for linguagem, presente in (("html", tem_html), ("css", tem_css), ("javascript", tem_js))
        if presente
    }
    if len(marcadas) == 1:
        return next(iter(marcadas))

    if padrao_js and not padrao_html and not padrao_css:
        return "javascript"

    if padrao_html in PADROES_SO_HTML:
        return "html"
    if padrao_css in PADROES_SO_CSS:
        return "css"

    # "botao" sem palavra explícita: presença de cor ou termo de estilo
    # indica CSS; do contrário, HTML (o elemento <button> em si) é o padrão
    # mais provável de quem só disse "cria um botão".
    if padrao_html == "botao" or padrao_css == "botao":
        if tem_css or any(cor in texto_normalizado for cor in css.CORES):
            return "css"
        return "html"

    return None


# ---------------------------------------------------------------------------
# Detecção de padrão (o que montar, dentro da linguagem já decidida)
# ---------------------------------------------------------------------------

# ---------------------------------------------------------------------------
# Cada padrão tem palavras FORTES (peso 2) — o próprio nome do padrão ou um
# sinônimo direto e inequívoco — e palavras FRACAS (peso 1) — pistas de
# contexto que ajudam a REFINAR o padrão (que tipo de formulário? que cor de
# botão?) mas não deveriam sozinhas DECIDIR o padrão.
#
# Bug real que motivou a separação: "monta uma navbar com início, sobre e
# contato" perdia para "formulario", porque "contato" é palavra-chave de
# formulário de contato e empatava 1 a 1 com "navbar" — a ordem da lista
# desempatava a favor do candidato errado. Com pesos, "navbar" (forte, peso
# 2) supera "contato" (fraca, peso 1) mesmo com uma palavra cada.
# ---------------------------------------------------------------------------
PADROES_HTML: list[tuple[str, set[str], set[str]]] = [
    ("landing", {"landing", "landingpage", "lanepage"}, set()),
    ("navbar", {"navbar", "nav", "menu", "navegacao"}, set()),
    ("modal", {"modal", "popup"}, set()),
    ("tabs", {"tabs", "abas"}, set()),
    ("accordion", {"accordion", "sanfona", "acordeao"}, set()),
    ("breadcrumb", {"breadcrumb", "trilha"}, set()),
    ("dropdown", {"dropdown", "suspenso"}, {"select"}),
    ("formulario", {"formulario", "form"}, {"cadastro", "login", "contato", "registro"}),
    ("card", {"card", "cartao"}, set()),
    ("tabela", {"tabela"}, set()),
    ("lista", {"lista"}, set()),
    ("botao", {"botao", "button"}, set()),
    ("pagina", {"pagina", "site", "esqueleto"}, set()),
]

PADROES_CSS: list[tuple[str, set[str], set[str]]] = [
    ("flexbox", {"flexbox", "flex"}, set()),
    ("grid", {"grid", "grade"}, set()),
    ("responsivo", {"responsivo", "responsiva", "mobile", "celular"}, set()),
    ("sombra", {"sombra"}, {"elevacao", "shadow"}),
    ("transicao", {"transicao", "hover"}, set()),
    ("animacao", {"animacao", "keyframes"}, set()),
    ("variaveis", {"variavel", "variaveis", "tema"}, {"cores", "cor"}),
    ("centralizar", {"centralizar", "centraliza", "centralizado", "centro"}, set()),
    ("botao", {"botao", "button"}, set()),
]

PADROES_JAVASCRIPT: list[tuple[str, set[str], set[str]]] = [
    ("debounce", {"debounce"}, set()),
    ("throttle", {"throttle"}, set()),
    ("memoize", {"memoize", "memoization", "memorizacao"}, {"cache"}),
    ("curry", {"curry", "currying"}, set()),
    ("clone", {"clone", "clonagem", "clonar"}, {"profundo", "profunda"}),
    ("emissor", {"emissor", "eventemitter", "pubsub"}, {"evento", "eventos", "observador"}),
    ("retry", {"retry", "retentativa"}, {"tentar", "tentativa", "tentativas", "novamente"}),
    ("timeout", {"timeout"}, {"limite", "tempo"}),
    ("fetch", {"fetch", "requisicao"}, {"api", "assincrona", "assincrono", "http"}),
    ("classe", {"classe", "heranca", "class"}, {"extends", "poo", "privado"}),
    ("gerador", {"gerador", "generator", "iterador"}, {"yield"}),
    ("singleton", {"singleton"}, set()),
    ("proxy", {"proxy"}, {"validar", "validacao", "validador"}),
]


def _normalizar_candidatos(
    candidatos: list[tuple[str, set[str], set[str]]],
) -> list[tuple[str, set[str], set[str]]]:
    """Aplica a MESMA singularização do tokenizador às palavras-chave.

    Sem isto, "abas" (plural, escrito na lista acima) nunca bate com "aba"
    (o que `tokenizar()` produz para a entrada "cria abas em html") — a
    mesma armadilha já corrigida em `dialogo.py::_normalizar_palavras`.
    A lição se repete: dois pontos do sistema que comparam texto precisam
    normalizar do mesmo jeito, e a forma seguro é derivar um do outro, não
    manter listas paralelas que podem divergir silenciosamente.
    """
    return [
        (nome, {singularizar(p) for p in fortes}, {singularizar(p) for p in fracas})
        for nome, fortes, fracas in candidatos
    ]


PADROES_HTML = _normalizar_candidatos(PADROES_HTML)
PADROES_CSS = _normalizar_candidatos(PADROES_CSS)
PADROES_JAVASCRIPT = _normalizar_candidatos(PADROES_JAVASCRIPT)


def total_padroes() -> int:
    return len(PADROES_HTML) + len(PADROES_CSS) + len(PADROES_JAVASCRIPT)


def _melhor_padrao(
    tokens: set[str], candidatos: list[tuple[str, set[str], set[str]]]
) -> str | None:
    """Pontua cada padrão (fortes valem 2, fracas valem 1) e devolve o maior.

    A ordem da lista de candidatos só desempata quando a PONTUAÇÃO empata de
    verdade — não quando uma palavra fraca de um se cruza com a forte de
    outro, que é o caso que o esquema de pesos evita.
    """
    melhor, melhor_pontuacao = None, 0
    for nome, fortes, fracas in candidatos:
        pontuacao = 2 * len(tokens & fortes) + len(tokens & fracas)
        if pontuacao > melhor_pontuacao:
            melhor, melhor_pontuacao = nome, pontuacao
    return melhor


# ---------------------------------------------------------------------------
# Extração de parâmetros
# ---------------------------------------------------------------------------

PADRAO_LISTA_APOS_COM = re.compile(r"\bcom\s+(.+?)(?:\s+em\s+(?:html|css))?$", re.IGNORECASE)


def _itens_apos_com(texto: str) -> list[str] | None:
    """Extrai uma lista de nomes que vem depois de 'com'.

    "formulário com nome, email e mensagem" -> ["nome", "email", "mensagem"]
    """
    achado = PADRAO_LISTA_APOS_COM.search(texto)
    if not achado:
        return None
    trecho = re.sub(r"\s+e\s+", ", ", achado.group(1), flags=re.IGNORECASE)
    itens = [i.strip(" .?!") for i in trecho.split(",")]
    itens = [i for i in itens if i]
    return itens or None


# Tecnologias que o gerador NÃO monta (ele só faz HTML, CSS e JavaScript de front-end). Quando o pedido as cita,
# a resposta avisa o que foi ignorado em vez de entregar só o formulário como se fosse o pedido completo.
_NAO_GERADAS = {
    "php": "PHP", "mysql": "MySQL", "postgres": "PostgreSQL", "postgresql": "PostgreSQL", "sqlite": "SQLite",
    "mongodb": "MongoDB", "sql": "SQL", "node": "Node.js", "nodejs": "Node.js", "express": "Express",
    "django": "Django", "flask": "Flask", "fastapi": "FastAPI", "laravel": "Laravel", "react": "React",
    "vue": "Vue", "angular": "Angular", "typescript": "TypeScript", "backend": "back-end", "servidor": "servidor",
    "banco": "banco de dados", "bootstrap": "Bootstrap", "tailwind": "Tailwind",
}


def detectar_ignorados(texto_normalizado: str) -> tuple[str, ...]:
    """Tecnologias fora do que o gerador monta que o pedido menciona, na ordem em que aparecem, sem repetir."""
    nomes = []
    for token in re.findall(r"[a-z0-9]+", texto_normalizado):
        nome = _NAO_GERADAS.get(token)
        if nome and nome not in nomes:
            nomes.append(nome)
    return tuple(nomes)


_PALAVRAS_DE_ESTILO = {"tema", "escuro", "escura", "claro", "clara", "cor", "cores", "estilo", "estilizado", "fundo"}


def _eh_estilo(item: str) -> bool:
    """"tema escuro", "azul": pedido de estilo, não nome de campo do formulário."""
    palavras = _sem_acentos(item.lower()).split()
    return any(p in _PALAVRAS_DE_ESTILO or p in css.CORES for p in palavras)


def _numero(texto: str) -> int | None:
    achado = re.search(r"\b(\d+)\b", texto)
    return int(achado.group(1)) if achado else None


def _campos_formulario(texto_normalizado: str, texto_original: str) -> list[str]:
    """Decide os campos do formulário: explícitos, por tipo, ou um padrão razoável."""
    explicitos = _itens_apos_com(texto_original)
    if explicitos:
        # Só aceita como "campos" itens que soam como palavra única — uma
        # lista de frases longas provavelmente não é uma lista de campos.
        candidatos = [i for i in explicitos if len(i.split()) <= 3 and not detectar_ignorados(_sem_acentos(i))
                      and not _eh_estilo(i)]
        if candidatos:
            return [c.lower() for c in candidatos]

    if "login" in texto_normalizado or "entrar" in texto_normalizado:
        return ["usuario", "senha"]
    if "cadastro" in texto_normalizado or "registro" in texto_normalizado:
        return ["nome", "email", "senha"]
    return ["nome", "email", "mensagem"]  # padrão: formulário de contato


def _cor_botao(texto_normalizado: str) -> str:
    for cor in css.CORES:
        if cor in texto_normalizado:
            return cor
    return css.COR_PADRAO


def _tema(texto_normalizado: str) -> str:
    return "escuro" if "escuro" in texto_normalizado else "claro"


# ---------------------------------------------------------------------------
# Resultado e dispatcher principal
# ---------------------------------------------------------------------------

@dataclass
class ResultadoGeracao:
    """O código montado, pronto para ser mostrado."""

    codigo: str
    linguagem: str
    padrao: str
    descricao: str
    ignorados: tuple[str, ...] = ()


class Gerador:
    """Ponto de entrada único: recebe a frase, devolve o código montado ou None."""

    def gerar(self, texto: str, contexto_tecnico: bool = False) -> ResultadoGeracao | None:
        texto = normalizar_prosa(texto)
        tokens = set(tokenizar(texto, stopwords=set()))
        texto_normalizado = " ".join(tokens)

        padrao_html = _melhor_padrao(tokens, PADROES_HTML)
        padrao_css = _melhor_padrao(tokens, PADROES_CSS)
        padrao_js = _melhor_padrao(tokens, PADROES_JAVASCRIPT)

        # Decide a linguagem levando em conta os três candidatos, depois usa
        # o padrão daquela linguagem especificamente - "botao" pertence a
        # HTML e CSS, mas o padrão CERTO depende de qual linguagem venceu.
        linguagem = _detectar_linguagem(texto_normalizado, padrao_html, padrao_css, padrao_js)
        explicita = any(p in texto_normalizado for p in PALAVRAS_HTML | PALAVRAS_CSS | PALAVRAS_JAVASCRIPT)
        if linguagem and not explicita and re.search(r"\bpython\b", _sem_acentos(texto.lower())):
            return None      # "como criar uma lista em python": é dúvida de Python, não um template de HTML

        if linguagem == "html":
            padrao = padrao_html
        elif linguagem == "css":
            padrao = padrao_css
        elif linguagem == "javascript":
            padrao = padrao_js
        else:
            return None

        if padrao is None:
            return None

        # Etapa 1 na geração (HTML e CSS): sem palavra da linguagem escrita pela pessoa, um padrão ambíguo isolado
        # ("lista", "tabela", "página", "formulário", "responsivo", "centralizar"...) exige verbo de geração ou
        # contexto técnico recente. JavaScript fica de fora: seus nomes de padrão (debounce, memoize...) já não têm
        # sentido corrente fora de código.
        if (linguagem in ("html", "css") and padrao not in ARTEFATOS_SEM_VERBO and not explicita
                and not (contexto_tecnico or _VERBO_GERACAO.search(texto_normalizado))):
            return None

        resultado = self._montar(linguagem, padrao, texto, texto_normalizado)
        if resultado is not None:
            resultado.ignorados = detectar_ignorados(_sem_acentos(texto.lower()))
        return resultado

    def _montar(
        self, linguagem: str, padrao: str, texto: str, texto_normalizado: str
    ) -> ResultadoGeracao:
        if linguagem == "html":
            return self._montar_html(padrao, texto, texto_normalizado)
        if linguagem == "javascript":
            return self._montar_javascript(padrao, texto, texto_normalizado)
        return self._montar_css(padrao, texto, texto_normalizado)

    def _montar_html(self, padrao: str, texto: str, norm: str) -> ResultadoGeracao:
        if padrao == "landing":
            codigo = html.landing_page()
            descricao = "uma landing page responsiva com apresentação, benefícios e contato"
        elif padrao == "modal":
            codigo = html.modal()
            descricao = "uma janela modal"

        elif padrao == "tabs":
            abas = _itens_apos_com(texto)
            abas = [a for a in abas if len(a.split()) <= 3] if abas else None
            codigo = html.tabs(abas=abas)
            descricao = "um conjunto de abas"

        elif padrao == "accordion":
            itens = _itens_apos_com(texto)
            itens = [i for i in itens if len(i.split()) <= 4] if itens else None
            codigo = html.accordion(itens=itens)
            descricao = "uma sanfona (accordion)"

        elif padrao == "breadcrumb":
            caminho = _itens_apos_com(texto)
            caminho = [c for c in caminho if len(c.split()) <= 3] if caminho else None
            codigo = html.breadcrumb(caminho=caminho)
            descricao = "uma trilha de navegação"

        elif padrao == "dropdown":
            opcoes = _itens_apos_com(texto)
            opcoes = [o for o in opcoes if len(o.split()) <= 3] if opcoes else None
            codigo = html.dropdown(opcoes=opcoes)
            descricao = "um menu suspenso"

        elif padrao == "formulario":
            campos = _campos_formulario(norm, texto)
            codigo = html.formulario(campos=campos)
            descricao = f"um formulário com os campos {', '.join(campos)}"

        elif padrao == "navbar":
            links = _itens_apos_com(texto)
            links = [l for l in links if len(l.split()) <= 3] if links else None
            codigo = html.navbar(links=links)
            descricao = "uma barra de navegação"

        elif padrao == "card":
            codigo = html.card()
            descricao = "um cartão de conteúdo"

        elif padrao == "lista":
            itens = _itens_apos_com(texto)
            numero = _numero(texto)
            if not itens and numero:
                itens = [f"Item {i}" for i in range(1, min(numero, 20) + 1)]
            ordenada = "ordenada" in norm or "numerada" in norm
            codigo = html.lista(itens=itens, ordenada=ordenada)
            descricao = "uma lista " + ("ordenada" if ordenada else "não ordenada")

        elif padrao == "tabela":
            colunas = _itens_apos_com(texto)
            colunas = [c for c in colunas if len(c.split()) <= 3] if colunas else None
            linhas = _numero(texto) or 3
            codigo = html.tabela(colunas=colunas, linhas=linhas)
            descricao = f"uma tabela de {linhas} linhas"

        elif padrao == "botao":
            codigo = html.botao()
            descricao = "um botão"

        else:  # pagina
            codigo = html.pagina()
            descricao = "o esqueleto de uma página completa"

        return ResultadoGeracao(codigo=codigo, linguagem="html", padrao=padrao, descricao=descricao)

    def _montar_css(self, padrao: str, texto: str, norm: str) -> ResultadoGeracao:
        if padrao == "sombra":
            intensidade = next(
                (n for n in ("leve", "media", "forte") if n in norm or
                 (n == "media" and "media" in norm)),
                "media",
            )
            codigo = css.sombra(intensidade=intensidade)
            descricao = f"uma sombra de intensidade {intensidade}"

        elif padrao == "transicao":
            codigo = css.transicao()
            descricao = "uma transição suave com efeito hover"

        elif padrao == "animacao":
            codigo = css.animacao()
            descricao = "uma animação de entrada"

        elif padrao == "flexbox":
            centralizar = "centralizar" in norm or "centralizado" in norm or "centro" in norm
            direcao = "column" if ("coluna" in norm or "vertical" in norm) else "row"
            codigo = css.flexbox(direcao=direcao, centralizar=centralizar)
            descricao = "um layout flexbox" + (" centralizado" if centralizar else "")

        elif padrao == "grid":
            colunas = _numero(texto) or 3
            codigo = css.grid(colunas=colunas)
            descricao = f"um layout em grade de {colunas} colunas"

        elif padrao == "responsivo":
            codigo = css.responsivo()
            descricao = "uma regra responsiva para telas pequenas"

        elif padrao == "variaveis":
            tema = _tema(norm)
            codigo = css.variaveis(tema=tema)
            descricao = f"variáveis de cor no tema {tema}"

        elif padrao == "centralizar":
            codigo = css.centralizar()
            descricao = "uma regra para centralizar qualquer conteúdo"

        else:  # botao
            cor = _cor_botao(norm)
            codigo = css.botao(cor=cor)
            descricao = f"o estilo de um botão {cor}"

        return ResultadoGeracao(codigo=codigo, linguagem="css", padrao=padrao, descricao=descricao)

    # Descrições e funções por padrão, num único lugar - evita um terceiro
    # bloco if/elif gigante como o de HTML e CSS acima, já que nenhum destes
    # padrões precisa de parâmetro extraído do pedido (diferente de, por
    # exemplo, "formulário com nome, email e mensagem"): geração "avançada"
    # de JS é sobre a ESTRUTURA do padrão, não sobre nomes de campos.
    _DESCRICOES_JAVASCRIPT: dict[str, str] = {
        "debounce": "uma função debounce",
        "throttle": "uma função throttle",
        "memoize": "uma função com cache de resultados (memoization)",
        "curry": "uma função com currying",
        "clone": "uma função de clonagem profunda",
        "emissor": "um emissor de eventos (padrão pub/sub)",
        "retry": "uma função que tenta novamente em caso de falha",
        "timeout": "uma Promise com tempo limite",
        "fetch": "uma requisição assíncrona com tratamento de erro",
        "classe": "classes com herança e campo privado",
        "gerador": "uma function generator",
        "singleton": "o padrão Singleton",
        "proxy": "um Proxy para validação de propriedades",
    }
    _GERADORES_JAVASCRIPT = {
        "debounce": javascript.debounce,
        "throttle": javascript.throttle,
        "memoize": javascript.memoize,
        "curry": javascript.curry,
        "clone": javascript.clone_profundo,
        "emissor": javascript.emissor_eventos,
        "retry": javascript.promise_retry,
        "timeout": javascript.promise_timeout,
        "fetch": javascript.busca_assincrona,
        "classe": javascript.classe_com_heranca,
        "gerador": javascript.gerador_sequencia,
        "singleton": javascript.singleton,
        "proxy": javascript.validador_proxy,
    }

    def _montar_javascript(self, padrao: str, texto: str, norm: str) -> ResultadoGeracao:
        codigo = self._GERADORES_JAVASCRIPT[padrao]()
        descricao = self._DESCRICOES_JAVASCRIPT[padrao]
        return ResultadoGeracao(codigo=codigo, linguagem="javascript", padrao=padrao, descricao=descricao)
