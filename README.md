<img src="Logo/logo_tartaruga.png" alt="Logo da Tartaruga" width="140" align="right">

# Tartaruga

Uma assistente de programação que fala português. Você pergunta como fazer um laço `for` em Python, pede um formulário em HTML ou um `debounce` em JavaScript, e ela responde na hora, sem precisar de internet nem de um modelo de linguagem para o básico.

O projeto nasceu como trabalho do curso de Análise e Desenvolvimento de Sistemas. A ideia era entender como um assistente funciona por dentro, então a parte de "inteligência" é feita à mão: um classificador Naive Bayes descobre o que a pessoa quer, TF-IDF com similaridade de cosseno procura a resposta numa base de conhecimento, e templates geram o código. Nada disso usa scikit-learn ou outra biblioteca de aprendizado de máquina.

Funciona numa janela (PyQt6) ou pelo terminal.

## O que ela faz

- Responde dúvidas de Python, JavaScript, HTML e CSS a partir de uma base com mais de 80 tópicos escritos à mão.
- Gera código com 35 templates: 13 de HTML (landing page, formulário, navbar, modal...), 9 de CSS (flexbox, grid, animação...) e 13 de JavaScript (debounce, throttle, memoize, fetch...).
- Lembra do que foi dito antes, então "e no geral?" ou "agora em CSS" funcionam como continuação da conversa.
- Roda código Python depois que você confirma, mostra a saída e explica em português os erros mais comuns.
- Lê e salva arquivos numa pasta própria, `workspace/`.
- Pesquisa na web (sem chave de API) e, se você pedir, guarda o que achou numa base separada, sempre com a fonte.
- Conduz um briefing de landing page: faz seis perguntas, uma de cada vez, e entrega um resumo para você confirmar.
- Guarda as conversas em disco e exporta/importa tudo num backup.

## Baixar e abrir (Windows)

O jeito mais simples é pegar o executável em [Releases](https://github.com/YuriVictor22/tartaruga/releases/latest): baixe o `.zip`, extraia a pasta inteira e abra `Tartaruga.exe`. Não precisa ter Python nem Ollama instalados.

- Mantenha `_internal` e `modelos` ao lado do executável.
- Extraída, a pasta ocupa cerca de 1,7 GB, porque leva junto o modelo de compreensão semântica e o navegador embutido do preview.
- A Tartaruga grava conversas e arquivos ao lado do executável, então extraia numa pasta onde você tem permissão de escrita (evite "Arquivos de Programas").
- O executável não é assinado. Na primeira vez o Windows pode mostrar um aviso do SmartScreen: clique em "Mais informações" e depois em "Executar assim mesmo".

## Rodar pelo código

Precisa de Python 3.10 ou mais novo (testado no Windows com 3.12). No PowerShell, dentro da pasta do projeto:

```powershell
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
.\.venv\Scripts\python.exe interface.py   # janela
.\.venv\Scripts\python.exe main.py        # terminal
```

Algumas coisas para experimentar:

```text
como faço um laço for em python
cria um formulário de login em html
cria grid com 4 colunas em css
cria debounce em javascript
quero uma landing page
pesquisa sobre fastapi na internet
salva isso em exemplo.py
qual foi minha última pergunta?
```

Para rodar código, cole um bloco Python (ou use **Colar código** na barra lateral) e peça "roda esse código". Ela mostra o que vai executar e espera a sua confirmação.

## Extras opcionais

### Phi-4-mini, pelo Ollama

Com o [Ollama](https://ollama.com) instalado e aberto:

```powershell
ollama pull phi4-mini
```

Na janela dá para escolher entre três modos: só a Tartaruga (o padrão), Tartaruga + Phi-4-mini (o modelo entra quando a base e os templates não resolvem) e só o Phi-4-mini. Código Python novo só sai com o modelo; os templates cobrem HTML, CSS e JavaScript.

### Compreensão semântica

Ajuda a entender paráfrases ("como repito algo várias vezes" é o mesmo que laço `for`). Usa um encoder multilíngue pequeno (MiniLM) que roda local, em CPU:

```powershell
.\.venv\Scripts\python.exe -m pip install -r requirements-semantic.txt
.\.venv\Scripts\python.exe preparar_semantica.py
```

O script baixa `sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2` para `modelos/semantica/` (cerca de 500 MB). Depois disso funciona sem internet. Ele só ajuda a achar o assunto: não gera texto e não decide nada sozinho sobre executar, apagar ou gravar. Para desligar, defina `TARTARUGA_SEMANTICA=0`.

### Preview de HTML, CSS e JavaScript

`pip install -r requirements-preview.txt` adiciona uma aba que mostra o código gerado num navegador embutido (Chromium), com a rede bloqueada por padrão.

## Como ela decide o que responder

1. Regras de conversa e de contexto resolvem o que é óbvio (saudações, "e agora em CSS?", correções do briefing).
2. Um classificador Naive Bayes, treinado com cerca de 800 frases rotuladas (`dados/intencoes.json`, 15 intenções), descobre a intenção.
3. Se for uma dúvida, TF-IDF com similaridade de cosseno procura na base (`dados/conhecimento.json`). Se a semelhança for baixa demais, ela prefere dizer que não sabe a inventar uma resposta.
4. Se for um pedido de código, a escolha do template é feita por regras e palavras-chave. Não é geração livre.

A pontuação que aparece ao lado da resposta é a do classificador e **não é uma porcentagem de certeza**. Em um conjunto de teste separado, o classificador acerta a intenção em cerca de 83% das frases.

Para ensinar algo novo, edite `dados/intencoes.json` (exemplos de frases) ou `dados/conhecimento.json` (tópicos de resposta). O recurso "aprenda sobre..." só amplia a base de consulta com o que foi pesquisado; ele não retreina o classificador.

## Onde ficam os seus dados

Tudo é gravado ao lado do programa, em JSON simples e sem criptografia: conversas em `historico/`, arquivos em `workspace/`, projetos de landing page em `projetos/` e o conhecimento aprendido em `dados_aprendidos.json`. A única coisa que sai do computador são as consultas de pesquisa, quando você pede uma, e as chamadas ao Ollama local, quando você usa o Phi-4-mini.

## Limitações

- Ela só conhece o que está na base e nos exemplos de treino. Frases ambíguas ou fora de programação podem ser classificadas errado, e a pontuação pode ser alta mesmo quando a resposta está errada.
- O Naive Bayes ignora a ordem das palavras, então frases complexas ou com negação são o ponto fraco.
- A base aprendida na web pode ter trechos incompletos ou desatualizados.
- O executor de Python **não é um sandbox**: o código roda em outro processo, com limite de 5 segundos, mas com os mesmos privilégios do seu usuário.
- A ferramenta de salvar arquivos pode sobrescrever um arquivo que já existe.
- Foi testada no Windows. Não foi verificada em Linux ou macOS.

## Licença

GPL-3.0, veja o arquivo [LICENSE](LICENSE). Copyright © 2026 Yuri Batista.

Cada dependência mantém a própria licença: PyQt6 (GPLv3), `ddgs`, e, nos extras, `sentence-transformers`, PyQt6-WebEngine, o modelo MiniLM e o Phi-4-mini (via Ollama). Issues e pull requests são bem-vindos.
