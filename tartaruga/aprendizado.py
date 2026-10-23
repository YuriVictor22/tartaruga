"""
Aprendizado por pesquisa: como a Tartaruga adquire conhecimento novo.

Até aqui ela só sabia o que estava escrito à mão em `dados/conhecimento.json`.
Este módulo permite que ela AMPLIE a própria base: pesquisa um assunto na
web, julga a qualidade das fontes, extrai o conteúdo e grava uma entrada nova.

---------------------------------------------------------------------------
O que "aprender" significa aqui - e o que não significa
---------------------------------------------------------------------------
Sem um modelo de linguagem, ela não COMPREENDE o que leu. Seria desonesto
dizer que sim. O que ela faz, e faz de verdade:

    1. formula uma consulta de busca a partir do assunto
    2. avalia as fontes e descarta as ruins
    3. baixa a melhor página e extrai texto e exemplos de código
    4. monta uma entrada e a grava, junto com a procedência
    5. passa a responder sobre aquele assunto, citando de onde veio

Isso é recuperação de informação com curadoria automática - não é
compreensão. A distinção está registrada no README e nas respostas: todo
conteúdo aprendido aparece marcado, com a fonte visível, para que quem lê
possa conferir.

---------------------------------------------------------------------------
A parte mais importante: julgar a fonte
---------------------------------------------------------------------------
Buscar é fácil; escolher em quem confiar é o que separa aprender de repetir
besteira. A internet não ordena resultados por correção - ordena por
popularidade e otimização para buscadores, que são coisas diferentes.

Por isso existe uma hierarquia explícita de confiança, e ela é a parte deste
arquivo que mais vale ler.
"""

import json
import re
import urllib.error
import urllib.request
from dataclasses import dataclass, field
from datetime import date
from html.parser import HTMLParser

from .caminhos import gravavel
from .ferramentas import web

CAMINHO_APRENDIDO = gravavel("dados_aprendidos.json")

TEMPO_LIMITE_REDE = 12
TAMANHO_MAXIMO_PAGINA = 800_000

# Identificamo-nos honestamente. Fingir ser um navegador para driblar bloqueio
# é má prática; alguns sites recusam requisições sem User-Agent nenhum, então
# enviamos um que diz o que somos.
CABECALHOS = {
    "User-Agent": "Tartaruga/1.0 (projeto academico de ADS; aprendizado por pesquisa)",
    "Accept-Language": "pt-BR,pt;q=0.9,en;q=0.8",
}


# ===========================================================================
# 1. HIERARQUIA DE CONFIANÇA DAS FONTES
# ===========================================================================

# NÍVEL 1 - Documentação primária.
# Escrita por quem mantém a própria tecnologia. Quando a especificação e um
# blog discordam, a especificação está certa por definição: ela É a regra.
DOMINIOS_OFICIAIS = {
    # Web
    "developer.mozilla.org", "w3.org", "whatwg.org", "web.dev",
    "developer.chrome.com", "webkit.org", "tc39.es", "ecma-international.org",
    # Linguagens e plataformas
    "docs.python.org", "python.org", "peps.python.org", "nodejs.org",
    "typescriptlang.org", "go.dev", "rust-lang.org", "docs.oracle.com",
    "learn.microsoft.com", "php.net", "ruby-lang.org",
    # Frameworks
    "react.dev", "vuejs.org", "angular.dev", "svelte.dev",
    "docs.djangoproject.com", "flask.palletsprojects.com",
    "fastapi.tiangolo.com", "expressjs.com", "tailwindcss.com",
    # Ferramentas
    "git-scm.com", "postgresql.org", "sqlite.org", "docker.com",
}

# NÍVEL 2 - Comunidade com reputação.
# Não são normativas, mas têm revisão editorial, correção de erros e
# reputação a perder. Boas para explicações e exemplos didáticos.
DOMINIOS_CONFIAVEIS = {
    "stackoverflow.com", "javascript.info", "css-tricks.com",
    "freecodecamp.org", "smashingmagazine.com", "realpython.com",
    "baeldung.com", "digitalocean.com", "caniuse.com", "devdocs.io",
    "wikipedia.org", "github.com", "gitlab.com", "kernel.org",
    "refactoring.guru", "patterns.dev", "overreacted.io",
}

