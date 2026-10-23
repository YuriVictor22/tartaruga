"""Exportação e restauração validada dos dados locais da Tartaruga."""

import json
import shutil
import tempfile
from datetime import datetime, timezone
from pathlib import Path, PurePosixPath
from zipfile import ZIP_DEFLATED, BadZipFile, ZipFile

from .caminhos import gravavel
from .persistencia import gravar_bytes_atomico

PASTAS = ("historico", "workspace", "projetos")
ARQUIVOS = ("dados_aprendidos.json", "configuracoes.json")
LIMITE_ARQUIVO = 50 * 1024 * 1024
LIMITE_TOTAL = 500 * 1024 * 1024


def _raiz() -> Path:
    return gravavel()


def exportar(destino: Path, raiz: Path | None = None) -> dict:
    raiz = Path(raiz or _raiz()).resolve()
    destino = Path(destino)
    itens: list[str] = []
    with ZipFile(destino, "w", ZIP_DEFLATED) as pacote:
        for nome in ARQUIVOS:
            caminho = raiz / nome
            if caminho.is_file():
                pacote.write(caminho, nome)
                itens.append(nome)
        for pasta in PASTAS:
            base = raiz / pasta
            if not base.is_dir():
                continue
            for caminho in base.rglob("*"):
                if caminho.is_file():
                    relativo = caminho.relative_to(raiz).as_posix()
                    pacote.write(caminho, relativo)
                    itens.append(relativo)
        manifesto = {
            "formato": "tartaruga-backup",
            "versao": 1,
            "criado_em": datetime.now(timezone.utc).isoformat(),
            "itens": itens,
        }
        pacote.writestr("manifesto.json", json.dumps(manifesto, ensure_ascii=False, indent=2))
    return manifesto


def _validar_manifesto(manifesto) -> list[str]:
    """O manifesto vem de um arquivo externo: JSON VÁLIDO não garante o formato
    esperado (`null`, lista, itens que não são texto...). Tudo vira ValueError
    controlado, antes de qualquer gravação."""
    if not isinstance(manifesto, dict):
        raise ValueError("O arquivo não contém um manifesto válido.")
    versao = manifesto.get("versao")
    # `type(...) is int`: em Python `True == 1` e `1.0 == 1`, e nenhum dos dois é a versão 1.
    if manifesto.get("formato") != "tartaruga-backup" or type(versao) is not int or versao != 1:
        raise ValueError("Versão de backup não reconhecida.")
    itens = manifesto.get("itens")
    if not isinstance(itens, list) or not all(isinstance(item, str) for item in itens):
        raise ValueError("Manifesto inválido: a lista de itens deve conter apenas textos.")
    if len(set(itens)) != len(itens):
        raise ValueError("Manifesto inválido: item duplicado.")
    return itens


def _gravar_com_rollback(raiz: Path, preparados: list[tuple[Path, bytes]]) -> None:
    """Grava todos os itens como uma TRANSAÇÃO: se qualquer gravação falhar
    (disco cheio, permissão, Ctrl+C), volta ao estado anterior.

    `gravar_bytes_atomico` só garante cada ARQUIVO isoladamente; sem isto, uma
    falha na segunda gravação deixaria a primeira já restaurada (achado em
    revisão independente). Antes de gravar, os arquivos que serão
    sobrescritos são copiados para um staging (`.restauracao-*`, criado e
    removido aqui mesmo). No rollback os originais voltam, o que era novo é
    apagado e as pastas criadas pela restauração somem.
    """
    raiz.mkdir(parents=True, exist_ok=True)
    staging = Path(tempfile.mkdtemp(prefix=".restauracao-", dir=raiz))
    anteriores: list[tuple[Path, Path | None]] = []
    pastas_criadas: list[Path] = []
    preservar_staging = False
    try:
        for destino, dados in preparados:
            faltando = []
            pasta = destino.parent
            while not pasta.exists():
                faltando.append(pasta)
                pasta = pasta.parent
            pastas_criadas.extend(reversed(faltando))
            copia = None
            if destino.exists():
                copia = staging / f"{len(anteriores)}.original"
                shutil.copy2(destino, copia)
            anteriores.append((destino, copia))
            gravar_bytes_atomico(destino, dados)
    except BaseException as erro:
        falhas = []
        for destino, copia in reversed(anteriores):
            try:
                if copia is not None:
                    original = copia.read_bytes()
                    if destino.exists() and destino.read_bytes() == original:
                        continue  # a gravação que falhou não chegou a alterá-lo
                    gravar_bytes_atomico(destino, original)
                else:
                    destino.unlink(missing_ok=True)
            except BaseException as falha:  # inclui Ctrl+C/SystemExit: continua revertendo o resto
                falhas.append(f"{destino.name}: {falha}")
        for pasta in reversed(pastas_criadas):
            try:
                pasta.rmdir()
            except OSError:
                pass
        if falhas:
            # O staging é a ÚNICA cópia dos originais: apagá-lo agora destruiria
            # a recuperação manual (achado na 2ª revisão). Só some
            # quando tudo deu certo, ou o rollback foi completo.
            preservar_staging = True
            raise RuntimeError(
                "A restauração falhou e o rollback também: os dados podem estar "
                "incompletos (" + "; ".join(falhas) + "). As cópias dos arquivos "
                f"originais foram PRESERVADAS em: {staging}"
            ) from erro
        raise
    finally:
        if not preservar_staging:
            shutil.rmtree(staging, ignore_errors=True)


