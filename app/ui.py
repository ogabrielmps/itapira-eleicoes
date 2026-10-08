"""Identidade visual e componentes de página (cabeçalho, cartões, respostas)."""
import html

import plotly.graph_objects as go
import streamlit as st

# Paleta categórica (ordem fixa, validada para daltonismo nas 3 primeiras posições)
SERIES = ["#1565d8", "#eb6834", "#1baf7a"]
OUTROS = "#8a93a6"
CINZA_CLARO = "#c5cfdf"
SEQ = ["#dce8fa", "#9ec5f4", "#5598e7", "#1c5cab", "#0b2557"]
MARINHO, AZUL, AMARELO = "#0b2557", "#1565d8", "#f6b500"

CSS = f"""
<style>
.block-container {{ padding-top: 4rem; max-width: 1200px; }}
h1, h2, h3 {{ text-transform: uppercase; letter-spacing: .01em; }}
h3 {{ font-size: 1.45rem !important; }}
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

.in-kpis {{ display: grid; grid-template-columns: repeat(auto-fit, minmax(190px, 1fr)); gap: .9rem;
           margin: .4rem 0 1.2rem; }}
.in-kpi {{ background: #fff; border-radius: 12px; padding: .9rem 1.1rem; border-left: 6px solid {AZUL};
          box-shadow: 0 2px 10px rgba(11,37,87,.07); }}
.in-kpi .rotulo {{ font-size: .78rem; font-weight: 700; text-transform: uppercase; letter-spacing: .04em;
                  color: #5a6b8c; }}
.in-kpi .valor {{ font-family: "Barlow Condensed", sans-serif; font-weight: 800; font-size: 2.1rem;
                 color: {MARINHO}; line-height: 1.1; }}
.in-kpi .apoio {{ font-size: .85rem; font-weight: 600; color: #5a6b8c; margin-top: .15rem; }}

.in-resposta {{ background: #fff; border-radius: 14px; padding: 1.3rem 1.6rem 1.1rem; margin: .4rem 0 1.4rem;
               border-top: 6px solid {AMARELO}; box-shadow: 0 2px 14px rgba(11,37,87,.09); }}
.in-resposta .pergunta {{ font-size: .82rem; font-weight: 800; text-transform: uppercase; letter-spacing: .06em;
                         color: {AZUL}; margin-bottom: .35rem; }}
.in-resposta .texto {{ font-family: "Barlow Condensed", sans-serif; font-weight: 800; color: {MARINHO};
                      font-size: clamp(1.45rem, 2.6vw, 2.05rem); line-height: 1.15; }}
.in-resposta ul {{ margin: .9rem 0 0; padding-left: 1.1rem; color: #24365e; }}
.in-resposta li {{ margin-bottom: .4rem; line-height: 1.45; }}
.in-resposta b {{ color: {MARINHO}; }}

.in-nota {{ font-size: .85rem; color: #5a6b8c; border-left: 3px solid {CINZA_CLARO}; padding: .2rem .8rem;
           margin: .2rem 0 1rem; }}

[data-testid="stTab"] p {{ font-family: "Barlow Condensed", sans-serif; font-weight: 800;
                          text-transform: uppercase; font-size: 1.05rem; letter-spacing: .02em; }}
[data-testid="stTab"][aria-selected="true"] p {{ color: {MARINHO}; }}
[role="tablist"] .react-aria-SelectionIndicator {{ background-color: {AMARELO} !important; height: 4px; }}

[class*="st-key-insight"] {{ background: #f7f9fd; border-radius: 14px; border: 1px dashed #b9c7e0;
                            padding: .9rem 1.3rem .5rem; margin: .4rem 0 1.4rem; }}
[class*="st-key-insight"] .in-insight-titulo {{ font-family: "Barlow Condensed", sans-serif; font-weight: 800;
                            text-transform: uppercase; font-size: 1.15rem; color: {MARINHO}; }}

.in-rodape {{ margin-top: 2.5rem; padding: 1rem 1.25rem; border-radius: 12px; background: {MARINHO};
             color: #cfd9ee; font-size: .85rem; }}
.in-rodape b {{ color: #fff; }}
</style>
"""


def estilo():
    st.markdown(CSS, unsafe_allow_html=True)


