"""Regras de segurança do preview ao vivo, isoladas em funções PURAS - sem
importar nada de `PyQt6.QtWebEngine` - pra serem testáveis mesmo numa
máquina sem a dependência opcional instalada.

Resumo do porquê disso existir:
`QWebEngineView` é um navegador completo por padrão - sozinho ele NÃO
bloqueia rede nem acesso a arquivo. A proteção real, montada em
`tartaruga/ferramentas/preview.py::criar_view()`, usa `url_permitida` daqui
em três pontas:

  1. `QWebEngineUrlRequestInterceptor` bloqueia todo sub-recurso (imagem,
     fetch, xhr, script externo) cuja URL não seja um esquema permitido.
  2. `QWebEnginePage.acceptNavigationRequest` bloqueia navegação de topo
     (clique em link, redirecionamento) pelo mesmo critério.
  3. `QWebEnginePage.createWindow` nega popups/`window.open()`
     incondicionalmente - nenhum cenário de preview precisa de janela nova.

Confirmado empiricamente (rodando de verdade, não só lendo documentação)
que o próprio `setHtml()` do Qt carrega o documento como uma navegação
`data:` internamente - por isso `data:` precisa estar na lista de
permitidos, senão o preview nem carrega o conteúdo legítimo (bloquear tudo
incondicionalmente quebra o load do próprio documento, foi testado). `about:`
(ex. about:blank, usado em páginas internas do Chromium) e `blob:` (usado
internamente por alguns recursos do próprio motor) são igualmente inertes
quanto a rede/arquivo real e entram na lista pela mesma razão.
"""

ESQUEMAS_PERMITIDOS = ("data", "about", "blob")


def url_permitida(url: str) -> bool:
    """Decide se uma URL pode ser carregada/requisitada dentro do preview.

    O documento do preview é sempre montado inteiro (HTML+CSS+JS já embutido
    inline, ver `preview_documento.py`) e carregado via `setHtml()` - não
    precisa buscar nada fora dele pra funcionar. A política é restritiva por
    padrão: só os esquemas que não tocam rede real nem arquivo local passam.
    Qualquer `http(s)`, `file`, `ftp` etc. é bloqueado - é exatamente o
    conteúdo renderizado tentando alcançar algo fora do documento que ele já
    tem, e é isso que precisa ser impedido.
    """
    if not url or ":" not in url:
        return False
    esquema = url.split(":", 1)[0].strip().lower()
    return esquema in ESQUEMAS_PERMITIDOS
