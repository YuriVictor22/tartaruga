"""
Classificador Naive Bayes Multinomial implementado do zero.

Esta é a parte do projeto que realmente APRENDE. Damos a ele uma lista de
frases já rotuladas ("quero rodar esse código" -> executar_codigo) e ele
descobre sozinho quais palavras indicam cada intenção. Depois, diante de uma
frase nova, responde qual é a intenção mais provável.

---------------------------------------------------------------------------
A matemática
---------------------------------------------------------------------------
Queremos a classe `c` mais provável dada a frase. Pelo Teorema de Bayes:

    P(c | frase) = P(frase | c) * P(c) / P(frase)

Como P(frase) é o mesmo para todas as classes, ele não muda qual é a maior
e pode ser descartado na comparação:

    P(c | frase)  ∝  P(c) * P(frase | c)

A parte "Naive" (ingênua) do nome é a simplificação de assumir que as
palavras são independentes entre si. Isso é falso na prática ("laço" e "for"
andam juntos), mas funciona surpreendentemente bem e torna o cálculo viável:

    P(frase | c) = P(palavra_1 | c) * P(palavra_2 | c) * ...

Dois cuidados de implementação:

1. LOGARITMOS. Multiplicar dezenas de probabilidades pequenas leva o número
   a zero por limite de precisão do computador (underflow). Somando os
   logaritmos chegamos ao mesmo ranking sem esse risco:

       log(a * b) = log(a) + log(b)

2. SUAVIZAÇÃO DE LAPLACE. Se uma palavra nunca apareceu numa classe durante
   o treino, sua probabilidade seria 0 e zeraria o produto inteiro - uma
   única palavra desconhecida vetaria a classe. Somamos `alfa` (por padrão 1)
   a toda contagem para que nenhuma probabilidade seja exatamente zero.

Nenhuma biblioteca externa é usada.
"""

import math

from .vetorizador import INTERROGATIVAS, tokenizar


