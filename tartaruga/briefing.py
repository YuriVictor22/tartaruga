"""Briefing guiado de landing page, com estado serializável e regras locais.

Etapa 1: coleta requisitos e apresenta um resumo. Não gera textos comerciais,
não publica páginas e não adivinha respostas que o usuário não forneceu.
"""
import re
from dataclasses import dataclass, field

from .vetorizador import remover_acentos


CAMPOS = {
    "negocio": ("Negócio", "Qual é o nome do negócio e o que ele faz?", "Exemplo: Oficina Horizonte, manutenção de bicicletas."),
    "publico": ("Público-alvo", "Quem você quer atingir com a página?", "Descreva o perfil, a necessidade e, se importar, a região do público."),
    "oferta": ("Oferta", "Qual produto ou serviço será oferecido e qual benefício real ele entrega?", "Use informações reais. Preço e condições podem ser informados se já estiverem definidos."),
    "objetivo": ("Objetivo de conversão", "Qual ação principal o visitante deve realizar?", "Exemplos: pedir orçamento, agendar atendimento, comprar ou fazer cadastro."),
    "estilo": ("Estilo visual", "Você tem preferência de estilo, cores ou referências visuais?", "Pode responder 'pular' se ainda não definiu. Não vou escolher por você nesta etapa."),
    "contato": ("Contato", "Qual canal e endereço de contato poderão aparecer na página?", "Informe apenas o contato comercial que deseja divulgar. Pode responder 'pular' para definir depois."),
}
ALIASES = {
    "negocio": "negocio", "empresa": "negocio", "marca": "negocio",
    "publico": "publico", "publico-alvo": "publico", "publico alvo": "publico",
    "oferta": "oferta", "produto": "oferta", "servico": "oferta",
    "objetivo": "objetivo", "conversao": "objetivo", "objetivo de conversao": "objetivo",
    "estilo": "estilo", "estilo visual": "estilo", "cores": "estilo",
    "contato": "contato", "whatsapp": "contato", "email": "contato", "e-mail": "contato",
}
OPCIONAIS = {"estilo", "contato"}
ESTADOS = {"inativo", "coletando", "pausado", "revisao", "confirmado", "cancelado"}
EXPLICACOES = {
    "negocio": "Quero saber quem será apresentado na página: o nome e a atividade do negócio.",
    "publico": "Público é quem você deseja atender. Exemplo: ciclistas do bairro que precisam de manutenção.",
    "oferta": "Oferta é o que você vende ou presta. Exemplo: revisão de bicicletas para mantê-las em bom funcionamento.",
    "objetivo": "É a ação mais importante que a página deve incentivar. Exemplo: pedir um orçamento.",
    "estilo": "É a aparência que você prefere. Exemplo: visual simples com verde e branco. Se não souber, diga 'pular'.",
    "contato": "É como o cliente falará com o negócio. Exemplo: um e-mail comercial. Se ainda não definiu, diga 'pular'.",
}


def normalizar(texto):
    return " ".join(remover_acentos(texto.lower()).split()).rstrip(".!?").strip()


def ato_dialogo(texto):
    """Reconhece atos completos, não palavras soltas dentro de uma oferta."""
    norm = normalizar(texto)
    norm = re.sub(r"^(?:por favor[, ]+)", "", norm)
    norm = re.sub(r"[, ]+por favor$", "", norm)
    if re.fullmatch(
        r"(?:para|pare|chega|parar|(?:eu )?nao (?:quero (?:continuar|responder|isso|(?:esse|este|o) briefing)|"
        r"(?:pedi|solicitei) (?:isso|isto|(?:esse|este|o) briefing))|nao foi isso que (?:eu )?pedi)", norm):
        return "recusa"
    if re.fullmatch(
        r"(?:ajuda(?: briefing)?|(?:eu )?(?:ainda )?nao (?:entendi|entendo|compreendi)"
        r"(?: (?:isso|nada|(?:essa|esta|a) pergunta))?|(?:e )?o ?que|o que (?:e|significa) (?:isso|isto)|"
        r"como assim|(?:me de|de) um exemplo|(?:pode )?explicar(?: melhor)?|explique (?:isso|melhor))", norm):
        return "ajuda"
    return ""


