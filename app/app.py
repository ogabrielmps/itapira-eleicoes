"""
Análise da votação de Itapira (Zona 54) - Eleições 2026, 1º e 2º turno.

Cada capítulo responde a uma pergunta: resposta curta, argumentos com números e, por fim,
a evidência (tabelas e poucos gráficos). As comparações usam as cidades vizinhas, o estado
de SP, o Brasil e a eleição de 2022.

Rodar:  streamlit run app/app.py
Dados:  etl/preparar_dados.py, etl/preparar_2022.py, etl/preparar_contexto.py e etl/preparar_2turno.py
IA:     ANTHROPIC_API_KEY nos Secrets do Streamlit (opcional) para a leitura em texto de cada capítulo
"""
import hmac
import os

import folium
import numpy as np
import pandas as pd
import plotly.graph_objects as go
import streamlit as st
from streamlit_folium import st_folium

import analise as A
import analise_2t as B
import insights
import ui
from analise import (BRANCO, CARGOS, DEP_ESTADUAL, DEP_FEDERAL, GOVERNADOR, ITAPIRA, NULO,
                     PRESIDENTE, SENADOR, curto)

st.set_page_config(page_title="Itapira 2026 · análise da votação", page_icon="🗳️", layout="wide",
                   initial_sidebar_state="collapsed")
# tema escolhido pelo visitante (escuro por padrão; o botão no topo alterna)
ESCURO = (st.context.theme.type or "dark") != "light"
ui.estilo(ESCURO)
SERIES, OUTROS, CINZA_CLARO, AZUL, FUNDO = ui.SERIES, ui.OUTROS, ui.CINZA_CLARO, ui.AZUL, ui.FUNDO
MARINHO = ui.DESTAQUE  # cor de destaque de Itapira nos gráficos (marinho no claro, amarelo no escuro)


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
    ui.botao_tema(ESCURO)
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
if B.disponivel():  # eleitorado oficial de cada seção no dia da eleição (boletim de urna), e não o do cadastro
    APTOS_SECAO = pd.read_csv(B.ITAPIRA_DIR / "secoes_2t.csv").set_index("NR_SECAO")["APTOS_1T"].reindex(
        APTOS_SECAO.index).fillna(APTOS_SECAO)
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


def mapa_itapira(locais: pd.DataFrame) -> folium.Map:
    """Mapa centrado na área urbana de Itapira com zoom fixo.

    (fit_bounds falha quando o mapa nasce numa aba ainda oculta: o Leaflet mede o tamanho zero e abre
    no mundo inteiro.) Os locais rurais ficam a poucos cliques de zoom."""
    ok = locais.dropna(subset=["NR_LATITUDE"])
    urb = ok[(ok["NR_LATITUDE"] - ok["NR_LATITUDE"].median()).abs() < 0.03]
    return folium.Map(location=[urb["NR_LATITUDE"].mean(), urb["NR_LONGITUDE"].mean()], zoom_start=13,
                      tiles="OpenStreetMap")


COL_PP = lambda nome: st.column_config.NumberColumn(nome, format="%+.1f")  # noqa: E731
COL_NUM = lambda nome: st.column_config.NumberColumn(nome, format="localized")  # noqa: E731

# ======================================================================= cabeçalho
ui.botao_tema(ESCURO)
ui.hero("O que os dados dizem", "Análise da votação", "Itapira comparada à região, ao estado e a 2022")
aptos = int(APTOS_SECAO.sum())


def cartao_vencedor(cargo):
    r = referencias(cargo)
    n = r.loc["Itapira"].idxmax()
    sit = str(ctx["situacao"].get((cargo, n), "")).lower()
    return (f"{CARGOS[cargo]} · {nome_cand(cargo, n)}", pc(r.loc["Itapira", n]),
            f"mais votado em Itapira · estado: {pc(r.loc['Estado de SP', n])}" + (f" · {sit}" if sit else ""))


def cartao_2turno():
    """Resultado do 2º turno presidencial em Itapira (se os dados já foram processados)."""
    if not B.disponivel():
        return cartao_vencedor(PRESIDENTE)
    r = B.carregar()[2]
    it, br, sp = r.loc["Itapira"], r.loc["Brasil"], r.loc["Estado de SP"]
    p = lambda x: x["22"] / (x["22"] + x["13"]) * 100  # noqa: E731
    return (f"Presidente · 2º turno · {nome_cand(PRESIDENTE, 22)}", pc(p(it)),
            f"em Itapira · estado: {pc(p(sp))} · {nome_cand(PRESIDENTE, 13)} eleito no país ({pc(100 - p(br))})")


ui.kpis([
    ("Eleitores aptos", num(aptos), "161 seções · 22 locais de votação"),
    ("Votaram (1º turno)", num(votantes_secao().sum()), pc(votantes_secao().sum() / aptos * 100) + " de comparecimento"),
    cartao_2turno(),
    cartao_vencedor(GOVERNADOR),
])

abas = st.tabs(["🗳️ 2º turno", "📌 Resumo 1º turno", "🗺️ Onde cada um é forte", "🔁 2022 → 2026", "🔀 Voto entre cargos",
                "👥 Perfil e voto", "🏛️ Deputados", "🚶 Comparecimento", "📘 Metodologia"])


# ======================================================================= 0. 2º turno
@st.cache_data
def dados_2t():
    """Seções (1º, 2º turno e 2022), totais de referência, municípios de SP e transferências."""
    if not B.disponivel():
        return None
    v2, s2, ref, mun = B.carregar()
    t = B.tabela_secoes(votos, v2, s2, v22)
    t["bairro"], t["local"] = BAIRRO.reindex(t.index), LOCAL.reindex(t.index).map(A.nome_local)
    ind = A.indicadores(perfil_secao)
    t = t.join(ind[["Idade média", "% com 60 anos ou mais", "% de 16 a 29 anos", "% com ensino superior",
                    "% até o fundamental", "% de mulheres"]])
    t["dF"], t["dL"] = t["pF2"] - t["pF1"], t["pL2"] - t["pL1"]
    t["d22"] = t["pF2"] - t["pF22"]
    s2e = s2[["ENCERRAMENTO_2T"]].copy()
    hm = s2e["ENCERRAMENTO_2T"].str[9:13]
    t["fechou_2t"] = (hm.str[:2].astype(int) * 60 + hm.str[2:].astype(int)).reindex(t.index)  # minutos
    r = ref.copy()
    r["pF"] = r["22"] / (r["22"] + r["13"]) * 100
    r["pL"] = 100 - r["pF"]
    r["comp"] = r["comparecimento"] / r["aptos"] * 100
    r["bn"] = (r["brancos"] + r["nulos"]) / r["comparecimento"] * 100
    mun = mun.copy()
    mun["pF"] = mun["22"] / (mun["22"] + mun["13"]) * 100
    return t, r, mun, B.transferencias_salvas()


