"""Comandos naturais que o classificador de intenção erra ou confunde.

Três famílias, todas decididas por regras explícitas e sem LLM:

* pesquisa explícita ("pesquise sobre X na internet", "pesquisa isso"): vira `buscar_web` com a consulta X. O
  verbo de pesquisa é um comando: vem ANTES do gatilho de capacidades e do classificador. "isso" recupera o
  assunto da última pergunta (ou o tópico recente) e, sem assunto inequívoco, a pergunta é devolvida ao usuário;
* catálogo/visão geral de uma linguagem ("quais tópicos você conhece de JavaScript?", "queria saber mais sobre
  o javascript"): lista os tópicos curados daquela linguagem em vez de cair em capacidades ou "fora da base";
* continuação de uma geração ("use css também" logo depois de montar uma página): o esclarecimento fala da
  página gerada, não de um tópico teórico qualquer.
"""
import re

from .conhecimento import Resultado
from .contexto_conversa import JANELA_TURNOS, _NEUTRAS, _com_abertura, tem_referencia, topico_recente, vizinhanca
from .vetorizador import STOPWORDS_BUSCA, remover_acentos, singularizar, tokenizar

# ---------------------------------------------------------------------------
# Pesquisa explícita
# ---------------------------------------------------------------------------

_POLIDEZ = r"(?:(?:por favor|pf|entao|agora|ok|e|mas|bom)\s+)*(?:(?:voce\s+)?(?:pode|poderia|podia|consegue)\s+)?(?:me\s+)?"
_VERBO_PESQUISA = re.compile(rf"^{_POLIDEZ}(?:pesquis(?:e|ar)|busque|buscar|busca|procure|procurar|procura)\b")
# "pesquisa" também é substantivo ("pesquisa de mercado", "pesquisa científica"): só é comando com um marcador logo depois.
_PESQUISA_COM_MARCADOR = re.compile(
    rf"^{_POLIDEZ}pesquisa\s+(?:sobre|a respeito|isso|isto|esse|essa|este|esta|assunto|tema|ele|ela|online|"
    r"(?:na|pela)\s+(?:internet|web|net|rede)|no\s+google)\b")
# "pesquisa pra mim X": marcador mais fraco que "sobre/internet" — pode ser tarefa de estrutura de dados dita com
# educação ("pesquisa o item na lista pra mim"), então passa pela mesma guarda que os verbos ambíguos.
_PESQUISA_PRA_MIM = re.compile(rf"^{_POLIDEZ}pesquisa\s+(?:pra|para)\s+mim\b")
_FAZER_PESQUISA = re.compile(rf"^{_POLIDEZ}(?:faz|faca|fazer)\s+(?:uma\s+)?(?:pesquisa|busca)\b")
_VERBO_AMBIGUO = re.compile(r"\b(?:busque|buscar|busca|procure|procurar|procura)\b")  # exigem "internet/web/sobre/pra mim…"
_INDICA_WEB = re.compile(r"\b(?:internet|web|google|online|net|sobre)\b")
_PRA_MIM = re.compile(r"\b(?:pra|para)\s+mim\b")   # "procura pra mim X": pedido direto, não tarefa de estrutura de dados
# Pedidos de aprender (outro fluxo) e de procurar dentro do projeto/arquivos nunca são pesquisa na web.
_ALGORITMO = re.compile(r"\bpesquisa\s+(?:binaria|sequencial|linear|operacional|de campo)\b")
# Sem "sobre/internet/web…", um verbo de pesquisa junto de estruturas de dados é a tarefa de achar um item.
_TAREFA_DE_DADOS = re.compile(
    r"\b(?:lista|listas|array|vetor|elemento|elementos|item|itens|valor|indice|dicionario|string|texto|tupla|"
    r"planilha|arquivo|arquivos|pasta|catalogo|estoque|inventario|cadastro|cadastros|registro|registros|"
    r"documento|documentos|produto|produtos|banco de dados)\b")
_OUTRO_FLUXO = re.compile(r"\b(?:aprend\w+|estud\w+|arquivos?|pasta|workspace|historico|conversa|codigo|erro|bug)\b|\.(?:py|js|html|css|txt|json|md|csv|log)\b")

_BORDA = {"sobre", "a", "o", "as", "os", "de", "da", "do", "das", "dos", "na", "no", "nas", "nos", "pela", "pelo",
          "por", "para", "pra", "me", "mim", "uma", "um", "favor", "pode", "poderia", "voce", "respeito", "acerca",
          "e", "que", "faz", "faca", "fazer", "com", "em", "ai", "tambem", "entao", "agora", "ok", "pf", "mais"}
_REFERENCIA = {"isso", "esse", "essa", "este", "esta", "assunto", "tema", "topico", "ele", "ela", "mesmo", "mesma",
               "nisso", "disso", "aquilo", "dele", "dela", "anterior", "acima"}
_ABERTURA_PERGUNTA = re.compile(
    r"^(?:(?:e|mas|entao|ok)\s+)?(?:o que\s+(?:e|era|sao|significa\w*)|o que\s+voce\s+\w+\s+(?:sobre|de)|"
    r"como\s+(?:funciona\w*|faz\w*|se\s+faz|usar|uso)|me\s+(?:explica|explique|fale|fala|diga|conta)|expli[cq]\w+|"
    r"quero\s+saber\s+(?:mais\s+)?(?:sobre|de)|queria\s+saber\s+(?:mais\s+)?(?:sobre|de)|"
    r"qual\s+(?:e|a)\s+(?:a\s+)?diferenca\s+entre|para\s+que\s+serve\w*|por\s+que)\b")


def _palavras(texto: str) -> list[str]:
    return re.findall(r"[\wÀ-ÿ]+", texto)


def _sem_borda(palavras: list[str]) -> list[str]:
    inicio, fim = 0, len(palavras)
    while inicio < fim and remover_acentos(palavras[inicio].lower()) in _BORDA:
        inicio += 1
    while fim > inicio and remover_acentos(palavras[fim - 1].lower()) in _BORDA:
        fim -= 1
    return palavras[inicio:fim]


