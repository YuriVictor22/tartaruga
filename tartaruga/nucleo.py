"""
Núcleo da Tartaruga: o cérebro que decide o que fazer.

O fluxo de cada mensagem:

    texto do usuário
        -> vetorizar (TF-IDF)
        -> classificar a intenção (Naive Bayes)
        -> classificar a CONFIANÇA em alta / média / baixa
        -> consultar o estado da conversa (dialogo.py)
        -> despachar para a ferramenta certa
        -> escolher uma variante de resposta
        -> registrar tudo na memória

Este módulo NÃO imprime nada e NÃO lê do teclado. Recebe texto e devolve um
objeto `Resposta`. Quem cuida da tela é `main.py` ou `interface.py`.

Essa separação é o que permitiu acrescentar a interface gráfica sem tocar
numa linha da lógica, e é o que torna o assistente testável sem simular
alguém digitando.
"""

import json
import re
from dataclasses import dataclass

from .aprendizado import Aprendiz
from .caminhos import recurso
from .classificador import ClassificadorNaiveBayes
from .conhecimento import BaseConhecimento
from .dialogo import GestorDialogo
from .ferramentas import arquivos, executar, llm, web
from .geracao import Gerador, total_padroes
from .interpretacao import interpretar
from .conversa import resolver
from .briefing import Briefing
from .projetos import RepositorioProjetos
from .contexto_conversa import (
    escolher_pelo_contexto, resolver_com_contexto, resolver_referencia_contextual, topico_recente,
)
from .semantica import (
    CompreensaoSemantica, _aplicar as _aplicar_chave, chave_consulta, montar_pergunta_de_esclarecimento, opcoes_distintas,
    resolver_escolha_lembrada, resolver_semantica,
)
from .comandos_naturais import (
    consulta_de_pesquisa, conversa_livre, intencao_direta, resolver_catalogo, resolver_comparacao, resolver_continuacao, resolver_social,
    resolver_ajuste_do_topico, resolver_cancelar_sem_fluxo, resolver_exemplo_do_topico, resolver_planejar_briefing,
    resolver_refino, resolver_troca_de_linguagem,
    social_canonico,
)
from .memoria import Memoria
from .ortografia import corrigir as corrigir_digitacao
from .sinonimos import TERMOS_AMBIGUOS

# Substantivos do dia a dia que TAMBÉM nomeiam uma entrada inteira da base ("lista de compras" x entrada
# "Listas"; "tabela de preços" x "CSS: box model"? não — x nenhuma, mas "lista"/"tabela"/"arquivo" batem sozinhos
# de qualquer forma). Fica FORA de TERMOS_AMBIGUOS de propósito: aquele conjunto é usado em outros lugares para
# decidir COMBINAÇÃO de sinais fracos (duas palavras destas juntas, como "item"+"lista", já bastavam para
# corroborar uma oferta, o que não é a intenção aqui — ver o achado da mutação/medição desta correção).
SUBSTANTIVOS_AMBIGUOS_ISOLADOS = TERMOS_AMBIGUOS | frozenset({"lista", "tabela", "pagina", "arquivo", "campo", "item", "pasta"})
from .vetorizador import STOPWORDS_BUSCA, tokenizar

CAMINHO_INTENCOES = recurso("dados", "intencoes.json")

# Detecta um nome de arquivo dentro da frase: "leia o teste.py"
PADRAO_ARQUIVO = re.compile(r"\b([\w\-]+\.[a-zA-Z]{1,5})\b")

# Palavras que só indicam o comando de busca e não fazem parte do assunto.
RUIDO_BUSCA = {
    "pesquisa", "pesquise", "pesquisar", "pesquisada", "busca", "buscar",
    "busque", "procura", "procurar", "procure", "internet", "web", "google",
    "online", "navegador", "consulta", "consultar", "quero", "voce", "você",
    "faz", "faça", "uma", "sobre", "isso", "favor", "informacoes",
    "informações", "da", "dá", "me", "no", "na", "também", "tambem",
}

# Intenções em que uma confiança apenas mediana merece uma ressalva. São as
# que EXECUTAM algo; num cumprimento ou num agradecimento, perguntar "é isso
# mesmo?" soaria pedante e pioraria a conversa.
INTENCOES_DE_ACAO = {"executar_codigo", "manipular_arquivo", "buscar_web", "gerar_codigo"}

# Histórico do limiar (ver classificador.py::cobertura_ponderada e o README
# para a métrica em si, que mudou mais de uma vez):
#
#   0.5  -> original, mesmo limiar de `conhecimento.py::COBERTURA_MINIMA`.
#   0.67 -> "quem foi Pelé"/"Tiradentes" e "me manda uma frase motivacional"
#           reconheciam 2 de 3 palavras (67%) contando toda palavra igual -
#           "quem"/"foi"/"manda"/"frase" tanto faz pra essa conta, e a
#           palavra que de fato importava ("motivacional") era a única fora.
#   0.7  -> a contagem bruta (uma palavra = uma palavra) não durava: "o que
#           é um race condition" e "quem foi Pelé" reconheciam a MESMA
#           fração (2 de 3), então nenhum limiar fixo separava os dois -
#           subir o número só trocava qual dos dois passava a falhar. A
#           correção foi na MÉTRICA, não no número: cada palavra passou a
#           valer conforme o quanto ela é exclusiva de um assunto (peso
#           baseado em quantas classes de treino a contêm), com palavras
#           interrogativas ("quem", "como", "que"...) zeradas de propósito -
#           são o motivo de "quem" ter concentração alta sem ser sobre
#           nenhum assunto específico. Medido contra os 37 casos catalogados
#           no README, foi de 31/37 pra 35/37 acertos nesse limiar.
COBERTURA_MINIMA_INTENCAO = 0.7


def _linguagem_do_topico(identificador: str, codigo: str) -> str:
    """Descobre a linguagem do exemplo, para rotular o bloco corretamente.

    Todos os blocos de código eram marcados como `python`, inclusive os de
    JavaScript, HTML e CSS. Rótulo errado não é detalhe estético: quem está
    aprendendo pode concluir que aquela sintaxe é de Python.

    Para o conteúdo curado, o prefixo do identificador já diz a linguagem -
    não é preciso anotar nada à mão nas entradas. Para o que foi aprendido na
    web, o identificador não diz nada, então o código é inspecionado.
    """
    for prefixo, linguagem in (("js-", "javascript"), ("html-", "html"), ("css-", "css")):
        if identificador.startswith(prefixo):
            return linguagem

    if not identificador.startswith("aprendido-"):
        return "python"

    # Conteúdo aprendido: decidir pelo próprio código.
    amostra = codigo[:600]
    if re.search(r"<(!DOCTYPE|html|div|p|a|span|body|head|section)\b", amostra, re.IGNORECASE):
        return "html"
    if re.search(r"\b(function|const|let|var|=>|console\.log|document\.)", amostra):
        return "javascript"
    if re.search(r"^\s*[.#@a-z-]+\s*\{[^}]*:", amostra, re.MULTILINE):
        return "css"
    if re.search(r"\b(def |import |print\(|elif |self\.)", amostra):
        return "python"
    return ""


def carregar_intencoes(caminho=None) -> tuple[list[str], list[str]]:
    """Lê o arquivo de treino e devolve (textos, rótulos).

    Usado pelo núcleo e por qualquer script de avaliação, garantindo que os
    dois trabalhem exatamente com os mesmos dados.
    """
    caminho = caminho or CAMINHO_INTENCOES
    with open(caminho, encoding="utf-8") as arquivo:
        registros = json.load(arquivo)

    textos = [registro["texto"] for registro in registros]
    rotulos = [registro["intencao"] for registro in registros]
    return textos, rotulos


