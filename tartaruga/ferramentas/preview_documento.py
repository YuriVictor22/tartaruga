"""
Montador de documento do preview ao vivo.

Este módulo resolve uma peça específica: o gerador de
templates (`geracao.py`) produz FRAGMENTOS — só o `<form>`, só a regra CSS,
só a função JavaScript — não um documento completo. Pra renderizar de
verdade num navegador embutido, é preciso um documento HTML inteiro ao
redor do fragmento.

Cinco categorias, como definido na revisão técnica do plano:

  1. Documento HTML completo   - já tem <!DOCTYPE>/<html> (ex.: o padrão
                                  "pagina"); passa quase direto.
  2. Fragmento HTML            - a maioria dos padrões de HTML; embrulha
                                  num esqueleto mínimo.
  3. CSS isolado               - a regra sozinha não mostra nada; precisa
                                  de um elemento de exemplo que ela decore.
  4. JavaScript isolado        - uma função/classe sozinha não faz nada
                                  visível; precisa de um gatilho (botão,
                                  campo de texto) que a invoque e mostre o
                                  resultado.
  5. Combinação HTML/CSS/JS    - nenhum padrão atual de geracao.py produz
                                  isso ainda (cada resultado tem uma única
                                  linguagem) - implementado por
                                  completude, pra quando existir um
                                  chamador que combine as três.

Um "botão genérico único" não serve pra CSS/JS: debounce precisa de um
campo de texto, uma classe precisa de outra chamada, um emissor de eventos
precisa de dois lados (quem emite, quem escuta). Por isso cada PADRÃO
(o nome que `geracao.py` já atribui: "botao", "debounce", "singleton"...)
tem seu próprio cenário nas tabelas abaixo. Código vindo do reforço do LLM
não tem padrão - cai no cenário genérico de cada linguagem.
"""

LINGUAGENS_SUPORTADAS = ("html", "css", "javascript")


def montar_documento(codigo: str, linguagem: str, padrao: str = "") -> str:
    """Monta um documento HTML completo, pronto pra renderizar.

    `padrao` é o nome do template (`ResultadoGeracao.padrao`, ver
    geracao.py) quando o código veio de um dos templates - usado só pra
    escolher um cenário de demonstração melhor pra CSS/JS. Vazio (código
    do reforço do LLM, sem padrão fixo) cai no cenário genérico.
    """
    linguagem = linguagem.strip().lower()
    if linguagem == "html":
        return codigo if _e_documento_completo(codigo) else _envolver_html(codigo)
    if linguagem == "css":
        return _montar_css(codigo, padrao)
    if linguagem == "javascript":
        return _montar_javascript(codigo, padrao)
    raise ValueError(
        f"Preview não suporta a linguagem {linguagem!r} - só {', '.join(LINGUAGENS_SUPORTADAS)}."
    )


def montar_documento_combinado(html: str = "", css: str = "", js: str = "") -> str:
    """Categoria 5: combina HTML, CSS e JS num documento só.

    Nenhum padrão atual de geracao.py produz um resultado combinando as
    três linguagens de uma vez (cada ResultadoGeracao tem uma linguagem
    só) - esta função existe por completude do plano de 5 categorias, sem
    um chamador real ainda. Partes vazias são omitidas.
    """
    corpo = html or "<p>(sem HTML nesta combinação)</p>"
    estilo = f"<style>\n{css}\n</style>" if css else ""
    script = f"<script>\n{js}\n</script>" if js else ""
    return f"""<!DOCTYPE html>
<html lang="pt-BR">
<head>
<meta charset="UTF-8">
<title>Preview</title>
{estilo}
</head>
<body>
{corpo}
{script}
</body>
</html>"""


def _e_documento_completo(codigo: str) -> bool:
    amostra = codigo[:300].lower()
    return "<!doctype" in amostra or "<html" in amostra


def _envolver_html(fragmento: str) -> str:
    return f"""<!DOCTYPE html>
<html lang="pt-BR">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>Preview</title>
</head>
<body>
{fragmento}
</body>
</html>"""


def _montar_css(codigo: str, padrao: str) -> str:
    demo = _DEMOS_CSS.get(padrao, _DEMO_CSS_GENERICO)
    return f"""<!DOCTYPE html>
<html lang="pt-BR">
<head>
<meta charset="UTF-8">
<title>Preview</title>
<style>
{codigo}
</style>
</head>
<body>
{demo}
</body>
</html>"""


def _montar_javascript(codigo: str, padrao: str) -> str:
    demo_html, demo_script = _DEMOS_JS.get(padrao, (_DEMO_JS_GENERICO_HTML, ""))
    return f"""<!DOCTYPE html>
<html lang="pt-BR">
<head>
<meta charset="UTF-8">
<title>Preview</title>
</head>
<body>
{demo_html}
<script>
{codigo}

{demo_script}
</script>
</body>
</html>"""