_PREFIXO_DE_COMANDO = {"por", "favor", "pf", "entao", "agora", "ok", "e", "mas", "bom", "voce", "pode", "poderia", "podia",
                       "consegue", "me", "faz", "faca", "fazer", "uma", "pesquisa", "pesquise", "pesquisar", "busque",
                       "buscar", "busca", "procure", "procurar", "procura"}
_LUGARES = {"internet", "web", "google", "net", "rede", "navegador"}
_ANTES_DO_LUGAR = {"na", "no", "pela", "pelo", "em", "pra", "para"}


def _sem_lugar(palavras: list[str]) -> list[str]:
    """Tira "na internet"/"no google"/"online" das pontas (no meio, a palavra pertence ao assunto)."""
    norm = [remover_acentos(p.lower()) for p in palavras]
    if norm and norm[0] == "online":
        return palavras[1:]
    if len(norm) >= 2 and norm[0] in _ANTES_DO_LUGAR and norm[1] in _LUGARES:
        return palavras[2:]
    if norm and norm[-1] == "online":
        return palavras[:-1]
    if len(norm) >= 2 and norm[-2] in _ANTES_DO_LUGAR and norm[-1] in _LUGARES:
        return palavras[:-2]
    return palavras


def _assunto_do_texto(texto: str) -> list[str]:
    """Palavras do assunto num comando de pesquisa.

    Só o PREFIXO de comando ("por favor, pode pesquisar…", "faz uma pesquisa…") e o lugar ("na internet") nas
    pontas saem; uma palavra do assunto que se pareça com o comando ("pesquisa científica") fica.
    """
    palavras = _palavras(texto)
    inicio = 0
    while inicio < len(palavras) and remover_acentos(palavras[inicio].lower()) in _PREFIXO_DE_COMANDO:
        inicio += 1
    resto = palavras[inicio:]
    while True:
        novo = _sem_borda(_sem_lugar(resto))
        if novo == resto:
            return resto
        resto = novo


def eh_comando_de_pesquisa(pedido) -> bool:
    norm = re.sub(r"[,;:]", " ", pedido.normalizado).strip()
    if pedido.codigo or _OUTRO_FLUXO.search(norm) or _ALGORITMO.search(norm):
        return False
    if _FAZER_PESQUISA.match(norm):
        return bool(_INDICA_WEB.search(norm))
    if _PESQUISA_COM_MARCADOR.match(norm):
        return True
    if _PESQUISA_PRA_MIM.match(norm):
        return not _TAREFA_DE_DADOS.search(norm)
    achou = _VERBO_PESQUISA.match(norm)
    if not achou:
        return False
    if _INDICA_WEB.search(norm):
        return True
    if _VERBO_AMBIGUO.search(achou.group(0)):
        return bool(_PRA_MIM.search(norm)) and not _TAREFA_DE_DADOS.search(norm)
    return not _TAREFA_DE_DADOS.search(norm)


def _assunto_da_pergunta_anterior(bot, pedido) -> list[str]:
    """O assunto da última mensagem do usuário que não é um comando de pesquisa, se houver um inequívoco."""
    from .interpretacao import interpretar
    turnos = [t for t in bot.memoria.turnos if t.papel == "usuario"]
    for turno in reversed(turnos[:-1] if turnos and turnos[-1].texto.strip() == pedido.original.strip() else turnos):
        anterior = interpretar(turno.texto)
        if anterior.codigo or eh_comando_de_pesquisa(anterior):
            continue
        norm = anterior.normalizado.strip(" .?!")
        sem_abertura = _ABERTURA_PERGUNTA.sub("", norm).strip(" .?!,")
        if sem_abertura == norm and not turno.texto.strip().endswith("?"):
            return []                 # a última mensagem não era uma pergunta sobre um assunto ("olá", "obrigado")
        norm = sem_abertura
        restante = _sem_borda(_palavras(norm))
        if not restante or len(restante) > 6:
            return []
        if any(remover_acentos(p.lower()) in _REFERENCIA for p in restante):
            return []                 # "o que é isso?", "isso serve para quê?": a pergunta também é uma referência
        return restante
    return []


_E_O_ASSUNTO = re.compile(r"^(?:e|tambem)\s+(?:sobre\s+)?(?:(?:o|a|os|as)\s+)?(?P<x>[a-z0-9_ ]+?)(?:\s+tambem)?$")


def _continuacao_de_busca(bot, pedido):
    """"e o flask também" logo depois de uma pesquisa: pesquisa o novo assunto (sem "e o" nem "também")."""
    buscas = bot.dialogo.contexto.ultimas_buscas
    if not buscas or bot.dialogo.turnos - buscas[-1][1] != 1 or pedido.codigo:
        return None
    norm = re.sub(r"[,;:]", " ", pedido.normalizado).strip(" .?!")
    achou = _E_O_ASSUNTO.match(norm)
    if not achou or not 1 <= len(achou.group("x").split()) <= 3 or achou.group("x").split()[0] in _REFERENCIA:
        return None
    palavras = _palavras(pedido.texto.strip(" .?!"))
    inicio = 0
    while inicio < len(palavras) and remover_acentos(palavras[inicio].lower()) in {"e", "tambem", "sobre", "o", "a", "os", "as"}:
        inicio += 1
    fim = len(palavras)
    if fim > inicio and remover_acentos(palavras[fim - 1].lower()) == "tambem":
        fim -= 1
    assunto = palavras[inicio:fim]
    return " ".join(assunto) if assunto else None


_REFINAMENTO_IDIOMA = re.compile(
    rf"^{_POLIDEZ}(?:pesquis(?:e|ar)|busque|buscar|busca|procure|procurar|procura)?\s*em\s+portugues\s*$"
)


