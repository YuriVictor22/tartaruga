"""Resolução de contexto e ações explícitas antes da classificação estatística."""
import re

from .analise_js import analisar
from .interpretacao import interpretar
from .geracao import total_padroes


def geral(bot):
    return (
        f"No geral, explico Python, JavaScript, HTML e CSS consultando {len(bot.base)} tópicos locais; "
        f"monto código com {total_padroes()} templates, incluindo landing page; "
        "analiso um subconjunto numérico de JavaScript (escopos e closures); "
        "executo Python após sua confirmação, salvo e leio arquivos, pesquiso e aprendo conteúdo com fonte.\n\n"
        "Para planejar uma landing page, diga 'quero uma landing page': conduzo um briefing com seis perguntas e um resumo revisável.\n\n"
        "Uso o assunto da conversa para interpretar respostas curtas. Ainda não entendo qualquer programa ou pedido: "
        "quando faltar um detalhe, vou pedir uma informação específica. No modo Tartaruga tudo isso funciona sem LLM gerador. "
        "Posso usar um encoder semântico pré-treinado para reconhecer paráfrases; consulte /semantica."
    )


def capacidade_landing():
    return ("Sim, consigo montar uma landing page (LP) usando um template de HTML e CSS responsivo. "
            "Também posso conduzir um briefing para organizar os requisitos. "
            "Ainda não gero uma página personalizada a partir desse briefing.\n\n"
            "Para iniciar o planejamento, diga 'quero uma landing page'. "
            "Para pedir o código do template, diga 'gere uma landing page simples'.")


