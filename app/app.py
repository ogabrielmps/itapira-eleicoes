"""
Análise da votação de Itapira (Zona 54) - Eleições 2026, 1º turno.

Cada capítulo responde a uma pergunta: resposta curta, argumentos com números e, por fim,
a evidência (tabelas e poucos gráficos). As comparações usam as cidades vizinhas, o estado
de SP, o Brasil e a eleição de 2022.

Rodar:  streamlit run app/app.py
Dados:  etl/preparar_dados.py, etl/preparar_2022.py e etl/preparar_contexto.py
IA:     ANTHROPIC_API_KEY nos Secrets do Streamlit (opcional) para a leitura em texto de cada capítulo
"""
import hmac
import os

import folium
import numpy as np
import pandas as pd
import plotly.graph_objects as go
import streamlit as st
from plotly.subplots import make_subplots
from streamlit_folium import st_folium

import analise as A
import insights
import ui
from analise import (CARGOS, DEP_ESTADUAL, DEP_FEDERAL, GOVERNADOR, ITAPIRA,
                     PRESIDENTE, SENADOR, curto)
from ui import AZUL, CINZA_CLARO, MARINHO, OUTROS, SERIES

st.set_page_config(page_title="Itapira 2026 · análise da votação", page_icon="🗳️", layout="wide",
                   initial_sidebar_state="collapsed")
ui.estilo()


# ======================================================================= formatação
def pc(x, casas=1):
    return f"{x:.{casas}f}%".replace(".", ",")


def pts(x, sinal=True):
    """Diferença em pontos percentuais: '+5,1 pontos'."""
    s = f"{x:+.1f}" if sinal else f"{abs(x):.1f}"
    return s.replace(".", ",") + (" ponto" if abs(round(x, 1)) == 1 else " pontos")


def num(n):
    return f"{int(round(n)):,}".replace(",", ".")


def dec(x, casas=2):
    return f"{x:.{casas}f}".replace(".", ",")


def pvar(x):
    """Variação percentual: '-7,1%'."""
    return f"{x:+.1f}%".replace(".", ",")


def sem_negrito(t: str) -> str:
    return t.replace("**", "")


# ======================================================================= acesso e IA
def segredo(nome: str):
    try:
        return st.secrets.get(nome)
    except FileNotFoundError:  # rodando local sem secrets.toml
        return None


SENHA = segredo("senha")
API_KEY = segredo("ANTHROPIC_API_KEY") or os.environ.get("ANTHROPIC_API_KEY")

if SENHA and not st.session_state.get("autenticado"):
    ui.hero("Acesso restrito", "Análise da votação", "Digite a senha para entrar")
    with st.form("login"):
        digitada = st.text_input("Senha", type="password")
        if st.form_submit_button("Entrar"):
            if hmac.compare_digest(digitada, str(SENHA)):
                st.session_state["autenticado"] = True
                st.rerun()
            st.error("Senha incorreta.")
    st.stop()

PENDENTES = []  # (placeholder, chave, future) preenchidos no fim da página


def _render_ia(ph, chave: str, texto: str | None, final: bool = False):
    # a chave muda no preenchimento final: o Streamlit não aceita a mesma chave duas vezes por execução
    with ph.container(key=f"insight_{chave}{'_f' if final else ''}"):
        st.markdown('<div class="in-insight-titulo">💡 Leitura por IA</div>', unsafe_allow_html=True)
        if texto:
            st.markdown(texto)
            st.caption("Texto escrito pelo Claude (IA) a partir dos números deste capítulo.")
        else:
            st.caption("⏳ Escrevendo a leitura…" if not final else
                       "A leitura por IA não está disponível agora.")


def leitura_ia(chave: str, titulo: str, fatos: list[str]):
    """Leitura em texto do capítulo pelo Claude (só aparece com chave de API)."""
    if not API_KEY:
        return
    fut = insights.pedir(API_KEY, titulo, [sem_negrito(f) for f in fatos])
    ph = st.empty()
    if fut.done():
        _render_ia(ph, chave, fut.result())
    else:
        _render_ia(ph, chave, None)
        PENDENTES.append((ph, chave, fut))


# ======================================================================= dados
@st.cache_data
def dados_itapira():
    return A.carregar_itapira()


@st.cache_data
def dados_perfil():
    return A.carregar_perfil()


@st.cache_data
def dados_contexto():
    return A.carregar_contexto()


@st.cache_data
def referencias(cargo, ano=2026, turno=1):
    return A.referencias(ctx, cargo, ano, turno)


@st.cache_data
def municipios_sp(cargo, ano=2026, turno=1):
    return A.pct_municipios_sp(ctx, cargo, ano, turno)


@st.cache_data
def posicao(cargo, nr):
    return A.posicao_sp(ctx, cargo, nr)


@st.cache_data
def deputados(cargo):
    return A.deputados(ctx, cargo, votos)


# como cada característica entra numa frase ("___ é o que mais separa as seções")
NOME_FRASE = {"Idade média": "a idade média", "% com 60 anos ou mais": "a proporção de idosos",
              "% de 16 a 29 anos": "a proporção de jovens",
              "% com ensino superior": "a proporção com ensino superior",
              "% até o fundamental": "a proporção que só tem até o fundamental",
              "% de mulheres": "a proporção de mulheres", "% de casados": "a proporção de casados"}
PEQUENO = 1000  # bairros/locais com menos eleitores que isso oscilam mais por acaso


votos, secoes, v22, s22 = dados_itapira()
perfil_secao = dados_perfil()
ctx = dados_contexto()
if ctx is None:
    st.error("Dados de comparação não encontrados. Rode `python etl/preparar_contexto.py`.")
    st.stop()

BAIRRO = secoes.set_index("NR_SECAO")["BAIRRO"]
LOCAL = secoes.set_index("NR_SECAO")["NM_LOCAL_VOTACAO"]
APTOS_SECAO = secoes.set_index("NR_SECAO")["QT_ELEITOR_SECAO"]
GRUPOS = {"Bairro": (BAIRRO, "bairro", "bairros"),
          "Local de votação": (LOCAL, "local de votação", "locais de votação")}


def nome_cand(cargo: int, nr: int) -> str:
    return ctx["cand"].get((cargo, nr), str(nr))


def votos_cargo(cargo: int) -> pd.DataFrame:
    return votos[votos["CD_CARGO"] == cargo]


def ranking_itapira(cargo: int) -> pd.Series:
    """Votos por candidato em Itapira, do mais ao menos votado (deputados: só nominais)."""
    v = A.validos(votos_cargo(cargo))
    if cargo in (DEP_FEDERAL, DEP_ESTADUAL):
        v = v[v["NR_VOTAVEL"] >= 100]
    return v.groupby("NR_VOTAVEL")["QT_VOTOS"].sum().sort_values(ascending=False)


def votantes_secao() -> pd.Series:
    """Quem votou, por seção (total de votos para Governador: 1 voto por eleitor)."""
    return votos_cargo(GOVERNADOR).groupby("NR_SECAO")["QT_VOTOS"].sum()


def seletor_candidato(cargo: int, chave: str, padrao: int = 0) -> int:
    r = ranking_itapira(cargo)
    tot = A.validos(votos_cargo(cargo))["QT_VOTOS"].sum()
    opcoes = list(r.index[:40])
    return st.selectbox("Candidato", opcoes, index=min(padrao, len(opcoes) - 1), key=chave,
                        format_func=lambda n: f"{nome_cand(cargo, n)} · {pc(r[n] / tot * 100)} em Itapira")