def _refinamento_de_idioma(bot, pedido):
    """"pesquise em português"/"agora em português"/"em português" logo depois de uma pesquisa recente:
    refina a ÚLTIMA consulta pesquisada, em vez de perder o assunto anterior e pesquisar só "português"
    sozinho.

    Precisa rodar ANTES da extração genérica de assunto: depois que `_assunto_do_texto` tira o verbo (prefixo
    de comando) e "em"/"sobre" (bordas), "pesquise EM português" e "pesquise SOBRE português" ficam
    indistinguíveis - os dois viram só a palavra "português". Aqui, olhando o texto inteiro, só "em português"
    conta como refinamento; "sobre português"/"a língua portuguesa" continuam assunto de pesquisa normal
    (mais de uma palavra, ou com "sobre" em vez de "em") - tratados no fluxo de sempre.

    Sem pesquisa recente, devolve "" (quem chama pede o assunto - não inventa nem pesquisa só o idioma).
    Fora do padrão exato, devolve `None` (não é um refinamento de idioma).
    """
    if pedido.codigo:
        return None
    norm = re.sub(r"[,;:]", " ", pedido.normalizado).strip(" .?!")
    if not _REFINAMENTO_IDIOMA.match(norm):
        return None
    buscas = bot.dialogo.contexto.ultimas_buscas
    if not buscas or bot.dialogo.turnos - buscas[-1][1] != 1:
        return ""
    ultima_consulta, _ = buscas[-1]
    return f"{ultima_consulta} em português"


def consulta_de_pesquisa(bot, pedido):
    """None: não é um comando de pesquisa. String (possivelmente vazia): a consulta; vazia = pedir o assunto."""
    refinamento = _refinamento_de_idioma(bot, pedido)
    if refinamento is not None:
        return refinamento
    if not eh_comando_de_pesquisa(pedido):
        return _continuacao_de_busca(bot, pedido)
    assunto = _assunto_do_texto(pedido.texto)
    if assunto and not all(remover_acentos(p.lower()) in _REFERENCIA for p in assunto):
        return " ".join(assunto)
    anterior = _assunto_da_pergunta_anterior(bot, pedido)
    if anterior:
        return " ".join(anterior)
    recente = topico_recente(bot)
    if recente:
        return recente["titulo"].split(":")[-1].strip()
    return ""


# ---------------------------------------------------------------------------
# Catálogo e visão geral por linguagem
# ---------------------------------------------------------------------------

_NOMES = {"javascript": "JavaScript", "css": "CSS", "html": "HTML", "python": "Python"}
_PREFIXOS = {"javascript": "JavaScript:", "css": "CSS:", "html": "HTML:"}
_GERAIS = {"linguagens-suportadas", "logica-programacao", "algoritmo", "o-que-e-programar", "paradigmas",
           "pseudocodigo", "estruturas-de-dados", "compilado-interpretado", "boas-praticas", "aprender-programar"}

_TOPICO = r"(?:topicos?|assuntos?|conceitos?|temas?|conteudos?|materias?)"
_CATALOGO = re.compile(
    rf"\b(?:quais|que|qual)\s+(?:sao\s+)?(?:os\s+|as\s+)?{_TOPICO}\b|"
    rf"\b(?:lista|liste|listar|mostre|mostra|mostrar|me mostra|me mostre)\b.*\b{_TOPICO}\b|"
    rf"\b(?:o que|oque)\s+(?:voce\s+)?(?:sabe|conhece|tem|ensina|explica)\s+(?:sobre|de|do|da|em)\b")
_VISAO_GERAL = re.compile(
    r"^(?:(?:e|entao|ok|olha|bom)\s+)*(?:(?:eu\s+)?(?:queria|quero|gostaria de|preciso|precisava|vou querer)\s+"
    r"(?:saber|aprender|estudar|entender|conhecer|ver)\s+(?:mais\s+)?(?:sobre|de|do|da)?\s*|"
    r"(?:me\s+)?(?:fala|fale|conta|conte|explica|explique|fala mais|fale mais)\s+(?:mais\s+)?(?:sobre|de|do|da)\s+)"
    r"(?:o\s+|a\s+|de\s+|do\s+|da\s+)*(?:linguagem\s+)?(?P<lang>javascript|css|html|python)\s*[?.! ]*$")


def _grupo(bot, linguagem: str) -> list[dict]:
    entradas = [e for e in bot.base.entradas if not e.get("aprendido")]
    if linguagem in _PREFIXOS:
        return [e for e in entradas if e["titulo"].startswith(_PREFIXOS[linguagem])]
    prefixos = tuple(_PREFIXOS.values())
    return [e for e in entradas if not e["titulo"].startswith(prefixos) and e["id"] not in _GERAIS]


def _nome_do_topico(entrada: dict) -> str:
    return entrada["titulo"].split(":", 1)[-1].strip()


def _linguagem_do_pedido(pedido) -> str:
    achada = pedido.linguagem if pedido.linguagem in _NOMES else ""
    if not achada:
        norm = pedido.normalizado
        achada = next((l for l in _NOMES if re.search(rf"\b{l}\b", norm)), "")
    return achada


def _texto_do_catalogo(bot, linguagem: str, abertura: str) -> str:
    entradas = _grupo(bot, linguagem)
    nome = _NOMES[linguagem]
    lista = "\n".join(f"• {_nome_do_topico(e)}" for e in entradas)
    exemplo = _nome_do_topico(entradas[0])
    return (f"{abertura}\n\nTenho {len(entradas)} tópicos de {nome} na minha base:\n\n{lista}\n\n"
            f"Peça qualquer um deles — por exemplo, \"o que é {exemplo}?\" — que eu explico. "
            f"Eu explico o que está na base e não invento o resto.")


def _catalogo_geral(bot) -> str:
    linhas = []
    for linguagem in ("python", "javascript", "html", "css"):
        linhas.append(f"• {_NOMES[linguagem]}: {len(_grupo(bot, linguagem))} tópicos")
    gerais = [e for e in bot.base.entradas if not e.get("aprendido") and e["id"] in _GERAIS]
    linhas.append(f"• Conceitos gerais de programação: {len(gerais)} tópicos")
    return ("Minha base curada está organizada assim:\n\n" + "\n".join(linhas) +
            "\n\nDiga a linguagem (por exemplo, \"quais tópicos você conhece de CSS?\") que eu listo os tópicos dela.")


