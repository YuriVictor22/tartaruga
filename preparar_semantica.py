"""Baixa pesos safetensors de uma revisão fixa. Não executa código remoto."""
from concurrent.futures import ThreadPoolExecutor
import hashlib
import json
import shutil
import urllib.request
from tartaruga.semantica import MODELO, PASTA_MODELO

REVISAO = "e8f8c211226b894fcb81acc59f3b34ba3efd5f42"
ARQUIVOS = ["model.safetensors", "config.json", "config_sentence_transformers.json",
            "sentence_bert_config.json", "special_tokens_map.json", "tokenizer.json",
            "tokenizer_config.json", "sentencepiece.bpe.model", "unigram.json",
            "1_Pooling/config.json"]


def baixar(nome):
    destino = PASTA_MODELO / nome
    destino.parent.mkdir(parents=True, exist_ok=True)
    if not destino.exists():
        temporario = destino.with_suffix(destino.suffix + ".part")
        url = f"https://huggingface.co/{MODELO}/resolve/{REVISAO}/{nome}"
        try:
            with urllib.request.urlopen(url, timeout=120) as origem, temporario.open("wb") as saida:
                shutil.copyfileobj(origem, saida, length=1024 * 1024)
            temporario.replace(destino)
        except BaseException:
            # A conexão pode cair DEPOIS do primeiro bloco: o .part parcial não
            # pode ficar como se fosse um download em andamento.
            temporario.unlink(missing_ok=True)
            raise
    with destino.open("rb") as arquivo:
        hash_arquivo = hashlib.sha256()
        for bloco in iter(lambda: arquivo.read(1024 * 1024), b""):
            hash_arquivo.update(bloco)
        digest = hash_arquivo.hexdigest()
    print(f"Pronto: {nome}", flush=True)
    return nome, digest


def main():
    print(f"Preparando {MODELO} em {PASTA_MODELO}", flush=True)
    PASTA_MODELO.mkdir(parents=True, exist_ok=True)
    with ThreadPoolExecutor(max_workers=3) as pool:
        hashes = dict(pool.map(baixar, ARQUIVOS))
    # O marcador consultado pelo programa só fica disponível ao final.
    nome, digest = baixar("modules.json")
    hashes[nome] = digest
    (PASTA_MODELO / "origem.json").write_text(json.dumps({"modelo": MODELO, "revisao": REVISAO, "sha256": hashes}, indent=2), encoding="utf-8")
    print("Modelo instalado. A inferência da Tartaruga será local.", flush=True)


if __name__ == "__main__":
    main()
