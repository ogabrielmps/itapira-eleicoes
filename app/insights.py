"""
Análises em texto geradas pelo Claude a partir de fatos já calculados pelo painel.

O painel calcula os números (quem venceu, maiores/menores, variações) e o modelo só os
transforma em conclusões curtas e legíveis. Sem chave de API, o painel mostra os fatos crus.

As respostas ficam em cache (memória + disco) pela combinação exata de fatos, então cada
combinação de filtros só gera uma chamada, compartilhada por todos os visitantes.
"""
import hashlib
import json
import threading
from concurrent.futures import Future, ThreadPoolExecutor
from pathlib import Path

import anthropic

MODELO = "claude-opus-5-5"
CACHE_DIR = Path(__file__).resolve().parent.parent / ".cache_insights"

SISTEMA = """Você escreve análises curtas de resultados eleitorais para o público geral de \
Itapira (SP), uma cidade de cerca de 70 mil habitantes. O leitor não é especialista em \
estatística: quer saber o que aconteceu e onde, em linguagem simples.

Você recebe fatos já calculados a partir dos dados oficiais do TSE e, às vezes, uma tabela. \
Escreva de 3 a 5 tópicos em Markdown (lista com "- "), cada um com uma conclusão concreta e \
os números que a sustentam (use **negrito** nos números-chave). Prefira comparações claras \
("10 pontos acima da média da cidade", "venceu em 18 de 20 bairros") a jargão.

Regras:
- Use somente os números fornecidos; não invente dados nem faça contas que não estejam nos fatos.
- Tom jornalístico e neutro: não opine sobre candidatos, partidos ou eleitores, e não especule \
sobre causas.
- Quando os fatos mencionarem uma limitação (por exemplo, bairro do local de votação, perfil de \
eleitores aptos, comparação entre seções e não entre pessoas), respeite-a e não tire \
conclusões que ela impede.
- Escreva em português do Brasil, com vírgula decimal. Responda apenas com os tópicos, sem \
título nem introdução."""

_executor = ThreadPoolExecutor(max_workers=6)
_futuros: dict[str, Future] = {}  # chave -> pedido em andamento ou concluído
_trava = threading.Lock()


def _chave(titulo: str, fatos: list[str], tabela: str) -> str:
    bruto = json.dumps([MODELO, SISTEMA, titulo, fatos, tabela], ensure_ascii=False)
    return hashlib.sha256(bruto.encode()).hexdigest()[:32]


def _gerar(api_key: str, chave: str, titulo: str, fatos: list[str], tabela: str) -> str | None:
    arquivo = CACHE_DIR / f"{chave}.json"
    if arquivo.exists():
        return json.loads(arquivo.read_text(encoding="utf-8"))["texto"]

    conteudo = f"Assunto: {titulo}\n\nFatos:\n" + "\n".join(f"- {f}" for f in fatos)
    if tabela:
        conteudo += f"\n\nTabela (CSV, separador ;):\n{tabela}"
    client = anthropic.Anthropic(api_key=api_key, timeout=120.0, max_retries=1)
    try:
        resp = client.beta.messages.create(
            model=MODELO,
            max_tokens=8000,
            system=SISTEMA,
            output_config={"effort": "medium"},
            # se o modelo recusar por engano, a API refaz o pedido num modelo alternativo
            betas=["server-side-fallback-2026-07-01"],
            fallbacks="default",
            messages=[{"role": "user", "content": conteudo}],
        )
    except anthropic.APIError:
        return None
    if resp.stop_reason == "refusal":
        return None
    texto = "".join(b.text for b in resp.content if b.type == "text").strip()
    if not texto:
        return None
    CACHE_DIR.mkdir(exist_ok=True)
    arquivo.write_text(json.dumps({"titulo": titulo, "texto": texto}, ensure_ascii=False),
                       encoding="utf-8")
    return texto


def pedir(api_key: str | None, titulo: str, fatos: list[str], tabela: str = "") -> Future | None:
    """Agenda a geração (em paralelo) e devolve um Future com o texto, ou None sem chave."""
    if not api_key or not fatos:
        return None
    chave = _chave(titulo, fatos, tabela)
    with _trava:
        f = _futuros.get(chave)
        # reaproveita o pedido em andamento ou o texto já pronto; refaz só se o anterior falhou
        if f is None or (f.done() and (f.exception() or f.result() is None)):
            f = _executor.submit(_gerar, api_key, chave, titulo, fatos, tabela)
            _futuros[chave] = f
        return f
