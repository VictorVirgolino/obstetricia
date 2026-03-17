"""
Relatorio SIGTAP - Todos os procedimentos da competencia 06/2025
com valores extraidos do site para validacao pelo cliente.
"""
import sqlite3

DB = "saude_real.db"
COMP = "06/2025"


def main():
    conn = sqlite3.connect(DB)
    conn.row_factory = sqlite3.Row
    c = conn.cursor()

    f = open("relatorio_sigtap_06_2025.txt", "w", encoding="utf-8")

    def out(msg=""):
        print(msg)
        f.write(msg + "\n")

    out("=" * 100)
    out("RELATORIO SIGTAP - COMPETENCIA 06/2025")
    out("Valores extraidos do site SIGTAP para validacao")
    out("=" * 100)

    # 1. Todos os procedimentos do SIGTAP para 06/2025
    c.execute("""
        SELECT * FROM sigtap_metadata
        WHERE competencia = ?
        ORDER BY proc_cod
    """, (COMP,))
    sigtap_rows = c.fetchall()

    out(f"\nTotal de procedimentos no SIGTAP para {COMP}: {len(sigtap_rows)}")

    out(f"\n{'='*130}")
    out("TABELA COMPLETA DE PROCEDIMENTOS SIGTAP")
    out(f"{'='*130}")
    out(f"{'Codigo':<12} {'Nome':<42} {'SA':>10} {'SH':>10} {'TA':>10} {'SP':>10} {'TH':>10} {'Complexidade':<22}")
    out(f"{'':12} {'':42} {'Srv.Amb':>10} {'Srv.Hosp':>10} {'Tot.Amb':>10} {'Srv.Prof':>10} {'Tot.Hosp':>10}")
    out("-" * 130)

    for row in sigtap_rows:
        nome = (row['nome'] or '')[:42]
        complexidade = (row['complexidade'] or '')[:22]
        out(f"{row['proc_cod']:<12} {nome:<42} {row['s_amb']:>10.2f} {row['s_hosp']:>10.2f} {row['t_amb']:>10.2f} {row['s_prof']:>10.2f} {row['t_hosp']:>10.2f} {complexidade:<22}")

    # 2. Detalhamento completo de cada procedimento
    out(f"\n{'='*130}")
    out("DETALHAMENTO COMPLETO POR PROCEDIMENTO")
    out(f"{'='*130}")

    for row in sigtap_rows:
        out(f"\n  {'-'*126}")
        out(f"  Codigo:                          {row['proc_cod']}")
        out(f"  Nome:                            {row['nome'] or 'N/A'}")
        out(f"  Descricao:                       {row['descricao'] or 'N/A'}")
        out(f"  Complexidade:                    {row['complexidade'] or 'N/A'}")
        out(f"  Financiamento:                   {row['financiamento'] or 'N/A'}")
        out(f"  Servico Ambulatorial (SA):       R$ {row['s_amb']:.2f}")
        out(f"  Servico Hospitalar (SH):         R$ {row['s_hosp']:.2f}")
        out(f"  Total Ambulatorial (TA):         R$ {row['t_amb']:.2f}")
        out(f"  Servico Profissional (SP):       R$ {row['s_prof']:.2f}")
        out(f"  Total Hospitalar (TH = SH + SP): R$ {row['t_hosp']:.2f}")
        out(f"  Idade Minima:                    {row['idade_min']} anos")
        out(f"  Idade Maxima:                    {row['idade_max']} anos")
        out(f"  Sexo:                            {row['sexo'] or 'N/A'}")
        out(f"  Permanencia Media:               {row['permanencia_media']} dias")

    # 3. Cruzamento: procedimentos usados nos prontuarios 06/2025
    out(f"\n{'='*100}")
    out("PROCEDIMENTOS UTILIZADOS EM AIHs DE 06/2025")
    out(f"{'='*100}")

    c.execute("""
        SELECT
            ap.proc_cod,
            sm.nome as sigtap_nome,
            sm.s_amb, sm.s_hosp, sm.t_amb, sm.s_prof, sm.t_hosp,
            COUNT(*) as vezes_usado,
            SUM(ap.qtd) as qtd_total,
            SUM(ap.qtd) * COALESCE(sm.s_amb, 0) as total_s_amb,
            SUM(ap.qtd) * COALESCE(sm.s_hosp, 0) as total_s_hosp,
            SUM(ap.qtd) * COALESCE(sm.t_amb, 0) as total_t_amb,
            SUM(ap.qtd) * COALESCE(sm.s_prof, 0) as total_s_prof,
            SUM(ap.qtd) * COALESCE(sm.t_hosp, 0) as total_t_hosp
        FROM aih_procedimentos ap
        JOIN aih_records r ON r.id_aih = ap.id_aih
        LEFT JOIN sigtap_metadata sm ON sm.proc_cod = ap.proc_cod AND sm.competencia = r.competencia
        WHERE r.competencia = ?
        GROUP BY ap.proc_cod
        ORDER BY total_t_hosp DESC
    """, (COMP,))
    usage = c.fetchall()

    out(f"\nTotal de procedimentos distintos usados: {len(usage)}")
    out(f"\nLegenda: SA=Servico Ambulatorial | SH=Servico Hospitalar | TA=Total Ambulatorial | SP=Servico Profissional | TH=Total Hospitalar")
    out(f"\n{'Codigo':<12} {'Nome':<38} {'Qtd':>5} {'SA Unit':>10} {'SH Unit':>10} {'TA Unit':>10} {'SP Unit':>10} {'TH Unit':>10} {'TH Total':>14}")
    out("-" * 130)

    grand_total = 0
    sem_valor = []
    for row in usage:
        nome = (row['sigtap_nome'] or 'SEM DADOS SIGTAP')[:38]
        t_hosp = row['t_hosp'] or 0
        total_t_hosp = row['total_t_hosp'] or 0
        grand_total += total_t_hosp
        out(f"{row['proc_cod']:<12} {nome:<38} {row['qtd_total']:>5} "
            f"R${row['s_amb'] or 0:>8.2f} R${row['s_hosp'] or 0:>8.2f} "
            f"R${row['t_amb'] or 0:>8.2f} R${row['s_prof'] or 0:>8.2f} "
            f"R${t_hosp:>8.2f} R${total_t_hosp:>12.2f}")
        if not row['t_hosp']:
            sem_valor.append(row['proc_cod'])

    out("-" * 100)
    out(f"{'TOTAL GERAL':>82} R$ {grand_total:>11.2f}")

    if sem_valor:
        out(f"\n  ATENCAO: {len(sem_valor)} procedimentos sem valor no SIGTAP:")
        for cod in sem_valor:
            out(f"    - {cod}")

    # 4. Top 20 procedimentos por valor total
    out(f"\n{'='*100}")
    out("TOP 20 PROCEDIMENTOS POR VALOR TOTAL")
    out(f"{'='*100}")

    c.execute("""
        SELECT
            ap.proc_cod,
            sm.nome as sigtap_nome,
            sm.s_amb, sm.s_hosp, sm.t_amb, sm.s_prof, sm.t_hosp,
            SUM(ap.qtd) as qtd_total,
            SUM(ap.qtd) * COALESCE(sm.s_amb, 0) as total_s_amb,
            SUM(ap.qtd) * COALESCE(sm.s_hosp, 0) as total_s_hosp,
            SUM(ap.qtd) * COALESCE(sm.t_amb, 0) as total_t_amb,
            SUM(ap.qtd) * COALESCE(sm.s_prof, 0) as total_s_prof,
            SUM(ap.qtd) * COALESCE(sm.t_hosp, 0) as total_t_hosp
        FROM aih_procedimentos ap
        JOIN aih_records r ON r.id_aih = ap.id_aih
        LEFT JOIN sigtap_metadata sm ON sm.proc_cod = ap.proc_cod AND sm.competencia = r.competencia
        WHERE r.competencia = ?
        GROUP BY ap.proc_cod
        ORDER BY total_t_hosp DESC
        LIMIT 20
    """, (COMP,))
    top20 = c.fetchall()

    out(f"\n{'#':>3} {'Codigo':<12} {'Nome':<35} {'Qtd':>5}  {'SH Unit':>10} {'SP Unit':>10} {'TH Unit':>10}  {'SH Total':>12} {'SP Total':>12} {'TH Total':>14}")
    out("-" * 130)
    for i, row in enumerate(top20, 1):
        nome = (row['sigtap_nome'] or 'SEM SIGTAP')[:35]
        out(f"{i:>3} {row['proc_cod']:<12} {nome:<35} {row['qtd_total']:>5}  "
            f"R${row['s_hosp'] or 0:>8.2f} R${row['s_prof'] or 0:>8.2f} R${row['t_hosp'] or 0:>8.2f}  "
            f"R${row['total_s_hosp'] or 0:>10.2f} R${row['total_s_prof'] or 0:>10.2f} R${row['total_t_hosp'] or 0:>12.2f}")

    # 5. Resumo financeiro
    out(f"\n{'='*100}")
    out("RESUMO FINANCEIRO - 06/2025")
    out(f"{'='*100}")

    c.execute("""
        SELECT COUNT(DISTINCT r.prontuario) as pacientes,
               COUNT(*) as total_registros
        FROM aih_records r WHERE r.competencia = ?
    """, (COMP,))
    r = c.fetchone()
    out(f"\n  Pacientes (prontuarios unicos): {r['pacientes']}")
    out(f"  Total registros (incl. multiplas): {r['total_registros']}")

    c.execute("""
        SELECT COUNT(DISTINCT ap.proc_cod) as procs_distintos,
               SUM(ap.qtd) as total_procedimentos,
               SUM(ap.qtd * COALESCE(sm.s_amb, 0)) as total_s_amb,
               SUM(ap.qtd * COALESCE(sm.s_hosp, 0)) as total_s_hosp,
               SUM(ap.qtd * COALESCE(sm.t_amb, 0)) as total_t_amb,
               SUM(ap.qtd * COALESCE(sm.s_prof, 0)) as total_s_prof,
               SUM(ap.qtd * COALESCE(sm.t_hosp, 0)) as total_t_hosp
        FROM aih_procedimentos ap
        JOIN aih_records r ON r.id_aih = ap.id_aih
        LEFT JOIN sigtap_metadata sm ON sm.proc_cod = ap.proc_cod AND sm.competencia = r.competencia
        WHERE r.competencia = ?
    """, (COMP,))
    r = c.fetchone()
    out(f"  Procedimentos distintos:             {r['procs_distintos']}")
    out(f"  Total de procedimentos realizados:   {r['total_procedimentos']}")
    out(f"")
    out(f"  Servico Ambulatorial (SA) total:     R$ {r['total_s_amb'] or 0:>14,.2f}")
    out(f"  Servico Hospitalar (SH) total:       R$ {r['total_s_hosp'] or 0:>14,.2f}")
    out(f"  Total Ambulatorial (TA) total:       R$ {r['total_t_amb'] or 0:>14,.2f}")
    out(f"  Servico Profissional (SP) total:     R$ {r['total_s_prof'] or 0:>14,.2f}")
    out(f"  Total Hospitalar (TH = SH+SP) total: R$ {r['total_t_hosp'] or 0:>14,.2f}")

    out(f"\n{'='*100}")
    out("FIM DO RELATORIO")
    out(f"{'='*100}")

    f.close()
    conn.close()
    print(f"\nRelatorio salvo em: relatorio_sigtap_06_2025.txt")


if __name__ == "__main__":
    main()
