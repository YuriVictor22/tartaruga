"""
Base de conhecimento de programação com busca por similaridade.

Depois que o classificador decide que o usuário tem uma DÚVIDA DE
PROGRAMAÇÃO, é este módulo que encontra a resposta.

A técnica é recuperação de informação: cada pergunta conhecida vira um vetor
TF-IDF (reaproveitando `vetorizador.py`), a pergunta do usuário também vira
um vetor, e comparamos todos por similaridade de cosseno. A entrada mais
próxima ganha.

Detalhe importante do projeto: se a melhor similaridade ficar abaixo de um
limiar, o sistema NÃO responde qualquer coisa - ele admite que não sabe e
oferece buscar na web. Um assistente que inventa resposta é pior que um que
reconhece o próprio limite.
"""

import json
import re
from dataclasses import dataclass
from pathlib import Path

from .caminhos import gravavel, recurso
from .sinonimos import MINIMO_AMBIGUOS, SINONIMOS, expandir, sinal_tecnico, termos_ambiguos, tokens_do_sinal
from .vetorizador import STOPWORDS_BUSCA, Vetorizador, similaridade_cosseno, tokenizar

# Base curada, escrita à mão: somente leitura, embutida no executável.
CAMINHO_PADRAO = recurso("dados", "conhecimento.json")

# Base aprendida por pesquisa: gravável, fica ao lado do executável.
# Os dois arquivos são separados de propósito. O conhecimento escrito à mão
# foi revisado por uma pessoa; o aprendido veio de uma página da internet e
# ninguém conferiu. Misturá-los apagaria essa diferença - e é justamente ela
# que permite à Tartaruga dizer de onde veio cada resposta.
CAMINHO_APRENDIDO = gravavel("dados_aprendidos.json")

# ---------------------------------------------------------------------------
# Os dois critérios para aceitar uma resposta
#
# O limiar começou em 0,25 e deixava passar falsos positivos graves:
# "o que é currying em javascript" era respondido com o tópico sobre `this`,
# só porque as duas frases tinham a palavra "javascript".
#
# A causa é geométrica. Quando quase todos os termos da pergunta são
# desconhecidos, o vetor resulta praticamente de UM termo - e aí a
# similaridade com qualquer entrada que contenha esse termo dispara. Um
# número alto não significava match bom; significava pergunta mal coberta.
#
# Daí o segundo critério, COBERTURA: que fração dos termos da pergunta o
# sistema reconheceu. A medição que definiu os valores abaixo:
#
#     respostas corretas : similaridade 0,79-1,00 | cobertura 0,50-1,00
#     falsos positivos   : similaridade 0,50-0,78 | cobertura 0,33-0,75
#
# Exigir os dois separa quase perfeitamente os dois grupos. Nenhum dos
# critérios sozinho separa.
#
# É melhor admitir ignorância do que responder com confiança sobre o que não
# se sabe - especialmente para quem está aprendendo e não tem como
# desconfiar da resposta.
# ---------------------------------------------------------------------------
LIMIAR_PADRAO = 0.75
COBERTURA_MINIMA = 0.5

# Abaixo do limiar de resposta direta, mas acima deste, a base tem um palpite
# plausível: em vez de "não entendi", a Tartaruga OFERECE o assunto e deixa a
# pessoa confirmar (ver `sugerir`).
LIMIAR_SUGESTAO = 0.35

# Com sinal técnico só COMBINADO (dois conceitos ambíguos, sem sintaxe/tecnologia),
# a oferta é mais exigente e usa a similaridade ponderada pela cobertura.
LIMIAR_SUGESTAO_COMBINADO = 0.45

# Mesmo com sinal técnico FORTE, uma entrada só é candidata se explica pelo menos
# esta fração das palavras DISTINTAS da pergunta (ver `_evidencia`): uma palavra
# isolada ("dom" de Dom Pedro, "len" de câmera) não basta.
EVIDENCIA_MINIMA_FORTE = 0.5

