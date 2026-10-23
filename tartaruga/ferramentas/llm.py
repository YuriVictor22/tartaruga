"""
Ponte com um modelo de linguagem local, via Ollama — usada só como REFORÇO.

Este é o único lugar do projeto que fala com um modelo de linguagem pronto.
A decisão de arquitetura, registrada no README, é manter o resto do sistema
(classificador, base curada, gerador de templates, gestor de diálogo) 100%
"feito do zero" e usar o LLM apenas como ÚLTIMO RECURSO — nunca como
primeira resposta.

Duas situações acionam o reforço, cada uma com seu próprio prompt:

    gerar()          -> geração de código (HTML/CSS/Python/JavaScript),
                         quando os 35 padrões de `geracao.py` não cobrem o
                         pedido - eles cobrem HTML, CSS e 13 padrões de
                         JavaScript avançado; Python não tem template, então
                         vai sempre por aqui, e JavaScript vai por aqui só
                         quando o pedido não é um dos 13 padrões conhecidos
    responder_geral() -> QUALQUER pergunta, quando o classificador, a base
                         curada e a base aprendida já foram tentados e
                         nenhum soube responder

A segunda existia inicialmente só para código; foi ampliada depois de um
uso real mostrar a Tartaruga recusando "me conte uma piada" com um genérico
"não entendi", quando o reforço já estava disponível e ligado. Isso muda a
identidade do projeto num ponto específico: no caso raro em que tudo mais
falha, a Tartaruga se comporta como um assistente de propósito geral, não
mais só de programação. É uma decisão deliberada, não um efeito colateral —
ver a seção correspondente no README.

Por que "reforço" e não "base": o gerador de templates e a base curada são
instantâneos e gratuitos; o LLM local, na máquina onde isto foi
desenvolvido (sem GPU dedicada), leva de dezenas de segundos a mais de um
minuto por resposta. Usá-lo como primeira opção deixaria toda a Tartaruga
lenta; usá-lo só quando o resto falha mantém a experiência rápida no caso
comum, que continua sendo a maioria.

Nenhuma falha aqui pode derrubar a Tartaruga: Ollama não instalado, não
rodando, modelo não baixado, timeout — tudo isso deve resultar em "não
consegui responder", nunca em uma exceção não tratada.
"""

import http.client
import json
import re
import urllib.error
import urllib.request

OLLAMA_URL = "http://localhost:11434/api/generate"
MODELO_PADRAO = "phi4-mini"

# Generoso de propósito: numa máquina sem GPU dedicada, um modelo de poucos
# bilhões de parâmetros pode legitimamente levar mais de um minuto para
# devolver um trecho de código. Um timeout curto derrubaria pedidos válidos.
TEMPO_LIMITE = 120

PROMPT_CODIGO = (
    "Você é um assistente que gera código HTML, CSS, Python ou JavaScript "
    "curto e funcional. Responda APENAS com o código, dentro de um bloco "
    "markdown (```html, ```css, ```python ou ```javascript). Não explique, "
    "não converse, não adicione texto antes ou depois do bloco de código. "
    "Código Python deve rodar sozinho, sem bibliotecas externas além da "
    "biblioteca padrão, e sem pedir entrada interativa quando um exemplo "
    "de uso já bastar. Código JavaScript deve ser autocontido (sem "
    "depender de um HTML externo específico) e usar apenas recursos "
    "padrão da linguagem, sem bibliotecas externas. Se o pedido não for "
    "sobre programação (HTML, CSS, Python ou JavaScript), responda apenas: "
    "NAO_SEI."
)

# Prompt do reforço de PROPÓSITO GERAL - deliberadamente mais permissivo que
# o de código. Sem a restrição NAO_SEI: aqui o modelo já é o último recurso,
# então recusar de novo devolveria a Tartaruga à estaca zero. As instruções
# de tom (curto, direto, sem se apresentar) existem porque o texto aparece
# DEPOIS de "Isto foi GERADO por um modelo..." - um preâmbulo tipo "Olá! Sou
# um assistente de IA..." seria redundante e alongaria a resposta à toa.
PROMPT_GERAL = (
    "Você é um assistente respondendo em português do Brasil, de forma "
    "direta e curta (no máximo 3 parágrafos pequenos, ou menos se a "
    "pergunta for simples). Não se apresente, não diga que é uma IA, não "
    "adicione ressalvas - vá direto à resposta."
)

