"""
Baixa os dados abertos do TSE (eleição 2026, 1º turno) e gera os arquivos de Itapira.

Saídas em data/itapira/:
  votos_secao.parquet   votos por seção x cargo x candidato
  perfil_secao.parquet  eleitores aptos por seção x gênero/idade/escolaridade/estado civil/raça
  secoes.csv            seção -> local de votação -> bairro (TSE) + coordenadas
Saída em mapping/:
  bairros.csv           um local de votação por linha; coluna BAIRRO (e coordenadas)
                        editável à mão (só é criado se ainda não existir)

Uso:  python etl/preparar_dados.py
"""
import csv
import io
import shutil
import urllib.request
import zipfile
from pathlib import Path

import pandas as pd

ANO = 2026
UF = "SP"
CD_MUNICIPIO = "65536"  # ITAPIRA
NR_ZONA = 54

ROOT = Path(__file__).resolve().parent.parent
RAW = ROOT / "data" / "raw"
OUT = ROOT / "data" / "itapira"
MAPPING = ROOT / "mapping" / "bairros.csv"

CDN = "https://cdn.tse.jus.br/estatistica/sead/odsele"
# Votação: o arquivo da UF traz os cargos estaduais/senado; o "_BR" traz Presidente.
VOTACAO = [
    (f"{CDN}/votacao_secao/votacao_secao_{ANO}_{uf}.zip", f"votacao_secao_{ANO}_{uf}.csv")
    for uf in (UF, "BR")
]
PERFIL = (f"{CDN}/perfil_eleitor_secao/perfil_eleitor_secao_{ANO}_{UF}.zip",
          f"perfil_eleitor_secao_{ANO}_{UF}.csv")
LOCAIS = (f"{CDN}/eleitorado_locais_votacao/eleitorado_local_votacao_{ANO}.zip",
          f"eleitorado_local_votacao_{ANO}_{UF}.csv")


def baixar(url: str) -> Path:
    destino = RAW / url.rsplit("/", 1)[1]
    if not destino.exists():
        print(f"Baixando {url} ...")
        RAW.mkdir(parents=True, exist_ok=True)
        tmp = destino.with_suffix(".part")
        # o CDN do TSE derruba conexões sem User-Agent de navegador
        req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
        with urllib.request.urlopen(req) as resp, open(tmp, "wb") as f:
            shutil.copyfileobj(resp, f, length=1 << 20)
        tmp.rename(destino)
    return destino


def filtrar_municipio(zip_path: Path, membro: str, coluna: str) -> pd.DataFrame:
    """Lê o CSV de dentro do zip em streaming e mantém só as linhas do município.

    O CSV de votação de SP tem ~5 GB, então filtramos linha a linha antes do pandas.
    """
    with zipfile.ZipFile(zip_path) as z, z.open(membro) as f:
        texto = io.TextIOWrapper(f, encoding="latin-1", newline="")
        cabecalho = next(csv.reader([texto.readline()], delimiter=";"))
        idx = cabecalho.index(coluna)
        alvo = CD_MUNICIPIO
        linhas = []
        for linha in texto:
            # filtro rápido por substring antes do parse completo
            if alvo not in linha:
                continue
            campos = next(csv.reader([linha], delimiter=";"))
            if campos[idx] == alvo:
                linhas.append(campos)
    return pd.DataFrame(linhas, columns=cabecalho)


def preparar_votos(zip_path: Path, membro: str) -> pd.DataFrame:
    df = filtrar_municipio(zip_path, membro, "CD_MUNICIPIO")
    df = df[["NR_TURNO", "NR_ZONA", "NR_SECAO", "CD_CARGO", "DS_CARGO",
             "NR_VOTAVEL", "NM_VOTAVEL", "QT_VOTOS", "SQ_CANDIDATO",
             "NR_LOCAL_VOTACAO", "NM_LOCAL_VOTACAO"]].copy()
    for c in ["NR_TURNO", "NR_ZONA", "NR_SECAO", "CD_CARGO", "NR_VOTAVEL",
              "QT_VOTOS", "NR_LOCAL_VOTACAO"]:
        df[c] = df[c].astype(int)
    return df


