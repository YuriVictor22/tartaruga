"""Recuperação semântica opcional. Não gera texto nem dispara ferramentas.

O modelo é carregado apenas de uma pasta local preparada explicitamente.
Regras, respostas e fluxo de diálogo continuam pertencendo à Tartaruga.
"""
import os
import importlib.util
import re
import threading
from dataclasses import dataclass
from functools import lru_cache

from .caminhos import gravavel
from .vetorizador import STOPWORDS_BUSCA, remover_acentos, tokenizar

MODELO = "sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2"
PASTA_MODELO = gravavel("modelos", "semantica")
LIMIAR = 0.72
MARGEM = 0.07
LIMIAR_SUGESTAO = 0.58
_LOCK = threading.RLock()

EXEMPLOS = {
    "briefing": ("Planejar uma landing page", [
        "Quero uma landing page para divulgar meu negócio",
        "Preciso de uma página para captar clientes",
        "Vamos planejar uma página de vendas",
        "Quero organizar os requisitos de uma landing page",
    ]),
    "capacidades": ("Conhecer as capacidades da Tartaruga", [
        "O que você é capaz de fazer?", "Que tarefas você pode me ajudar a realizar?",
        "Quais recursos estão disponíveis neste assistente?",
    ]),
    # Concorrentes negativos: impedem encaminhar assuntos parecidos para ações.
    "fora": ("Outro assunto", [
        "Não quero criar uma página", "O que é uma landing page?",
        "Quero comprar um disco LP", "Quem descobriu o Brasil?",
        "Qual é a previsão do tempo?", "Quanto custa anunciar minha empresa?",
        "Execute este programa", "Apague os arquivos", "Pesquise na internet",
        "Gere código para um aplicativo", "Quero uma página de livro",
    ]),
}


@dataclass(frozen=True)
class Candidato:
    chave: str
    titulo: str
    similaridade: float


def decidir(candidatos):
    """Compara tópicos diferentes, não duas paráfrases do mesmo tópico."""
    if not candidatos or candidatos[0].chave == "fora":
        return "rejeitado"
    primeiro = candidatos[0].similaridade
    segundo = candidatos[1].similaridade if len(candidatos) > 1 else 0
    if primeiro >= LIMIAR and primeiro - segundo >= MARGEM:
        return "aceito"
    return "esclarecer" if primeiro >= LIMIAR_SUGESTAO else "rejeitado"


@lru_cache(maxsize=2)
def _carregar_modelo(pasta):
    from sentence_transformers import SentenceTransformer
    import torch
    torch.set_num_threads(min(4, os.cpu_count() or 1))
    return SentenceTransformer(pasta, device="cpu", local_files_only=True,
                               trust_remote_code=False)


class CompreensaoSemantica:
    def __init__(self):
        self.erro = ""
        self._assinatura = None
        self._vetores = None
        self._referencias = []

    def status(self):
        if os.environ.get("TARTARUGA_SEMANTICA", "1") == "0":
            return "Compreensão semântica desativada. Regras e Naive Bayes continuam disponíveis."
        if not (PASTA_MODELO / "modules.json").is_file():
            return "Modelo semântico não instalado. Execute preparar_semantica.py; o sistema tradicional continua disponível."
        if self.erro:
            return "Compreensão semântica indisponível: " + self.erro + ". O sistema tradicional continua disponível."
        if importlib.util.find_spec("sentence_transformers") is None:
            return "Pesos disponíveis, mas falta instalar requirements-semantic.txt. O sistema tradicional continua disponível."
        if self._vetores is None:
            return "Encoder MiniLM local disponível para carregamento na primeira consulta semântica. Não usa Phi-4-mini."
        return "Compreensão semântica habilitada: MiniLM multilíngue local, em CPU. Não gera respostas e não usa Phi-4-mini."

    def comparar(self, texto, entradas):
        if (os.environ.get("TARTARUGA_SEMANTICA", "1") == "0" or self.erro
                or not (PASTA_MODELO / "modules.json").is_file()
                or len(texto) > 1000):
            return []
        try:
            with _LOCK:
                modelo = _carregar_modelo(str(PASTA_MODELO))
                documentos, referencias = [], []
                for chave, (titulo, exemplos) in EXEMPLOS.items():
                    for exemplo in exemplos:
                        documentos.append(exemplo)
                        referencias.append((chave, titulo))
                for entrada in entradas:
                    if entrada.get("aprendido"):
                        continue  # esta primeira integração usa apenas conteúdo revisado
                    for pergunta in entrada["perguntas"]:
                        documentos.append(pergunta)
                        referencias.append(("conhecimento:" + entrada["id"], entrada["titulo"]))
                assinatura = tuple(zip(documentos, referencias))
                if assinatura != self._assinatura:
                    self._vetores = modelo.encode(documentos, normalize_embeddings=True, show_progress_bar=False)
                    self._referencias = referencias
                    self._assinatura = assinatura
                vetor = modelo.encode([texto], normalize_embeddings=True, show_progress_bar=False)[0]
                scores = self._vetores @ vetor
                melhores = {}
                for (chave, titulo), score in zip(self._referencias, scores):
                    if chave not in melhores or score > melhores[chave].similaridade:
                        melhores[chave] = Candidato(chave, titulo, float(score))
                return sorted(melhores.values(), key=lambda c: c.similaridade, reverse=True)[:3]
        except Exception as exc:
            self.erro = f"{type(exc).__name__}: {str(exc)[:180]}"
            return []