# NÍVEL 3 - Usar com ressalva.
# Populares nos buscadores, qualidade irregular. O W3Schools é o caso
# clássico: aparece em primeiro lugar para quase tudo e já foi notório por
# imprecisões - melhorou, mas continua sendo segunda opção diante da MDN.
# Medium e dev.to aceitam qualquer autor, sem revisão.
DOMINIOS_CAUTELA = {
    "w3schools.com", "geeksforgeeks.org", "tutorialspoint.com",
    "javatpoint.com", "medium.com", "dev.to", "hashnode.dev",
    "blogspot.com", "wordpress.com", "quora.com", "reddit.com",
}

# NÍVEL 4 - Evitar.
# Sites que copiam respostas do Stack Overflow sem crédito nem atualização.
# Costumam trazer código obsoleto com aparência de atual, que é o pior
# tipo de erro: o que parece certo.
DOMINIOS_EVITAR = {
    "coderanch.com", "codegrepper.com", "stackoverflow.tech",
    "programcreek.com", "csdn.net", "cnblogs.com", "qastack.com",
    "stackoom.com", "code-examples.net",
}

PONTUACAO_BASE = {
    "oficial": 100,
    "confiavel": 70,
    "cautela": 35,
    "desconhecido": 45,
    "evitar": 0,
}


@dataclass
class Fonte:
    """Um resultado de busca já avaliado."""

    titulo: str
    url: str
    trecho: str
    dominio: str
    categoria: str
    pontuacao: int
    motivos: list[str] = field(default_factory=list)

    @property
    def confiavel(self) -> bool:
        return self.categoria in ("oficial", "confiavel")


def extrair_dominio(url: str) -> str:
    """Devolve o domínio de uma URL, sem 'www.'."""
    achado = re.match(r"https?://([^/]+)", url, re.IGNORECASE)
    if not achado:
        return ""
    dominio = achado.group(1).lower()
    return dominio[4:] if dominio.startswith("www.") else dominio


def _categoria_do_dominio(dominio: str) -> str:
    """Classifica o domínio na hierarquia de confiança.

    A comparação aceita subdomínios: `docs.python.org` casa com uma regra
    para `python.org`, e `pt.wikipedia.org` casa com `wikipedia.org`.
    """
    for conjunto, nome in (
        (DOMINIOS_EVITAR, "evitar"),
        (DOMINIOS_OFICIAIS, "oficial"),
        (DOMINIOS_CONFIAVEIS, "confiavel"),
        (DOMINIOS_CAUTELA, "cautela"),
    ):
        for alvo in conjunto:
            if dominio == alvo or dominio.endswith("." + alvo):
                return nome
    return "desconhecido"


class AvaliadorFontes:
    """Ordena resultados de busca por confiabilidade, não por posição.

    A ordem que o buscador devolve reflete popularidade e otimização para
    buscadores. Nenhuma das duas coisas é sinônimo de estar correto. Aqui
    reordenamos por critérios que têm a ver com qualidade da informação.
    """

    def avaliar(self, resultado: web.ResultadoWeb) -> Fonte:
        dominio = extrair_dominio(resultado.link)
        categoria = _categoria_do_dominio(dominio)
        pontuacao = PONTUACAO_BASE[categoria]
        motivos: list[str] = []

        if categoria == "oficial":
            motivos.append("documentação oficial da tecnologia")
        elif categoria == "confiavel":
            motivos.append("fonte de comunidade com boa reputação")
        elif categoria == "cautela":
            motivos.append("popular, mas de qualidade irregular")
        elif categoria == "evitar":
            motivos.append("site de conteúdo copiado — descartado")
        else:
            motivos.append("domínio desconhecido")

        # HTTPS não garante conteúdo correto, mas indica um site minimamente
        # mantido. Em 2026, quem não tem certificado não cuida do resto.
        if resultado.link.startswith("https://"):
            pontuacao += 5
        else:
            pontuacao -= 10
            motivos.append("sem HTTPS")

        # Um trecho muito curto costuma indicar página de índice ou lista de
        # links, não conteúdo explicativo.
        if len(resultado.trecho) >= 120:
            pontuacao += 8
        elif len(resultado.trecho) < 40:
            pontuacao -= 8
            motivos.append("pouco conteúdo textual")

        # Páginas de referência específica valem mais que a raiz do site.
        if resultado.link.count("/") >= 4:
            pontuacao += 4

        return Fonte(
            titulo=resultado.titulo,
            url=resultado.link,
            trecho=resultado.trecho,
            dominio=dominio,
            categoria=categoria,
            pontuacao=max(0, pontuacao),
            motivos=motivos,
        )

    def ordenar(self, resultados: list[web.ResultadoWeb]) -> list[Fonte]:
        """Avalia e ordena, descartando o que estiver na lista de evitar."""
        fontes = [self.avaliar(r) for r in resultados]
        aproveitaveis = [f for f in fontes if f.categoria != "evitar"]
        return sorted(aproveitaveis, key=lambda f: f.pontuacao, reverse=True)


