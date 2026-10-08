"""
Cálculos da análise (sem Streamlit): carregamento dos dados, percentuais, referências de
comparação (região, SP, Brasil), mudança 2022 -> 2026, voto entre cargos, perfil e deputados.
"""
import unicodedata
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parent.parent
ITAPIRA_DIR = ROOT / "data" / "itapira"
CONTEXTO_DIR = ROOT / "data" / "contexto"
MAPPING = ROOT / "mapping" / "bairros.csv"

ITAPIRA = 65536
BRANCO, NULO = 95, 96
PRESIDENTE, GOVERNADOR, SENADOR, DEP_FEDERAL, DEP_ESTADUAL = 1, 3, 5, 6, 7
CARGOS = {PRESIDENTE: "Presidente", GOVERNADOR: "Governador", SENADOR: "Senador",
          DEP_FEDERAL: "Deputado Federal", DEP_ESTADUAL: "Deputado Estadual"}

# Cidades vizinhas usadas como referência regional (Circuito das Águas e Baixa Mogiana, SP)
VIZINHAS = ["MOGI MIRIM", "MOGI GUACU", "AMPARO", "SERRA NEGRA", "JAGUARIUNA",
            "SANTO ANTONIO DE POSSE", "PEDREIRA", "HOLAMBRA", "LINDOIA", "AGUAS DE LINDOIA",
            "MONTE ALEGRE DO SUL", "SOCORRO", "ESTIVA GERBI", "ESPIRITO SANTO DO PINHAL",
            "CONCHAL", "ARTUR NOGUEIRA"]

SITUACOES = {"ELEITO": "Eleito", "ELEITO POR QP": "Eleito pelo quociente partidário",
             "ELEITO POR MÉDIA": "Eleito pela média", "SUPLENTE": "Suplente", "NÃO ELEITO": "Não eleito",
             "2º TURNO": "Vai ao 2º turno", "#NULO": "Candidatura anulada"}

APELIDOS = {"Luiz Inácio Lula da Silva": "Lula"}  # quando primeiro + último nome não é o conhecido


def partido_de(nr: int) -> int:
    """Número do partido = 2 primeiros dígitos (deputado federal tem 4, estadual 5)."""
    return int(str(nr)[:2]) if nr >= 100 else nr


def sem_acento(s: str) -> str:
    return "".join(c for c in unicodedata.normalize("NFD", s) if unicodedata.category(c) != "Mn")


def nome(n: str) -> str:
    """Nome do TSE em maiúsculas -> forma de título."""
    t = n.title()
    for p in [" Da ", " De ", " Do ", " Das ", " Dos ", " E "]:
        t = t.replace(p, p.lower())
    return t


def curto(n: str) -> str:
    """Nome completo longo -> primeiro + último ('Flavio Nantes Bolsonaro' -> 'Flavio Bolsonaro').
    Nomes de urna já são curtos e passam inalterados."""
    if n in APELIDOS:
        return APELIDOS[n]
    if len(n.split()) <= 3:
        return n
    p = [x for x in n.split() if x.lower() not in ("da", "de", "do", "das", "dos", "e")]
    return n if len(p) <= 2 else f"{p[0]} {p[-1]}"


# ======================================================================= carregamento
def carregar_itapira():
    """Votos por seção (2026), seções com bairro, perfil e Presidente 2022 por seção."""
    votos = pd.read_parquet(ITAPIRA_DIR / "votos_secao.parquet")
    secoes = pd.read_csv(ITAPIRA_DIR / "secoes.csv")
    mapa = pd.read_csv(MAPPING, encoding="utf-8-sig")
    mapa["BAIRRO"] = mapa["BAIRRO"].fillna(mapa["BAIRRO_TSE"]).str.strip()
    secoes = secoes.drop(columns=["NR_LATITUDE", "NR_LONGITUDE"]).merge(
        mapa[["NR_LOCAL_VOTACAO", "BAIRRO", "NR_LATITUDE", "NR_LONGITUDE"]],
        on="NR_LOCAL_VOTACAO", how="left")
    votos = votos.drop(columns=["NR_LOCAL_VOTACAO", "NM_LOCAL_VOTACAO"]).merge(
        secoes[["NR_SECAO", "NR_LOCAL_VOTACAO", "NM_LOCAL_VOTACAO", "BAIRRO"]], on="NR_SECAO")
    votos["NOME"] = votos["NM_VOTAVEL"].map(nome)
    v22 = pd.read_parquet(ITAPIRA_DIR / "votos_2022.parquet")
    v22["NOME"] = v22["NM_VOTAVEL"].map(nome)
    s22 = pd.read_csv(ITAPIRA_DIR / "secoes_2022.csv")
    return votos, secoes, v22, s22


