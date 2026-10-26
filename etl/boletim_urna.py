"""
Leitor mínimo de boletins de urna (arquivos -bu.dat do TSE, codificados em ASN.1/BER).

Não depende da especificação: percorre a árvore TLV (tag-tamanho-valor) e extrai os blocos de
votos por votável. A interpretação foi validada contra os votos oficiais por seção do 1º turno
(ver etl/preparar_2turno.py).
"""


def _tlv(buf: bytes, i: int):
    """Lê um TLV em buf[i:]; devolve (classe, construído, tag, início do valor, fim do valor)."""
    b = buf[i]
    classe, construido, tag = b >> 6, bool(b & 0x20), b & 0x1F
    i += 1
    if tag == 0x1F:  # tag em vários bytes
        tag = 0
        while True:
            b = buf[i]
            i += 1
            tag = (tag << 7) | (b & 0x7F)
            if not b & 0x80:
                break
    n = buf[i]
    i += 1
    if n & 0x80:
        k = n & 0x7F
        n = int.from_bytes(buf[i:i + k], "big")
        i += k
    return classe, construido, tag, i, i + n


def arvore(buf: bytes, i: int = 0, fim: int | None = None):
    """Converte BER em lista de nós (classe, tag, filhos | bytes)."""
    fim = len(buf) if fim is None else fim
    nos = []
    while i < fim:
        classe, construido, tag, ini, i = _tlv(buf, i)
        if construido:
            nos.append((classe, tag, arvore(buf, ini, i)))
        else:
            val = buf[ini:i]
            # OCTET STRING que contém outro BER (o envelope guarda o boletim dentro de um octet string)
            if classe == 0 and tag == 4 and len(val) > 2 and val[0] == 0x30:
                try:
                    nos.append((classe, tag, arvore(val)))
                    continue
                except (IndexError, ValueError):
                    pass
            nos.append((classe, tag, val))
    return nos


def inteiro(v: bytes) -> int:
    return int.from_bytes(v, "big", signed=True)


TIPO_VOTO = {1: "nominal", 2: "branco", 3: "nulo", 4: "legenda"}


def _eh_votavel(no) -> bool:
    """TotalVotosVotavel: SEQUENCE que começa com [1] tipoVoto e [2] quantidade."""
    classe, tag, v = no
    return (classe == 0 and tag == 16 and isinstance(v, list) and len(v) >= 3
            and v[0][:2] == (2, 1) and v[1][:2] == (2, 2) and not isinstance(v[1][2], list))


def _eh_total_cargo(no) -> bool:
    """TotalVotosCargo: SEQUENCE (código do cargo, ordem, SEQUENCE OF votáveis)."""
    classe, tag, v = no
    return (classe == 0 and tag == 16 and isinstance(v, list) and len(v) == 3
            and isinstance(v[2][2], list) and v[2][2] and all(_eh_votavel(x) for x in v[2][2]))


def _primitivo(no):
    return None if isinstance(no[2], list) else inteiro(no[2])


def extrair(buf: bytes) -> dict:
    """Extrai do boletim: eleições, aptos, comparecimento e votos por votável de cada cargo,
    além dos horários de abertura/encerramento e da identificação dos eleitores."""
    raiz = arvore(buf)
    out = {"eleicoes": [], "abertura": None, "encerramento": None, "identificacao": None}

    def visitar(nos):
        for no in nos:
            classe, tag, v = no
            if not isinstance(v, list):
                continue
            # [0] SEQUENCE (abertura, encerramento) logo após a data de emissão
            if classe == 2 and tag == 0 and len(v) == 2 and all(x[1] == 27 for x in v):
                out["abertura"], out["encerramento"] = (x[2].decode() for x in v)
            # [1] SEQUENCE de 3 inteiros: forma de identificação dos eleitores
            if classe == 2 and tag == 1 and len(v) == 3 and all(_primitivo(x) is not None for x in v):
                out["identificacao"] = [_primitivo(x) for x in v]
            # ResultadoVotacaoPorEleicao: (idEleicao, aptos, ..., SEQUENCE OF ResultadoVotacao, ...)
            if (classe == 0 and tag == 16 and len(v) >= 5 and _primitivo(v[0]) is not None
                    and 6000 < _primitivo(v[0]) < 7000):
                elei = {"eleicao": _primitivo(v[0]), "aptos": _primitivo(v[1]), "cargos": []}
                for filho in v:
                    if isinstance(filho[2], list):
                        for rv in filho[2]:  # ResultadoVotacao: (tipoCargo, comparecimento, totais)
                            if isinstance(rv[2], list) and len(rv[2]) == 3 and isinstance(rv[2][2][2], list):
                                comp = _primitivo(rv[2][1])
                                for tc in rv[2][2][2]:
                                    if _eh_total_cargo(tc):
                                        cargo = tc[2][0]
                                        cod = _primitivo(cargo) if not isinstance(cargo[2], list) else None
                                        votos = []
                                        for vv in tc[2][2][2]:
                                            f = vv[2]
                                            tipo, qtd = _primitivo(f[0]), _primitivo(f[1])
                                            partido = numero = None
                                            for x in f[2:]:
                                                if x[:2] == (2, 3) and isinstance(x[2], list):
                                                    partido, numero = (_primitivo(y) for y in x[2][:2])
                                            votos.append({"tipo": TIPO_VOTO.get(tipo, tipo), "qtd": qtd,
                                                          "partido": partido, "numero": numero})
                                        elei["cargos"].append({"cargo": cod, "comparecimento": comp,
                                                               "votos": votos})
                out["eleicoes"].append(elei)
                continue
            visitar(v)

    visitar(raiz)
    return out


def mostrar(nos, nivel=0, limite=400):
    """Imprime a árvore (para inspeção)."""
    for classe, tag, v in nos:
        rot = f"{'UCAP'[classe]}{tag}"
        if isinstance(v, list):
            print("  " * nivel + f"{rot} [{len(v)}]")
            mostrar(v, nivel + 1, limite)
        else:
            txt = v.decode("latin-1") if v and all(32 <= c < 127 for c in v) else v.hex()
            print("  " * nivel + f"{rot} = {txt[:60]}" + (f" ({inteiro(v)})" if 0 < len(v) <= 4 else ""))
