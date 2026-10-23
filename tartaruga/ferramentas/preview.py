"""
Preview ao vivo de HTML/CSS/JS gerado — dependência OPCIONAL.

Desenho da proteção:
QWebEngineProfile efêmero, QWebEngineUrlRequestInterceptor bloqueando rede
por padrão, CSP como reforço, gatilho estruturado vindo da própria resposta,
cinco categorias de montador de documento, painel único de abas
compartilhado com o de Execuções, import tardio do WebEngine, matriz de
distribuições testada antes de fechar.

Etapa 1 (`disponivel()`): só a checagem de disponibilidade, sem nenhuma peça
de interface. Etapa 3 (`criar_view()`/`renderizar()`): a view de verdade,
com o import do WebEngine sempre tardio - só quando chamado, nunca no
carregamento normal deste módulo.
"""
import importlib.util

from .preview_seguranca import url_permitida


def disponivel() -> bool:
    """Verifica se PyQt6-WebEngine está instalado, sem importar o módulo.

    `find_spec` localiza o pacote no sistema de arquivos sem executar o
    código dele - ao contrário de um `import` de verdade, não paga o custo
    de inicializar o Chromium embutido nem arrisca uma falha de
    carregamento de DLL numa máquina sem a dependência opcional instalada.

    Isso espelha o mesmo cuidado já usado em `ferramentas/llm.py::disponivel()`
    (uma checagem barata, chamada antes de qualquer uso pesado) e em
    `semantica.py` (que confere `sentence_transformers` do mesmo jeito,
    sem importar antes de saber que os pesos existem).

    Checar "PyQt6.QtWebEngineWidgets" como submódulo é seguro aqui porque
    PyQt6 em si já é dependência OBRIGATÓRIA do projeto (é a interface
    gráfica inteira) - `find_spec` de um submódulo importa o pacote pai
    pra localizar o `__path__` dele, mas isso não tem custo extra: PyQt6
    já estaria carregado de qualquer forma.
    """
    return importlib.util.find_spec("PyQt6.QtWebEngineWidgets") is not None