def resolver_catalogo(bot, pedido):
    """(texto, intenção) para catálogo/visão geral, ou None."""
    if pedido.codigo:
        return None
    norm = pedido.normalizado.strip()
    visao = _VISAO_GERAL.match(norm)
    if visao:
        linguagem = visao.group("lang")
        if not _grupo(bot, linguagem):
            return None
        return _texto_do_catalogo(bot, linguagem, f"Vamos por {_NOMES[linguagem]} então."), "topicos"
    if not _CATALOGO.search(norm):
        return None
    linguagem = _linguagem_do_pedido(pedido)
    if linguagem and _grupo(bot, linguagem):
        return _texto_do_catalogo(bot, linguagem, f"Claro, esses são os assuntos de {_NOMES[linguagem]} que eu conheço."), "topicos"
    if re.search(rf"\b{_TOPICO}\s+(?:de|sobre|em|do|da|dos|das)\s+(?!voce\b)\w+", norm):
        return None                   # "tópicos de história": assunto que não é linguagem da base
    if re.search(rf"\b{_TOPICO}\b", norm):
        return _catalogo_geral(bot), "topicos"
    return None


# ---------------------------------------------------------------------------
# Continuação de uma geração
# ---------------------------------------------------------------------------

_CONTINUACAO = re.compile(
    r"^(?:(?:e|entao|agora|ok|mas|so)\s+)*(?:(?:use|usa|usar|coloque|coloca|colocar|adicione|adiciona|adicionar|"
    r"inclua|inclui|incluir|ponha|poe|bota|bote|mete|acrescente|acrescenta|faca|faz|com|tambem)\s+)+"
    r"(?:o\s+|a\s+|um\s+|uma\s+|de\s+|em\s+|no\s+|na\s+)*(?P<lang>css|javascript|js|html)\b")
_MAIS = re.compile(r"\b(?:tambem|junto|ainda|alem disso)\b")


def resolver_continuacao(bot, pedido):
    """(texto, intenção) quando o pedido complementa a página que acabou de ser gerada, ou None."""
    ultima = bot.dialogo.contexto.ultima_geracao
    if not ultima or pedido.codigo or bot.dialogo.turnos - ultima["turno"] != 1:
        return None
    norm = pedido.normalizado.strip(" .?!")
    achou = _CONTINUACAO.match(norm)
    if not achou or len(norm.split()) > 8:
        return None
    if not (_MAIS.search(norm) or norm.split()[0] in {"use", "usa", "coloque", "coloca", "adicione", "adiciona",
                                                     "inclua", "inclui", "ponha", "poe", "bota", "acrescente"}):
        return None
    linguagem = {"js": "javascript"}.get(achou.group("lang"), achou.group("lang"))
    ctx = bot.dialogo.contexto
    gerada, codigo = ultima["linguagem"], ultima["codigo"]
    descricao = "a página" if gerada == "html" else "o código"
    if linguagem == gerada:
        return None
    ctx.pendente, ctx.linguagem = "tipo_codigo", linguagem
    if linguagem == "css":
        estilo = ("já vem com o CSS dentro de `<style>`, então ela já está estilizada"
                  if "<style" in codigo else "ainda não tem estilo")
        return (f"Sobre {descricao} que acabei de montar: ela {estilo}. Posso montar agora um trecho CSS avulso para "
                "você juntar a ela — grid, flexbox, botão, responsividade ou variáveis de cor. Qual deles?"), "esclarecimento"
    if linguagem == "javascript":
        return (f"Sobre {descricao} que acabei de montar: não misturo JavaScript dentro dela automaticamente, mas posso "
                "montar um trecho avulso para você acrescentar — debounce, throttle, memoization ou currying, por "
                "exemplo. Qual deles?"), "esclarecimento"
    return (f"Sobre {descricao} que acabei de montar: ela já é HTML. Posso montar outro bloco HTML para acrescentar — "
            "formulário, navbar ou outra seção. Qual deles?"), "esclarecimento"


# ---------------------------------------------------------------------------
# Intenções diretas: arquivo e "aprenda sobre X"
# ---------------------------------------------------------------------------

_ARQUIVO = re.compile(r"\b[\w\-]+\.(?:py|js|html|css|txt|json|md|csv|log)\b")
_SALVAR = re.compile(rf"^{_POLIDEZ}(?:salv\w+|grav\w+|guard\w+|escrev\w+)\b")
_CRIAR_ARQUIVO = re.compile(rf"^{_POLIDEZ}cri(?:a|e|ar)\s+(?:um\s+|o\s+)?arquivo\b")
_LER_ARQUIVO = re.compile(rf"^{_POLIDEZ}(?:le|leia|ler|abra|abrir|mostre|mostra|mostrar|veja|ver)\s+(?:o\s+|um\s+)?(?:arquivo\s+)?[\w\-]+\.")
_APRENDER = re.compile(
    rf"^{_POLIDEZ}(?:aprenda|aprender|estude|estudar|memorize)\s+(?:mais\s+)?(?:sobre\s+|a respeito de\s+)?(?P<assunto>.+)$")


def intencao_direta(bot, pedido) -> str | None:
    """'manipular_arquivo' ou 'aprender' quando a frase é um comando inequívoco para essas ferramentas."""
    norm = re.sub(r"[,;:]", " ", pedido.normalizado).strip(" .!?")
    if _ARQUIVO.search(norm) and (_SALVAR.match(norm) or _CRIAR_ARQUIVO.match(norm) or _LER_ARQUIVO.match(norm)):
        return "manipular_arquivo"
    achou = _APRENDER.match(norm)
    if achou and not pedido.codigo:
        assunto = achou.group("assunto").split()
        if assunto and assunto[0] not in {"a", "como", "que", "por"}:
            return "aprender"
    return None


# ---------------------------------------------------------------------------
# Conversa social com gíria
# ---------------------------------------------------------------------------

