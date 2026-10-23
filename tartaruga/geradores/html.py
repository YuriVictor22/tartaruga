"""
Gerador de HTML: monta seis padrões comuns a partir de parâmetros.

Cada função devolve uma string de HTML pronta. Nenhuma delas lê arquivo, faz
rede ou executa nada — são funções puras, fáceis de testar isoladamente.

Todo texto que vem do PEDIDO DO USUÁRIO (nomes de campo, títulos de card,
itens de lista, links de menu) passa por `html.escape` antes de entrar no
template. Sem isso, um título como `Ofertas <script>` viraria HTML executável
dentro do próprio HTML gerado — o mesmo cuidado já tomado ao extrair páginas
da web em `aprendizado.py` e ao renderizar a conversa em `interface.py`.
"""

import html as _html_stdlib

# ---------------------------------------------------------------------------
# Vocabulário de campos de formulário conhecidos
#
# Cada campo tem um tipo de <input> apropriado e um rótulo em português.
# Campos fora deste dicionário ainda funcionam — viram <input type="text">
# com o próprio nome como rótulo — mas sem o tipo certo (um "telefone" fora
# da lista não ganharia type="tel", por exemplo).
# ---------------------------------------------------------------------------
CAMPOS_CONHECIDOS: dict[str, tuple[str, str]] = {
    "nome": ("text", "Nome"),
    "email": ("email", "E-mail"),
    "senha": ("password", "Senha"),
    "usuario": ("text", "Usuário"),
    "usuário": ("text", "Usuário"),
    "telefone": ("tel", "Telefone"),
    "celular": ("tel", "Celular"),
    "idade": ("number", "Idade"),
    "data": ("date", "Data"),
    "nascimento": ("date", "Data de nascimento"),
    "mensagem": ("textarea", "Mensagem"),
    "cidade": ("text", "Cidade"),
    "endereco": ("text", "Endereço"),
    "endereço": ("text", "Endereço"),
    "cpf": ("text", "CPF"),
    "cnpj": ("text", "CNPJ"),
    "assunto": ("text", "Assunto"),
    "site": ("url", "Site"),
    "cep": ("text", "CEP"),
}

# Campos que, por convenção, quase sempre são obrigatórios num formulário.
CAMPOS_OBRIGATORIOS_PADRAO = {"nome", "email", "senha", "usuario", "usuário"}


def _seguro(texto: str) -> str:
    """Escapa texto vindo do usuário antes de entrar num template HTML."""
    return _html_stdlib.escape(str(texto).strip())


def _slug(texto: str) -> str:
    """Versão do texto segura para usar como id/href (sem espaço, minúscula)."""
    import re
    import unicodedata

    sem_acento = unicodedata.normalize("NFD", texto.lower())
    sem_acento = "".join(c for c in sem_acento if unicodedata.category(c) != "Mn")
    return re.sub(r"[^a-z0-9]+", "-", sem_acento).strip("-") or "item"


def pagina(titulo: str = "Minha Página", secoes: list[str] | None = None) -> str:
    """Esqueleto completo de uma página HTML.

    Sem os `secoes` explícitos, entra um corpo mínimo mas válido — a mesma
    espinha dorsal descrita na entrada curada "HTML: estrutura de uma
    página": doctype, charset, viewport, título.
    """
    corpo = "\n  ".join(secoes) if secoes else (
        "<h1>Bem-vindo</h1>\n  <p>Conteúdo da página.</p>"
    )
    return f"""<!DOCTYPE html>
<html lang="pt-BR">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <title>{_seguro(titulo)}</title>
  <link rel="stylesheet" href="estilo.css">
</head>
<body>
  {corpo}
</body>
</html>"""