def resolver(bot, pedido):
    """Retorna (texto, intenção) ou None. Nunca executa código do usuário."""
    ctx = bot.dialogo.contexto
    norm = pedido.normalizado
    capacidade = bool(re.search(r"\b(capacidades?|limites?)\b", norm)) or bool(re.search(
        r"\b(?:voce|tu)\s+(?:e capaz de|seria capaz de|sabe|saberia|conhece|entende|consegue|conseguiria|pode|programa|trabalha)\b|^(?:e|seria) capaz de\b", norm))
    landing = bool(re.search(r"\b(?:landing page|lp)\b", norm))
    if ctx.assunto == "capacidades" and landing and re.fullmatch(r"(?:e\s+)?(?:uma?\s+)?(?:lp|landing page)[?.! ]*", norm):
        capacidade = True
    # Corrigir o ato de fala vem antes de interpretar verbos como comandos.
    correcao = re.search(r"\bnao (?:pedi|solicitei)\b", norm) and re.search(r"\bpergunta\w*\b", norm)
    correcao = correcao or re.search(r"\b(?:so|apenas) (?:fiz uma pergunta|perguntei)\b", norm)
    if correcao and not pedido.codigo:
        ctx.pendente = ctx.instrucao_pendente = ""
        if bot.dialogo.briefing.estado == "coletando":
            bot.dialogo.briefing.estado = "pausado"
        anteriores = [t for t in bot.memoria.turnos if t.papel == "usuario"]
        anterior = interpretar(anteriores[-1].texto) if anteriores else None
        if landing or (anterior and re.search(r"\b(?:landing page|lp)\b", anterior.normalizado)):
            ctx.assunto = "capacidades"
            return "Entendi: você estava perguntando sobre minha capacidade, sem pedir a criação da página.\n\n" + capacidade_landing(), "capacidades"
        return "Entendi: você fez uma pergunta, sem solicitar uma ação. Qual pergunta você quer que eu responda?", "esclarecimento"
    if capacidade and landing and not pedido.codigo:
        ctx.assunto, ctx.pendente = "capacidades", ""
        ctx.instrucao_pendente = ""
        if bot.dialogo.briefing.estado == "coletando":
            bot.dialogo.briefing.estado = "pausado"
            return capacidade_landing() + "\n\nPausei o briefing. Diga 'retomar briefing' para continuar.", "capacidades"
        return capacidade_landing(), "capacidades"
    complemento_codigo = ctx.pendente == "tipo_codigo" and norm.strip(" .?!") == "landing page"
    briefing = None if complemento_codigo or capacidade else bot.dialogo.briefing.processar(pedido)
    if briefing is not None:
        ctx.assunto = "briefing"
        ctx.pendente = ""
        ctx.instrucao_pendente = ""
        return briefing, "briefing"
    anteriores = [t for t in bot.memoria.turnos if t.papel == "usuario"]
    if re.search(r"\b(anterior\w*|antes|ultima pergunta)\b", norm) and re.search(r"\b(pergunt\w*|entend\w*|pedi\w*)\b", norm):
        for turno in reversed(anteriores):
            anterior = interpretar(turno.texto).normalizado
            if not (re.search(r"anterior|antes|ultima pergunta", anterior) and re.search(r"pergunt|entend", anterior)):
                return f"Sua pergunta anterior foi:\n\n{turno.texto}\n\nPosso continuar a partir dela; isso não significa que minha resposta anterior tenha sido correta.", "contexto"
        return "Não encontrei uma pergunta anterior nesta conversa. Escreva a pergunta que você quer retomar.", "contexto"

    if norm.strip(" .?!") in {"no geral", "em geral", "tudo", "todas", "geral", "de forma geral"}:
        if ctx.assunto == "capacidades":
            ctx.pendente = ""
            return geral(bot), "capacidades"
        return "Você quer uma visão geral de qual assunto? Por exemplo: minhas capacidades ou JavaScript.", "esclarecimento"

    if ctx.pendente == "tipo_codigo" and not pedido.codigo:
        if re.search(r"landing page|formulario|navbar|pagina|grid|debounce", norm):
            pedido = interpretar("cria " + pedido.texto)
            norm = pedido.normalizado
        ctx.pendente = ""

    # Código em uma mensagem seguinte pode completar a pergunta anterior.
    analise = bool(pedido.acoes & {"explicar", "prever_saida", "alterar"}) or ctx.pendente == "codigo_javascript"
    codigo, linguagem = pedido.codigo, pedido.linguagem
    if not codigo and analise and (re.search(r"\b(isso|esse codigo|este codigo|anterior|ele)\b", norm) or (ctx.assunto == "analise_codigo" and "alterar" in pedido.acoes)):
        for turno in reversed(anteriores):
            p = interpretar(turno.texto)
            if p.codigo:
                codigo, linguagem = p.codigo, p.linguagem
                break
        if not codigo:
            achado = bot.memoria.ultimo_codigo_com_linguagem()
            if achado:
                codigo, linguagem = achado
    if codigo and analise:
        ctx.pendente = ""
        if linguagem not in ("javascript", "js") and not (not linguagem and ctx.linguagem == "javascript"):
            return "Recebi o código. Meu analisador local de programas atualmente atende JavaScript numérico. Para outras linguagens, posso buscar explicações de conceitos; execução direta é apenas Python, com confirmação.", "esclarecimento"
        ctx.assunto, ctx.linguagem = "analise_codigo", "javascript"
        if pedido.restricoes and any(nome not in codigo for nome in pedido.restricoes):
            return "A função que você pediu para preservar não aparece no código. Confira o nome ou envie o trecho completo.", "esclarecimento"
        instrucao = "\n".join(p for p in (ctx.instrucao_pendente, pedido.texto) if p)
        ctx.instrucao_pendente = ""
        return analisar(codigo, instrucao), "analise_javascript"
    if not codigo and analise and pedido.linguagem == "javascript" and re.search(r"\b(codigo|console|saida)\b", norm):
        ctx.pendente, ctx.linguagem = "codigo_javascript", "javascript"
        ctx.instrucao_pendente = pedido.texto
        return "Cole o código JavaScript que você quer analisar. Vou verificar a saída e os escopos dentro do subconjunto que conheço.", "esclarecimento"

    if ctx.assunto == "capacidades" and pedido.linguagem and re.fullmatch(r"(?:e |agora )?(?:em |sobre )?[a-z ]+[?.! ]*", norm) and len(norm.split()) <= 4:
        capacidade = True
    if capacidade and not pedido.codigo:
        ctx.assunto, ctx.pendente = "capacidades", ""
        if pedido.linguagem:
            ctx.linguagem = pedido.linguagem
            nomes = {"javascript": "JavaScript", "python": "Python", "html": "HTML", "css": "CSS"}
            nome = nomes.get(pedido.linguagem, pedido.linguagem)
            if pedido.linguagem not in nomes:
                return f"Ainda não tenho suporte próprio completo a {nome}. Posso pesquisar conteúdo se você pedir, mas não vou afirmar que consigo gerar ou analisar programas nessa linguagem.", "capacidades"
            if re.search(r"\b(rodar|executar|compilar)\b", norm):
                return ("Sim, executo Python depois que você confirmar o código." if pedido.linguagem == "python" else f"Não executo {nome} diretamente. Executo apenas Python; para JavaScript tenho análise local de um subconjunto numérico."), "capacidades"
            detalhe = {
                "javascript": "explico conceitos, monto 13 padrões de código e analiso exemplos numéricos com funções, escopo e closures. Não executo JavaScript no navegador nem analiso toda a linguagem",
                "python": "explico conceitos, recupero exemplos e executo código com sua confirmação. Sem LLM, ainda não gero programas Python arbitrários",
                "html": "explico elementos e monto páginas, landing pages, formulários e outros templates",
                "css": "explico estilos e monto templates como grid, flexbox e responsividade",
            }[pedido.linguagem]
            return f"Sim, trabalho com {nome}: {detalhe}.\n\nQual exemplo ou problema você quer resolver?", "capacidades"
        if re.search(r"\b(codar|programar|codigo|gerar)\b", norm):
            return f"Monto {total_padroes()} templates de HTML, CSS e JavaScript com parâmetros, incluindo landing pages. Em Python, recupero exemplos e posso executá-los com confirmação. Analiso um subconjunto numérico de JavaScript. Ainda não escrevo qualquer programa do zero.\n\nO que você quer construir e em qual linguagem?", "capacidades"
        return geral(bot), "capacidades"

    if "gerar" in pedido.acoes and not pedido.codigo:
        ctx.assunto = "geracao"
        ctx.linguagem = pedido.linguagem or ctx.linguagem
        resultado = bot.gerador.gerar(pedido.texto)
        if resultado is not None:
            ctx.pendente = ""
            resposta = bot._gerar_codigo(pedido.texto, "gerar_codigo", 0)
            return resposta.texto, "gerar_codigo"
        if re.search(r"\b(codigo|programa|pagina)\b", norm):
            ctx.pendente = "tipo_codigo"
            return "Que tipo de código você quer: landing page, formulário, layout CSS ou uma função JavaScript como debounce? Diga também a linguagem. Sem LLM não monto programas arbitrários.", "esclarecimento"
    return None
