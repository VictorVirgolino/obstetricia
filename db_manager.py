import sqlite3

DB_NAME = "saude_real.db"


def get_connection():
    conn = sqlite3.connect(DB_NAME)
    conn.execute("PRAGMA journal_mode=WAL")
    return conn


def create_tables():
    conn = get_connection()
    cursor = conn.cursor()

    cursor.execute("""
    CREATE TABLE IF NOT EXISTS pacientes (
        cns TEXT PRIMARY KEY,
        nome TEXT,
        dt_nasc TEXT,
        sexo TEXT,
        raca TEXT,
        nome_mae TEXT,
        cidade TEXT,
        estado TEXT
    )
    """)

    cursor.execute("""
    CREATE TABLE IF NOT EXISTS aih_records (
        prontuario TEXT,
        competencia TEXT,
        data_ent TEXT,
        id_aih TEXT,
        cns_paciente TEXT,
        data_sai TEXT,
        cid_principal TEXT,
        motivo_saida TEXT,
        medico_solic TEXT,
        medico_resp TEXT,
        data_atendimento TEXT DEFAULT '',
        observacao TEXT DEFAULT '',
        FOREIGN KEY (cns_paciente) REFERENCES pacientes (cns),
        PRIMARY KEY (prontuario, competencia, data_ent, data_sai)
    )
    """)

    cursor.execute("""
    CREATE TABLE IF NOT EXISTS aih_procedimentos (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        id_aih TEXT,
        proc_cod TEXT,
        qtd INTEGER,
        cbo_profissional TEXT,
        cnes_executante TEXT,
        FOREIGN KEY (id_aih) REFERENCES aih_records (id_aih)
    )
    """)

    cursor.execute("""
    CREATE TABLE IF NOT EXISTS sigtap_metadata (
        proc_cod TEXT,
        competencia TEXT,
        nome TEXT,
        descricao TEXT,
        complexidade TEXT,
        financiamento TEXT,
        s_amb REAL,
        s_hosp REAL,
        t_amb REAL,
        s_prof REAL,
        t_hosp REAL,
        idade_min INTEGER,
        idade_max INTEGER,
        sexo TEXT,
        permanencia_media INTEGER,
        PRIMARY KEY (proc_cod, competencia)
    )
    """)

    # View com custo mais recente por procedimento
    cursor.execute("DROP VIEW IF EXISTS sigtap_custo_atual")
    cursor.execute("""
    CREATE VIEW sigtap_custo_atual AS
    SELECT s.proc_cod, s.nome, s.descricao, s.complexidade, s.financiamento,
           s.s_amb, s.s_hosp, s.t_amb, s.s_prof, s.t_hosp,
           s.idade_min, s.idade_max, s.sexo, s.permanencia_media,
           s.competencia as competencia_ref
    FROM sigtap_metadata s
    INNER JOIN (
        SELECT proc_cod,
               MAX(SUBSTR(competencia, 4, 4) || SUBSTR(competencia, 1, 2)) as max_comp
        FROM sigtap_metadata
        GROUP BY proc_cod
    ) latest ON s.proc_cod = latest.proc_cod
        AND (SUBSTR(s.competencia, 4, 4) || SUBSTR(s.competencia, 1, 2)) = latest.max_comp
    """)

    conn.commit()
    conn.close()


