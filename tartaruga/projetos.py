"""Projetos persistentes criados a partir de briefings de landing page."""
from dataclasses import asdict, dataclass, field
from datetime import datetime
from pathlib import Path
from uuid import uuid4

from .caminhos import gravavel
from .persistencia import gravar_json_atomico


@dataclass
class ProjetoLanding:
    id: str
    nome: str
    criado_em: str
    atualizado_em: str
    briefing: dict[str, str]
    origem_sessao: str = ""
    arquivos: list[str] = field(default_factory=list)
    revisoes: list[dict] = field(default_factory=list)
    testes: list[dict] = field(default_factory=list)
    publicacao: dict = field(default_factory=lambda: {"status": "nao_publicado", "destino": ""})

    def revisar(self, descricao: str) -> None:
        self.revisoes.append({"em": datetime.now().isoformat(timespec="seconds"), "descricao": descricao})
        self.atualizado_em = datetime.now().isoformat(timespec="seconds")

    def registrar_teste(self, nome: str, aprovado: bool, detalhe: str = "") -> None:
        self.testes.append({"em": datetime.now().isoformat(timespec="seconds"), "nome": nome,
                           "aprovado": bool(aprovado), "detalhe": detalhe})
        self.atualizado_em = datetime.now().isoformat(timespec="seconds")


class RepositorioProjetos:
    def __init__(self, pasta: Path | None = None):
        self.pasta = Path(pasta or gravavel("projetos"))
        self.pasta.mkdir(parents=True, exist_ok=True)

    def salvar(self, projeto: ProjetoLanding) -> Path:
        caminho = self.pasta / f"{projeto.id}.json"
        gravar_json_atomico(caminho, asdict(projeto))
        return caminho

    def carregar(self, identificador: str) -> ProjetoLanding | None:
        import json
        try:
            dados = json.loads((self.pasta / f"{identificador}.json").read_text(encoding="utf-8"))
            return ProjetoLanding(**dados)
        except (OSError, ValueError, TypeError):
            return None

    def listar(self) -> list[ProjetoLanding]:
        projetos = [p for caminho in sorted(self.pasta.glob("*.json"), reverse=True)
                    if (p := self.carregar(caminho.stem)) is not None]
        return projetos

    def criar_ou_atualizar(self, briefing: dict[str, str], origem_sessao: str = "") -> ProjetoLanding:
        existente = next((p for p in self.listar() if origem_sessao and p.origem_sessao == origem_sessao), None)
        agora = datetime.now().isoformat(timespec="seconds")
        if existente:
            existente.briefing = dict(briefing)
            existente.nome = briefing.get("negocio", existente.nome)
            existente.atualizado_em = agora
            existente.revisar("Briefing atualizado e confirmado.")
            self.salvar(existente)
            return existente
        projeto = ProjetoLanding(
            id=f"lp-{datetime.now():%Y%m%d-%H%M%S}-{uuid4().hex[:6]}",
            nome=briefing.get("negocio", "Landing page"), criado_em=agora,
            atualizado_em=agora, briefing=dict(briefing), origem_sessao=origem_sessao,
        )
        projeto.revisar("Projeto criado a partir do briefing confirmado.")
        self.salvar(projeto)
        return projeto