_GIRIA_SAUDACAO = re.compile(r"^(?:e\s*)?(?:eae|eai|e ai|opa|salve|fala ai)(?:\s+(?:tartaruga|amigo|mano|cara|pessoal|galera))?\s*[!?. ]*$")
_GIRIA_AGRADECIMENTO = re.compile(r"^(?:muito\s+)?(?:obrigad\w*|brigad\w*|valeu\w*|vlw\w*)(?:\s+\w+){0,2}\s*[!?. ]*$")
_PERGUNTA_DO_NOME = re.compile(
    r"\bqual\s+(?:e\s+)?(?:o\s+)?(?:seu|teu)\s+nome\b|\bcomo\s+(?:voce\s+)?(?:se\s+chama|te\s+chama)\b|^quem\s+(?:e|eh)\s+(?:voce|vc)\b")


def conversa_livre(bot) -> bool:
    """False quando a mensagem pode ser resposta a algo em andamento (briefing, esclarecimento, pendência)."""
    dialogo = bot.dialogo
    return not (dialogo.briefing.estado == "coletando" or dialogo.contexto.pendente
                or dialogo.contexto.opcoes_semanticas)


def social_canonico(bot, pedido) -> str | None:
    """A frase-modelo de saudação/agradecimento equivalente a uma gíria ("eae", "obrigadao"), ou None."""
    if pedido.codigo or not conversa_livre(bot):
        return None
    norm = re.sub(r"[,;:]", " ", pedido.normalizado).strip()
    if _GIRIA_SAUDACAO.match(norm):
        return "oi"
    if _GIRIA_AGRADECIMENTO.match(norm):
        return "obrigado"
    return None


def resolver_social(bot, pedido):
    """(texto, intenção) para "qual seu nome?" e "quem é você?", ou None."""
    if pedido.codigo or not conversa_livre(bot):
        return None
    norm = re.sub(r"[,;:]", " ", pedido.normalizado).strip(" .!?")
    palavras = norm.split()
    if len(palavras) <= 6 and _PERGUNTA_DO_NOME.search(norm):
        return ("Me chamo Tartaruga: sou uma assistente de programação. Explico Python, HTML, CSS e JavaScript, "
                "monto alguns modelos de código e pesquiso na internet quando você pede.\n\n"
                "Sobre o que você quer conversar?"), "sobre_projeto"
    return None


# ---------------------------------------------------------------------------
# Continuações de contexto: outra linguagem e comparação entre os tópicos recentes
# ---------------------------------------------------------------------------

_EM_LINGUAGEM = re.compile(r"\b(?:em|no|na|com|de|do|da)\s+(?P<lang>javascript|css|html|python)\b")


def _linguagem_da_entrada(entrada: dict) -> str:
    titulo = entrada["titulo"]
    for linguagem, prefixo in _PREFIXOS.items():
        if titulo.startswith(prefixo):
            return linguagem
    return "python" if entrada["id"] not in _GERAIS else ""


def resolver_troca_de_linguagem(bot, pedido):
    """"e em javascript, como faz isso?" depois de um tópico de Python: procura o equivalente NA linguagem pedida
    entre os tópicos curados; se não houver, diz que não tem (em vez de responder outro assunto) e oferece a busca."""
    norm = re.sub(r"\bjs\b", "javascript", pedido.normalizado.strip(" .?!"))
    if pedido.codigo or len(norm.split()) > 10 or not (tem_referencia(pedido.texto) or _so_troca_de_linguagem(norm)):
        return None
    recente = topico_recente(bot)
    achou = _EM_LINGUAGEM.search(norm)
    if recente is None or not achou:
        return None
    linguagem = achou.group("lang")
    if _linguagem_da_entrada(recente) == linguagem:
        return None
    nome_do_assunto = recente["titulo"].split(":", 1)[-1].strip()
    entradas_da_linguagem = _grupo(bot, linguagem)
    palavras = set(tokenizar(nome_do_assunto, STOPWORDS_BUSCA))
    proximos = []
    for entrada in entradas_da_linguagem:
        titulo = set(tokenizar(_nome_do_topico(entrada), STOPWORDS_BUSCA))
        comuns = len(palavras & titulo)
        if comuns:
            proximos.append((comuns, comuns / len(palavras | titulo), entrada))
    proximos.sort(key=lambda item: (item[0], item[1]), reverse=True)
    grupo = {e["id"] for e in entradas_da_linguagem}
    abertura = f"Ligando ao que vimos (**{recente['titulo']}**), você quer isso em {_NOMES[linguagem]}."
    if proximos:
        entrada = proximos[0][2]
        alvo = Resultado(entrada["id"], entrada["titulo"], entrada["resposta"], entrada.get("codigo", ""), 0)
        return _com_abertura(bot, abertura + f" O que tenho de mais próximo é **{alvo.titulo}**.", alvo), "duvida_programacao"
    if not grupo:
        return None
    topicos = ", ".join(_nome_do_topico(e) for e in _grupo(bot, linguagem))
    return (f"{abertura} Isso eu ainda não tenho na base em {_NOMES[linguagem]}, e prefiro dizer a inventar.\n\n"
            f"Meus tópicos de {_NOMES[linguagem]}: {topicos}.\n\n"
            f"Se quiser, peça \"pesquise sobre {nome_do_assunto.lower()} em {_NOMES[linguagem]}\" que eu busco na internet."), "esclarecimento"


_COMPARACAO = re.compile(
    r"\b(?:no geral|de modo geral|em geral)\b.*\bqual\b|\bqual\s+(?:dos\s+dois|deles|delas|e\s+melhor|melhor|usar|escolher|"
    r"eu\s+uso|eu\s+devo\s+usar|devo\s+usar|vale\s+mais|compensa)\b|\bentre\s+(?:os|as)\s+dois\b|\bentre\s+(?:eles|elas)\b|"
    r"\bquando\s+usar\s+cada\b|\bqual\s+a\s+diferenca\s+entre\s+(?:eles|elas|os\s+dois)\b")
_ESCOLHA = re.compile(r"\b(?:use|usa|escolha|ideal|melhor|quando|ferramenta certa|prefira|indicado)\b", re.IGNORECASE)


