"""
Tartaruga - assistente de programação construído do zero.

Projeto acadêmico de Análise e Desenvolvimento de Sistemas.

O pacote está dividido em camadas:

    vetorizador   -> transforma texto em números (TF-IDF)
    classificador -> aprende a reconhecer a intenção do usuário (Naive Bayes)
    conhecimento  -> busca respostas numa base local (similaridade de cosseno)
    memoria       -> guarda e persiste o histórico da conversa
    ferramentas/  -> ações concretas: executar código, mexer em arquivos, buscar na web
    nucleo        -> junta tudo: recebe a frase, decide o que fazer, responde
"""

__version__ = "1.1.0-dev"
