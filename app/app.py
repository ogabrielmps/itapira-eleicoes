"""
Painel: votação de Itapira (Zona 54) por bairro - Eleições 2026, 1º turno.

Rodar:  streamlit run app/app.py
Dados:  gerados por etl/preparar_dados.py; bairros revisáveis em mapping/bairros.csv
"""
import hmac
from pathlib import Path

import folium
import numpy as np
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
import streamlit as st
from streamlit_folium import st_folium

ROOT = Path(__file__).resolve().parent.parent
DADOS = ROOT / "data" / "itapira"
MAPPING = ROOT / "mapping" / "bairros.csv"

BRANCO, NULO = 95, 96
# Paleta categórica (ordem fixa, validada para daltonismo nas 3 primeiras posições)
SERIES = ["#2a78d6", "#eb6834", "#1baf7a"]
OUTROS = "#898781"
SEQ = ["#cde2fb", "#86b6ef", "#3987e5", "#1c5cab", "#0d366b"]
DIV = [[0, "#e34948"], [0.5, "#f0efec"], [1, "#2a78d6"]]

AGRUPAMENTOS = {
    "Bairro": "BAIRRO",
    "Região": "REGIAO",
    "Local de votação": "NM_LOCAL_VOTACAO",
    "Seção": "NR_SECAO",
}

st.set_page_config(page_title="Itapira 2026 · votos por bairro", page_icon="🗳️", layout="wide")


# ---------------------------------------------------------------- acesso
def senha_configurada():
    try:
        return st.secrets.get("senha")
    except FileNotFoundError:  # rodando local sem secrets.toml
        return None


SENHA = senha_configurada()
if SENHA and not st.session_state.get("autenticado"):
    st.title("🗳️ Itapira · 2026")
    with st.form("login"):
        digitada = st.text_input("Senha", type="password")
        if st.form_submit_button("Entrar"):
            if hmac.compare_digest(digitada, str(SENHA)):
                st.session_state["autenticado"] = True
                st.rerun()
            st.error("Senha incorreta.")
    st.stop()


# ---------------------------------------------------------------- dados
@st.cache_data
def carregar():
    votos = pd.read_parquet(DADOS / "votos_secao.parquet")
    secoes = pd.read_csv(DADOS / "secoes.csv")
    mapa = pd.read_csv(MAPPING, encoding="utf-8-sig")
    mapa["BAIRRO"] = mapa["BAIRRO"].fillna(mapa["BAIRRO_TSE"]).str.strip()
    mapa["REGIAO"] = mapa["REGIAO"].fillna("").astype(str).str.strip()
    mapa.loc[mapa["REGIAO"] == "", "REGIAO"] = mapa["BAIRRO"]
    # coordenadas também podem ser corrigidas no mapping
    secoes = secoes.drop(columns=["NR_LATITUDE", "NR_LONGITUDE"]).merge(
        mapa[["NR_LOCAL_VOTACAO", "BAIRRO", "REGIAO", "NR_LATITUDE", "NR_LONGITUDE"]],
        on="NR_LOCAL_VOTACAO", how="left")
    votos = votos.drop(columns=["NR_LOCAL_VOTACAO", "NM_LOCAL_VOTACAO"]).merge(
        secoes[["NR_SECAO", "NR_LOCAL_VOTACAO", "NM_LOCAL_VOTACAO", "BAIRRO", "REGIAO"]],
        on="NR_SECAO", how="left")
    return votos, secoes


votos, secoes = carregar()


@st.cache_data
def carregar_perfil():
    """Indicadores por seção (eleitores aptos, cadastro de jul/2026)."""
    p = pd.read_parquet(DADOS / "perfil_secao.parquet")
    # idade aproximada: ponto médio da faixa (ex.: 2529 -> 27; 1600..2000 são idades exatas)
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
    soma = p.groupby("NR_SECAO")[["QT_ELEITORES", "w_idade", "jovens", "idosos", "mulheres",
                                  "superior", "fundamental", "casados"]].sum()
    return p, soma


INDICADORES = {
    "Idade média": "w_idade",
    "% jovens (16-29)": "jovens",
    "% idosos (60+)": "idosos",
    "% mulheres": "mulheres",
    "% com ensino superior (completo ou não)": "superior",
    "% até fundamental completo": "fundamental",
    "% casados": "casados",
}