# ===========================================================================
# 2. EXTRAÇÃO DO CONTEÚDO DA PÁGINA
# ===========================================================================

# Elementos cujo conteúdo nunca é texto para leitura.
TAGS_IGNORADAS = {"script", "style", "noscript", "svg", "head", "nav", "footer"}

# Texto que TODA página tem e NENHUMA página quis dizer.
#
# Isto apareceu logo no primeiro teste real: ao estudar flexbox, o resumo
# guardado começava com "Esta página foi traduzida do inglês pela comunidade.
# Saiba mais e junte-se à comunidade MDN Web Docs." - um aviso do site, não
# uma explicação de flexbox.
#
# O problema é que esse texto satisfaz todos os critérios estruturais: é um
# parágrafo, tem tamanho suficiente, está fora de <nav> e <footer>. Só o
# CONTEÚDO denuncia. Daí a lista abaixo.
PADROES_RUIDO = re.compile(
    r"(esta p[áa]gina foi traduzida|this page (was|is) translated"
    r"|junte-se [àa] comunidade|join the .{0,30}community"
    r"|saiba mais e junte|learn more and join"
    r"|aceitar (todos os )?cookies|accept (all )?cookies|pol[íi]tica de privacidade"
    r"|privacy policy|todos os direitos reservados|all rights reserved"
    r"|fa[çc]a login|inscreva-se|sign up (for|to)|subscribe to our"
    r"|newsletter|skip to (main )?content|pular para o conte[úu]do"
    r"|habilite o javascript|enable javascript"
    r"|este artigo foi [úu]til|was this (page|article) helpful"
    r"|this feature is well established|esta funcionalidade est[áa] bem estabelecida"
    r"|works across many devices|funciona em v[áa]rios dispositivos"
    r"|it.s been available across browsers|dispon[íi]vel em navegadores desde"
    r"|baseline (widely|newly) available|experimental.{0,20}n[ãa]o use"
    r"|siga-nos|follow us on|compartilhe|share this"
    r"|[úu]ltima (modifica[çc][ãa]o|atualiza[çc][ãa]o)|last modified"
    r"|contribuidores desta p[áa]gina|contributors to this page"
    # Acrescentados depois de um teste real: uma página de FÓRUM DE CURSO
    # (cursos.alura.com.br) passou por todos os filtros acima e foi salva
    # como conhecimento - o texto era propaganda da plataforma, não
    # explicação do assunto perguntado.
    r"|nova experi[êe]ncia|identidade visual novinha|matricule-se"
    r"|garanta (sua vaga|seu acesso)|assine (agora|j[áa])|fa[çc]a parte da"
    r"|conhe[çc]a (nossos|os) (planos|cursos)|acesso a todos os cursos"
    r"|teste gr[áa]tis|comece (agora|hoje)|experimente gr[áa]tis"
    # Acrescentado depois de outro teste real: páginas de refactoring.guru
    # sobre padrões de projeto (Singleton, Observer) vieram com propaganda de
    # um curso de terceiros ("GitByBit.com") repetida várias vezes no meio
    # do texto extraído - mesma classe de bug do Alura acima, fonte
    # diferente. A lição se repete: qualquer site pode ter esse tipo de
    # injeção, então o filtro precisa crescer conforme aparece, não é algo
    # que dá para prever todo de uma vez.
    r"|d[áa]\s+uma\s+olhada|curso novo (de|do)|meu curso"
    r"|quer dar um up)",
    re.IGNORECASE,
)

