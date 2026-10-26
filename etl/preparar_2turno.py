"""
2º turno presidencial de 2026 em Itapira, seção a seção, a partir dos boletins de urna (BU)
publicados pelo TSE em resultados.tse.jus.br (antes de sair o arquivo de dados abertos).

Passos:
  1. baixa o BU de cada seção no 1º turno (pleito 3220) e no 2º turno (pleito 3221);
  2. valida a leitura: os votos do BU do 1º turno têm de bater, número por número, com o arquivo
     oficial de votação por seção (data/itapira/votos_secao.parquet) - se não baterem, o script para;
  3. grava os resultados do 2º turno por seção e os totais de referência (vizinhas, SP, Brasil).

Saídas em data/itapira/:
  votos_2t.parquet    NR_SECAO x NR_VOTAVEL (13, 22, 95 branco, 96 nulo) -> QT_VOTOS
  secoes_2t.csv       NR_SECAO -> aptos, comparecimento (1º e 2º turno), abertura/encerramento da urna
  transferencias_2t.parquet  estimativa de transferência de votos 1º -> 2º turno (com intervalos)
Saída em data/contexto/:
  ref_2t.parquet      votos de 13/22, brancos, nulos, comparecimento e aptos no 2º turno:
                      Itapira, vizinhas, SP, Brasil
  mun_2t_sp.parquet   o mesmo para cada um dos 645 municípios de SP

Uso:  python etl/preparar_2turno.py
"""
import json
import sys
import time
import urllib.request
from pathlib import Path

import pandas as pd

import boletim_urna as bu

ROOT = Path(__file__).resolve().parent.parent
RAW = ROOT / "data" / "raw" / "bu"
OUT = ROOT / "data" / "itapira"
CTX = ROOT / "data" / "contexto"
BASE = "https://resultados.tse.jus.br/oficial/ele2026"
PLEITOS = {1: 3220, 2: 3221}
ELEICAO_PRES = {1: 6257, 2: 6258}
UF, MUN, ZONA = "sp", 65536, 54


def baixar(url: str, tentativas: int = 4) -> bytes:
    for t in range(tentativas):
        try:
            req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
            with urllib.request.urlopen(req, timeout=60) as r:
                return r.read()
        except Exception:
            if t == tentativas - 1:
                raise
            time.sleep(2 * (t + 1))


def boletim(turno: int, secao: int) -> dict:
    """BU de uma seção, já extraído (com cache em data/raw/bu)."""
    cache = RAW / f"t{turno}_s{secao:04d}.json"
    if cache.exists():
        return json.loads(cache.read_text())
    p = PLEITOS[turno]
    pasta = f"{BASE}/arquivo-urna/{p}/dados/{UF}/{MUN}/{ZONA:04d}/{secao:04d}"
    aux = json.loads(baixar(f"{pasta}/p00{p}-{UF}-m{MUN}-z{ZONA:04d}-s{secao:04d}-aux.json"))
    h = next(x for x in aux["hashes"] if x["st"] in ("Totalizado", "Recebido"))
    nome = next(a["nm"] for a in h["arq"] if a["tp"] == "bu")
    dados = bu.extrair(baixar(f"{pasta}/{h['hash']}/{nome}"))
    dados["status"] = h["st"]
    RAW.mkdir(parents=True, exist_ok=True)
    cache.write_text(json.dumps(dados))
    return dados


def votos_pres(b: dict, turno: int):
    e = next(x for x in b["eleicoes"] if x["eleicao"] == ELEICAO_PRES[turno])
    c = next(x for x in e["cargos"] if x["cargo"] == 1)
    linhas = [({"branco": 95, "nulo": 96}.get(v["tipo"], v["numero"]), v["qtd"]) for v in c["votos"]]
    return e["aptos"], c["comparecimento"], linhas


def validar_1t(secoes: list[int]) -> None:
    """Compara todos os votos (todos os cargos) do BU do 1º turno com o arquivo oficial."""
    oficial = pd.read_parquet(OUT / "votos_secao.parquet")
    of = oficial.groupby(["NR_SECAO", "CD_CARGO", "NR_VOTAVEL"])["QT_VOTOS"].sum()
    lidos, difs = 0, []
    for s in secoes:
        b = boletim(1, s)
        for e in b["eleicoes"]:
            for c in e["cargos"]:
                for v in c["votos"]:
                    nr = {"branco": 95, "nulo": 96}.get(v["tipo"], v["numero"])
                    if v["tipo"] == "legenda":
                        nr = v["partido"]
                    esperado = of.get((s, c["cargo"], nr), 0)
                    lidos += 1
                    if esperado != v["qtd"]:
                        difs.append((s, c["cargo"], nr, v["qtd"], esperado))
    total_bu = sum(v["qtd"] for s in secoes for e in boletim(1, s)["eleicoes"]
                   for c in e["cargos"] for v in c["votos"])
    print(f"Validação 1º turno: {lidos - len(difs)} de {lidos} números iguais; "
          f"total de votos BU {total_bu:,} x oficial {int(oficial['QT_VOTOS'].sum()):,}")
    if difs or total_bu != oficial["QT_VOTOS"].sum():
        print("Diferenças:", difs[:20])
        sys.exit("A leitura do boletim não bate com o oficial; abortando.")