def indicadores(soma: pd.DataFrame) -> pd.DataFrame:
    """Converte somas (por seção ou agregadas) em idade média / percentuais."""
    out = pd.DataFrame(index=soma.index)
    for nome, col in INDICADORES.items():
        f = 1 if nome == "Idade média" else 100
        out[nome] = soma[col] / soma["QT_ELEITORES"] * f
    out["Eleitores"] = soma["QT_ELEITORES"]
    return out


perfil, perfil_secao = carregar_perfil()
sem_bairro = votos["BAIRRO"].isna().sum()

# ---------------------------------------------------------------- filtros
st.sidebar.title("🗳️ Itapira · 2026")
st.sidebar.caption("Zona 0054 · 1º turno · fonte: TSE Dados Abertos")

ordem_cargos = ["Presidente", "Governador", "Senador", "Deputado Federal", "Deputado Estadual"]
cargos = [c for c in ordem_cargos if c in votos["DS_CARGO"].unique()]
cargo = st.sidebar.selectbox("Cargo", cargos)
nome_grupo = st.sidebar.radio("Agrupar por", list(AGRUPAMENTOS))
col_grupo = AGRUPAMENTOS[nome_grupo]

v = votos[votos["DS_CARGO"] == cargo].copy()
legenda = False
if cargo.startswith("Deputado"):
    legenda = st.sidebar.checkbox("Incluir votos de legenda (só no partido)", value=False)

v["TIPO"] = "Nominal"
v.loc[v["NR_VOTAVEL"] == BRANCO, "TIPO"] = "Branco"
v.loc[v["NR_VOTAVEL"] == NULO, "TIPO"] = "Nulo"
if cargo.startswith("Deputado"):  # Presidente/Governador também têm números de 2 dígitos
    v.loc[(v["TIPO"] == "Nominal") & (v["NR_VOTAVEL"] < 100), "TIPO"] = "Legenda"
validos = v[v["TIPO"].isin(["Nominal", "Legenda"] if legenda else ["Nominal"])].copy()
validos["CANDIDATO"] = validos["NM_VOTAVEL"].str.title()
validos.loc[validos["TIPO"] == "Legenda", "CANDIDATO"] = "Legenda " + validos["NM_VOTAVEL"]

# ranking da cidade -> ordem fixa de cor (cor segue o candidato, não a posição local)
ranking = validos.groupby("CANDIDATO")["QT_VOTOS"].sum().sort_values(ascending=False)
total_validos = ranking.sum()
cor_cand = {c: SERIES[i] for i, c in enumerate(ranking.index[:3])}


def cor(c):
    return cor_cand.get(c, OUTROS)


# tabela grupo x candidato
pivot = validos.pivot_table(index=col_grupo, columns="CANDIDATO", values="QT_VOTOS",
                            aggfunc="sum", fill_value=0)
pivot = pivot[ranking.index]
pct = pivot.div(pivot.sum(axis=1), axis=0) * 100
pct_cidade = ranking / total_validos * 100

# comparecimento: Governador (1 voto por eleitor, todas as seções)
votantes = (votos[votos["DS_CARGO"] == "Governador"].groupby("NR_SECAO")["QT_VOTOS"].sum()
            .rename("VOTANTES"))
sec = secoes.merge(votantes, on="NR_SECAO", how="left").fillna({"VOTANTES": 0})

# ---------------------------------------------------------------- cabeçalho
st.title(f"{cargo} · votos por {nome_grupo.lower()}")
k1, k2, k3, k4 = st.columns(4)
aptos = int(sec["QT_ELEITOR_SECAO"].sum())
comp = int(sec["VOTANTES"].sum())
k1.metric("Eleitores aptos", f"{aptos:,}".replace(",", "."))
k2.metric("Comparecimento", f"{comp / aptos:.1%}".replace(".", ","))
k3.metric("Votos válidos (" + ("com legenda" if legenda else "nominais") + ")",
          f"{total_validos:,}".replace(",", "."))