def carregar_perfil():
    """Indicadores de perfil (eleitores aptos) somados por seção."""
    p = pd.read_parquet(ITAPIRA_DIR / "perfil_secao.parquet")
    ini, fim = p["CD_FAIXA_ETARIA"] // 100, p["CD_FAIXA_ETARIA"] % 100
    p["IDADE"] = np.where(p["CD_FAIXA_ETARIA"] < 2100, ini, (ini + np.minimum(fim, 100)) / 2)
    q = p["QT_ELEITORES"]
    p["w_idade"] = p["IDADE"] * q
    p["jovens"] = q * (p["IDADE"] < 30)
    p["idosos"] = q * (p["IDADE"] >= 60)
    p["mulheres"] = q * (p["DS_GENERO"] == "FEMININO")
    p["superior"] = q * (p["CD_GRAU_ESCOLARIDADE"] >= 7)
    p["fundamental"] = q * (p["CD_GRAU_ESCOLARIDADE"] <= 4)
    p["casados"] = q * (p["DS_ESTADO_CIVIL"] == "CASADO")
    return p.groupby("NR_SECAO")[["QT_ELEITORES", "w_idade", "jovens", "idosos", "mulheres",
                                  "superior", "fundamental", "casados"]].sum()


# nome -> (coluna, rótulo quando alto, rótulo quando baixo, unidade)
INDICADORES = {
    "Idade média": ("w_idade", "eleitorado mais velho", "eleitorado mais jovem", " anos"),
    "% com 60 anos ou mais": ("idosos", "mais idosos", "menos idosos", "%"),
    "% de 16 a 29 anos": ("jovens", "mais jovens", "menos jovens", "%"),
    "% com ensino superior": ("superior", "mais escolarizado", "menos escolarizado", "%"),
    "% até o fundamental": ("fundamental", "mais eleitores só com o fundamental",
                            "menos eleitores só com o fundamental", "%"),
    "% de mulheres": ("mulheres", "mais mulheres", "menos mulheres", "%"),
    "% de casados": ("casados", "mais casados", "menos casados", "%"),
}


def indicadores(soma: pd.DataFrame) -> pd.DataFrame:
    out = pd.DataFrame(index=soma.index)
    for n, (col, *_rest) in INDICADORES.items():
        out[n] = soma[col] / soma["QT_ELEITORES"] * (1 if n == "Idade média" else 100)
    out["Eleitores"] = soma["QT_ELEITORES"]
    return out


def carregar_contexto():
    """Totais por município (SP todos os cargos; Brasil para Presidente) - pode não existir."""
    if not (CONTEXTO_DIR / "votos_mun_2026.parquet").exists():
        return None
    mun = pd.read_parquet(CONTEXTO_DIR / "municipios.parquet").set_index("CD_MUNICIPIO")
    mun["CHAVE"] = mun["NM_MUNICIPIO"].map(sem_acento)
    vizinhas = mun[(mun["SG_UF"] == "SP") & mun["CHAVE"].isin(VIZINHAS)].index
    cand = pd.read_parquet(CONTEXTO_DIR / "candidatos_2026.parquet")
    # sigla de cada número de partido = a mais comum entre os candidatos com aquele prefixo
    c = cand[cand["NR_VOTAVEL"] >= 100].dropna(subset=["SG_PARTIDO"])
    sigla = c.groupby(c["NR_VOTAVEL"].map(partido_de))["SG_PARTIDO"].agg(lambda x: x.mode().iloc[0]).to_dict()
    # nome de urna quando existe ("Tarcísio", "Barros Munhoz"); partido: sigla; senão, nome do TSE
    cand["NOME"] = [
        nome(u) if isinstance(u, str) else sigla.get(n, nome(v)) if n not in (BRANCO, NULO) else nome(v)
        for u, n, v in zip(cand["NM_URNA"], cand["NR_VOTAVEL"], cand["NM_VOTAVEL"])]
    idx = ["CD_CARGO", "NR_VOTAVEL"]
    return {
        "mun": mun,
        "vizinhas": list(vizinhas),
        "v26": pd.read_parquet(CONTEXTO_DIR / "votos_mun_2026.parquet"),
        "v22": pd.read_parquet(CONTEXTO_DIR / "votos_mun_2022.parquet"),
        "cand": cand.set_index(idx)["NOME"],
        "partido": cand.set_index(idx)["SG_PARTIDO"],
        "situacao": cand.set_index(idx)["SITUACAO"].map(SITUACOES),
        "sigla": sigla,
        "perfil": (pd.read_parquet(CONTEXTO_DIR / "perfil_mun.parquet").set_index("CD_MUNICIPIO")
                   if (CONTEXTO_DIR / "perfil_mun.parquet").exists() else None),
    }