def cap_2turno():
    D = dados_2t()
    if D is None:
        st.info("Dados do 2º turno ainda não processados. Rode `python etl/preparar_2turno.py`.")
        return
    t, r, mun, (T, lo, hi, n_or) = D
    nF, nL = nome_cand(PRESIDENTE, 22), nome_cand(PRESIDENTE, 13)
    r22 = referencias(PRESIDENTE, 2022, 2)
    r1 = referencias(PRESIDENTE)
    m22 = municipios_sp(PRESIDENTE, 2022, 2)[22]
    mun["pF22"] = m22.reindex(mun.index)
    mun["sw"] = mun["pF"] - mun["pF22"]
    tot = t[["F1", "L1", "O1", "BN1", "F2", "L2", "BN2", "votaram_1t", "votaram_2t", "aptos", "aptos_1t"]].sum()
    it = r.loc["Itapira"]

    abas2 = st.tabs(["Resultado", "Do 1º para o 2º turno", "Seção a seção", "2022 × 2026", "Comparecimento",
                     "Perfil do eleitorado"])

    # ------------------------------------------------------------------ resultado
    with abas2[0]:
        p = mun["pF"].sort_values(ascending=False)
        pos, acima = list(p.index).index(ITAPIRA) + 1, (p < p[ITAPIRA]).mean() * 100
        esp, r2m = B.esperado_pelo_perfil_2t(ctx, mun)
        d22 = it["pF"] - r22.loc["Itapira", 22]
        sw_sp = r.loc["Estado de SP", "pF"] - r22.loc["Estado de SP", 22]
        sw_br = r.loc["Brasil", "pF"] - r22.loc["Brasil", 22]
        mediana_sp = mun["sw"].median()
        quase = abs(d22) < 0.5
        casas = 2 if quase else 1  # tão perto que vale mostrar os centésimos
        texto = (f"{nF} venceu em Itapira com {pc(it['pF'], casas)}: "
                 + ("praticamente o mesmo resultado" if quase else f"{pts(abs(d22), False)} {'acima' if d22 > 0 else 'abaixo'} do resultado")
                 + f" de Jair Bolsonaro no 2º turno de 2022 ({pc(r22.loc['Itapira', 22], casas)}). No país, {nL} foi eleito "
                 f"com {pc(r.loc['Brasil', 'pL'])}.")
        args = [
            f"**Votos em Itapira:** {nF} {num(it['22'])} × {nL} {num(it['13'])}: diferença de "
            f"**{num(it['22'] - it['13'])} votos**. Brancos e nulos: {num(it['brancos'] + it['nulos'])} "
            f"({pc(it['bn'])} de quem votou).",
            f"**Comparação:** cidades vizinhas {pc(r.loc['Cidades vizinhas', 'pF'])}, estado de SP "
            f"{pc(r.loc['Estado de SP', 'pF'])}, Brasil {pc(r.loc['Brasil', 'pF'])}. Itapira votou como a sua "
            f"região e {pts(it['pF'] - r.loc['Estado de SP', 'pF'], False)} acima do estado.",
            f"**No ranking paulista:** Itapira foi o **{pos}º** de {len(p)} municípios em % de {nF}, acima de "
            f"{acima:.0f}% das cidades do estado.",
            f"**Desde 2022 (2º turno × 2º turno):** Itapira {pts(d22)}; estado {pts(sw_sp)}; Brasil {pts(sw_br)}. "
            f"Mas o município paulista típico (mediana) andou {pts(mediana_sp)} na direção do 22: o recuo do estado "
            "veio das cidades maiores, e Itapira ficou parada.",
            f"**Do 1º para o 2º turno:** {nF} foi de {pc(r1.loc['Itapira', 22])} para {pc(it['pF'])} dos votos válidos e "
            f"{nL} de {pc(r1.loc['Itapira', 13])} para {pc(it['pL'])}: no 2º turno só sobram dois nomes, então os "
            "dois sobem; quem subiu mais ganhou mais eleitores novos (ver a próxima aba).",
            f"**O perfil não explica:** pelo perfil do eleitorado (idade, escolaridade, sexo, calculado com os 645 "
            f"municípios), o esperado para {nF} em Itapira seria **{pc(esp.loc[ITAPIRA, 'esperado'])}**; foi "
            f"{pc(it['pF'])}. Das 17 cidades da região, {(esp.loc[ctx['vizinhas'] + [ITAPIRA], 'real'] > esp.loc[ctx['vizinhas'] + [ITAPIRA], 'esperado']).sum()} "
            "ficaram acima do esperado: o voto é regional.",
        ]
        ui.resposta("Quem venceu em Itapira, e como isso se compara ao estado, ao país e a 2022?", texto, args)

        st.subheader("Itapira lado a lado")
        tab = pd.DataFrame({
            f"{nF} · 1º turno 2026": r1[22], f"{nF} · 2º turno 2026": r["pF"],
            "Número 22 · 2º turno 2022": r22[22], "Mudança vs 2022 (pontos)": r["pF"] - r22[22],
            "Comparecimento 2º turno": r["comp"],
        }).loc[["Itapira", "Cidades vizinhas", "Estado de SP", "Brasil"]]
        tabela_progress(tab, {c: 100 for c in tab.columns if "Mudança" not in c},
                        {"Mudança vs 2022 (pontos)": COL_PP("Mudança vs 2022 (pontos)")}, indice="Onde")
        ui.nota("Percentuais sobre os votos válidos (sem brancos e nulos). Em 2022 o 2º turno também foi 22 × 13 "
                "(Jair Bolsonaro × Lula). Brasil inclui os votos do exterior no 2º turno de 2026.")

        st.subheader("Onde Itapira fica entre os 645 municípios paulistas")
        fig = go.Figure(go.Histogram(x=mun["pF"], nbinsx=40,
                                     marker=dict(color=CINZA_CLARO, line=dict(width=1, color=FUNDO)),
                                     hovertemplate="%{x}: %{y} municípios<extra></extra>"))
        for x, rot, corl, dash in [(it["pF"], f"Itapira {pc(it['pF'])}", MARINHO, "solid"),
                                   (r.loc["Estado de SP", "pF"], f"Estado {pc(r.loc['Estado de SP', 'pF'])}", OUTROS, "dot")]:
            fig.add_vline(x=x, line_color=corl, line_width=3 if dash == "solid" else 2, line_dash=dash,
                          annotation_text=rot, annotation_position="top")
        fig.update_layout(height=320, margin=dict(l=10, r=10, t=40, b=10), bargap=0.05, showlegend=False,
                          xaxis_title=f"% de {nF} nos votos válidos, por município", yaxis_title="nº de municípios")
        ui.mostrar(fig)

        st.subheader("Cidades da região: 2º turno de 2022 × 2026")
        cid = ctx["vizinhas"] + [ITAPIRA]
        rg = mun.loc[cid, ["pF22", "pF", "sw"]].sort_values("sw")
        nomes = [A.nome(ctx["mun"].loc[c, "NM_MUNICIPIO"]) for c in rg.index]
        ui.barras_h(rg["sw"].values, nomes, [MARINHO if c == ITAPIRA else CINZA_CLARO for c in rg.index],
                    [f"{pts(x).replace(' pontos', '').replace(' ponto', '')}  ({a:.0f}% → {b:.0f}%)"
                     for x, a, b in zip(rg["sw"], rg["pF22"], rg["pF"])],
                    "<b>%{y}</b><br>%{x:+.1f} pontos<extra></extra>",
                    "mudança do número 22 entre o 2º turno de 2022 e o de 2026 (pontos)", sw_sp,
                    f"estado {pts(sw_sp)}")
        leitura_ia("2t_res", "2º turno presidencial em Itapira: resultado e comparações", args)

    # ------------------------------------------------------------------ transferências
    with abas2[1]:
        rot_o = {"F1": f"Votou em {nF}", "L1": f"Votou em {nL}", "O1": "Votou em outro candidato",
                 "BN1": "Votou branco ou nulo", "ABS1": "Não votou"}
        rot_d = {"F2": nF, "L2": nL, "BN2": "Branco ou nulo", "ABS2": "Não votou"}
        dF, dL = tot["F2"] - tot["F1"], tot["L2"] - tot["L1"]
        fluxo = T.mul(n_or, axis=0)  # eleitores estimados de cada origem para cada destino
        ganho_L = fluxo["L2"].drop("L1").sort_values(ascending=False)
        ganho_F = fluxo["F2"].drop("F1").sort_values(ascending=False)
        o_F, o_L = T.loc["O1", "F2"] * 100, T.loc["O1", "L2"] * 100
        divisao = ("se dividiram quase ao meio" if abs(o_F - o_L) < 10 else
                   f"foram mais para {nF if o_F > o_L else nL}")
        outros_1t = votos_cargo(PRESIDENTE)
        outros_1t = (outros_1t[~outros_1t["NR_VOTAVEL"].isin([22, 13, BRANCO, NULO])]
                     .groupby("NR_VOTAVEL")["QT_VOTOS"].sum().sort_values(ascending=False))
        lista_outros = ", ".join(f"{nome_cand(PRESIDENTE, n)} ({num(q)})" for n, q in outros_1t.head(4).items())

        # evidência por contagem (sem modelo): seções com mais x menos votos em outros candidatos
        q = pd.qcut(t["pO1"].rank(method="first"), 3, labels=[0, 1, 2])
        g = t.groupby(q, observed=True)[["F1", "L1", "O1", "F2", "L2"]].sum()
        g["dF"] = g["F2"] / (g["F2"] + g["L2"]) * 100 - g["F1"] / (g["F1"] + g["L1"] + g["O1"]) * 100
        g["dL"] = g["L2"] / (g["F2"] + g["L2"]) * 100 - g["L1"] / (g["F1"] + g["L1"] + g["O1"]) * 100
        faixa = t.groupby(q, observed=True)["pO1"].agg(["min", "max"])

        texto = (f"{nL} cresceu mais: +{num(dL)} votos, contra +{num(dF)} de {nF}. Pela estimativa, os eleitores dos "
                 f"candidatos eliminados {divisao}, e {nL} levou a maior parte de quem tinha votado branco ou nulo.")
        args = [
            f"**Contagem (dado oficial, sem estimativa):** {nF} {num(tot['F1'])} → {num(tot['F2'])} "
            f"(+{num(dF)}); {nL} {num(tot['L1'])} → {num(tot['L2'])} (+{num(dL)}); brancos e nulos "
            f"{num(tot['BN1'])} → {num(tot['BN2'])} ({num(tot['BN2'] - tot['BN1'])}); votaram "
            f"{num(tot['votaram_1t'])} → {num(tot['votaram_2t'])} (+{num(tot['votaram_2t'] - tot['votaram_1t'])}).",
            f"**Votos que ficaram livres:** {num(tot['O1'])} eleitores votaram em outros candidatos no 1º turno "
            f"({lista_outros}…).",
            f"**Eleitores dos eliminados (estimativa):** de cada 100, ~{o_F:.0f} foram para {nF} "
            f"(entre {lo.loc['O1', 'F2'] * 100:.0f} e {hi.loc['O1', 'F2'] * 100:.0f}), ~{o_L:.0f} para {nL} "
            f"(entre {lo.loc['O1', 'L2'] * 100:.0f} e {hi.loc['O1', 'L2'] * 100:.0f}), ~{T.loc['O1', 'BN2'] * 100:.0f} "
            f"votaram branco/nulo e ~{T.loc['O1', 'ABS2'] * 100:.0f} não voltaram.",
            f"**Quem tinha votado branco ou nulo:** ~{T.loc['BN1', 'L2'] * 100:.0f}% foram para {nL}, "
            f"~{T.loc['BN1', 'F2'] * 100:.0f}% para {nF} e ~{T.loc['BN1', 'BN2'] * 100:.0f}% repetiram o branco/nulo.",
            f"**Quem não tinha votado no 1º turno:** ~{T.loc['ABS1', 'L2'] * 100:.0f}% votaram em {nL} e "
            f"~{T.loc['ABS1', 'F2'] * 100:.0f}% em {nF} no 2º turno; ~{T.loc['ABS1', 'ABS2'] * 100:.0f}% continuaram sem votar.",
            f"**Fidelidade:** ~{T.loc['F1', 'F2'] * 100:.0f}% dos eleitores de {nF} e ~{T.loc['L1', 'L2'] * 100:.0f}% "
            f"dos de {nL} no 1º turno repetiram o voto.",
            f"**De onde veio o crescimento de {nL} (estimativa):** "
            + "; ".join(f"~{num(round(v, -1))} de \"{rot_o[k].lower()}\"" for k, v in ganho_L.head(3).items()) + ".",
            f"**De onde veio o crescimento de {nF} (estimativa):** "
            + "; ".join(f"~{num(round(v, -1))} de \"{rot_o[k].lower()}\"" for k, v in ganho_F.head(3).items()) + ".",
            f"**Evidência por contagem (sem modelo):** nas seções onde os outros candidatos tiveram mais votos no 1º turno "
            f"({dec(faixa.loc[2, 'min'], 1)}% a {dec(faixa.loc[2, 'max'], 1)}%), {nF} subiu {pts(g.loc[2, 'dF'])} e {nL} "
            f"{pts(g.loc[2, 'dL'])}; nas com menos ({dec(faixa.loc[0, 'min'], 1)}% a {dec(faixa.loc[0, 'max'], 1)}%), "
            f"{nF} {pts(g.loc[0, 'dF'])} e {nL} {pts(g.loc[0, 'dL'])}.",
        ]
        ui.resposta("De onde vieram os votos do 2º turno?", texto, args)

        st.subheader("Para onde foi cada eleitor do 1º turno (estimativa)")
        cores_o = {"F1": SERIES[0], "L1": SERIES[1], "O1": SERIES[2], "BN1": OUTROS, "ABS1": CINZA_CLARO}
        cores_d = {"F2": SERIES[0], "L2": SERIES[1], "BN2": OUTROS, "ABS2": CINZA_CLARO}
        orig, dest = list(T.index), list(T.columns)
        # totais oficiais do 2º turno nos rótulos (os fluxos são estimados e somam quase o mesmo)
        oficial_d = {"F2": tot["F2"], "L2": tot["L2"], "BN2": tot["BN2"], "ABS2": tot["aptos"] - tot["votaram_2t"]}
        src, tgt, val, cor_l = [], [], [], []
        for i, o in enumerate(orig):
            for j, dd in enumerate(dest):
                v = fluxo.loc[o, dd]
                if v >= 40:
                    src.append(i)
                    tgt.append(len(orig) + j)
                    val.append(round(v))
                    h = cores_o[o].lstrip("#")
                    cor_l.append(f"rgba({int(h[0:2], 16)},{int(h[2:4], 16)},{int(h[4:6], 16)},0.35)")
        fig = go.Figure(go.Sankey(
            node=dict(label=[f"{rot_o[o]} ({num(n_or[o])})" for o in orig]
                      + [f"{rot_d[dd]} ({num(oficial_d[dd])})" for dd in dest],
                      color=[cores_o[o] for o in orig] + [cores_d[dd] for dd in dest], pad=18, thickness=16),
            link=dict(source=src, target=tgt, value=val, color=cor_l,
                      hovertemplate="%{source.label} → %{target.label}<br>~%{value:,.0f} eleitores<extra></extra>"),
        ))
        fig.update_layout(height=430, margin=dict(l=10, r=10, t=10, b=10), font=dict(size=13))
        st.plotly_chart(fig, width="stretch", config={"displayModeBar": False})
        ui.nota("Esquerda: o que cada eleitor fez no 1º turno. Direita: no 2º turno. A espessura é o número estimado de "
                "eleitores (fluxos com menos de 40 pessoas ficam ocultos).")

        st.subheader("De cada 100 eleitores do 1º turno… (com margem de incerteza)")
        mat = pd.DataFrame({rot_d[dd]: [f"{T.loc[o, dd] * 100:.0f}  ({lo.loc[o, dd] * 100:.0f}–{hi.loc[o, dd] * 100:.0f})"
                                        for o in orig] for dd in dest}, index=[rot_o[o] for o in orig])
        mat.insert(0, "Eleitores no 1º turno", [num(n_or[o]) for o in orig])
        st.dataframe(mat.rename_axis("No 1º turno").reset_index(), hide_index=True, width="stretch")
        ui.nota("**Como foi estimado:** o voto é secreto, então ninguém sabe como cada pessoa votou. A estimativa usa a "
                "variação entre as 161 seções: se onde havia mais eleitores de um grupo no 1º turno aparece mais voto "
                "num candidato no 2º, isso indica a transferência. Supõe que os grupos se comportaram de forma parecida "
                "em toda a cidade. Entre parênteses, a faixa onde o valor real provavelmente está (90% das repetições do "
                "cálculo com seções sorteadas). Faixas largas = pouca certeza.")
        leitura_ia("2t_transf", "2º turno em Itapira: de onde vieram os votos de cada candidato", args)

    # ------------------------------------------------------------------ seção a seção
    with abas2[2]:
        venc_L = t[t["pL2"] > t["pF2"]]
        q1, q3 = t["pF2"].quantile([.25, .75])
        r_12 = t["pF1"].corr(t["pF2"])
        maisL = t.sort_values("dL", ascending=False).head(3)
        maisF = t.sort_values("dF", ascending=False).head(3)
        caiuF = (t["pF2"] < t["pF1"]).sum()
        ext_max, ext_min = t["pF2"].idxmax(), t["pF2"].idxmin()

        def sec_txt(s):
            return f"seção {s} ({t.loc[s, 'local']}, {t.loc[s, 'bairro']})"

        texto = (f"{nF} venceu em {len(t) - len(venc_L)} das {len(t)} seções"
                 + (f"; {nL} venceu em {len(venc_L)}: " + ", ".join(sec_txt(s) + f", com {pc(t.loc[s, 'pL2'])}"
                                                                     for s in venc_L.index) + "." if len(venc_L) else "."))
        args = [
            f"**Faixa:** de {pc(t.loc[ext_min, 'pF2'])} na {sec_txt(ext_min)} a {pc(t.loc[ext_max, 'pF2'])} na "
            f"{sec_txt(ext_max)}. Metade das seções ficou entre {pc(q1)} e {pc(q3)}.",
            f"**O mapa do 1º turno se manteve:** a correlação entre o % de {nF} no 1º e no 2º turno, seção a seção, é "
            f"{dec(r_12)}. As seções fortes de um continuaram fortes no outro.",
            f"**{nF} perdeu fatia em {caiuF} seções** do 1º para o 2º turno (% dos válidos); em todas as outras, subiu.",
            f"**Onde {nL} mais cresceu:** " + "; ".join(f"{sec_txt(s)}: {pts(t.loc[s, 'dL'])}" for s in maisL.index) + ".",
            f"**Onde {nF} mais cresceu:** " + "; ".join(f"{sec_txt(s)}: {pts(t.loc[s, 'dF'])}" for s in maisF.index) + ".",
            "**Cuidado com seções pequenas:** cada seção tem entre "
            f"{num(t['aptos'].min())} e {num(t['aptos'].max())} eleitores; numa seção de ~300 votos, 3 votos já mudam "
            "1 ponto percentual.",
        ]
        ui.resposta("Como cada uma das 161 seções votou?", texto, args)

        c1, c2 = st.columns([1, 1])
        with c1:
            st.subheader("Distribuição das seções")
            fig = go.Figure(go.Histogram(x=t["pF2"], xbins=dict(size=2), marker=dict(color=SERIES[0],
                                         line=dict(width=1, color=FUNDO)),
                                         hovertemplate="%{x}%: %{y} seções<extra></extra>"))
            fig.add_vline(x=it["pF"], line_color=MARINHO, line_width=3, annotation_text=f"cidade {pc(it['pF'])}",
                          annotation_position="top")
            fig.add_vline(x=50, line_color=OUTROS, line_dash="dot", annotation_text="50%", annotation_position="top left")
            fig.update_layout(height=380, margin=dict(l=10, r=10, t=40, b=10), bargap=0.05, showlegend=False,
                              xaxis_title=f"% de {nF} na seção (2º turno)", yaxis_title="nº de seções")
            ui.mostrar(fig)
        with c2:
            st.subheader("Mapa por local de votação")
            loc = t.assign(L=secoes.set_index("NR_SECAO")["NR_LOCAL_VOTACAO"].reindex(t.index)).groupby("L")[["F2", "L2"]].sum()
            loc["p"] = loc["F2"] / (loc["F2"] + loc["L2"]) * 100
            locais = secoes.groupby("NR_LOCAL_VOTACAO").first()
            m = mapa_itapira(locais)
            for lid, row in loc.iterrows():
                info = locais.loc[lid]
                if pd.isna(info["NR_LATITUDE"]):
                    continue
                tt = row["F2"] + row["L2"]
                folium.CircleMarker(
                    [info["NR_LATITUDE"], info["NR_LONGITUDE"]], radius=7 + 16 * (tt / (loc["F2"] + loc["L2"]).max()) ** .5,
                    color="#ffffff", weight=2, fill=True, fill_color=ui.cor_seq(row["p"], loc["p"].min(), loc["p"].max()),
                    fill_opacity=.9,
                    tooltip=f"<b>{info['NM_LOCAL_VOTACAO']}</b><br>{info['BAIRRO']}<br>{nF}: {pc(row['p'])} · "
                            f"{nL}: {pc(100 - row['p'])}",
                ).add_to(m)
            st_folium(m, height=380, use_container_width=True, returned_objects=[], key="mapa_2t")
            ui.nota(f"Mais escuro = maior % de {nF} (de {pc(loc['p'].min())} a {pc(loc['p'].max())}).")

        st.subheader("Todas as seções")
        f1, f2 = st.columns([2, 1])
        bairros_sel = f1.multiselect("Filtrar bairros", sorted(t["bairro"].dropna().unique()), key="2t_bairros")
        ordem = f2.selectbox("Ordenar por", ["Seção", f"% {nF} (2º turno)", f"Crescimento de {nL}",
                                              f"Crescimento de {nF}", "Mudança vs 2022", "Comparecimento"],
                             key="2t_ordem")
        tv = t if not bairros_sel else t[t["bairro"].isin(bairros_sel)]
        chave_ord = {"Seção": None, f"% {nF} (2º turno)": "pF2", f"Crescimento de {nL}": "dL",
                     f"Crescimento de {nF}": "dF", "Mudança vs 2022": "d22", "Comparecimento": "comp2"}[ordem]
        if chave_ord:
            tv = tv.sort_values(chave_ord, ascending=False)
        tabela = pd.DataFrame({
            "Bairro": tv["bairro"], "Local": tv["local"], "Aptos": tv["aptos"],
            f"{nF} 2º t.": tv["pF2"], f"{nL} 2º t.": tv["pL2"],
            f"{nF} 1º t.": tv["pF1"], f"{nL} 1º t.": tv["pL1"], "Outros 1º t.": tv["pO1"],
            f"Var. {nF}": tv["dF"], f"Var. {nL}": tv["dL"],
            "22 em 2022 (2º t.)": tv["pF22"], "Mudança vs 2022": tv["d22"],
            "Comparec. 1º t.": tv["comp1"], "Comparec. 2º t.": tv["comp2"], "Branco/nulo 2º t.": tv["bn2"],
            "Idade média": tv["Idade média"], "% superior": tv["% com ensino superior"],
        })
        tabela.index.name = "Seção"
        tabela_progress(tabela, {f"{nF} 2º t.": 100, f"{nL} 2º t.": 100},
                        {**{c: COL_PP(c) for c in [f"Var. {nF}", f"Var. {nL}", "Mudança vs 2022"]},
                         **{c: st.column_config.NumberColumn(c, format="%.1f%%") for c in
                            [f"{nF} 1º t.", f"{nL} 1º t.", "Outros 1º t.", "22 em 2022 (2º t.)", "Comparec. 1º t.",
                             "Comparec. 2º t.", "Branco/nulo 2º t.", "% superior"]},
                         "Idade média": st.column_config.NumberColumn(format="%.1f"), "Aptos": COL_NUM("Aptos")},
                        altura=520, indice="Seção")
        ui.nota("Percentuais de candidatos sobre os votos válidos; comparecimento sobre os aptos; branco/nulo sobre quem "
                "votou. \"Var.\" = mudança do 1º para o 2º turno, em pontos. Clique no nome de uma coluna para ordenar.")
        st.download_button("Baixar a tabela (CSV)", tabela.round(2).to_csv(sep=";").encode("utf-8-sig"),
                           file_name="itapira_2026_2turno_por_secao.csv")
        leitura_ia("2t_secoes", "2º turno em Itapira, seção a seção", args)

    # ------------------------------------------------------------------ 2022 x 2026
    with abas2[3]:
        tc = t.dropna(subset=["pF22"])
        dentro2 = (tc["d22"].abs() <= 2).mean() * 100
        r_22 = tc["pF22"].corr(tc["pF2"])
        sobe, desce = tc.sort_values("d22", ascending=False).head(3), tc.sort_values("d22").head(3)
        bai = tc.groupby("bairro")[["F2", "L2"]].sum()
        v22b = v22[(v22["NR_TURNO"] == 2) & v22["NR_SECAO"].isin(tc.index)].assign(B=lambda d: d["NR_SECAO"].map(BAIRRO))
        p22b = v22b.pivot_table(index="B", columns="NR_VOTAVEL", values="QT_VOTOS", aggfunc="sum")
        bai["2022"] = p22b[22] / (p22b[22] + p22b[13]) * 100
        bai["2026"] = bai["F2"] / (bai["F2"] + bai["L2"]) * 100
        bai["Mudança (pontos)"] = bai["2026"] - bai["2022"]
        bai = bai.sort_values("Mudança (pontos)", ascending=False)
        d22 = it["pF"] - r22.loc["Itapira", 22]
        texto = (f"Na cidade, Itapira repetiu 2022 ({pc(r22.loc['Itapira', 22])} → {pc(it['pF'])}). Por dentro, porém, "
                 f"houve trocas: algumas seções andaram até {pts(tc['d22'].abs().max(), False)} para um lado ou para o outro.")
        args = [
            f"**Na média, nada mudou:** a variação média das seções foi de {pts(tc['d22'].mean())}, e "
            f"{dentro2:.0f}% delas ficaram a até 2 pontos do resultado de 2022.",
            f"**O mapa é o mesmo:** correlação de {dec(r_22)} entre 2022 e 2026, seção a seção.",
            "**Onde o 22 mais avançou:** " + "; ".join(f"seção {s} ({tc.loc[s, 'bairro']}): {pts(tc.loc[s, 'd22'])}"
                                                       for s in sobe.index) + ".",
            "**Onde o 22 mais recuou:** " + "; ".join(f"seção {s} ({tc.loc[s, 'bairro']}): {pts(tc.loc[s, 'd22'])}"
                                                      for s in desce.index) + ".",
            f"**Por bairro:** maior avanço do 22 em {bai.index[0]} ({pts(bai.iloc[0]['Mudança (pontos)'])}); maior recuo "
            f"em {bai.index[-1]} ({pts(bai.iloc[-1]['Mudança (pontos)'])}).",
            f"**Fora de Itapira:** o estado foi {pts(r.loc['Estado de SP', 'pF'] - r22.loc['Estado de SP', 22])} e o Brasil "
            f"{pts(r.loc['Brasil', 'pF'] - r22.loc['Brasil', 22])} para o 22; entre as cidades vizinhas, a mudança foi de "
            f"{pts(mun.loc[ctx['vizinhas'], 'sw'].min())} a {pts(mun.loc[ctx['vizinhas'], 'sw'].max())}.",
            f"**Candidatos diferentes:** o número 22 foi Jair Bolsonaro em 2022 e {nF} em 2026; Lula foi o 13 nas duas. "
            "A comparação mostra a força do número/campo, não de uma pessoa só.",
        ]
        ui.resposta("O 2º turno de 2026 repetiu o de 2022?", texto, args)
        st.subheader("Por bairro: número 22 no 2º turno")
        tabela_progress(bai[["2022", "2026", "Mudança (pontos)"]], {"2022": 100, "2026": 100},
                        {"Mudança (pontos)": COL_PP("Mudança (pontos)")}, indice="Bairro")
        with st.expander("Ver seção a seção (gráfico de dispersão)"):
            fig = go.Figure()
            lo_, hi_ = min(tc["pF22"].min(), tc["pF2"].min()) - 2, max(tc["pF22"].max(), tc["pF2"].max()) + 2
            fig.add_trace(go.Scatter(x=[lo_, hi_], y=[lo_, hi_], mode="lines", line=dict(color=OUTROS, dash="dot"),
                                     hoverinfo="skip", showlegend=False))
            fig.add_trace(go.Scatter(x=tc["pF22"], y=tc["pF2"], mode="markers", showlegend=False,
                                     marker=dict(size=9, color=SERIES[0], opacity=.8, line=dict(width=1.5, color=FUNDO)),
                                     customdata=np.c_[tc.index, tc["bairro"]],
                                     hovertemplate="<b>Seção %{customdata[0]}</b> · %{customdata[1]}<br>2022: %{x:.1f}%<br>"
                                                   "2026: %{y:.1f}%<extra></extra>"))
            fig.update_layout(height=430, margin=dict(l=10, r=10, t=10, b=10),
                              xaxis_title="% do 22 no 2º turno de 2022", yaxis_title=f"% de {nF} no 2º turno de 2026")
            fig.update_xaxes(range=[lo_, hi_])
            fig.update_yaxes(range=[lo_, hi_])
            ui.mostrar(fig)
            ui.nota("Cada ponto é uma seção. Acima da linha: o 22 foi melhor em 2026; abaixo: pior. A seção 161 é nova "
                    "e não aparece.")
        leitura_ia("2t_2022", "2º turno de 2026 comparado ao de 2022 em Itapira", args)

    # ------------------------------------------------------------------ comparecimento
    with abas2[4]:
        comp = A.comparecimento_ref(ctx)
        dcomp = t["comp2"] - t["comp1"]
        r_cl = dcomp.corr(t["dL"])
        r_cf = dcomp.corr(t["dF"])
        tarde = t[t["fechou_2t"] > 17 * 60 + 10]
        ultima = t["fechou_2t"].idxmax()
        hhmm = lambda m: f"{int(m // 60)}h{int(m % 60):02d}"  # noqa: E731
        bai = t.groupby("bairro")[["votaram_1t", "votaram_2t", "aptos", "BN1", "BN2"]].sum()
        bai["Comparec. 1º t."] = bai["votaram_1t"] / bai["aptos"] * 100
        bai["Comparec. 2º t."] = bai["votaram_2t"] / bai["aptos"] * 100
        bai["Variação (pontos)"] = bai["Comparec. 2º t."] - bai["Comparec. 1º t."]
        bai["Branco/nulo 1º t."] = bai["BN1"] / bai["votaram_1t"] * 100
        bai["Branco/nulo 2º t."] = bai["BN2"] / bai["votaram_2t"] * 100
        bai = bai.sort_values("Variação (pontos)", ascending=False)
        c1t, c2t = tot["votaram_1t"] / tot["aptos_1t"] * 100, it["comp"]
        texto = (f"Sim: votaram {num(tot['votaram_2t'] - tot['votaram_1t'])} pessoas a mais que no 1º turno "
                 f"({pc(c1t)} → {pc(c2t)}), e os brancos e nulos caíram de {pc(tot['BN1'] / tot['votaram_1t'] * 100)} para "
                 f"{pc(it['bn'])} dos votos.")
        args = [
            f"**Comparação:** no estado, o comparecimento foi de {pc(comp.loc['Estado de SP', 2026])} para "
            f"{pc(r.loc['Estado de SP', 'comp'])}; no Brasil, de {pc(comp.loc['Brasil', 2026])} para {pc(r.loc['Brasil', 'comp'])}; "
            f"nas vizinhas, de {pc(comp.loc['Cidades vizinhas', 2026])} para {pc(r.loc['Cidades vizinhas', 'comp'])}.",
            f"**Seções:** o comparecimento subiu em {(dcomp > 0).sum()} das {len(t)} seções; a maior alta foi na seção "
            f"{dcomp.idxmax()} ({t.loc[dcomp.idxmax(), 'bairro']}, {pts(dcomp.max())}).",
            f"**Quem ganhou com o aumento?** A relação entre o aumento do comparecimento e o crescimento de cada "
            f"candidato, seção a seção, é {dec(r_cl)} para {nL} e {dec(r_cf)} para {nF}: "
            + ("fraca nos dois casos, ou seja, os novos votantes não mudaram o resultado das seções de forma clara."
               if max(abs(r_cl), abs(r_cf)) < .3 else
               f"{'positiva' if r_cl > 0 else 'negativa'} para {nL}: onde mais gente voltou, {nL} cresceu "
               f"{'mais' if r_cl > 0 else 'menos'}."),
            f"**Brancos e nulos:** caíram em {(t['bn2'] < t['bn1']).sum()} das {len(t)} seções: no 2º turno, parte de quem "
            "anulou no 1º escolheu um lado (ver a aba \"Do 1º para o 2º turno\").",
            (f"**Filas:** {len(tarde)} urnas encerraram depois das 17h10 (sinal de eleitores na fila no fim do dia); a "
             if len(tarde) else "**Filas:** nenhuma urna encerrou depois das 17h10, sinal de que não houve fila relevante "
             "no fim do dia; a ")
            + f"última a fechar foi a da seção {ultima} ({t.loc[ultima, 'local']}), às {hhmm(t.loc[ultima, 'fechou_2t'])}.",
        ]
        ui.resposta("Mais gente votou no 2º turno?", texto, args)
        st.subheader("Por bairro")
        tabela_progress(bai[["Comparec. 1º t.", "Comparec. 2º t.", "Variação (pontos)", "Branco/nulo 1º t.",
                             "Branco/nulo 2º t."]], {"Comparec. 1º t.": 100, "Comparec. 2º t.": 100},
                        {"Variação (pontos)": COL_PP("Variação (pontos)"),
                         "Branco/nulo 1º t.": st.column_config.NumberColumn(format="%.1f%%"),
                         "Branco/nulo 2º t.": st.column_config.NumberColumn(format="%.1f%%")}, indice="Bairro")
        ui.nota("Comparecimento = quem votou ÷ eleitores aptos. Branco/nulo = % de quem votou. Os horários vêm do "
                "boletim de cada urna.")
        leitura_ia("2t_comp", "2º turno em Itapira: comparecimento, brancos e nulos", args)

    # ------------------------------------------------------------------ perfil
    with abas2[5]:
        inds = ["Idade média", "% com 60 anos ou mais", "% de 16 a 29 anos", "% com ensino superior",
                "% até o fundamental", "% de mulheres"]
        linhas = []
        for i in inds:
            rF, r2F = A.r2_simples(t[i], t["pF2"])
            rL, r2L = A.r2_simples(t[i], t["dL"])
            qq = pd.qcut(t[i].rank(method="first"), 3, labels=[0, 1, 2])
            g = t.groupby(qq, observed=True)[["F2", "L2", "F1", "L1", "O1"]].sum()
            pF_alto = g.loc[2, "F2"] / (g.loc[2, "F2"] + g.loc[2, "L2"]) * 100
            pF_baixo = g.loc[0, "F2"] / (g.loc[0, "F2"] + g.loc[0, "L2"]) * 100
            dl = lambda k: g.loc[k, "L2"] / (g.loc[k, "F2"] + g.loc[k, "L2"]) * 100 - g.loc[k, "L1"] / (g.loc[k, ["F1", "L1", "O1"]].sum()) * 100  # noqa: E731
            fx = t.groupby(qq, observed=True)[i].agg(["min", "max"])
            un = A.INDICADORES[i][3]
            linhas.append({"Característica": i, "faixa_mais": f"{fx.loc[2, 'min']:.0f}–{fx.loc[2, 'max']:.0f}{un}",
                           "faixa_menos": f"{fx.loc[0, 'min']:.0f}–{fx.loc[0, 'max']:.0f}{un}",
                           f"{nF}: seções com mais": pF_alto, f"{nF}: seções com menos": pF_baixo,
                           "Diferença (pontos)": pF_alto - pF_baixo,
                           f"Cresc. {nL}: com mais": dl(2), f"Cresc. {nL}: com menos": dl(0),
                           "r2F": r2F * 100, "rF": rF, "r2L": r2L * 100, "rL": rL})
        pf = pd.DataFrame(linhas).set_index("Característica")
        top = pf["Diferença (pontos)"].abs().idxmax()
        topL = (pf[f"Cresc. {nL}: com mais"] - pf[f"Cresc. {nL}: com menos"]).abs().idxmax()
        multi = A.r2_multiplo(t[["Idade média", "% com ensino superior", "% de mulheres"]], t["pF2"]) * 100
        multiL = A.r2_multiplo(t[["Idade média", "% com ensino superior", "% de mulheres"]], t["dL"]) * 100
        alto, baixo = A.INDICADORES[top][1], A.INDICADORES[top][2]
        texto = (f"Pouco. O que mais separa as seções é {NOME_FRASE[top]}: nas seções com {alto}, {nF} teve "
                 f"{pc(pf.loc[top, f'{nF}: seções com mais'])}; nas com {baixo}, {pc(pf.loc[top, f'{nF}: seções com menos'])}.")
        args = [
            f"**Juntas**, idade, escolaridade e sexo explicam **{pc(multi, 0)}** das diferenças de voto entre as seções no 2º "
            f"turno; o resto vem de outros fatores (vizinhança, história local, candidatos locais…).",
            f"**{NOME_FRASE[top].capitalize()}:** seções com {alto} ({pf.loc[top, 'faixa_mais']}) deram "
            f"{pc(pf.loc[top, f'{nF}: seções com mais'])} a {nF}; com {baixo} ({pf.loc[top, 'faixa_menos']}), "
            f"{pc(pf.loc[top, f'{nF}: seções com menos'])}.",
            f"**Onde {nL} cresceu mais do 1º para o 2º turno:** o que mais separa é {NOME_FRASE[topL]}: "
            f"{pts(pf.loc[topL, f'Cresc. {nL}: com mais'])} nas seções com {A.INDICADORES[topL][1]} e "
            f"{pts(pf.loc[topL, f'Cresc. {nL}: com menos'])} nas com {A.INDICADORES[topL][2]}. As características juntas "
            f"explicam {pc(multiL, 0)} do crescimento dele.",
            "**Limitação:** o perfil é dos eleitores aptos de cada seção e a comparação é entre seções, não entre "
            "pessoas. Não dá para concluir que \"os mais velhos votaram em X\".",
        ]
        ui.resposta("O perfil do eleitorado explica o 2º turno?", texto, args)
        st.subheader("Seções com mais × com menos de cada característica")
        cols = ["faixa_mais", f"{nF}: seções com mais", "faixa_menos", f"{nF}: seções com menos", "Diferença (pontos)",
                f"Cresc. {nL}: com mais", f"Cresc. {nL}: com menos"]
        tabela_progress(pf[cols].rename(columns={"faixa_mais": "Faixa (mais)", "faixa_menos": "Faixa (menos)"}),
                        {f"{nF}: seções com mais": 100, f"{nF}: seções com menos": 100},
                        {"Diferença (pontos)": COL_PP("Diferença (pontos)"),
                         f"Cresc. {nL}: com mais": COL_PP(f"Cresc. {nL}: com mais"),
                         f"Cresc. {nL}: com menos": COL_PP(f"Cresc. {nL}: com menos")}, indice="Característica")
        ui.nota("Para cada característica, as 161 seções foram divididas em três grupos iguais; a tabela compara o terço "
                f"com mais com o terço com menos. \"Cresc. {nL}\" = quanto a fatia dele subiu do 1º para o 2º turno.")
        leitura_ia("2t_perfil", "2º turno em Itapira: perfil do eleitorado e voto", args)


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
    fig = go.Figure(go.Histogram(x=dist, nbinsx=40, marker=dict(color=CINZA_CLARO, line=dict(width=1, color=FUNDO)),
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
        m = mapa_itapira(locais)
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
        f"(maior: {A.nome(ctx['mun'].loc[var_cid.index[0], 'NM_MUNICIPIO'])}, {pts(var_cid.iloc[0])}; menor: "
        f"{A.nome(ctx['mun'].loc[var_cid.index[-1], 'NM_MUNICIPIO'])}, {pts(var_cid.iloc[-1])}).",
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
    nomes = [A.nome(ctx["mun"].loc[c, "NM_MUNICIPIO"]) for c in var_cid.index]
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
            marker=dict(size=9, color=SERIES[0], opacity=.8, line=dict(width=1.5, color=FUNDO)),
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
    p1, p2, g1, g2 = rp.index[0], rp.index[1], rg.index[0], rg.index[1]
    s_top = list(rs.index[:4])
    linhas = ([(PRESIDENTE, p1), (PRESIDENTE, p2)] + [(GOVERNADOR, g1), (GOVERNADOR, g2)]
              + [(SENADOR, n) for n in s_top])
    bn = [(c, n) for c in (PRESIDENTE, GOVERNADOR, SENADOR) for n in (BRANCO, NULO)]
    t = A.por_100_eleitores(ctx, linhas + bn)
    nm = lambda c, n: curto(nome_cand(c, n))  # noqa: E731
    it = t["Itapira"]

    def gap(a, b, onde="Itapira"):
        return t.loc[[b], onde].iloc[0] - t.loc[[a], onde].iloc[0]

    d1, d2 = gap((PRESIDENTE, p1), (GOVERNADOR, g1)), gap((PRESIDENTE, p2), (GOVERNADOR, g2))
    d1_sp, d1_viz = gap((PRESIDENTE, p1), (GOVERNADOR, g1), "Estado de SP"), gap((PRESIDENTE, p1), (GOVERNADOR, g1), "Cidades vizinhas")
    d2_sp = gap((PRESIDENTE, p2), (GOVERNADOR, g2), "Estado de SP")
    vot = votantes_secao().sum()
    falta = abs(d1) / 100 * vot
    brancos = {c: it[(c, BRANCO)] + it[(c, NULO)] for c in (PRESIDENTE, GOVERNADOR, SENADOR)}

    def por100(x):
        return f"{x:.0f}".replace(".", ",")

    mais_g = nm(GOVERNADOR, g1) if d1 > 0 else nm(PRESIDENTE, p1)
    texto = (f"Quase: a cada 100 eleitores, {por100(it[(PRESIDENTE, p1)])} votaram em {nm(PRESIDENTE, p1)} para presidente, "
             f"{por100(it[(GOVERNADOR, g1)])} em {nm(GOVERNADOR, g1)} para governador e cerca de "
             f"{por100(it[(SENADOR, s_top[0])])} em cada um dos dois mais votados para o Senado.")
    args = [
        f"**{nm(PRESIDENTE, p1)} × {nm(GOVERNADOR, g1)}:** {mais_g} teve **{dec(abs(d1), 1)} votos a mais a cada 100 "
        f"eleitores**. Como cada eleitor dá no máximo um voto a cada candidato, isso quer dizer que pelo menos "
        f"~{num(round(falta, -1))} pessoas votaram em um e não no outro.",
        f"**Comparando com fora:** essa diferença foi de {dec(abs(d1_viz), 1)} nas cidades vizinhas e de "
        f"{dec(abs(d1_sp), 1)} no estado. "
        + ("Em Itapira, o voto para presidente e governador ficou **mais alinhado** que no estado."
           if abs(d1) < abs(d1_sp) - 0.5 else
           "Em Itapira, o voto para presidente e governador ficou **menos alinhado** que no estado."
           if abs(d1) > abs(d1_sp) + 0.5 else "Itapira seguiu o padrão do estado."),
        f"**{nm(PRESIDENTE, p2)} × {nm(GOVERNADOR, g2)}:** {por100(it[(PRESIDENTE, p2)])} e "
        f"{por100(it[(GOVERNADOR, g2)])} a cada 100 eleitores; diferença de {dec(abs(d2), 1)} (no estado, {dec(abs(d2_sp), 1)}).",
        f"**Senado:** {nm(SENADOR, s_top[0])} e {nm(SENADOR, s_top[1])} tiveram votações quase idênticas "
        f"({por100(it[(SENADOR, s_top[0])])} e {por100(it[(SENADOR, s_top[1])])} a cada 100 eleitores). Como as duas "
        f"somam mais de 100, **pelo menos {por100(max(0, it[(SENADOR, s_top[0])] + it[(SENADOR, s_top[1])] - 100))} "
        "a cada 100 eleitores votaram nos dois** (o número real provavelmente é bem maior). "
        f"{nm(SENADOR, s_top[2])} e {nm(SENADOR, s_top[3])} tiveram {por100(it[(SENADOR, s_top[2])])} e "
        f"{por100(it[(SENADOR, s_top[3])])}.",
        f"**Brancos e nulos crescem fora da disputa presidencial:** {por100(brancos[PRESIDENTE])} a cada 100 eleitores "
        f"para presidente, {por100(brancos[GOVERNADOR])} para governador e {por100(brancos[SENADOR])} votos para senador "
        f"(cada eleitor tinha 2 votos para o Senado). No estado: {por100(t.loc[[(PRESIDENTE, BRANCO)], 'Estado de SP'].iloc[0] + t.loc[[(PRESIDENTE, NULO)], 'Estado de SP'].iloc[0])}, "
        f"{por100(t.loc[[(GOVERNADOR, BRANCO)], 'Estado de SP'].iloc[0] + t.loc[[(GOVERNADOR, NULO)], 'Estado de SP'].iloc[0])} e "
        f"{por100(t.loc[[(SENADOR, BRANCO)], 'Estado de SP'].iloc[0] + t.loc[[(SENADOR, NULO)], 'Estado de SP'].iloc[0])}.",
    ]
    ui.resposta("O eleitor de Itapira votou do mesmo jeito para presidente, governador e senador?", texto, args)

    st.subheader("A cada 100 eleitores que votaram")
    tab = t.loc[linhas].copy()
    tab.index = [f"{CARGOS[c]} · {nome_cand(c, n)}" for c, n in linhas]
    for c in (PRESIDENTE, GOVERNADOR, SENADOR):
        tab.loc[f"{CARGOS[c]} · brancos e nulos"] = t.loc[[(c, BRANCO), (c, NULO)]].sum()
    ordem = [i for c in (PRESIDENTE, GOVERNADOR, SENADOR) for i in tab.index if i.startswith(CARGOS[c])]
    tab = tab.loc[ordem]
    tab["Itapira − estado"] = tab["Itapira"] - tab["Estado de SP"]
    tabela_progress(tab, {c: 100 for c in ["Itapira", "Cidades vizinhas", "Estado de SP"]},
                    {"Itapira − estado": COL_PP("Itapira − estado")}, indice="Cargo e candidato")
    ui.nota("Base: todas as pessoas que votaram (inclui quem votou em branco ou anulou), o que permite comparar "
            "cargos diferentes na mesma régua. Para o Senado cada eleitor tinha 2 votos, então a soma passa de 100.")

    st.subheader("Por bairro")
    vs = votos[votos["CD_CARGO"].isin([PRESIDENTE, GOVERNADOR])].assign(B=lambda d: d["NR_SECAO"].map(BAIRRO))
    base_b = vs[vs["CD_CARGO"] == GOVERNADOR].groupby("B")["QT_VOTOS"].sum()

    def col(c, n):
        return vs[(vs["CD_CARGO"] == c) & (vs["NR_VOTAVEL"] == n)].groupby("B")["QT_VOTOS"].sum() / base_b * 100

    tb = pd.DataFrame({nm(PRESIDENTE, p1): col(PRESIDENTE, p1), nm(GOVERNADOR, g1): col(GOVERNADOR, g1),
                       f"Diferença {nm(GOVERNADOR, g1)} − {nm(PRESIDENTE, p1)}": col(GOVERNADOR, g1) - col(PRESIDENTE, p1),
                       nm(PRESIDENTE, p2): col(PRESIDENTE, p2), nm(GOVERNADOR, g2): col(GOVERNADOR, g2),
                       f"Diferença {nm(GOVERNADOR, g2)} − {nm(PRESIDENTE, p2)}": col(GOVERNADOR, g2) - col(PRESIDENTE, p2)})
    dcol = tb.columns[2]
    tb = tb.sort_values(dcol, ascending=False)
    tabela_progress(tb, {c: 100 for c in tb.columns if not c.startswith("Diferença")},
                    {c: COL_PP(c) for c in tb.columns if c.startswith("Diferença")}, indice="Bairro")
    ui.nota(f"Também a cada 100 eleitores que votaram no bairro. Bairros no topo: onde {nm(GOVERNADOR, g1)} mais se "
            f"descolou de {nm(PRESIDENTE, p1)}.")

    with st.expander("Comparar outro par de candidatos"):
        ca, cb = st.columns(2)
        with ca:
            cargo_a = st.selectbox("Cargo A", [PRESIDENTE, GOVERNADOR, SENADOR], format_func=CARGOS.get, key="car_ca")
            nr_a = seletor_candidato(cargo_a, f"car_a_{cargo_a}")
        with cb:
            cargo_b = st.selectbox("Cargo B", [GOVERNADOR, SENADOR, PRESIDENTE], format_func=CARGOS.get, key="car_cb")
            nr_b = seletor_candidato(cargo_b, f"car_b_{cargo_b}")
        if (cargo_a, nr_a) == (cargo_b, nr_b):
            st.info("Escolha dois candidatos diferentes.")
            return
        par = A.por_100_eleitores(ctx, [(cargo_a, nr_a), (cargo_b, nr_b)])
        par.index = [f"{CARGOS[cargo_a]} · {nome_cand(cargo_a, nr_a)}", f"{CARGOS[cargo_b]} · {nome_cand(cargo_b, nr_b)}"]
        par.loc["Diferença (B − A)"] = par.iloc[1] - par.iloc[0]
        st.dataframe(par.round(1), width="stretch")
        dif = par.loc["Diferença (B − A)", "Itapira"]
        st.markdown(f"Em Itapira, a diferença é de **{dec(abs(dif), 1)} votos a cada 100 eleitores**: pelo menos "
                    f"~{num(round(abs(dif) / 100 * vot, -1))} pessoas votaram em "
                    f"{nome_cand(cargo_b, nr_b) if dif > 0 else nome_cand(cargo_a, nr_a)} e não em "
                    f"{nome_cand(cargo_a, nr_a) if dif > 0 else nome_cand(cargo_b, nr_b)}.")
    leitura_ia("cargos", "Voto entre cargos em Itapira (presidente, governador e senado)", args)


# ======================================================================= 5. perfil
def cap_perfil():
    c1, c2 = st.columns([1, 1.6])
    cargo = c1.selectbox("Cargo", [PRESIDENTE, GOVERNADOR, SENADOR], format_func=CARGOS.get, key="per_cargo")
    with c2:
        nr = seletor_candidato(cargo, f"per_cand_{cargo}")
    nm = curto(nome_cand(cargo, nr))

    # --- cidades: perfil e "esperado pelo perfil"
    pr = A.perfil_ref(ctx)
    ref = referencias(cargo)
    dif_sp = ref.loc["Itapira", nr] - ref.loc["Estado de SP", nr]
    esp, r2 = A.esperado_pelo_perfil(ctx, cargo, nr)
    esp["diferença"] = esp["real"] - esp["esperado"]
    regiao = esp.loc[[ITAPIRA] + ctx["vizinhas"]]
    acima_reg = (regiao["diferença"] > 0).sum()
    e_it = esp.loc[ITAPIRA]
    perfil_dif = (pr["Itapira"] - pr["Estado de SP"]).drop("Eleitores")
    maior_dif = perfil_dif.abs().idxmax()

    # --- dentro da cidade: seções com mais x menos de cada característica
    v = A.validos(votos_cargo(cargo))
    vs = v.pivot_table(index="NR_SECAO", columns="NR_VOTAVEL", values="QT_VOTOS", aggfunc="sum", fill_value=0)
    ind = A.indicadores(perfil_secao)
    linhas = []
    for nome_i, (_, alto, baixo, un) in A.INDICADORES.items():
        res, fx = A.tercos(ind[nome_i], vs, [nr])
        linhas.append({"Característica": nome_i, "alto": alto, "baixo": baixo,
                       "Seções com mais": res.loc[2, nr], "Seções com menos": res.loc[0, nr],
                       "faixa_mais": f"{fx[2][0]:.0f}–{fx[2][1]:.0f}{un}".replace(".", ","),
                       "faixa_menos": f"{fx[0][0]:.0f}–{fx[0][1]:.0f}{un}".replace(".", ",")})
    sec = pd.DataFrame(linhas).set_index("Característica")
    sec["Diferença (pontos)"] = sec["Seções com mais"] - sec["Seções com menos"]
    sec = sec.reindex(sec["Diferença (pontos)"].abs().sort_values(ascending=False).index)
    top = sec.iloc[0]
    # características que andam juntas (ex.: idade e estado civil)
    corr_ind = ind[list(A.INDICADORES)].corr()
    par_junto = corr_ind.loc[sec.index[0], sec.index[1]] if len(sec) > 1 else 0

    texto = (f"Pouco. Itapira tem um eleitorado parecido com o do estado, mas deu a {nm} "
             f"{pts(abs(dif_sp), False)} {'a mais' if dif_sp > 0 else 'a menos'}. E, dentro da cidade, seções de "
             f"perfis bem diferentes votaram de forma parecida.") if abs(top["Diferença (pontos)"]) < 6 else (
             f"Em parte. Dentro da cidade, {NOME_FRASE[sec.index[0]]} faz diferença: {pts(abs(top['Diferença (pontos)']), False)} "
             f"entre as seções com mais e com menos.")
    args = [
        f"**Perfil de Itapira × estado:** idade média de {dec(pr.loc['Idade média', 'Itapira'], 1)} anos (estado: "
        f"{dec(pr.loc['Idade média', 'Estado de SP'], 1)}), {pc(pr.loc['% com ensino superior', 'Itapira'])} com ensino "
        f"superior (estado: {pc(pr.loc['% com ensino superior', 'Estado de SP'])}). A maior diferença é em "
        f"{maior_dif.lower()}: {pc(pr.loc[maior_dif, 'Itapira'])} contra {pc(pr.loc[maior_dif, 'Estado de SP'])}.",
        f"**Se o perfil decidisse o voto:** usando idade, escolaridade e sexo dos 645 municípios paulistas, o "
        f"resultado esperado para {nm} em Itapira seria **{pc(e_it['esperado'])}**. O real foi **{pc(e_it['real'])}** "
        f"({pts(e_it['diferença'])}).",
        f"**É um efeito da região:** em {acima_reg} das {len(regiao)} cidades da região (Itapira e as 16 vizinhas), "
        f"{nm} ficou {'acima' if regiao['diferença'].mean() > 0 else 'abaixo'} do esperado pelo perfil, em média "
        f"{pts(abs(regiao['diferença'].mean()), False)}. O que mais se parece com o voto de Itapira é o voto dos vizinhos, "
        "não o perfil dos eleitores.",
        f"**O perfil explica pouco também no estado:** as três características juntas dão conta de só "
        f"{pc(r2 * 100, 0)} das diferenças de voto entre os municípios paulistas.",
        f"**Dentro de Itapira:** a maior diferença aparece em {sec.index[0].lower()}. Nas seções com "
        f"{top['alto']} ({top['faixa_mais']}), {nm} teve **{pc(top['Seções com mais'])}**; nas com {top['baixo']} "
        f"({top['faixa_menos']}), **{pc(top['Seções com menos'])}**.",
    ]
    if abs(par_junto) >= .5:
        args.append(f"**Cuidado:** {sec.index[0].lower()} e {sec.index[1].lower()} andam juntos nas seções "
                    f"(correlação {dec(par_junto)}), então não dá para dizer qual dos dois pesa mais.")
    args.append("**Limitação:** o perfil é dos eleitores aptos, e a comparação é entre lugares (seções e cidades), "
                "não entre pessoas. Não dá para concluir que \"os mais velhos votaram em X\".")
    ui.resposta(f"O perfil do eleitorado explica o voto em {nm}?", texto, args)

    st.subheader("Quem é o eleitor de Itapira")
    t = pr.drop("Eleitores").copy()
    t["Itapira − estado"] = t["Itapira"] - t["Estado de SP"]
    idade = t.loc[["Idade média"]]
    st.dataframe(
        t.drop("Idade média").rename_axis("Característica").reset_index(), hide_index=True, width="stretch",
        column_config={c: st.column_config.ProgressColumn(c, format="%.1f%%", min_value=0, max_value=60)
                       for c in ["Itapira", "Cidades vizinhas", "Estado de SP"]}
        | {"Itapira − estado": COL_PP("Itapira − estado (pontos)")})
    ui.nota(f"Idade média: {dec(idade['Itapira'].iloc[0], 1)} anos em Itapira, {dec(idade['Cidades vizinhas'].iloc[0], 1)} "
            f"nas vizinhas e {dec(idade['Estado de SP'].iloc[0], 1)} no estado. Perfil dos eleitores aptos (TSE, julho de 2026).")

    st.subheader(f"Resultado real × esperado pelo perfil: {nm}")
    rg = regiao.copy()
    rg.index = [A.nome(ctx["mun"].loc[c, "NM_MUNICIPIO"]) for c in rg.index]
    rg = rg.sort_values("diferença")
    fig = go.Figure()
    for cid, r in rg.iterrows():
        fig.add_shape(type="line", x0=r["esperado"], x1=r["real"], y0=cid, y1=cid, layer="below",
                      line=dict(color=CINZA_CLARO, width=3))
    fig.add_trace(go.Scatter(x=rg["esperado"], y=rg.index, mode="markers", name="Esperado pelo perfil",
                             marker=dict(size=11, color=FUNDO, line=dict(width=2.5, color=OUTROS)),
                             hovertemplate="<b>%{y}</b><br>esperado: %{x:.1f}%<extra></extra>"))
    fig.add_trace(go.Scatter(x=rg["real"], y=rg.index, mode="markers+text", name="Resultado real",
                             marker=dict(size=12, color=[MARINHO if c == "Itapira" else AZUL for c in rg.index],
                                         line=dict(width=2, color=FUNDO)),
                             text=[pts(x).replace(" pontos", "").replace(" ponto", "") for x in rg["diferença"]],
                             textposition="middle right", cliponaxis=False,
                             hovertemplate="<b>%{y}</b><br>real: %{x:.1f}%<extra></extra>"))
    fig.update_yaxes(type="category")
    fig.update_layout(height=26 * len(rg) + 110, margin=dict(l=10, r=40, t=30, b=10),
                      xaxis_title=f"% dos votos válidos de {nm}", legend=dict(orientation="h", y=1.06, x=0))
    ui.mostrar(fig)
    ui.nota("Círculo vazio: o resultado que o perfil do eleitorado (idade, escolaridade, sexo) indicaria, calculado "
            "com os 645 municípios de SP. Círculo cheio: o resultado real. O número é a diferença. Quando quase "
            "todas as cidades da região ficam do mesmo lado, o motivo é regional, não o perfil.")

    st.subheader("Dentro de Itapira: seções com mais × com menos de cada característica")
    tsec = sec[["faixa_mais", "Seções com mais", "faixa_menos", "Seções com menos", "Diferença (pontos)"]].rename(
        columns={"faixa_mais": "Faixa (mais)", "faixa_menos": "Faixa (menos)",
                 "Seções com mais": f"{nm}: seções com mais", "Seções com menos": f"{nm}: seções com menos"})
    teto = float(sec[["Seções com mais", "Seções com menos"]].max().max()) * 1.05
    tabela_progress(tsec, {f"{nm}: seções com mais": teto, f"{nm}: seções com menos": teto},
                    {"Diferença (pontos)": COL_PP("Diferença (pontos)")}, indice="Característica")
    ui.nota("Para cada característica, as 161 seções foram ordenadas e divididas em três grupos iguais. A tabela "
            "compara o terço com mais com o terço com menos. Diferenças de 1 a 3 pontos são pequenas: indicam voto "
            "parecido em perfis diferentes.")

    with st.expander("Perfil e voto de cada bairro"):
        pb = A.indicadores(perfil_secao.groupby(BAIRRO).sum())
        vb = A.pct_por(v.assign(B=v["NR_SECAO"].map(BAIRRO)), "B")[nr]
        tb = pb[["Idade média", "% com 60 anos ou mais", "% com ensino superior", "Eleitores"]].join(vb.rename(f"% {nm}"))
        tb = tb.sort_values(f"% {nm}", ascending=False)
        tabela_progress(tb, {f"% {nm}": 100, "% com 60 anos ou mais": 50, "% com ensino superior": 50},
                        {"Idade média": st.column_config.NumberColumn(format="%.1f"), "Eleitores": COL_NUM("Eleitores")},
                        indice="Bairro")
    leitura_ia(f"per_{cargo}_{nr}", f"{CARGOS[cargo]}: o perfil do eleitorado explica o voto em {nome_cand(cargo, nr)}?", args)


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
    viz = sorted(ctx["mun"].loc[ctx["vizinhas"], "NM_MUNICIPIO"].map(A.nome))
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
- **Comparecimento**: votos dados divididos pelos eleitores aptos. Para Itapira, os aptos de cada seção vêm do
  boletim de urna (o número oficial do dia da eleição); nas comparações entre municípios, do cadastro de locais de
  votação do TSE, que é a mesma fonte para todas as cidades (diferença de ~0,1 ponto).
- **2º turno**: votos de cada seção lidos dos boletins de urna publicados pelo TSE em resultados.tse.jus.br.
  A leitura foi conferida contra o 1º turno (23.230 números, todos iguais ao arquivo oficial) e a soma das seções
  bate com o total oficial do município.
- **Transferência de votos**: estimativa estatística (inferência ecológica) feita com a variação entre as 161
  seções; não é uma contagem, porque o voto é secreto.
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


for aba, cap in zip(abas, [cap_2turno, cap_resumo, cap_geografia, cap_mudanca, cap_cargos, cap_perfil, cap_deputados,
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