def tabela_progress(df: pd.DataFrame, pct_cols: dict, outros: dict | None = None, altura=None,
                    indice: str | None = None):
    """st.dataframe com barras de progresso nas colunas de percentual."""
    cfg = {c: st.column_config.ProgressColumn(c, format="%.1f%%", min_value=0, max_value=m)
           for c, m in pct_cols.items()}
    cfg.update(outros or {})
    if indice:
        df = df.rename_axis(indice).reset_index()
    extra = {"height": altura} if altura else {}
    st.dataframe(df, column_config=cfg, hide_index=True, width="stretch", **extra)


COL_PP = lambda nome: st.column_config.NumberColumn(nome, format="%+.1f")  # noqa: E731
COL_NUM = lambda nome: st.column_config.NumberColumn(nome, format="localized")  # noqa: E731

# ======================================================================= cabeçalho
ui.hero("O que os dados dizem", "Análise da votação", "Itapira comparada à região, ao estado e a 2022")
total_pres = votos_cargo(PRESIDENTE)["QT_VOTOS"].sum()
aptos = int(APTOS_SECAO.sum())
ui.kpis([
    ("Eleitores aptos", num(aptos), "161 seções · 22 locais de votação"),
    ("Votaram", num(votantes_secao().sum()), pc(votantes_secao().sum() / aptos * 100) + " de comparecimento"),
    ("Cidades vizinhas usadas na comparação", str(len(ctx["vizinhas"])), "Mogi Mirim, Mogi Guaçu, Amparo…"),
    ("Municípios de SP no ranking", "645", "fonte: TSE, dados por seção"),
])

abas = st.tabs(["📌 Resumo", "🗺️ Onde cada um é forte", "🔁 2022 → 2026", "🔀 Voto entre cargos",
                "👥 Perfil e voto", "🏛️ Deputados", "🚶 Comparecimento", "📘 Metodologia"])


# ======================================================================= 1. resumo
def cap_resumo():
    ref = {c: referencias(c) for c in (PRESIDENTE, GOVERNADOR, SENADOR)}
    p1, p2 = ref[PRESIDENTE].loc["Itapira"].sort_values(ascending=False).index[:2]
    g1 = ref[GOVERNADOR].loc["Itapira"].sort_values(ascending=False).index[0]
    s1, s2 = ref[SENADOR].loc["Itapira"].sort_values(ascending=False).index[:2]
    rp, rg = ref[PRESIDENTE], ref[GOVERNADOR]
    np1 = curto(nome_cand(PRESIDENTE, p1))
    dif_sp = rp.loc["Itapira", p1] - rp.loc["Estado de SP", p1]
    dif_viz = rp.loc["Itapira", p1] - rp.loc["Cidades vizinhas", p1]
    pos, tot, acima = posicao(PRESIDENTE, p1)
    pos_g, _, _ = posicao(GOVERNADOR, g1)
    r22 = referencias(PRESIDENTE, 2022, 1)
    sw_it = rp.loc["Itapira", p1] - r22.loc["Itapira"].get(p1, np.nan)
    sw_sp = rp.loc["Estado de SP", p1] - r22.loc["Estado de SP"].get(p1, np.nan)
    comp = A.comparecimento_ref(ctx)
    d_est = deputados(DEP_ESTADUAL).iloc[0]

    if abs(dif_viz) < 2:
        texto = (f"Itapira votou como as cidades vizinhas, e deu a {np1} {pts(dif_sp, False)} a mais "
                 f"do que o estado de São Paulo.")
    else:
        texto = (f"Itapira deu a {np1} {pts(dif_sp, False)} a mais do que o estado, e "
                 f"{pts(abs(dif_viz), False)} {'a mais' if dif_viz > 0 else 'a menos'} que as cidades vizinhas.")
    seg = [nome_cand(PRESIDENTE, n) for n in rp.columns if ctx["situacao"].get((PRESIDENTE, n)) == "Vai ao 2º turno"]
    eleitos_sen = [nome_cand(SENADOR, n) for n in ref[SENADOR].columns
                   if str(ctx["situacao"].get((SENADOR, n), "")).startswith("Eleito")]
    args = [
        f"**Presidente:** {np1} teve **{pc(rp.loc['Itapira', p1])}** dos votos válidos em Itapira, "
        f"contra {pc(rp.loc['Cidades vizinhas', p1])} nas vizinhas, {pc(rp.loc['Estado de SP', p1])} no estado "
        f"e {pc(rp.loc['Brasil', p1])} no Brasil. {curto(nome_cand(PRESIDENTE, p2))} teve "
        f"{pc(rp.loc['Itapira', p2])} (estado: {pc(rp.loc['Estado de SP', p2])}).",
        f"**No ranking paulista:** Itapira foi o **{pos}º** de {tot} municípios em votos para {np1}: "
        f"ficou acima de {acima:.0f}% das cidades do estado.",
        (f"**No país, a eleição vai ao 2º turno** entre {' e '.join(seg)}, em 25 de outubro." if len(seg) == 2 else ""),
        f"**Governador:** {curto(nome_cand(GOVERNADOR, g1))} teve **{pc(rg.loc['Itapira', g1])}** em Itapira "
        f"(estado: {pc(rg.loc['Estado de SP', g1])}; {str(ctx['situacao'].get((GOVERNADOR, g1), '')).lower()} no 1º turno); "
        f"{pos_g}º lugar entre os municípios paulistas.",
        f"**Senado (2 vagas):** os mais votados em Itapira foram {curto(nome_cand(SENADOR, s1))} "
        f"({pc(ref[SENADOR].loc['Itapira', s1])}) e {curto(nome_cand(SENADOR, s2))} "
        f"({pc(ref[SENADOR].loc['Itapira', s2])})"
        + (f"; no estado, foram eleitos {' e '.join(eleitos_sen)}." if eleitos_sen else "."),
        f"**Desde 2022:** o número 22 cresceu **{pts(sw_it)}** em Itapira, contra {pts(sw_sp)} no estado "
        f"(Jair Bolsonaro em 2022, Flávio Bolsonaro em 2026).",
        f"**Comparecimento:** {pc(comp.loc['Itapira', 2026])}, acima do estado ({pc(comp.loc['Estado de SP', 2026])}), "
        f"mas o eleitorado apto de Itapira encolheu "
        f"{pc((1 - comp.loc['Itapira', 'aptos_2026'] / comp.loc['Itapira', 'aptos_2022']) * 100)} desde 2022.",
        f"**Voto local:** para deputado estadual, {d_est['Candidato']} teve **{pc(d_est['% dos votos de Itapira'])}** "
        f"dos votos nominais da cidade; {pc(d_est['% do total dele que veio da região'], 0)} de todos os votos dele "
        f"no estado vieram de Itapira e das cidades vizinhas "
        f"({str(ctx['situacao'].get((DEP_ESTADUAL, int(d_est.name)), '')).lower()}).",
    ]
    args = [a for a in args if a]
    ui.resposta("Itapira votou diferente do estado e do país?", texto, args)

    st.subheader("Itapira lado a lado com a região, o estado e o país")
    cargo = st.segmented_control("Cargo", [PRESIDENTE, GOVERNADOR, SENADOR], default=PRESIDENTE,
                                 format_func=CARGOS.get, key="res_cargo") or PRESIDENTE
    r = ref[cargo]
    top = list(r.loc["Itapira"].sort_values(ascending=False).index[:4])
    tab = r[top].T
    tab.loc["Demais candidatos"] = 100 - tab.sum()
    tab.index = [nome_cand(cargo, n) if isinstance(n, (int, np.integer)) else n for n in tab.index]
    tab["Itapira − estado (pontos)"] = tab["Itapira"] - tab["Estado de SP"]
    teto = float(tab[r.index].max().max()) * 1.05
    tabela_progress(tab, {c: teto for c in r.index},
                    {"Itapira − estado (pontos)": COL_PP("Itapira − estado (pontos)")}, indice="Candidato")
    ui.nota("Percentuais sobre os votos válidos (sem brancos e nulos). "
            + ("Para Senador cada eleitor votou em 2 candidatos. " if cargo == SENADOR else "")
            + "Cidades vizinhas: soma dos votos de 16 municípios da região (lista em Metodologia).")

    st.subheader("Onde Itapira fica entre os 645 municípios paulistas")
    c_alvo = r.loc["Itapira"].sort_values(ascending=False).index[0]
    dist = municipios_sp(cargo)[c_alvo]
    fig = go.Figure(go.Histogram(x=dist, nbinsx=40, marker=dict(color=CINZA_CLARO, line=dict(width=1, color="#fff")),
                                 hovertemplate="%{x}: %{y} municípios<extra></extra>"))
    for x, rot, corl in [(dist[ITAPIRA], f"Itapira {pc(dist[ITAPIRA])}", MARINHO),
                         (r.loc["Estado de SP", c_alvo], f"Estado {pc(r.loc['Estado de SP', c_alvo])}", OUTROS)]:
        fig.add_vline(x=x, line_color=corl, line_width=3 if corl == MARINHO else 2,
                      line_dash="solid" if corl == MARINHO else "dot",
                      annotation_text=rot, annotation_position="top")
    fig.update_layout(height=320, margin=dict(l=10, r=10, t=40, b=10), bargap=0.05, showlegend=False,
                      xaxis_title=f"% dos votos válidos de {curto(nome_cand(cargo, c_alvo))} em cada município",
                      yaxis_title="nº de municípios")
    ui.mostrar(fig)
    pos_c, tot_c, acima_c = posicao(cargo, c_alvo)
    ui.nota(f"Cada barra conta quantos municípios paulistas deram a {curto(nome_cand(cargo, c_alvo))} "
            f"aquela faixa de votos. Itapira é o **{pos_c}º** de {tot_c}: acima de {acima_c:.0f}% dos municípios. "
            "A linha pontilhada é o resultado do estado inteiro (puxado pelas cidades grandes).")
    leitura_ia("resumo", "Resumo: Itapira comparada à região, ao estado e ao Brasil", args)


