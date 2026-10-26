"""
Cálculos do 2º turno presidencial (seção a seção): resultado, mudança do 1º para o 2º turno,
estimativa de transferência de votos, comparecimento, perfil e comparação com 2022.
"""
from pathlib import Path

import numpy as np
import pandas as pd
from scipy.optimize import minimize

import analise as A

ROOT = Path(__file__).resolve().parent.parent
ITAPIRA_DIR = ROOT / "data" / "itapira"
CONTEXTO_DIR = ROOT / "data" / "contexto"

F, L = 22, 13  # Flávio Bolsonaro, Lula


def disponivel() -> bool:
    return (ITAPIRA_DIR / "votos_2t.parquet").exists()


def carregar():
    v2 = pd.read_parquet(ITAPIRA_DIR / "votos_2t.parquet")
    s2 = pd.read_csv(ITAPIRA_DIR / "secoes_2t.csv").set_index("NR_SECAO")
    ref = pd.read_parquet(CONTEXTO_DIR / "ref_2t.parquet").set_index("onde")
    mun = pd.read_parquet(CONTEXTO_DIR / "mun_2t_sp.parquet").set_index("CD_MUNICIPIO")
    return v2, s2, ref, mun


def transferencias_salvas():
    """Estimativa gravada pelo ETL: (est, lo, hi) como matrizes origem x destino e n por origem."""
    d = pd.read_parquet(ITAPIRA_DIR / "transferencias_2t.parquet")
    piv = {c: d.pivot(index="origem", columns="destino", values=c) for c in ("est", "lo", "hi")}
    ordem_o, ordem_d = ["F1", "L1", "O1", "BN1", "ABS1"], ["F2", "L2", "BN2", "ABS2"]
    n = d.drop_duplicates("origem").set_index("origem")["n_origem"]
    return tuple(piv[c].loc[ordem_o, ordem_d] for c in ("est", "lo", "hi")) + (n.loc[ordem_o],)


def tabela_secoes(votos_1t: pd.DataFrame, v2: pd.DataFrame, s2: pd.DataFrame, v22: pd.DataFrame) -> pd.DataFrame:
    """Uma linha por seção com tudo o que a análise usa (votos e % nos dois turnos e em 2022)."""
    p1 = votos_1t[votos_1t["CD_CARGO"] == 1].pivot_table(index="NR_SECAO", columns="NR_VOTAVEL",
                                                         values="QT_VOTOS", aggfunc="sum", fill_value=0)
    p2 = v2.pivot_table(index="NR_SECAO", columns="NR_VOTAVEL", values="QT_VOTOS", aggfunc="sum", fill_value=0)
    t = pd.DataFrame(index=p2.index)
    t["aptos"], t["aptos_1t"] = s2["APTOS_2T"], s2["APTOS_1T"]
    t["votaram_1t"], t["votaram_2t"] = s2["COMPARECIMENTO_1T"], s2["COMPARECIMENTO_2T"]
    t["F1"], t["L1"] = p1.get(F, 0), p1.get(L, 0)
    t["BN1"] = p1.get(A.BRANCO, 0) + p1.get(A.NULO, 0)
    t["O1"] = p1.drop(columns=[c for c in (F, L, A.BRANCO, A.NULO) if c in p1.columns]).sum(axis=1)
    t["F2"], t["L2"] = p2.get(F, 0), p2.get(L, 0)
    t["BN2"] = p2.get(A.BRANCO, 0) + p2.get(A.NULO, 0)
    val1, val2 = t["F1"] + t["L1"] + t["O1"], t["F2"] + t["L2"]
    t["pF1"], t["pL1"], t["pO1"] = t["F1"] / val1 * 100, t["L1"] / val1 * 100, t["O1"] / val1 * 100
    t["pF2"], t["pL2"] = t["F2"] / val2 * 100, t["L2"] / val2 * 100
    t["comp1"], t["comp2"] = t["votaram_1t"] / s2["APTOS_1T"] * 100, t["votaram_2t"] / t["aptos"] * 100
    t["bn1"], t["bn2"] = t["BN1"] / t["votaram_1t"] * 100, t["BN2"] / t["votaram_2t"] * 100
    # 2022, 2º turno (mesmos números 22 x 13); seção 161 é nova
    p22 = v22[v22["NR_TURNO"] == 2].pivot_table(index="NR_SECAO", columns="NR_VOTAVEL", values="QT_VOTOS",
                                                aggfunc="sum", fill_value=0)
    t["pF22"] = (p22.get(F, 0) / (p22.get(F, 0) + p22.get(L, 0)) * 100).reindex(t.index)
    return t


