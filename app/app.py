"""
Painel: votação de Itapira (Zona 54) por bairro - Eleições 2026, 1º turno.

Rodar:  streamlit run app/app.py
Dados:  gerados por etl/preparar_dados.py e etl/preparar_2022.py; bairros em mapping/bairros.csv
IA:     defina ANTHROPIC_API_KEY nos Secrets do Streamlit (ou no ambiente) para as análises em texto
"""
import hmac
import os
from pathlib import Path

import folium
import numpy as np
import pandas as pd
import plotly.graph_objects as go
import streamlit as st
from plotly.subplots import make_subplots
from streamlit_folium import st_folium

import insights

ROOT = Path(__file__).resolve().parent.parent
DADOS = ROOT / "data" / "itapira"
MAPPING = ROOT / "mapping" / "bairros.csv"

BRANCO, NULO = 95, 96
# Paleta categórica (ordem fixa, validada para daltonismo nas 3 primeiras posições)
# (azul, laranja "corrige", verde "confirma" - as teclas da urna)
SERIES = ["#1565d8", "#eb6834", "#1baf7a"]
OUTROS = "#8a93a6"

# identidade visual
MARINHO, AZUL, AMARELO = "#0b2557", "#1565d8", "#f6b500"
CSS = f"""
<style>
.block-container {{ padding-top: 4rem; }}
h1, h2, h3 {{ text-transform: uppercase; letter-spacing: .01em; }}
h3 {{ font-size: 1.6rem !important; }}
h3::after {{ content: ""; display: block; width: 56px; height: 5px; margin-top: 6px;
            background: {AMARELO}; border-radius: 3px; }}
[data-testid="stSidebar"] h1::after {{ display: none; }}

.in-hero {{ display: grid; grid-template-columns: 1fr 1.25fr; gap: 1.25rem; align-items: stretch;
           margin-bottom: 1.25rem; }}
.in-hero .marca {{ padding: .5rem 0; }}
.in-hero .eleicoes {{ font-family: "Barlow Condensed", sans-serif; font-weight: 900; line-height: .85;
                     font-size: clamp(2.6rem, 6vw, 4.6rem); color: {MARINHO}; }}
.in-hero .ano {{ color: {AZUL}; }}
.in-hero .barra {{ width: 42%; height: 8px; background: {AMARELO}; border-radius: 4px; margin: .8rem 0 .6rem; }}
.in-hero .local {{ font-weight: 700; color: {MARINHO}; font-size: 1.05rem; letter-spacing: .02em; }}
.in-hero .local span {{ font-weight: 500; opacity: .75; }}
.in-hero .caixa {{ background: linear-gradient(135deg, {MARINHO} 0%, #12398a 100%); color: #fff;
                  border-radius: 14px; padding: 1.2rem 1.5rem; display: flex; flex-direction: column;
                  justify-content: center; box-shadow: 0 8px 24px rgba(11,37,87,.18);
                  font-family: "Barlow Condensed", sans-serif; text-transform: uppercase; line-height: 1; }}
.in-hero .caixa .linha {{ font-weight: 800; font-size: clamp(1.2rem, 2.2vw, 1.8rem); }}
.in-hero .caixa .destaque {{ font-weight: 900; color: {AMARELO}; font-size: clamp(2rem, 4.2vw, 3.4rem); }}
@media (max-width: 760px) {{ .in-hero {{ grid-template-columns: 1fr; }} }}

.in-kpis {{ display: grid; grid-template-columns: repeat(4, 1fr); gap: .9rem; margin-bottom: 1.2rem; }}
.in-kpi {{ background: #fff; border-radius: 12px; padding: .9rem 1.1rem; border-left: 6px solid {AZUL};
          box-shadow: 0 2px 10px rgba(11,37,87,.07); }}
.in-kpi .rotulo {{ font-size: .78rem; font-weight: 700; text-transform: uppercase; letter-spacing: .04em;
                  color: #5a6b8c; }}
.in-kpi .valor {{ font-family: "Barlow Condensed", sans-serif; font-weight: 800; font-size: 2.3rem;
                 color: {MARINHO}; line-height: 1.1; }}
.in-kpi .apoio {{ font-size: .85rem; font-weight: 600; color: #5a6b8c; margin-top: .15rem; }}
@media (max-width: 760px) {{ .in-kpis {{ grid-template-columns: repeat(2, 1fr); }} }}

[data-testid="stTab"] p {{ font-family: "Barlow Condensed", sans-serif; font-weight: 800;
                          text-transform: uppercase; font-size: 1.1rem; letter-spacing: .02em; }}
[data-testid="stTab"][aria-selected="true"] p {{ color: {MARINHO}; }}
[role="tablist"] .react-aria-SelectionIndicator {{ background-color: {AMARELO} !important; height: 4px; }}

[class*="st-key-insight"] {{ background: #fff; border-radius: 14px; border-left: 6px solid {AMARELO};
                            padding: 1rem 1.4rem .6rem; box-shadow: 0 2px 12px rgba(11,37,87,.08);
                            margin: .4rem 0 1.4rem; }}
[class*="st-key-insight"] .in-insight-titulo {{ font-family: "Barlow Condensed", sans-serif; font-weight: 800;
                            text-transform: uppercase; font-size: 1.3rem; color: {MARINHO}; }}
[class*="st-key-insight"] li {{ margin-bottom: .35rem; }}

.in-rodape {{ margin-top: 2.5rem; padding: 1rem 1.25rem; border-radius: 12px; background: {MARINHO};
             color: #cfd9ee; font-size: .85rem; }}
.in-rodape b {{ color: #fff; }}
</style>
"""