def _aplicar(bot, chave, original=""):
    from .interpretacao import interpretar
    from .conversa import geral
    from .conhecimento import Resultado
    bot.dialogo.contexto.pendente = ""
    bot.dialogo.contexto.instrucao_pendente = ""
    if chave == "briefing":
        bot.dialogo.contexto.assunto = "briefing"
        briefing = bot.dialogo.briefing
        novo = briefing.estado in {"inativo", "cancelado"}
        resposta = briefing.processar(interpretar("quero uma landing page"))
        if novo and original:
            briefing.pedido_inicial = original[:4000]
        return resposta, "briefing"
    if chave == "capacidades":
        bot.dialogo.contexto.assunto = "capacidades"
        return geral(bot), "capacidades"
    identificador = chave.removeprefix("conhecimento:")
    entrada = next((e for e in bot.base.entradas if e["id"] == identificador and not e.get("aprendido")), None)
    if entrada:
        bot.dialogo.contexto.assunto = "duvida_programacao"
        resultado = Resultado(entrada["id"], entrada["titulo"], entrada["resposta"], entrada.get("codigo", ""), 0)
        return bot._formatar_conhecimento(resultado), "duvida_programacao"
    return None


# ---------------------------------------------------------------------------
# Esclarecimento: perguntar, entender a resposta e lembrar a escolha
# ---------------------------------------------------------------------------

def chave_consulta(texto: str) -> str:
    """Identifica "a mesma pergunta": as palavras distintas (sem stopwords), em ordem."""
    return " ".join(sorted(set(tokenizar(texto, STOPWORDS_BUSCA))))


def _termos_do_titulo(titulo: str) -> set[str]:
    return set(tokenizar(titulo, STOPWORDS_BUSCA))


def opcoes_distintas(candidatos, maximo: int = 2):
    """Até `maximo` candidatos [(chave, titulo, nota)] realmente DIFERENTES entre si:
    o segundo só entra se a nota ficar perto da primeira e o título não for a MESMA coisa
    dita de outro jeito (um título contido no outro, ou palavras em comum >= 60% do total)."""
    escolhidas = []
    for chave, titulo, nota in candidatos:
        if len(escolhidas) >= maximo:
            break
        if escolhidas:
            _, titulo1, nota1 = escolhidas[0]
            termos, termos1 = _termos_do_titulo(titulo), _termos_do_titulo(titulo1)
            uniao = len(termos | termos1) or 1
            repetido = termos <= termos1 or termos1 <= termos or len(termos & termos1) / uniao >= 0.6
            if nota < 0.7 * nota1 or repetido:
                continue
        escolhidas.append((chave, titulo, nota))
    return escolhidas


def montar_pergunta_de_esclarecimento(opcoes) -> str:
    """Texto da pergunta de esclarecimento para 1 ou 2 opções [(chave, titulo)]."""
    if len(opcoes) == 1:
        titulo = opcoes[0][1]
        return "\n".join([
            f"Acho que você está falando de **{titulo}**, mas não tenho certeza. É isso?",
            "",
            f"1. {titulo}",
            "",
            'Responda "sim" para eu explicar, ou "não" se for outro assunto.',
        ])
    (_, a), (_, b) = opcoes[:2]
    return "\n".join([
        f"Quero ter certeza de que entendi: você quer saber sobre **{a}** ou sobre **{b}**?",
        "",
        f"1. {a}",
        f"2. {b}",
        "",
        'Responda com 1 ou 2. Se não for nenhum dos dois, diga "outra coisa" e me explique de outro jeito.',
    ])