# Frases que abrem uma pergunta de fórum, escrita por OUTRO usuário - não é
# conhecimento, é a MESMA dúvida que a Tartaruga está tentando responder.
# Descoberto no mesmo teste real: depois de filtrado o ruído promocional, o
# que sobrava da página da Alura era a pergunta de outra pessoa ("Eu
# gostaria de saber se toda linguagem tem documentação...") - sem nenhuma
# resposta. Um parágrafo assim passava em todos os critérios estruturais
# (tamanho, pontuação, fora de tags de navegação) porque É prosa de verdade;
# só não é uma EXPLICAÇÃO, é a pergunta que alguém fez.
PADRAO_PERGUNTA_ALHEIA = re.compile(
    r"^\s*(eu\s+)?gostaria\s+de\s+saber|^\s*algu[ée]m\s+sabe"
    r"|^\s*tem\s+como|^\s*ser[áa]\s+que|^\s*existe\s+alguma\s+forma"
    r"|^\s*como\s+fa[çc]o\s+para|^\s*algu[ée]m\s+(pode|poderia)\s+me\s+ajudar",
    re.IGNORECASE,
)


def _e_conteudo_util(paragrafo: str) -> bool:
    """Decide se um parágrafo é explicação, ou mobília do site, ou pergunta alheia.

    Três critérios, todos necessários:

    1. Não bater com os padrões de ruído (mobília do site, propaganda).
    2. Não ser a ABERTURA de uma pergunta feita por outra pessoa - isso é
       prosa de verdade, mas não é uma resposta a guardar.
    3. Parecer uma explicação de verdade - ter ao menos uma frase
       DECLARATIVA (ponto final ou exclamação). Um parágrafo que só termina
       em "?" pode ser inteiramente uma pergunta, sem informação nenhuma;
       exigir "." ou "!" filtra isso sem proibir perguntas retóricas dentro
       de uma explicação maior ("Por que isso importa? Porque X.").
    """
    if PADROES_RUIDO.search(paragrafo):
        return False
    if PADRAO_PERGUNTA_ALHEIA.search(paragrafo):
        return False
    return "." in paragrafo or "!" in paragrafo


class ExtratorPagina(HTMLParser):
    """Extrai texto corrido e blocos de código de uma página HTML.

    Escrito sobre o `html.parser` da biblioteca padrão, mantendo o projeto
    sem dependências novas. Não é um navegador: ignora JavaScript e não
    monta layout. Para documentação técnica, que é texto estruturado, isso
    basta.

    IMPORTANTE: o conteúdo baixado é DADO, nunca instrução. A Tartaruga o
    trata como texto a ser guardado e exibido com a fonte à vista - jamais
    como comando a executar.
    """

    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.paragrafos: list[str] = []
        self.codigos: list[str] = []
        self._pilha_ignorar: list[str] = []
        self._em_codigo = 0
        self._buffer_texto: list[str] = []
        self._buffer_codigo: list[str] = []

    def handle_starttag(self, tag, attrs):
        if tag in TAGS_IGNORADAS:
            self._pilha_ignorar.append(tag)
        elif tag in ("pre", "code"):
            self._em_codigo += 1
        elif tag in ("p", "li", "h1", "h2", "h3", "h4", "div", "br"):
            self._fechar_paragrafo()

    def handle_endtag(self, tag):
        if self._pilha_ignorar and self._pilha_ignorar[-1] == tag:
            self._pilha_ignorar.pop()
        elif tag in ("pre", "code"):
            self._em_codigo = max(0, self._em_codigo - 1)
            if self._em_codigo == 0:
                self._fechar_codigo()
        elif tag in ("p", "li", "h1", "h2", "h3", "h4", "div"):
            self._fechar_paragrafo()

    def handle_data(self, data):
        if self._pilha_ignorar:
            return
        if self._em_codigo:
            self._buffer_codigo.append(data)
        else:
            self._buffer_texto.append(data)

    def _fechar_paragrafo(self) -> None:
        texto = re.sub(r"\s+", " ", "".join(self._buffer_texto)).strip()
        self._buffer_texto = []
        # Fragmentos curtos são quase sempre rótulos de menu, migalhas de
        # navegação ou legendas — não conteúdo explicativo.
        if len(texto) >= 60 and _e_conteudo_util(texto):
            self.paragrafos.append(texto)

    def _fechar_codigo(self) -> None:
        codigo = "".join(self._buffer_codigo).strip()
        self._buffer_codigo = []
        if 12 <= len(codigo) <= 1200:
            self.codigos.append(codigo)

    def close(self):
        super().close()
        self._fechar_paragrafo()
        self._fechar_codigo()


