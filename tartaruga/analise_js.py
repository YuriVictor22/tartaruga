"""Parser e avaliador didático de um SUBCONJUNTO numérico de JavaScript.

Não usa eval/exec, navegador, rede ou processo JavaScript. Rejeita sintaxe
fora da gramática em vez de adivinhar. Suporta let/const, funções, closures,
return, chamadas, aritmética numérica e console.log. Limites de tamanho e
passos também se aplicam a funções recursivas.
"""
from dataclasses import dataclass
import math
import re


class NaoSuportado(ValueError):
    pass


TOKEN = re.compile(r"\s+|//[^\n]*|/\*.*?\*/|\d+(?:\.\d+)?|[A-Za-z_$][\w$]*|[{}();,.=+*/\-]", re.S)
RESERVADAS = set("let const var function return if else while do for new this class true false null undefined console break case catch continue debugger default delete enum export extends finally import in instanceof super switch throw try typeof void with yield await implements interface package private protected public static".split())


class Parser:
    def __init__(self, codigo):
        if len(codigo) > 12000:
            raise NaoSuportado("Trecho acima de 12.000 caracteres.")
        self.codigo, self.tokens, self.i = codigo, [], 0
        pos = 0
        for m in TOKEN.finditer(codigo):
            if m.start() != pos:
                raise NaoSuportado(f"Símbolo não suportado na posição {pos}.")
            pos = m.end()
            if not (m[0].isspace() or m[0].startswith(("//", "/*"))):
                self.tokens.append((m[0], m.start(), m.end()))
        if pos != len(codigo):
            raise NaoSuportado(f"Símbolo não suportado na posição {pos}.")
        self.tokens.append(("EOF", len(codigo), len(codigo)))

    def atual(self):
        return self.tokens[self.i][0]

    def pegar(self, esperado=None):
        token = self.atual()
        if esperado is not None and token != esperado:
            raise NaoSuportado(f"Esperado {esperado!r}; encontrado {token!r}.")
        if token == "EOF":
            raise NaoSuportado("Código incompleto.")
        self.i += 1
        return token

    def nome(self):
        token = self.pegar()
        if not re.fullmatch(r"[A-Za-z_$][\w$]*", token) or token in RESERVADAS:
            raise NaoSuportado(f"Identificador não suportado: {token}.")
        return token

    def programa(self, interno=False):
        nos = []
        while self.atual() not in ("EOF", "}"):
            t = self.atual()
            if t in ("let", "const"):
                especie = self.pegar()
                nome = self.nome()
                self.pegar("=")
                inicio = self.tokens[self.i][1]
                expr = self.expressao()
                fim = self.tokens[self.i - 1][2]
                self.pegar(";")
                nos.append(("declaracao", nome, expr, especie, inicio, fim))
            elif t == "function":
                self.pegar()
                nome = self.nome()
                nos.append(("funcao", nome, self.funcao()))
            elif t == "return" and interno:
                self.pegar()
                if re.search(r"[\r\n\u2028\u2029]", self.codigo[self.tokens[self.i - 1][2]:self.tokens[self.i][1]]):
                    raise NaoSuportado("Quebra de linha após return: a inserção automática de ponto e vírgula não é suportada.")
                expr = self.expressao()
                self.pegar(";")
                nos.append(("retorno", expr))
            elif t == "console":
                self.pegar(); self.pegar("."); self.pegar("log"); self.pegar("(")
                args = self.argumentos()
                self.pegar(")"); self.pegar(";")
                nos.append(("console", args))
            else:
                raise NaoSuportado(f"Instrução {t!r} fora do subconjunto suportado.")
        if not interno and self.atual() != "EOF":
            raise NaoSuportado("Chave sem abertura.")
        return nos

    def funcao(self):
        self.pegar("(")
        params = []
        if self.atual() != ")":
            params.append(self.nome())
            while self.atual() == ",":
                self.pegar(); params.append(self.nome())
        if len(set(params)) != len(params):
            raise NaoSuportado("Parâmetros duplicados.")
        self.pegar(")"); self.pegar("{")
        corpo = self.programa(interno=True)
        self.pegar("}")
        return ("lambda", params, corpo)

    def argumentos(self):
        args = []
        if self.atual() != ")":
            args.append(self.expressao())
            while self.atual() == ",":
                self.pegar(); args.append(self.expressao())
        return args

    def expressao(self, minimo=0):
        token = self.atual()
        if token in ("+", "-"):
            self.pegar()
            no = ("unario", token, self.expressao(30))
        elif re.fullmatch(r"\d+(?:\.\d+)?", token):
            if len(token) > 1 and token.startswith("0") and token[1] != ".":
                raise NaoSuportado("Literais numéricos com zero inicial não são suportados.")
            no = ("numero", float(self.pegar()))
        elif token == "function":
            self.pegar()
            no = self.funcao()
        elif token == "(":
            self.pegar(); no = self.expressao(); self.pegar(")")
        else:
            no = ("nome", self.nome())
        while True:
            op = self.atual()
            if op == "(" and minimo <= 40:
                self.pegar(); args = self.argumentos(); self.pegar(")")
                no = ("chamada", no, args)
                continue
            prioridade = {"+": 10, "-": 10, "*": 20, "/": 20}.get(op, -1)
            if prioridade < minimo:
                break
            self.pegar()
            no = ("binario", op, no, self.expressao(prioridade + 1))
        return no