# ======================================================================= 2. geografia
def cap_geografia():
    c1, c2, c3 = st.columns([1, 1.6, 1])
    cargo = c1.selectbox("Cargo", list(CARGOS), format_func=CARGOS.get, key="geo_cargo")
    with c2:
        nr = seletor_candidato(cargo, f"geo_cand_{cargo}")
    agrup = c3.radio("Agrupar por", list(GRUPOS), key="geo_grupo", horizontal=True)
    grupo, sing, plur = GRUPOS[agrup]

    v = A.validos(votos_cargo(cargo))
    pct = A.pct_por(v.assign(G=v["NR_SECAO"].map(grupo)), "G")
    votos_g = v[v["NR_VOTAVEL"] == nr].assign(G=lambda d: d["NR_SECAO"].map(grupo)).groupby("G")["QT_VOTOS"].sum()
    cid_tot = v["QT_VOTOS"].sum()
    cid = v[v["NR_VOTAVEL"] == nr]["QT_VOTOS"].sum() / cid_tot * 100
    s = pct[nr].sort_values(ascending=False)
    nm = nome_cand(cargo, nr)
    amp = s.iloc[0] - s.iloc[-1]
    eleitores = APTOS_SECAO.groupby(grupo).sum().reindex(s.index)
    grandes = s[eleitores >= PEQUENO]
    amp_g = grandes.iloc[0] - grandes.iloc[-1] if len(grandes) > 1 else amp
    pequenos_ext = [g for g in (s.index[0], s.index[-1]) if eleitores[g] < PEQUENO]
    acima, abaixo = (s >= cid + 3).sum(), (s <= cid - 3).sum()
    vencidos = (pct.idxmax(axis=1) == nr).sum()
    rk = ranking_itapira(cargo)
    posicao = list(rk.index).index(nr) + 1 if nr in rk.index else None
    top3 = s.index[:3]
    peso_top3_cand = votos_g.reindex(top3).sum() / votos_g.sum() * 100
    peso_top3_cid = v[v["NR_SECAO"].map(grupo).isin(top3)]["QT_VOTOS"].sum() / cid_tot * 100

    if amp_g < 10:
        leitura = "um voto distribuído de forma parecida pela cidade"
    elif amp_g < 20:
        leitura = f"diferenças claras entre os {plur}, mas sem redutos isolados"
    else:
        leitura = "um voto bem concentrado em algumas partes da cidade"
    args = [
        f"Na cidade: **{pc(cid)}** dos votos válidos ({num(votos_g.sum())} votos)"
        + (f", {posicao}º mais votado." if posicao else "."),
        f"Foi o mais votado em **{vencidos} de {len(s)}** {plur}." if vencidos
        else f"Não foi o mais votado em nenhum {sing}.",
        f"Ficou **3 pontos ou mais acima** da própria média em {acima} {plur} e **3 ou mais abaixo** em {abaixo}; "
        f"nos outros {len(s) - acima - abaixo}, ficou perto da média.",
        (f"**Cuidado com lugares pequenos:** {' e '.join(f'{g} ({num(eleitores[g])} eleitores)' for g in pequenos_ext)} "
         f"{'têm' if len(pequenos_ext) > 1 else 'tem'} poucos eleitores, e resultados de lugares pequenos oscilam mais por "
         f"acaso. Considerando só os {plur} com mais de {num(PEQUENO)} eleitores, o melhor é {grandes.index[0]} "
         f"({pc(grandes.iloc[0])}) e o pior é {grandes.index[-1]} ({pc(grandes.iloc[-1])}): {pts(amp_g, False)} de "
         f"diferença, o que indica {leitura}.") if pequenos_ext else
        f"A distância entre o melhor e o pior {sing} é de {pts(amp, False)}: {leitura}.",
        f"Os 3 {plur} onde foi mais forte ({', '.join(top3)}) deram {pc(peso_top3_cand)} dos votos dele, "
        f"embora tenham {pc(peso_top3_cid)} dos votos da cidade.",
    ]
    ui.resposta(f"Onde {curto(nm)} foi mais forte e mais fraco?",
                f"Mais forte em {s.index[0]} ({pc(s.iloc[0])}) e mais fraco em {s.index[-1]} "
                f"({pc(s.iloc[-1])}): {pts(amp, False)} de diferença.", args)

    col_mapa, col_tab = st.columns([1.1, 1])
    with col_mapa:
        st.subheader("Mapa")
        por_local = v.assign(L=v["NR_LOCAL_VOTACAO"]).pivot_table(
            index="L", columns="NR_VOTAVEL", values="QT_VOTOS", aggfunc="sum", fill_value=0)
        pl = por_local[nr] / por_local.sum(axis=1) * 100
        locais = secoes.groupby("NR_LOCAL_VOTACAO").first()
        m = folium.Map(tiles="OpenStreetMap")
        pts_ok = locais.dropna(subset=["NR_LATITUDE"])
        m.fit_bounds([[pts_ok["NR_LATITUDE"].min(), pts_ok["NR_LONGITUDE"].min()],
                      [pts_ok["NR_LATITUDE"].max(), pts_ok["NR_LONGITUDE"].max()]])
        tot_l = por_local.sum(axis=1)
        for loc, val in pl.items():
            info = locais.loc[loc]
            if pd.isna(info["NR_LATITUDE"]):
                continue
            folium.CircleMarker(
                [info["NR_LATITUDE"], info["NR_LONGITUDE"]], radius=7 + 16 * (tot_l[loc] / tot_l.max()) ** .5,
                color="#ffffff", weight=2, fill=True, fill_color=ui.cor_seq(val, pl.min(), pl.max()),
                fill_opacity=.9,
                tooltip=f"<b>{info['NM_LOCAL_VOTACAO']}</b><br>{info['BAIRRO']}<br>{curto(nm)}: {pc(val)} "
                        f"({num(por_local.loc[loc, nr])} votos)",
            ).add_to(m)
        st_folium(m, height=440, use_container_width=True, returned_objects=[])
        ui.nota(f"Cada círculo é um local de votação. Quanto **mais escuro**, maior o % de {curto(nm)} ali "
                f"(de {pc(pl.min())} no mais claro a {pc(pl.max())} no mais escuro). Tamanho = nº de votos.")
    with col_tab:
        st.subheader(f"Ranking por {sing}")
        tab = pd.DataFrame({"%": s, "Diferença da média (pontos)": s - cid,
                            "Votos": votos_g.reindex(s.index).fillna(0), "Eleitores": eleitores.reindex(s.index)})
        tabela_progress(tab, {"%": float(s.max()) * 1.05},
                        {"Diferença da média (pontos)": COL_PP("Diferença da média (pontos)"),
                         "Votos": COL_NUM("Votos"), "Eleitores": COL_NUM("Eleitores")},
                        altura=440, indice=agrup)

    with st.expander(f"Quem foi o mais votado em cada {sing}"):
        venc = pd.DataFrame({
            "1º lugar": pct.idxmax(axis=1).map(lambda n: nome_cand(cargo, n)),
            "% do 1º": pct.max(axis=1),
            "2º lugar": pct.apply(lambda r: nome_cand(cargo, r.nlargest(2).index[-1]), axis=1),
            "% do 2º": pct.apply(lambda r: r.nlargest(2).iloc[-1], axis=1),
        })
        venc["Vantagem (pontos)"] = venc["% do 1º"] - venc["% do 2º"]
        tabela_progress(venc.sort_values("Vantagem (pontos)"), {"% do 1º": 100, "% do 2º": 100},
                        {"Vantagem (pontos)": st.column_config.NumberColumn(format="%.1f")}, indice=agrup)
    ui.nota(f"O {sing} é o do **local de votação**, não o endereço de quem votou.")
    leitura_ia(f"geo_{cargo}_{nr}_{agrup}", f"{CARGOS[cargo]}: onde {nm} foi mais forte em Itapira", args)