# Uma OFERTA (sugestão) precisa que a entrada explique pelo menos tantas palavras
# DISTINTAS da pergunta. Quando as stopwords deixam um só termo ("Qual é o dom?"),
# a evidência seria 1/1 por definição e não distingue "dom" técnico de "dom" comum:
# um termo isolado só pode ser RESPONDIDO por casamento direto forte, nunca oferecido.
MINIMO_TERMOS_OFERTA = 2


@dataclass
class _IndiceCurado:
    """Índice vetorial só das entradas curadas (ver `BaseConhecimento.sugerir`)."""

    vetorizador: Vetorizador
    vetores: list[dict[str, float]]
    indice_entrada: list[int]
    termos_por_entrada: dict[int, set[str]]


@dataclass
class Resultado:
    """Uma entrada da base junto com o quanto ela combinou com a pergunta."""

    identificador: str
    titulo: str
    resposta: str
    codigo: str
    similaridade: float

    # Procedência. Conteúdo aprendido na web é sempre exibido com a fonte,
    # para que quem lê possa conferir - ninguém revisou aquilo.
    aprendido: bool = False
    fonte_dominio: str = ""
    fonte_url: str = ""


class BaseConhecimento:
    """Carrega a base local e responde perguntas por similaridade.

    Uso:
        base = BaseConhecimento()
        resultado = base.buscar("como faco um laco for")
        if resultado:
            print(resultado.resposta)
    """

    def __init__(
        self,
        caminho: Path | None = None,
        caminho_aprendido: Path | None = None,
    ) -> None:
        self.caminho = caminho or CAMINHO_PADRAO
        self.caminho_aprendido = caminho_aprendido or CAMINHO_APRENDIDO
        self.entradas: list[dict] = []

        # STOPWORDS_BUSCA descarta também as palavras interrogativas: aqui
        # interessa o ASSUNTO da pergunta, não o formato dela. Sem isso,
        # perguntas com a mesma estrutura ("me explica o que é X") casavam
        # entre si independentemente do tema.
        self.vetorizador = Vetorizador(stopwords=STOPWORDS_BUSCA)

        # Para cada documento indexado, de qual entrada ele veio.
        # Indexamos cada variação da pergunta separadamente (em vez de juntar
        # tudo num texto só) porque assim cada formulação é comparada por si,
        # o que dá um casamento bem mais preciso.
        self._indice_entrada: list[int] = []
        self._vetores: list[dict[str, float]] = []

        # Palavras que as perguntas de cada entrada realmente usam. Serve de
        # âncora: ver `buscar_varios`.
        self._termos_por_entrada: list[set[str]] = []

        # Índice SÓ da base curada (sem o conteúdo aprendido). As SUGESTÕES são
        # decididas nele: o IDF e as notas das sugestões não podem depender do
        # que o usuário aprendeu na internet.
        self._curado: _IndiceCurado | None = None

        self.carregar()

    def carregar(self) -> None:
        """Lê as duas bases (curada e aprendida) e constrói o índice vetorial."""
        if not self.caminho.exists():
            raise FileNotFoundError(
                f"Base de conhecimento não encontrada em: {self.caminho}"
            )

        with open(self.caminho, encoding="utf-8") as arquivo:
            self.entradas = json.load(arquivo)

        # O conhecimento aprendido entra no MESMO índice, para que uma
        # pergunta encontre a melhor resposta venha ela de onde vier. A
        # distinção de procedência é preservada em cada entrada, não na
        # estrutura de busca.
        if self.caminho_aprendido.exists():
            try:
                with open(self.caminho_aprendido, encoding="utf-8") as arquivo:
                    aprendidas = json.load(arquivo)
                conhecidos = {e["id"] for e in self.entradas}
                self.entradas.extend(
                    e for e in aprendidas
                    if e.get("id") not in conhecidos and e.get("ativa", True)
                )
            except (json.JSONDecodeError, OSError, KeyError, TypeError):
                # Arquivo corrompido não pode impedir o assistente de abrir:
                # o conhecimento curado continua disponível.
                pass

        documentos: list[str] = []
        self._indice_entrada = []
        self._termos_por_entrada = []

        for posicao, entrada in enumerate(self.entradas):
            termos: set[str] = set()
            for variacao in entrada["perguntas"]:
                documentos.append(variacao)
                self._indice_entrada.append(posicao)
                termos.update(tokenizar(variacao, STOPWORDS_BUSCA))
            self._termos_por_entrada.append(termos)

        if not documentos:
            raise ValueError("A base de conhecimento está vazia.")

        self._vetores = self.vetorizador.ajustar_transformar(documentos)
        self._curado = self._montar_indice_curado()

    def _montar_indice_curado(self) -> "_IndiceCurado":
        """Reindexa só as entradas curadas, com IDF calculado só sobre elas."""
        vetorizador = Vetorizador(stopwords=STOPWORDS_BUSCA)
        documentos: list[str] = []
        indice_entrada: list[int] = []
        termos_por_entrada: dict[int, set[str]] = {}
        for posicao, entrada in enumerate(self.entradas):
            if entrada.get("aprendido"):
                continue
            termos: set[str] = set()
            for variacao in entrada["perguntas"]:
                documentos.append(variacao)
                indice_entrada.append(posicao)
                termos.update(tokenizar(variacao, STOPWORDS_BUSCA))
            termos_por_entrada[posicao] = termos
        vetores = vetorizador.ajustar_transformar(documentos) if documentos else []
        return _IndiceCurado(vetorizador, vetores, indice_entrada, termos_por_entrada)

    def buscar(self, pergunta: str, limiar: float = LIMIAR_PADRAO) -> Resultado | None:
        """Devolve a melhor resposta, ou None se nada for suficientemente parecido."""
        # Com sinal técnico FORTE escrito pela pessoa (python, for, append...),
        # vale a similaridade de sempre. Sem ele - inclusive quando só há termos
        # conceituais ambíguos ("função", "classe") - palavras que a base não
        # conhece pesam contra: só uma pergunta quase toda reconhecida passa
        # como resposta direta.
        sinal = sinal_tecnico(tokens_do_sinal(tokenizar(pergunta, self.vetorizador.stopwords), pergunta))
        # Só conceitos ambíguos combinados ("classe" + "programa"): a resposta
        # precisa vir de uma entrada que contenha AO MENOS DOIS deles (a combinação
        # tem de fazer sentido junta), não de uma que case com um só.
        corroborar = termos_ambiguos(tokenizar(pergunta, self.vetorizador.stopwords)) if sinal == "combinado" else None
        ponderar = sinal != "forte"
        evidencia = EVIDENCIA_MINIMA_FORTE if sinal == "forte" else 0.0
        # O conteúdo CURADO é decidido no índice só da base curada (o que o usuário
        # aprendeu na internet mexe no IDF e não pode mudar essa decisão); o
        # aprendido concorre a partir do índice completo.
        melhores = self.buscar_varios(
            pergunta, quantidade=1, limiar=limiar, ponderar_cobertura=ponderar,
            corroborar=corroborar, apenas_curado=True, evidencia_minima=evidencia,
        )
        aprendidos = [
            r for r in self.buscar_varios(
                pergunta, quantidade=len(self.entradas), limiar=limiar,
                ponderar_cobertura=ponderar, corroborar=corroborar, evidencia_minima=evidencia,
            ) if r.aprendido
        ]
        candidatos = melhores + aprendidos[:1]
        return max(candidatos, key=lambda r: r.similaridade) if candidatos else None

    def buscar_varios(
        self,
        pergunta: str,
        quantidade: int = 3,
        limiar: float = LIMIAR_PADRAO,
        ponderar_cobertura: bool = False,
        corroborar: set[str] | None = None,
        apenas_curado: bool = False,
        evidencia_minima: float = 0.0,
        termos_minimos: int = 0,
    ) -> list[Resultado]:
        """Devolve as melhores entradas acima do limiar, da mais para a menos parecida.

        `ponderar_cobertura=True` é usado por `buscar` quando a pergunta não traz
        nenhum termo técnico: a similaridade é multiplicada pela cobertura da pergunta, então palavras
        desconhecidas (as do dia a dia: "convidados", "despensa") derrubam a
        nota em vez de sumir sem deixar rastro. Para sugestões (que exigem contexto técnico escrito
        pela pessoa) a similaridade é a bruta.

        Com `ponderar_cobertura`, a nota é multiplicada pela EVIDÊNCIA DA ENTRADA
        (ver `_evidencia`): a fração das palavras DISTINTAS da pergunta que aquela
        entrada explica. `evidencia_minima` descarta a entrada abaixo dessa fração.
        Repetir uma palavra não aumenta a evidência e vocabulário que só outras
        entradas conhecem não ajuda a candidata.

        `corroborar`: conceitos ambíguos escritos pela pessoa; a entrada só vale se
        AO MENOS `MINIMO_AMBIGUOS` deles aparecem nas perguntas dela.
        `apenas_curado`: usa o índice só da base curada (IDF sem o aprendido).
        """
        if apenas_curado:
            vetorizador, vetores = self._curado.vetorizador, self._curado.vetores
            indice_entrada, termos_por_entrada = self._curado.indice_entrada, self._curado.termos_por_entrada
        else:
            vetorizador, vetores = self.vetorizador, self._vetores
            indice_entrada = self._indice_entrada
            termos_por_entrada = dict(enumerate(self._termos_por_entrada))

        vetor_pergunta = vetorizador.transformar(self._consulta(pergunta))
        if not vetor_pergunta:
            return []
        # "python" é o CONTEXTO da base curada (as entradas sem prefixo são todas de Python): em "o que é uma lista
        # em python" a palavra não faz parte do assunto e não pode derrubar a similaridade de "Listas".
        sem_python = re.sub(r"\bpython\b", " ", pergunta, flags=re.IGNORECASE)
        vetor_sem_python = None
        if sem_python != pergunta:
            vetor_sem_python = vetorizador.transformar(self._consulta(sem_python))

        # Se reconhecemos poucos termos da pergunta, a similaridade calculada
        # é sobre um fragmento dela - e não representa a pergunta inteira.
        # "<=", não "<": a mesma armadilha de limite encontrada depois em
        # `nucleo.py::COBERTURA_MINIMA_INTENCAO` - frases curtas batendo
        # EXATAMENTE na metade reconhecida passavam pela checagem por causa
        # do operador estrito.
        if self.cobertura(pergunta, vetorizador) <= COBERTURA_MINIMA:
            return []

        # Melhor similaridade encontrada para cada entrada. Como uma mesma
        # entrada tem várias variações indexadas, guardamos só a maior - caso
        # contrário a mesma resposta apareceria repetida na lista.
        melhor_por_entrada: dict[int, float] = {}
        for posicao_documento, vetor in enumerate(vetores):
            similaridade = similaridade_cosseno(vetor_pergunta, vetor)
            if vetor_sem_python:
                # 0,98: quem escreveu "python" na pergunta ainda favorece quem também escreve "python"
                similaridade = max(similaridade, 0.98 * similaridade_cosseno(vetor_sem_python, vetor))
            posicao_entrada = indice_entrada[posicao_documento]
            if similaridade > melhor_por_entrada.get(posicao_entrada, 0.0):
                melhor_por_entrada[posicao_entrada] = similaridade

        ordenadas = sorted(
            melhor_por_entrada.items(),
            key=lambda item: item[1],
            reverse=True,
        )

        # Âncora: a expansão por sinônimos só REFORÇA um assunto que a pessoa
        # já tocou com palavras dela. Se nenhuma palavra digitada aparece nas
        # perguntas da entrada, o casamento veio só do sinônimo ("proteger
        # minha casa" -> try/except) e não vale nem como palpite.
        digitadas = set(tokenizar(pergunta, vetorizador.stopwords))
        ordenadas = [
            (posicao, sim) for posicao, sim in ordenadas
            if digitadas & termos_por_entrada[posicao]
        ]
        if corroborar is not None:
            ordenadas = [
                (posicao, sim) for posicao, sim in ordenadas
                if len(corroborar & termos_por_entrada[posicao]) >= MINIMO_AMBIGUOS
            ]

        # Palavras da pergunta que a base NÃO conhece somem do vetor e não baixam
        # a similaridade: "organizar uma lista de convidados" ficava idêntica a
        # "ordenar lista". Na resposta direta, a similaridade é ponderada pela
        # fração de palavras reconhecidas (`cobertura`).
        if ponderar_cobertura or evidencia_minima > 0 or termos_minimos:
            distintas = set(tokenizar(pergunta, vetorizador.stopwords))
            evidencias = {posicao: self._evidencia(distintas, termos_por_entrada[posicao]) for posicao, _ in ordenadas}
            ordenadas = [(posicao, sim) for posicao, sim in ordenadas if evidencias[posicao] >= evidencia_minima]
            if termos_minimos and len(distintas) < termos_minimos:
                ordenadas = []      # termos distintos demais poucos: a evidência 1/1 não prova domínio
            if ponderar_cobertura:
                ordenadas = [(posicao, sim * evidencias[posicao]) for posicao, sim in ordenadas]

        resultados: list[Resultado] = []
        for posicao_entrada, similaridade in ordenadas[:quantidade]:
            if similaridade < limiar:
                break
            entrada = self.entradas[posicao_entrada]
            resultados.append(
                Resultado(
                    identificador=entrada["id"],
                    titulo=entrada["titulo"],
                    resposta=entrada["resposta"],
                    codigo=entrada.get("codigo", ""),
                    similaridade=similaridade,
                    aprendido=entrada.get("aprendido", False),
                    fonte_dominio=entrada.get("fonte_dominio", ""),
                    fonte_url=entrada.get("fonte_url", ""),
                )
            )

        return resultados

    @staticmethod
    def _evidencia(distintas: set[str], termos_entrada: set[str]) -> float:
        """Fração das palavras DISTINTAS da pergunta explicadas por UMA entrada.

        Uma palavra é explicada se aparece nas perguntas da entrada ou se um sinônimo
        de domínio dela aparece. Conta termos distintos (repetir "dom" não soma) e só
        o vocabulário DA ENTRADA candidata (palavras que outras entradas conhecem não
        ajudam), ao contrário da `cobertura`, que é global.
        """
        if not distintas:
            return 0.0
        explicadas = sum(
            1 for t in distintas
            if t in termos_entrada or any(s in termos_entrada for s in SINONIMOS.get(t, ()))
        )
        return explicadas / len(distintas)

    def _consulta(self, pergunta: str) -> str:
        """A pergunta acrescida dos termos que a base usa para as mesmas ideias."""
        extras = expandir(tokenizar(pergunta, self.vetorizador.stopwords))
        return f"{pergunta} {' '.join(extras)}" if extras else pergunta

    def sugerir(self, pergunta: str, quantidade: int = 2) -> list[Resultado]:
        """Assuntos plausíveis quando nenhum passa do limiar de resposta direta.

        Só entra conteúdo REVISADO (curado): o aprendido da internet não é
        oferecido como palpite. Devolve vazio fora do domínio da base (a
        checagem de cobertura de `buscar_varios` continua valendo).
        """
        # Oferta de assunto técnico exige contexto técnico ESCRITO pela pessoa.
        # Sinal FORTE (python, for, append...) basta e usa a similaridade bruta;
        # só COMBINADO (dois conceitos ambíguos) exige mais: similaridade
        # ponderada pela cobertura e limiar maior. Palavras do dia a dia
        # ("lista", "arquivo", "item") e sinônimos nunca contam.
        sinal = sinal_tecnico(tokens_do_sinal(tokenizar(pergunta, self.vetorizador.stopwords), pergunta))
        if sinal not in ("forte", "combinado"):      # nenhum ou só um polissêmico ("print", "string")
            return []
        combinado = sinal == "combinado"
        # A decisão é tomada no índice SÓ da base curada, e a combinação de
        # conceitos ambíguos precisa ser corroborada por uma entrada que contenha
        # dois deles: "classe" + "programa" de televisão não fecha com nenhuma.
        candidatos = self.buscar_varios(
            pergunta, quantidade=quantidade + 3,
            limiar=LIMIAR_SUGESTAO_COMBINADO if combinado else LIMIAR_SUGESTAO,
            ponderar_cobertura=True,             # nenhuma palavra isolada dispensa a evidência da entrada
            evidencia_minima=EVIDENCIA_MINIMA_FORTE if not combinado else 0.0,
            termos_minimos=MINIMO_TERMOS_OFERTA,
            corroborar=termos_ambiguos(tokenizar(pergunta, self.vetorizador.stopwords)) if combinado else None,
            apenas_curado=True,
        )
        return [c for c in candidatos if not c.aprendido][:quantidade]

    def recarregar(self) -> None:
        """Reconstrói o índice. Chamado depois de aprender algo novo.

        Necessário porque o IDF depende do conjunto INTEIRO de documentos:
        acrescentar uma entrada muda o peso das palavras em todas as outras.
        Não dá para indexar a nova isoladamente.
        """
        self.vetorizador = Vetorizador(stopwords=STOPWORDS_BUSCA)
        self.carregar()

    def cobertura(self, pergunta: str, vetorizador: Vetorizador | None = None) -> float:
        """Fração dos termos da pergunta que existem no vocabulário da base.

        Cobertura 1,0 significa que entendemos todas as palavras relevantes
        da pergunta. Cobertura 0,33 significa que respondemos olhando para um
        terço dela — e é aí que nascem os falsos positivos.
        """
        vetorizador = vetorizador or self.vetorizador
        tokens = tokenizar(pergunta, vetorizador.stopwords)
        if not tokens:
            return 0.0
        # Um sinônimo de domínio conta como reconhecido quando o termo que a
        # base usa para o mesmo conceito existe no vocabulário.
        reconhecidos = sum(
            1 for t in tokens
            if t in vetorizador.idf
            or any(s in vetorizador.idf for s in SINONIMOS.get(t, ()))
        )
        return reconhecidos / len(tokens)

    def relacionados(self, identificador: str, quantidade: int = 2) -> list[Resultado]:
        """Entradas mais parecidas com a informada, para sugerir continuidade.

        Nenhuma ligação entre assuntos foi escrita à mão: a proximidade é
        calculada pela mesma similaridade de cosseno usada na busca. Depois
        de explicar "Laço for", as entradas mais próximas no espaço vetorial
        são naturalmente "Laço while" e "Laços aninhados".

        É de graça - reaproveita o índice que já existe - e acompanha
        automaticamente qualquer assunto novo acrescentado à base.
        """
        posicao = next(
            (p for p, e in enumerate(self.entradas) if e["id"] == identificador),
            None,
        )
        if posicao is None:
            return []

        # Usamos todas as formulações da entrada como consulta, para que a
        # comparação represente o assunto inteiro e não uma frase só.
        consulta = " ".join(self.entradas[posicao]["perguntas"])

        # Limiar mais baixo que o da busca: aqui não estamos respondendo, só
        # sugerindo - um palpite fraco custa pouco.
        candidatos = self.buscar_varios(consulta, quantidade + 1, limiar=0.10)
        return [r for r in candidatos if r.identificador != identificador][:quantidade]

    def __len__(self) -> int:
        return len(self.entradas)