VAZIO = object()


class Escopo:
    def __init__(self, pai=None):
        self.pai, self.valores = pai, {}

    def ler(self, nome):
        if nome in self.valores:
            valor = self.valores[nome]
            if valor is VAZIO:
                raise NaoSuportado(f"{nome} acessado antes da inicialização (zona morta temporal).")
            return valor
        if self.pai:
            return self.pai.ler(nome)
        raise NaoSuportado(f"Nome não declarado: {nome}.")


@dataclass
class Funcao:
    params: list
    corpo: list
    ambiente: Escopo


class Retorno(Exception):
    def __init__(self, valor):
        self.valor = valor


def numero(valor):
    if not isinstance(valor, float) or not math.isfinite(valor):
        raise NaoSuportado("Somente valores numéricos finitos são suportados nesta operação.")
    return valor


def formatar(valor):
    valor = numero(valor)
    return str(int(valor)) if valor.is_integer() else str(valor)


class Avaliador:
    def __init__(self):
        self.passos = 0
        self.saidas = []
        self.eventos = []
        self.global_ = Escopo()
        self.fechamentos = 0

    def passo(self):
        self.passos += 1
        if self.passos > 2000:
            raise NaoSuportado("Limite de 2.000 passos de análise atingido.")

    def bloco(self, nos, escopo):
        for no in nos:
            if no[0] in ("declaracao", "funcao"):
                if no[1] in escopo.valores:
                    raise NaoSuportado(f"Declaração duplicada: {no[1]}.")
                escopo.valores[no[1]] = VAZIO
        for no in nos:
            if no[0] == "funcao":
                escopo.valores[no[1]] = self.expr(no[2], escopo)
        for no in nos:
            self.passo()
            if no[0] == "declaracao":
                valor = self.expr(no[2], escopo)
                escopo.valores[no[1]] = valor
                if isinstance(valor, float):
                    local = "global" if escopo.pai is None else "local"
                    self.eventos.append(f"`{no[1]}` recebe {formatar(valor)} no escopo {local}.")
            elif no[0] == "retorno":
                raise Retorno(self.expr(no[1], escopo))
            elif no[0] == "console":
                self.saidas.append(" ".join(formatar(self.expr(a, escopo)) for a in no[1]))

    def expr(self, no, escopo):
        self.passo()
        tipo = no[0]
        if tipo == "numero":
            return no[1]
        if tipo == "nome":
            return escopo.ler(no[1])
        if tipo == "lambda":
            if escopo.pai:
                self.fechamentos += 1
            return Funcao(no[1], no[2], escopo)
        if tipo == "unario":
            n = numero(self.expr(no[2], escopo))
            return -n if no[1] == "-" else n
        if tipo == "binario":
            a, b = numero(self.expr(no[2], escopo)), numero(self.expr(no[3], escopo))
            if no[1] == "/" and b == 0:
                raise NaoSuportado("Divisão por zero está fora da análise numérica finita.")
            valor = {"+": lambda: a + b, "-": lambda: a - b, "*": lambda: a * b, "/": lambda: a / b}[no[1]]()
            return numero(valor)
        if tipo == "chamada":
            funcao = self.expr(no[1], escopo)
            if not isinstance(funcao, Funcao):
                raise NaoSuportado("Tentativa de chamar um valor que não é função.")
            args = [self.expr(a, escopo) for a in no[2]]
            if len(args) != len(funcao.params):
                raise NaoSuportado("Chamadas com parâmetros ausentes ou extras não são suportadas.")
            local = Escopo(funcao.ambiente)
            local.valores.update(zip(funcao.params, args))
            try:
                self.bloco(funcao.corpo, local)
            except Retorno as r:
                return r.valor
            raise NaoSuportado("Função sem retorno explícito não é suportada.")
        raise NaoSuportado("Expressão desconhecida.")


