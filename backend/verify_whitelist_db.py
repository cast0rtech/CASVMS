# ==============================================================================
# CASVMS - Test & Verification Script for ALPRWhitelistDB
# ==============================================================================
import os
import sys
import tempfile

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from core.plate_whitelist import ALPRWhitelistDB

def test_alpr_whitelist_db():
    print("-> Verificando ALPRWhitelistDB...")
    
    with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as tf:
        db_path = tf.name

    try:
        db = ALPRWhitelistDB(db_path=db_path)
        
        # 1. Insertar matrícula con normalización (minúsculas y espacios)
        db.add_plate("  zurich-1234 ", "Director General")
        
        # 2. Comprobar acceso con variaciones de espaciado
        res1 = db.check_access("ZURICH-1234")
        assert res1 is not None, "Fallo al verificar matrícula autorizada."
        assert res1["plate"] == "ZURICH-1234"
        assert res1["owner"] == "Director General"
        print("   [OK] Inserción y verificación con normalización exitosa.")

        # 3. Comprobar matrícula no registrada
        res_fail = db.check_access("UNKNOWN-999")
        assert res_fail is None, "Una matrícula no registrada fue autorizada erróneamente."
        print("   [OK] Denegación correcta para matrícula desconocida.")

        # 4. Actualizar propietario de matrícula existente
        db.add_plate("ZURICH-1234", "Director Operaciones")
        res2 = db.check_access("ZURICH-1234")
        assert res2["owner"] == "Director Operaciones"
        print("   [OK] INSERT OR REPLACE actualiza propietario correctamente.")

        # 5. Listar matrículas
        all_plates = db.get_all_plates()
        assert len(all_plates) == 1
        print(f"   [OK] Listado de matrículas verificado: {all_plates[0]['plate']}")

        # 6. Eliminar matrícula
        db.delete_plate("ZURICH-1234")
        res_deleted = db.check_access("ZURICH-1234")
        assert res_deleted is None, "La matrícula no fue eliminada correctamente."
        print("   [OK] Eliminación de matrícula confirmada.")

    finally:
        if os.path.exists(db_path):
            os.remove(db_path)

if __name__ == "__main__":
    print("==================================================")
    print("TEST: ALPR WHITELIST SQLITE MANAGER")
    print("==================================================")
    test_alpr_whitelist_db()
    print("\n>>> ALPR WHITELIST DB VALIDADO EXITOSAMENTE <<<")