@dataclass
class Resposta:
    """O que a Tartaruga devolve para a interface."""

    texto: str
    intencao: str
    confianca: float

    # Quando preenchido, a interface deve MOSTRAR o código e PEDIR
    # confirmação antes de executar. Nada roda sem o usuário aprovar.
    codigo_pendente: str | None = None

    # Sinaliza para a interface encerrar o programa.
    encerrar: bool = False

    # Dado estruturado (linguagem, código, padrão) quando a resposta gerou
    # HTML/CSS/JS - é o que o botão "Visualizar" da interface usa, em vez de
    # tentar recuperar o bloco a partir do texto já renderizado no balão.
    visualizacao: tuple[str, str, str] | None = None


class Tartaruga:
    """O assistente completo: classificador, conhecimento, diálogo e ferramentas."""

    # Três formas de responder dúvidas e geração de código - a escolha do
    # usuário na interface. Não afeta ferramentas (executar código, mexer em
    # arquivo, buscar na web, ver histórico) nem conversa fixa (saudação,
    # despedida, sobre o projeto): essas continuam sendo sempre da Tartaruga,
    # em qualquer modo - não faria sentido pedir ao LLM para "executar" algo
    # que ele não tem como executar de fato.
    #
    #   "tartaruga" -> núcleo próprio e encoder semântico opcional (classificador, base
    #                  curada, base aprendida, templates). NUNCA chama o LLM,
    #                  nem como reforço - admite "não sei" quando não sabe.
    #   "phi4mini"  -> pula direto para o modelo local em TODA pergunta e
    #                  pedido de código, sem tentar a base nem os templates
    #                  primeiro. Existe para comparação: mostra o que o LLM
    #                  sozinho faria com a mesma pergunta.
    #   "hibrido"   -> modo opcional: base e templates
    #                  primeiro, LLM só como reforço quando eles falham.
    MODOS = ("tartaruga", "hibrido", "phi4mini")
    MODO_PADRAO = "tartaruga"

    def __init__(self, retomar_conversa: bool = True) -> None:
        textos, rotulos = carregar_intencoes()
        self.classificador = ClassificadorNaiveBayes().treinar(textos, rotulos)
        self.base = BaseConhecimento()
        self.dialogo = GestorDialogo()
        self.aprendiz = Aprendiz()
        self.gerador = Gerador()
        self.memoria = Memoria()
        self.projetos = RepositorioProjetos()
        self.projeto_atual = None
        self.modo = self.MODO_PADRAO
        self.semantica = CompreensaoSemantica()

        if retomar_conversa:
            self.memoria.carregar_ultima()
            for turno in reversed(self.memoria.turnos):
                if turno.briefing is not None:
                    self.dialogo.briefing = Briefing.restaurar(turno.briefing)
                    break
            for turno in self.memoria.turnos[-12:]:
                if turno.papel == "usuario":
                    pedido = interpretar(turno.texto)
                    if pedido.linguagem:
                        self.dialogo.contexto.linguagem = pedido.linguagem
                    if turno.intencao == "capacidades" or "capacidade" in pedido.normalizado:
                        self.dialogo.contexto.assunto = "capacidades"

    # ------------------------------------------------------------------
    # Entrada principal
    # ------------------------------------------------------------------

    def responder(self, entrada: str) -> Resposta:
        """Recebe a frase do usuário e devolve a resposta da Tartaruga."""
        entrada = entrada.strip()
        self._visualizacao_pendente = None
        if not entrada:
            return Resposta(
                texto="Não recebi nada. Pode escrever sua pergunta?",
                intencao="vazio",
                confianca=0.0,
            )

        original = entrada
        pedido = interpretar(entrada)
        giria = social_canonico(self, pedido)          # "eae", "obrigadao": a saudação/agradecimento equivalente
        if giria:
            pedido = interpretar(giria)
        self._aviso_digitacao = ""
        if self.modo != "phi4mini" and conversa_livre(self):
            corrigida = corrigir_digitacao(self.base, pedido.texto)
            if corrigida is not None and self.base.buscar(pedido.texto) is None:
                # "oq e flexbos": erro de digitação num termo conhecido, corrigido só se a base responde à versão certa.
                self._aviso_digitacao = f'_Entendi "{corrigida}" (você escreveu "{pedido.texto}")._'
                pedido = interpretar(corrigida)
        # O turno é contado UMA vez por mensagem, aqui, para todos os caminhos: a janela do contexto
        # (contexto_conversa.JANELA_TURNOS) depende de que o tópico e o turno sejam contados igual, seja
        # qual for o resolvedor que responde (achado do Hypothesis: contexto expirando uma mensagem antes).
        self.dialogo.registrar_turno()
        # Regras de contexto e análise própria também funcionam sem o LLM.
        # No modo de comparação exclusivo, preservamos o encaminhamento antigo.
        if self.modo != "phi4mini":
            tratamento = resolver_semantica(self, pedido, apenas_pendente=True)
            if tratamento is None:
                consulta = consulta_de_pesquisa(self, pedido)
                if consulta is not None:
                    # Verbo de pesquisa é comando: vale antes de capacidades e do classificador.
                    self.memoria.adicionar("usuario", original, intencao="buscar_web", confianca=0)
                    resposta = self._buscar_web(original, "buscar_web", 1.0, consulta=consulta)
                    self.dialogo.contexto.assunto = "buscar_web"
                    self.dialogo.contexto.pendente = ""
                    return self._registrar_resposta(resposta)
            if tratamento is None:
                direta = intencao_direta(self, pedido)
                if direta:
                    # Comando inequívoco de arquivo ("salva isso em x.py", "leia x.py") ou "aprenda sobre X".
                    entrada_direta = pedido.texto
                    if pedido.codigo:
                        entrada_direta += f"\n```{pedido.linguagem}\n{pedido.codigo}\n```"
                    self.memoria.adicionar("usuario", original, intencao=direta, confianca=0)
                    resposta = self._despachar(entrada_direta, direta, 1.0)
                    if resposta.intencao not in ("desconhecido", "esclarecimento"):
                        self.dialogo.contexto.assunto = resposta.intencao
                        self.dialogo.contexto.pendente = ""
                        self.dialogo.contexto.instrucao_pendente = ""
                    return self._registrar_resposta(resposta)
            if tratamento is None:
                tratamento = resolver_social(self, pedido)
            if tratamento is None:
                tratamento = (resolver_planejar_briefing(self, pedido) or resolver_cancelar_sem_fluxo(self, pedido)
                              or resolver_continuacao(self, pedido) or resolver_catalogo(self, pedido)
                              or resolver_comparacao(self, pedido) or resolver_troca_de_linguagem(self, pedido)
                              or resolver_exemplo_do_topico(self, pedido) or resolver_ajuste_do_topico(self, pedido)
                              or resolver_refino(self, pedido))
            if tratamento is None:
                tratamento = resolver(self, pedido)
            if tratamento is None:
                # A mesma pergunta já teve uma opção escolhida nesta sessão: responde direto.
                tratamento = resolver_escolha_lembrada(self, pedido)
            if tratamento is None:
                # Referência curta ("isso aceita append?") com assunto recente: o contexto responde ANTES de o
                # classificador levá-la a outra intenção ("isso suporta extend?" -> capacidades).
                tratamento = resolver_referencia_contextual(self, pedido.texto or pedido.original)
            if tratamento is None:
                tratamento = resolver_semantica(self, pedido)
            if tratamento is not None:
                texto, intencao = tratamento
                self.memoria.adicionar("usuario", original, intencao=intencao, confianca=0)
                resposta = Resposta(texto, intencao, 0)
                return self._registrar_resposta(resposta)
        entrada = pedido.texto
        if pedido.codigo:
            entrada += f"\n```{pedido.linguagem}\n{pedido.codigo}\n```"
        intencao, confianca = self.classificador.prever(pedido.texto or entrada)
        faixa = self.dialogo.faixa(confianca, len(self.classificador.classes))

        # Proteção contra "âncora única": quando quase nenhuma palavra da
        # frase é reconhecida, a confiança não é confiável, mesmo que pareça
        # alta em relação ao acaso.
        #
        # BUG ENCONTRADO NUM TESTE REAL: "quem descobriu o brasil" tinha só
        # "quem" reconhecido (1 de 3 palavras - 33% de cobertura), e "quem"
        # sozinho já é forte o bastante para `sobre_projeto` (aparece em
        # quase todo exemplo de treino - "quem te criou", "quem fez você").
        # Resultado: 32% de confiança, alta o bastante para passar pela
        # faixa "alta" e disparar a resposta fixa sobre a própria Tartaruga
        # - CONFIANTE e completamente errada, pior que admitir "não sei".
        #
        # A base de conhecimento já tinha essa proteção
        # (`conhecimento.py::COBERTURA_MINIMA`); faltava a mesma ideia aqui,
        # no classificador de INTENÇÃO.
        if faixa != "baixa":
            # Cobertura PONDERADA (`classificador.cobertura_ponderada`), não
            # a fração bruta de palavras reconhecidas. A versão bruta
            # (contar 1 por palavra, não importa qual) tratava "quem"/"foi"
            # igual a "css"/"debounce" - e "quem foi Pelé" (2 de 3 palavras
            # = 67%) e "o que é stacking context em css" (2 de 4 = 50%)
            # ficavam do lado ERRADO do mesmo corte por pura coincidência de
            # contagem. A versão ponderada dá peso conforme o quão exclusiva
            # de um assunto a palavra é (ver `_calcular_pesos_palavras`), e
            # zera palavras interrogativas de propósito (mesma lista de
            # `vetorizador.INTERROGATIVAS`) - medido contra os mesmos casos
            # documentados no README, foi de 31/37 pra 35/37 acertos.
            cobertura = self.classificador.cobertura_ponderada(pedido.texto or entrada)
            if cobertura <= COBERTURA_MINIMA_INTENCAO:
                faixa = "baixa"

            # Mesma proteção de âncora, para GERAR CÓDIGO: um padrão ambíguo isolado ("responsivo", "lista",
            # "tabela"...) não deve nem chegar a mostrar o catálogo técnico — bloquear só o template não bastava
            # (achado em revisão: a resposta ainda "engajava com programação"). Downgrade
            # para a faixa baixa faz o pedido seguir pelo caminho honesto de sempre (base, contexto, "não sei"),
            # em vez do texto de `_gerar_codigo`.
            if (intencao == "gerar_codigo" and self.modo != "phi4mini"
                    and self.gerador.gerar(pedido.texto or entrada, contexto_tecnico=self._contexto_tecnico_recente()) is None):
                faixa = "baixa"

            # Mesmo achado, para a FERRAMENTA de arquivo: "arquivo" isolado despachava direto para
            # manipular_arquivo (o catálogo "sei listar, ler e salvar..."), sem nunca passar pela base — a
            # fuga que a revisão encontrou. Mesmo critério do substantivo ambíguo isolado, sem lista de frases:
            # comandos de verdade ("leia exemplo.py", "lista os arquivos") têm mais de uma palavra e não são afetados.
            if intencao == "manipular_arquivo" and self._kb_bloqueada_por_substantivo_isolado(pedido.texto or entrada):
                faixa = "baixa"

        self.memoria.adicionar("usuario", original, intencao=intencao, confianca=confianca)

        if faixa == "baixa":
            resposta = self._tratar_incerteza(entrada, intencao, 0)
        else:
            resposta = self._despachar(entrada, intencao, confianca)

            # Confiança mediana numa ação: agimos, mas avisamos. Antes o
            # sistema tratava 53% com a mesma segurança de 99%, o que soava
            # presunçoso justamente nos casos em que ele mais errava.
            if faixa == "media" and intencao in INTENCOES_DE_ACAO:
                resposta.texto += (
                    f"\n\n_(Não tenho certeza absoluta de que entendi — "
                    f"se eu errei, me diz que eu corrijo.)_"
                )

        if resposta.intencao in ("desconhecido", "esclarecimento"):
            resposta.confianca = 0
        if resposta.intencao == "capacidades":
            self.dialogo.contexto.assunto = "capacidades"
        elif resposta.intencao not in ("desconhecido", "saudacao", "agradecimento", "reacao_positiva"):
            self.dialogo.contexto.assunto = resposta.intencao
            self.dialogo.contexto.pendente = ""
            self.dialogo.contexto.instrucao_pendente = ""
        return self._registrar_resposta(resposta)

    def _registrar_resposta(self, resposta: Resposta) -> Resposta:
        """Grava o estado do briefing junto à conversa, sem um arquivo global separado."""
        # Alguns caminhos (ex.: o resolvedor de contexto de conversa.py)
        # devolvem só texto e perdem o campo estruturado; `_gerar_codigo`
        # o deixa guardado aqui e este ponto único de saída o reanexa.
        if resposta.visualizacao is None:
            resposta.visualizacao = getattr(self, "_visualizacao_pendente", None)
        if getattr(self, "_aviso_digitacao", ""):
            resposta.texto = self._aviso_digitacao + "\n\n" + resposta.texto
            self._aviso_digitacao = ""
        briefing = self.dialogo.briefing
        if briefing.aviso:
            resposta.texto += "\n\n" + briefing.aviso
            briefing.aviso = ""
        self.memoria.adicionar("tartaruga", resposta.texto, briefing=briefing.exportar())
        self.memoria.salvar()
        if briefing.estado == "confirmado" and "Briefing confirmado" in resposta.texto:
            projeto = self.projetos.criar_ou_atualizar(
                briefing.dados, str(self.memoria.caminho_sessao or "")
            )
            self.projeto_atual = projeto
            resposta.texto += f"\n\nProjeto salvo: **{projeto.nome}** (`{projeto.id}`)."
            self.memoria.turnos[-1].texto = resposta.texto
            self.memoria.salvar()
        return resposta

    def _despachar(self, entrada: str, intencao: str, confianca: float) -> Resposta:
        """Chama o tratador correspondente à intenção detectada."""
        tratadores = {
            "saudacao": self._saudacao,
            "como_vai": self._como_vai,
            "capacidades": self._capacidades,
            "sobre_projeto": self._sobre_projeto,
            "agradecimento": self._agradecimento,
            "reacao_positiva": self._reacao_positiva,
            "nao_entendi": self._nao_entendi,
            "duvida_programacao": self._duvida_programacao,
            "aprender": self._aprender,
            "gerar_codigo": self._gerar_codigo,
            "executar_codigo": self._executar_codigo,
            "buscar_web": self._buscar_web,
            "manipular_arquivo": self._manipular_arquivo,
            "ver_historico": self._ver_historico,
            "despedida": self._despedida,
        }
        tratador = tratadores.get(intencao)
        if tratador is None:
            return self._tratar_incerteza(entrada, intencao, confianca)
        return tratador(entrada, intencao, confianca)

    # ------------------------------------------------------------------
    # Incerteza
    # ------------------------------------------------------------------

    def _tratar_incerteza(self, entrada: str, intencao: str, confianca: float) -> Resposta:
        """Plano B quando o classificador não tem confiança suficiente.

        Em vez de agir com base num palpite fraco, tentamos a base de
        conhecimento: a maioria das frases ambíguas acaba sendo uma dúvida de
        programação, e a similaridade é um sinal independente do classificador.
        Só se nem isso resolver é que admitimos não ter entendido.

        O comportamento muda conforme `self.modo` (ver a constante MODOS):
        em "tartaruga" a base é tentada mas o reforço nunca é chamado; em
        "phi4mini" a base é pulada e o reforço é tentado direto - é o modo
        que existe para COMPARAR, então não faz sentido ele ainda torcer
        para a base própria responder primeiro.
        """
        if self.modo != "phi4mini":
            resultado = self.base.buscar(entrada)
            if resultado is not None and not self._kb_bloqueada_por_substantivo_isolado(entrada):
                return Resposta(
                    texto=self._formatar_conhecimento(resultado),
                    intencao="duvida_programacao",
                    confianca=confianca,
                )

        # O contexto da conversa (assunto recente, "isso", "dessa forma") resolve ANTES de
        # oferecer opções ou pedir reformulação; ver contexto_conversa.py.
        if self.modo != "phi4mini":
            contextual = resolver_com_contexto(self, entrada)
            if contextual is not None:
                texto_contextual, intencao_contextual = contextual
                return Resposta(
                    texto=texto_contextual, intencao=intencao_contextual,
                    confianca=confianca if intencao_contextual == "duvida_programacao" else 0)

        if self.modo != "tartaruga":
            reforco = self._reforco_geral(entrada)
            if reforco is not None:
                return Resposta(texto=reforco, intencao="desconhecido", confianca=confianca)

        # Nada passou do limiar de resposta direta, mas a base pode ter um
        # palpite plausível: melhor OFERECER o assunto e deixar a pessoa
        # confirmar do que dizer "não entendi". Só conteúdo curado; fora do
        # domínio da base a lista vem vazia e cai no "não entendi" de sempre.
        if self.modo != "phi4mini":
            ctx = self.dialogo.contexto
            consulta = chave_consulta(entrada)
            recusadas = ctx.rejeitadas.get(consulta, set())
            # Até 2 opções realmente DIFERENTES; o que a pessoa já recusou para esta
            # mesma pergunta não é oferecido de novo.
            opcoes = [(c, t_) for c, t_, _ in opcoes_distintas(
                [("conhecimento:" + s.identificador, s.titulo, s.similaridade)
                 for s in self.base.sugerir(entrada) if "conhecimento:" + s.identificador not in recusadas])]
            # Duas opções, mas só UMA fica na vizinhança do assunto recente: o contexto
            # desambigua e responde, sem perguntar.
            pelo_contexto = escolher_pelo_contexto(self, opcoes)
            if pelo_contexto is not None:
                (chave, titulo), recente = pelo_contexto
                aplicado = _aplicar_chave(self, chave)
                if aplicado is not None:
                    texto_aplicado, _ = aplicado
                    return Resposta(
                        texto=(f"Como estávamos falando de **{recente['titulo']}**, entendi que você "
                               f"quer saber sobre **{titulo}**.\n\n{texto_aplicado}"),
                        intencao="duvida_programacao", confianca=confianca)
            if opcoes:
                ctx.opcoes_semanticas = opcoes
                ctx.consulta_opcoes = consulta
                return Resposta(
                    texto=montar_pergunta_de_esclarecimento(opcoes),
                    intencao="esclarecimento",
                    confianca=0,
                )

        return Resposta(
            texto=self.dialogo.escolher("incerteza"),
            intencao="desconhecido",
            confianca=confianca,
        )

    # ------------------------------------------------------------------
    # Conversa
    # ------------------------------------------------------------------

    def _saudacao(self, entrada: str, intencao: str, confianca: float) -> Resposta:
        """Cumprimenta - de forma diferente a partir da segunda vez.

        Repetir a apresentação inteira a cada 'oi' foi o comportamento que
        mais denunciava um robô: o texto idêntico ficava na tela duas vezes,
        uma embaixo da outra.
        """
        if self.dialogo.ja_cumprimentou:
            texto = self.dialogo.escolher("saudacao_repetida")
        else:
            texto = self.dialogo.escolher("saudacao_primeira")
            self.dialogo.ja_cumprimentou = True

        return Resposta(texto=texto, intencao=intencao, confianca=confianca)

    def _como_vai(self, entrada: str, intencao: str, confianca: float) -> Resposta:
        self.dialogo.ja_cumprimentou = True
        return Resposta(
            texto=self.dialogo.escolher("como_vai"),
            intencao=intencao,
            confianca=confianca,
        )

    def _capacidades(self, entrada: str, intencao: str, confianca: float) -> Resposta:
        """Responde o que sabe fazer, adequando-se à forma da pergunta.

        Quem pergunta "você consegue conversar comigo?" fez uma pergunta de
        sim ou não e merece uma resposta que comece por "consigo". Despejar
        um menu de funcionalidades é responder à CATEGORIA da frase e ignorar
        a frase em si.
        """
        # A ordem aqui importa. Num teste real, "quais linguagens você
        # consegue codar?" caiu em `capacidades_repetida` - "continua valendo
        # o que falei" - porque o estado dizia que as capacidades já tinham
        # sido listadas. Mas a pergunta era MAIS ESPECÍFICA que a anterior,
        # e dispensá-la foi pior do que se não houvesse estado nenhum.
        #
        # Por isso o assunto específico é verificado primeiro: só caímos na
        # resposta genérica quando a pergunta é, de fato, genérica.
        assunto = self.dialogo.assunto_da_capacidade(entrada)

        # Caso especial: perguntar sobre o modelo local ("você usa o
        # phi-4?") exige saber se ele está DE FATO disponível agora, não só
        # se a Tartaruga sabe usá-lo em tese - a resposta muda conforme o
        # Ollama esteja rodando ou não nesta execução.
        if assunto == "llm":
            chave = "capacidade_llm_ativo" if llm.disponivel() else "capacidade_llm_inativo"
            self.dialogo.ja_listou_capacidades = True
            self.dialogo.ja_cumprimentou = True
            return Resposta(
                texto=self.dialogo.escolher(chave, modelo=llm.MODELO_PADRAO),
                intencao=intencao,
                confianca=confianca,
            )

        if assunto:
            chave = f"capacidade_{assunto}"
        elif self.dialogo.ja_listou_capacidades:
            chave = "capacidades_repetida"
        elif self.dialogo.e_pergunta_sim_nao(entrada):
            chave = "capacidades_sim_nao"
        else:
            chave = "capacidades_geral"

        self.dialogo.ja_listou_capacidades = True
        self.dialogo.ja_cumprimentou = True

        return Resposta(
            texto=self.dialogo.escolher(chave, topicos=len(self.base), padroes=total_padroes()),
            intencao=intencao,
            confianca=confianca,
        )

    def _sobre_projeto(self, entrada: str, intencao: str, confianca: float) -> Resposta:
        self.dialogo.ja_falou_do_projeto = True
        return Resposta(
            texto=self.dialogo.escolher("sobre_projeto"),
            intencao=intencao,
            confianca=confianca,
        )

    def _agradecimento(self, entrada: str, intencao: str, confianca: float) -> Resposta:
        return Resposta(
            texto=self.dialogo.escolher("agradecimento"),
            intencao=intencao,
            confianca=confianca,
        )

    def _reacao_positiva(self, entrada: str, intencao: str, confianca: float) -> Resposta:
        return Resposta(
            texto=self.dialogo.escolher("reacao_positiva"),
            intencao=intencao,
            confianca=confianca,
        )

    def _nao_entendi(self, entrada: str, intencao: str, confianca: float) -> Resposta:
        """Reapresenta o último assunto, em vez de só pedir desculpas.

        Se sabemos sobre o que estávamos falando, o mais útil é mostrar o
        conteúdo de novo com outro enquadramento - especialmente o exemplo
        de código, que costuma esclarecer mais que a explicação.
        """
        if self.dialogo.ultimo_topico:
            entrada_base = next(
                (e for e in self.base.entradas if e["id"] == self.dialogo.ultimo_topico),
                None,
            )
            if entrada_base is not None:
                partes = [
                    f"Vou tentar de outro jeito, então — {entrada_base['titulo']}.\n",
                    entrada_base["resposta"],
                ]
                if entrada_base.get("codigo"):
                    partes.append(
                        "\nOlhe o exemplo com calma, linha por linha — "
                        "costuma esclarecer mais que a explicação:\n"
                    )
                    partes.append(f"```python\n{entrada_base['codigo']}\n```")
                partes.append("\nQual parte específica ainda não fechou?")
                return Resposta(
                    texto="\n".join(partes),
                    intencao=intencao,
                    confianca=confianca,
                )

        return Resposta(
            texto=self.dialogo.escolher("nao_entendi"),
            intencao=intencao,
            confianca=confianca,
        )

    def _despedida(self, entrada: str, intencao: str, confianca: float) -> Resposta:
        return Resposta(
            texto=self.dialogo.escolher("despedida"),
            intencao=intencao,
            confianca=confianca,
            encerrar=True,
        )

    # ------------------------------------------------------------------
    # Conhecimento
    # ------------------------------------------------------------------

    def _duvida_programacao(self, entrada: str, intencao: str, confianca: float) -> Resposta:
        """Responde uma dúvida de programação - o caminho muda conforme `self.modo`.

        Em "phi4mini" a base é pulada de propósito, mesmo que ela tivesse a
        resposta: o modo existe para mostrar o que o modelo local faz
        sozinho, e torcer para a base responder primeiro desvirtuaria a
        comparação.
        """
        resultado = None if self.modo == "phi4mini" else self.base.buscar(entrada)
        if resultado is not None and self._kb_bloqueada_por_substantivo_isolado(entrada):
            resultado = None

        if resultado is None:
            # O assunto recente (ou um "isso"/"dessa forma") pode resolver antes de admitir que não sabe.
            if self.modo != "phi4mini":
                contextual = resolver_com_contexto(self, entrada)
                if contextual is not None:
                    texto_contextual, intencao_contextual = contextual
                    return Resposta(
                        texto=texto_contextual,
                        intencao=intencao_contextual,
                        confianca=confianca if intencao_contextual == "duvida_programacao" else 0)

            if self.modo != "tartaruga":
                reforco = self._reforco_geral(entrada)
                if reforco is not None:
                    return Resposta(texto=reforco, intencao=intencao, confianca=confianca)

            return Resposta(
                texto=self.dialogo.escolher("sem_conhecimento", topicos=len(self.base)),
                intencao=intencao,
                confianca=confianca,
            )

        return Resposta(
            texto=self._formatar_conhecimento(resultado),
            intencao=intencao,
            confianca=confianca,
        )

    def _reforco_geral(self, entrada: str) -> str | None:
        """Último recurso antes de admitir que não sabe: pergunta ao Phi-4-mini.

        Chamado só depois que classificador, base curada e base aprendida já
        foram tentados. Amplia o papel do LLM além de geração de código - foi
        uma decisão deliberada, não um efeito colateral (ver README): no caso
        raro em que TUDO mais falha, a Tartaruga responde como um assistente
        de propósito geral por um instante, em vez de simplesmente desistir.

        Devolve None se o Ollama não estiver disponível ou a chamada falhar -
        nesses casos o chamador cai na recusa honesta de sempre.
        """
        if not llm.disponivel():
            return None

        resposta = llm.responder_geral(entrada)
        if not resposta:
            return None

        # Transparência sobre a origem, mas sem o parágrafo inteiro: um
        # aviso longo repetido em toda resposta do reforço poluía o chat.
        # O nome do modelo no rodapé já basta para quem quiser saber a
        # procedência - os detalhes completos ficam só no README.
        # Negrito (**), não itálico com underscore: a interface gráfica só
        # sabe renderizar **negrito** - um itálico com "_texto_" apareceria
        # com os underscores crus na tela, e a regex genérica que os
        # reconheceria arriscaria capturar por engano nomes com underscore
        # dentro de texto técnico (ex: "minha_funcao").
        return f"{resposta}\n\n— **{llm.MODELO_PADRAO}**"

    def _formatar_conhecimento(self, resultado) -> str:
        """Monta a resposta a partir de uma entrada da base.

        Três detalhes de conversa acontecem aqui:

        1. Se o assunto já foi explicado nesta conversa, a abertura muda -
           repetir do zero como se fosse a primeira vez soa desatento.
        2. O código vai em bloco markdown, o que permite à memória extraí-lo
           depois e ao usuário dizer "roda isso aí".
        3. No fim, sugerimos assuntos próximos, dando continuidade em vez de
           encerrar o turno num ponto final.
        """
        repetido = self.dialogo.ja_explicou(resultado.identificador)
        self.dialogo.registrar_topico(resultado.identificador)

        partes = []
        if repetido:
            partes.append(f"Já tínhamos passado por isso, mas vamos de novo — {resultado.titulo}\n")
        else:
            partes.append(f"{resultado.titulo}\n")

        partes.append(resultado.resposta)

        if resultado.codigo:
            linguagem = _linguagem_do_topico(resultado.identificador, resultado.codigo)
            partes.append(f"\n```{linguagem}\n{resultado.codigo}\n```")

        # Conhecimento aprendido na web SEMPRE vem com a fonte à vista.
        # Ninguém revisou aquele texto - quem lê precisa poder conferir, e
        # precisa saber que a origem é diferente do conteúdo curado.
        if resultado.aprendido and resultado.fonte_dominio:
            partes.append(
                f"\n_Isto eu aprendi pesquisando, lendo {resultado.fonte_dominio}. "
                f"Não foi revisado por ninguém — vale conferir na fonte:_\n"
                f"{resultado.fonte_url}"
            )

        proximos = self.base.relacionados(resultado.identificador)
        if proximos and not repetido:
            titulos = " · ".join(r.titulo for r in proximos)
            partes.append("\n" + self.dialogo.escolher("sugestao_relacionados", topicos=titulos))

        return "\n".join(partes)

    # ------------------------------------------------------------------
    # Geração de código
    # ------------------------------------------------------------------

    def _kb_bloqueada_por_substantivo_isolado(self, entrada: str) -> bool:
        """Etapa 1 na BASE (não só na geração): "lista", "formulário", "classe", "função", "objeto",
        "variável"... isolados respondiam com confiança total, porque a evidência por cobertura não penaliza
        nada quando a única palavra da pergunta é exatamente a que a base conhece — não há palavra desconhecida
        para derrubar a nota. Bloqueia só quando a pergunta INTEIRA é uma palavra E ela está em TERMOS_AMBIGUOS
        (tem sentido comum fora de programação) — não qualquer palavra fora do léxico: "debounce"/"singleton"
        continuam liberados sozinhos por não terem sentido comum nenhum para confundir. "for"/"grid"
        (polissêmicos) e "append"/"python" (fortes) também continuam liberados, como já eram. Um tópico técnico
        recém-explicado libera de novo (ex.: repetir "lista" logo após termos explicado Listas).
        """
        palavras = re.findall(r"[\wÀ-ÿ]+", entrada)
        if len(palavras) != 1:
            return False
        tokens = tokenizar(entrada, STOPWORDS_BUSCA)
        if not tokens or tokens[0] not in SUBSTANTIVOS_AMBIGUOS_ISOLADOS:
            return False
        return topico_recente(self) is None

    def _contexto_tecnico_recente(self) -> bool:
        """Tópico de CSS/HTML recém-explicado: vale como âncora para um padrão de geração ambíguo isolado."""
        recente = topico_recente(self)
        return bool(recente and recente["titulo"].startswith(("CSS:", "HTML:")))

    def _gerar_codigo(self, entrada: str, intencao: str, confianca: float) -> Resposta:
        """Monta um trecho de HTML ou CSS a partir de um pedido concreto.

        Diferença para `_duvida_programacao`: aquela EXPLICA um conceito
        recuperando texto já escrito; esta MONTA um artefato novo, com
        parâmetros tirados do pedido (`geracao.py`). É a diferença entre
        "o que é um formulário" e "cria um formulário de login".

        Honestidade obrigatória: para o caminho comum (um dos 35 padrões
        conhecidos, agora incluindo 13 de JavaScript avançado), isto NÃO é
        geração livre por modelo de linguagem, é montagem de templates. A
        resposta sempre diz isso.

        Só quando NENHUM padrão bate é que existe um segundo caminho: um
        modelo de linguagem local (Phi-4-mini, via Ollama), tentado como
        REFORÇO, não como base — ver `ferramentas/llm.py` e a seção do
        README sobre essa decisão. Se o modelo também não estiver disponível
        ou não souber responder, a recusa honesta de sempre continua sendo
        o resultado final; nunca um código inventado com cara de acerto.

        `self.modo` muda essa ordem: em "phi4mini" os templates nem são
        tentados (o modo existe para comparação, então não faz sentido
        deixar o template "vencer" antes do LLM ter a chance); em
        "tartaruga" o LLM nunca é chamado, nem como reforço.
        """
        resultado = None if self.modo == "phi4mini" else self.gerador.gerar(entrada, contexto_tecnico=self._contexto_tecnico_recente())

        if resultado is not None:
            extensao = {"html": "html", "css": "css", "javascript": "js"}[resultado.linguagem]
            aviso = ""
            if resultado.ignorados:
                aviso = (f"Atenção: você pediu também {', '.join(resultado.ignorados)}. Isso eu não gero: monto só HTML, CSS "
                         f"e JavaScript puros. O que depende disso fica por sua conta.\n\n")
            texto = (
                f"{aviso}Montei {resultado.descricao} em {resultado.linguagem.upper()}:\n\n"
                f"```{resultado.linguagem}\n{resultado.codigo}\n```\n\n"
                f"_Isto foi MONTADO por um gerador de templates com parâmetros — "
                f"não escrito por um modelo de linguagem. Ele sabe montar um conjunto "
                f"fixo de padrões comuns; fora deles, eu explico o conceito, mas não "
                f"invento um layout do zero._\n\n"
                f"Se quiser, peça \"salva isso em nome.{extensao}\"."
            )
            visualizacao = (resultado.linguagem, resultado.codigo, resultado.padrao)
            self._visualizacao_pendente = visualizacao
            self.dialogo.contexto.ultima_geracao = {
                "linguagem": resultado.linguagem, "descricao": resultado.descricao,
                "codigo": resultado.codigo, "turno": self.dialogo.turnos, "padrao": resultado.padrao,
            }
            if resultado.padrao == "landing" and self.dialogo.briefing.estado != "coletando":
                texto += ("\n\nSe preferir planejar a página passo a passo, diga 'quero uma landing page' "
                          "que eu conduzo um briefing.")
            return Resposta(
                texto=texto, intencao=intencao, confianca=confianca,
                visualizacao=visualizacao,
            )

        # Nenhum dos 35 padrões bateu (ou o modo pulou direto pra cá). Tenta
        # o modelo local - a não ser que o modo seja "tartaruga", que nunca
        # chama o LLM - e só se ele estiver rodando (checagem rápida, 2s,
        # para não esperar até 2 minutos de timeout quando o Ollama nem
        # está de pé).
        if self.modo != "tartaruga" and llm.disponivel():
            resultado_llm = llm.gerar(entrada)
            if resultado_llm is not None:
                codigo, linguagem = resultado_llm
                # Transparência sobre a origem reduzida ao nome do modelo no
                # rodapé - um aviso de parágrafo inteiro repetido em toda
                # geração de reforço poluía o chat. Detalhes completos sobre
                # o que isso significa ficam só no README.
                texto = (
                    f"Isto está fora dos meus {total_padroes()} padrões prontos, então pedi reforço:\n\n"
                    f"```{linguagem}\n{codigo}\n```\n\n"
                    + (
                        # Python, diferente de HTML/CSS, pode ser EXECUTADO pelo
                        # fluxo de confirmação já existente - vale oferecer isso
                        # em vez de só sugerir salvar.
                        'Peça "roda isso" para executar (com a confirmação de '
                        'sempre), ou "salva isso em nome.py" para guardar.'
                        if linguagem == "python"
                        else f"Se quiser, peça \"salva isso em nome.{linguagem}\"."
                    )
                    + f"\n\n— **{llm.MODELO_PADRAO}**"
                )
                visualizacao = (
                    (linguagem, codigo, "") if linguagem in ("html", "css", "javascript") else None
                )
                self._visualizacao_pendente = visualizacao
                return Resposta(
                    texto=texto, intencao=intencao, confianca=confianca,
                    visualizacao=visualizacao,
                )

            # No modo Phi-4-mini, chegar aqui com o Ollama disponível
            # significa que o próprio modelo devolveu NAO_SEI ou algo sem
            # bloco de código reconhecível - diferente de não tentar.
            if self.modo == "phi4mini":
                return Resposta(
                    texto=f"O {llm.MODELO_PADRAO} não conseguiu gerar nada para esse pedido.",
                    intencao=intencao,
                    confianca=confianca,
                )

        # Caso especial: modo Phi-4-mini escolhido, mas o Ollama não está
        # rodando agora. A recusa padrão (listando os 35 padrões) soaria
        # estranha aqui - eles nem foram tentados, de propósito. Melhor
        # dizer exatamente o que faltou.
        if self.modo == "phi4mini":
            return Resposta(
                texto=(
                    f"O modo Phi-4-mini está selecionado, mas o Ollama não está "
                    f"rodando agora — não tenho como responder sem ele. Troque para "
                    f"\"Tartaruga\" ou \"Tartaruga + Phi-4-mini\", ou inicie o Ollama."
                ),
                intencao=intencao,
                confianca=confianca,
            )

        return Resposta(
            texto=(
                "Não reconheci que tipo de código você quer que eu monte.\n\n"
                "Em HTML, sei montar: página, formulário, navbar, card, lista, "
                "tabela, botão, modal, abas, sanfona, trilha de navegação e menu "
                "suspenso.\n"
                "Em CSS, sei montar: flexbox, grid, botão, variáveis de cor/tema, "
                "centralização, responsivo, sombra, transição e animação.\n"
                "Em JavaScript avançado, sei montar: debounce, throttle, memoization, "
                "currying, clonagem profunda, emissor de eventos (pub/sub), retry, "
                "Promise com tempo limite, requisição assíncrona (fetch), classes com "
                "herança, generator, singleton e Proxy de validação.\n\n"
                "Diga algo como \"cria um formulário de login em html\", "
                "\"gera um layout com flexbox\" ou \"cria uma função debounce em "
                "javascript\"."
            ),
            intencao=intencao,
            confianca=confianca,
        )

    # ------------------------------------------------------------------
    # Aprendizado
    # ------------------------------------------------------------------

    def _aprender(self, entrada: str, intencao: str, confianca: float) -> Resposta:
        """Pesquisa um assunto, escolhe a melhor fonte e guarda o que leu.

        A resposta mostra o RACIOCÍNIO sobre as fontes, não só o resultado.
        Isso é proposital: a parte difícil de pesquisar não é achar páginas,
        é decidir em quem acreditar — e deixar esse critério à vista é o que
        transforma a funcionalidade em algo defensável.
        """
        assunto = self._extrair_assunto_estudo(entrada)

        if not assunto:
            return Resposta(
                texto=(
                    "Sobre o que você quer que eu estude?\n\n"
                    "Diga, por exemplo: \"aprenda sobre flexbox\" ou "
                    "\"estude o que é uma promise em JavaScript\"."
                ),
                intencao=intencao,
                confianca=confianca,
            )

        # Verifica ANTES de pesquisar se algum conhecimento equivalente já
        # existe — curado ou aprendido antes, tanto faz.
        #
        # BUG ENCONTRADO: `Aprendiz.ja_sabe()` só compara contra a própria
        # base aprendida (dados_aprendidos.json), pelo id exato. Pedir
        # "aprenda sobre flexbox" quando "CSS: Flexbox" já existe CURADO
        # não seria detectado por ele — geraria uma segunda entrada sobre o
        # mesmo assunto, de qualidade inferior (não revisada por ninguém),
        # competindo com a curada na busca.
        #
        # A verificação certa usa a mesma busca por similaridade que
        # responde dúvidas — ela já enxerga as duas bases juntas — em vez de
        # comparação por id, que só serve para reconhecer o que o PRÓPRIO
        # aprendiz já pesquisou antes.
        ja_existe = self.base.buscar(assunto)
        if ja_existe is not None:
            origem = (
                f"aprendi antes, lendo {ja_existe.fonte_dominio}"
                if ja_existe.aprendido
                else "já revisado na minha base"
            )
            return Resposta(
                texto=(
                    f"Já sei sobre isso — {origem}: **{ja_existe.titulo}**.\n\n"
                    f"Pergunte diretamente que eu respondo, sem precisar pesquisar de novo."
                ),
                intencao=intencao,
                confianca=confianca,
            )

        resultado = self.aprendiz.aprender(assunto)

        if not resultado.sucesso:
            texto = f"Não consegui aprender sobre \"{assunto}\".\n\n{resultado.mensagem}"
            if resultado.fontes_avaliadas:
                texto += "\n\nAs fontes que avaliei:\n" + self._listar_fontes(
                    resultado.fontes_avaliadas
                )
            return Resposta(texto=texto, intencao=intencao, confianca=confianca)

        # O IDF depende do conjunto inteiro de documentos, então o índice
        # precisa ser reconstruído para a entrada nova ser encontrável.
        self.base.recarregar()

        entrada_nova = resultado.entrada or {}
        partes = [resultado.mensagem]

        if resultado.fontes_avaliadas:
            partes.append("\nComo escolhi a fonte:")
            partes.append(self._listar_fontes(resultado.fontes_avaliadas[:4]))

        resumo = entrada_nova.get("resposta", "")
        if resumo:
            trecho = resumo[:400] + ("..." if len(resumo) > 400 else "")
            partes.append(f"\nO que guardei:\n\n{trecho}")

        partes.append(
            f"\nJá posso responder sobre isso — minha base foi de "
            f"{len(self.base) - 1} para {len(self.base)} tópicos."
        )

        return Resposta(texto="\n".join(partes), intencao=intencao, confianca=confianca)

    @staticmethod
    def _listar_fontes(fontes) -> str:
        """Lista as fontes avaliadas com nota e justificativa."""
        simbolos = {
            "oficial": "★",
            "confiavel": "•",
            "cautela": "!",
            "desconhecido": "?",
            "evitar": "✗",
        }
        linhas = []
        for fonte in fontes:
            simbolo = simbolos.get(fonte.categoria, "?")
            motivo = fonte.motivos[0] if fonte.motivos else ""
            linhas.append(f"  {simbolo} {fonte.dominio} ({fonte.pontuacao}) — {motivo}")
        return "\n".join(linhas)

    @staticmethod
    def _extrair_assunto_estudo(entrada: str) -> str:
        """Remove o comando e devolve só o assunto a estudar.

        "aprenda sobre flexbox" -> "flexbox"
        """
        texto = entrada.strip()
        padrao = re.compile(
            r"^\s*(quero\s+que\s+voc[êe]\s+)?"
            r"(v[áa]\s+)?"
            r"(aprenda|aprender|estude|estuda|estudar|pesquise\s+e\s+aprenda|"
            r"memorize|acrescente|adicione|amplie|se\s+aprimore)"
            r"\s*(mais\s+)?(sobre|o\s+que\s+[ée]|em|no|na|isso|esse|essa)?\s*",
            re.IGNORECASE,
        )
        assunto = padrao.sub("", texto, count=1).strip()
        assunto = re.sub(
            r"\b(ao?\s+seu\s+conhecimento|na\s+sua\s+base(\s+de\s+conhecimento)?|"
            r"esse\s+assunto|esse\s+t[óo]pico|esse\s+tema)\b",
            "",
            assunto,
            flags=re.IGNORECASE,
        ).strip(" .?!")
        return assunto

    # ------------------------------------------------------------------
    # Ferramentas
    # ------------------------------------------------------------------

    def _executar_codigo(self, entrada: str, intencao: str, confianca: float) -> Resposta:
        """Localiza o código a ser executado e pede confirmação.

        O código pode vir colado na própria mensagem ou ter sido mencionado
        antes na conversa - é o que faz "roda isso aí" funcionar.

        BUG ENCONTRADO NUM TESTE REAL: depois de mostrar um exemplo de
        JavaScript e o usuário pedir "roda esse código", o sistema preparava
        para executar - como Python - um texto que começava com a palavra
        "javascript" solta, sobrada do marcador de linguagem do bloco
        markdown que o extrator antigo não sabia reconhecer. O único
        interpretador embutido é Python (ver `ferramentas/executar.py`), e
        rodar outra linguagem por engano nele não trava nada, mas produz um
        erro sem sentido para quem só queria ver o exemplo funcionando.

        A correção verifica a linguagem ANTES de propor a execução, e recusa
        com uma explicação honesta quando não é Python — em vez de tentar e
        deixar a pessoa decifrar um SyntaxError enigmático.
        """
        achado = Memoria.extrair_codigo_com_linguagem(entrada) or self.memoria.ultimo_codigo_com_linguagem()

        if not achado:
            return Resposta(
                texto=self.dialogo.escolher("codigo_ausente"),
                intencao=intencao,
                confianca=confianca,
            )

        codigo, linguagem = achado

        if linguagem != "python":
            nome_exibido = {"js": "JavaScript", "javascript": "JavaScript",
                             "html": "HTML", "css": "CSS"}.get(linguagem, linguagem)
            return Resposta(
                texto=(
                    f"Esse código é {nome_exibido}, e eu só executo Python — "
                    "é o único interpretador que carrego embutido.\n\n"
                    "Posso mostrar o que o código faz, mas rodar de verdade "
                    "só se for Python."
                ),
                intencao=intencao,
                confianca=confianca,
            )

        # Aviso preventivo, não bloqueio: o código ainda roda se confirmado,
        # mas quem vai autorizar merece saber ANTES que aquele input() vai
        # falhar - em vez de confirmar, esperar e só então ler um EOFError
        # sem contexto. Descoberto testando um jogo da velha gerado pelo
        # modelo local: `input()` não tem o que ler no ambiente isolado de
        # execução (sem entrada interativa), e o erro batia sem explicação.
        aviso_input = ""
        if re.search(r"\binput\s*\(", codigo):
            aviso_input = (
                "\n\n_Aviso: este código usa input() para pedir algo digitado, "
                "e o ambiente onde eu executo não tem entrada interativa — "
                "provavelmente vai falhar com EOFError. Para testar de verdade, "
                "salve com \"salva isso em nome.py\" e rode pelo terminal._"
            )

        return Resposta(
            texto="Encontrei este código:" + aviso_input,
            intencao=intencao,
            confianca=confianca,
            codigo_pendente=codigo,
        )

    def _buscar_web(self, entrada: str, intencao: str, confianca: float, consulta: str | None = None) -> Resposta:
        if consulta is None:
            consulta = self._extrair_consulta(entrada)

        if not consulta:
            return Resposta(
                texto="O que você quer que eu pesquise? Diga, por exemplo: "
                      "\"pesquisa sobre Django na internet\".",
                intencao=intencao,
                confianca=confianca,
            )

        buscas = self.dialogo.contexto.ultimas_buscas
        buscas.append((consulta, self.dialogo.turnos))
        del buscas[:-4]
        resposta_busca = web.buscar(consulta)

        if not resposta_busca.ok:
            return Resposta(
                texto=(
                    f"{resposta_busca.erro}\n\n"
                    "Minha base local continua funcionando — pode me perguntar "
                    "sobre programação que eu respondo sem internet."
                ),
                intencao=intencao,
                confianca=confianca,
            )

        linhas = [f'Achei isto na web sobre "{consulta}":\n']
        for posicao, item in enumerate(resposta_busca.resultados, start=1):
            trecho = item.trecho.strip()
            if len(trecho) > 200:
                trecho = trecho[:200].rstrip() + "..."
            linhas.append(f"{posicao}. {item.titulo}")
            if trecho:
                linhas.append(f"   {trecho}")
            linhas.append(f"   {item.link}\n")

        return Resposta(
            texto="\n".join(linhas).rstrip(),
            intencao=intencao,
            confianca=confianca,
        )

    def _manipular_arquivo(self, entrada: str, intencao: str, confianca: float) -> Resposta:
        """Decide entre listar, ler ou escrever, a partir das palavras da frase."""
        texto = entrada.lower()
        nome_arquivo = self._extrair_nome_arquivo(entrada)

        # --- listar ---
        # "mostre/mostra/mostrar/exiba/exibe os arquivos" também é listar: mesmo verbo de exibição usado para
        # ler um arquivo nomeado ("mostre exemplo.py"), mas aqui sem nome — a guarda `not nome_arquivo` já
        # distingue os dois casos, então não precisa de uma frase inteira decorada.
        palavras_listar = ("lista", "listar", "liste", "quais arquivos", "o que tem")
        pede_exibir_arquivos = bool(re.search(r"\b(?:mostre|mostra|mostrar|exiba|exibe|exibir)\b.*\barquivos\b", texto))
        if (any(p in texto for p in palavras_listar) or pede_exibir_arquivos) and not nome_arquivo:
            itens = arquivos.listar()
            if not itens:
                return Resposta(
                    texto="A pasta workspace/ está vazia. Peça para eu salvar algum código lá.",
                    intencao=intencao,
                    confianca=confianca,
                )
            lista = "\n".join(f"  • {item}" for item in itens)
            return Resposta(
                texto=f"Arquivos em workspace/:\n\n{lista}",
                intencao=intencao,
                confianca=confianca,
            )

        # --- escrever ---
        palavras_escrever = (
            "salva", "salvar", "grava", "gravar", "cria", "criar",
            "escreve", "escrever", "guarda",
        )
        if any(p in texto for p in palavras_escrever):
            conteudo = Memoria.extrair_codigo(entrada) or self.memoria.ultimo_codigo()
            if not conteudo:
                return Resposta(
                    texto=(
                        "Não achei conteúdo para salvar. Pergunte algo de programação "
                        "primeiro que eu salvo o exemplo, ou cole um código."
                    ),
                    intencao=intencao,
                    confianca=confianca,
                )

            destino = nome_arquivo or "codigo.py"
            try:
                caminho = arquivos.escrever(destino, conteudo)
            except (arquivos.ErroDeCaminho, OSError) as erro:
                return Resposta(texto=str(erro), intencao=intencao, confianca=confianca)

            if self.projeto_atual is not None and caminho.name not in self.projeto_atual.arquivos:
                self.projeto_atual.arquivos.append(caminho.name)
                self.projeto_atual.revisar(f"Arquivo associado: {caminho.name}")
                self.projetos.salvar(self.projeto_atual)
            return Resposta(
                texto=f"Pronto, salvei em workspace/{caminho.name} "
                      f"({len(conteudo)} caracteres).",
                intencao=intencao,
                confianca=confianca,
            )

        # --- ler ---
        if nome_arquivo:
            try:
                conteudo = arquivos.ler(nome_arquivo)
            except (arquivos.ErroDeCaminho, FileNotFoundError, IsADirectoryError, OSError) as erro:
                return Resposta(texto=str(erro), intencao=intencao, confianca=confianca)

            return Resposta(
                texto=f"Conteúdo de {nome_arquivo}:\n\n```\n{conteudo}\n```",
                intencao=intencao,
                confianca=confianca,
            )

        return Resposta(
            texto=self.dialogo.escolher("arquivo_ambiguo"),
            intencao=intencao,
            confianca=confianca,
        )

    def _ver_historico(self, entrada: str, intencao: str, confianca: float) -> Resposta:
        turnos = self.memoria.ultimos(12)

        # O turno atual ("mostra o histórico") já foi registrado; exibi-lo
        # seria ruído.
        turnos = [
            t for t in turnos
            if not (t.papel == "usuario" and t.texto == entrada.strip())
        ]

        if not turnos:
            return Resposta(
                texto="Ainda não conversamos nada nesta sessão.",
                intencao=intencao,
                confianca=confianca,
            )

        linhas = ["Nossa conversa até agora:\n"]
        for turno in turnos:
            quem = "Você" if turno.papel == "usuario" else "Tartaruga"
            texto = turno.texto.replace("\n", " ")
            if len(texto) > 90:
                texto = texto[:90].rstrip() + "..."
            hora = turno.hora[11:16] if len(turno.hora) >= 16 else ""
            linhas.append(f"  [{hora}] {quem}: {texto}")

        linhas.append(f"\nTotal de {len(self.memoria)} mensagens registradas.")
        return Resposta(texto="\n".join(linhas), intencao=intencao, confianca=confianca)

    # ------------------------------------------------------------------
    # Execução confirmada
    # ------------------------------------------------------------------

    def executar_codigo_confirmado(self, codigo: str) -> str:
        """Roda o código DEPOIS que o usuário autorizou na interface.

        Separado de `responder` de propósito: garante que nenhum caminho do
        código consiga executar algo sem passar pela confirmação.

        Mantido devolvendo só o texto por compatibilidade com `main.py`.
        Quem precisa saber se deu certo sem sniffar a string (a interface
        gráfica, para colorir o painel de execução) usa
        `executar_codigo_confirmado_info`.
        """
        _, texto = self.executar_codigo_confirmado_info(codigo)
        return texto

    def executar_codigo_confirmado_info(self, codigo: str) -> tuple[bool, str]:
        """Como `executar_codigo_confirmado`, mas também devolve se deu certo.

        Existir separado evita que quem precisa do resultado estruturado
        tenha que adivinhar o sucesso pelo TEXTO da resposta (checando se
        começa com "O código falhou", por exemplo) — frágil e o tipo de
        acoplamento que quebra silenciosamente se a frase mudar um dia.
        """
        resultado = executar.executar_python(codigo)

        if resultado.sucesso:
            if resultado.vazio:
                texto = ("O código rodou sem erros, mas não imprimiu nada. "
                         "Use print() para ver valores.")
            else:
                texto = f"Saída:\n\n{resultado.saida.rstrip()}"
        else:
            texto = f"O código falhou:\n\n{resultado.erro.rstrip()}"
            explicacao = executar.explicar_erro(resultado.erro)
            if explicacao:
                texto += f"\n\nO que isso significa: {explicacao}"

        self.memoria.adicionar("tartaruga", texto)
        self.memoria.salvar()
        return resultado.sucesso, texto

    # ------------------------------------------------------------------
    # Auxiliares
    # ------------------------------------------------------------------

    @staticmethod
    def _extrair_consulta(entrada: str) -> str:
        """Remove as palavras de comando para sobrar só o assunto da busca.

        "pesquisa na internet sobre django" -> "django"
        """
        entrada = re.sub(r"^\s*e\s+(?:o|a|os|as)\s+", "", entrada.strip(), flags=re.IGNORECASE)     # "e o flask também"
        palavras = re.findall(r"[\wÀ-ÿ]+", entrada.lower())
        uteis = [p for p in palavras if p not in RUIDO_BUSCA]
        return " ".join(uteis).strip()

    @staticmethod
    def _extrair_nome_arquivo(entrada: str) -> str | None:
        """Procura algo com cara de nome de arquivo na frase."""
        achado = PADRAO_ARQUIVO.search(entrada)
        return achado.group(1) if achado else None