# Perguntas gerais tendem a caber em respostas mais curtas que código;
# limitar o tamanho da geração mantém o tempo de espera razoável.
LIMITE_TOKENS_GERAL = 350

PADRAO_BLOCO = re.compile(r"```(\w*)\s*\n?(.*?)```", re.DOTALL)


# Tudo o que pode dar errado ao falar com o serviço sem ser um bug do nosso
# código. `http.client.HTTPException` (IncompleteRead, BadStatusLine...) NÃO é
# OSError: uma conexão que cai no meio do corpo, ou uma porta 11434 ocupada por
# algo que não fala HTTP direito, escapava dos `except` antigos.
ERROS_DO_SERVICO = (urllib.error.URLError, urllib.error.HTTPError, OSError,
                    TimeoutError, http.client.HTTPException)


def _texto_da_resposta(dados) -> str | None:
    """Extrai o campo `response` de um JSON JÁ decodificado, ou None.

    JSON sintaticamente válido não garante o formato esperado: `null`, uma
    lista, `{"response": null}` ou `{"response": 42}` derrubavam as funções
    com AttributeError (achado em revisão). O serviço é externo, então
    o formato também é validado: precisa ser objeto e `response` precisa ser
    texto.
    """
    if not isinstance(dados, dict):
        return None
    texto = dados.get("response")
    if not isinstance(texto, str):
        return None
    return texto.strip()


def disponivel() -> bool:
    """Verifica rapidamente se o Ollama está rodando nesta máquina.

    Chamado ANTES de tentar gerar, para que a interface possa decidir se
    vale a pena nem mostrar a opção — sem esperar um timeout de minuto só
    para descobrir que o serviço está desligado.
    """
    try:
        urllib.request.urlopen("http://localhost:11434/api/tags", timeout=2)
        return True
    except ERROS_DO_SERVICO:
        return False


def gerar(pedido: str, modelo: str = MODELO_PADRAO, tentativas: int = 2) -> tuple[str, str] | None:
    """Pede ao modelo local para gerar código. Devolve (código, linguagem) ou None.

    None cobre TODOS os casos de falha: Ollama fora do ar, modelo não
    baixado, timeout, resposta sem bloco de código reconhecível, o próprio
    modelo dizendo que não sabe (`NAO_SEI`), ou nenhuma das tentativas
    produzindo código que passe na checagem de sanidade da linguagem. O
    chamador trata None como "reforço indisponível" e cai na recusa honesta
    padrão.

    A validação existe porque um teste real expôs o modelo misturando
    português na sintaxe Python: `[[''] * 3 para _ in range(3)]` em vez de
    `for`. Como o modelo é probabilístico (`temperature > 0`), a MESMA
    pergunta pode gerar sintaxe válida numa tentativa e inválida na outra -
    por isso a nova tentativa automática, em vez de desistir na primeira
    falha. A força da checagem varia por linguagem - ver `_sintaxe_valida`.
    """
    for tentativa in range(tentativas):
        resultado = _uma_geracao(pedido, modelo)
        if resultado is None:
            continue

        codigo, linguagem = resultado
        if _sintaxe_valida(codigo, linguagem):
            return codigo, linguagem
        # Sintaxe inválida: tenta de novo (se ainda houver tentativa) em vez
        # de devolver código quebrado como se estivesse pronto.

    return None


def _sintaxe_valida(codigo: str, linguagem: str) -> bool:
    """Checagem de sanidade antes de apresentar o código como pronto.

    A força da checagem depende do que está disponível:

    - Python tem `compile()` na biblioteca padrão - validação REAL de
      sintaxe, pega qualquer erro que impediria o código de rodar.
    - JavaScript não tem parser nenhum na biblioteca padrão do Python. A
      alternativa é uma checagem bem mais fraca: chaves, parênteses e
      colchetes balanceados. Não pega todo erro de sintaxe (um `;` ou `,`
      faltando passa direto), mas pega o mais comum e mais embaraçoso -
      uma função ou bloco que o modelo esqueceu de fechar.
    - HTML e CSS não têm checagem nenhuma aqui: o gerador de TEMPLATES já
      cobre a maioria dos casos comuns dessas duas, e a validação de tags
      HTML já é feita como teste (não em tempo de execução) no projeto.
    """
    if linguagem == "python":
        try:
            compile(codigo, "<gerado>", "exec")
            return True
        except SyntaxError:
            return False

    if linguagem == "javascript":
        pares = {"(": ")", "{": "}", "[": "]"}
        pilha: list[str] = []
        for caractere in codigo:
            if caractere in pares:
                pilha.append(pares[caractere])
            elif caractere in pares.values():
                if not pilha or pilha.pop() != caractere:
                    return False
        return not pilha

    return True


