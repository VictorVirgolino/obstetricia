import sqlite3
import pandas as pd

def check_patient_procedures(prontuario):
    conn = sqlite3.connect('saude_real.db')
    
    with open('diag_368677_output.txt', 'w', encoding='utf-8') as f:
        f.write(f"=== Report for Prontuario: {prontuario} ===\n")
        
        # Check aih_records
        query_aih = "SELECT * FROM aih_records WHERE prontuario = ?"
        df_aih = pd.read_sql_query(query_aih, conn, params=(prontuario,))
        
        if df_aih.empty:
            f.write(f"No record found in aih_records for prontuario {prontuario}\n")
            return
        
        f.write("\n[AIH Records]\n")
        f.write(df_aih.to_string() + "\n")
        
        for _, row in df_aih.iterrows():
            id_aih = row['id_aih']
            comp = row['competencia']
            f.write(f"\n--- Procedures for ID_AIH: {id_aih} (Comp: {comp}) ---\n")
            
            query_proc = """
                SELECT p.proc_cod, p.qtd, p.cbo_profissional, p.cnes_executante, s.nome as descricao
                FROM aih_procedimentos p
                LEFT JOIN sigtap_metadata s ON p.proc_cod = s.proc_cod AND s.competencia = ?
                WHERE p.id_aih = ?
            """
            df_proc = pd.read_sql_query(query_proc, conn, params=(comp, id_aih))
            
            if df_proc.empty:
                f.write("No procedures found for this AIH record.\n")
            else:
                f.write(df_proc.to_string() + "\n")
            
    conn.close()
    print("Output saved to diag_368677_output.txt")

if __name__ == "__main__":
    check_patient_procedures("368677")