bn = v[v["TIPO"].isin(["Branco", "Nulo"])]["QT_VOTOS"].sum()
k4.metric("Brancos + nulos", f"{bn / v['QT_VOTOS'].sum():.1%}".replace(".", ","))
if sem_bairro:
    st.warning(f"{sem_bairro} linhas de voto sem bairro mapeado - confira mapping/bairros.csv.")

aba1, aba2, aba3, aba4, aba6, aba5 = st.tabs(
    ["🏆 Quem venceu onde", "👤 Desempenho por candidato", "🔥 Comparativo",
     "🚶 Comparecimento", "👥 Perfil do eleitorado", "📄 Dados"])


def fmt_pct(x):
    return f"{x:.1f}%".replace(".", ",")


# ---------------------------------------------------------------- aba 1
with aba1:
    top2 = pd.DataFrame({
        "1º": pct.idxmax(axis=1),
        "% 1º": pct.max(axis=1),
        "2º": pct.apply(lambda r: r.nlargest(2).index[-1], axis=1),
        "% 2º": pct.apply(lambda r: r.nlargest(2).iloc[-1], axis=1),
        "Votos válidos": pivot.sum(axis=1),
    })
    top2["Margem (p.p.)"] = top2["% 1º"] - top2["% 2º"]
    top2 = top2.sort_values("Votos válidos", ascending=False)

    c_mapa, c_tab = st.columns([1, 1])
    with c_mapa:
        st.subheader("Mapa por local de votação")
        por_local = validos.pivot_table(index="NR_LOCAL_VOTACAO", columns="CANDIDATO",
                                        values="QT_VOTOS", aggfunc="sum", fill_value=0)
        locais = secoes.groupby("NR_LOCAL_VOTACAO").first()[
            ["NM_LOCAL_VOTACAO", "BAIRRO", "NR_LATITUDE", "NR_LONGITUDE"]]
        m = folium.Map(location=[secoes["NR_LATITUDE"].median(), secoes["NR_LONGITUDE"].median()],
                       zoom_start=13, tiles="OpenStreetMap")
        pts = locais.dropna(subset=["NR_LATITUDE"])
        m.fit_bounds([[pts["NR_LATITUDE"].min(), pts["NR_LONGITUDE"].min()],
                      [pts["NR_LATITUDE"].max(), pts["NR_LONGITUDE"].max()]])
        maxv = por_local.sum(axis=1).max()
        for loc, linha in por_local.iterrows():
            if loc not in locais.index or pd.isna(locais.loc[loc, "NR_LATITUDE"]):
                continue
            info = locais.loc[loc]
            tot = linha.sum()
            top = linha.nlargest(3)
            html = (f"<b>{info['NM_LOCAL_VOTACAO']}</b><br>{info['BAIRRO']}<br>"
                    + "<br>".join(f"{c}: {n} ({n / tot:.1%})" for c, n in top.items()))
            folium.CircleMarker(
                [info["NR_LATITUDE"], info["NR_LONGITUDE"]],
                radius=6 + 18 * (tot / maxv) ** 0.5,
                color="#ffffff", weight=2, fill=True, fill_color=cor(top.index[0]),
                fill_opacity=0.85, tooltip=html,
            ).add_to(m)
        st_folium(m, height=460, use_container_width=True, returned_objects=[])
        st.caption("Cor = candidato mais votado no local · tamanho = votos válidos · "
                   + " · ".join(f"<span style='color:{c}'>●</span> {n}" for n, c in cor_cand.items())
                   + f" · <span style='color:{OUTROS}'>●</span> outros", unsafe_allow_html=True)
    with c_tab:
        st.subheader(f"1º e 2º colocados por {nome_grupo.lower()}")
        st.dataframe(
            top2.style.format({"% 1º": fmt_pct, "% 2º": fmt_pct, "Margem (p.p.)": "{:.1f}",
                               "Votos válidos": "{:,.0f}"}),
            height=460, width="stretch")

    st.subheader("Vitórias por candidato")
    vit = top2["1º"].value_counts().rename_axis("Candidato").reset_index(name=nome_grupo + "s vencidos")
    st.dataframe(vit, hide_index=True)