# ======================================================================= percentuais
def validos(df: pd.DataFrame, legenda: bool = True) -> pd.DataFrame:
    """Só votos válidos (sem branco/nulo); para deputados, opcionalmente sem legenda."""
    df = df[~df["NR_VOTAVEL"].isin([BRANCO, NULO])]
    if not legenda:
        df = df[~((df["CD_CARGO"].isin([DEP_FEDERAL, DEP_ESTADUAL])) & (df["NR_VOTAVEL"] < 100))]
    return df


def pct_por(df: pd.DataFrame, grupo, coluna="NR_VOTAVEL") -> pd.DataFrame:
    """% de cada votável sobre os votos válidos de cada grupo (linhas = grupo)."""
    p = df.pivot_table(index=grupo, columns=coluna, values="QT_VOTOS", aggfunc="sum", fill_value=0)
    return p.div(p.sum(axis=1), axis=0) * 100


def referencias(ctx, cargo: int, ano: int = 2026, turno: int = 1) -> pd.DataFrame:
    """% dos válidos por votável em Itapira, região, SP e (Presidente) Brasil."""
    v = ctx["v26"] if ano == 2026 else ctx["v22"]
    v = validos(v[(v["CD_CARGO"] == cargo) & (v["NR_TURNO"] == turno)])
    uf = v["CD_MUNICIPIO"].map(ctx["mun"]["SG_UF"])
    partes = {
        "Itapira": v["CD_MUNICIPIO"] == ITAPIRA,
        "Cidades vizinhas": v["CD_MUNICIPIO"].isin(ctx["vizinhas"]),
        "Estado de SP": uf == "SP",
    }
    if cargo == PRESIDENTE:
        partes["Brasil"] = pd.Series(True, index=v.index)
    linhas = []
    for nome_ref, m in partes.items():
        p = v[m].groupby("NR_VOTAVEL")["QT_VOTOS"].sum()
        linhas.append((p / p.sum() * 100).rename(nome_ref))
    return pd.DataFrame(linhas).fillna(0)


def pct_municipios_sp(ctx, cargo: int, ano: int = 2026, turno: int = 1) -> pd.DataFrame:
    v = ctx["v26"] if ano == 2026 else ctx["v22"]
    v = validos(v[(v["CD_CARGO"] == cargo) & (v["NR_TURNO"] == turno)])
    v = v[v["CD_MUNICIPIO"].map(ctx["mun"]["SG_UF"]) == "SP"]
    return pct_por(v, "CD_MUNICIPIO")


def posicao_sp(ctx, cargo: int, nr: int) -> tuple[int, int, float]:
    """(posição de Itapira, nº de municípios, % de municípios com resultado menor)."""
    p = pct_municipios_sp(ctx, cargo)[nr].sort_values(ascending=False)
    pos = list(p.index).index(ITAPIRA) + 1
    return pos, len(p), (p < p[ITAPIRA]).mean() * 100


def comparecimento_ref(ctx) -> pd.DataFrame:
    """Comparecimento (votos para Presidente / aptos) em 2022 e 2026 por referência."""
    mun = ctx["mun"]
    out = {}
    for ano, v, col in [(2022, ctx["v22"], "APTOS_2022"), (2026, ctx["v26"], "APTOS_2026")]:
        tot = v[(v["CD_CARGO"] == PRESIDENTE) & (v["NR_TURNO"] == 1)].groupby("CD_MUNICIPIO")["QT_VOTOS"].sum()
        df = pd.DataFrame({"votos": tot, "aptos": mun[col]}).dropna()
        uf = mun["SG_UF"].reindex(df.index)
        grupos = {"Itapira": df.index == ITAPIRA, "Cidades vizinhas": df.index.isin(ctx["vizinhas"]),
                  "Estado de SP": (uf == "SP").values, "Brasil": np.ones(len(df), bool)}
        out[ano] = {k: df[m]["votos"].sum() / df[m]["aptos"].sum() * 100 for k, m in grupos.items()}
        out[f"aptos_{ano}"] = {k: df[m]["aptos"].sum() for k, m in grupos.items()}
    return pd.DataFrame(out)