class ClassificadorNaiveBayes:
    """Aprende a associar frases a intenções.

    Uso:
        c = ClassificadorNaiveBayes()
        c.treinar(["oi", "bom dia", "rode esse codigo"],
                  ["saudacao", "saudacao", "executar_codigo"])
        intencao, confianca = c.prever("ola")
    """

    def __init__(self, alfa: float = 1.0, atributos: str = "palavras") -> None:
        # alfa é o parâmetro da suavização de Laplace. 1.0 é o valor clássico.
        self.alfa = alfa
        if atributos not in ("palavras", "bigramas", "caracteres"):
            raise ValueError("Atributos devem ser palavras, bigramas ou caracteres.")
        self.atributos = atributos

        self.classes: list[str] = []
        self.vocabulario: set[str] = set()

        # log P(classe) - o quanto cada intenção é comum, antes de ver a frase
        self.log_prior: dict[str, float] = {}

        # log P(palavra | classe) - o quanto cada palavra "puxa" para cada classe
        self.log_verossimilhanca: dict[str, dict[str, float]] = {}

        # log P(palavra desconhecida naquela classe | classe)
        # Vale para palavras que estão no vocabulário geral mas nunca
        # apareceram naquela classe específica.
        self.log_padrao: dict[str, float] = {}

        # Quanto cada palavra do vocabulário AJUDA a distinguir uma classe
        # da outra - ver `_calcular_pesos_palavras`. Usado por
        # `cobertura_ponderada`, não pela previsão em si.
        self.pesos_palavras: dict[str, float] = {}

        self.treinado: bool = False

    def _atributos(self, texto: str) -> list[str]:
        palavras = tokenizar(texto)
        if self.atributos == "palavras":
            return palavras
        if self.atributos == "bigramas":
            return palavras + [f"@b:{a}/{b}" for a, b in zip(palavras, palavras[1:])]
        caracteres = [f"@c:{p[i:i + 3]}" for p in palavras if len(p) >= 5 for i in range(len(p) - 2)]
        return palavras + caracteres

    def treinar(self, textos: list[str], rotulos: list[str]) -> "ClassificadorNaiveBayes":
        """Aprende a partir de exemplos já rotulados.

        `textos[i]` é uma frase e `rotulos[i]` é a intenção correspondente.
        """
        if len(textos) != len(rotulos):
            raise ValueError("textos e rotulos precisam ter o mesmo tamanho.")
        if not textos:
            raise ValueError("É preciso ao menos um exemplo para treinar.")

        self.classes = sorted(set(rotulos))
        # Um novo treino substitui o anterior, inclusive seu vocabulário.
        self.vocabulario.clear()
        self.log_prior.clear()
        self.log_verossimilhanca.clear()
        self.log_padrao.clear()
        total_documentos = len(textos)

        # Contagem de documentos e de palavras por classe.
        documentos_por_classe: dict[str, int] = {c: 0 for c in self.classes}
        contagem_palavras: dict[str, dict[str, int]] = {c: {} for c in self.classes}
        total_palavras_classe: dict[str, int] = {c: 0 for c in self.classes}

        for texto, rotulo in zip(textos, rotulos):
            documentos_por_classe[rotulo] += 1
            for token in self._atributos(texto):
                self.vocabulario.add(token)
                contagem_palavras[rotulo][token] = contagem_palavras[rotulo].get(token, 0) + 1
                total_palavras_classe[rotulo] += 1

        tamanho_vocabulario = len(self.vocabulario)

        for classe in self.classes:
            # P(classe): proporção de exemplos daquela intenção no treino.
            self.log_prior[classe] = math.log(
                documentos_por_classe[classe] / total_documentos
            )

            # Denominador da suavização: total de palavras da classe mais
            # alfa por cada palavra possível do vocabulário.
            denominador = total_palavras_classe[classe] + self.alfa * tamanho_vocabulario

            self.log_verossimilhanca[classe] = {
                termo: math.log((quantidade + self.alfa) / denominador)
                for termo, quantidade in contagem_palavras[classe].items()
            }

            # Palavra conhecida, mas com contagem zero nesta classe.
            self.log_padrao[classe] = math.log(self.alfa / denominador)

        self._calcular_pesos_palavras()
        self.treinado = True
        return self

    def _calcular_pesos_palavras(self) -> None:
        """Mede o quanto cada palavra do vocabulário distingue uma classe da outra.

        Motivação (bug real, ver README): "quem foi Pelé" e "o que é
        stacking context em css" reconheciam a MESMA fração de palavras
        (2 de 3, 2 de 4) - mas num caso as palavras reconhecidas eram
        conectivos genéricos ("quem", "foi", presentes em quase toda
        classe), e no outro era uma palavra que só aparece em contextos de
        programação ("css"). Contar palavra por palavra, como
        `tokens_reconhecidos` faz, não enxerga essa diferença - as duas
        contam "1 palavra reconhecida" do mesmo jeito.

        A ideia, na prática: em quantas classes DISTINTAS a palavra aparece
        pelo menos uma vez? Uma palavra genérica ("que", "como") aparece em
        quase todas as 15 classes; uma palavra de assunto ("css",
        "debounce") aparece só numa ou duas. Isso é a mesma lógica do IDF
        já usado em `vetorizador.py` pra busca na base (`log((1+N)/(1+df))
        + 1`) - só que aqui "documento" é "classe de intenção", não
        "entrada da base de conhecimento". Reaproveitamos a fórmula.

        TENTATIVA ANTERIOR, DESCARTADA: usar a variação de
        `log_verossimilhanca` entre classes (máximo menos mínimo) parecia
        mais direto, mas se mostrou distorcida pelo TAMANHO da classe - uma
        classe pequena infla a proporção de qualquer palavra que apareça
        nela poucas vezes, mesmo palavras comuns. Um teste real expôs isso:
        "race" (de "Promise.race", 1 único exemplo de treino) ganhou peso
        BAIXO (0,20) por aquela conta, quando deveria ser um dos pesos mais
        ALTOS do vocabulário - aparece numa classe só, é exatamente o caso
        que o peso deveria destacar. Contar em quantas classes a palavra
        aparece, em vez de comparar a magnitude do log, não sofre desse
        problema: não importa quantas vezes "race" apareceu, importa que
        apareceu numa classe só.

        SEGUNDA DISTORÇÃO, TAMBÉM ENCONTRADA TESTANDO: por essa mesma conta
        de "em quantas classes aparece", a palavra "quem" ficou com peso
        MÁXIMO (1,0) - porque, na base de treino atual, ela só aparece
        mesmo em exemplos de `sobre_projeto` ("quem te criou", "quem fez
        você"). Estatisticamente ela É concentrada; na prática, "quem" é um
        pronome interrogativo de uso universal em português ("quem foi
        Pelé", "quem descobriu o Brasil") - a concentração é um artefato de
        a base de treino ter poucos jeitos de perguntar sobre a própria
        Tartaruga, não um sinal real de que "quem" é sobre a Tartaruga.
        Isso é exatamente o bug documentado no README sobre "quem descobriu
        o brasil" - e o peso estatístico, sozinho, reproduziria o mesmo
        erro. Nenhuma conta feita só a partir da base de treino atual
        resolveria isso sozinha, porque o problema É a base ser pequena
        demais pra "quem" aparecer nos outros contextos onde ele também é
        usado. A correção usa conhecimento linguístico que já existe no
        projeto: `vetorizador.INTERROGATIVAS` já documenta esse grupo de
        palavras ("que", "quem", "como", "qual", "faz"...) como palavras
        que "montam a pergunta sem dizer nada sobre o assunto dela" - a
        mesma propriedade que este peso precisa capturar. Forçamos peso
        zero pra elas, por cima do valor estatístico.

        Normalizamos o restante pelo maior valor observado no vocabulário
        treinado, pra manter o peso sempre entre 0 e 1.
        """
        n_classes = len(self.classes)
        pesos_brutos: dict[str, float] = {}
        for termo in self.vocabulario:
            classes_com_termo = sum(1 for classe in self.classes if termo in self.log_verossimilhanca[classe])
            pesos_brutos[termo] = math.log((1 + n_classes) / (1 + classes_com_termo)) + 1

        maior_peso = max(pesos_brutos.values(), default=0.0)
        menor_peso = min(pesos_brutos.values(), default=0.0)
        amplitude = maior_peso - menor_peso
        if amplitude <= 0:
            # Vocabulário degenerado (ex.: uma classe só) - todo peso igual.
            self.pesos_palavras = {termo: 1.0 for termo in self.vocabulario}
        else:
            self.pesos_palavras = {
                termo: (peso - menor_peso) / amplitude for termo, peso in pesos_brutos.items()
            }

        for termo in INTERROGATIVAS:
            if termo in self.pesos_palavras:
                self.pesos_palavras[termo] = 0.0

    def cobertura_ponderada(self, texto: str) -> float:
        """Fração do PESO INFORMATIVO da frase que o classificador reconhece.

        Substitui a ideia de "quantas palavras eu já vi" (que trata "quem"
        e "css" como equivalentes) por "quanto do que torna esta frase
        distinguível eu já vi". Uma palavra fora do vocabulário (nunca
        apareceu em nenhum exemplo de treino) recebe o peso máximo (1.0)
        no denominador - não sabemos o quão importante ela seria, e tratar
        o desconhecido como potencialmente decisivo é o lado mais seguro
        do erro, na mesma linha do resto do projeto (recusa honesta em vez
        de confiança injustificada).

        Devolve 0.0 para texto vazio ou só stopwords/pontuação (tokenizar
        devolve lista vazia) - o núcleo trata isso como cobertura nula.
        """
        tokens = tokenizar(texto)
        if not tokens:
            return 0.0

        pesos_totais = [self.pesos_palavras.get(t, 1.0) for t in tokens]
        pesos_reconhecidos = [self.pesos_palavras[t] for t in tokens if t in self.vocabulario]

        total = sum(pesos_totais)
        if total == 0:
            # Só palavras reconhecidas com peso 0 (nenhuma discrimina nada)
            # - cobertura "completa" sobre uma frase sem sinal nenhum não
            # faria sentido; melhor sinalizar incerteza.
            return 0.0
        return sum(pesos_reconhecidos) / total

    def tokens_reconhecidos(self, texto: str) -> list[str]:
        """Palavras da frase que o modelo viu durante o treino.

        Se esta lista vier vazia, o modelo não tem NENHUMA evidência sobre a
        frase - e isso precisa ser tratado explicitamente (ver `prever`).
        """
        return [t for t in tokenizar(texto) if t in self.vocabulario]

    def pontuar(self, texto: str) -> dict[str, float]:
        """Calcula o log-score de cada classe para a frase.

        São log-probabilidades não normalizadas: servem para comparar as
        classes entre si, não como probabilidade absoluta.
        """
        if not self.treinado:
            raise RuntimeError("O classificador precisa ser treinado antes de prever.")

        # Só consideramos palavras vistas no treino. Uma palavra inédita não
        # traz informação: contribuiria igualmente para todas as classes.
        tokens = [t for t in self._atributos(texto) if t in self.vocabulario]

        pontuacoes: dict[str, float] = {}
        for classe in self.classes:
            pontuacao = self.log_prior[classe]
            verossimilhanca = self.log_verossimilhanca[classe]
            padrao = self.log_padrao[classe]
            for token in tokens:
                pontuacao += verossimilhanca.get(token, padrao)
            pontuacoes[classe] = pontuacao

        return pontuacoes

    def prever_probabilidades(self, texto: str) -> dict[str, float]:
        """Converte os log-scores em probabilidades que somam 1 (softmax).

        Subtraímos o maior score antes de exponenciar. Isso não altera o
        resultado (é a mesma fração multiplicada em cima e embaixo) mas evita
        que `math.exp` estoure com números muito grandes ou muito pequenos.
        """
        pontuacoes = self.pontuar(texto)
        if not pontuacoes:
            return {}

        maior = max(pontuacoes.values())
        exponenciais = {c: math.exp(p - maior) for c, p in pontuacoes.items()}
        soma = sum(exponenciais.values())
        return {c: valor / soma for c, valor in exponenciais.items()}

    def prever(self, texto: str) -> tuple[str, float]:
        """Devolve a intenção mais provável e o quanto o modelo está confiante.

        A confiança é a probabilidade da classe vencedora, entre 0 e 1.
        O núcleo usa esse número para decidir se age ou se pede
        esclarecimento ao usuário - ver `nucleo.py`.

        CASO IMPORTANTE - frase sem nenhuma palavra conhecida:

        Quando nada da frase está no vocabulário, a soma das verossimilhanças
        é vazia e o log-score de cada classe se reduz ao seu log-prior. O
        vencedor passa a ser simplesmente a classe com MAIS exemplos no
        treino, sempre - e o softmax ainda devolveria uma confiança de
        aparência normal, mascarando o chute.

        Isso foi detectado na avaliação: frases como "vlw" e "bye" caíam em
        `duvida_programacao` só por ser a classe majoritária. A correção é
        assumir a ignorância: sem evidência, devolvemos confiança zero, e o
        núcleo trata como incerteza em vez de agir.
        """
        if not any(t in self.vocabulario for t in self._atributos(texto)):
            return "desconhecido", 0.0

        probabilidades = self.prever_probabilidades(texto)
        if not probabilidades:
            return "desconhecido", 0.0

        classe = max(probabilidades, key=lambda c: probabilidades[c])
        return classe, probabilidades[classe]