def avaliar(codigo):
    try:
        nos = Parser(codigo).programa()
        avaliador = Avaliador()
        avaliador.bloco(nos, avaliador.global_)
        return nos, avaliador
    except RecursionError as erro:
        raise NaoSuportado("Profundidade de análise excedida.") from erro


def analisar(codigo, instrucao):
    from .vetorizador import remover_acentos
    try:
        nos, a = avaliar(codigo)
        texto = "Análise local de JavaScript (subconjunto numérico, sem executar no navegador).\n\n"
        texto += "Saída prevista no console:\n```text\n" + ("\n".join(a.saidas) or "(nenhuma impressão)") + "\n```\n\n"
        texto += "\n".join(a.eventos[:20])
        texto += "\n\nConceitos: declarações let/const, expressões e escopo léxico. Cada função procura nomes no ambiente em que foi definida. Variáveis locais podem sombrear nomes externos sem alterá-los."
        if a.fechamentos:
            texto += " Uma closure mantém acesso ao ambiente externo mesmo depois que a função que a criou retorna. Chamadas encadeadas como `f()()` primeiro obtêm a função e depois chamam essa função."
        norm = remover_acentos(instrucao.lower())
        alvo = re.search(r"\b(?:resultado|valor)\s+(?:seja|ser|fique|igual a)\s*(-?\d+(?:\.\d+)?)", norm)
        if re.search(r"\b(altere|alterar|modifique|modificar|mude|ajuste)\b", norm):
            if not alvo:
                texto += "\n\nPara propor a alteração, diga qual valor numérico `resultado` deve ter."
            else:
                declaracao = next((n for n in nos if n[0] == "declaracao" and n[1] == "resultado"), None)
                if declaracao is None:
                    texto += "\n\nAinda só proponho essa transformação para uma declaração global chamada `resultado`. Não modifiquei o código."
                else:
                    desejado = float(alvo[1])
                    delta = numero(desejado) - numero(a.global_.ler("resultado"))
                    inicio, fim = declaracao[4:6]
                    expressao = codigo[inicio:fim]
                    novo = codigo[:inicio] + f"({expressao}) + ({formatar(delta)})" + codigo[fim:]
                    _, validacao = avaliar(novo)
                    if validacao.global_.ler("resultado") != desejado:
                        raise NaoSuportado("Não consegui verificar a transformação proposta.")
                    texto += f"\n\nUma solução é ajustar o valor após a chamada, sem modificar nenhuma função:\n```javascript\n{novo}\n```\nA expressão original vale {formatar(a.global_.ler('resultado'))}; o ajuste de {formatar(delta)} produz {formatar(desejado)}. A closure continua igual."
        return texto
    except (NaoSuportado, OverflowError) as erro:
        return f"Reconheci um pedido de análise de JavaScript, mas não posso prever a saída deste trecho com segurança: {erro}\n\nMeu analisador local cobre let/const com inicializador, funções com return, closures, chamadas, aritmética numérica e console.log, com ponto e vírgula. Ainda não cobre objetos, arrays, strings, loops, async, DOM ou atribuições posteriores. Posso explicar o conceito se você fizer uma pergunta específica."
