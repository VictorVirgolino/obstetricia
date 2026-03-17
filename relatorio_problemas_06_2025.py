"""
Relatorio de exemplos de problemas - 06/2025
Extrai 3 exemplos de cada tipo de problema com dados completos.
"""
import sqlite3

DB = "saude_real.db"
COMP = "06/2025"


def get_conn():
    conn = sqlite3.connect(DB)
    conn.row_factory = sqlite3.Row
    return conn


def print_record_full(conn, prontuario, data_ent, data_sai):
    """Imprime todos os dados de um registro + seus procedimentos."""
    c = conn.cursor()
    c.execute("""
        SELECT r.*, p.nome as pac_nome, p.dt_nasc, p.sexo, p.nome_mae, p.cidade, p.estado, p.cns
        FROM aih_records r
        LEFT JOIN pacientes p ON r.cns_paciente = p.cns
        WHERE r.prontuario = ? AND r.competencia = ? AND r.data_ent = ? AND r.data_sai = ?
    """, (prontuario, COMP, data_ent, data_sai))
    rec = c.fetchone()
    if not rec:
        print(f"      (registro nao encontrado)")
        return

    print(f"      Prontuario:    {rec['prontuario']}")
    print(f"      Paciente:      {rec['pac_nome'] or 'N/A'}")
    print(f"      CNS:           {rec['cns_paciente'] or 'VAZIO'}")
    print(f"      Nascimento:    {rec['dt_nasc'] or 'N/A'}")
    print(f"      Sexo:          {rec['sexo'] or 'N/A'}")
    print(f"      Mae:           {rec['nome_mae'] or 'N/A'}")
    print(f"      Cidade:        {rec['cidade'] or 'N/A'} - {rec['estado'] or 'N/A'}")
    print(f"      AIH:           {rec['id_aih'] or 'VAZIO'}")
    print(f"      Data Entrada:  {rec['data_ent']}")
    print(f"      Data Saida:    {rec['data_sai']}")
    print(f"      CID Principal: {rec['cid_principal'] or 'N/A'}")
    print(f"      Motivo Saida:  {rec['motivo_saida'] or 'N/A'}")
    print(f"      Medico Solic:  {rec['medico_solic'] or 'N/A'}")
    print(f"      Medico Resp:   {rec['medico_resp'] or 'N/A'}")
    print(f"      Observacao:    {rec['observacao'] or 'nenhuma'}")

    # Procedimentos - buscar por id_aih OU por prontuario se id_aih vazio
    id_aih = rec['id_aih']
    if id_aih:
        c.execute("""
            SELECT proc_cod, qtd, cbo_profissional, cnes_executante
            FROM aih_procedimentos WHERE id_aih = ?
            ORDER BY proc_cod
        """, (id_aih,))
    else:
        # Sem AIH - nao tem como vincular procedimentos diretamente
        c.execute("""
            SELECT proc_cod, qtd, cbo_profissional, cnes_executante
            FROM aih_procedimentos WHERE id_aih = ?
            ORDER BY proc_cod
        """, (f"P{prontuario}",))

    procs = c.fetchall()
    if procs:
        print(f"      Procedimentos ({len(procs)}):")
        for p in procs:
            print(f"        - {p['proc_cod']} | qtd={p['qtd']} | CBO={p['cbo_profissional'] or 'N/A'} | CNES={p['cnes_executante'] or 'N/A'}")
    else:
        print(f"      Procedimentos: NENHUM ENCONTRADO")


def section(title):
    print(f"\n{'='*80}")
    print(f"  {title}")
    print(f"{'='*80}")