def baixar_pagina(url: str) -> str | None:
    """Baixa o HTML de uma página. Devolve None se não der certo.

    Nenhuma falha aqui pode derrubar o assistente: rede fora do ar, página
    removida, site que recusa robôs, conteúdo que não é HTML — tudo isso é
    normal e resulta apenas em "não consegui aprender agora".
    """
    try:
        requisicao = urllib.request.Request(url, headers=CABECALHOS)
        with urllib.request.urlopen(requisicao, timeout=TEMPO_LIMITE_REDE) as resposta:
            tipo = resposta.headers.get("Content-Type", "")
            if "html" not in tipo.lower():
                return None
            bruto = resposta.read(TAMANHO_MAXIMO_PAGINA)
    except (urllib.error.URLError, urllib.error.HTTPError, OSError, ValueError):
        return None

    codificacao = "utf-8"
    achado = re.search(rb'charset=["\']?([\w\-]+)', bruto[:2000], re.IGNORECASE)
    if achado:
        try:
            codificacao = achado.group(1).decode("ascii")
        except UnicodeDecodeError:
            pass

    try:
        return bruto.decode(codificacao, errors="replace")
    except (LookupError, UnicodeDecodeError):
        return bruto.decode("utf-8", errors="replace")


def extrair_conteudo(html_bruto: str) -> tuple[list[str], list[str]]:
    """Devolve (parágrafos, blocos de código) de uma página."""
    extrator = ExtratorPagina()
    try:
        extrator.feed(html_bruto)
        extrator.close()
    except Exception:
        # Um parser de HTML tolerante ainda pode falhar em página muito
        # malformada. Aproveitamos o que já foi extraído até ali.
        pass
    return extrator.paragrafos, extrator.codigos


# ===========================================================================
# 3. O APRENDIZ
# ===========================================================================

@dataclass
class ResultadoAprendizado:
    """O que aconteceu numa tentativa de aprender."""

    sucesso: bool
    assunto: str
    mensagem: str
    fontes_avaliadas: list[Fonte] = field(default_factory=list)
    entrada: dict | None = None


