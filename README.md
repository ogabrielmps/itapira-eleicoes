# Elections Analyzer · Itapira

Votação das Eleições 2026 (1º turno) em Itapira-SP (Zona 0054, 161 seções, 22 locais)
agrupada por bairro, região, local de votação ou seção.

## Como usar

```bash
pip install -r requirements.txt
python etl/preparar_dados.py   # baixa do TSE (~1 GB) e gera data/itapira/
streamlit run app/app.py
```

## Fontes (TSE Dados Abertos)

- `votacao_secao_2026_SP.zip` / `_BR.zip` – votos por seção (BR traz Presidente)
- `eleitorado_local_votacao_2026.zip` – seção → local de votação → endereço, bairro, lat/long
- `perfil_eleitor_secao_2026_SP.zip` – eleitores aptos por seção × idade, gênero, escolaridade,
  estado civil (raça/cor existe mas ~88% "não informado" em Itapira, por isso não é usada)

## Bairros e regiões

`mapping/bairros.csv` tem um local de votação por linha. Edite à vontade:

- `BAIRRO` – nome usado no painel (vem do TSE, normalizado)
- `REGIAO` – agrupamento livre (ex.: "Zona Norte", "Rural"); vazio = usa o bairro
- `NR_LATITUDE` / `NR_LONGITUDE` – corrija se algum ponto estiver errado no mapa

O ETL nunca sobrescreve esse arquivo.

Observação: o bairro é o do **local de votação**, não o endereço do eleitor.
