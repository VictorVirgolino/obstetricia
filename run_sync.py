"""
Orchestrator: Run hospital scraper + SIGTAP cost sync.

Usage:
    python run_sync.py                      # Full sync (all competences)
    python run_sync.py --comp 03/2026       # Single competence
    python run_sync.py --sigtap-only        # Only sync SIGTAP costs
    python run_sync.py --hospital-only      # Only scrape hospital
"""
import asyncio
import sys
import db_manager
import scraper_hospital
import scraper_sigtap


async def main():
    args = sys.argv[1:]

    sigtap_only = "--sigtap-only" in args
    hospital_only = "--hospital-only" in args

    # Parse competence filter
    comp = None
    for i, arg in enumerate(args):
        if arg == "--comp" and i + 1 < len(args):
            comp = args[i + 1]

    # Init DB
    db_manager.create_tables()
    db_manager.migrate_db()

    if not sigtap_only:
        print("=" * 60)
        print("STEP 1: Hospital Scraper")
        print("=" * 60)

        competences = None
        if comp:
            month, year = comp.split("/")
            competences = [(month, year)]

        await scraper_hospital.run_scraper(competences)

    if not hospital_only:
        print("\n" + "=" * 60)
        print("STEP 2: SIGTAP Cost Sync")
        print("=" * 60)
        await scraper_sigtap.sync_all_procedures()

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