def referencias_2t() -> pd.DataFrame:
    """Totais oficiais do 2º turno (divulgação) de todos os municípios de SP, do estado e do Brasil."""
    sys.path.insert(0, str(ROOT / "app"))
    import analise as A
    ctx = A.carregar_contexto()
    e = ELEICAO_PRES[2]

    def ler(caminho):
        d = json.loads(baixar(f"{BASE}/{e}/dados/{caminho}"))
        votos = {int(c["n"]): int(c["vap"]) for a in d["carg"][0]["agr"] for p in a["par"] for c in p["cand"]}
        return {"13": votos.get(13, 0), "22": votos.get(22, 0), "brancos": int(d["v"]["vb"]),
                "nulos": int(d["v"]["tvn"]), "comparecimento": int(d["e"]["c"]), "aptos": int(d["e"]["te"])}

    cache = CTX / "mun_2t_sp.parquet"
    if cache.exists():
        mun = pd.read_parquet(cache).set_index("CD_MUNICIPIO")
    else:
        codigos = ctx["mun"][ctx["mun"]["SG_UF"] == "SP"].index
        linhas = {}
        for i, c in enumerate(codigos, 1):
            linhas[c] = ler(f"sp/sp{c}-c0001-e00{e}-u.json")
            time.sleep(0.15)
            if i % 100 == 0:
                print(f"  municípios: {i}/{len(codigos)}")
        mun = pd.DataFrame(linhas).T
        mun.index.name = "CD_MUNICIPIO"
        mun.reset_index().to_parquet(cache, index=False)
    soma = lambda idx: mun.loc[idx].sum().to_dict()  # noqa: E731
    df = pd.DataFrame({"Itapira": mun.loc[MUN].to_dict(), "Cidades vizinhas": soma(ctx["vizinhas"]),
                       "Estado de SP": ler(f"sp/sp-c0001-e00{e}-u.json"),
                       "Brasil": ler(f"br/br-c0001-e00{e}-u.json")}).T
    df.index.name = "onde"
    return df.reset_index()


ITAPIRA = MUN


def main() -> None:
    secoes = sorted(pd.read_csv(OUT / "secoes.csv")["NR_SECAO"].tolist())
    print(f"Baixando boletins de {len(secoes)} seções (1º e 2º turno)...")
    for i, s in enumerate(secoes, 1):
        boletim(1, s)
        boletim(2, s)
        if i % 20 == 0:
            print(f"  {i}/{len(secoes)}")
    validar_1t(secoes)

    votos, info = [], []
    for s in secoes:
        b1, b2 = boletim(1, s), boletim(2, s)
        aptos1, comp1, _ = votos_pres(b1, 1)
        aptos2, comp2, linhas = votos_pres(b2, 2)
        votos += [{"NR_SECAO": s, "NR_VOTAVEL": nr, "QT_VOTOS": q} for nr, q in linhas]
        info.append({"NR_SECAO": s, "APTOS_1T": aptos1, "COMPARECIMENTO_1T": comp1, "APTOS_2T": aptos2,
                     "COMPARECIMENTO_2T": comp2, "ABERTURA_2T": b2["abertura"],
                     "ENCERRAMENTO_2T": b2["encerramento"], "ENCERRAMENTO_1T": b1["encerramento"],
                     "STATUS_2T": b2["status"]})
    v = pd.DataFrame(votos)
    v.to_parquet(OUT / "votos_2t.parquet", index=False)
    pd.DataFrame(info).to_csv(OUT / "secoes_2t.csv", index=False)
    tot = v.groupby("NR_VOTAVEL")["QT_VOTOS"].sum()
    print(f"2º turno em Itapira: 22={tot.get(22, 0):,} 13={tot.get(13, 0):,} brancos={tot.get(95, 0)} "
          f"nulos={tot.get(96, 0)} | seções: {v['NR_SECAO'].nunique()}")

    ref = referencias_2t()
    ref.to_parquet(CTX / "ref_2t.parquet", index=False)
    print(ref.to_string())
    it_div = ref.set_index("onde").loc["Itapira"]
    if (int(it_div["22"]), int(it_div["13"])) != (int(tot.get(22, 0)), int(tot.get(13, 0))):
        sys.exit("Soma das seções não bate com o total oficial de Itapira na divulgação.")
    print("Soma das seções = total oficial de Itapira na divulgação. OK")

    # estimativa de transferência de votos (lenta: bootstrap), gravada para o painel abrir rápido
    sys.path.insert(0, str(ROOT / "app"))
    import analise as A
    import analise_2t as B
    votos1, _, v22, _ = A.carregar_itapira()
    t = B.tabela_secoes(votos1, *B.carregar()[:2], v22)
    T, lo, hi, n = B.transferencias(t, n_boot=300)
    est = pd.concat({"est": T.stack(), "lo": lo.stack(), "hi": hi.stack()}, axis=1).reset_index()
    est.columns = ["origem", "destino", "est", "lo", "hi"]
    est["n_origem"] = est["origem"].map(n)
    est.to_parquet(OUT / "transferencias_2t.parquet", index=False)
    print((T * 100).round(0).to_string())


if __name__ == "__main__":
    main()
