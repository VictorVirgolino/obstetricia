"""
Teste do scraper para 06/2025 - roda apenas esse mes
e depois mostra os registros com problemas.
"""
import asyncio
import sqlite3
import scraper_hospital


async def main():
    # Rodar scraper apenas para 06/2025
    await scraper_hospital.run_scraper(competences=[("06", "2025")])

    # Mostrar registros com problemas
    print("\n" + "=" * 70)
    print("REGISTROS COM PROBLEMAS NO BANCO - 06/2025")
    print("=" * 70)

    conn = sqlite3.connect("saude_real.db")
    cursor = conn.cursor()

    # Total geral
    cursor.execute("SELECT COUNT(*) FROM aih_records WHERE competencia = '06/2025'")
    total = cursor.fetchone()[0]
    print(f"\nTotal de registros: {total}")

    # Com observacao
    cursor.execute("""
        SELECT COUNT(*) FROM aih_records
        WHERE competencia = '06/2025' AND observacao != '' AND observacao IS NOT NULL
    """)
    total_problems = cursor.fetchone()[0]
    print(f"Com problemas: {total_problems}")

    # Sem observacao
    print(f"Sem problemas: {total - total_problems}")

    # Listar todos com problemas
    cursor.execute("""
        SELECT r.prontuario, r.data_ent, r.data_sai, r.id_aih, r.cns_paciente,
               r.observacao, p.nome
        FROM aih_records r
        LEFT JOIN pacientes p ON r.cns_paciente = p.cns
        WHERE r.competencia = '06/2025' AND r.observacao != '' AND r.observacao IS NOT NULL
        ORDER BY r.observacao, r.prontuario
    """)
    rows = cursor.fetchall()

    if rows:
        # Agrupar por tipo de problema
        from collections import defaultdict
        by_problem = defaultdict(list)
        for row in rows:
            problems = row[5].split(" | ")
            for prob in problems:
                by_problem[prob].append(row)

        for problem, records in sorted(by_problem.items()):
            print(f"\n--- {problem}: {len(records)} registros ---")
            for row in records:
                pront, ent, sai, aih, cns, obs, nome = row
                print(f"  Pront={pront} | {nome or 'SEM NOME'} | ent={ent} sai={sai} | aih={aih or 'VAZIO'} | obs={obs}")
    else:
        print("\nNenhum registro com problemas!")

    # Prontuarios com internação múltipla - detalhar
    cursor.execute("""
        SELECT prontuario, COUNT(*) as cnt
        FROM aih_records
        WHERE competencia = '06/2025'
        GROUP BY prontuario
        HAVING cnt > 1
        ORDER BY cnt DESC, prontuario
    """)
    multi = cursor.fetchall()
    if multi:
        print(f"\n{'='*70}")
        print(f"PRONTUARIOS COM MULTIPLAS INTERNACOES: {len(multi)}")
        print(f"{'='*70}")
        for pront, cnt in multi:
            cursor.execute("""
                SELECT data_ent, data_sai, id_aih, cid_principal, observacao
                FROM aih_records
                WHERE prontuario = ? AND competencia = '06/2025'
                ORDER BY data_ent
            """, (pront,))
            internacoes = cursor.fetchall()
            cursor.execute("""
                SELECT p.nome FROM aih_records r
                LEFT JOIN pacientes p ON r.cns_paciente = p.cns
                WHERE r.prontuario = ? AND r.competencia = '06/2025' LIMIT 1
            """, (pront,))
            nome = cursor.fetchone()[0] or 'SEM NOME'
            print(f"\n  {pront} - {nome} ({cnt} internacoes):")
            for ent, sai, aih, cid, obs in internacoes:
                print(f"    ent={ent} -> sai={sai} | aih={aih or 'VAZIO'} | cid={cid} | obs={obs}")

    conn.close()


if __name__ == "__main__":
    asyncio.run(main())
