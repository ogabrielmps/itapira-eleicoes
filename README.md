# Elections Analyzer · Itapira

Votação das Eleições 2026 (1º turno) em Itapira-SP (Zona 0054, 161 seções, 22 locais)
agrupada por bairro, local de votação ou seção, com comparação com 2022 e análises em texto por IA.

## Como usar

```bash
pip install -r requirements.txt
python etl/preparar_dados.py   # baixa do TSE (~1,6 GB) e gera data/itapira/
python etl/preparar_2022.py    # Presidente 2022 (1º e 2º turno), para a aba 2022 × 2026
streamlit run app/app.py
```

## Análises por IA

Cada aba tem um bloco "O que os números dizem". O painel calcula os fatos (quem venceu, maiores e
menores resultados, variações) e o Claude (`claude-opus-5-5`) os transforma em conclusões curtas.

- Defina `ANTHROPIC_API_KEY` nos Secrets do Streamlit Cloud (ou como variável de ambiente local).
- Sem a chave, o bloco mostra só os fatos calculados.
- As respostas ficam em cache por combinação de filtros (`.cache_insights/`), então cada
  combinação gera no máximo uma chamada.

## Fontes (TSE Dados Abertos)

- `votacao_secao_2026_SP.zip` / `_BR.zip` – votos por seção (BR traz Presidente)
- `eleitorado_local_votacao_2026.zip` – seção → local de votação → endereço, bairro, lat/long
- `perfil_eleitor_secao_2026_SP.zip` – eleitores aptos por seção × idade, gênero, escolaridade,
  estado civil (raça/cor existe mas ~88% "não informado" em Itapira, por isso não é usada)
- `votacao_secao_2022_BR.zip` / `eleitorado_local_votacao_2022.zip` – Presidente 2022

## Bairros

`mapping/bairros.csv` tem um local de votação por linha. Edite à vontade:

- `BAIRRO` – nome usado no painel (vem do TSE, normalizado)
- `NR_LATITUDE` / `NR_LONGITUDE` – corrija se algum ponto estiver errado no mapa

O ETL nunca sobrescreve esse arquivo.

Observação: o bairro é o do **local de votação**, não o endereço do eleitor.