def criar_view():
    """Cria um QWebEngineView pronto para exibir documentos do preview, já
    configurado com perfil efêmero e bloqueio de rede/navegação/popup.

    Só chame depois de confirmar `disponivel()`. O import do WebEngine
    acontece aqui dentro, e só aqui - nunca no topo do módulo - para que
    quem nunca abre o preview não pague o custo de carregar o Chromium
    embutido, mesmo com a dependência instalada.

    IMPORTANTE (achado ao testar de verdade, não só documentação): o Qt
    exige que `QCoreApplication.setAttribute(Qt.ApplicationAttribute.
    AA_ShareOpenGLContexts)` seja chamado ANTES da QApplication existir,
    senão até este import tardio falha com `ImportError` mesmo com o
    pacote instalado. Isso é responsabilidade de quem sobe a aplicação
    (`interface.py::main()`), não deste módulo - aqui só documentamos a
    dependência.

    Cada ponta de bloqueio foi confirmada rodando de verdade
    (QT_QPA_PLATFORM=offscreen), não só lida na documentação do Qt. O que foi
    testado manualmente antes deste código existir:
      - perfil sem nome é efêmero (isOffTheRecord() == True);
      - o interceptor bloqueia sub-recursos (imagem, fetch/xhr) fora do
        esquema permitido, mas deixa passar a navegação inicial via
        `data:` que o próprio `setHtml()` usa internamente;
      - `acceptNavigationRequest` bloqueia clique em link para fora do
        documento;
      - `createWindow` retornando None nega popup/`window.open()` sem
        travar nada.
    """
    from PyQt6.QtWebEngineCore import (
        QWebEngineProfile,
        QWebEnginePage,
        QWebEngineUrlRequestInterceptor,
    )
    from PyQt6.QtWebEngineWidgets import QWebEngineView

    class _Interceptador(QWebEngineUrlRequestInterceptor):
        def interceptRequest(self, info) -> None:  # noqa: N802 (nome da API do Qt)
            if not url_permitida(info.requestUrl().toString()):
                info.block(True)

    class _PaginaRestrita(QWebEnginePage):
        def acceptNavigationRequest(self, url, tipo, is_main_frame) -> bool:  # noqa: N802
            return url_permitida(url.toString())

        def createWindow(self, tipo):  # noqa: N802
            # Nenhum cenário de preview precisa de aba/janela nova - negar
            # incondicionalmente também bloqueia `window.open()` do JS.
            return None

        # Diálogos de JavaScript são MODAIS: o padrão do Qt abre uma caixa
        # que trava a aplicação inteira até alguém fechá-la (confirmado ao
        # testar `alert()` de verdade - o programa parou de responder).
        # Código gerado/colado pode chamá-los sem querer (ou de propósito),
        # então são todos silenciados: alert vira no-op, confirm/prompt
        # devolvem "cancelado".
        def javaScriptAlert(self, origem, mensagem) -> None:  # noqa: N802
            return None

        def javaScriptConfirm(self, origem, mensagem) -> bool:  # noqa: N802
            return False

        def javaScriptPrompt(self, origem, mensagem, padrao):  # noqa: N802
            return False, ""

        def chooseFiles(self, modo, arquivos_antigos, tipos_aceitos):  # noqa: N802
            return []  # nunca abre seletor de arquivos do sistema

        def javaScriptConsoleMessage(self, nivel, mensagem, linha, origem) -> None:  # noqa: N802
            return None

    perfil = QWebEngineProfile()  # sem nome = efêmero, sem cache/cookies em disco
    perfil.setPersistentCookiesPolicy(QWebEngineProfile.PersistentCookiesPolicy.NoPersistentCookies)
    perfil.setHttpCacheType(QWebEngineProfile.HttpCacheType.NoCache)

    interceptador = _Interceptador(perfil)
    perfil.setUrlRequestInterceptor(interceptador)
    perfil.downloadRequested.connect(lambda item: item.cancel())

    pagina = _PaginaRestrita(perfil, None)
    pagina.featurePermissionRequested.connect(
        lambda origem, funcionalidade: pagina.setFeaturePermission(
            origem, funcionalidade, QWebEnginePage.PermissionPolicy.PermissionDeniedByUser
        )
    )

    view = QWebEngineView()
    view.setPage(pagina)
    # Perfil/interceptador/página são referenciados só pelo C++ do Qt por
    # padrão - guardar aqui evita que o coletor de lixo do Python os
    # destrua enquanto a view ainda está viva (PyQt não segura essa
    # referência sozinho).
    view._preview_perfil = perfil
    view._preview_pagina = pagina
    view._preview_interceptador = interceptador
    return view


def renderizar(view, documento: str) -> None:
    """Carrega um documento HTML já montado (ver `preview_documento.py`) na
    view criada por `criar_view()`.

    `setHtml()` sem `baseUrl` é o que faz o Qt tratar o conteúdo como uma
    navegação `data:` isolada, sem acesso a nenhum caminho de arquivo local
    - é essa a razão de nunca usar `load(QUrl.fromLocalFile(...))` aqui.
    """
    view.setHtml(documento)


def responde(view, espera_ms: int = 800) -> bool:
    """Sonda se o renderizador da view ainda responde (ex.: não está preso
    num `while(true){}` do código de demonstração).

    O Chromium roda o JavaScript num processo separado, então a interface
    Qt NUNCA trava por causa dele - mas uma página presa em loop infinito
    para de responder e não se recupera carregando outro documento
    (confirmado ao testar de verdade). Roda um `runJavaScript("1")` e
    espera a resposta por até `espera_ms`, processando eventos do Qt.
    """
    from PyQt6.QtCore import QEventLoop, QTimer

    loop = QEventLoop()
    resposta = {}

    def _callback(valor):
        # Só conta como "responde" se voltou o valor esperado - um callback
        # disparado pela destruição da página (a documentação do Qt avisa
        # que isso pode acontecer) não prova que o renderizador está vivo.
        resposta["ok"] = valor == 1
        loop.quit()

    view.page().runJavaScript("1", _callback)
    QTimer.singleShot(espera_ms, loop.quit)
    loop.exec()
    return resposta.get("ok", False)


def descartar(view) -> None:
    """Destrói a view, a página e o perfil (e com eles o renderizador preso)."""
    pagina = getattr(view, "_preview_pagina", None)
    perfil = getattr(view, "_preview_perfil", None)
    view.setPage(None)
    view.deleteLater()
    if pagina is not None:
        pagina.deleteLater()
    if perfil is not None:
        perfil.deleteLater()