# ---------------------------------------------------------------------------
# Cenários de demonstração por padrão de CSS (ver tartaruga/geradores/css.py
# e PADROES_CSS em geracao.py pros nomes e seletores que cada um usa).
# ---------------------------------------------------------------------------
_DEMO_CSS_GENERICO = """<div class="preview-generico" style="padding: 16px; border: 1px dashed #999;">
  Elemento de exemplo genérico - se o CSS usar uma classe específica,
  este cenário pode não mostrar o efeito. Padrões conhecidos (botão,
  flexbox, grid...) têm demonstração própria.
</div>"""

_DEMOS_CSS: dict[str, str] = {
    "flexbox": """<div class="container">
  <div style="padding:12px;background:#ddd;">1</div>
  <div style="padding:12px;background:#ccc;">2</div>
  <div style="padding:12px;background:#bbb;">3</div>
</div>""",
    "grid": """<div class="grade">
  <div style="padding:12px;background:#ddd;">1</div>
  <div style="padding:12px;background:#ccc;">2</div>
  <div style="padding:12px;background:#bbb;">3</div>
</div>""",
    "botao": '<button class="botao">Clique aqui</button>',
    "centralizar": '<div class="centralizado"><p>Conteúdo centralizado</p></div>',
    "variaveis": """<div style="background: var(--cor-fundo); color: var(--cor-texto); border: 1px solid var(--cor-borda); padding: 20px;">
  Usando as variáveis definidas no bloco :root
</div>""",
    "responsivo": """<div class="container">
  <div style="padding:12px;background:#ddd;">1</div>
  <div style="padding:12px;background:#ccc;">2</div>
</div>
<p>Redimensione a janela pra ver a regra responsiva agir.</p>""",
    "sombra": '<div class="elevado" style="padding:20px;background:#fff;display:inline-block;">Elemento com sombra</div>',
    "transicao": '<div class="suave" style="padding:20px;background:#4ade80;display:inline-block;">Passe o mouse aqui</div>',
    "animacao": '<div class="animado" style="padding:20px;background:#60a5fa;display:inline-block;color:#fff;">Elemento animado</div>',
}

# ---------------------------------------------------------------------------
# Cenários de demonstração por padrão de JavaScript (ver
# tartaruga/geradores/javascript.py pros nomes de função/classe exatos -
# o cenário só funciona se esses nomes não forem alterados no gerador).
# Cada valor é (html_do_gatilho, script_que_invoca_e_mostra_resultado).
# ---------------------------------------------------------------------------
_DEMO_JS_GENERICO_HTML = """<p>Código carregado. Este padrão não tem um cenário de demonstração
específico - abra o console do navegador (se disponível) pra interagir
manualmente, ou peça um dos 13 padrões de JavaScript avançado conhecidos.</p>"""

_GATILHO_BOTAO = '<button id="gatilho">Executar</button>\n<div id="saida">Clique pra testar</div>'
_GATILHO_INPUT = '<input id="gatilho" placeholder="Digite algo">\n<div id="saida">Aguardando...</div>'