def restaurar(origem: Path, raiz: Path | None = None) -> dict:
    raiz = Path(raiz or _raiz()).resolve()
    try:
        pacote = ZipFile(origem, "r")
    except (OSError, BadZipFile) as erro:
        raise ValueError("Backup inválido ou ilegível.") from erro
    with pacote:
        # `manifesto.json` na raiz do zip precisa existir EXATAMENTE uma vez: o
        # ZipFile leria só um deles (o último) e qual vale seria ambíguo.
        if [i.filename for i in pacote.infolist()].count("manifesto.json") != 1:
            raise ValueError("O arquivo não contém um manifesto válido "
                             "(deve haver exatamente um manifesto.json).")
        try:
            manifesto = json.loads(pacote.read("manifesto.json"))
        except (KeyError, json.JSONDecodeError, UnicodeDecodeError) as erro:
            raise ValueError("O arquivo não contém um manifesto válido.") from erro
        permitidos = set(_validar_manifesto(manifesto))
        total = 0
        vistos: set[str] = set()
        preparados: list[tuple[Path, bytes]] = []
        for info in pacote.infolist():
            if info.filename == "manifesto.json" or info.is_dir():
                continue
            relativo = PurePosixPath(info.filename)
            topo = relativo.parts[0] if relativo.parts else ""
            # Itens de PASTA precisam ter algo DENTRO dela (>= 2 partes). Só
            # `topo in PASTAS` aceitava um item chamado exatamente
            # "historico", que virava um ARQUIVO onde o app espera uma pasta.
            valido = (len(relativo.parts) == 1 and topo in ARQUIVOS) or (
                topo in PASTAS and len(relativo.parts) > 1)
            if (not valido or info.filename not in permitidos or relativo.is_absolute()
                    or ".." in relativo.parts or info.file_size > LIMITE_ARQUIVO):
                raise ValueError(f"Item inseguro no backup: {info.filename}")
            if info.filename in vistos:
                raise ValueError(f"Item duplicado no backup: {info.filename}")
            vistos.add(info.filename)
            total += info.file_size
            if total > LIMITE_TOTAL:
                raise ValueError("Backup excede o limite de restauração.")
            destino = raiz.joinpath(*relativo.parts).resolve()
            if raiz != destino and raiz not in destino.parents:
                raise ValueError(f"Destino inseguro: {info.filename}")
            preparados.append((destino, pacote.read(info)))
        ausentes = permitidos - vistos
        if ausentes:
            # Backup truncado: o manifesto promete o que o zip não tem.
            raise ValueError("Backup incompleto: faltam " + ", ".join(sorted(ausentes)[:5])
                             + (" e outros" if len(ausentes) > 5 else "") + ".")
        _gravar_com_rollback(raiz, preparados)
    return {"itens": len(preparados), "manifesto": manifesto}
