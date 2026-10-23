"""Registro local e anonimizado de falhas indicadas pelo usuário."""
import json
import re
from datetime import datetime
from pathlib import Path

from .caminhos import gravavel
from .persistencia import gravar_json_atomico

CAMINHO = gravavel("avaliacao", "falhas_reais.json")


def anonimizar(texto: str) -> str:
    texto = re.sub(r"```.*?```", "[CODIGO]", texto, flags=re.DOTALL)
    texto = re.sub(r"[\w.+-]+@[\w.-]+\.[A-Za-z]{2,}", "[EMAIL]", texto)
    texto = re.sub(r"https?://\S+", "[URL]", texto)
    texto = re.sub(r"(?<!\w)(?:\+?\d[\d ()-]{7,}\d)(?!\w)", "[TELEFONE]", texto)
    return " ".join(texto.split())[:1000]


def registrar(entrada: str, intencao_obtida: str, esperado: str, caminho: Path = CAMINHO) -> dict:
    registro = {"em": datetime.now().isoformat(timespec="seconds"),
                "entrada": anonimizar(entrada), "intencao_obtida": intencao_obtida,
                "esperado": esperado.strip()[:100]}
    try:
        atuais = json.loads(Path(caminho).read_text(encoding="utf-8"))
        if not isinstance(atuais, list):
            atuais = []
    except (OSError, json.JSONDecodeError):
        atuais = []
    atuais.append(registro)
    gravar_json_atomico(Path(caminho), atuais)
    return registro


def metricas(caminho: Path = CAMINHO) -> dict:
    try:
        itens = json.loads(Path(caminho).read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        itens = []
    por_intencao = {}
    for item in itens if isinstance(itens, list) else []:
        chave = item.get("intencao_obtida", "desconhecido")
        por_intencao[chave] = por_intencao.get(chave, 0) + 1
    return {"falhas": sum(por_intencao.values()), "por_intencao": por_intencao}