def migrate_db():
    """Add new columns and migrate primary key if needed."""
    conn = get_connection()
    cursor = conn.cursor()

    # Check existing columns in aih_procedimentos
    cursor.execute("PRAGMA table_info(aih_procedimentos)")
    existing_cols = {row[1] for row in cursor.fetchall()}

    if "custo_unitario" not in existing_cols:
        cursor.execute("ALTER TABLE aih_procedimentos ADD COLUMN custo_unitario REAL DEFAULT 0.0")
        print("Added column: aih_procedimentos.custo_unitario")

    if "custo_total" not in existing_cols:
        cursor.execute("ALTER TABLE aih_procedimentos ADD COLUMN custo_total REAL DEFAULT 0.0")
        print("Added column: aih_procedimentos.custo_total")

    # Check aih_records structure
    cursor.execute("PRAGMA table_info(aih_records)")
    aih_cols = cursor.fetchall()
    existing_cols_aih = {row[1] for row in aih_cols}

    # Detect current PK structure
    pk_cols = [col[1] for col in aih_cols if col[5] > 0]
    target_pk = ["prontuario", "competencia", "data_ent", "data_sai"]

    # Migrate to PK (prontuario, competencia, data_ent, data_sai) + observacao column
    needs_migration = (
        "observacao" not in existing_cols_aih
        or pk_cols != target_pk
    )

    if needs_migration:
        print("Migrando aih_records: PK -> (prontuario, competencia, data_ent) + observacao...")
        cursor.execute("""
        CREATE TABLE aih_records_new (
            prontuario TEXT,
            competencia TEXT,
            data_ent TEXT,
            id_aih TEXT,
            cns_paciente TEXT,
            data_sai TEXT,
            cid_principal TEXT,
            motivo_saida TEXT,
            medico_solic TEXT,
            medico_resp TEXT,
            data_atendimento TEXT DEFAULT '',
            observacao TEXT DEFAULT '',
            FOREIGN KEY (cns_paciente) REFERENCES pacientes (cns),
            PRIMARY KEY (prontuario, competencia, data_ent, data_sai)
        )
        """)
        cursor.execute("""
        INSERT OR IGNORE INTO aih_records_new
            (prontuario, competencia, data_ent, id_aih, cns_paciente, data_sai,
             cid_principal, motivo_saida, medico_solic, medico_resp, data_atendimento)
        SELECT prontuario, competencia, COALESCE(data_ent, ''), id_aih, cns_paciente,
               data_sai, cid_principal, motivo_saida, medico_solic, medico_resp,
               COALESCE(data_atendimento, '')
        FROM aih_records
        """)
        old_count = cursor.execute("SELECT COUNT(*) FROM aih_records").fetchone()[0]
        new_count = cursor.execute("SELECT COUNT(*) FROM aih_records_new").fetchone()[0]
        cursor.execute("DROP TABLE aih_records")
        cursor.execute("ALTER TABLE aih_records_new RENAME TO aih_records")
        print(f"  Migrado: {old_count} -> {new_count} registros")

    # Migrate empty id_aih to synthetic keys (SEM_AIH_prontuario_data_ent_data_sai)
    # This fixes the bug where all patients without AIH shared id_aih=''
    cursor.execute("SELECT COUNT(*) FROM aih_records WHERE id_aih = ''")
    empty_count = cursor.fetchone()[0]
    if empty_count > 0:
        print(f"Migrando {empty_count} registros com id_aih vazio para chave sintetica...")
        # Update aih_records: generate synthetic id_aih
        cursor.execute("""
            UPDATE aih_records
            SET id_aih = 'SEM_AIH_' || prontuario || '_' || data_ent || '_' || data_sai
            WHERE id_aih = ''
        """)
        # Delete orphaned procedures with empty id_aih (they were shared/corrupt)
        # They will be re-extracted with correct id_aih on next scraper run
        cursor.execute("DELETE FROM aih_procedimentos WHERE id_aih = ''")
        deleted = cursor.rowcount
        print(f"  Registros AIH atualizados: {empty_count}")
        print(f"  Procedimentos orfaos removidos: {deleted}")
        print(f"  Execute 'python run_sync.py' para re-extrair os procedimentos corretos.")

    conn.commit()
    conn.close()


def save_paciente(data):
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("""
    INSERT OR REPLACE INTO pacientes (cns, nome, dt_nasc, sexo, raca, nome_mae, cidade, estado)
    VALUES (?, ?, ?, ?, ?, ?, ?, ?)
    """, (data['cns'], data['nome'], data['dt_nasc'], data['sexo'], data['raca'],
          data['nome_mae'], data['cidade'], data['estado']))
    conn.commit()
    conn.close()


