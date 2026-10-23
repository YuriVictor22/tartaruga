"""Informações locais para identificar versão, dados e recursos ativos."""
import sys
from pathlib import Path

from . import __version__
from .caminhos import empacotado, gravavel, recurso


def coletar(assistente=None) -> dict:
    raiz = Path(sys.executable).resolve().parent if empacotado() else Path(__file__).resolve().parent.parent
    dados = {
        "versao": __version__, "empacotado": empacotado(), "raiz": str(raiz),
        "executavel": str(Path(sys.executable).resolve()),
        "historico": str(gravavel("historico")), "workspace": str(gravavel("workspace")),
    }
    try:
        import json
        manifesto = json.loads(recurso("versao.json").read_text(encoding="utf-8"))
        dados["distribuicao"] = manifesto.get("distribuicao", "desenvolvimento")
        dados["recursos"] = ", ".join(manifesto.get("recursos", []))
    except (OSError, ValueError, TypeError):
        dados["distribuicao"] = "não identificada"
    if assistente is not None:
        dados.update({"modo": assistente.modo, "topicos": len(assistente.base),
                      "termos": len(assistente.classificador.vocabulario),
                      "sessao": str(assistente.memoria.caminho_sessao or "nova")})
    return dados


def formatar(dados: dict) -> str:
    rotulos = {"versao": "Versão", "empacotado": "Executável empacotado", "raiz": "Pasta do aplicativo",
               "executavel": "Python/executável", "historico": "Histórico", "workspace": "Workspace",
               "modo": "Modo", "topicos": "Tópicos", "termos": "Termos", "sessao": "Sessão",
               "distribuicao": "Distribuição", "recursos": "Recursos"}
    return "\n".join(f"{rotulos.get(k, k)}: {v}" for k, v in dados.items())