def brancos_nulos_ref(ctx) -> pd.DataFrame:
    """% de brancos + nulos sobre o total de votos, por cargo, em Itapira e no estado."""
    v = ctx["v26"]
    v = v[(v["NR_TURNO"] == 1) & (v["CD_MUNICIPIO"].map(ctx["mun"]["SG_UF"]) == "SP")]
    linhas = []
    for cargo, n in CARGOS.items():
        c = v[v["CD_CARGO"] == cargo]
        bn = c["NR_VOTAVEL"].isin([BRANCO, NULO])
        it = c["CD_MUNICIPIO"] == ITAPIRA
        linhas.append({"Cargo": n,
                       "Itapira": c[bn & it]["QT_VOTOS"].sum() / c[it]["QT_VOTOS"].sum() * 100,
                       "Estado de SP": c[bn]["QT_VOTOS"].sum() / c["QT_VOTOS"].sum() * 100})
    return pd.DataFrame(linhas).set_index("Cargo")


# ======================================================================= perfil: cidades
def perfil_ref(ctx) -> pd.DataFrame:
    """Indicadores de perfil (eleitores aptos) de Itapira, das vizinhas e do estado."""
    pm = ctx["perfil"]
    grupos = {"Itapira": [ITAPIRA], "Cidades vizinhas": ctx["vizinhas"], "Estado de SP": list(pm.index)}
    return pd.DataFrame({k: indicadores(pm.loc[v].sum().to_frame().T).iloc[0] for k, v in grupos.items()})


PREDITORES = ["Idade média", "% com ensino superior", "% de mulheres"]


def esperado_pelo_perfil(ctx, cargo: int, nr: int) -> tuple[pd.DataFrame, float]:
    """Resultado 'esperado' de cada município de SP só pelo perfil do eleitorado.

    Regressão linear simples entre os 645 municípios (cada cidade conta igual): % do candidato
    explicado por idade média, % com ensino superior e % de mulheres. Devolve real x esperado e o R².
    """
    y = pct_municipios_sp(ctx, cargo)[nr]
    X = indicadores(ctx["perfil"])[PREDITORES]
    d = X.join(y.rename("real")).dropna()
    M = np.c_[np.ones(len(d)), d[PREDITORES].values]
    coef, *_ = np.linalg.lstsq(M, d["real"].values, rcond=None)
    d["esperado"] = M @ coef
    res = d["real"] - d["esperado"]
    r2 = 1 - (res ** 2).sum() / ((d["real"] - d["real"].mean()) ** 2).sum()
    return d[["real", "esperado"]], r2


# ======================================================================= voto entre cargos
def por_100_eleitores(ctx, alvos: list[tuple[int, int]]) -> pd.DataFrame:
    """Votos de cada (cargo, número) a cada 100 eleitores que votaram, em Itapira, vizinhas e SP.

    A base é o total de votos para Governador (cada eleitor dá exatamente 1 voto para esse cargo)."""
    v = ctx["v26"]
    v = v[(v["NR_TURNO"] == 1) & (v["CD_MUNICIPIO"].map(ctx["mun"]["SG_UF"]) == "SP")]
    grupos = {"Itapira": v["CD_MUNICIPIO"] == ITAPIRA, "Cidades vizinhas": v["CD_MUNICIPIO"].isin(ctx["vizinhas"]),
              "Estado de SP": pd.Series(True, index=v.index)}
    out = {}
    for g, m in grupos.items():
        vv = v[m]
        base = vv[vv["CD_CARGO"] == GOVERNADOR]["QT_VOTOS"].sum()
        soma = vv.groupby(["CD_CARGO", "NR_VOTAVEL"])["QT_VOTOS"].sum()
        out[g] = {a: soma.get(a, 0) / base * 100 for a in alvos}
    return pd.DataFrame(out)


# ======================================================================= estatística simples
def r2_simples(x: pd.Series, y: pd.Series) -> tuple[float, float]:
    """(correlação, R²) entre duas séries alinhadas."""
    d = pd.concat([x, y], axis=1).dropna()
    r = d.iloc[:, 0].corr(d.iloc[:, 1])
    return r, r * r


