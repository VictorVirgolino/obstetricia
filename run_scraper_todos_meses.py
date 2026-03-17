"""
Scraper completo - todos os meses exceto 06/2025 (ja feito).
Limpa dados antigos, re-extrai tudo, e marca problemas.
"""
import asyncio
import sqlite3
import scraper_hospital
import db_manager

MESES = [
    ("07", "2025"), ("08", "2025"), ("09", "2025"),
    ("10", "2025"), ("11", "2025"), ("12", "2025"),
    ("01", "2026"), ("02", "2026"), ("03", "2026"),
]


def limpar_meses():
    conn = sqlite3.connect("saude_real.db")
    c = conn.cursor()
    for month, year in MESES:
        comp = f"{month}/{year}"
        c.execute("DELETE FROM aih_records WHERE competencia = ?", (comp,))
        print(f"  {comp}: {c.rowcount} registros removidos")
    conn.commit()
    conn.close()


def marcar_problemas():
    conn = sqlite3.connect("saude_real.db")
    c = conn.cursor()

    for month, year in MESES:
        comp = f"{month}/{year}"

        # INTERNACAO MULTIPLA
        c.execute('''
            SELECT prontuario, COUNT(*) as cnt FROM aih_records
            WHERE competencia = ? GROUP BY prontuario HAVING cnt > 1
        ''', (comp,))
        multi = c.fetchall()
        for pront, cnt in multi:
            c.execute('''
                UPDATE aih_records SET observacao =
                    CASE
                        WHEN observacao IS NULL OR observacao = '' THEN 'INTERNACAO MULTIPLA (' || ? || 'x no site)'
                        WHEN observacao NOT LIKE '%MULTIPLA%' THEN observacao || ' | INTERNACAO MULTIPLA (' || ? || 'x no site)'
                        ELSE observacao
                    END
                WHERE prontuario = ? AND competencia = ?
            ''', (cnt, cnt, pront, comp))

        # SEM AIH
        c.execute('''
            UPDATE aih_records SET observacao =
                CASE
                    WHEN observacao IS NULL OR observacao = '' THEN 'SEM AIH'
                    WHEN observacao NOT LIKE '%SEM AIH%' THEN observacao || ' | SEM AIH'
                    ELSE observacao
                END
            WHERE competencia = ? AND (id_aih = '' OR id_aih IS NULL)
        ''', (comp,))

        # SEM CNS
        c.execute('''
            UPDATE aih_records SET observacao =
                CASE
                    WHEN observacao IS NULL OR observacao = '' THEN 'SEM CNS'
                    WHEN observacao NOT LIKE '%SEM CNS%' THEN observacao || ' | SEM CNS'
                    ELSE observacao
                END
            WHERE competencia = ? AND (cns_paciente = '' OR cns_paciente IS NULL)
        ''', (comp,))

        # SEM CID
        c.execute('''
            UPDATE aih_records SET observacao =
                CASE
                    WHEN observacao IS NULL OR observacao = '' THEN 'SEM CID'
                    WHEN observacao NOT LIKE '%SEM CID%' THEN observacao || ' | SEM CID'
                    ELSE observacao
                END
            WHERE competencia = ? AND (cid_principal = '' OR cid_principal IS NULL)
        ''', (comp,))

        # Contar
        c.execute("SELECT COUNT(*) FROM aih_records WHERE competencia = ?", (comp,))
        total = c.fetchone()[0]
        c.execute("SELECT COUNT(*) FROM aih_records WHERE competencia = ? AND observacao != '' AND observacao IS NOT NULL", (comp,))
        probs = c.fetchone()[0]
        print(f"  {comp}: {total} registros, {probs} com problemas")

    conn.commit()
    conn.close()


async def main():
    db_manager.create_tables()
    db_manager.migrate_db()

    print("=" * 60)
    print("FASE 1: Limpando dados antigos dos meses restantes")
    print("=" * 60)
    limpar_meses()

    print("\n" + "=" * 60)
    print("FASE 2: Executando scraper para todos os meses")
    print("=" * 60)
    await scraper_hospital.run_scraper(competences=MESES, max_concurrent=10)

    print("\n" + "=" * 60)
    print("FASE 3: Marcando problemas nos registros")
    print("=" * 60)
    marcar_problemas()

    # Resumo final
    print("\n" + "=" * 60)
    print("RESUMO FINAL")
    print("=" * 60)
    conn = sqlite3.connect("saude_real.db")
    c = conn.cursor()
    todos = [("06", "2025")] + MESES
    for month, year in todos:
        comp = f"{month}/{year}"
        c.execute("SELECT COUNT(*) FROM aih_records WHERE competencia = ?", (comp,))
        total = c.fetchone()[0]
        c.execute("SELECT COUNT(*) FROM aih_records WHERE competencia = ? AND observacao != '' AND observacao IS NOT NULL", (comp,))
        probs = c.fetchone()[0]
        print(f"  {comp}: {total} registros ({probs} com problemas)")
    c.execute("SELECT COUNT(*) FROM aih_records")
    print(f"\n  TOTAL GERAL: {c.fetchone()[0]} registros")
    conn.close()

    print("\nConcluido!")


if __name__ == "__main__":
    asyncio.run(main())