def preparar_secoes(zip_path: Path, membro: str) -> pd.DataFrame:
    df = filtrar_municipio(zip_path, membro, "CD_MUNICIPIO")
    df = df[["NR_TURNO", "NR_ZONA", "NR_SECAO", "DS_TIPO_SECAO_AGREGADA",
             "NR_SECAO_PRINCIPAL", "NR_LOCAL_VOTACAO", "NM_LOCAL_VOTACAO",
             "DS_ENDERECO", "NM_BAIRRO", "NR_CEP", "NR_LATITUDE", "NR_LONGITUDE",
             "DS_SITU_SECAO", "QT_ELEITOR_SECAO"]].copy()
    for c in ["NR_TURNO", "NR_ZONA", "NR_SECAO", "NR_SECAO_PRINCIPAL",
              "NR_LOCAL_VOTACAO", "QT_ELEITOR_SECAO"]:
        df[c] = df[c].astype(int)
    for c in ["NR_LATITUDE", "NR_LONGITUDE"]:
        df[c] = pd.to_numeric(df[c].str.replace(",", "."), errors="coerce")
    df = df[df["NR_TURNO"] == 1].drop(columns="NR_TURNO")
    return df.sort_values("NR_SECAO").reset_index(drop=True)


def preparar_perfil(zip_path: Path, membro: str) -> pd.DataFrame:
    df = filtrar_municipio(zip_path, membro, "CD_MUNICIPIO")
    df = df[["NR_ZONA", "NR_SECAO", "DS_GENERO", "DS_ESTADO_CIVIL", "CD_FAIXA_ETARIA",
             "DS_FAIXA_ETARIA", "CD_GRAU_ESCOLARIDADE", "DS_GRAU_ESCOLARIDADE",
             "DS_RACA_COR", "QT_ELEITORES"]].copy()
    for c in ["NR_ZONA", "NR_SECAO", "CD_FAIXA_ETARIA", "CD_GRAU_ESCOLARIDADE", "QT_ELEITORES"]:
        df[c] = df[c].astype(int)
    return df


def gerar_mapeamento(secoes: pd.DataFrame) -> None:
    """Cria mapping/bairros.csv para revisão manual (não sobrescreve)."""
    if MAPPING.exists():
        print(f"{MAPPING.relative_to(ROOT)} já existe - mantendo suas edições.")
        return
    locais = (secoes.groupby(["NR_LOCAL_VOTACAO", "NM_LOCAL_VOTACAO", "DS_ENDERECO",
                              "NM_BAIRRO", "NR_LATITUDE", "NR_LONGITUDE"], dropna=False)
                    .agg(QT_SECOES=("NR_SECAO", "count"),
                         QT_ELEITORES=("QT_ELEITOR_SECAO", "sum"))
                    .reset_index()
                    .rename(columns={"NM_BAIRRO": "BAIRRO_TSE"}))
    locais["BAIRRO"] = locais["BAIRRO_TSE"].str.strip().str.title()
    MAPPING.parent.mkdir(parents=True, exist_ok=True)
    locais.sort_values("BAIRRO").to_csv(MAPPING, index=False, encoding="utf-8-sig")
    print(f"Criado {MAPPING.relative_to(ROOT)} com {len(locais)} locais - revise BAIRRO.")


def main() -> None:
    OUT.mkdir(parents=True, exist_ok=True)

    url, membro = LOCAIS
    secoes = preparar_secoes(baixar(url), membro)
    secoes = secoes[secoes["NR_ZONA"] == NR_ZONA]
    secoes.to_csv(OUT / "secoes.csv", index=False, encoding="utf-8-sig")
    print(f"Seções: {len(secoes)} ({(secoes['DS_TIPO_SECAO_AGREGADA'] != 'Principal').sum()} agregadas), "
          f"locais: {secoes['NR_LOCAL_VOTACAO'].nunique()}, "
          f"eleitores: {secoes['QT_ELEITOR_SECAO'].sum()}")
    gerar_mapeamento(secoes)

    url, membro = PERFIL
    print("Filtrando perfil do eleitorado...")
    perfil = preparar_perfil(baixar(url), membro)
    perfil = perfil[perfil["NR_ZONA"] == NR_ZONA]
    perfil.to_parquet(OUT / "perfil_secao.parquet", index=False)
    print(f"Perfil: {perfil['QT_ELEITORES'].sum()} eleitores em {perfil['NR_SECAO'].nunique()} seções")

    print("Filtrando votos de Itapira (arquivos grandes, pode levar alguns minutos)...")
    votos = pd.concat([preparar_votos(baixar(url), membro) for url, membro in VOTACAO])
    votos = votos[votos["NR_ZONA"] == NR_ZONA].drop_duplicates()
    votos.to_parquet(OUT / "votos_secao.parquet", index=False)
    print(f"Votos: {len(votos)} linhas, {votos['NR_SECAO'].nunique()} seções com urna, "
          f"turnos {sorted(votos['NR_TURNO'].unique())}")
    print(votos.groupby("DS_CARGO")["QT_VOTOS"].sum().to_string())


if __name__ == "__main__":
    main()