def _frase_de_escolha(entrada: dict) -> str:
    frases = [f.strip() for f in re.split(r"(?<=[.!?])\s+|\n+", entrada["resposta"]) if f.strip()]
    escolhida = next((f for f in frases if _ESCOLHA.search(f)), frases[0] if frases else "")
    return escolhida if len(escolhida) <= 240 else escolhida[:237].rstrip() + "..."


def _topicos_recentes(bot) -> list[tuple[int, str]]:
    dialogo = bot.dialogo
    achados: list[tuple[int, str]] = []
    for identificador, turno in reversed(dialogo.historico_topicos):
        if dialogo.turnos - turno > JANELA_TURNOS:
            break
        if identificador not in [i for _, i in achados]:
            achados.append((turno, identificador))
        if len(achados) == 2:
            break
    return achados


def _buscas_recentes(bot) -> list[tuple[int, str]]:
    dialogo = bot.dialogo
    achados: list[tuple[int, str]] = []
    for consulta, turno in reversed(dialogo.contexto.ultimas_buscas):
        if dialogo.turnos - turno > JANELA_TURNOS:
            break
        if consulta.lower() not in [c.lower() for _, c in achados]:
            achados.append((turno, consulta))
        if len(achados) == 2:
            break
    return achados


_CASO_DE_USO = re.compile(
    r"\bpra\s+fazer\s+(?:um[a]?\s+)?(?P<caso1>.+)$|\bpara\s+fazer\s+(?:um[a]?\s+)?(?P<caso2>.+)$|"
    r"\bpra\s+(?P<caso3>.+)$|\bpara\s+(?P<caso4>.+)$")


def _caso_de_uso(norm: str) -> str | None:
    """"...pra fazer um layout de galeria de fotos?": o caso de uso citado, se houver, sem inventar se não houver."""
    achou = _CASO_DE_USO.search(norm)
    if not achou:
        return None
    caso = next((g for g in achou.groups() if g), None)
    return caso.strip(" ?.!") if caso else None


def resolver_comparacao(bot, pedido):
    """"no geral, qual usar?" / "qual dos dois é mais fácil?" / "qual dos dois é melhor pra fazer X?": compara as
    DUAS últimas coisas tratadas — dois tópicos explicados (o que a base diz de cada um) ou duas pesquisas na web (que
    só devolveram links: o limite é dito). Um caso de uso citado ("pra fazer X") é reconhecido mas não inventado: a
    resposta cita o caso e admite que a base não decide para ele especificamente, sem deixar de comparar o que sabe."""
    if pedido.codigo or len(pedido.normalizado.split()) > 20 or not _COMPARACAO.search(pedido.normalizado):
        return None
    topicos, buscas = _topicos_recentes(bot), _buscas_recentes(bot)
    if len(buscas) == 2:                # a janela é de 3 turnos: duas buscas e dois tópicos não cabem juntos
        primeira, segunda = buscas[1][1], buscas[0][1]
        return (f"Você pesquisou **{primeira}** e **{segunda}** na web, mas eu só mostrei os links: não comparo o conteúdo "
                f"das páginas e não vou chutar qual é melhor. Se quiser, peça \"pesquise sobre {primeira} ou {segunda} "
                "para iniciantes\" que eu busco uma comparação."), "esclarecimento"
    if len(topicos) < 2:
        return None
    entradas = [next((e for e in bot.base.entradas if e["id"] == i and not e.get("aprendido")), None) for _, i in topicos]
    if None in entradas:
        return None
    entradas.reverse()                      # na ordem em que foram explicados
    linhas = "\n".join(f"• **{e['titulo']}**: {_frase_de_escolha(e)}" for e in entradas)
    caso = _caso_de_uso(pedido.normalizado)
    abertura = (f'Não tenho "{caso}" comparado na minha base, então não decido por esse caso específico. '
                "Comparando o que vimos, do jeito que a minha base diz:" if caso
                else "Comparando o que vimos, do jeito que a minha base diz:")
    return (f"{abertura}\n\n{linhas}\n\n"
            "Não escolho por você: depende do que você está montando. Se me disser o objetivo, ajudo a decidir."), "duvida_programacao"


# ---------------------------------------------------------------------------
# Refino de um artefato gerado ("deixa ele azul", "adiciona hover", "alert ao clicar")
# ---------------------------------------------------------------------------

_VERBO_DE_REFINO = re.compile(
    r"^(?:(?:e|entao|agora|ok|mas|so)\s+)*(?:deixa|deixe|faz|faca|fazer|muda|mude|troca|troque|coloca|coloque|adiciona|"
    r"adicione|poe|ponha|bota|bote|aumenta|aumente|diminui|diminua|tira|tire|remove|remova|inclui|inclua|altera|altere|"
    r"ajusta|ajuste|quero|queria|preciso|com)\b")
_TEMA_DE_REFINO = re.compile(
    r"\b(?:hover|transicao|animacao|animado|sombra|tema\s+(?:escuro|claro)|modo\s+(?:escuro|claro)|escuro|claro|alert|"
    r"clicar|clique|clicado|passar\s+o\s+mouse|maior|menor|grande|pequeno|arredondad\w*|borda|fonte|letra|negrito)\b")
_REFERE_O_ARTEFATO = re.compile(r"\b(?:ele|ela|eles|elas|isso|o\s+botao|a\s+pagina|o\s+formulario|o\s+card|a\s+lista|a\s+tabela|o\s+menu)\b")
_PERGUNTA_TEORICA = re.compile(r"^(?:o que|como|qual|quais|por que|porque|quando|onde)\b")


def _cor_pedida(norm: str) -> str | None:
    from .geradores import css
    return next((cor for cor in css.CORES if re.search(rf"\b{cor}\b", norm)), None)