def save_aih_record(data):
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("""
    INSERT OR REPLACE INTO aih_records
    (prontuario, competencia, data_ent, id_aih, cns_paciente, data_sai,
     cid_principal, motivo_saida, medico_solic, medico_resp, data_atendimento, observacao)
    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
    """, (data['prontuario'], data['competencia'], data['data_ent'], data['id_aih'],
          data['cns_paciente'], data['data_sai'],
          data['cid_principal'], data['motivo_saida'], data['medico_solic'],
          data['medico_resp'], data.get('data_atendimento', ''), data.get('observacao', '')))
    conn.commit()
    conn.close()


def save_procedimento(id_aih, proc_cod, qtd, cbo, cnes):
    conn = get_connection()
    cursor = conn.cursor()
    # Check if this exact procedure already exists for this AIH
    cursor.execute("""
    SELECT 1 FROM aih_procedimentos WHERE id_aih = ? AND proc_cod = ?
    """, (id_aih, proc_cod))
    if cursor.fetchone():
        # Update quantity if it changed
        cursor.execute("""
        UPDATE aih_procedimentos SET qtd = ?, cbo_profissional = ?, cnes_executante = ?
        WHERE id_aih = ? AND proc_cod = ?
        """, (qtd, cbo, cnes, id_aih, proc_cod))
    else:
        cursor.execute("""
        INSERT INTO aih_procedimentos (id_aih, proc_cod, qtd, cbo_profissional, cnes_executante)
        VALUES (?, ?, ?, ?, ?)
        """, (id_aih, proc_cod, qtd, cbo, cnes))
    conn.commit()
    conn.close()


def save_sigtap(data):
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("""
    INSERT OR REPLACE INTO sigtap_metadata
    (proc_cod, competencia, nome, descricao, complexidade, financiamento,
     s_amb, s_hosp, t_amb, s_prof, t_hosp, idade_min, idade_max, sexo, permanencia_media)
    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
    """, (data['proc_cod'], data['competencia'], data['nome'], data['descricao'],
          data['complexidade'], data['financiamento'],
          data['s_amb'], data['s_hosp'], data['t_amb'], data['s_prof'], data['t_hosp'],
          data['idade_min'], data['idade_max'], data['sexo'], data['permanencia_media']))
    conn.commit()
    conn.close()


