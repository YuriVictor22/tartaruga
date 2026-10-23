"""Primitivas pequenas para persistir dados locais sem arquivos pela metade."""

import json
import os
import tempfile
from pathlib import Path
from typing import Any


def gravar_json_atomico(caminho: Path, dados: Any) -> None:
    """Grava JSON em arquivo temporário e substitui o destino de uma vez."""
    caminho = Path(caminho)
    caminho.parent.mkdir(parents=True, exist_ok=True)
    temporario: Path | None = None
    try:
        with tempfile.NamedTemporaryFile(
            "w", encoding="utf-8", dir=caminho.parent,
            prefix=f".{caminho.name}.", suffix=".tmp", delete=False,
        ) as arquivo:
            temporario = Path(arquivo.name)
            json.dump(dados, arquivo, ensure_ascii=False, indent=2)
            arquivo.flush()
            os.fsync(arquivo.fileno())
        os.replace(temporario, caminho)
    except BaseException:
        if temporario is not None:
            temporario.unlink(missing_ok=True)
        raise


def gravar_bytes_atomico(caminho: Path, dados: bytes) -> None:
    """Versão binária usada na restauração de backups."""
    caminho = Path(caminho)
    caminho.parent.mkdir(parents=True, exist_ok=True)
    temporario: Path | None = None
    try:
        with tempfile.NamedTemporaryFile(
            "wb", dir=caminho.parent, prefix=f".{caminho.name}.",
            suffix=".tmp", delete=False,
        ) as arquivo:
            temporario = Path(arquivo.name)
            arquivo.write(dados)
            arquivo.flush()
            os.fsync(arquivo.fileno())
        os.replace(temporario, caminho)
    except BaseException:
        if temporario is not None:
            temporario.unlink(missing_ok=True)
        raise