def resolver_refino(bot, pedido):
    """(texto, intenção) para um ajuste pedido logo depois de gerar algo, ou None.

    O gerador não EDITA o que já montou: cada pedido monta um modelo inteiro. O que dá para fazer de verdade é
    complementar com o modelo de CSS que cobre o ajuste (cor do botão, transição/hover, sombra, tema); o resto
    (comportamento em JavaScript, tamanho, fonte…) recebe o limite dito com clareza, ligado ao artefato recente.
    """
    ultima = bot.dialogo.contexto.ultima_geracao
    if not ultima or pedido.codigo or bot.dialogo.turnos - ultima["turno"] > JANELA_TURNOS:
        return None
    norm = pedido.normalizado.strip(" .?!")
    if len(norm.split()) > 10 or _PERGUNTA_TEORICA.match(norm) or _MAIS.search(norm) and _CONTINUACAO.match(norm):
        return None
    cor = _cor_pedida(norm)
    tema = _TEMA_DE_REFINO.search(norm)
    verbo = _VERBO_DE_REFINO.match(norm)
    if not ((verbo and (cor or tema or _REFERE_O_ARTEFATO.search(norm))) or (tema and len(norm.split()) <= 6)):
        return None
    descricao = ultima["descricao"]
    pedido_css = None
    if cor and ultima.get("padrao") == "botao":
        pedido_css = f"crie um botão {cor} em css"
    elif re.search(r"\b(?:hover|transicao|animacao|animado|passar\s+o\s+mouse)\b", norm):
        pedido_css = "crie uma transição suave em css"
    elif re.search(r"\bsombra\b", norm):
        pedido_css = "crie uma sombra em css"
    elif re.search(r"\b(?:tema|modo)\s+(?:escuro|claro)\b|\bescuro\b", norm):
        pedido_css = "crie variáveis de tema escuro em css" if "escuro" in norm else "crie variáveis de tema claro em css"
    if pedido_css:
        resultado = bot.gerador.gerar(pedido_css)
        if resultado is not None and resultado.linguagem == "css":
            bot.dialogo.contexto.ultima_geracao = {**ultima, "turno": bot.dialogo.turnos}
            return (f"Não edito {descricao} que já montei, mas esse ajuste sai de um modelo de CSS. Junte isto ao que "
                    f"você já tem (para o hover/transição, use a classe indicada no elemento):\n\n```css\n{resultado.codigo}\n```\n\n"
                    "_Montado por um gerador de templates, não escrito por um modelo de linguagem._"), "gerar_codigo"
    return (f"Não edito {descricao} que acabei de montar: o meu gerador refaz um modelo inteiro a cada pedido novo, e "
            "esse ajuste não é um dos que ele sabe fazer sozinho (comportamento em JavaScript, como um alerta ao clicar, "
            "tamanho, fonte e posição não estão entre eles).\n\n"
            "O que eu consigo complementar com um pedido novo: cor do botão (\"botão azul em css\"), transição/hover, "
            "sombra e tema escuro. Diga um deles, ou peça outro modelo ('formulário', 'card', 'navbar'…)."), "esclarecimento"


# ---------------------------------------------------------------------------
# Troca curta de linguagem ("e em javascript?")
# ---------------------------------------------------------------------------

_SO_TROCA = frozenset({"e", "entao", "agora", "em", "no", "na", "com", "como", "faz", "fazer", "fica", "ficaria", "seria",
                       "funciona", "isso", "javascript", "python", "css", "html", "js"})


def _so_troca_de_linguagem(norm: str) -> bool:
    return bool(_EM_LINGUAGEM.search(norm)) and all(p in _SO_TROCA for p in norm.split()) and len(norm.split()) <= 6


# ---------------------------------------------------------------------------
# Briefing depois de um template e "cancelar" sem fluxo ativo
# ---------------------------------------------------------------------------

_PEDE_PERGUNTAS = re.compile(
    r"\bbriefing\b|\bme\s+(?:faz|faca|fazer)\s+(?:umas?\s+)?perguntas?\b|\bme\s+pergunt\w+")
_PLANEJAR = re.compile(r"\bplaneja\w*\b")
_SO_PLANEJAR = frozenset({"prefiro", "quero", "melhor", "vamos", "planejar", "planeja", "planejando", "direito", "antes",
                          "primeiro", "um", "pouco", "agora", "na", "vdd", "verdade", "mesmo", "entao", "e", "ok", "mas",
                          "de", "fazer", "isso", "gerar", "codigo"})
_A_PAGINA = re.compile(r"\b(?:pagina|site|lp|landing)\b")
_LANDING = re.compile(r"\b(?:landing|lp)\b")
_CANCELAR = frozenset({"cancelar", "cancela", "cancele", "desistir", "deixa pra la", "esquece", "esquece isso", "para", "parar"})


def resolver_planejar_briefing(bot, pedido):
    """"na vdd quero planejar direito antes, me faz umas perguntas" depois de gerar uma landing: inicia o briefing
    (a alternativa que a própria resposta da landing oferece). Sem landing recente, exige citar a landing."""
    briefing = bot.dialogo.briefing
    if pedido.codigo or briefing.estado not in {"inativo", "cancelado"}:
        return None
    norm = pedido.normalizado.strip(" .?!")
    if len(norm.split()) > 16 or re.search(r"\bperguntas?\s+(?:de|sobre|do|da)\b", norm):
        return None                   # "me faz perguntas de matemática" não é o briefing da página
    ultima = bot.dialogo.contexto.ultima_geracao
    landing_recente = bool(ultima and ultima.get("padrao") == "landing" and bot.dialogo.turnos - ultima["turno"] <= 5)
    sobre_landing = landing_recente or bool(_LANDING.search(norm))
    planeja_antes = landing_recente and _PLANEJAR.search(norm) and all(p in _SO_PLANEJAR for p in norm.split()) and any(
        p in {"antes", "direito", "primeiro"} for p in norm.split())
    pede = _PEDE_PERGUNTAS.search(norm) or planeja_antes or (_PLANEJAR.search(norm) and _A_PAGINA.search(norm))
    if not (pede and sobre_landing):
        return None
    from .interpretacao import interpretar
    texto = briefing.processar(interpretar("quero uma landing page"))
    if texto is None:
        return None
    bot.dialogo.contexto.assunto = "briefing"
    bot.dialogo.contexto.pendente = ""
    return texto, "briefing"