def save_batch(pacientes, aihs, procedimentos):
    """Save all records for a competencia in a single transaction."""
    conn = get_connection()
    cursor = conn.cursor()
    try:
        for data in pacientes:
            cursor.execute("""
            INSERT OR REPLACE INTO pacientes (cns, nome, dt_nasc, sexo, raca, nome_mae, cidade, estado)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """, (data['cns'], data['nome'], data['dt_nasc'], data['sexo'], data['raca'],
                  data['nome_mae'], data['cidade'], data['estado']))

        for data in aihs:
            cursor.execute("""
            INSERT OR REPLACE INTO aih_records
            (prontuario, competencia, data_ent, id_aih, cns_paciente, data_sai,
             cid_principal, motivo_saida, medico_solic, medico_resp, data_atendimento, observacao)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (data['prontuario'], data['competencia'], data['data_ent'], data['id_aih'],
                  data['cns_paciente'], data['data_sai'],
                  data['cid_principal'], data['motivo_saida'], data['medico_solic'],
                  data['medico_resp'], data.get('data_atendimento', ''), data.get('observacao', '')))

        for proc in procedimentos:
            cursor.execute("""
            SELECT 1 FROM aih_procedimentos WHERE id_aih = ? AND proc_cod = ?
            """, (proc['id_aih'], proc['code']))
            if cursor.fetchone():
                cursor.execute("""
                UPDATE aih_procedimentos SET qtd = ?, cbo_profissional = ?, cnes_executante = ?
                WHERE id_aih = ? AND proc_cod = ?
                """, (proc['qty'], proc['cbo'], proc['cnes'], proc['id_aih'], proc['code']))
            else:
                cursor.execute("""
                INSERT INTO aih_procedimentos (id_aih, proc_cod, qtd, cbo_profissional, cnes_executante)
                VALUES (?, ?, ?, ?, ?)
                """, (proc['id_aih'], proc['code'], proc['qty'], proc['cbo'], proc['cnes']))

        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


def check_aih_exists(prontuario, competencia, data_ent=None, data_sai=None):
    conn = get_connection()
    cursor = conn.cursor()
    if data_ent and data_sai:
        cursor.execute(
            "SELECT 1 FROM aih_records WHERE prontuario = ? AND competencia = ? AND data_ent = ? AND data_sai = ?",
            (prontuario, competencia, data_ent, data_sai))
    elif data_ent:
        cursor.execute(
            "SELECT 1 FROM aih_records WHERE prontuario = ? AND competencia = ? AND data_ent = ?",
            (prontuario, competencia, data_ent))
    else:
        cursor.execute(
            "SELECT 1 FROM aih_records WHERE prontuario = ? AND competencia = ?",
            (prontuario, competencia))
    exists = cursor.fetchone() is not None
    conn.close()
    return exists


def count_by_competencia(competencia):
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT COUNT(*) FROM aih_records WHERE competencia = ?", (competencia,))
    count = cursor.fetchone()[0]
    conn.close()
    return count


def sync_costs():
    """Propagate SIGTAP costs to aih_procedimentos table.
    Uses t_hosp when available, falls back to t_amb for ambulatorial procedures.
    """
    conn = get_connection()
    cursor = conn.cursor()

    # Use t_hosp if > 0, otherwise fall back to t_amb
    cursor.execute("""
        UPDATE aih_procedimentos
        SET custo_unitario = COALESCE((
            SELECT CASE
                WHEN s.t_hosp > 0 THEN s.t_hosp
                WHEN s.t_amb > 0 THEN s.t_amb
                ELSE 0.0
            END
            FROM sigtap_metadata s
            JOIN aih_records r ON r.id_aih = aih_procedimentos.id_aih
            WHERE s.proc_cod = aih_procedimentos.proc_cod
              AND s.competencia = r.competencia
        ), 0.0),
        custo_total = qtd * COALESCE((
            SELECT CASE
                WHEN s.t_hosp > 0 THEN s.t_hosp
                WHEN s.t_amb > 0 THEN s.t_amb
                ELSE 0.0
            END
            FROM sigtap_metadata s
            JOIN aih_records r ON r.id_aih = aih_procedimentos.id_aih
            WHERE s.proc_cod = aih_procedimentos.proc_cod
              AND s.competencia = r.competencia
        ), 0.0)
    """)

    updated = cursor.rowcount
    conn.commit()

    # Print summary
    cursor.execute("""
        SELECT COUNT(*), SUM(custo_total)
        FROM aih_procedimentos WHERE custo_total > 0
    """)
    row = cursor.fetchone()
    print(f"Cost sync: {row[0]} procedures with costs, total: R$ {row[1] or 0:.2f}")

    cursor.execute("""
        SELECT COUNT(*) FROM aih_procedimentos WHERE custo_unitario = 0.0 OR custo_unitario IS NULL
    """)
    missing = cursor.fetchone()[0]
    if missing > 0:
        print(f"  WARNING: {missing} procedures still without costs (SIGTAP data missing)")

    # Generate report of all-zero procedures for review
    cursor.execute("""
        SELECT s.proc_cod, s.nome, s.competencia, s.complexidade, s.financiamento,
               s.s_amb, s.s_hosp, s.t_amb, s.s_prof, s.t_hosp
        FROM sigtap_metadata s
        WHERE s.s_amb = 0.0 AND s.s_hosp = 0.0 AND s.t_amb = 0.0
          AND s.s_prof = 0.0 AND s.t_hosp = 0.0
        ORDER BY s.proc_cod, s.competencia
    """)
    zeros = cursor.fetchall()

    if zeros:
        from datetime import datetime
        fname = f"sigtap_zerados_{datetime.now().strftime('%Y%m%d_%H%M%S')}.txt"
        with open(fname, "w", encoding="utf-8") as f:
            f.write(f"PROCEDIMENTOS SIGTAP COM TODOS OS VALORES ZERADOS\n")
            f.write(f"Gerado em: {datetime.now().strftime('%d/%m/%Y %H:%M')}\n")
            f.write(f"Total: {len(zeros)} registros\n")
            f.write("=" * 100 + "\n\n")

            # Group by proc_cod
            from collections import defaultdict
            by_proc = defaultdict(list)
            for row in zeros:
                by_proc[row[0]].append(row)

            f.write(f"Procedimentos unicos: {len(by_proc)}\n\n")

            for proc_cod, entries in sorted(by_proc.items()):
                first = entries[0]
                nome = first[1]
                complexidade = first[3]
                financiamento = first[4]
                comps = sorted([e[2] for e in entries])

                f.write(f"CODIGO: {proc_cod}\n")
                f.write(f"  Nome: {nome}\n")
                f.write(f"  Complexidade: {complexidade}\n")
                f.write(f"  Financiamento: {financiamento}\n")
                f.write(f"  Competencias: {', '.join(comps)}\n")

                # Possible reason
                if "Incentivo" in financiamento:
                    f.write(f"  ** Motivo provavel: financiamento por INCENTIVO (valor nao aparece na tabela)\n")
                elif complexidade == "Não se Aplica" or complexidade == "N\xe3o se Aplica":
                    f.write(f"  ** Motivo provavel: complexidade 'Nao se Aplica' - valor depende do contexto\n")
                else:
                    f.write(f"  ** Motivo provavel: procedimento valorado por pontos/percentual ou sem custo direto\n")

                f.write("\n")

        print(f"  Relatorio de zerados salvo em: {fname}")

    conn.close()


def get_competencia_summary():
    """Returns summary by competencia for dashboard integration."""
    conn = get_connection()
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()
    cursor.execute("""
        SELECT
            r.competencia,
            COUNT(DISTINCT r.prontuario) as total_aihs,
            COUNT(p.id) as total_procedimentos,
            COALESCE(SUM(p.custo_total), 0) as custo_total,
            COALESCE(SUM(p.custo_unitario * p.qtd), 0) as custo_calculado
        FROM aih_records r
        LEFT JOIN aih_procedimentos p ON r.id_aih = p.id_aih
        GROUP BY r.competencia
        ORDER BY r.competencia
    """)
    rows = [dict(r) for r in cursor.fetchall()]
    conn.close()
    return rows


def get_costs_by_city():
    """Returns costs grouped by patient city."""
    conn = get_connection()
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()
    cursor.execute("""
        SELECT
            COALESCE(pac.cidade, 'Desconhecida') as cidade,
            r.competencia,
            COUNT(DISTINCT r.prontuario) as total_aihs,
            COALESCE(SUM(p.custo_total), 0) as custo_total
        FROM aih_records r
        JOIN pacientes pac ON r.cns_paciente = pac.cns
        LEFT JOIN aih_procedimentos p ON r.id_aih = p.id_aih
        GROUP BY pac.cidade, r.competencia
        ORDER BY pac.cidade, r.competencia
    """)
    rows = [dict(r) for r in cursor.fetchall()]
    conn.close()
    return rows


if __name__ == "__main__":
    create_tables()
    migrate_db()
    print(f"Database {DB_NAME} initialized and migrated.")