_ORDINAIS = {
    0: r"(?:1|um|uma|primeir[oa]|1o|1a)",
    1: r"(?:2|dois|duas|segund[oa]|2o|2a)",
}
# Uma escolha é uma frase CURTA e fechada: [verbo] [artigos/"opção"] número-ou-ordinal ["opção"].
# "segunda opção", "escolho a segunda", "fico com a segunda", "vou de 2", "pode ser a 1" valem;
# uma pergunta que apenas CONTÉM um número ("como usar a segunda lista em python") não.
_VERBO_ESCOLHA = (r"(?:(?:eu )?(?:escolho|escolha|fico com|fico|vou de|vou com|vou|vamos de|vamos com|quero|prefiro|"
                  r"opto por|seleciono|pode ser|manda|seria|e|eh|pelo|pela) )?")
_ARTIGOS_ESCOLHA = r"(?:(?:o|a|os|as|na|no|numero|item|opcao|alternativa) )*"
_SUFIXO_ESCOLHA = r"(?: (?:opcao|alternativa|item|mesmo|mesma|por favor|ai|entao))*"
_REJEICAO = re.compile(
    r"^(?:nenhum[a]?(?: d(?:e|el)[ae]s?| dos dois| das duas)?|nao|nao (?:e|era) isso|nao (?:e|era) nada disso|nada disso|"
    r"nem um nem (?:o )?outro|cancelar|esquece|deixa(?: pra la)?|nao quero|"
    r"nao e (?:nenhum|nenhuma)(?: d(?:e|el)[ae]s?| dos dois| das duas)?)$")
_CONFIRMACAO = re.compile(
    r"^(?:sim|isso|e isso|isso mesmo|exato|exatamente|certo|correto|pode ser|quero|claro|ok|"
    r"sim,? (?:e )?isso|sim,? quero|e (?:esse|isso mesmo))$")


def _limpo(texto: str) -> str:
    return re.sub(r"\s+", " ", re.sub(r"[^\w\s]", " ", remover_acentos(texto.lower()))).strip()


# Recusa dita numa frase curta ("na verdade é outra coisa", "prefiro outro assunto"): a expressão
# tem de FECHAR a frase, e uma pergunta ("como faço outra coisa com lista") nunca conta.
_RECUSA_NO_FIM = re.compile(r"(?:outra coisa|outro assunto|nada disso)(?: por favor| mesmo| obrigad[oa])?$")
_COMECA_PERGUNTA = re.compile(
    r"^(?:como|o que|oque|qual|quais|onde|quando|por que|porque|quem|quanto|quantos|quantas|para que|existe|"
    r"tem como|posso|pode|preciso|me ensina|me explica|explique|explica|ensine|ensina|mostra|mostre)"
    r"\b")


def _rejeita(resposta: str) -> bool:
    limpo = _limpo(resposta)
    if _REJEICAO.match(limpo):
        return True
    return bool(_RECUSA_NO_FIM.search(limpo)) and len(limpo.split()) <= 6 and not _COMECA_PERGUNTA.match(limpo)


_COMECA_COMO_PERGUNTA = re.compile(
    r"^(?:e )?(?:como|o que|oque|qual|quais|onde|quando|por que|porque|quem|quanto|quantos|quantas|para que|"
    r"existe|tem como|posso|preciso|me explica|me ensina|explique|explica|ensina|mostra|mostre)\b")


def _indice_escolhido(resposta: str, opcoes) -> int | None:
    """Qual opção a pessoa escolheu: número, ordinal, "sim" (só com uma opção) ou o nome."""
    limpo = _limpo(resposta)
    for indice in range(min(len(opcoes), len(_ORDINAIS))):        # só há ordinais para as 2 primeiras opções
        if re.match(rf"^{_VERBO_ESCOLHA}{_ARTIGOS_ESCOLHA}{_ORDINAIS[indice]}{_SUFIXO_ESCOLHA}$", limpo):
            return indice
    if len(opcoes) == 1 and _CONFIRMACAO.match(limpo):
        return 0
    # Pelo NOME: tira só UM prefixo curto de escolha ("escolho", "fico com a opção de", "quero o") e
    # um sufixo ("por favor", "mesmo"); o resto tem de caber no título de uma única opção. Uma
    # frase mais longa ou com palavras alheias ao título ("quero entender conjuntos em python")
    # continua sendo pergunta nova.
    prefixo = re.match(rf"^{_VERBO_ESCOLHA}{_ARTIGOS_ESCOLHA}", limpo)     # "de/do" sobram como stopwords
    resto = re.sub(rf"{_SUFIXO_ESCOLHA}$", "", limpo[prefixo.end():] if prefixo else limpo).strip()
    palavras = set(tokenizar(resto, STOPWORDS_BUSCA))
    # Um NOME é resposta curta; frase que COMEÇA como pergunta ("o que é uma lista") é pergunta nova, mesmo que
    # a palavra caiba no título da opção pendente (achado do Hypothesis).
    if palavras and len(resto.split()) <= 4 and not _COMECA_COMO_PERGUNTA.match(limpo):
        combinam = [i for i, (_, titulo) in enumerate(opcoes) if palavras <= _termos_do_titulo(titulo)]
        if len(combinam) == 1:
            return combinam[0]
    return None