def hero(destaque: str, linha_cima: str = "Resultado da votação para", linha_baixo: str = ""):
    st.markdown(CSS + f"""
<div class="in-hero">
  <div class="marca">
    <div class="eleicoes">ELEIÇÕES<br><span class="ano">2026</span></div>
    <div class="barra"></div>
    <div class="local">ITAPIRA, SP <span>| 1º TURNO</span></div>
  </div>
  <div class="caixa">
    <div class="linha">{linha_cima}</div>
    <div class="destaque">{destaque}</div>
    <div class="linha">{linha_baixo}</div>
  </div>
</div>""", unsafe_allow_html=True)


def mostrar(fig):
    """Plotly com margem automática (nomes longos de bairro não cortam)."""
    fig.update_xaxes(automargin=True)
    fig.update_yaxes(automargin=True)
    # automargin nem sempre basta no Streamlit: reserva espaço pelo maior rótulo de texto do eixo y
    rotulos = [str(y) for t in fig.data if t.y is not None and t.type in ("bar", "scatter")
               for y in t.y if isinstance(y, str)]
    if rotulos:
        fig.update_layout(margin_l=max(fig.layout.margin.l or 0, 7 * max(map(len, rotulos)) + 10))
    st.plotly_chart(fig, width="stretch")


def kpis(itens: list[tuple]):
    """Cartões (rótulo, valor) ou (rótulo, valor, linha de apoio)."""
    cards = "".join(
        f'<div class="in-kpi"><div class="rotulo">{i[0]}</div><div class="valor">{i[1]}</div>'
        + (f'<div class="apoio">{i[2]}</div>' if len(i) > 2 else "") + "</div>"
        for i in itens)
    st.markdown(f'<div class="in-kpis">{cards}</div>', unsafe_allow_html=True)


def pc(x):
    return f"{x:.1f}%".replace(".", ",")


def pp(x):
    return f"{x:+.1f}".replace(".", ",") + " p.p."


def num(n):
    return f"{int(round(n)):,}".replace(",", ".")


APELIDOS = {"Luiz Inácio Lula Da Silva": "Lula"}  # quando primeiro + último nome não reconhece


def curto(nome: str) -> str:
    """'Flavio Nantes Bolsonaro' -> 'Flavio Bolsonaro' (rótulos de gráfico)."""
    if nome.startswith("Legenda") or nome in APELIDOS:
        return APELIDOS.get(nome, nome)
    p = nome.split()
    return nome if len(p) <= 2 else f"{p[0]} {p[-1]}"


# (coluna, singular, plural)
AGRUPAMENTOS = {
    "Bairro": ("BAIRRO", "bairro", "bairros"),
    "Local de votação": ("NM_LOCAL_VOTACAO", "local de votação", "locais de votação"),
    "Seção": ("NR_SECAO", "seção", "seções"),
}

st.set_page_config(page_title="Itapira 2026 · votos por bairro", page_icon="🗳️", layout="wide")


# ---------------------------------------------------------------- acesso e IA
def segredo(nome: str):
    try:
        return st.secrets.get(nome)
    except FileNotFoundError:  # rodando local sem secrets.toml
        return None


SENHA = segredo("senha")
API_KEY = segredo("ANTHROPIC_API_KEY") or os.environ.get("ANTHROPIC_API_KEY")

if SENHA and not st.session_state.get("autenticado"):
    hero("Acesso restrito", "Painel de votação", "Digite a senha para entrar")
    with st.form("login"):
        digitada = st.text_input("Senha", type="password")
        if st.form_submit_button("Entrar"):
            if hmac.compare_digest(digitada, str(SENHA)):
                st.session_state["autenticado"] = True
                st.rerun()
            st.error("Senha incorreta.")
    st.stop()

PENDENTES = []  # (placeholder, future, fatos) preenchidos no fim da página


def _render_insight(ph, chave: str, texto: str | None, fatos: list[str], carregando: bool,
                    final: bool = False):
    # a chave muda no preenchimento final: o Streamlit não aceita a mesma chave duas vezes por execução
    with ph.container(key=f"insight_{chave}{'_final' if final else ''}"):
        st.markdown('<div class="in-insight-titulo">💡 O que os números dizem</div>',
                    unsafe_allow_html=True)
        if texto:
            st.markdown(texto)
            st.caption("Análise escrita por IA (Claude) a partir dos números desta página. "
                       "Os valores vêm do TSE; confira nos gráficos abaixo.")
        else:
            st.markdown("\n".join(f"- {f}" for f in fatos))
            st.caption("⏳ Gerando a análise por IA…" if carregando
                       else "Destaques calculados automaticamente a partir dos dados do TSE.")


def bloco_insight(chave: str, titulo: str, fatos: list[str], tabela: pd.DataFrame | None = None):
    """Mostra os fatos e, se houver chave de API, troca pela análise do Claude quando ficar pronta."""
    csv = tabela.round(1).to_csv(sep=";") if tabela is not None else ""
    ph = st.empty()
    fut = insights.pedir(API_KEY, titulo, fatos, csv)
    if fut is not None and fut.done():
        _render_insight(ph, chave, fut.result(), fatos, False)
    else:
        _render_insight(ph, chave, None, fatos, fut is not None)
        if fut is not None:
            PENDENTES.append((ph, chave, fut, fatos))


