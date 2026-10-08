"""Identidade visual e componentes de página (cabeçalho, cartões, respostas), em tema claro e escuro.

O tema nativo do Streamlit (widgets, tabelas, gráficos) vem de .streamlit/config.toml; o CSS próprio
abaixo usa os mesmos tokens. `estilo(escuro)` define as cores do tema atual e injeta o CSS.
"""
import html
import json

import plotly.graph_objects as go
import streamlit as st
import streamlit.components.v1 as components

AMARELO = "#f6b500"

# tokens por tema (séries categóricas validadas para daltonismo em cada fundo)
TEMAS = {
    "claro": dict(
        series=["#1565d8", "#eb6834", "#1baf7a"], outros="#8a93a6", neutro="#c5cfdf",
        destaque="#0b2557", azul="#1565d8", fundo="#f2f5fa", cartao="#ffffff", texto="#0b2557",
        texto2="#24365e", suave="#5a6b8c", borda="#d5deeb", titulo="#0b2557", ano="#1565d8",
        pergunta="#1565d8", insight="#f7f9fd", insight_borda="#b9c7e0", rodape="#0b2557",
        rodape_txt="#cfd9ee", sombra="rgba(11,37,87,.08)",
    ),
    "escuro": dict(
        series=["#3987e5", "#d95926", "#199e70"], outros="#8a93a6", neutro="#2f3e5c",
        destaque=AMARELO, azul="#4d94ff", fundo="#0b1220", cartao="#121c31", texto="#e6ecf7",
        texto2="#c9d4ea", suave="#9fb0cf", borda="#24324f", titulo="#ffffff", ano="#4d94ff",
        pergunta="#6ea8ff", insight="#0f1a2e", insight_borda="#2a3a5c", rodape="#070c17",
        rodape_txt="#9fb0cf", sombra="rgba(0,0,0,.35)",
    ),
}
SEQ = ["#dce8fa", "#9ec5f4", "#5598e7", "#1c5cab", "#0b2557"]  # mapa (fundo do mapa é sempre claro)

# valores do tema atual (definidos em estilo())
T = TEMAS["escuro"]
SERIES, OUTROS, CINZA_CLARO, DESTAQUE, AZUL, FUNDO = (T["series"], T["outros"], T["neutro"], T["destaque"],
                                                      T["azul"], T["cartao"])


def _css(t: dict) -> str:
    return f"""
<style>
.block-container {{ padding-top: 3.2rem; max-width: 1200px; }}
h1, h2, h3 {{ text-transform: uppercase; letter-spacing: .01em; }}
h3 {{ font-size: 1.45rem !important; }}
h3::after {{ content: ""; display: block; width: 56px; height: 5px; margin-top: 6px;
            background: {AMARELO}; border-radius: 3px; }}

.in-hero {{ display: grid; grid-template-columns: 1fr 1.25fr; gap: 1.25rem; align-items: stretch;
           margin-bottom: 1.25rem; }}
.in-hero .marca {{ padding: .5rem 0; }}
.in-hero .eleicoes {{ font-family: "Barlow Condensed", sans-serif; font-weight: 900; line-height: .85;
                     font-size: clamp(2.6rem, 6vw, 4.6rem); color: {t['titulo']}; }}
.in-hero .ano {{ color: {t['ano']}; }}
.in-hero .barra {{ width: 42%; height: 8px; background: {AMARELO}; border-radius: 4px; margin: .8rem 0 .6rem; }}
.in-hero .local {{ font-weight: 700; color: {t['titulo']}; font-size: 1.05rem; letter-spacing: .02em; }}
.in-hero .local span {{ font-weight: 500; opacity: .75; }}
.in-hero .caixa {{ background: linear-gradient(135deg, #0b2557 0%, #12398a 100%); color: #fff;
                  border-radius: 14px; padding: 1.2rem 1.5rem; display: flex; flex-direction: column;
                  justify-content: center; box-shadow: 0 8px 24px {t['sombra']};
                  border: 1px solid {t['borda']};
                  font-family: "Barlow Condensed", sans-serif; text-transform: uppercase; line-height: 1; }}
.in-hero .caixa .linha {{ font-weight: 800; font-size: clamp(1.2rem, 2.2vw, 1.8rem); }}
.in-hero .caixa .destaque {{ font-weight: 900; color: {AMARELO}; font-size: clamp(2rem, 4.2vw, 3.4rem); }}
@media (max-width: 760px) {{ .in-hero {{ grid-template-columns: 1fr; }} }}

.in-kpis {{ display: grid; grid-template-columns: repeat(4, 1fr); gap: .9rem; margin: .4rem 0 1.2rem; }}
@media (max-width: 900px) {{ .in-kpis {{ grid-template-columns: repeat(2, 1fr); }} }}
.in-kpi {{ background: {t['cartao']}; border-radius: 12px; padding: .9rem 1.1rem; border-left: 6px solid {t['azul']};
          box-shadow: 0 2px 10px {t['sombra']}; }}
.in-kpi .rotulo {{ font-size: .78rem; font-weight: 700; text-transform: uppercase; letter-spacing: .04em;
                  color: {t['suave']}; }}
.in-kpi .valor {{ font-family: "Barlow Condensed", sans-serif; font-weight: 800; font-size: 2.1rem;
                 color: {t['titulo']}; line-height: 1.1; }}
.in-kpi .apoio {{ font-size: .85rem; font-weight: 600; color: {t['suave']}; margin-top: .15rem; }}

.in-resposta {{ background: {t['cartao']}; border-radius: 14px; padding: 1.3rem 1.6rem 1.1rem;
               margin: .4rem 0 1.4rem; border-top: 6px solid {AMARELO}; box-shadow: 0 2px 14px {t['sombra']}; }}
.in-resposta .pergunta {{ font-size: .82rem; font-weight: 800; text-transform: uppercase; letter-spacing: .06em;
                         color: {t['pergunta']}; margin-bottom: .35rem; }}
.in-resposta .texto {{ font-family: "Barlow Condensed", sans-serif; font-weight: 800; color: {t['titulo']};
                      font-size: clamp(1.45rem, 2.6vw, 2.05rem); line-height: 1.15; }}
.in-resposta ul {{ margin: .9rem 0 0; padding-left: 1.1rem; color: {t['texto2']}; }}
.in-resposta li {{ margin-bottom: .4rem; line-height: 1.45; }}
.in-resposta b {{ color: {t['titulo']}; }}

.in-nota {{ font-size: .85rem; color: {t['suave']}; border-left: 3px solid {t['borda']}; padding: .2rem .8rem;
           margin: .2rem 0 1rem; }}
.in-nota b {{ color: {t['texto2']}; }}

[data-testid="stTab"] p {{ font-family: "Barlow Condensed", sans-serif; font-weight: 800;
                          text-transform: uppercase; font-size: 1.05rem; letter-spacing: .02em; }}
[data-testid="stTab"][aria-selected="true"] p {{ color: {t['titulo']}; }}
[role="tablist"] .react-aria-SelectionIndicator {{ background-color: {AMARELO} !important; height: 4px; }}

[class*="st-key-insight"] {{ background: {t['insight']}; border-radius: 14px; border: 1px dashed {t['insight_borda']};
                            padding: .9rem 1.3rem .5rem; margin: .4rem 0 1.4rem; }}
[class*="st-key-insight"] .in-insight-titulo {{ font-family: "Barlow Condensed", sans-serif; font-weight: 800;
                            text-transform: uppercase; font-size: 1.15rem; color: {t['titulo']}; }}

.in-rodape {{ margin-top: 2.5rem; padding: 1rem 1.25rem; border-radius: 12px; background: {t['rodape']};
             color: {t['rodape_txt']}; font-size: .85rem; border: 1px solid {t['borda']}; }}
.in-rodape b {{ color: #fff; }}
</style>
"""