def resolver_escolha_lembrada(bot, pedido):
    """Se esta MESMA pergunta já teve uma opção escolhida nesta sessão, responde direto."""
    ctx = bot.dialogo.contexto
    chave = ctx.escolhas.get(chave_consulta(pedido.texto or pedido.original))
    return _aplicar(bot, chave) if chave else None


def resolver_semantica(bot, pedido, apenas_pendente=False):
    ctx = bot.dialogo.contexto
    norm = pedido.normalizado.strip(" .?!")
    if norm in {"/semantica", "status semantica", "status da semantica"}:
        return bot.semantica.status(), "semantica"
    if ctx.opcoes_semanticas:
        opcoes = ctx.opcoes_semanticas
        consulta = ctx.consulta_opcoes
        ctx.opcoes_semanticas = []
        ctx.consulta_opcoes = ""
        resposta = pedido.original
        # 1) Recusa ("nenhuma", "não é isso", "outra coisa"): descarta as opções e LEMBRA que
        #    estas não serviram para essa pergunta, para não oferecê-las de novo.
        if _rejeita(resposta):
            ctx.reperguntas = 0
            if consulta:
                ctx.rejeitadas.setdefault(consulta, set()).update(chave for chave, _ in opcoes)
            return ("Tudo bem, então não era isso. Me explica de outro jeito o que você quer saber ou fazer "
                    'ou peça "pesquisa isso na internet".'), "esclarecimento"
        # 2) Escolha (número, ordinal, nome; "sim" quando só havia uma opção).
        indice = _indice_escolhido(resposta, opcoes)
        if indice is not None:
            ctx.reperguntas = 0
            escolha = opcoes[indice][0]
            resultado = _aplicar(bot, escolha)
            if resultado is not None and consulta:
                ctx.escolhas[consulta] = escolha          # não perguntar de novo, nesta sessão
            return resultado
        # 3) "Sim" com DUAS opções não diz qual: pergunta de novo, uma vez só.
        if len(opcoes) > 1 and _CONFIRMACAO.match(_limpo(resposta)) and ctx.reperguntas < 1:
            ctx.reperguntas += 1
            ctx.opcoes_semanticas = opcoes
            ctx.consulta_opcoes = consulta
            return (f"Você me deixou na dúvida: é o 1 ({opcoes[0][1]}) ou o 2 ({opcoes[1][1]})?"), "esclarecimento"
        # 4) Qualquer outra coisa é uma pergunta NOVA: as opções já foram descartadas acima e a
        #    mensagem segue os fluxos normais; não é resposta forçada.
        ctx.reperguntas = 0
    if apenas_pendente:
        return None
    if (pedido.codigo or "`" in pedido.original or pedido.acoes & {"gerar", "alterar"}
            or re.search(r"\b(nao|nunca|sem|execute|executar|roda|rodar|salva|salvar|apague|deletar|pesquise|pesquisa|aprenda)\b", norm)
            or norm.startswith("/") or len(norm.split()) < 3
            or bot.dialogo.briefing.estado == "coletando"):
        return None
    # As respostas lexicais já conhecidas mantêm prioridade.
    if bot.base.buscar(pedido.texto) is not None:
        return None
    candidatos = bot.semantica.comparar(pedido.texto, bot.base.entradas)
    decisao = decidir(candidatos)
    if decisao == "aceito":
        return _aplicar(bot, candidatos[0].chave, pedido.original)
    if decisao == "esclarecer":
        consulta = chave_consulta(pedido.texto or pedido.original)
        recusadas = ctx.rejeitadas.get(consulta, set())
        opcoes = [(chave, titulo) for chave, titulo, _ in opcoes_distintas(
            [(c.chave, c.titulo, c.similaridade) for c in candidatos[:2]
             if c.chave != "fora" and c.chave not in recusadas])]
        if not opcoes:
            return None
        ctx.opcoes_semanticas = opcoes
        ctx.consulta_opcoes = consulta
        return montar_pergunta_de_esclarecimento(opcoes), "esclarecimento"
    return None
