import sqlite3
import pandas as pd

def check_empty_ids():
    conn = sqlite3.connect('saude_real.db')
    
    with open('check_integrity_output.txt', 'w', encoding='utf-8') as f:
        f.write("--- AIH Records with empty/null id_aih ---\n")
        query = "SELECT prontuario, competencia, data_ent, id_aih, observacao FROM aih_records WHERE id_aih IS NULL OR id_aih = ''"
        df = pd.read_sql_query(query, conn)
        f.write(df.to_string() + "\n")
        f.write(f"\nTotal records with empty ID: {len(df)}\n")
        
        f.write("\n--- Procedures with empty/null id_aih ---\n")
        query_proc = "SELECT COUNT(*) as count FROM aih_procedimentos WHERE id_aih IS NULL OR id_aih = ''"
        count_proc = pd.read_sql_query(query_proc, conn).iloc[0]['count']
        f.write(f"Total procedures with empty id_aih: {count_proc}\n")
        
        if len(df) > 1:
            f.write("\nCRITICAL: Multiple records share the same empty id_aih!\n")
            f.write("This causes all procedures with empty id_aih to be associated with ALL these records.\n")
            
            f.write("\nExample: Procedures linked to empty ID are:\n")
            query_list = "SELECT proc_cod, SUM(qtd) as total_qtd FROM aih_procedimentos WHERE id_aih = '' GROUP BY proc_cod"
            df_list = pd.read_sql_query(query_list, conn)
            f.write(df_list.to_string() + "\n")
    
    conn.close()
    print("Integrity check saved to check_integrity_output.txt")

if __name__ == "__main__":
    check_empty_ids()