# ======================================================================= 3. 2022 -> 2026
def cap_mudanca():
    turno = st.radio("Comparar 2026 com", [1, 2], horizontal=True, key="mud_turno",
                     format_func=lambda t: f"{t}º turno de 2022" + (" (recomendado)" if t == 1 else ""))
    r22, r26 = referencias(PRESIDENTE, 2022, turno), referencias(PRESIDENTE)
    refs = list(r26.index)
    tab = pd.DataFrame({
        "22 em 2022": r22[22], "22 em 2026": r26[22], "Variação do 22": r26[22] - r22[22],
        "13 em 2022": r22[13], "13 em 2026": r26[13], "Variação do 13": r26[13] - r22[13],
    }).loc[refs]
    sw = tab["Variação do 22"]

    # cidades da região: variação do 22
    m22, m26 = municipios_sp(PRESIDENTE, 2022, turno), municipios_sp(PRESIDENTE)
    cidades = ctx["vizinhas"] + [ITAPIRA]
    var_cid = (m26.loc[cidades, 22] - m22.loc[cidades, 22]).sort_values(ascending=False)
    pos_reg = list(var_cid.index).index(ITAPIRA) + 1

    # seção a seção dentro de Itapira
    a = A.pct_por(A.validos(v22[v22["NR_TURNO"] == turno]).assign(CD_CARGO=PRESIDENTE), "NR_SECAO")[22]
    b = A.pct_por(A.validos(votos_cargo(PRESIDENTE)), "NR_SECAO")[22]
    sec = pd.DataFrame({"a": a, "b": b}).dropna()
    sec["d"] = sec["b"] - sec["a"]
    r_estab = sec["a"].corr(sec["b"])
    q1, q3 = sec["d"].quantile([.25, .75])

    def comparar(x, y):
        return "mais do que" if x > y + 0.5 else "menos do que" if x < y - 0.5 else "no mesmo ritmo que"

    texto = (f"O 22 cresceu {pts(sw['Itapira'], False)} em Itapira: {comparar(sw['Itapira'], sw['Estado de SP'])} "
             f"no estado ({pts(sw['Estado de SP'])}) e {comparar(sw['Itapira'], sw['Cidades vizinhas'])} "
             f"nas cidades vizinhas ({pts(sw['Cidades vizinhas'])}).")
    args = [
        f"**Número 22** (Jair Bolsonaro em 2022, Flávio Bolsonaro em 2026): em Itapira foi de "
        f"{pc(tab.loc['Itapira', '22 em 2022'])} para **{pc(tab.loc['Itapira', '22 em 2026'])}**; "
        f"no Brasil, {pts(sw['Brasil'])}.",
        f"**Número 13** (Lula): em Itapira foi de {pc(tab.loc['Itapira', '13 em 2022'])} para "
        f"**{pc(tab.loc['Itapira', '13 em 2026'])}** ({pts(tab.loc['Itapira', 'Variação do 13'])}); no estado, "
        f"{pts(tab.loc['Estado de SP', 'Variação do 13'])}.",
        f"Entre Itapira e as 16 cidades vizinhas, Itapira teve a **{pos_reg}ª maior** variação do 22 "
        f"(maior: {ctx['mun'].loc[var_cid.index[0], 'NM_MUNICIPIO'].title()}, {pts(var_cid.iloc[0])}; menor: "
        f"{ctx['mun'].loc[var_cid.index[-1], 'NM_MUNICIPIO'].title()}, {pts(var_cid.iloc[-1])}).",
        f"**Os redutos não mudaram:** as seções onde o 22 era forte em 2022 continuaram sendo as mais fortes "
        f"(correlação de {dec(r_estab)} entre 2022 e 2026)." if r_estab >= .7 else
        f"**O mapa mudou:** a correlação entre as seções de 2022 e 2026 é só {dec(r_estab)}.",
        f"**A mudança foi geral:** o 22 cresceu em {(sec['d'] > 0).sum()} de {len(sec)} seções, e metade delas "
        f"variou entre {pts(q1)} e {pts(q3)}." if (sec['d'] > 0).mean() > .7 else
        f"O 22 cresceu em {(sec['d'] > 0).sum()} de {len(sec)} seções; metade variou entre {pts(q1)} e {pts(q3)}.",
    ]
    if turno == 2:
        args.append("Atenção: o 2º turno de 2022 tinha só dois candidatos, então os percentuais tendem a ser "
                    "maiores do que num 1º turno; a comparação justa é com o 1º turno.")
    ui.resposta("Itapira acompanhou o movimento do estado desde 2022?", texto, args)

    st.subheader("Itapira, região, estado e país")
    teto = float(tab[["22 em 2022", "22 em 2026", "13 em 2022", "13 em 2026"]].max().max()) * 1.05
    tabela_progress(tab, {c: teto for c in ["22 em 2022", "22 em 2026", "13 em 2022", "13 em 2026"]},
                    {"Variação do 22": COL_PP("Variação do 22"), "Variação do 13": COL_PP("Variação do 13")},
                    indice="Onde")

    st.subheader("Variação do 22 nas cidades da região")
    nomes = [ctx["mun"].loc[c, "NM_MUNICIPIO"].title() for c in var_cid.index]
    ui.barras_h(var_cid.values[::-1], nomes[::-1],
                [MARINHO if c == ITAPIRA else CINZA_CLARO for c in var_cid.index[::-1]],
                [pts(x).replace(" pontos", "").replace(" ponto", "") for x in var_cid.values[::-1]],
                "<b>%{y}</b><br>%{x:+.1f} pontos<extra></extra>",
                "variação do 22 entre 2022 e 2026 (pontos percentuais)",
                sw["Estado de SP"], f"estado {pts(sw['Estado de SP'])}")
    ui.nota("Itapira em azul-marinho. A linha pontilhada é a variação no estado inteiro.")

    st.subheader("Dentro de Itapira, por bairro")
    vb = A.validos(v22[v22["NR_TURNO"] == turno]).assign(G=lambda d: d["NR_SECAO"].map(BAIRRO))
    vb26 = A.validos(votos_cargo(PRESIDENTE)).assign(G=lambda d: d["NR_SECAO"].map(BAIRRO))
    vb = vb[vb["NR_SECAO"].isin(sec.index)]
    vb26 = vb26[vb26["NR_SECAO"].isin(sec.index)]
    p_a, p_b = A.pct_por(vb, "G"), A.pct_por(vb26, "G")
    tb = pd.DataFrame({"22 em 2022": p_a[22], "22 em 2026": p_b[22], "Variação do 22": p_b[22] - p_a[22],
                       "13 em 2022": p_a[13], "13 em 2026": p_b[13], "Variação do 13": p_b[13] - p_a[13]}
                      ).sort_values("Variação do 22", ascending=False)
    tabela_progress(tb, {c: 100 for c in ["22 em 2022", "22 em 2026", "13 em 2022", "13 em 2026"]},
                    {"Variação do 22": COL_PP("Variação do 22"), "Variação do 13": COL_PP("Variação do 13")},
                    indice="Bairro")

    with st.expander("Ver seção a seção (gráfico de dispersão)"):
        fig = go.Figure()
        lo, hi = min(sec["a"].min(), sec["b"].min()) - 2, max(sec["a"].max(), sec["b"].max()) + 2
        fig.add_trace(go.Scatter(x=[lo, hi], y=[lo, hi], mode="lines", line=dict(color=OUTROS, dash="dot"),
                                 hoverinfo="skip", showlegend=False))
        fig.add_trace(go.Scatter(
            x=sec["a"], y=sec["b"], mode="markers", showlegend=False,
            marker=dict(size=9, color=SERIES[0], opacity=.8, line=dict(width=1.5, color="#fff")),
            customdata=np.c_[sec.index, BAIRRO.reindex(sec.index)],
            hovertemplate="<b>Seção %{customdata[0]}</b> · %{customdata[1]}<br>2022: %{x:.1f}%<br>"
                          "2026: %{y:.1f}%<extra></extra>"))
        fig.add_annotation(x=lo + (hi - lo) * .2, y=hi - (hi - lo) * .08, showarrow=False,
                           text="acima da linha: o 22 cresceu", font=dict(color=MARINHO))
        fig.update_layout(height=430, margin=dict(l=10, r=10, t=10, b=10),
                          xaxis_title=f"% do 22 em 2022 ({turno}º turno)", yaxis_title="% do 22 em 2026")
        fig.update_xaxes(range=[lo, hi])
        fig.update_yaxes(range=[lo, hi])
        ui.mostrar(fig)
        ui.nota("Cada ponto é uma seção eleitoral (os mesmos eleitores, em grande parte, nos dois anos). "
                "Pontos acima da linha pontilhada: o 22 teve uma fatia maior em 2026. Pontos alinhados numa faixa "
                "estreita indicam que a cidade se moveu junta.")
    ui.nota("As seções são comparadas pelo número. As 9 seções que votavam no IESI em 2022 foram transferidas "
            "para a ETEC; a seção 161 é nova e fica de fora desta comparação.")
    leitura_ia(f"mud_{turno}", f"Presidente: o que mudou em Itapira entre 2022 ({turno}º turno) e 2026", args)


