"""
Orchestrator: Run hospital scraper + SIGTAP cost sync + Diretoria reports.

Usage:
    python run_sync.py                      # Full sync (all competences)
    python run_sync.py --comp 03/2026       # Single competence
    python run_sync.py --sigtap-only        # Only sync SIGTAP costs
    python run_sync.py --hospital-only      # Only scrape hospital
    python run_sync.py --diretoria-only     # Only scrape Diretoria (estatística + NAQ)
    python run_sync.py --inicio 2026-01-01 --fim 2026-01-31  # Date range for Diretoria
"""
import asyncio
import sys
import db_manager
import scraper_hospital
import scraper_sigtap
import scraper_diretoria


async def main():
    args = sys.argv[1:]

    sigtap_only = "--sigtap-only" in args
    hospital_only = "--hospital-only" in args
    diretoria_only = "--diretoria-only" in args

    # Parse competence filter
    comp = None
    data_inicio = None
    data_fim = None
    for i, arg in enumerate(args):
        if arg == "--comp" and i + 1 < len(args):
            comp = args[i + 1]
        elif arg == "--inicio" and i + 1 < len(args):
            data_inicio = args[i + 1]
        elif arg == "--fim" and i + 1 < len(args):
            data_fim = args[i + 1]

    # Init DB
    db_manager.create_tables()
    db_manager.migrate_db()

    if not sigtap_only and not diretoria_only:
        print("=" * 60)
        print("STEP 1: Hospital Scraper")
        print("=" * 60)

        competences = None
        if comp:
            month, year = comp.split("/")
            competences = [(month, year)]

        await scraper_hospital.run_scraper(competences)

    if not hospital_only and not diretoria_only:
        print("\n" + "=" * 60)
        print("STEP 2: SIGTAP Cost Sync")
        print("=" * 60)
        await scraper_sigtap.sync_all_procedures()

    if not sigtap_only and not hospital_only:
        print("\n" + "=" * 60)
        print("STEP 3: Diretoria (Estatística + NAQ)")
        print("=" * 60)
        await scraper_diretoria.run_scraper_diretoria(data_inicio, data_fim)

    # Summary
    print("\n" + "=" * 60)
    print("SUMMARY")
    print("=" * 60)
    summary = db_manager.get_competencia_summary()
    total_cost = 0
    total_aihs = 0
    total_procs = 0
    for row in summary:
        print(f"  {row['competencia']}: {row['total_aihs']} AIHs, {row['total_procedimentos']} procs, R$ {row['custo_total']:.2f}")
        total_cost += row['custo_total']
        total_aihs += row['total_aihs']
        total_procs += row['total_procedimentos']
    print(f"\n  TOTAL: {total_aihs} AIHs, {total_procs} procedures, R$ {total_cost:,.2f}")


if __name__ == "__main__":
    asyncio.run(main())
