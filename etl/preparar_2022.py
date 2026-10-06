"""
Eleição presidencial de 2022 (1º e 2º turno) em Itapira, para comparar com 2026.

Saídas em data/itapira/:
  votos_2022.parquet    votos para Presidente por seção x turno x candidato
  secoes_2022.csv       seção -> local de votação (cadastro de 2022)

Uso:  python etl/preparar_2022.py
"""
import pandas as pd

from preparar_dados import CDN, CD_MUNICIPIO, NR_ZONA, OUT, baixar, filtrar_municipio

VOTACAO = (f"{CDN}/votacao_secao/votacao_secao_2022_BR.zip", "votacao_secao_2022_BR.csv")
LOCAIS = (f"{CDN}/eleitorado_locais_votacao/eleitorado_local_votacao_2022.zip",
          "eleitorado_local_votacao_2022.csv")


def main() -> None:
    url, membro = LOCAIS
    sec = filtrar_municipio(baixar(url), membro, "CD_MUNICIPIO")
    sec = sec[["NR_TURNO", "NR_ZONA", "NR_SECAO", "NR_LOCAL_VOTACAO", "NM_LOCAL_VOTACAO",
               "NM_BAIRRO", "QT_ELEITOR_SECAO"]]
    for c in ["NR_TURNO", "NR_ZONA", "NR_SECAO", "NR_LOCAL_VOTACAO", "QT_ELEITOR_SECAO"]:
        sec[c] = sec[c].astype(int)
    sec = sec[(sec["NR_ZONA"] == NR_ZONA) & (sec["NR_TURNO"] == 1)].drop(columns="NR_TURNO")
    sec.to_csv(OUT / "secoes_2022.csv", index=False, encoding="utf-8-sig")
    print(f"2022 - seções: {len(sec)}, locais: {sec['NR_LOCAL_VOTACAO'].nunique()}, "
          f"eleitores: {sec['QT_ELEITOR_SECAO'].sum()}")

    url, membro = VOTACAO
    v = filtrar_municipio(baixar(url), membro, "CD_MUNICIPIO")
    v = v[["NR_TURNO", "NR_ZONA", "NR_SECAO", "DS_CARGO", "NR_VOTAVEL", "NM_VOTAVEL",
           "QT_VOTOS", "NR_LOCAL_VOTACAO"]]
    for c in ["NR_TURNO", "NR_ZONA", "NR_SECAO", "NR_VOTAVEL", "QT_VOTOS", "NR_LOCAL_VOTACAO"]:
        v[c] = v[c].astype(int)
    v = v[(v["NR_ZONA"] == NR_ZONA) & (v["DS_CARGO"].str.upper() == "PRESIDENTE")]
    v.to_parquet(OUT / "votos_2022.parquet", index=False)
    print(v.groupby(["NR_TURNO", "NM_VOTAVEL"])["QT_VOTOS"].sum()
           .sort_values(ascending=False).groupby(level=0).head(4).to_string())


if __name__ == "__main__":
    main()
