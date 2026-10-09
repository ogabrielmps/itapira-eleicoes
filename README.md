# Elections Analyzer · Itapira

Votação das Eleições 2026 (1º turno) em Itapira-SP (Zona 0054, 161 seções, 22 locais)
analisada por bairro e comparada com 16 cidades vizinhas, o estado de SP, o Brasil e a eleição de 2022.

## Como usar

```bash
pip install -r requirements.txt
python etl/preparar_dados.py   # baixa do TSE (~1,6 GB) e gera data/itapira/
python etl/preparar_2022.py    # Presidente 2022 (1º e 2º turno), seção a seção
python etl/preparar_contexto.py  # totais por município (SP e Brasil) e cadastro de candidaturas
streamlit run app/app.py
```

## Como a análise é organizada

Cada capítulo responde a uma pergunta: resposta curta, argumentos com números e, por fim, a
evidência (tabelas e poucos gráficos). As comparações usam 16 cidades vizinhas, o estado de SP,
o Brasil e a eleição de 2022.

| Capítulo | Pergunta |
|---|---|
| Resumo | Itapira votou diferente do estado e do país? |
| Onde cada um é forte | Em que bairros cada candidato foi melhor ou pior? |
| 2022 → 2026 | Itapira acompanhou o movimento do estado? |
| Voto entre cargos | Quem votou em X também votou em Y? |
| Perfil e voto | Idade, escolaridade etc. explicam o voto? |
| Deputados | Quem Itapira escolheu, e quem depende de Itapira? |
| Comparecimento | Itapira foi mais às urnas? |
| Metodologia | Fontes, definições e limitações |

Código: `app/analise.py` (cálculos), `app/ui.py` (visual), `app/app.py` (capítulos),
`app/insights.py` (leitura por IA).

Tema escuro por padrão, com botão no topo para alternar para o claro (cores em `.streamlit/config.toml`
e nos tokens de `app/ui.py`).

## Análises por IA

Com uma chave de API, cada capítulo ganha um bloco "Leitura por IA": o Claude (`claude-opus-5-5`)
reescreve em texto corrido os argumentos que o painel já calculou.

- Defina `ANTHROPIC_API_KEY` nos Secrets do Streamlit Cloud (ou como variável de ambiente local).
- Sem a chave, o painel funciona igual; só não mostra esse bloco.
- As respostas ficam em cache por combinação de filtros (`.cache_insights/`), então cada
  combinação gera no máximo uma chamada.

## Fontes (TSE Dados Abertos)

- `votacao_secao_2026_SP.zip` / `_BR.zip` – votos por seção (BR traz Presidente)
- `eleitorado_local_votacao_2026.zip` – seção → local de votação → endereço, bairro, lat/long
- `perfil_eleitor_secao_2026_SP.zip` – eleitores aptos por seção × idade, gênero, escolaridade,
  estado civil (raça/cor existe mas ~88% "não informado" em Itapira, por isso não é usada)
- `votacao_secao_2022_BR.zip` / `eleitorado_local_votacao_2022.zip` – Presidente 2022
- `consulta_cand_2026.zip` – nome de urna, partido e situação (eleito, 2º turno…) dos candidatos

## Bairros

`mapping/bairros.csv` tem um local de votação por linha. Edite à vontade:

- `BAIRRO` – nome usado no painel (vem do TSE, normalizado)
- `NR_LATITUDE` / `NR_LONGITUDE` – corrija se algum ponto estiver errado no mapa

O ETL nunca sobrescreve esse arquivo.

Observação: o bairro é o do **local de votação**, não o endereço do eleitor.

## Manter o app acordado

O Streamlit Community Cloud gratuito põe o app para dormir depois de um tempo sem visitas.
O workflow `.github/workflows/manter-acordado.yml` abre o painel a cada 6 horas com um navegador sem
tela (`scripts/manter_acordado.py`) e, se ele estiver dormindo, clica em "Yes, get this app back up!".
O GitHub desativa agendamentos após 60 dias sem commits no repositório; se isso acontecer, reative
na aba Actions.