# ---------------------------------------------------------------- aba 2
with aba2:
    cand = st.selectbox("Candidato", ranking.index,
                        format_func=lambda c: f"{c} - {ranking[c]:,} votos ({pct_cidade[c]:.1f}%)")
    serie = pd.DataFrame({
        "Votos": pivot[cand],
        "%": pct[cand],
    })
    serie["Índice vs cidade"] = serie["%"] / pct_cidade[cand] * 100
    serie = serie.sort_values("%")

    fig = go.Figure(go.Bar(
        x=serie["%"], y=serie.index.astype(str), orientation="h",
        marker=dict(color=cor(cand), cornerradius=4),
        customdata=serie[["Votos", "Índice vs cidade"]],
        hovertemplate="<b>%{y}</b><br>%{x:.1f}% dos válidos<br>%{customdata[0]:,} votos"
                      "<br>índice %{customdata[1]:.0f}<extra></extra>",
    ))
    fig.add_vline(x=pct_cidade[cand], line_dash="dot", line_color=OUTROS,
                  annotation_text=f"média da cidade {pct_cidade[cand]:.1f}%",
                  annotation_position="top")
    fig.update_layout(height=max(380, 22 * len(serie) + 80), margin=dict(l=10, r=20, t=40, b=10),
                      xaxis_title="% dos votos válidos", yaxis_title=None, bargap=0.25)
    st.plotly_chart(fig, width="stretch")
    st.caption("Índice = % no grupo ÷ % na cidade × 100. Acima de 100 = desempenho acima da média.")
    st.dataframe(serie.sort_values("%", ascending=False)
                 .style.format({"%": fmt_pct, "Índice vs cidade": "{:.0f}", "Votos": "{:,.0f}"}),
                 width="stretch")

# ---------------------------------------------------------------- aba 3
with aba3:
    n = st.slider("Quantos candidatos (ranking da cidade)", 3, min(25, len(ranking)),
                  min(10, len(ranking)))
    modo = st.radio("Mostrar", ["% dos válidos", "Índice vs média da cidade"], horizontal=True)
    cols = ranking.index[:n]
    ordem = pivot.sum(axis=1).sort_values(ascending=False).index
    if modo == "% dos válidos":
        z = pct.loc[ordem, cols]
        escala, meio, fmt = SEQ, None, ".1f"
    else:
        z = pct.loc[ordem, cols].div(pct_cidade[cols]) * 100
        escala, meio, fmt = DIV, 100, ".0f"
    fig = px.imshow(z, color_continuous_scale=escala, color_continuous_midpoint=meio,
                    text_auto=fmt, aspect="auto")
    fig.update_traces(xgap=2, ygap=2,
                      hovertemplate="<b>%{y}</b><br>%{x}<br>%{z:.1f}<extra></extra>")
    fig.update_layout(height=max(400, 26 * len(z) + 140), margin=dict(l=10, r=10, t=10, b=10),
                      xaxis_title=None, yaxis_title=None, xaxis_side="top")
    fig.update_yaxes(type="category")
    st.plotly_chart(fig, width="stretch")
    if modo != "% dos válidos":
        st.caption("Azul = acima da média do candidato na cidade · vermelho = abaixo · cinza = na média.")

# ---------------------------------------------------------------- aba 4
with aba4:
    g = sec.groupby(col_grupo)[["QT_ELEITOR_SECAO", "VOTANTES"]].sum()
    g["Comparecimento"] = g["VOTANTES"] / g["QT_ELEITOR_SECAO"] * 100
    g = g.sort_values("Comparecimento")
    media = comp / aptos * 100
    fig = go.Figure(go.Bar(
        x=g["Comparecimento"], y=g.index.astype(str), orientation="h",
        marker=dict(color=SERIES[0], cornerradius=4),
        customdata=g[["VOTANTES", "QT_ELEITOR_SECAO"]],
        hovertemplate="<b>%{y}</b><br>%{x:.1f}%<br>%{customdata[0]:,} de %{customdata[1]:,}"
                      " eleitores<extra></extra>",
    ))
    fig.add_vline(x=media, line_dash="dot", line_color=OUTROS,
                  annotation_text=f"cidade {media:.1f}%", annotation_position="top")
    fig.update_layout(height=max(380, 22 * len(g) + 80), margin=dict(l=10, r=20, t=40, b=10),
                      xaxis_title="% de comparecimento", xaxis_range=[50, 100], bargap=0.25)
    st.plotly_chart(fig, width="stretch")
    st.caption("Comparecimento = votos para Governador ÷ eleitores aptos da seção. "
               "Eleitores em trânsito podem distorcer levemente algumas seções.")