# ======================================================================= 4. voto entre cargos
def cap_cargos():
    rp, rg, rs = ranking_itapira(PRESIDENTE), ranking_itapira(GOVERNADOR), ranking_itapira(SENADOR)
    pares = {
        f"{curto(nome_cand(PRESIDENTE, rp.index[0]))} × {curto(nome_cand(GOVERNADOR, rg.index[0]))}":
            ((PRESIDENTE, rp.index[0]), (GOVERNADOR, rg.index[0])),
        f"{curto(nome_cand(PRESIDENTE, rp.index[1]))} × {curto(nome_cand(GOVERNADOR, rg.index[1]))}":
            ((PRESIDENTE, rp.index[1]), (GOVERNADOR, rg.index[1])),
        f"{curto(nome_cand(PRESIDENTE, rp.index[0]))} × {curto(nome_cand(SENADOR, rs.index[0]))} (Senado)":
            ((PRESIDENTE, rp.index[0]), (SENADOR, rs.index[0])),
        f"{curto(nome_cand(PRESIDENTE, rp.index[0]))} × {curto(nome_cand(SENADOR, rs.index[1]))} (Senado)":
            ((PRESIDENTE, rp.index[0]), (SENADOR, rs.index[1])),
        "Escolher outro par": None,
    }
    escolha = st.radio("Comparar", list(pares), horizontal=True, key="car_par")
    if pares[escolha] is None:
        ca, cb = st.columns(2)
        with ca:
            cargo_a = st.selectbox("Cargo A", [PRESIDENTE, GOVERNADOR, SENADOR], format_func=CARGOS.get, key="car_ca")
            nr_a = seletor_candidato(cargo_a, f"car_a_{cargo_a}")
        with cb:
            cargo_b = st.selectbox("Cargo B", [GOVERNADOR, SENADOR, PRESIDENTE], format_func=CARGOS.get, key="car_cb")
            nr_b = seletor_candidato(cargo_b, f"car_b_{cargo_b}")
    else:
        (cargo_a, nr_a), (cargo_b, nr_b) = pares[escolha]
    na, nb = curto(nome_cand(cargo_a, nr_a)), curto(nome_cand(cargo_b, nr_b))

    def por_secao(cargo, nr):
        return votos_cargo(cargo)[votos_cargo(cargo)["NR_VOTAVEL"] == nr].groupby("NR_SECAO")["QT_VOTOS"].sum()

    va, vb = por_secao(cargo_a, nr_a), por_secao(cargo_b, nr_b)
    vot = votantes_secao()
    tot_a, tot_b, tot_v = va.sum(), vb.sum(), vot.sum()
    dif = tot_b - tot_a
    por100 = dif / tot_v * 100
    sec = pd.DataFrame({"a": va, "b": vb, "v": vot}).fillna(0)
    r = (sec["a"] / sec["v"]).corr(sec["b"] / sec["v"])
    g = sec.join(BAIRRO).groupby("BAIRRO").sum()
    g["d100"] = (g["b"] - g["a"]) / g["v"] * 100

    # estado: diferença por 100 eleitores
    v26 = ctx["v26"]
    sp = v26[(v26["CD_MUNICIPIO"].map(ctx["mun"]["SG_UF"]) == "SP") & (v26["NR_TURNO"] == 1)]
    sp_a = sp[(sp["CD_CARGO"] == cargo_a) & (sp["NR_VOTAVEL"] == nr_a)]["QT_VOTOS"].sum()
    sp_b = sp[(sp["CD_CARGO"] == cargo_b) & (sp["NR_VOTAVEL"] == nr_b)]["QT_VOTOS"].sum()
    sp_v = sp[sp["CD_CARGO"] == GOVERNADOR]["QT_VOTOS"].sum()
    sp100 = (sp_b - sp_a) / sp_v * 100

    mais, menos = (nb, na) if dif > 0 else (na, nb)
    texto = (f"{mais} teve {num(abs(dif))} votos a mais que {menos}: pelo menos {num(abs(dif))} eleitores "
             f"votaram em {mais} sem votar em {menos}.")
    args = [
        f"**{na}** ({CARGOS[cargo_a]}): {num(tot_a)} votos · **{nb}** ({CARGOS[cargo_b]}): {num(tot_b)} votos, "
        f"entre {num(tot_v)} eleitores que votaram.",
        "**Por que \"pelo menos\":** o voto é secreto, mas cada eleitor dá no máximo um voto a cada candidato. "
        f"Então, se {mais} teve {num(abs(dif))} votos a mais, no mínimo esse número de pessoas votou nele e não "
        f"em {menos}. O número real pode ser maior, porque trocas nos dois sentidos se compensam.",
        f"**Por 100 eleitores:** em Itapira, {mais} teve {dec(abs(por100), 1)} votos a mais a cada 100 eleitores; "
        f"no estado, a diferença foi de {dec(sp100, 1)} a favor de "
        f"{nb if sp100 > 0 else na}.",
        f"**Mesma base?** A correlação entre os dois, seção a seção, é de {dec(r)}: "
        + ("eles vão bem nos mesmos lugares." if r >= .7 else
           "eles têm bases parcialmente diferentes." if r >= .3 else "eles têm bases bem diferentes."),
        f"**Onde a diferença foi maior:** {g['d100'].idxmax()} ({dec(g['d100'].max(), 1)} por 100 eleitores); "
        f"**menor:** {g['d100'].idxmin()} ({dec(g['d100'].min(), 1)}).",
    ]
    if SENADOR in (cargo_a, cargo_b):
        args.append("Para Senador cada eleitor podia votar em 2 candidatos; o raciocínio do \"pelo menos\" continua "
                    "valendo, porque ninguém vota duas vezes no mesmo candidato.")
    ui.resposta(f"Quem votou em {na} também votou em {nb}?", texto, args)

    st.subheader(f"Diferença {nb} − {na} por bairro")
    g = g.sort_values("d100")
    ui.barras_h(g["d100"].values, g.index, [SERIES[1] if x > 0 else SERIES[0] for x in g["d100"]],
                [("+" if x > 0 else "") + dec(x, 1) for x in g["d100"]],
                "<b>%{y}</b><br>%{x:+.1f} por 100 eleitores<extra></extra>",
                f"votos a mais para {nb} (→) ou para {na} (←), a cada 100 eleitores", por100,
                f"cidade {('+' if por100 > 0 else '')}{dec(por100, 1)}")
    ui.nota(f"<span style='color:{SERIES[1]}'>●</span> {nb} teve mais votos · "
            f"<span style='color:{SERIES[0]}'>●</span> {na} teve mais votos. "
            "A medida é a diferença de votos dividida pelo número de pessoas que votaram no bairro.")
    leitura_ia(f"car_{cargo_a}_{nr_a}_{cargo_b}_{nr_b}", f"Voto entre cargos em Itapira: {na} × {nb}", args)