@dataclass
class Briefing:
    dados: dict[str, str] = field(default_factory=dict)
    pulados: list[str] = field(default_factory=list)
    estado: str = "inativo"
    editando: str = ""
    pedido_inicial: str = ""
    aviso: str = ""  # transitório: anexado à resposta quando o usuário muda de assunto
    duvidas_seguidas: int = 0

    def exportar(self):
        return {"versao": 1, "dados": dict(self.dados), "pulados": list(self.pulados),
                "estado": self.estado, "editando": self.editando, "pedido_inicial": self.pedido_inicial,
                "duvidas_seguidas": self.duvidas_seguidas}

    @classmethod
    def restaurar(cls, registro):
        """Históricos antigos não têm snapshot; formatos inválidos não quebram a abertura."""
        if not isinstance(registro, dict) or registro.get("versao") != 1:
            return cls()
        dados, pulados = registro.get("dados"), registro.get("pulados")
        estado, editando = registro.get("estado"), registro.get("editando", "")
        inicial = registro.get("pedido_inicial", "")
        if (not isinstance(dados, dict) or any(k not in CAMPOS or not isinstance(v, str) or not v.strip() or len(v) > 2000 for k, v in dados.items())
                or not isinstance(pulados, list) or any(not isinstance(k, str) or k not in OPCIONAIS for k in pulados)
                or len(set(pulados)) != len(pulados) or any(k in dados for k in pulados)
                or not isinstance(estado, str) or estado not in ESTADOS
                or not isinstance(editando, str) or (editando and editando not in CAMPOS)
                or not isinstance(inicial, str) or len(inicial) > 4000):
            return cls()
        resultado = cls(dict(dados), list(pulados), estado, editando, inicial)
        duvidas = registro.get("duvidas_seguidas", 0)
        if type(duvidas) is int and 0 <= duvidas <= 2:
            resultado.duvidas_seguidas = duvidas
        if estado in {"revisao", "confirmado"} and resultado.proximo():
            resultado.estado = "coletando"
        elif estado == "coletando" and not resultado.proximo():
            resultado.estado = "revisao"
        return resultado

    def proximo(self):
        return self.editando or next((c for c in CAMPOS if c not in self.dados and c not in self.pulados), "")

    def perguntar(self):
        campo = self.proximo()
        if not campo:
            self.estado = "revisao"
            return self.resumo()
        numero = list(CAMPOS).index(campo) + 1
        _, pergunta, ajuda = CAMPOS[campo]
        prefixo = "Correção" if self.editando else f"Pergunta {numero} de {len(CAMPOS)}"
        return f"{prefixo} — {pergunta}\n\n{ajuda}"

    def resumo(self):
        linhas = ["Resumo do briefing da landing page:"]
        for campo, (rotulo, _, _) in CAMPOS.items():
            valor = self.dados.get(campo, "Não definido (pulado)" if campo in self.pulados else "Ainda não informado")
            linhas.append(f"• **{rotulo}:** {valor}")
        if self.estado == "confirmado":
            linhas.append("\nBriefing confirmado. Nesta etapa, entrego os requisitos organizados; a página personalizada ainda não foi gerada.")
        elif self.proximo():
            linhas.append("\nBriefing incompleto. " + self.perguntar())
        else:
            linhas.append("\nConfira as informações. Diga **confirmar briefing** ou, por exemplo, **corrigir público para estudantes universitários**.")
        linhas.append("\nPara consultar: 'resumo do briefing'. Para iniciar outro: 'novo briefing'.")
        return "\n".join(linhas)

    def _registrar(self, campo, valor):
        valor = valor.strip()
        norm = normalizar(valor)
        if not valor or len(valor) > 2000:
            return "Informe uma resposta de até 2.000 caracteres."
        if ato_dialogo(valor):
            return "Isso parece uma recusa ou um pedido de ajuda, não uma informação comercial. Nenhum dado foi alterado. Diga 'ajuda briefing' ou 'pausar briefing'."
        if norm in {"pular", "nao sei", "nao definido", "a definir", "ainda nao sei", "nao tenho"}:
            if campo not in OPCIONAIS:
                return f"Precisamos definir {CAMPOS[campo][0].lower()} antes de confirmar. {CAMPOS[campo][2]}"
            self.dados.pop(campo, None)
            if campo not in self.pulados:
                self.pulados.append(campo)
        elif norm in {"sim", "nao", "ok", "entendi", "obrigado", "obrigada"}:
            return "Preciso da informação por escrito, não apenas de uma confirmação. " + CAMPOS[campo][2]
        else:
            self.dados[campo] = valor
            if campo in self.pulados:
                self.pulados.remove(campo)
        if self.editando == campo:
            self.editando = ""
        self.estado = "coletando"
        self.duvidas_seguidas = 0
        return ""

    def ajudar(self):
        self.duvidas_seguidas = min(2, self.duvidas_seguidas + 1)
        resposta = (EXPLICACOES[self.proximo()] + " Não registrei sua mensagem como resposta. "
                    "Os exemplos são ilustrativos; responda com os dados do seu projeto.\n\n" + self.perguntar())
        if self.duvidas_seguidas >= 2:
            resposta += ("\n\nPodemos **continuar** nesta pergunta, **pausar** e retomar depois, "
                         "ou **cancelar** este briefing. Digite uma dessas palavras. Nenhum dado será apagado.")
        return resposta

    def processar(self, pedido):
        """Texto de resposta ou None para deixar outro fluxo atender à mensagem."""
        texto = pedido.original.strip()
        norm = normalizar(pedido.texto)
        comecar = norm in {"/briefing", "briefing", "iniciar briefing", "começar briefing", "comecar briefing", "novo briefing", "reiniciar briefing"}
        comecar = comecar or norm == "landing page"
        # LP é ambíguo fora de um pedido de criação; não expandir globalmente.
        comecar = comecar or bool(re.search(r"\b(?:quero|preciso de|vamos criar|planejar)\s+(?:criar\s+)?(?:uma?\s+)?(?:landing page|lp)\b", norm))
        reiniciar = norm in {"novo briefing", "reiniciar briefing"}
        # Um bloco de código nunca é interpretado como resposta comercial.
        if pedido.codigo:
            if self.estado == "coletando":
                self.estado = "pausado"
                self.aviso = "Pausei o briefing para tratar o código. Diga 'retomar briefing' para continuar."
            return None
        if comecar:
            if self.estado not in {"inativo", "cancelado"} and not reiniciar:
                return "Já existe um briefing nesta conversa.\n\n" + self.resumo() + "\nDiga 'retomar briefing' para continuar a coleta."
            self.dados.clear()
            self.pulados.clear()
            self.editando = ""
            self.duvidas_seguidas = 0
            self.estado = "coletando"
            self.pedido_inicial = texto[:4000]
            return ("Vamos organizar o briefing da sua landing page, uma pergunta por vez. "
                    "Você pode corrigir respostas, pedir 'resumo do briefing', pausar ou cancelar.\n\n" + self.perguntar())
        if norm in {"cancelar briefing", "cancele o briefing", "cancelar"} and self.estado not in {"inativo", "cancelado"}:
            self.estado = "cancelado"
            self.editando = ""
            self.duvidas_seguidas = 0
            return "Briefing cancelado. Não vou coletar mais respostas para ele. O que você já informou continua no histórico. Para começar outro, diga 'novo briefing'."
        if (norm in {"pausar briefing", "pause o briefing", "pausar"} or ato_dialogo(norm) == "recusa") and self.estado == "coletando":
            self.estado = "pausado"
            self.duvidas_seguidas = 0
            return "Briefing pausado, com as respostas guardadas. Diga 'retomar briefing' para continuar."
        if norm in {"retomar briefing", "continuar briefing", "continue o briefing"} or (norm == "continuar" and self.estado == "coletando" and self.duvidas_seguidas >= 2):
            if self.estado in {"inativo", "cancelado"}:
                return "Não há briefing ativo para retomar. Diga 'quero uma landing page' para começar."
            if self.estado == "confirmado":
                return self.resumo()
            self.estado = "coletando"
            self.duvidas_seguidas = 0
            return self.perguntar()
        if norm in {"resumo do briefing", "mostrar briefing", "ver briefing", "resumo briefing"} or (norm == "resumo" and self.estado not in {"inativo", "cancelado"}):
            return self.resumo() if self.estado not in {"inativo", "cancelado"} else "Não há briefing ativo. Diga 'quero uma landing page' para iniciar."
        if norm in {"confirmar briefing", "confirmo o briefing", "confirmar", "confirmo", "sim"} and self.estado not in {"inativo", "cancelado"}:
            if self.proximo():
                return "Ainda falta preencher ou corrigir uma informação.\n\n" + self.perguntar() + ("\nDiga 'retomar briefing' antes de responder." if self.estado == "pausado" else "")
            self.estado = "confirmado"
            return self.resumo()
        if self.estado in {"inativo", "cancelado"}:
            return None
        if self.estado == "coletando" and norm in {"oi", "ola", "bom dia", "boa tarde", "boa noite"}:
            return "Olá! Estamos preenchendo o briefing.\n\n" + self.perguntar()
        if ato_dialogo(norm) == "ajuda":
            return self.ajudar() if self.estado == "coletando" else self.resumo()
        correcao = re.match(r"^(?:corrigir|corrija|alterar|altere|mudar|mude|trocar|troque|atualizar|atualize)\s+(.*)$", texto, re.I | re.S)
        if correcao:
            partes = re.split(r"\s+(?:para|por)\s+|[:=]", correcao[1], maxsplit=1, flags=re.I)
            nome = re.sub(r"^(?:o|a)\s+", "", normalizar(partes[0]))
            campo = ALIASES.get(nome)
            if not campo:
                if self.estado != "coletando":
                    return None
                return "Qual campo deseja corrigir? Negócio, público, oferta, objetivo, estilo ou contato. Use 'corrigir público para ...'."
            if len(partes) == 1 or not partes[1].strip():
                self.editando, self.estado = campo, "coletando"
                self.duvidas_seguidas = 0
                return self.perguntar()
            erro = self._registrar(campo, partes[1])
            return erro or (f"{CAMPOS[campo][0]} atualizado.\n\n" + self.perguntar())
        if self.estado != "coletando":
            return None
        if re.match(r"^(?:o que (?:e|significa)|como (?:faco|funciona|usar)|explique|pesquise|pesquisa|aprenda|mostra o historico|lista os arquivos|roda |execute |/|tchau\b)", norm):
            self.estado = "pausado"
            self.aviso = "Pausei o briefing para atender ao novo assunto. Diga 'retomar briefing' para continuar."
            return None
        # Rótulos explícitos permitem informar vários campos sem inferir fatos.
        rotulados = []
        for parte in re.split(r"[;\n]", texto):
            if ":" in parte:
                rotulo, valor = parte.split(":", 1)
                campo = ALIASES.get(normalizar(rotulo))
                if campo:
                    rotulados.append((campo, valor))
        if rotulados:
            # Valida o lote inteiro antes de modificar o briefing.
            copia = self.restaurar(self.exportar())
            for campo, valor in rotulados:
                erro = copia._registrar(campo, valor)
                if erro:
                    return f"{CAMPOS[campo][0]}: {erro} Nenhuma resposta deste lote foi aplicada."
            self.dados, self.pulados, self.editando = copia.dados, copia.pulados, copia.editando
            self.duvidas_seguidas = 0
            return "Informações registradas.\n\n" + self.perguntar()
        if "?" in texto:
            # Pode ser uma marca/oferta interrogativa; exigir rótulo evita adivinhar.
            rotulo = CAMPOS[self.proximo()][0]
            return ("Você está pedindo uma explicação ou informando o conteúdo desse campo? "
                    f"Para registrar o texto comercial, escreva **{rotulo}: {texto}**. "
                    "Para entender a pergunta, diga 'ajuda briefing'. Nenhum dado foi alterado.")
        erro = self._registrar(self.proximo(), texto)
        return erro or self.perguntar()