# ---------------------------------------------------------------- aba 6
with aba6:
    st.info("O perfil é dos **eleitores aptos** de cada seção (cadastro do TSE, jul/2026), não de quem "
            "compareceu. As relações abaixo são entre **seções**, não entre pessoas: mostram onde o "
            "candidato foi melhor, não provam como cada grupo votou.", icon="ℹ️")

    # ---- perfil por grupo
    st.subheader(f"Perfil por {nome_grupo.lower()}")
    grupo_secao = secoes.set_index("NR_SECAO")[col_grupo] if col_grupo != "NR_SECAO" \
        else secoes.set_index("NR_SECAO").index.to_series()
    tab_perfil = indicadores(perfil_secao.groupby(grupo_secao).sum())
    cidade = indicadores(perfil_secao.sum().to_frame().T).iloc[0]
    ind = st.selectbox("Indicador", list(INDICADORES), key="ind_grupo")
    g = tab_perfil.sort_values(ind)
    fig = go.Figure(go.Bar(
        x=g[ind], y=g.index.astype(str), orientation="h",
        marker=dict(color=SERIES[0], cornerradius=4),
        customdata=g[["Eleitores"]],
        hovertemplate="<b>%{y}</b><br>%{x:.1f}<br>%{customdata[0]:,} eleitores<extra></extra>",
    ))
    fig.add_vline(x=cidade[ind], line_dash="dot", line_color=OUTROS,
                  annotation_text=f"cidade {cidade[ind]:.1f}", annotation_position="top")
    fig.update_layout(height=max(380, 22 * len(g) + 80), margin=dict(l=10, r=20, t=40, b=10),
                      xaxis_title=ind, yaxis_title=None, bargap=0.25)
    fig.update_yaxes(type="category")
    st.plotly_chart(fig, width="stretch")
    with st.expander("Tabela com todos os indicadores"):
        st.dataframe(tab_perfil.sort_values("Eleitores", ascending=False)
                     .style.format("{:.1f}").format("{:,.0f}", subset=["Eleitores"]),
                     width="stretch")

    # ---- distribuição de idade: grupo vs cidade
    st.subheader("Distribuição de idade")
    escolha = st.selectbox(nome_grupo, tab_perfil.sort_values("Eleitores", ascending=False).index,
                           key="grupo_idade")
    faixas = [16, 25, 35, 45, 55, 65, 75, 200]
    rot = ["16-24", "25-34", "35-44", "45-54", "55-64", "65-74", "75+"]
    pf = perfil.assign(GRUPO=perfil["NR_SECAO"].map(grupo_secao),
                       FAIXA=pd.cut(perfil["IDADE"], faixas, right=False, labels=rot))
    dist_g = pf[pf["GRUPO"] == escolha].groupby("FAIXA", observed=False)["QT_ELEITORES"].sum()
    dist_c = pf.groupby("FAIXA", observed=False)["QT_ELEITORES"].sum()
    fig = go.Figure([
        go.Bar(name=str(escolha), x=rot, y=dist_g / dist_g.sum() * 100,
               marker=dict(color=SERIES[0], cornerradius=4),
               hovertemplate="%{x}: %{y:.1f}%<extra>" + str(escolha) + "</extra>"),
        go.Bar(name="Cidade", x=rot, y=dist_c / dist_c.sum() * 100,
               marker=dict(color=OUTROS, cornerradius=4),
               hovertemplate="%{x}: %{y:.1f}%<extra>Cidade</extra>"),
    ])
    fig.update_layout(barmode="group", height=340, margin=dict(l=10, r=10, t=30, b=10),
                      yaxis_title="% dos eleitores", bargap=0.25, bargroupgap=0.08,
                      legend=dict(orientation="h", y=1.12, x=0))
    st.plotly_chart(fig, width="stretch")

    # ---- voto x perfil (por seção)
    st.subheader(f"{cargo}: voto × perfil, seção a seção")
    votos_secao = validos.pivot_table(index="NR_SECAO", columns="CANDIDATO", values="QT_VOTOS",
                                      aggfunc="sum", fill_value=0)
    pct_secao = votos_secao.div(votos_secao.sum(axis=1), axis=0) * 100
    ind_secao = indicadores(perfil_secao)

    n_top = min(8, len(ranking))
    corr = pd.DataFrame({
        i: [pct_secao[c].corr(ind_secao[i]) for c in ranking.index[:n_top]] for i in INDICADORES
    }, index=ranking.index[:n_top])
    fig = px.imshow(corr, color_continuous_scale=DIV, zmin=-1, zmax=1, text_auto=".2f",
                    aspect="auto")
    fig.update_traces(xgap=2, ygap=2,
                      hovertemplate="<b>%{y}</b><br>%{x}<br>correlação %{z:.2f}<extra></extra>")
    fig.update_layout(height=120 + 34 * n_top, margin=dict(l=10, r=10, t=10, b=10),
                      xaxis_title=None, yaxis_title=None, xaxis_side="top")
    st.plotly_chart(fig, width="stretch")
    st.caption("Correlação entre o % do candidato na seção e o indicador (161 seções). "
               "Azul = vai melhor onde o indicador é mais alto · vermelho = vai pior · "
               "|r| < 0,3 fraca, 0,3–0,5 moderada, > 0,5 forte.")

    c1, c2 = st.columns(2)
    cand_p = c1.selectbox("Candidato", ranking.index[:max(n_top, 15)], key="cand_perfil")
    ind_p = c2.selectbox("Indicador", list(INDICADORES), key="ind_perfil")
    d = ind_secao[[ind_p]].join(pct_secao[cand_p].rename("pct"), how="inner").join(
        secoes.set_index("NR_SECAO")[["NM_LOCAL_VOTACAO", "BAIRRO"]])
    r = d[ind_p].corr(d["pct"])
    a, b = np.polyfit(d[ind_p], d["pct"], 1)
    xs = np.linspace(d[ind_p].min(), d[ind_p].max(), 50)
    fig = go.Figure([
        go.Scatter(x=d[ind_p], y=d["pct"], mode="markers", name="Seção",
                   marker=dict(size=9, color=cor(cand_p), opacity=0.8,
                               line=dict(width=1.5, color="#ffffff")),
                   customdata=np.c_[d.index, d["NM_LOCAL_VOTACAO"], d["BAIRRO"]],
                   hovertemplate="<b>Seção %{customdata[0]}</b> · %{customdata[2]}<br>"
                                 "%{customdata[1]}<br>" + ind_p + ": %{x:.1f}<br>"
                                 + cand_p + ": %{y:.1f}%<extra></extra>"),
        go.Scatter(x=xs, y=a * xs + b, mode="lines", name="Tendência",
                   line=dict(color=OUTROS, width=2, dash="dot"), hoverinfo="skip"),
    ])
    fig.update_layout(height=440, margin=dict(l=10, r=10, t=10, b=10), showlegend=False,
                      xaxis_title=ind_p, yaxis_title=f"% de {cand_p} nos válidos")
    st.plotly_chart(fig, width="stretch")
    forca = "fraca" if abs(r) < 0.3 else "moderada" if abs(r) < 0.5 else "forte"
    unidade = "ano" if ind_p == "Idade média" else "ponto percentual"
    br = lambda x: f"{x:+.2f}".replace(".", ",")
    st.markdown(f"Correlação **{br(r)}** ({forca}). Em média, cada **+1 {unidade}** em "
                f"*{ind_p.lower()}* acompanha **{br(a)} p.p.** para {cand_p}.")

# ---------------------------------------------------------------- aba 5
with aba5:
    st.write(f"Votos válidos de **{cargo}** por {nome_grupo.lower()} × candidato")
    st.dataframe(pivot, width="stretch")
    st.download_button("Baixar CSV", pivot.to_csv(sep=";", encoding="utf-8-sig").encode("utf-8-sig"),
                       file_name=f"itapira_2026_{cargo.lower().replace(' ', '_')}_{col_grupo.lower()}.csv")
    st.write("Seções → locais → bairros")
    st.dataframe(secoes, width="stretch", hide_index=True)