def r2_multiplo(X: pd.DataFrame, y: pd.Series, pesos: pd.Series | None = None) -> float:
    """R² de uma regressão linear com várias variáveis (mínimos quadrados, com pesos opcionais)."""
    d = X.join(y.rename("_y")).dropna()
    w = np.sqrt(pesos.reindex(d.index).values) if pesos is not None else np.ones(len(d))
    A = np.c_[np.ones(len(d)), d[X.columns].values] * w[:, None]
    b = d["_y"].values * w
    coef, *_ = np.linalg.lstsq(A, b, rcond=None)
    res = b - A @ coef
    tot = b - np.average(d["_y"].values, weights=w ** 2) * w
    return 1 - (res @ res) / (tot @ tot)


def tercos(ind: pd.Series, votos_secao: pd.DataFrame, cols: list) -> tuple[pd.DataFrame, list[str]]:
    """Divide as seções em 3 grupos iguais pelo indicador e calcula o % de cada candidato."""
    s = ind.reindex(votos_secao.index).dropna()
    t = pd.qcut(s.rank(method="first"), 3, labels=[0, 1, 2])
    soma = votos_secao.loc[s.index].groupby(t, observed=True).sum()
    res = soma[cols].div(soma.sum(axis=1), axis=0) * 100
    faixa = s.groupby(t, observed=True).agg(["min", "max"]).values
    return res, [(f, m) for f, m in faixa]


# ======================================================================= deputados
def deputados(ctx, cargo: int, votos_itapira: pd.DataFrame) -> pd.DataFrame:
    """Candidatos a deputado: votos em Itapira, na região, no estado e dependência de Itapira."""
    v = ctx["v26"]
    v = v[(v["CD_CARGO"] == cargo) & (v["NR_VOTAVEL"] >= 100)]
    total = v.groupby("NR_VOTAVEL")["QT_VOTOS"].sum()
    regiao = v[v["CD_MUNICIPIO"].isin(ctx["vizinhas"] + [ITAPIRA])].groupby("NR_VOTAVEL")["QT_VOTOS"].sum()
    it = (votos_itapira[(votos_itapira["CD_CARGO"] == cargo) & (votos_itapira["NR_VOTAVEL"] >= 100)]
          .groupby("NR_VOTAVEL")["QT_VOTOS"].sum())
    df = pd.DataFrame({"Itapira": it, "Itapira + vizinhas": regiao, "Estado": total}).fillna(0)
    df = df[df["Itapira"] > 0]
    df["% dos votos de Itapira"] = df["Itapira"] / it.sum() * 100
    df["Posição no estado"] = total.rank(ascending=False, method="min").reindex(df.index)
    df["% do total dele que veio de Itapira"] = df["Itapira"] / df["Estado"] * 100
    df["% do total dele que veio da região"] = df["Itapira + vizinhas"] / df["Estado"] * 100
    df["Partido"] = [ctx["partido"].get((cargo, n)) or ctx["sigla"].get(partido_de(n), "") for n in df.index]
    df["Candidato"] = [ctx["cand"].get((cargo, n), str(n)) for n in df.index]
    df["Situação"] = [ctx["situacao"].get((cargo, n), "") for n in df.index]
    return df.sort_values("Itapira", ascending=False)


def partidos(ctx, cargo: int) -> pd.DataFrame:
    """Votos por partido (nominais + legenda): % em Itapira e no estado."""
    v = ctx["v26"]
    v = validos(v[(v["CD_CARGO"] == cargo) & (v["CD_MUNICIPIO"].map(ctx["mun"]["SG_UF"]) == "SP")])
    v = v.assign(PARTIDO=v["NR_VOTAVEL"].map(partido_de))
    it = v[v["CD_MUNICIPIO"] == ITAPIRA].groupby("PARTIDO")["QT_VOTOS"].sum()
    sp = v.groupby("PARTIDO")["QT_VOTOS"].sum()
    df = pd.DataFrame({"Itapira": it / it.sum() * 100, "Estado de SP": sp / sp.sum() * 100,
                       "Votos em Itapira": it}).fillna(0)
    df["Diferença (p.p.)"] = df["Itapira"] - df["Estado de SP"]
    df.index = [ctx["sigla"].get(n) or ctx["cand"].get((cargo, n), str(n)) for n in df.index]
    return df.sort_values("Itapira", ascending=False)