def landing_page() -> str:
    """Página autocontida, sem bibliotecas, formulários falsos ou recursos remotos."""
    return '''<!DOCTYPE html>
<html lang="pt-BR">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <title>Seu projeto — conheça nossa proposta</title>
  <style>
    * { box-sizing: border-box; }
    body { margin: 0; font: 1rem/1.6 system-ui, sans-serif; color: #142b25; background: #f6faf7; }
    .container { width: min(1100px, 90%); margin: auto; }
    header { border-bottom: 1px solid #d7e5dd; padding: 1rem 0; }
    nav { display: flex; justify-content: space-between; gap: 1rem; flex-wrap: wrap; }
    a { color: #145c40; }
    .hero { padding: clamp(3rem, 10vw, 7rem) 0; max-width: 760px; }
    h1 { font-size: clamp(2rem, 6vw, 4rem); line-height: 1.12; }
    .botao { display: inline-block; background: #145c40; color: white; padding: .8rem 1.4rem; border-radius: .5rem; }
    .cards { display: grid; grid-template-columns: repeat(auto-fit, minmax(min(240px, 100%), 1fr)); gap: 1rem; }
    article { padding: 1.5rem; background: white; border: 1px solid #d7e5dd; border-radius: 1rem; }
    section { padding-bottom: 3rem; }
    footer { padding: 2rem 0; border-top: 1px solid #d7e5dd; }
    :focus-visible { outline: 3px solid #c16700; outline-offset: 4px; }
  </style>
</head>
<body>
  <header><nav class="container" aria-label="Principal"><strong>Seu projeto</strong><a href="#beneficios">Benefícios</a><a href="#contato">Contato</a></nav></header>
  <main class="container">
    <section class="hero"><p>Uma proposta feita para você</p><h1>Uma solução simples para o seu próximo passo.</h1><p>Apresente aqui seu produto, o público que atende e o problema que resolve.</p><a class="botao" href="#contato">Quero saber mais</a></section>
    <section id="beneficios"><h2>Por que escolher nosso projeto?</h2><div class="cards"><article><h3>Simplicidade</h3><p>Explique o primeiro benefício de forma concreta.</p></article><article><h3>Qualidade</h3><p>Descreva o que torna sua proposta útil.</p></article><article><h3>Proximidade</h3><p>Conte como você atende e acompanha seus clientes.</p></article></div></section>
    <section id="contato"><h2>Vamos conversar?</h2><p>Substitua este texto pelo seu e-mail ou telefone de contato.</p></section>
  </main>
  <footer><div class="container">Seu projeto · Personalize esta página antes de publicar.</div></footer>
</body>
</html>'''


def formulario(
    campos: list[str] | None = None,
    titulo: str | None = None,
    acao: str = "/enviar",
) -> str:
    """Formulário com os campos pedidos, cada um com o `<label>` ligado ao `<input>`.

    Os dois cuidados que a entrada curada "HTML: formulários" ensina são
    aplicados aqui de propósito: todo campo tem `label` associado por
    `for`/`id`, e `name` presente para o dado ser enviado de fato.
    """
    campos = campos or ["nome", "email", "mensagem"]

    blocos = []
    for campo_bruto in campos:
        chave = campo_bruto.strip().lower()
        tipo, rotulo_padrao = CAMPOS_CONHECIDOS.get(chave, ("text", campo_bruto.strip().capitalize()))
        rotulo = _seguro(rotulo_padrao)
        id_campo = _slug(chave)
        obrigatorio = " required" if chave in CAMPOS_OBRIGATORIOS_PADRAO else ""

        if tipo == "textarea":
            blocos.append(
                f'  <label for="{id_campo}">{rotulo}</label>\n'
                f'  <textarea id="{id_campo}" name="{id_campo}" rows="4"{obrigatorio}></textarea>'
            )
        else:
            blocos.append(
                f'  <label for="{id_campo}">{rotulo}</label>\n'
                f'  <input type="{tipo}" id="{id_campo}" name="{id_campo}"{obrigatorio}>'
            )

    corpo = "\n\n".join(blocos)
    comentario = f"  <!-- {_seguro(titulo)} -->\n" if titulo else ""
    return f"""{comentario}<form action="{acao}" method="post">
{corpo}

  <button type="submit">Enviar</button>
</form>"""


def navbar(links: list[str] | None = None) -> str:
    """Barra de navegação com os itens de menu pedidos."""
    links = links or ["Início", "Sobre", "Contato"]
    itens = "\n".join(
        f'      <li><a href="#{_slug(l)}">{_seguro(l)}</a></li>' for l in links
    )
    return f"""<nav>
  <ul>
{itens}
  </ul>
</nav>"""


def card(
    titulo: str = "Título do card",
    texto: str = "Descrição do conteúdo.",
    com_imagem: bool = False,
) -> str:
    """Um cartão de conteúdo — título, texto e, opcionalmente, imagem."""
    linha_imagem = f'  <img src="imagem.jpg" alt="{_seguro(titulo)}">\n' if com_imagem else ""
    return f"""<div class="card">
{linha_imagem}  <h3>{_seguro(titulo)}</h3>
  <p>{_seguro(texto)}</p>
</div>"""


def lista(itens: list[str] | None = None, ordenada: bool = False) -> str:
    """Lista não-ordenada (`<ul>`) ou ordenada (`<ol>`)."""
    itens = itens or ["Primeiro item", "Segundo item", "Terceiro item"]
    tag = "ol" if ordenada else "ul"
    linhas = "\n".join(f"  <li>{_seguro(item)}</li>" for item in itens)
    return f"<{tag}>\n{linhas}\n</{tag}>"