def main():
    conn = get_conn()
    c = conn.cursor()

    # Abrir arquivo de saida
    import sys, io
    output = io.StringIO()
    original_stdout = sys.stdout

    class Tee:
        def __init__(self, *streams):
            self.streams = streams
        def write(self, data):
            for s in self.streams:
                s.write(data)
        def flush(self):
            for s in self.streams:
                s.flush()

    f = open("relatorio_problemas_06_2025.txt", "w", encoding="utf-8")
    sys.stdout = Tee(original_stdout, f)

    print("RELATORIO DE PROBLEMAS - COMPETENCIA 06/2025")
    print("=" * 80)

    # Resumo geral
    c.execute("SELECT COUNT(*) FROM aih_records WHERE competencia = ?", (COMP,))
    total = c.fetchone()[0]
    c.execute("SELECT COUNT(*) FROM aih_records WHERE competencia = ? AND observacao != '' AND observacao IS NOT NULL", (COMP,))
    total_prob = c.fetchone()[0]
    print(f"\nTotal de registros: {total}")
    print(f"Com problemas:      {total_prob}")
    print(f"Sem problemas:      {total - total_prob}")

    # Contar tipos
    c.execute("""
        SELECT observacao, COUNT(*) as cnt FROM aih_records
        WHERE competencia = ? AND observacao != '' AND observacao IS NOT NULL
        GROUP BY observacao ORDER BY cnt DESC
    """, (COMP,))
    print(f"\nTipos de problemas:")
    for row in c.fetchall():
        print(f"  [{row['cnt']:>3}] {row['observacao']}")

    # =========================================================================
    # 1. INTERNACAO MULTIPLA
    # =========================================================================
    section("INTERNACAO MULTIPLA - 3 Exemplos")
    print("  Mesmo prontuario aparece 2x no site com datas/procedimentos diferentes.")
    print("  Sao internacoes encadeadas do mesmo paciente.\n")

    c.execute("""
        SELECT prontuario FROM aih_records
        WHERE competencia = ? AND observacao LIKE '%MULTIPLA%'
        GROUP BY prontuario
        HAVING COUNT(*) = 2
        LIMIT 3
    """, (COMP,))
    multi_pronts = [row['prontuario'] for row in c.fetchall()]

    for idx, pront in enumerate(multi_pronts, 1):
        c.execute("""
            SELECT data_ent, data_sai, id_aih, cid_principal, observacao
            FROM aih_records
            WHERE prontuario = ? AND competencia = ?
            ORDER BY data_ent
        """, (pront, COMP))
        internacoes = c.fetchall()

        print(f"  --- Exemplo {idx}: Prontuario {pront} ---")
        for j, inter in enumerate(internacoes, 1):
            print(f"\n    INTERNACAO {j}:")
            print_record_full(conn, pront, inter['data_ent'], inter['data_sai'])
        print()

    # =========================================================================
    # 2. SEM AIH (sem ser multipla)
    # =========================================================================
    section("SEM AIH (sem internacao multipla) - 3 Exemplos")
    print("  Prontuario sem numero de AIH preenchido no sistema.\n")

    c.execute("""
        SELECT prontuario, data_ent, data_sai FROM aih_records
        WHERE competencia = ? AND observacao = 'SEM AIH'
        LIMIT 3
    """, (COMP,))
    sem_aih = c.fetchall()

    for idx, row in enumerate(sem_aih, 1):
        print(f"  --- Exemplo {idx}: Prontuario {row['prontuario']} ---\n")
        print_record_full(conn, row['prontuario'], row['data_ent'], row['data_sai'])
        print()

    # =========================================================================
    # 3. SEM CNS
    # =========================================================================
    section("SEM CNS - 3 Exemplos")
    print("  Paciente sem Cartao Nacional de Saude preenchido.\n")

    c.execute("""
        SELECT prontuario, data_ent, data_sai FROM aih_records
        WHERE competencia = ? AND observacao LIKE '%SEM CNS%'
        LIMIT 3
    """, (COMP,))
    sem_cns = c.fetchall()

    if sem_cns:
        for idx, row in enumerate(sem_cns, 1):
            print(f"  --- Exemplo {idx}: Prontuario {row['prontuario']} ---\n")
            print_record_full(conn, row['prontuario'], row['data_ent'], row['data_sai'])
            print()
    else:
        print("  Nenhum registro encontrado com esse problema.\n")

    # =========================================================================
    # 4. INTERNACAO MULTIPLA + SEM AIH (combinado)
    # =========================================================================
    section("INTERNACAO MULTIPLA + SEM AIH (combinado) - 3 Exemplos")
    print("  Prontuario com internacao multipla onde uma das entradas nao tem AIH.")
    print("  Tipicamente: a primeira internacao (pre-parto) nao tem AIH,")
    print("  e a segunda (parto/pos-parto) tem.\n")

    c.execute("""
        SELECT prontuario FROM aih_records
        WHERE competencia = ? AND observacao LIKE '%MULTIPLA%SEM AIH%'
        GROUP BY prontuario
        LIMIT 3
    """, (COMP,))
    multi_sem_aih = [row['prontuario'] for row in c.fetchall()]

    for idx, pront in enumerate(multi_sem_aih, 1):
        c.execute("""
            SELECT data_ent, data_sai, id_aih, cid_principal, observacao
            FROM aih_records
            WHERE prontuario = ? AND competencia = ?
            ORDER BY data_ent
        """, (pront, COMP))
        internacoes = c.fetchall()

        print(f"  --- Exemplo {idx}: Prontuario {pront} ---")
        for j, inter in enumerate(internacoes, 1):
            print(f"\n    INTERNACAO {j} {'(SEM AIH)' if 'SEM AIH' in (inter['observacao'] or '') else '(COM AIH)'}:")
            print_record_full(conn, pront, inter['data_ent'], inter['data_sai'])
        print()

    # =========================================================================
    # 5. SEM AIH + SEM CNS
    # =========================================================================
    section("SEM AIH + SEM CNS (combinado) - 3 Exemplos")
    print("  Prontuario sem AIH e sem CNS do paciente.\n")

    c.execute("""
        SELECT prontuario, data_ent, data_sai FROM aih_records
        WHERE competencia = ? AND observacao LIKE '%SEM AIH%' AND observacao LIKE '%SEM CNS%'
        AND observacao NOT LIKE '%MULTIPLA%'
        LIMIT 3
    """, (COMP,))
    sem_ambos = c.fetchall()

    if sem_ambos:
        for idx, row in enumerate(sem_ambos, 1):
            print(f"  --- Exemplo {idx}: Prontuario {row['prontuario']} ---\n")
            print_record_full(conn, row['prontuario'], row['data_ent'], row['data_sai'])
            print()
    else:
        print("  Nenhum registro encontrado com esse problema.\n")

    # =========================================================================
    print("\n" + "=" * 80)
    print("FIM DO RELATORIO")
    print("=" * 80)

    sys.stdout = original_stdout
    f.close()
    print(f"\nRelatorio salvo em: relatorio_problemas_06_2025.txt")


if __name__ == "__main__":
    main()