# ======================================================================= 5. perfil
def cap_perfil():
    c1, c2 = st.columns([1, 1.6])
    cargo = c1.selectbox("Cargo", list(CARGOS), format_func=CARGOS.get, key="per_cargo")
    with c2:
        nr = seletor_candidato(cargo, f"per_cand_{cargo}")
    nm = curto(nome_cand(cargo, nr))
    v = A.validos(votos_cargo(cargo))
    vs = v.pivot_table(index="NR_SECAO", columns="NR_VOTAVEL", values="QT_VOTOS", aggfunc="sum", fill_value=0)
    y = vs[nr] / vs.sum(axis=1) * 100
    ind = A.indicadores(perfil_secao)

    linhas = []
    for nome_i, (_, alto, baixo, _u) in A.INDICADORES.items():
        r, r2 = A.r2_simples(ind[nome_i], y)
        linhas.append({"ind": nome_i, "r": r, "r2": r2 * 100, "onde": alto if r > 0 else baixo})
    exp = pd.DataFrame(linhas).set_index("ind").sort_values("r2", ascending=False)
    multi = A.r2_multiplo(ind[["Idade média", "% com ensino superior", "% de mulheres", "% de casados"]], y) * 100
    melhor = exp.index[0]
    m = exp.iloc[0]

    if m["r2"] < 10:
        texto = (f"Pouco. Nenhuma característica do eleitorado explica mais que 10% das diferenças de voto em "
                 f"{nm} entre as seções; o voto foi parecido em perfis diferentes.")
    else:
        grau = "Em parte" if m["r2"] < 30 else "Bastante"
        texto = (f"{grau}: {NOME_FRASE[melhor]} é o que mais separa as seções. "
                 f"{nm} vai melhor onde há {m['onde']}.")
    top_c = list(vs.sum().sort_values(ascending=False).index[:3])
    if nr not in top_c:
        top_c = [nr] + top_c[:2]
    res, faixas = A.tercos(ind[melhor], vs, top_c)
    un = A.INDICADORES[melhor][3]
    fx = lambda f: f"{f[0]:.0f} a {f[1]:.0f}{un}".replace(".", ",")  # noqa: E731
    args = [
        f"**{NOME_FRASE[melhor].capitalize()}** explica **{pc(m['r2'], 0)}** das diferenças entre seções (correlação {dec(m['r'])}): "
        f"mais votos para {nm} onde há {m['onde']}.",
        f"Na prática: nas seções com {A.INDICADORES[melhor][1]} ({fx(faixas[2])}), {nm} teve "
        f"**{pc(res.loc[2, nr])}**; nas com {A.INDICADORES[melhor][2]} ({fx(faixas[0])}), **{pc(res.loc[0, nr])}**.",
    ] + [
        f"{NOME_FRASE[i].capitalize()} explica {pc(exp.loc[i, 'r2'], 0)} (mais votos onde há {exp.loc[i, 'onde']})."
        for i in exp.index[1:3]
    ] + [
        f"**Juntas**, idade, escolaridade, sexo e estado civil explicam **{pc(multi, 0)}** das diferenças entre "
        f"seções; o resto ({pc(100 - multi, 0)}) depende de fatores que estes dados não mostram.",
        "**Limitação:** o perfil é dos eleitores aptos de cada seção, não de quem votou, e a comparação é entre "
        "seções, não entre pessoas. Não dá para concluir, por exemplo, que \"os idosos votaram em X\".",
    ]
    ui.resposta(f"O perfil do eleitorado explica o voto em {nm}?", texto, args)

    st.subheader("Quanto cada característica explica")
    e = exp.sort_values("r2")
    ui.barras_h(e["r2"].values, e.index, [AZUL if x == melhor else CINZA_CLARO for x in e.index],
                [f"{pc(x, 0)} · {'↑' if r > 0 else '↓'} onde há {o}" for x, r, o in zip(e["r2"], e["r"], e["onde"])],
                "<b>%{y}</b><br>explica %{x:.0f}% das diferenças<extra></extra>",
                "% das diferenças de voto entre seções explicado pela característica (R²)", faixa=[0, max(30, e["r2"].max() * 2.4)])
    ui.nota("Como ler: se a característica explicasse 100%, saber o perfil de uma seção bastaria para prever o "
            "voto nela; 0% significa que não ajuda nada. A seta mostra o sentido.")

    st.subheader("Quem vai melhor onde")
    ind_t = st.selectbox("Dividir as seções por", list(A.INDICADORES), index=list(A.INDICADORES).index(melhor),
                         key=f"per_ind_{cargo}")
    res, faixas = A.tercos(ind[ind_t], vs, top_c)
    _, alto, baixo, un = A.INDICADORES[ind_t]
    rot = [f"{f[0]:.0f}–{f[1]:.0f}{un}".replace(".", ",") for f in faixas]
    fig = make_subplots(rows=1, cols=len(top_c), subplot_titles=[curto(nome_cand(cargo, c)) for c in top_c],
                        horizontal_spacing=.08)
    for i, c in enumerate(top_c, start=1):
        yy = res[c].values
        folga = max(1.5, (yy.max() - yy.min()) * .6)
        corc = SERIES[i - 1]
        fig.add_trace(go.Scatter(x=rot, y=yy, mode="lines+markers+text", line=dict(color=corc, width=2),
                                 marker=dict(size=10, color=corc, line=dict(width=2, color="#fff")),
                                 text=[pc(x) for x in yy], textposition="top center", cliponaxis=False,
                                 hovertemplate="%{x}: %{y:.1f}%<extra></extra>", showlegend=False), row=1, col=i)
        fig.update_yaxes(range=[yy.min() - folga, yy.max() + folga], ticksuffix="%", row=1, col=i)
    fig.update_xaxes(type="category")
    fig.update_layout(height=340, margin=dict(l=10, r=10, t=40, b=10))
    ui.mostrar(fig)
    ui.nota(f"As 161 seções foram divididas em três grupos do mesmo tamanho: da esquerda ({baixo}) para a direita "
            f"({alto}). Linha subindo = o candidato vai melhor onde o indicador é mais alto. Cada painel tem a "
            "sua própria escala.")
    leitura_ia(f"per_{cargo}_{nr}", f"{CARGOS[cargo]}: perfil do eleitorado e voto em {nome_cand(cargo, nr)}", args)