# ---------------------------------------------------------------- dados
@st.cache_data
def carregar():
    votos = pd.read_parquet(DADOS / "votos_secao.parquet")
    secoes = pd.read_csv(DADOS / "secoes.csv")
    mapa = pd.read_csv(MAPPING, encoding="utf-8-sig")
    mapa["BAIRRO"] = mapa["BAIRRO"].fillna(mapa["BAIRRO_TSE"]).str.strip()
    # coordenadas também podem ser corrigidas no mapping
    secoes = secoes.drop(columns=["NR_LATITUDE", "NR_LONGITUDE"]).merge(
        mapa[["NR_LOCAL_VOTACAO", "BAIRRO", "NR_LATITUDE", "NR_LONGITUDE"]],
        on="NR_LOCAL_VOTACAO", how="left")
    votos = votos.drop(columns=["NR_LOCAL_VOTACAO", "NM_LOCAL_VOTACAO"]).merge(
        secoes[["NR_SECAO", "NR_LOCAL_VOTACAO", "NM_LOCAL_VOTACAO", "BAIRRO"]],
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


# nome -> (coluna somada, descrição de "mais" e "menos" para o texto)
INDICADORES = {
    "Idade média": ("w_idade", "eleitorado mais velho", "eleitorado mais jovem"),
    "% jovens (16-29)": ("jovens", "mais jovens de 16 a 29 anos", "menos jovens de 16 a 29 anos"),
    "% idosos (60+)": ("idosos", "mais eleitores com 60 anos ou mais", "menos eleitores com 60+"),
    "% mulheres": ("mulheres", "mais mulheres", "menos mulheres"),
    "% com ensino superior (completo ou não)": ("superior", "mais eleitores com ensino superior",
                                                "menos eleitores com ensino superior"),
    "% até fundamental completo": ("fundamental", "mais eleitores com até o fundamental",
                                   "menos eleitores com até o fundamental"),
    "% casados": ("casados", "mais casados", "menos casados"),
}


def indicadores(soma: pd.DataFrame) -> pd.DataFrame:
    """Converte somas (por seção ou agregadas) em idade média / percentuais."""
    out = pd.DataFrame(index=soma.index)
    for nome, (col, _, _) in INDICADORES.items():
        f = 1 if nome == "Idade média" else 100
        out[nome] = soma[col] / soma["QT_ELEITORES"] * f
    out["Eleitores"] = soma["QT_ELEITORES"]
    return out


perfil, perfil_secao = carregar_perfil()


@st.cache_data
def carregar_2022():
    """Presidente 2022 por seção (gerado por etl/preparar_2022.py)."""
    if not (DADOS / "votos_2022.parquet").exists():
        return None, None
    return pd.read_parquet(DADOS / "votos_2022.parquet"), pd.read_csv(DADOS / "secoes_2022.csv")


v22, secoes_22 = carregar_2022()

# Ligação entre os anos pelo número na urna: 22 = Jair (2022) / Flávio (2026); 13 = Lula
CAMPOS = {"Bolsonaro (22)": SERIES[0], "Lula (13)": SERIES[1], "Demais candidatos": SERIES[2]}


def votos_por_campo(df: pd.DataFrame, grupo: pd.Series) -> pd.DataFrame:
    """Votos (NR_SECAO, NR_VOTAVEL, QT_VOTOS) -> votos por grupo x campo."""
    campo = np.select([df["NR_VOTAVEL"] == 22, df["NR_VOTAVEL"] == 13,
                       df["NR_VOTAVEL"].isin([BRANCO, NULO])],
                      ["Bolsonaro (22)", "Lula (13)", "Brancos e nulos"], "Demais candidatos")
    return (df.assign(CAMPO=campo, GRUPO=df["NR_SECAO"].map(grupo))
              .pivot_table(index="GRUPO", columns="CAMPO", values="QT_VOTOS", aggfunc="sum",
                           fill_value=0))


def pct_validos(p):
    """% de cada campo sobre os votos válidos (Series da cidade ou DataFrame por grupo)."""
    if isinstance(p, pd.Series):
        p = p.reindex(list(CAMPOS), fill_value=0)
        return p / p.sum() * 100
    p = p.reindex(columns=list(CAMPOS), fill_value=0)
    return p.div(p.sum(axis=1), axis=0) * 100


sem_bairro = votos["BAIRRO"].isna().sum()

# ---------------------------------------------------------------- filtros
st.sidebar.title("📊 Itapira · 2026")
st.sidebar.caption("Zona 0054 · 1º turno")

ordem_cargos = ["Presidente", "Governador", "Senador", "Deputado Federal", "Deputado Estadual"]
cargos = [c for c in ordem_cargos if c in votos["DS_CARGO"].unique()]
cargo = st.sidebar.selectbox("Cargo", cargos)
nome_grupo = st.sidebar.radio("Agrupar por", list(AGRUPAMENTOS))
col_grupo, g_sing, g_plur = AGRUPAMENTOS[nome_grupo]

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


# seção -> grupo escolhido (mapeamento de 2026; usado também para 2022)
grupo_secao = secoes.set_index("NR_SECAO")[col_grupo] if col_grupo != "NR_SECAO" \
    else secoes.set_index("NR_SECAO").index.to_series()
if col_grupo == "NR_SECAO":
    grupo_secao = grupo_secao.map(lambda s: f"Seção {s}")
validos["GRUPO"] = validos["NR_SECAO"].map(grupo_secao)

# tabela grupo x candidato
pivot = validos.pivot_table(index="GRUPO", columns="CANDIDATO", values="QT_VOTOS",
                            aggfunc="sum", fill_value=0)
pivot = pivot[ranking.index]
pct = pivot.div(pivot.sum(axis=1), axis=0) * 100
pct_cidade = ranking / total_validos * 100
n_grupos = len(pivot)

# comparecimento: Governador (1 voto por eleitor, todas as seções)
votantes = (votos[votos["DS_CARGO"] == "Governador"].groupby("NR_SECAO")["QT_VOTOS"].sum()
            .rename("VOTANTES"))
sec = secoes.merge(votantes, on="NR_SECAO", how="left").fillna({"VOTANTES": 0})
sec["GRUPO"] = sec["NR_SECAO"].map(grupo_secao)

NOTA_CARGO = []
if cargo == "Senador":
    NOTA_CARGO.append("Para Senador, cada eleitor podia votar em 2 candidatos; os percentuais são "
                      "sobre o total de votos válidos dados.")
if col_grupo != "NR_SECAO":
    NOTA_CARGO.append(f"O {g_sing} é o do local de votação, não o endereço de quem votou.")

# ---------------------------------------------------------------- cabeçalho
hero(cargo, linha_baixo=f"em Itapira · por {g_sing}")
aptos = int(sec["QT_ELEITOR_SECAO"].sum())
comp = int(sec["VOTANTES"].sum())
bn = v[v["TIPO"].isin(["Branco", "Nulo"])]["QT_VOTOS"].sum()
kpis([
    ("Eleitores aptos", num(aptos)),
    ("Comparecimento", pc(comp / aptos * 100)),
    ("Votos válidos" + (" (com legenda)" if legenda else ""), num(total_validos)),
    ("Brancos + nulos", pc(bn / v["QT_VOTOS"].sum() * 100)),
])
if sem_bairro:
    st.warning(f"{sem_bairro} linhas de voto sem bairro mapeado - confira mapping/bairros.csv.")

aba1, aba2, aba3, aba4, aba5, aba6, aba7 = st.tabs(
    ["🏆 Quem venceu onde", "👤 Desempenho por candidato", "⚔️ Confronto",
     "🚶 Comparecimento", "👥 Perfil do eleitorado", "🔁 2022 × 2026", "📄 Dados"])


def barras_h(serie: pd.Series, cores, texto, hover: str, titulo_x: str, media: float | None = None,
             rotulo_media: str = "", custom=None, x_range=None):
    """Barras horizontais ordenadas, com rótulo de valor na ponta e linha da média da cidade."""
    fig = go.Figure(go.Bar(
        x=serie.values, y=serie.index.astype(str), orientation="h",
        marker=dict(color=cores, cornerradius=4), text=texto, textposition="outside",
        cliponaxis=False, customdata=custom, hovertemplate=hover,
    ))
    if media is not None:
        fig.add_vline(x=media, line_dash="dot", line_color=OUTROS,
                      annotation_text=rotulo_media, annotation_position="top")
    fig.update_layout(height=max(380, 24 * len(serie) + 90), margin=dict(l=10, r=60, t=40, b=10),
                      xaxis_title=titulo_x, yaxis_title=None, bargap=0.25)
    if not x_range:  # folga nas pontas para os rótulos de texto não serem cortados
        lo, hi = min(0, serie.min()), max(0, serie.max())
        maior_rotulo = max((len(str(t)) for t in texto), default=0) if isinstance(texto, list) else 8
        folga = (hi - lo) * (0.15 + 0.02 * maior_rotulo)
        x_range = [lo - folga if lo < 0 else 0, hi + folga if hi > 0 else 0]
    fig.update_xaxes(range=x_range)
    fig.update_yaxes(type="category")
    mostrar(fig)


# ---------------------------------------------------------------- aba 1: vencedores
with aba1:
    top2 = pd.DataFrame({
        "1º": pct.idxmax(axis=1),
        "% 1º": pct.max(axis=1),
        "2º": pct.apply(lambda r: r.nlargest(2).index[-1], axis=1),
        "% 2º": pct.apply(lambda r: r.nlargest(2).iloc[-1], axis=1),
        "Votos válidos": pivot.sum(axis=1),
    })
    top2["Diferença (p.p.)"] = top2["% 1º"] - top2["% 2º"]
    top2 = top2.sort_values("Votos válidos", ascending=False)

    vit = top2["1º"].value_counts()
    c1, c2 = ranking.index[0], ranking.index[1]
    apertado = top2.sort_values("Diferença (p.p.)").iloc[0]
    folgado = top2.sort_values("Diferença (p.p.)").iloc[-1]
    fatos = [
        f"{cargo} em Itapira: {c1} teve {pc(pct_cidade[c1])} dos votos válidos ({num(ranking[c1])} "
        f"votos); {c2} teve {pc(pct_cidade[c2])} ({num(ranking[c2])}).",
        "Vitórias por " + g_sing + ": " + "; ".join(f"{c} em {n} de {n_grupos}" for c, n in vit.items()) + ".",
        f"Disputa mais apertada: {apertado.name} ({apertado['1º']} {pc(apertado['% 1º'])} × "
        f"{apertado['2º']} {pc(apertado['% 2º'])}, diferença de {pc(apertado['Diferença (p.p.)'])[:-1]} p.p.).",
        f"Maior vantagem: {folgado.name} ({folgado['1º']} {pc(folgado['% 1º'])} × "
        f"{folgado['2º']} {pc(folgado['% 2º'])}).",
    ]
    if len(ranking) > 2:
        fatos.append("Demais mais votados na cidade: " + "; ".join(
            f"{c} {pc(pct_cidade[c])}" for c in ranking.index[2:6]) + ".")
    bloco_insight(f"venc_{cargo}_{col_grupo}_{legenda}", f"{cargo}: quem venceu em cada {g_sing}",
                  fatos + NOTA_CARGO,
                  top2.drop(columns="Votos válidos").head(30) if n_grupos <= 30 else None)

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
        st.caption("Cada círculo é um local de votação. Cor = quem foi mais votado ali · "
                   "tamanho = quantidade de votos · "
                   + " · ".join(f"<span style='color:{c}'>●</span> {n}" for n, c in cor_cand.items())
                   + f" · <span style='color:{OUTROS}'>●</span> outros", unsafe_allow_html=True)
    with c_tab:
        st.subheader(f"1º e 2º colocados por {g_sing}")
        st.dataframe(
            top2.rename_axis(nome_grupo).style.format(
                {"% 1º": pc, "% 2º": pc, "Diferença (p.p.)": "{:.1f}", "Votos válidos": "{:,.0f}"}),
            height=460, width="stretch")

# ---------------------------------------------------------------- aba 2: candidato
with aba2:
    cand = st.selectbox("Candidato", ranking.index,
                        format_func=lambda c: f"{c} - {num(ranking[c])} votos ({pc(pct_cidade[c])})")
    serie = pd.DataFrame({"Votos": pivot[cand], "%": pct[cand]})
    serie["Diferença para a média (p.p.)"] = serie["%"] - pct_cidade[cand]
    serie = serie.sort_values("%")
    acima = (serie["Diferença para a média (p.p.)"] > 0).sum()
    melhores, piores = serie.iloc[::-1].head(3), serie.head(3)
    posicao = list(ranking.index).index(cand) + 1
    fatos = [
        f"{cand} ficou em {posicao}º lugar na cidade, com {pc(pct_cidade[cand])} dos votos válidos "
        f"({num(ranking[cand])} votos).",
        f"Ficou acima da própria média da cidade em {acima} de {n_grupos} {g_plur}.",
        "Melhores resultados: " + "; ".join(f"{g} {pc(r['%'])}" for g, r in melhores.iterrows()) + ".",
        "Piores resultados: " + "; ".join(f"{g} {pc(r['%'])}" for g, r in piores.iterrows()) + ".",
        f"Distância entre o melhor e o pior {g_sing}: {pc(melhores['%'].iloc[0] - piores['%'].iloc[0])[:-1]} p.p.",
    ]
    bloco_insight(f"cand_{cargo}_{col_grupo}_{legenda}_{cand}", f"{cargo}: desempenho de {cand}",
                  fatos + NOTA_CARGO)

    st.subheader(f"{curto(cand)} em cada {g_sing}")
    barras_h(serie["%"], cor(cand), [pc(x) for x in serie["%"]],
             "<b>%{y}</b><br>%{x:.1f}% dos válidos<br>%{customdata[0]:,} votos<extra></extra>",
             "% dos votos válidos", pct_cidade[cand], f"média da cidade {pc(pct_cidade[cand])}",
             custom=serie[["Votos"]])
    st.caption("Barras à direita da linha pontilhada = o candidato foi melhor ali do que na cidade "
               "como um todo.")
    with st.expander("Ver tabela"):
        st.dataframe(serie.sort_values("%", ascending=False).rename_axis(nome_grupo)
                     .style.format({"%": pc, "Diferença para a média (p.p.)": "{:+.1f}",
                                    "Votos": "{:,.0f}"}), width="stretch")

# ---------------------------------------------------------------- aba 3: confronto
with aba3:
    if len(ranking) < 2:
        st.info("Este cargo tem só um candidato.")
    else:
        ca, cb = st.columns(2)
        a = ca.selectbox("Candidato A", ranking.index, index=0, key="conf_a")
        b = cb.selectbox("Candidato B", [c for c in ranking.index if c != a], index=0, key="conf_b")
        cor_a = cor(a) if cor(a) != OUTROS else SERIES[0]
        cor_b = cor(b) if cor(b) not in (OUTROS, cor_a) else next(c for c in SERIES if c != cor_a)

        dif = (pct[a] - pct[b]).sort_values()
        frente_a, frente_b = (dif > 0).sum(), (dif < 0).sum()
        kpis([
            (curto(a), pc(pct_cidade[a]), f"{num(ranking[a])} votos"),
            (curto(b), pc(pct_cidade[b]), f"{num(ranking[b])} votos"),
            (f"{g_plur} com {curto(a)} à frente", f"{frente_a} de {n_grupos}"),
            (f"{g_plur} com {curto(b)} à frente", f"{frente_b} de {n_grupos}"),
        ])
        fatos = [
            f"Na cidade: {a} {pc(pct_cidade[a])} × {b} {pc(pct_cidade[b])} "
            f"(diferença de {pc(abs(pct_cidade[a] - pct_cidade[b]))[:-1]} p.p.).",
            f"{a} ficou à frente de {b} em {frente_a} de {n_grupos} {g_plur}; {b} à frente em {frente_b}.",
            f"Maiores vantagens de {a} sobre {b}: " + "; ".join(
                f"{g} ({pp(x)})" for g, x in dif.iloc[::-1].head(3).items()) + ".",
            f"Menores vantagens de {a} sobre {b} (negativo = {b} à frente): " + "; ".join(
                f"{g} ({pp(x)})" for g, x in dif.head(3).items()) + ".",
        ]
        bloco_insight(f"conf_{cargo}_{col_grupo}_{legenda}_{a}_{b}", f"{cargo}: {a} × {b}",
                      fatos + NOTA_CARGO)

        st.subheader(f"Vantagem em cada {g_sing}")
        rot = [f"{curto(a) if x > 0 else curto(b)} +" + f"{abs(x):.1f}".replace(".", ",") for x in dif]
        barras_h(dif, [cor_a if x > 0 else cor_b for x in dif], rot,
                 "<b>%{y}</b><br>" + curto(a) + ": %{customdata[0]:.1f}%<br>" + curto(b)
                 + ": %{customdata[1]:.1f}%<extra></extra>",
                 f"pontos percentuais (← {curto(b)} à frente · {curto(a)} à frente →)",
                 0, "", custom=np.c_[pct[a].reindex(dif.index), pct[b].reindex(dif.index)])
        st.markdown(f"<span style='color:{cor_a}'>●</span> **{curto(a)}** à frente &nbsp;&nbsp; "
                    f"<span style='color:{cor_b}'>●</span> **{curto(b)}** à frente · "
                    "o número é a diferença entre os dois, em pontos percentuais.",
                    unsafe_allow_html=True)

# ---------------------------------------------------------------- aba 4: comparecimento
with aba4:
    g = sec.groupby("GRUPO")[["QT_ELEITOR_SECAO", "VOTANTES"]].sum()
    g["Comparecimento"] = g["VOTANTES"] / g["QT_ELEITOR_SECAO"] * 100
    g = g.sort_values("Comparecimento")
    media = comp / aptos * 100
    fatos = [
        f"Comparecimento na cidade: {pc(media)} ({num(comp)} de {num(aptos)} eleitores aptos); "
        f"abstenção de {pc(100 - media)}.",
        "Maior comparecimento: " + "; ".join(f"{i} {pc(r['Comparecimento'])}"
                                            for i, r in g.iloc[::-1].head(3).iterrows()) + ".",
        "Menor comparecimento: " + "; ".join(f"{i} {pc(r['Comparecimento'])}"
                                            for i, r in g.head(3).iterrows()) + ".",
        "Comparecimento calculado pelos votos para Governador; eleitores em trânsito podem "
        "distorcer levemente algumas seções.",
    ]
    bloco_insight(f"comp_{col_grupo}", f"Comparecimento por {g_sing}", fatos)
    st.subheader(f"Comparecimento por {g_sing}")
    barras_h(g["Comparecimento"], SERIES[0], [pc(x) for x in g["Comparecimento"]],
             "<b>%{y}</b><br>%{x:.1f}%<br>%{customdata[0]:,} de %{customdata[1]:,} eleitores"
             "<extra></extra>", "% dos eleitores aptos que votaram", media, f"cidade {pc(media)}",
             custom=g[["VOTANTES", "QT_ELEITOR_SECAO"]], x_range=[50, 100])

# ---------------------------------------------------------------- aba 5: perfil
with aba5:
    tab_perfil = indicadores(perfil_secao.groupby(grupo_secao).sum())
    cidade = indicadores(perfil_secao.sum().to_frame().T).iloc[0]
    ind_secao = indicadores(perfil_secao)
    votos_secao = validos.pivot_table(index="NR_SECAO", columns="CANDIDATO", values="QT_VOTOS",
                                      aggfunc="sum", fill_value=0)
    top_c = list(ranking.index[:3])

    def tercos(ind: str) -> tuple[pd.DataFrame, list[str]]:
        """Divide as seções em 3 grupos iguais pelo indicador e soma os votos de cada grupo."""
        s = ind_secao[ind].reindex(votos_secao.index).dropna()
        t = pd.qcut(s.rank(method="first"), 3, labels=[0, 1, 2])
        soma = votos_secao.loc[s.index].groupby(t, observed=True).sum()
        res = soma[top_c].div(soma.sum(axis=1), axis=0) * 100
        faixa = s.groupby(t, observed=True).agg(["min", "max"])
        un = " anos" if ind == "Idade média" else "%"
        rot = [f"{f:.0f} a {m:.0f}{un}".replace(".", ",") for f, m in faixa.values]
        return res, rot

    fatos = [
        f"Eleitorado de Itapira (aptos): idade média de {cidade['Idade média']:.0f} anos, "
        f"{pc(cidade['% idosos (60+)'])} com 60 anos ou mais, {pc(cidade['% jovens (16-29)'])} "
        f"entre 16 e 29, {pc(cidade['% mulheres'])} mulheres, {pc(cidade['% com ensino superior (completo ou não)'])} "
        "com ensino superior (completo ou não).",
    ]
    if col_grupo != "NR_SECAO":
        velho, novo = tab_perfil["Idade média"].idxmax(), tab_perfil["Idade média"].idxmin()
        esc = tab_perfil["% com ensino superior (completo ou não)"]
        fatos.append(f"{g_sing.capitalize()} com eleitorado mais velho: {velho} "
                     f"({tab_perfil.loc[velho, 'Idade média']:.0f} anos em média); mais jovem: {novo} "
                     f"({tab_perfil.loc[novo, 'Idade média']:.0f} anos).")
        fatos.append(f"Maior fatia com ensino superior: {esc.idxmax()} ({pc(esc.max())}); "
                     f"menor: {esc.idxmin()} ({pc(esc.min())}).")
    for ind in ["Idade média", "% com ensino superior (completo ou não)", "% mulheres"]:
        res, rot = tercos(ind)
        _, mais, menos = INDICADORES[ind]
        partes = [f"{c} {pc(res.loc[2, c])} contra {pc(res.loc[0, c])}" for c in top_c]
        fatos.append(f"{cargo} - seções com {mais} (terço com {rot[2]}) × seções com {menos} "
                     f"(terço com {rot[0]}): " + "; ".join(partes) + ".")
    fatos.append("Limitação: o perfil é dos eleitores aptos de cada seção, não de quem votou, e a "
                 "comparação é entre seções, não entre pessoas; não mostra como cada grupo votou.")
    bloco_insight(f"perfil_{cargo}_{col_grupo}_{legenda}", f"{cargo}: voto e perfil do eleitorado",
                  fatos + NOTA_CARGO)

    st.subheader("Quem vai melhor onde")
    ind_t = st.selectbox("Comparar seções por", list(INDICADORES), key="ind_tercos")
    res, rot = tercos(ind_t)
    _, mais, menos = INDICADORES[ind_t]
    # um painel por candidato, cada um com a própria escala: diferenças de 2-3 p.p. ficam visíveis
    fig = make_subplots(rows=1, cols=len(top_c), subplot_titles=[curto(c) for c in top_c],
                        horizontal_spacing=0.08)
    for i, c in enumerate(top_c, start=1):
        y = res[c].values
        folga = max(1.5, (y.max() - y.min()) * 0.6)
        fig.add_trace(go.Scatter(
            x=rot, y=y, mode="lines+markers+text", line=dict(color=cor(c), width=2),
            marker=dict(size=10, color=cor(c), line=dict(width=2, color="#ffffff")),
            text=[pc(x) for x in y], textposition="top center", cliponaxis=False,
            hovertemplate=curto(c) + " · %{x}: %{y:.1f}%<extra></extra>", showlegend=False,
        ), row=1, col=i)
        fig.update_yaxes(range=[y.min() - folga, y.max() + folga], ticksuffix="%", row=1, col=i)
    fig.update_xaxes(type="category")
    fig.update_layout(height=360, margin=dict(l=10, r=10, t=40, b=10))
    st.plotly_chart(fig, width="stretch")
    st.caption(f"As 161 seções foram divididas em três grupos do mesmo tamanho pela "
               f"{ind_t.lower()}: da esquerda (seções com {menos}) para a direita (seções com {mais}). "
               "Cada ponto é quanto o candidato teve somando as seções do grupo. Linha subindo = o "
               "candidato vai melhor onde o indicador é mais alto. Atenção: cada painel tem a sua "
               "própria escala, e a comparação é entre seções, não entre pessoas.")

    if col_grupo != "NR_SECAO":
        st.subheader(f"Perfil por {g_sing}")
        ind = st.selectbox("Indicador", list(INDICADORES), key="ind_grupo")
        gp = tab_perfil[ind].sort_values()
        fmt = (lambda x: f"{x:.0f} anos") if ind == "Idade média" else pc
        barras_h(gp, SERIES[0], [fmt(x) for x in gp], "<b>%{y}</b><br>%{x:.1f}<extra></extra>",
                 ind, cidade[ind], f"cidade {fmt(cidade[ind])}")
        with st.expander("Tabela com todos os indicadores"):
            st.dataframe(tab_perfil.sort_values("Eleitores", ascending=False).rename_axis(nome_grupo)
                         .style.format("{:.1f}").format("{:,.0f}", subset=["Eleitores"]),
                         width="stretch")

# ---------------------------------------------------------------- aba 6: 2022 x 2026
with aba6:
    if v22 is None:
        st.warning("Dados de 2022 não encontrados. Rode `python etl/preparar_2022.py`.")
    else:
        turno = st.radio("Comparar 2026 com", ["1º turno de 2022", "2º turno de 2022"],
                         horizontal=True)
        t = 1 if turno.startswith("1") else 2

        g22 = pct_validos(votos_por_campo(v22[v22["NR_TURNO"] == t], grupo_secao))
        g26 = pct_validos(votos_por_campo(votos[votos["CD_CARGO"] == 1], grupo_secao))
        cid = pd.Series("Itapira", index=secoes["NR_SECAO"])
        c22 = votos_por_campo(v22[v22["NR_TURNO"] == t], cid).iloc[0]
        c26 = votos_por_campo(votos[votos["CD_CARGO"] == 1], cid).iloc[0]
        k22, k26 = pct_validos(c22), pct_validos(c26)
        aptos22 = secoes_22["QT_ELEITOR_SECAO"].sum()
        comp22 = c22.sum() / secoes_22.set_index("NR_SECAO")["QT_ELEITOR_SECAO"] \
            .reindex(secoes["NR_SECAO"]).sum() * 100
        comp26 = c26.sum() / aptos * 100

        kpis([
            ("Bolsonaro (22)", f"{pc(k22['Bolsonaro (22)'])} → {pc(k26['Bolsonaro (22)'])}",
             f"{pp(k26['Bolsonaro (22)'] - k22['Bolsonaro (22)'])} · Jair em 2022, Flávio em 2026"),
            ("Lula (13)", f"{pc(k22['Lula (13)'])} → {pc(k26['Lula (13)'])}",
             pp(k26["Lula (13)"] - k22["Lula (13)"])),
            ("Comparecimento", f"{pc(comp22)} → {pc(comp26)}", pp(comp26 - comp22)),
            ("Eleitores aptos", f"{num(aptos22)} → {num(aptos)}", f"{num(aptos - aptos22)} eleitores"),
        ])

        delta = (g26 - g22).dropna()
        tabela = pd.DataFrame({
            "22 em 2022": g22["Bolsonaro (22)"], "22 em 2026": g26["Bolsonaro (22)"],
            "Variação 22": delta["Bolsonaro (22)"],
            "13 em 2022": g22["Lula (13)"], "13 em 2026": g26["Lula (13)"],
            "Variação 13": delta["Lula (13)"],
        }).dropna().sort_values("Variação 22", ascending=False)

        d22, d13 = tabela["Variação 22"], tabela["Variação 13"]
        fatos = [
            f"Presidente, {turno} × 1º turno de 2026. Número 22: Jair Bolsonaro em 2022 e Flávio "
            f"Bolsonaro em 2026; número 13: Lula nos dois anos.",
            f"Na cidade, o 22 foi de {pc(k22['Bolsonaro (22)'])} para {pc(k26['Bolsonaro (22)'])} "
            f"({pp(k26['Bolsonaro (22)'] - k22['Bolsonaro (22)'])}); o 13 foi de {pc(k22['Lula (13)'])} "
            f"para {pc(k26['Lula (13)'])} ({pp(k26['Lula (13)'] - k22['Lula (13)'])}).",
            f"O 22 cresceu em {(d22 > 0).sum()} de {len(d22)} {g_plur}; o 13 cresceu em "
            f"{(d13 > 0).sum()} de {len(d13)}.",
            "Maior crescimento do 22: " + "; ".join(f"{i} ({pp(x)})" for i, x in d22.head(3).items()) + ".",
            "Menor variação do 22: " + "; ".join(f"{i} ({pp(x)})" for i, x in d22.tail(3).items()) + ".",
            "Maior queda do 13: " + "; ".join(f"{i} ({pp(x)})" for i, x in d13.sort_values().head(3).items()) + ".",
            f"Comparecimento: {pc(comp22)} em 2022 e {pc(comp26)} em 2026; o número de eleitores "
            f"aptos caiu de {num(aptos22)} para {num(aptos)}.",
            "As seções foram comparadas pelo número (mesmos eleitores, em grande parte); a seção 161 "
            "é nova e não entra na comparação.",
        ]
        bloco_insight(f"2022_{col_grupo}_{t}", f"Presidente: {turno} × 2026 por {g_sing}", fatos,
                      tabela if len(tabela) <= 30 else None)

        st.subheader(f"Quanto cada um ganhou ou perdeu por {g_sing}")
        campo = st.radio("Ver", list(CAMPOS), horizontal=True, key="campo_2022")
        dd = pd.DataFrame({"a": g22[campo], "b": g26[campo]}).dropna()
        dd["d"] = dd["b"] - dd["a"]
        dd = dd.sort_values("d")
        rot = [f"{pp(r.d)}  ({r.a:.0f}% → {r.b:.0f}%)" for r in dd.itertuples()]
        barras_h(dd["d"], CAMPOS[campo], rot,
                 "<b>%{y}</b><br>2022: %{customdata[0]:.1f}%<br>2026: %{customdata[1]:.1f}%"
                 "<extra></extra>",
                 f"variação de {campo} em pontos percentuais", 0, "", custom=dd[["a", "b"]].values)
        st.caption("Barra para a direita = o candidato teve uma fatia maior dos votos válidos em 2026 "
                   "do que em 2022 naquele lugar; para a esquerda = menor. Entre parênteses, o "
                   "percentual de 2022 → 2026.")

        st.subheader("Tabela lado a lado")
        st.dataframe(tabela.rename_axis(nome_grupo).style.format(
            {c: ("{:+.1f}" if c.startswith("Variação") else "{:.1f}%") for c in tabela.columns}),
            width="stretch")
        st.caption("Percentuais sobre votos válidos. As 9 seções que votavam no IESI em 2022 foram "
                   "transferidas para a ETEC e aparecem no grupo de 2026.")

# ---------------------------------------------------------------- aba 7: dados
with aba7:
    st.write(f"Votos válidos de **{cargo}** por {g_sing} × candidato")
    st.dataframe(pivot.rename_axis(nome_grupo), width="stretch")
    st.download_button("Baixar CSV", pivot.to_csv(sep=";", encoding="utf-8-sig").encode("utf-8-sig"),
                       file_name=f"itapira_2026_{cargo.lower().replace(' ', '_')}_{col_grupo.lower()}.csv")
    st.write("Seções → locais → bairros")
    st.dataframe(secoes, width="stretch", hide_index=True)

st.markdown('<div class="in-rodape"><b>Fonte:</b> TSE – Dados Abertos (votação por seção, locais de '
            'votação e perfil do eleitorado) · Eleições 2022 e 2026 · Zona Eleitoral 0054'
            + (' · Análises em texto geradas por IA (Claude)' if API_KEY else '') + '</div>',
            unsafe_allow_html=True)

# ---------------------------------------------------------------- análises da IA
# as chamadas rodam em paralelo desde que cada bloco foi criado; aqui só esperamos e preenchemos
for ph, chave, fut, fatos in PENDENTES:
    try:
        texto = fut.result(timeout=180)
    except Exception:  # timeout ou erro inesperado: fica com os fatos calculados
        texto = None
    _render_insight(ph, chave, texto, fatos, False, final=True)