class Aprendiz:
    """Pesquisa um assunto, escolhe a melhor fonte e grava o que aprendeu."""

    def __init__(self, caminho=None) -> None:
        self.caminho = caminho or CAMINHO_APRENDIDO
        self.avaliador = AvaliadorFontes()
        self.entradas: list[dict] = []
        self.carregar()

    # -- persistência ---------------------------------------------------

    def carregar(self) -> None:
        if not self.caminho.exists():
            self.entradas = []
            return
        try:
            with open(self.caminho, encoding="utf-8") as arquivo:
                dados = json.load(arquivo)
        except (json.JSONDecodeError, UnicodeDecodeError, OSError):
            self.entradas = []
            return
        # JSON VÁLIDO não garante o formato esperado (`null`, número, texto,
        # itens sem `id`...): sem esta checagem o Aprendiz - criado na
        # inicialização do app - quebrava com TypeError/KeyError depois.
        if not isinstance(dados, list):
            self.entradas = []
            return
        self.entradas = [e for e in dados if isinstance(e, dict) and isinstance(e.get("id"), str)]

    def salvar(self) -> None:
        gravar_json_atomico(self.caminho, self.entradas)

    def ja_sabe(self, assunto: str) -> dict | None:
        chave = _identificador(assunto)
        return next((e for e in self.entradas if e["id"] == chave), None)

    def remover(self, identificador: str) -> bool:
        antes = len(self.entradas)
        self.entradas = [e for e in self.entradas if e.get("id") != identificador]
        if len(self.entradas) == antes:
            return False
        self.salvar()
        return True

    def marcar_incorreta(self, identificador: str) -> bool:
        entrada = next((e for e in self.entradas if e.get("id") == identificador), None)
        if entrada is None:
            return False
        entrada["revisao"] = "incorreta"
        entrada["ativa"] = False
        self.salvar()
        return True

    def listar_fontes(self) -> list[dict]:
        return [{"id": e.get("id", ""), "titulo": e.get("titulo", ""),
                 "url": e.get("fonte_url", ""), "dominio": e.get("fonte_dominio", ""),
                 "data": e.get("data", ""), "ativa": e.get("ativa", True)} for e in self.entradas]

    # -- aprendizado ----------------------------------------------------

    def montar_consulta(self, assunto: str) -> str:
        """Transforma o assunto numa consulta melhor para o buscador.

        Acrescentar "documentação" e o idioma muda bastante o resultado:
        empurra a documentação oficial para cima e afasta fóruns e vídeos.
        Formular bem a busca é parte de pesquisar bem.
        """
        limpo = assunto.strip().rstrip("?.!")
        return f"{limpo} documentação exemplo"

    def aprender(self, assunto: str, forcar: bool = False) -> ResultadoAprendizado:
        """Executa o ciclo completo de aprendizado sobre um assunto."""
        # O lstrip do ﻿ remove a marca de ordem de bytes (BOM), que vem
        # grudada quando o assunto chega de um arquivo UTF-8 gerado no
        # Windows. Sem isso, ela entra no título e no identificador do que
        # foi aprendido - um caractere invisível corrompendo o registro.
        assunto = assunto.lstrip("﻿").strip()
        if not assunto:
            return ResultadoAprendizado(False, assunto, "Não disseram o que estudar.")

        if not forcar and (existente := self.ja_sabe(assunto)):
            return ResultadoAprendizado(
                True,
                assunto,
                f"Já estudei isso antes (fonte: {existente['fonte_dominio']}).",
                entrada=existente,
            )

        resposta = web.buscar(self.montar_consulta(assunto), quantidade=6)
        if not resposta.ok:
            return ResultadoAprendizado(
                False, assunto, f"Não consegui pesquisar: {resposta.erro}"
            )

        fontes = self.avaliador.ordenar(resposta.resultados)
        if not fontes:
            return ResultadoAprendizado(
                False, assunto,
                "Encontrei resultados, mas nenhum de fonte aproveitável.",
                fontes_avaliadas=[],
            )

        # Tentamos as melhores em ordem: a primeira pode recusar robôs ou
        # estar fora do ar, e desistir na primeira falha desperdiçaria uma
        # busca inteira.
        for fonte in fontes[:3]:
            html_bruto = baixar_pagina(fonte.url)
            if not html_bruto:
                continue

            paragrafos, codigos = extrair_conteudo(html_bruto)
            if len(paragrafos) < 2:
                continue

            entrada = self._montar_entrada(assunto, fonte, paragrafos, codigos)
            self.entradas = [e for e in self.entradas if e["id"] != entrada["id"]]
            self.entradas.append(entrada)
            self.salvar()

            return ResultadoAprendizado(
                True, assunto,
                f"Aprendi sobre \"{assunto}\" lendo {fonte.dominio}.",
                fontes_avaliadas=fontes,
                entrada=entrada,
            )

        return ResultadoAprendizado(
            False, assunto,
            "Achei fontes boas, mas não consegui baixar o conteúdo de nenhuma.",
            fontes_avaliadas=fontes,
        )

    def _montar_entrada(
        self, assunto: str, fonte: Fonte, paragrafos: list[str], codigos: list[str]
    ) -> dict:
        """Constrói a entrada de conhecimento a partir do que foi extraído.

        Pegamos os primeiros parágrafos porque documentação técnica quase
        sempre define o conceito logo na abertura — o detalhamento e os
        casos especiais vêm depois.
        """
        resumo = " ".join(paragrafos[:3])
        if len(resumo) > 900:
            resumo = resumo[:900].rsplit(" ", 1)[0] + "..."

        codigo = ""
        if codigos:
            # O exemplo mais longo dentro de um limite: trechos minúsculos
            # costumam ser nomes de função soltos no meio do texto.
            candidatos = [c for c in codigos if 30 <= len(c) <= 700]
            if candidatos:
                codigo = max(candidatos, key=len)

        return {
            "id": _identificador(assunto),
            "titulo": _titular(assunto),
            "perguntas": _gerar_variacoes(assunto),
            "resposta": resumo,
            "codigo": codigo,
            "aprendido": True,
            "fonte_url": fonte.url,
            "fonte_dominio": fonte.dominio,
            "fonte_categoria": fonte.categoria,
            "data": date.today().isoformat(),
        }


