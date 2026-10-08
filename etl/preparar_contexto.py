"""
Dados de comparação para a análise de Itapira: totais por município (SP inteiro e, para
Presidente, o Brasil inteiro), em 2026 e 2022, além do eleitorado apto por município.

Saídas em data/contexto/:
  votos_mun_2026.parquet    CD_MUNICIPIO x CD_CARGO x NR_VOTAVEL -> QT_VOTOS (SP: todos os cargos;
                            demais UFs: só Presidente)
  votos_mun_2022.parquet    Presidente 2022, 1º e 2º turno, por município (Brasil)
  candidatos_2026.parquet   CD_CARGO x NR_VOTAVEL -> NM_VOTAVEL, nome de urna, partido e situação
                            (cadastro de candidaturas do TSE; SP e Presidente)
  municipios.parquet        CD_MUNICIPIO -> NM_MUNICIPIO, SG_UF, aptos 2026 e 2022

Uso:  python etl/preparar_contexto.py                  (lê os zips de data/raw; leva alguns minutos)
      python etl/preparar_contexto.py --candidatos     (só atualiza o cadastro de candidaturas)
"""
import sys
import zipfile
from pathlib import Path

import pandas as pd

from preparar_dados import CDN, baixar

ROOT = Path(__file__).resolve().parent.parent
OUT = ROOT / "data" / "contexto"

CHAVE = ["SG_UF", "CD_MUNICIPIO", "NM_MUNICIPIO", "NR_TURNO", "CD_CARGO", "NR_VOTAVEL",
         "NM_VOTAVEL"]


def somar_votos(zip_path: Path, membro: str, filtro=None) -> pd.DataFrame:
    """Soma QT_VOTOS por município x cargo x votável lendo o CSV do zip em blocos."""
    partes = []
    with zipfile.ZipFile(zip_path) as z, z.open(membro) as f:
        leitor = pd.read_csv(f, sep=";", encoding="latin-1", usecols=CHAVE + ["QT_VOTOS"],
                             dtype={c: "string" for c in ["SG_UF", "NM_MUNICIPIO", "NM_VOTAVEL"]},
                             chunksize=2_000_000)
        for i, bloco in enumerate(leitor):
            if filtro is not None:
                bloco = bloco[filtro(bloco)]
            partes.append(bloco.groupby(CHAVE, observed=True)["QT_VOTOS"].sum().reset_index())
            print(f"  {membro}: bloco {i + 1}", end="\r")
    print()
    df = pd.concat(partes).groupby(CHAVE, observed=True)["QT_VOTOS"].sum().reset_index()
    for c in ["CD_MUNICIPIO", "NR_TURNO", "CD_CARGO", "NR_VOTAVEL", "QT_VOTOS"]:
        df[c] = df[c].astype("int64")
    return df


def aptos(zip_path: Path, membro: str) -> pd.Series:
    with zipfile.ZipFile(zip_path) as z, z.open(membro) as f:
        df = pd.read_csv(f, sep=";", encoding="latin-1",
                         usecols=["NR_TURNO", "CD_MUNICIPIO", "QT_ELEITOR_SECAO"])
    df = df[df["NR_TURNO"].astype(int) == 1]
    return df.groupby(df["CD_MUNICIPIO"].astype(int))["QT_ELEITOR_SECAO"].sum()


def candidaturas() -> pd.DataFrame:
    """Nome de urna, partido e situação (eleito, 2º turno...) de SP e de Presidente."""
    zp = baixar(f"{CDN}/consulta_cand/consulta_cand_2026.zip")
    with zipfile.ZipFile(zp) as z, z.open("consulta_cand_2026_BRASIL.csv") as f:
        c = pd.read_csv(f, sep=";", encoding="latin-1",
                        usecols=["NR_TURNO", "SG_UF", "CD_CARGO", "NR_CANDIDATO", "NM_URNA_CANDIDATO",
                                 "SG_PARTIDO", "DS_SIT_TOT_TURNO"])
    c = c[(c["NR_TURNO"] == 1) & c["SG_UF"].isin(["SP", "BR"])]
    c = c.rename(columns={"NR_CANDIDATO": "NR_VOTAVEL", "NM_URNA_CANDIDATO": "NM_URNA",
                          "DS_SIT_TOT_TURNO": "SITUACAO"})
    return c[["CD_CARGO", "NR_VOTAVEL", "NM_URNA", "SG_PARTIDO", "SITUACAO"]].drop_duplicates(
        ["CD_CARGO", "NR_VOTAVEL"])


def salvar_candidatos(cand_votos: pd.DataFrame) -> None:
    cand = cand_votos.merge(candidaturas(), on=["CD_CARGO", "NR_VOTAVEL"], how="left")
    cand.to_parquet(OUT / "candidatos_2026.parquet", index=False)
    print(f"Candidatos: {len(cand)} ({cand['NM_URNA'].notna().sum()} com nome de urna)")


def main() -> None:
    if "--candidatos" in sys.argv:
        atual = pd.read_parquet(OUT / "candidatos_2026.parquet")
        salvar_candidatos(atual[["CD_CARGO", "NR_VOTAVEL", "NM_VOTAVEL"]])
        return

    OUT.mkdir(parents=True, exist_ok=True)
    raw = ROOT / "data" / "raw"

    print("2026 - SP (todos os cargos)")
    sp = somar_votos(baixar(f"{CDN}/votacao_secao/votacao_secao_2026_SP.zip"),
                     "votacao_secao_2026_SP.csv")
    print("2026 - Presidente (Brasil)")
    br = somar_votos(baixar(f"{CDN}/votacao_secao/votacao_secao_2026_BR.zip"),
                     "votacao_secao_2026_BR.csv")
    br = br[br["SG_UF"] != "ZZ"]  # exterior fica de fora das comparações por município
    v26 = pd.concat([sp, br])

    print("2022 - Presidente (Brasil)")
    v22 = somar_votos(raw / "votacao_secao_2022_BR.zip", "votacao_secao_2022_BR.csv")
    v22 = v22[v22["SG_UF"] != "ZZ"]

    cand = (v26[["CD_CARGO", "NR_VOTAVEL", "NM_VOTAVEL"]].drop_duplicates(["CD_CARGO", "NR_VOTAVEL"])
            .sort_values(["CD_CARGO", "NR_VOTAVEL"]))
    salvar_candidatos(cand)

    mun = (pd.concat([v26, v22])[["CD_MUNICIPIO", "NM_MUNICIPIO", "SG_UF"]]
           .drop_duplicates("CD_MUNICIPIO").set_index("CD_MUNICIPIO"))
    mun["APTOS_2026"] = aptos(raw / "eleitorado_local_votacao_2026.zip",
                              "eleitorado_local_votacao_2026_BRASIL.csv")
    mun["APTOS_2022"] = aptos(raw / "eleitorado_local_votacao_2022.zip",
                              "eleitorado_local_votacao_2022.csv")
    mun.reset_index().to_parquet(OUT / "municipios.parquet", index=False)

    cols = ["CD_MUNICIPIO", "NR_TURNO", "CD_CARGO", "NR_VOTAVEL", "QT_VOTOS"]
    v26[cols].to_parquet(OUT / "votos_mun_2026.parquet", index=False)
    v22[cols].to_parquet(OUT / "votos_mun_2022.parquet", index=False)

    print(f"Municípios: {len(mun)} · linhas 2026: {len(v26):,} · linhas 2022: {len(v22):,}")
    for f in sorted(OUT.iterdir()):
        print(f"  {f.name}: {f.stat().st_size / 1e6:.1f} MB")


if __name__ == "__main__":
    main()