def estilo(escuro: bool):
    """Define as cores do tema atual e injeta o CSS da página."""
    global T, SERIES, OUTROS, CINZA_CLARO, DESTAQUE, AZUL, FUNDO
    T = TEMAS["escuro" if escuro else "claro"]
    SERIES, OUTROS, CINZA_CLARO, DESTAQUE, AZUL, FUNDO = (T["series"], T["outros"], T["neutro"], T["destaque"],
                                                          T["azul"], T["cartao"])
    st.markdown(_css(T), unsafe_allow_html=True)


def botao_tema(escuro: bool):
    """Botão que alterna claro/escuro.

    O Streamlit guarda a escolha de tema do visitante no localStorage do navegador; o botão grava a
    escolha oposta e recarrega a página. Na primeira visita (sem escolha salva), fixa o escuro."""
    rotulo = "☀️ Modo claro" if escuro else "🌙 Modo escuro"
    proximo = "Light" if escuro else "Dark"
    t = T
    components.html(f"""
<style>
  body {{ margin: 0; display: flex; justify-content: flex-end; font-family: "Barlow", system-ui, sans-serif; }}
  button {{ background: {t['cartao']}; color: {t['titulo']}; border: 1px solid {t['borda']}; border-radius: 999px;
           padding: 6px 16px; font-size: 14px; font-weight: 700; cursor: pointer; }}
  button:hover {{ border-color: {AMARELO}; }}
</style>
<button id="b">{rotulo}</button>
<script>
  const P = window.parent, K = "stActiveTheme-" + P.location.pathname + "-v2";
  let salvo = null;
  try {{ salvo = JSON.parse(P.localStorage.getItem(K)); }} catch (e) {{}}
  if (!salvo || salvo === "System") {{
    P.localStorage.setItem(K, JSON.stringify("Dark"));
    if (!{json.dumps(escuro)}) P.location.reload();
  }}
  document.getElementById("b").onclick = () => {{
    P.localStorage.setItem(K, JSON.stringify({json.dumps(proximo)}));
    P.location.reload();
  }};
</script>""", height=40)


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
               and (t.type == "scatter" or getattr(t, "orientation", None) == "h")
               for y in t.y if isinstance(y, str)]
    if rotulos:
        fig.update_layout(margin_l=max(fig.layout.margin.l or 0, 7 * max(map(len, rotulos)) + 10))
    if altura:
        fig.update_layout(height=altura)
    # legenda horizontal com largura fixa por item (a fonte carrega depois e os itens se sobrepunham)
    fig.update_layout(legend=dict(entrywidth=190, entrywidthmode="pixels"))
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
