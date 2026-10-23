"""
Geradores de código por template — a parte "programar", não só "explicar".

Até aqui a Tartaruga só RECUPERAVA código: um exemplo fixo da base curada, ou
um trecho extraído de uma página aprendida. Este pacote faz algo diferente —
MONTA um trecho de código a partir de parâmetros extraídos do pedido do
usuário: "cria um formulário de login em html" vira um `<form>` de verdade,
com os campos certos.

Não é geração livre. É montagem de um conjunto FIXO de padrões comuns
(página, formulário, navbar, card, lista, tabela / flexbox, grid, botão,
tema, responsivo), a partir de peças reutilizáveis.

Por que templates, e não um modelo de linguagem: o projeto inteiro foi
construído sem LLM. Um gerador por templates é honesto sobre o que faz —
monta o que já sabe montar, do jeito que já conhece — em vez de fingir uma
criatividade que exigiria exatamente o que este projeto decidiu não usar.
É por isso que toda resposta gerada vem marcada como tal, junto com o que
ela NÃO faz: um pedido fora dos padrões conhecidos não produz um layout
inventado — produz uma recusa honesta.
"""

from . import css, html

__all__ = ["css", "html"]