def _uma_geracao(pedido: str, modelo: str) -> tuple[str, str] | None:
    """Uma única chamada ao modelo - a parte que `gerar()` repete se preciso."""
    corpo = {
        "model": modelo,
        "prompt": f"{PROMPT_CODIGO}\n\nPedido: {pedido.strip()}",
        "stream": False,
        "options": {"temperature": 0.3, "num_predict": 600},
    }

    try:
        requisicao = urllib.request.Request(
            OLLAMA_URL,
            data=json.dumps(corpo).encode("utf-8"),
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        with urllib.request.urlopen(requisicao, timeout=TEMPO_LIMITE) as resposta:
            dados = json.loads(resposta.read().decode("utf-8"))
    except ERROS_DO_SERVICO:
        return None
    except (json.JSONDecodeError, UnicodeDecodeError):
        return None

    texto = _texto_da_resposta(dados)
    if not texto or "NAO_SEI" in texto.upper():
        return None

    achado = PADRAO_BLOCO.search(texto)
    if not achado:
        return None

    codigo = achado.group(2).strip()
    if not codigo:
        return None

    marcador = achado.group(1).strip().lower()
    marcadores_conhecidos = ("html", "css", "python", "py", "javascript", "js")
    linguagem = marcador if marcador in marcadores_conhecidos else _adivinhar_linguagem(codigo)
    if linguagem == "py":
        linguagem = "python"
    elif linguagem == "js":
        linguagem = "javascript"
    return codigo, linguagem


def _adivinhar_linguagem(codigo: str) -> str:
    """Quando o modelo não marcou a linguagem do bloco, tenta inferir pelo conteúdo.

    Python é checado antes de JavaScript porque `class ` e `if ` aparecem nas
    duas linguagens - mas `def `, `self.` e `elif ` são exclusivos de Python,
    então testá-lo primeiro evita falso positivo de JS num código Python. Uma
    classe JavaScript ("class X extends Y" / "constructor(") é checada ANTES
    do fallback genérico "class \\w+ -> python" logo abaixo, para não tratar
    uma classe puramente JS (sem nenhuma outra palavra da lista de JS) como
    Python só por ter a palavra `class`.
    """
    amostra = codigo[:400]
    if re.search(r"<(!DOCTYPE|html|div|p|a|span|body|head|section|button)\b", amostra, re.IGNORECASE):
        return "html"
    if re.search(r"\b(def |import |print\(|elif |self\.|if __name__)", amostra):
        return "python"
    if re.search(r"\b(function |const |let |var |console\.log\(|=>|document\.|await |extends |constructor\()", amostra):
        return "javascript"
    if re.search(r"\bclass \w+", amostra):
        return "python"
    return "css"


def responder_geral(pergunta: str, modelo: str = MODELO_PADRAO) -> str | None:
    """Pede ao modelo local uma resposta livre — o último recurso da Tartaruga.

    Chamado quando classificador, base curada e base aprendida JÁ FORAM
    TENTADOS e nenhum soube responder. Diferente de `gerar()`, não há bloco
    de código para extrair nem sintaxe para validar - a pergunta pode ser
    qualquer coisa, então o resultado é o texto puro do modelo, ou None em
    qualquer falha (Ollama fora do ar, timeout, resposta vazia).

    O chamador (`nucleo.py`) é responsável por marcar a resposta como vinda
    de um modelo de linguagem antes de mostrá-la — a mesma transparência já
    aplicada ao conteúdo aprendido por pesquisa e ao código gerado.
    """
    corpo = {
        "model": modelo,
        "prompt": f"{PROMPT_GERAL}\n\nPergunta: {pergunta.strip()}",
        "stream": False,
        "options": {"temperature": 0.6, "num_predict": LIMITE_TOKENS_GERAL},
    }

    try:
        requisicao = urllib.request.Request(
            OLLAMA_URL,
            data=json.dumps(corpo).encode("utf-8"),
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        with urllib.request.urlopen(requisicao, timeout=TEMPO_LIMITE) as resposta:
            dados = json.loads(resposta.read().decode("utf-8"))
    except ERROS_DO_SERVICO:
        return None
    except (json.JSONDecodeError, UnicodeDecodeError):
        return None

    return _texto_da_resposta(dados) or None
