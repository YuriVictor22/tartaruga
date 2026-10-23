"""Preferências locais validadas e compatíveis com versões anteriores."""
import json
from dataclasses import asdict, dataclass
from pathlib import Path

from .caminhos import gravavel
from .persistencia import gravar_json_atomico

CAMINHO = gravavel("configuracoes.json")


@dataclass
class Configuracoes:
    modo_inicial: str = "tartaruga"
    retomar_conversa: bool = True
    tamanho_fonte: int = 13
    tema: str = "escuro"
    confirmar_execucao: bool = True
    semantica_ativa: bool = True

    @classmethod
    def carregar(cls, caminho: Path = CAMINHO):
        try:
            dados = json.loads(Path(caminho).read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError, TypeError):
            return cls()
        base = cls()
        if dados.get("modo_inicial") in {"tartaruga", "hibrido", "phi4mini"}:
            base.modo_inicial = dados["modo_inicial"]
        if type(dados.get("retomar_conversa")) is bool:
            base.retomar_conversa = dados["retomar_conversa"]
        if type(dados.get("tamanho_fonte")) is int and 10 <= dados["tamanho_fonte"] <= 24:
            base.tamanho_fonte = dados["tamanho_fonte"]
        if dados.get("tema") in {"escuro", "claro"}:
            base.tema = dados["tema"]
        for nome in ("confirmar_execucao", "semantica_ativa"):
            if type(dados.get(nome)) is bool:
                setattr(base, nome, dados[nome])
        return base

    def salvar(self, caminho: Path = CAMINHO) -> None:
        gravar_json_atomico(caminho, asdict(self))
