"""Interpretação local de pedidos; preserva código e não usa modelo externo."""
import re
from dataclasses import dataclass, field

from .vetorizador import remover_acentos

LINGUAGENS = ("javascript", "python", "html", "css", "typescript", "java", "rust", "ruby", "php", "kotlin", "sql")
CORRECOES = {
    "oque": "o que", "oq": "o que", "vc": "você", "vcs": "vocês",
    "anteriomente": "anteriormente",
    "lanepage": "landing page", "landpage": "landing page", "landingpage": "landing page",
    "javascrit": "javascript", "javscript": "javascript",
}


def normalizar_prosa(texto: str) -> str:
    texto = re.sub(r"\blane\s+page\b", "landing page", texto, flags=re.I)
    texto = re.sub(r"\bjava\s+script\b", "javascript", texto, flags=re.I)
    texto = re.sub(r"\b(?:eu|ue)\s+perguntei\b", "eu perguntei", texto, flags=re.I)
    return re.sub(r"\b\w+\b", lambda m: CORRECOES.get(m[0].lower(), m[0]), texto)


@dataclass
class Pedido:
    original: str
    texto: str
    codigo: str = ""
    linguagem: str = ""
    acoes: set[str] = field(default_factory=set)
    restricoes: list[str] = field(default_factory=list)

    @property
    def normalizado(self) -> str:
        return remover_acentos(self.texto.lower())


def interpretar(entrada: str) -> Pedido:
    # Blocos e código inline ficam fora da normalização ortográfica.
    blocos = list(re.finditer(r"```([^\n`]*)\n(.*?)```", entrada, re.S))
    codigo, linguagem = "", ""
    prosa = entrada
    if blocos:
        codigo = blocos[0][2].strip()
        linguagem = blocos[0][1].strip().lower()
        prosa = re.sub(r"```[^\n`]*\n.*?```", " ", entrada, flags=re.S)
    else:
        inicio = re.search(r"(?m)^\s*(?:(?:let|const|var)\s+\w+\s*=|function\s+\w+\s*\(|console\.log\s*\()", entrada)
        if inicio:
            antes, trecho = entrada[:inicio.start()], entrada[inicio.start():]
            fim = re.search(r"(?im)^\s*(?:al[eé]m\b|depois\b|explique\b|sem modificar\b|agora\b)", trecho)
            codigo = trecho[:fim.start()].strip() if fim else trecho.strip()
            prosa = antes + (trecho[fim.start():] if fim else "")
            linguagem = "javascript"
    partes = re.split(r"(`[^`]*`)", prosa)
    texto = "".join(p if p.startswith("`") else normalizar_prosa(p) for p in partes)
    norm = remover_acentos(texto.lower())
    linguagem = {"js": "javascript", "py": "python"}.get(linguagem, linguagem)
    if not linguagem:
        linguagem = next((l for l in LINGUAGENS if re.search(rf"\b{l}\b", norm)), "")
        if re.search(r"\bjs\b", norm):
            linguagem = "javascript"
    acoes = set()
    for nome, padrao in {
        "explicar": r"\b(expli[cq]\w*|por que|conceitos?|analise|analisar)\b",
        "prever_saida": r"\b(console|impress\w*|imprim\w*|saida|retorna\w*)\b",
        "alterar": r"\b(altere|alterar|modifique|modificar|mude|mudar|ajuste)\b",
        "gerar": r"\b(crie|cria|criar|gere|gera|gerar|monte|monta|desenvolva|faca)\b",
    }.items():
        if re.search(padrao, norm):
            acoes.add(nome)
    restricoes = re.findall(r"sem (?:modificar|alterar|mudar)\s+(?:a\s+)?funcao\s+(\w+)", norm)
    return Pedido(entrada, texto.strip(), codigo, linguagem, acoes, restricoes)


@dataclass
class Contexto:
    assunto: str = ""
    linguagem: str = ""
    pendente: str = ""
    instrucao_pendente: str = ""
    opcoes_semanticas: list[tuple[str, str]] = field(default_factory=list)
    # Esclarecimento: a pergunta (chave normalizada) que gerou as opções em aberto, o que a
    # pessoa ESCOLHEU e o que ela RECUSOU para cada pergunta, nesta sessão.
    consulta_opcoes: str = ""
    escolhas: dict[str, str] = field(default_factory=dict)
    rejeitadas: dict[str, set[str]] = field(default_factory=dict)
    reperguntas: int = 0
    # A última geração de código (linguagem, descrição, código, turno): "use css também" a complementa.
    ultima_geracao: dict | None = None
    # As últimas consultas de pesquisa na web (consulta, turno): "qual dos dois é mais fácil?" as compara.
    ultimas_buscas: list[tuple[str, int]] = field(default_factory=list)

    def limpar(self):
        self.assunto = self.linguagem = self.pendente = self.instrucao_pendente = ""
        self.opcoes_semanticas.clear()
        self.consulta_opcoes = ""
        self.escolhas.clear()
        self.rejeitadas.clear()
        self.reperguntas = 0
        self.ultima_geracao = None
        self.ultimas_buscas.clear()