def _titular(assunto: str) -> str:
    """Monta o título preservando siglas e nomes próprios.

    `str.capitalize()` põe a primeira letra em maiúscula e REBAIXA todo o
    resto - o que transformou "CORS" em "Cors" e destruiria "JWT", "HTTP",
    "SQL" e "API" do mesmo jeito.

    Aqui cada palavra é decidida por si: quem já tem maiúscula no meio
    (sigla ou nome próprio) fica como está; só as inteiramente minúsculas
    recebem a inicial maiúscula, e apenas na primeira palavra.
    """
    palavras = assunto.strip().split()
    if not palavras:
        return assunto.strip()

    resultado = []
    for posicao, palavra in enumerate(palavras):
        if palavra != palavra.lower():
            resultado.append(palavra)          # tem maiúscula: preserva
        elif posicao == 0:
            resultado.append(palavra.capitalize())
        else:
            resultado.append(palavra)
    return " ".join(resultado)


def _identificador(assunto: str) -> str:
    """Gera um id estável e legível a partir do assunto."""
    import unicodedata

    texto = unicodedata.normalize("NFD", assunto.lower())
    texto = "".join(c for c in texto if unicodedata.category(c) != "Mn")
    texto = re.sub(r"[^a-z0-9]+", "-", texto).strip("-")
    return f"aprendido-{texto[:50]}" if texto else "aprendido-sem-nome"


def _gerar_variacoes(assunto: str) -> list[str]:
    """Formulações da mesma pergunta, para o índice de similaridade.

    Uma entrada indexada por uma frase só é encontrada apenas por quem
    escrever quase exatamente aquela frase. Gerar variações naturais amplia
    bastante o alcance da busca.

    Caso especial: assunto COMPOSTO ("WeakMap e WeakSet", "debounce e
    throttle"). Descoberto num teste real: perguntar só sobre "WeakMap"
    tinha cosseno 0,707 contra a entrada indexada - matematicamente correto
    (a pergunta cobre 1 de 2 conceitos do documento), mas abaixo do limiar,
    então a Tartaruga dizia "não sei" sobre um assunto que TINHA acabado de
    estudar. A correção não é afrouxar o limiar global, que reabriria os
    falsos positivos já corrigidos - é reconhecer que "X e Y" também deveria
    responder por perguntas só sobre X e só sobre Y.
    """
    base = assunto.strip().rstrip("?.!")
    variacoes = [
        base,
        f"o que é {base}",
        f"como funciona {base}",
        f"como usar {base}",
        f"me explica {base}",
    ]

    partes = re.split(r"\s+e\s+", base, maxsplit=1, flags=re.IGNORECASE)
    if len(partes) == 2 and all(len(p.split()) <= 3 for p in partes):
        for parte in partes:
            variacoes.append(f"o que é {parte.strip()}")
            variacoes.append(parte.strip())

    return variacoes
from .persistencia import gravar_json_atomico
