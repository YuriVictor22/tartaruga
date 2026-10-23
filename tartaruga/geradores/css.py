"""
Gerador de CSS: monta seis padrões comuns a partir de parâmetros.

Mesmo espírito do gerador de HTML — funções puras, sem rede nem arquivo,
fáceis de testar isoladamente. Os seletores gerados (`.container`, `.grade`,
`.botao`...) usam nomes genéricos de propósito: quem for usar o CSS ajusta o
seletor para o elemento real da própria página.
"""

# ---------------------------------------------------------------------------
# Paleta de cores em português -> hexadecimal
#
# Pequena de propósito. O objetivo não é cobrir toda cor possível, é permitir
# "cria um botão vermelho" sem o usuário precisar saber hexadecimal.
# ---------------------------------------------------------------------------
CORES: dict[str, str] = {
    "verde": "#4ade80",
    "azul": "#60a5fa",
    "vermelho": "#f87171",
    "amarelo": "#fbbf24",
    "roxo": "#a78bfa",
    "rosa": "#f472b6",
    "cinza": "#8b949e",
    "preto": "#16191d",
    "branco": "#ffffff",
    "laranja": "#fb923c",
}

COR_PADRAO = "verde"


def flexbox(direcao: str = "row", centralizar: bool = False, espaco: str = "16px") -> str:
    """Layout flexbox — uma dimensão, como a entrada curada `CSS: Flexbox` explica."""
    direcao = direcao if direcao in ("row", "column") else "row"
    justificar = "center" if centralizar else "flex-start"
    alinhar = "center" if centralizar else "stretch"
    return f""".container {{
  display: flex;
  flex-direction: {direcao};
  justify-content: {justificar};
  align-items: {alinhar};
  gap: {espaco};
}}"""


def grid(colunas: int = 3, espaco: str = "16px") -> str:
    """Layout em grade com N colunas iguais."""
    colunas = max(1, min(colunas, 12))  # mais que 12 colunas não é razoável
    return f""".grade {{
  display: grid;
  grid-template-columns: repeat({colunas}, 1fr);
  gap: {espaco};
}}"""


def botao(cor: str = COR_PADRAO) -> str:
    """Estilo de botão com a cor pedida (ou verde, se a cor não for conhecida)."""
    hexadecimal = CORES.get(cor.lower().strip(), CORES[COR_PADRAO])
    return f""".botao {{
  background-color: {hexadecimal};
  color: #16191d;
  border: none;
  padding: 10px 20px;
  border-radius: 8px;
  font-weight: 600;
  cursor: pointer;
}}

.botao:hover {{
  opacity: 0.85;
}}"""


def centralizar() -> str:
    """Centraliza qualquer conteúdo, na horizontal e na vertical, com flexbox."""
    return """.centralizado {
  display: flex;
  justify-content: center;
  align-items: center;
  min-height: 100vh;
}"""


def variaveis(tema: str = "claro") -> str:
    """Bloco de variáveis CSS (`:root`), no tema claro ou escuro.

    Variáveis CSS existem em tempo de execução — trocar o bloco (ou usar uma
    media query) muda a página inteira de uma vez, como a entrada curada
    "CSS: variáveis" explica.
    """
    if tema.lower().strip() == "escuro":
        return """:root {
  --cor-fundo: #16191d;
  --cor-texto: #e6edf3;
  --cor-primaria: #4ade80;
  --cor-borda: #2d333b;
}"""
    return """:root {
  --cor-fundo: #ffffff;
  --cor-texto: #16191d;
  --cor-primaria: #4ade80;
  --cor-borda: #e2e8f0;
}"""


def responsivo(largura: str = "768px") -> str:
    """Bloco de media query para telas até a largura informada."""
    return f"""@media (max-width: {largura}) {{
  .container {{
    flex-direction: column;
    padding: 16px;
  }}
}}"""


def sombra(intensidade: str = "media") -> str:
    """Sombra de elevação — três níveis prontos, do mais sutil ao mais forte."""
    niveis = {
        "leve": "0 1px 3px rgba(0, 0, 0, 0.12)",
        "media": "0 4px 12px rgba(0, 0, 0, 0.15)",
        "forte": "0 12px 32px rgba(0, 0, 0, 0.25)",
    }
    valor = niveis.get(intensidade, niveis["media"])
    return f""".elevado {{
  box-shadow: {valor};
}}"""


def transicao(propriedade: str = "all", duracao: str = "0.2s") -> str:
    """Transição suave ao trocar de estado (`:hover`, por exemplo).

    `transition` sozinho não faz nada — precisa de uma regra `:hover` (ou
    outra mudança de estado) para a transição ter o que animar. Por isso o
    gerador já inclui um exemplo de hover junto.
    """
    return f""".suave {{
  transition: {propriedade} {duracao} ease;
}}

.suave:hover {{
  transform: scale(1.03);
  opacity: 0.9;
}}"""


def animacao(nome: str = "aparecer") -> str:
    """Uma animação `@keyframes` simples de entrada (fade + leve deslocamento)."""
    return f"""@keyframes {nome} {{
  from {{
    opacity: 0;
    transform: translateY(8px);
  }}
  to {{
    opacity: 1;
    transform: translateY(0);
  }}
}}

.animado {{
  animation: {nome} 0.4s ease-out;
}}"""