def resolver_cancelar_sem_fluxo(bot, pedido):
    """"cancelar" quando não há nada em andamento: diz isso, em vez de "não entendi"."""
    if pedido.codigo or not conversa_livre(bot):
        return None
    if bot.dialogo.briefing.estado not in {"inativo", "cancelado"}:
        return None
    if pedido.normalizado.strip(" .!?") not in _CANCELAR:
        return None
    ja_cancelado = bot.dialogo.briefing.estado == "cancelado"
    return (("O briefing já foi cancelado e não há nada mais em andamento. " if ja_cancelado
             else "Não há nada em andamento para cancelar agora (nenhum briefing ou pergunta em aberto). ")
            + "O que você quer fazer? Para planejar uma landing page, diga 'quero uma landing page'."), "esclarecimento"


# ---------------------------------------------------------------------------
# Exemplo/simplificação do tópico recente ("me mostra um exemplo disso", "dá um exemplo mais simples")
# ---------------------------------------------------------------------------

_PEDE_EXEMPLO = re.compile(
    r"^(?:(?:e|entao|ai|agora)\s+)*(?:(?:me\s+)?(?:mostra|mostre|da|de|manda|passa)\s+)?(?:outro\s+|mais\s+um\s+|um\s+)?"
    r"exemplos?(?:\s+(?:disso|disto|desse|dessa|deste|desta|mais\s+simples|mais\s+facil|mais\s+facin|simples|"
    r"pratico|basico|de\s+novo))?\s*[?.! ]*$")
_PEDE_SIMPLES = re.compile(r"\b(?:simples|facil|facin|basico)\b")
_LINGUAGEM_DO_TITULO = (("JavaScript:", "javascript"), ("HTML:", "html"), ("CSS:", "css"))


def _linguagem_da_entrada2(entrada: dict) -> str:
    titulo = entrada["titulo"]
    return next((l for p, l in _LINGUAGEM_DO_TITULO if titulo.startswith(p)), "python")


def resolver_exemplo_do_topico(bot, pedido):
    """"me mostra um exemplo disso" / "dá um exemplo mais simples" logo depois de um tópico explicado: mostra o
    código já na entrada; sem gerador de simplificação, admite o limite em vez de abandonar o contexto."""
    if pedido.codigo:
        return None
    norm = pedido.normalizado.strip(" .?!")
    if len(norm.split()) > 8 or not _PEDE_EXEMPLO.match(norm):
        return None
    recente = topico_recente(bot)
    if recente is None:
        return None
    codigo, titulo = recente.get("codigo", ""), recente["titulo"]
    if not codigo:
        return (f"Não tenho um exemplo de código pronto para **{titulo}** além do que já expliquei; "
                "posso detalhar algum ponto específico, se ajudar."), "duvida_programacao"
    if _PEDE_SIMPLES.search(norm):
        abertura = (f"Não gero uma versão ainda mais simples automaticamente; este é o exemplo mais simples que "
                    f"tenho de **{titulo}**:")
    else:
        abertura = f"Aqui está um exemplo de **{titulo}**:"
    return f"{abertura}\n\n```{_linguagem_da_entrada2(recente)}\n{codigo}\n```", "duvida_programacao"


# ---------------------------------------------------------------------------
# Ajuste do tópico recente ("e deixa responsivo tbm", "faz isso responsivo também")
# ---------------------------------------------------------------------------

_AJUSTE = re.compile(
    r"^(?:(?:e|entao|ai|agora|so)\s+)*(?:deixa|deixe|faz|faca|fazer|coloca|coloque|poe|ponha|bota|bote|torna|torne)\s+"
    r"(?:(?:ele|ela|isso|o|a)\s+)*(?P<termo>[a-zçãõáéíóúâêô ]+?)\s*(?:tambem|tbm|também)?\s*[?.! ]*$")
_MARCA_TAMBEM = re.compile(r"\b(?:tambem|tbm|também)\b")
# tokenizar() devolve os tokens SEM filtrar quando a filtragem esvaziaria a lista (frase só de stopwords) — por
# isso o termo do ajuste é filtrado de novo aqui, contra as formas SINGULARIZADAS de _NEUTRAS/STOPWORDS_BUSCA.
_NEUTRAS_SING = frozenset(singularizar(w) for w in _NEUTRAS)
_STOPWORDS_SING = frozenset(singularizar(w) for w in STOPWORDS_BUSCA)


def resolver_ajuste_do_topico(bot, pedido):
    """"e deixa responsivo tbm" depois de Flexbox/Grid: liga a um tópico vizinho de verdade (CSS: design responsivo),
    sem inventar; sem um vizinho que combine, admite o limite citando o tópico recente em vez de virar "desconhecido"."""
    if pedido.codigo:
        return None
    norm = pedido.normalizado.strip(" .?!")
    if len(norm.split()) > 8 or not _MARCA_TAMBEM.search(norm):
        return None
    achou = _AJUSTE.match(norm)
    if not achou:
        return None
    recente = topico_recente(bot)
    if recente is None:
        return None
    termo = achou.group("termo").strip()
    termo_tokens = {t for t in tokenizar(termo, STOPWORDS_BUSCA)
                    if t not in _NEUTRAS_SING and t not in _STOPWORDS_SING}
    if not termo_tokens:
        return None
    ids = vizinhanca(bot, recente)
    candidatos = [e for e in bot.base.entradas if not e.get("aprendido") and e["id"] in ids
                  and termo_tokens & set(tokenizar(e["titulo"], STOPWORDS_BUSCA))]
    if len(candidatos) == 1:
        alvo = candidatos[0]
        resultado = Resultado(alvo["id"], alvo["titulo"], alvo["resposta"], alvo.get("codigo", ""), 0)
        abertura = f"Ligando ao que vimos (**{recente['titulo']}**), isso também tem a ver com **{alvo['titulo']}**."
        return _com_abertura(bot, abertura, resultado), "duvida_programacao"
    return (f'Não sei aplicar "{termo}" automaticamente ao que já expliquei sobre **{recente["titulo"]}**: minha '
            f'base explica conceitos, mas não edita uma explicação anterior. Pergunte sobre "{termo}" diretamente '
            "que eu explico, se for um assunto que eu conheça."), "esclarecimento"
