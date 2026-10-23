"""
Ferramentas: as ações concretas que a Tartaruga sabe executar.

Cada módulo aqui expõe funções simples e previsíveis. O `nucleo` decide
QUAL ferramenta chamar; as ferramentas apenas fazem o trabalho e devolvem
o resultado, sem imprimir nada na tela.

Essa separação é proposital: mantém a lógica de decisão isolada da execução,
o que torna cada parte testável sozinha.
"""

from . import arquivos, executar, web

__all__ = ["arquivos", "executar", "web"]