def tabela(colunas: list[str] | None = None, linhas: int = 3) -> str:
    """Tabela com as colunas pedidas e um número de linhas vazias para preencher."""
    colunas = colunas or ["Nome", "Idade", "Cidade"]
    # Limite defensivo: alguém pedindo "uma tabela com 500000 linhas" não
    # deveria gerar um documento gigante por engano de digitação.
    linhas = max(1, min(linhas, 50))

    cabecalho = "".join(f"<th>{_seguro(c)}</th>" for c in colunas)
    corpo_linhas = []
    for _ in range(linhas):
        celulas = "".join("<td></td>" for _ in colunas)
        corpo_linhas.append(f"    <tr>{celulas}</tr>")
    corpo = "\n".join(corpo_linhas)

    return f"""<table>
  <thead>
    <tr>{cabecalho}</tr>
  </thead>
  <tbody>
{corpo}
  </tbody>
</table>"""


def botao(texto: str = "Clique aqui", tipo: str = "button") -> str:
    """Um elemento `<button>` simples."""
    return f'<button type="{tipo}">{_seguro(texto)}</button>'


def modal(titulo: str = "Título do modal", texto: str = "Conteúdo do modal.") -> str:
    """Janela modal com fundo escurecido (`<dialog>`, nativo do HTML).

    `<dialog>` dispensa JavaScript para abrir/fechar de forma acessível — o
    próprio navegador cuida do foco e do Escape para fechar. O `<script>`
    incluído é o mínimo para abrir a partir de um clique.
    """
    return f"""<dialog id="modal">
  <h2>{_seguro(titulo)}</h2>
  <p>{_seguro(texto)}</p>
  <button onclick="document.getElementById('modal').close()">Fechar</button>
</dialog>

<button onclick="document.getElementById('modal').showModal()">Abrir modal</button>"""


def tabs(abas: list[str] | None = None) -> str:
    """Abas (tabs) simples: um botão por aba e um painel de conteúdo cada.

    A troca de aba é feita com um `data-tab` e um pouquinho de JavaScript —
    a técnica mais comum antes de qualquer framework entrar em cena.
    """
    abas = abas or ["Aba 1", "Aba 2", "Aba 3"]
    botoes = "\n".join(
        f'    <button class="tab-botao" data-tab="{_slug(a)}">{_seguro(a)}</button>'
        for a in abas
    )
    paineis = "\n".join(
        f'  <div class="tab-painel" id="{_slug(a)}">Conteúdo de {_seguro(a)}.</div>'
        for a in abas
    )
    return f"""<div class="tabs">
{botoes}
</div>

{paineis}

<script>
  document.querySelectorAll(".tab-botao").forEach(botao => {{
    botao.addEventListener("click", () => {{
      document.querySelectorAll(".tab-painel").forEach(p => p.hidden = true);
      document.getElementById(botao.dataset.tab).hidden = false;
    }});
  }});
</script>"""


def accordion(itens: list[str] | None = None) -> str:
    """Sanfona (accordion): cada item expande/recolhe seu conteúdo.

    Usa `<details>`/`<summary>`, nativos do HTML — expande e recolhe sem
    nenhum JavaScript, e funciona com leitor de tela sem esforço extra.
    """
    itens = itens or ["Pergunta 1", "Pergunta 2", "Pergunta 3"]
    blocos = "\n".join(
        f"<details>\n  <summary>{_seguro(item)}</summary>\n"
        f"  <p>Resposta de {_seguro(item)}.</p>\n</details>"
        for item in itens
    )
    return blocos


def breadcrumb(caminho: list[str] | None = None) -> str:
    """Trilha de navegação (breadcrumb): onde a página está, dentro do site."""
    caminho = caminho or ["Início", "Categoria", "Página atual"]
    partes = []
    for posicao, item in enumerate(caminho):
        if posicao == len(caminho) - 1:
            partes.append(f'    <li aria-current="page">{_seguro(item)}</li>')
        else:
            partes.append(f'    <li><a href="#{_slug(item)}">{_seguro(item)}</a></li>')
    itens = "\n".join(partes)
    return f"""<nav aria-label="breadcrumb">
  <ol>
{itens}
  </ol>
</nav>"""


def dropdown(rotulo: str = "Menu", opcoes: list[str] | None = None) -> str:
    """Menu suspenso (`<select>` nativo — a forma mais simples e acessível)."""
    opcoes = opcoes or ["Opção 1", "Opção 2", "Opção 3"]
    id_campo = _slug(rotulo)
    itens = "\n".join(
        f'    <option value="{_slug(o)}">{_seguro(o)}</option>' for o in opcoes
    )
    return f"""<label for="{id_campo}">{_seguro(rotulo)}</label>
<select id="{id_campo}" name="{id_campo}">
{itens}
</select>"""