_DEMOS_JS: dict[str, tuple[str, str]] = {
    "debounce": (
        _GATILHO_INPUT,
        """const saida = document.getElementById('saida');
const aoDigitar = debounce(() => {
  saida.textContent = 'Debounce disparou às ' + new Date().toLocaleTimeString();
}, 500);
document.getElementById('gatilho').addEventListener('input', aoDigitar);""",
    ),
    "throttle": (
        _GATILHO_BOTAO.replace("Executar", "Clique repetidamente, rápido"),
        """const saida = document.getElementById('saida');
let contador = 0;
const aoClicar = throttle(() => {
  contador++;
  saida.textContent = 'Throttle disparou ' + contador + ' vez(es)';
}, 1000);
document.getElementById('gatilho').addEventListener('click', aoClicar);""",
    ),
    "memoize": (
        _GATILHO_BOTAO.replace("Executar", "Calcular fibonacci(20)"),
        """const saida = document.getElementById('saida');
function fibLento(n) { return n <= 1 ? n : fibLento(n - 1) + fibLento(n - 2); }
const fibRapido = memoize(fibLento);
document.getElementById('gatilho').addEventListener('click', () => {
  const inicio = performance.now();
  const resultado = fibRapido(20);
  const duracao = (performance.now() - inicio).toFixed(2);
  saida.textContent = 'fib(20) = ' + resultado + ' em ' + duracao + 'ms (clique de novo: fica instantâneo)';
});""",
    ),
    "curry": (
        _GATILHO_BOTAO,
        """const saida = document.getElementById('saida');
const somarTres = curry((a, b, c) => a + b + c);
document.getElementById('gatilho').addEventListener('click', () => {
  saida.textContent = 'somarTres(1)(2)(3) = ' + somarTres(1)(2)(3);
});""",
    ),
    "clone": (
        _GATILHO_BOTAO,
        """const saida = document.getElementById('saida');
document.getElementById('gatilho').addEventListener('click', () => {
  const original = { nome: 'a', tags: ['x', 'y'] };
  const copia = clonarProfundo(original);
  copia.tags.push('z');
  saida.textContent = 'original: ' + JSON.stringify(original.tags) + ' | cópia: ' + JSON.stringify(copia.tags);
});""",
    ),
    "emissor": (
        _GATILHO_BOTAO.replace("Executar", "Emitir evento"),
        """const saida = document.getElementById('saida');
const bus = new EmissorEventos();
bus.on('evento:teste', (dado) => { saida.textContent = 'Ouvinte recebeu: ' + dado; });
document.getElementById('gatilho').addEventListener('click', () => {
  bus.emit('evento:teste', 'disparado às ' + new Date().toLocaleTimeString());
});""",
    ),
    "retry": (
        _GATILHO_BOTAO.replace("Executar", "Tentar operação instável"),
        """const saida = document.getElementById('saida');
document.getElementById('gatilho').addEventListener('click', async () => {
  saida.textContent = 'Tentando...';
  let tentativas = 0;
  try {
    const resultado = await tentarNovamente(() => {
      tentativas++;
      if (tentativas < 3) throw new Error('falhou na tentativa ' + tentativas);
      return 'sucesso na tentativa ' + tentativas;
    }, 5, 200);
    saida.textContent = resultado;
  } catch (erro) {
    saida.textContent = 'Desistiu: ' + erro.message;
  }
});""",
    ),
    "timeout": (
        _GATILHO_BOTAO.replace("Executar", "Rodar operação lenta com limite de 1s"),
        """const saida = document.getElementById('saida');
document.getElementById('gatilho').addEventListener('click', async () => {
  saida.textContent = 'Aguardando...';
  const operacaoLenta = new Promise((resolve) => setTimeout(() => resolve('terminou'), 3000));
  try {
    saida.textContent = await comLimiteDeTempo(operacaoLenta, 1000);
  } catch (erro) {
    saida.textContent = 'Como esperado: ' + erro.message;
  }
});""",
    ),
    "fetch": (
        _GATILHO_BOTAO.replace("Executar", "Buscar dados"),
        """const saida = document.getElementById('saida');
document.getElementById('gatilho').addEventListener('click', async () => {
  saida.textContent = 'Buscando...';
  try {
    const dado = await buscarDados('https://exemplo.invalido/api');
    saida.textContent = JSON.stringify(dado);
  } catch (erro) {
    saida.textContent = 'Falha na busca (esperado neste preview, sem acesso à rede): ' + erro.message;
  }
});""",
    ),
    "classe": (
        _GATILHO_BOTAO.replace("Executar", "Fazer o pássaro voar"),
        """const saida = document.getElementById('saida');
document.getElementById('gatilho').addEventListener('click', () => {
  const ave = new Passaro('Coruja');
  saida.textContent = ave.voar();
});""",
    ),
    "gerador": (
        _GATILHO_BOTAO.replace("Executar", "Gerar intervalo"),
        """const saida = document.getElementById('saida');
document.getElementById('gatilho').addEventListener('click', () => {
  const numeros = [...gerarIntervalo(1, 10, 2)];
  saida.textContent = numeros.join(', ');
});""",
    ),
    "singleton": (
        _GATILHO_BOTAO.replace("Executar", "Obter instância duas vezes"),
        """const saida = document.getElementById('saida');
document.getElementById('gatilho').addEventListener('click', () => {
  const c1 = ConfiguracaoApp.obter();
  const c2 = ConfiguracaoApp.obter();
  saida.textContent = 'Mesma instância? ' + (c1 === c2) + ' | tema: ' + c1.tema;
});""",
    ),
    "proxy": (
        _GATILHO_BOTAO.replace("Executar", "Tentar definir idade inválida"),
        """const saida = document.getElementById('saida');
const usuario = criarObjetoValidado({ idade: 0 }, {
  idade: (v) => typeof v === 'number' && v >= 0,
});
document.getElementById('gatilho').addEventListener('click', () => {
  try {
    usuario.idade = -1;
    saida.textContent = 'idade definida: ' + usuario.idade;
  } catch (erro) {
    saida.textContent = 'Bloqueado como esperado: ' + erro.message;
  }
});""",
    ),
}