# ======================================================================= 6. deputados
def cap_deputados():
    cargo = st.segmented_control("Cargo", [DEP_FEDERAL, DEP_ESTADUAL], default=DEP_ESTADUAL,
                                 format_func=CARGOS.get, key="dep_cargo") or DEP_ESTADUAL
    d = deputados(cargo)
    par = A.partidos(ctx, cargo)
    t1 = d.iloc[0]
    top10 = d["% dos votos de Itapira"].head(10).sum()
    base = d[(d["Itapira"] >= 100) & (d["% do total dele que veio da região"] >= 20)]
    est_top = d.sort_values("Posição no estado").head(3)
    p_mais = par[par["Votos em Itapira"] >= 200].sort_values("Diferença (p.p.)")
    mais_rep, menos_rep = p_mais.iloc[-1], p_mais.iloc[0]

    eleitos10 = d.head(10)["Situação"].astype(str).str.startswith("Eleito").sum()
    texto = f"{t1['Candidato']} foi o mais votado, com {pc(t1['% dos votos de Itapira'])} dos votos nominais da cidade."
    if t1["% do total dele que veio da região"] >= 20:
        texto += f" E Itapira foi decisiva para ele: {pc(t1['% do total dele que veio de Itapira'], 0)} de todos os votos dele vieram daqui."
    args = [
        "**Mais votados em Itapira:** " + "; ".join(
            f"{r['Candidato']} {pc(r['% dos votos de Itapira'])}" for _, r in d.head(3).iterrows()) + ".",
        f"**Concentração:** {num(len(d))} candidatos receberam ao menos um voto na cidade, mas os 10 mais votados "
        f"ficaram com {pc(top10, 0)} dos votos nominais. Desses 10, **{eleitos10} foram eleitos**.",
        f"**Situação do mais votado:** {t1['Candidato']} ({t1['Partido']}): {str(t1['Situação']).lower()}.",
        ("**Candidatos com base na região** (20% ou mais de todos os seus votos vieram de Itapira e das 16 vizinhas): "
         + "; ".join(f"{r['Candidato']} ({pc(r['% do total dele que veio da região'], 0)} da região)"
                     for _, r in base.head(4).iterrows())
         + f". Juntos, tiveram {pc(base['% dos votos de Itapira'].sum(), 0)} dos votos nominais de Itapira.")
        if len(base) else "Nenhum candidato teve 20% ou mais dos seus votos vindos de Itapira e das vizinhas.",
        "**Os mais votados do estado em Itapira:** " + "; ".join(
            f"{r['Candidato']} ({int(r['Posição no estado'])}º no estado) teve {pc(r['% dos votos de Itapira'])} aqui"
            for _, r in est_top.iterrows()) + ".",
        f"**Partidos:** em Itapira, {mais_rep.name} teve {pc(mais_rep['Itapira'])} dos votos válidos, "
        f"{pts(mais_rep['Diferença (p.p.)'], False)} acima do estado; {menos_rep.name} teve {pc(menos_rep['Itapira'])}, "
        f"{pts(-menos_rep['Diferença (p.p.)'], False)} abaixo.",
    ]
    ui.resposta(f"Quem Itapira escolheu para {CARGOS[cargo].lower()}?", texto, args)

    st.subheader("Os 15 mais votados em Itapira")
    t = d.head(15)[["Candidato", "Partido", "Situação", "Itapira", "% dos votos de Itapira", "Estado", "Posição no estado",
                    "% do total dele que veio de Itapira", "% do total dele que veio da região"]]
    st.dataframe(t, hide_index=True, width="stretch", column_config={
        "Itapira": COL_NUM("Votos em Itapira"),
        "% dos votos de Itapira": st.column_config.ProgressColumn("% dos votos de Itapira", format="%.1f%%",
                                                                  min_value=0, max_value=float(t["% dos votos de Itapira"].max())),
        "Estado": COL_NUM("Votos no estado"),
        "Posição no estado": st.column_config.NumberColumn("Posição no estado", format="%dº"),
        "% do total dele que veio de Itapira": st.column_config.NumberColumn(format="%.1f%%"),
        "% do total dele que veio da região": st.column_config.ProgressColumn(
            "% do total dele que veio de Itapira + vizinhas", format="%.0f%%", min_value=0, max_value=100),
    })
    ui.nota("**Votos nominais** = votos dados a um candidato (sem os votos só no partido). A última coluna mostra "
            "quanto o candidato depende da região: perto de 100%, quase todos os votos dele vieram daqui.")

    st.subheader("Partidos: Itapira × estado")
    pt = par[par["Votos em Itapira"] >= 100].head(12)
    teto = float(pt[["Itapira", "Estado de SP"]].max().max())
    st.dataframe(pt.rename_axis("Partido").reset_index(), hide_index=True, width="stretch", column_config={
        "Itapira": st.column_config.ProgressColumn("Itapira", format="%.1f%%", min_value=0, max_value=teto),
        "Estado de SP": st.column_config.ProgressColumn("Estado de SP", format="%.1f%%", min_value=0, max_value=teto),
        "Votos em Itapira": COL_NUM("Votos em Itapira"),
        "Diferença (p.p.)": COL_PP("Itapira − estado (pontos)"),
    })
    ui.nota("Votos do partido = votos nos seus candidatos + votos só na legenda, sobre os votos válidos.")
    leitura_ia(f"dep_{cargo}", f"{CARGOS[cargo]}: quem Itapira escolheu", args)