def transferencias(t: pd.DataFrame, origens=("F1", "L1", "O1", "BN1", "ABS1"),
                   destinos=("F2", "L2", "BN2", "ABS2"), n_boot: int = 300, semente: int = 7):
    """Estimativa ecológica de transferência de votos do 1º para o 2º turno.

    Para cada seção, a composição do eleitorado no 2º turno (Flávio, Lula, branco/nulo, abstenção)
    é modelada como combinação da composição no 1º turno: D = O · T, com cada linha de T somando 1
    e T >= 0 (um eleitor do 1º turno vai para exatamente um destino). T é ajustada por mínimos
    quadrados entre as 161 seções, ponderando pelo eleitorado. Intervalos por bootstrap das seções.
    Hipótese forte: o comportamento é parecido em todas as seções - é uma estimativa, não uma contagem.
    """
    d = t.copy()
    # abstenção no 1º turno medida sobre o eleitorado do 2º (diferença de poucos eleitores entre os turnos)
    d["ABS1"] = (d["aptos"] - d["votaram_1t"]).clip(lower=0)
    d["ABS2"] = (d["aptos"] - d["votaram_2t"])
    O = d[list(origens)].div(d[list(origens)].sum(axis=1), axis=0).values
    D = d[list(destinos)].div(d[list(destinos)].sum(axis=1), axis=0).values
    w = d["aptos"].values.astype(float)
    k, m = O.shape[1], D.shape[1]

    def ajustar(Oi, Di, wi):
        def perda(x):
            T = x.reshape(k, m)
            r = Oi @ T - Di
            return float((wi[:, None] * r * r).sum())

        x0 = np.full(k * m, 1 / m)
        cons = [{"type": "eq", "fun": (lambda x, i=i: x.reshape(k, m)[i].sum() - 1)} for i in range(k)]
        res = minimize(perda, x0, method="SLSQP", bounds=[(0, 1)] * (k * m), constraints=cons,
                       options={"maxiter": 500, "ftol": 1e-12})
        return res.x.reshape(k, m)

    T = ajustar(O, D, w)
    rng = np.random.default_rng(semente)
    boots = []
    for _ in range(n_boot):
        idx = rng.integers(0, len(O), len(O))
        boots.append(ajustar(O[idx], D[idx], w[idx]))
    boots = np.array(boots)
    lo, hi = np.percentile(boots, 5, axis=0), np.percentile(boots, 95, axis=0)
    # eleitores (contagem) de cada origem na cidade, para converter taxas em pessoas
    n_origem = d[list(origens)].sum().values
    return (pd.DataFrame(T, index=origens, columns=destinos), pd.DataFrame(lo, index=origens, columns=destinos),
            pd.DataFrame(hi, index=origens, columns=destinos), pd.Series(n_origem, index=origens))


def esperado_pelo_perfil_2t(ctx, mun: pd.DataFrame) -> tuple[pd.DataFrame, float]:
    """% de Flávio no 2º turno 'esperado' em cada município de SP só pelo perfil do eleitorado
    (regressão linear entre os 645 municípios, cada um contando igual). Devolve real x esperado e R²."""
    X = A.indicadores(ctx["perfil"])[A.PREDITORES]
    d = X.join(mun["pF"].rename("real")).dropna()
    M = np.c_[np.ones(len(d)), d[A.PREDITORES].values]
    coef, *_ = np.linalg.lstsq(M, d["real"].values, rcond=None)
    d["esperado"] = M @ coef
    res = d["real"] - d["esperado"]
    r2 = 1 - (res ** 2).sum() / ((d["real"] - d["real"].mean()) ** 2).sum()
    return d[["real", "esperado"]], r2