def hero(destaque: str, linha_cima: str, linha_baixo: str = ""):
    st.markdown(f"""
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


def kpis(itens: list[tuple]):
    """Cartões (rótulo, valor) ou (rótulo, valor, linha de apoio)."""
    cards = "".join(
        f'<div class="in-kpi"><div class="rotulo">{i[0]}</div><div class="valor">{i[1]}</div>'
        + (f'<div class="apoio">{i[2]}</div>' if len(i) > 2 else "") + "</div>"
        for i in itens)
    st.markdown(f'<div class="in-kpis">{cards}</div>', unsafe_allow_html=True)


def _md_negrito(t: str) -> str:
    """Escapa HTML e converte **x** em <b>x</b> (para textos montados pelo código)."""
    partes = html.escape(t).split("**")
    return "".join(f"<b>{p}</b>" if i % 2 else p for i, p in enumerate(partes))


def resposta(pergunta: str, texto: str, argumentos: list[str]):
    """Pergunta -> resposta curta em destaque -> argumentos com números."""
    itens = "".join(f"<li>{_md_negrito(a)}</li>" for a in argumentos)
    st.markdown(f'<div class="in-resposta"><div class="pergunta">{html.escape(pergunta)}</div>'
                f'<div class="texto">{_md_negrito(texto)}</div><ul>{itens}</ul></div>',
                unsafe_allow_html=True)


def nota(texto: str):
    st.markdown(f'<div class="in-nota">{_md_negrito(texto)}</div>', unsafe_allow_html=True)


def mostrar(fig, altura: int | None = None):
    """Plotly com margem esquerda pelo maior rótulo (nomes longos de bairro não cortam)."""
    rotulos = [str(y) for t in fig.data if getattr(t, "y", None) is not None
               and t.type in ("bar", "scatter") and getattr(t, "orientation", None) == "h"
               for y in t.y if isinstance(y, str)]
    if rotulos:
        fig.update_layout(margin_l=max(fig.layout.margin.l or 0, 7 * max(map(len, rotulos)) + 10))
    if altura:
        fig.update_layout(height=altura)
    st.plotly_chart(fig, width="stretch", config={"displayModeBar": False})


def barras_h(valores, rotulos_y, cores, textos, hover: str, titulo_x: str, linha: float | None = None,
             rotulo_linha: str = "", custom=None, faixa=None):
    """Barras horizontais com o valor escrito na ponta e uma linha de referência opcional."""
    fig = go.Figure(go.Bar(
        x=list(valores), y=[str(r) for r in rotulos_y], orientation="h",
        marker=dict(color=cores, cornerradius=4), text=textos, textposition="outside",
        cliponaxis=False, customdata=custom, hovertemplate=hover,
    ))
    if linha is not None:
        fig.add_vline(x=linha, line_dash="dot", line_color=OUTROS,
                      annotation_text=rotulo_linha, annotation_position="top")
    if faixa is None:
        lo, hi = min(0, min(valores)), max(0, max(valores))
        maior = max((len(str(t)) for t in textos), default=6)
        folga = (hi - lo) * (0.12 + 0.02 * maior)
        faixa = [lo - folga if lo < 0 else 0, hi + folga if hi > 0 else 0]
    fig.update_xaxes(range=faixa, title=titulo_x)
    fig.update_yaxes(type="category")
    fig.update_layout(height=max(300, 26 * len(rotulos_y) + 90), margin=dict(l=10, r=30, t=40, b=10),
                      bargap=0.28, showlegend=False)
    mostrar(fig)


def cor_seq(x: float, lo: float, hi: float) -> str:
    """Cor da rampa sequencial (azul claro -> marinho) para x entre lo e hi."""
    t = 0.0 if hi <= lo else min(1.0, max(0.0, (x - lo) / (hi - lo)))
    i = t * (len(SEQ) - 1)
    a, b = SEQ[int(i)], SEQ[min(int(i) + 1, len(SEQ) - 1)]
    f = i - int(i)
    ca = [int(a[k:k + 2], 16) for k in (1, 3, 5)]
    cb = [int(b[k:k + 2], 16) for k in (1, 3, 5)]
    return "#" + "".join(f"{round(ca[k] + (cb[k] - ca[k]) * f):02x}" for k in range(3))
