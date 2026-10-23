"""
Busca na web via DuckDuckGo.

Usada quando a base de conhecimento local não tem a resposta. É a única parte
de busca depende de internet e da biblioteca externa `ddgs`. O aprendizado
também baixa páginas; a interface gráfica depende separadamente de PyQt6.

Regra de projeto: falhar aqui NUNCA pode derrubar a Tartaruga. Sem internet,
sem a biblioteca instalada ou com o serviço fora do ar, a função devolve uma
lista vazia e um recado - e o assistente segue funcionando offline. Por isso
o import acontece dentro da função, e não no topo do arquivo.
"""

import threading
import time
from dataclasses import dataclass

QUANTIDADE_PADRAO = 3

# ---------------------------------------------------------------------------
# Intervalo mínimo entre buscas
#
# O DuckDuckGo é gratuito e sem chave de API, o que significa que o limite
# de uso é implícito: buscas seguidas demais são recusadas. Ao mandar a
# Tartaruga estudar 12 assuntos em sequência, as três últimas falharam por
# isso - e não por falta de internet, como a mensagem sugeria.
#
# Esperar entre as chamadas é cortesia com um serviço que não cobra nada, e
# também a diferença entre aprender 9 de 12 assuntos e aprender os 12.
# ---------------------------------------------------------------------------
INTERVALO_MINIMO = 2.5

_ultima_busca = 0.0
_trava = threading.Lock()


def _aguardar_vez() -> None:
    """Garante o intervalo mínimo desde a busca anterior.

    A trava existe porque a interface gráfica faz buscas numa thread
    separada: sem ela, duas buscas simultâneas passariam pela verificação
    ao mesmo tempo e o espaçamento não aconteceria.
    """
    global _ultima_busca
    with _trava:
        espera = INTERVALO_MINIMO - (time.monotonic() - _ultima_busca)
        if espera > 0:
            time.sleep(espera)
        _ultima_busca = time.monotonic()


@dataclass
class ResultadoWeb:
    """Um resultado de busca."""

    titulo: str
    trecho: str
    link: str


@dataclass
class RespostaBusca:
    """O que a busca devolveu, incluindo o motivo de uma eventual falha."""

    resultados: list[ResultadoWeb]
    erro: str | None = None

    @property
    def ok(self) -> bool:
        return self.erro is None and bool(self.resultados)


def buscar(consulta: str, quantidade: int = QUANTIDADE_PADRAO) -> RespostaBusca:
    """Busca no DuckDuckGo e devolve os primeiros resultados.

    Não exige chave de API nem cadastro, o que mantém o projeto gratuito e
    reproduzível por qualquer pessoa que baixe o repositório.
    """
    consulta = consulta.strip()
    if not consulta:
        return RespostaBusca(resultados=[], erro="A busca está vazia.")

    # O import e a chamada ficam no MESMO try porque o `ddgs` carrega o
    # módulo real só quando é usado. Um módulo faltando aparece no primeiro
    # `DDGS()`, e não na linha do import - foi assim que um executável sem a
    # biblioteca passou despercebido.
    try:
        from ddgs import DDGS

        _aguardar_vez()
        with DDGS() as cliente:
            brutos = list(cliente.text(consulta, max_results=quantidade))

    except ImportError as erro:
        # Biblioteca ausente ou incompleta. Distinguir isso de falha de rede
        # importa: a primeira versão desta mensagem mandava o usuário
        # verificar a conexão quando o problema era um módulo faltando no
        # executável - fazendo procurar no lugar errado.
        return RespostaBusca(
            resultados=[],
            erro=(
                f"A biblioteca de busca não está disponível ({erro.name or 'módulo desconhecido'}). "
                "Isto é um problema da instalação, não da sua internet. "
                "Rodando pelo código-fonte: pip install -r requirements.txt"
            ),
        )

    except Exception as erro:
        # Captura ampla de propósito: falha de rede, timeout, recusa do
        # serviço. Qualquer uma deve degradar com elegância, não derrubar a
        # aplicação.
        texto_erro = f"{type(erro).__name__}: {erro}".lower()

        # Distinguir recusa por excesso de uso de falha de conexão: são
        # problemas diferentes e o usuário deve fazer coisas diferentes.
        if any(p in texto_erro for p in ("ratelimit", "rate limit", "429", "too many")):
            mensagem = (
                "O buscador recusou a consulta por excesso de pedidos seguidos. "
                "Espere alguns segundos e tente de novo — não é problema na sua internet."
            )
        else:
            mensagem = (
                f"Não consegui buscar na web ({type(erro).__name__}). "
                "Você está conectado à internet?"
            )

        return RespostaBusca(resultados=[], erro=mensagem)

    resultados = [
        ResultadoWeb(
            titulo=item.get("title", "(sem título)"),
            trecho=item.get("body", ""),
            link=item.get("href", ""),
        )
        for item in brutos
    ]

    if not resultados:
        return RespostaBusca(resultados=[], erro="A busca não retornou resultados.")

    return RespostaBusca(resultados=resultados)