# ======================================================================= 7. comparecimento
def cap_comparecimento():
    comp = A.comparecimento_ref(ctx)
    bn = A.brancos_nulos_ref(ctx)
    it = comp.loc["Itapira"]
    votos22 = ctx["v22"].query("CD_MUNICIPIO == @ITAPIRA and NR_TURNO == 1 and CD_CARGO == 1")["QT_VOTOS"].sum()
    votos26 = ctx["v26"].query("CD_MUNICIPIO == @ITAPIRA and NR_TURNO == 1 and CD_CARGO == 1")["QT_VOTOS"].sum()
    var_aptos = {k: (comp.loc[k, "aptos_2026"] / comp.loc[k, "aptos_2022"] - 1) * 100 for k in comp.index}
    var_votos = (votos26 / votos22 - 1) * 100

    if it[2026] > it[2022] and votos26 < votos22:
        texto = (f"O comparecimento subiu de {pc(it[2022])} para {pc(it[2026])}, mas não porque mais gente votou: "
                 f"foram {num(votos22 - votos26)} votos a menos. O que mudou foi o eleitorado, que encolheu "
                 f"{pc(-var_aptos['Itapira'])}.")
    else:
        texto = f"O comparecimento foi de {pc(it[2022])} em 2022 para {pc(it[2026])} em 2026."
    vot = votantes_secao()
    tsec = (vot / APTOS_SECAO * 100).dropna()
    idade = A.indicadores(perfil_secao)["Idade média"]
    r_idade, _ = A.r2_simples(idade, tsec)
    tb = (pd.DataFrame({"v": vot, "a": APTOS_SECAO}).join(BAIRRO).groupby("BAIRRO").sum())
    tb["%"] = tb["v"] / tb["a"] * 100
    n_maior = (bn["Itapira"] > bn["Estado de SP"]).sum()
    gap = (bn["Itapira"] - bn["Estado de SP"])
    args = [
        f"**Eleitorado apto** de 2022 para 2026: Itapira {pvar(var_aptos['Itapira'])}, "
        f"vizinhas {pvar(var_aptos['Cidades vizinhas'])}, estado {pvar(var_aptos['Estado de SP'])}. "
        f"Itapira perdeu proporcionalmente mais eleitores cadastrados que a região.",
        f"**Votos dados:** {num(votos22)} em 2022 e {num(votos26)} em 2026 ({pvar(var_votos)}).",
        "**Por que isso importa:** quando o cadastro deixa de contar eleitores que já não votavam (por exemplo, "
        "títulos cancelados), a taxa de comparecimento sobe mesmo sem mais gente indo às urnas. Os dados mostram o "
        "efeito, não a causa exata.",
        f"**Comparação:** em 2026, o comparecimento foi de {pc(it[2026])} em Itapira, {pc(comp.loc['Cidades vizinhas', 2026])} "
        f"nas vizinhas e {pc(comp.loc['Estado de SP', 2026])} no estado.",
        f"**Brancos e nulos:** Itapira teve mais brancos e nulos que o estado em {n_maior} de {len(bn)} cargos; a maior "
        f"diferença foi para {gap.idxmax()} ({pc(bn.loc[gap.idxmax(), 'Itapira'])} contra {pc(bn.loc[gap.idxmax(), 'Estado de SP'])}).",
        f"**Dentro da cidade:** o comparecimento foi de {pc(tb['%'].min())} ({tb['%'].idxmin()}) a "
        f"{pc(tb['%'].max())} ({tb['%'].idxmax()}). A relação com a idade média das seções é "
        + ("fraca" if abs(r_idade) < .3 else "moderada" if abs(r_idade) < .5 else "forte")
        + f" (correlação {dec(r_idade)})"
        + (": seções mais velhas votaram menos." if r_idade < -.3 else
           ": seções mais velhas votaram mais." if r_idade > .3 else "."),
    ]
    ui.resposta("Itapira foi mais às urnas?", texto, args)

    c1, c2 = st.columns(2)
    with c1:
        st.subheader("Comparecimento")
        t = pd.DataFrame({"2022": comp[2022], "2026": comp[2026], "Variação (pontos)": comp[2026] - comp[2022],
                          "Eleitorado (variação %)": pd.Series(var_aptos)})
        tabela_progress(t, {"2022": 100, "2026": 100},
                        {"Variação (pontos)": COL_PP("Variação (pontos)"),
                         "Eleitorado (variação %)": st.column_config.NumberColumn(format="%+.1f%%")}, indice="Onde")
    with c2:
        st.subheader("Brancos e nulos")
        b = bn.assign(**{"Diferença (pontos)": gap})
        tabela_progress(b, {"Itapira": 25, "Estado de SP": 25}, {"Diferença (pontos)": COL_PP("Diferença (pontos)")},
                        indice="Cargo")
    st.subheader("Comparecimento por bairro")
    tb = tb.sort_values("%", ascending=False)
    tabela_progress(tb.rename(columns={"v": "Votaram", "a": "Aptos", "%": "Comparecimento"})[
        ["Comparecimento", "Votaram", "Aptos"]], {"Comparecimento": 100},
        {"Votaram": COL_NUM("Votaram"), "Aptos": COL_NUM("Aptos")}, indice="Bairro")
    ui.nota("Comparecimento = votos para Presidente (comparação entre lugares e anos) ou para Governador "
            "(dentro da cidade) divididos pelos eleitores aptos.")
    leitura_ia("comp", "Comparecimento e votos brancos e nulos em Itapira", args)


# ======================================================================= 8. metodologia
def cap_metodologia():
    viz = sorted(ctx["mun"].loc[ctx["vizinhas"], "NM_MUNICIPIO"].str.title())
    st.markdown(f"""
### De onde vêm os dados
Todos os números vêm do **Portal de Dados Abertos do TSE**:
- **Votação por seção eleitoral** (2026 e 2022): votos de cada candidato em cada seção, para todos os municípios.
- **Locais de votação** (2026 e 2022): em que escola fica cada seção, com bairro e coordenadas.
- **Perfil do eleitorado por seção** (julho de 2026): idade, sexo, escolaridade e estado civil dos eleitores aptos.

### Definições
- **Votos válidos**: votos em candidatos e partidos, sem brancos e nulos. É a base dos percentuais.
- **Pontos (p.p.)**: diferença entre dois percentuais. De 60% para 65% são 5 pontos.
- **Bairro**: o bairro do **local de votação** (escola), conforme o cadastro do TSE, revisado em `mapping/bairros.csv`.
- **Cidades vizinhas** ({len(viz)}): {", ".join(viz)}.
- **Comparecimento**: votos dados divididos pelos eleitores aptos.
- **Número 22 / 13**: o número na urna. O 22 foi Jair Bolsonaro em 2022 e Flávio Bolsonaro em 2026; o 13 foi Lula nos dois anos.
- **Correlação**: vai de −1 a +1 e mede se duas coisas sobem e descem juntas entre as seções. Perto de 0 = sem relação.
- **"Explica X% das diferenças" (R²)**: quanto da variação de voto entre seções acompanha uma característica do eleitorado.

### Limitações
- O voto é secreto. Toda comparação é entre **lugares** (seções, bairros, cidades), não entre pessoas.
- O perfil é dos eleitores **aptos**, não de quem compareceu.
- Seções de 2022 e 2026 são comparadas pelo número. As 9 seções do IESI foram transferidas para a ETEC; a seção 161 é nova.
- Votos no exterior ficam fora das comparações por município.
""")
    st.subheader("Baixar dados")
    c1, c2 = st.columns(2)
    tab = votos.pivot_table(index=["NR_SECAO", "BAIRRO", "NM_LOCAL_VOTACAO"], columns=["DS_CARGO", "NOME"],
                            values="QT_VOTOS", aggfunc="sum", fill_value=0)
    c1.download_button("Votos por seção (Itapira, 2026)", tab.to_csv(sep=";").encode("utf-8-sig"),
                       file_name="itapira_2026_votos_por_secao.csv")
    c2.download_button("Seções, locais e bairros", secoes.to_csv(sep=";", index=False).encode("utf-8-sig"),
                       file_name="itapira_2026_secoes.csv")


for aba, cap in zip(abas, [cap_resumo, cap_geografia, cap_mudanca, cap_cargos, cap_perfil, cap_deputados,
                           cap_comparecimento, cap_metodologia]):
    with aba:
        cap()

st.markdown('<div class="in-rodape"><b>Fonte:</b> TSE – Portal de Dados Abertos (votação por seção, locais de '
            'votação e perfil do eleitorado) · Eleições 2022 e 2026 · Zona Eleitoral 0054 – Itapira/SP'
            + (' · Leituras em texto geradas por IA (Claude)' if API_KEY else '') + '</div>',
            unsafe_allow_html=True)

# as chamadas à IA rodam em paralelo desde que cada bloco foi criado; aqui só esperamos e preenchemos
for ph, chave, fut in PENDENTES:
    try:
        texto = fut.result(timeout=180)
    except Exception:  # timeout ou erro inesperado
        texto = None
    _render_ia(ph, chave, texto, final=True)
