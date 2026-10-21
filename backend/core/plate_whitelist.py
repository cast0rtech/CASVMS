# ==============================================================================
# CASVMS - SQLite Whitelist Manager for ALPR Access Control
# ==============================================================================
import os
import re
import sqlite3
import logging
from typing import List, Dict, Any, Optional
from contextlib import contextmanager

logger = logging.getLogger("CASVMS.ALPR.Whitelist")

class PlateWhitelistManager:
    """
    Gestor de Base de Datos SQLite para control de acceso vehicular por matrícula (Whitelist).
    
    Permite inicializar la tabla, añadir matrículas autorizadas, eliminarlas, listar
    y verificar la validez de un vehículo de manera segura frente a concurrencia.
    """

    def __init__(self, db_path: str = "/app/config/plates_whitelist.db"):
        self.db_path = db_path
        
        # Asegurar que el directorio de la base de datos existe
        dir_name = os.path.dirname(self.db_path)
        if dir_name:
            os.makedirs(dir_name, exist_ok=True)
            
        self.initialize_db()

    @staticmethod
    def normalize_plate(plate: str) -> str:
        """
        Normaliza el texto de la matrícula eliminando espacios, guiones
        y caracteres no alfanuméricos, convirtiendo a mayúsculas.
        Ejemplo: 'ZURICH-1234 ' -> 'ZURICH1234'
        """
        if not plate:
            return ""
        return re.sub(r"[^A-Z0-9]", "", plate.upper().strip())

    def _get_connection(self) -> sqlite3.Connection:
        """Crea una conexión SQLite con timeout extendido y modo WAL."""
        conn = sqlite3.connect(self.db_path, timeout=10.0)
        conn.row_factory = sqlite3.Row
        # Activar Write-Ahead Logging para lectura/escritura concurrente segura
        conn.execute("PRAGMA journal_mode=WAL;")
        return conn

    def initialize_db(self) -> None:
        """Crea la tabla de matrículas si no existe e inserta registros de ejemplo."""
        try:
            with self._get_connection() as conn:
                conn.execute("""
                    CREATE TABLE IF NOT EXISTS authorized_plates (
                        id INTEGER PRIMARY KEY AUTOINCREMENT,
                        plate_number TEXT UNIQUE NOT NULL,
                        normalized_plate TEXT UNIQUE NOT NULL,
                        owner_name TEXT DEFAULT '',
                        vehicle_model TEXT DEFAULT '',
                        is_active INTEGER DEFAULT 1,
                        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                    );
                """)
                conn.execute("""
                    CREATE INDEX IF NOT EXISTS idx_normalized_plate 
                    ON authorized_plates(normalized_plate);
                """)
                conn.commit()

            # Insertar matrículas de prueba si está vacía
            if len(self.get_all_plates()) == 0:
                self.add_plate("ZURICH-1234", owner_name="Dirección Operativa", vehicle_model="Audi A6")
                self.add_plate("1234-BBB", owner_name="Flota Logística 01", vehicle_model="Ford Transit")
                self.add_plate("ABC-5678", owner_name="Mantenimiento Industrial", vehicle_model="Toyota Hilux")
                logger.info("Base de datos de matrículas inicializada con registros de ejemplo.")

        except Exception as e:
            logger.error(f"Error inicializando base de datos SQLite de matrículas: {str(e)}", exc_info=True)

    def add_plate(
        self,
        plate_number: str,
        owner_name: str = "",
        vehicle_model: str = ""
    ) -> bool:
        """
        Añade una nueva matrícula a la whitelist autorizada.
        """
        normalized = self.normalize_plate(plate_number)
        if not normalized:
            logger.warning("Intento de registrar matrícula vacía o no válida.")
            return False

        try:
            with self._get_connection() as conn:
                conn.execute("""
                    INSERT INTO authorized_plates (plate_number, normalized_plate, owner_name, vehicle_model, is_active)
                    VALUES (?, ?, ?, ?, 1)
                    ON CONFLICT(normalized_plate) DO UPDATE SET
                        plate_number=excluded.plate_number,
                        owner_name=excluded.owner_name,
                        vehicle_model=excluded.vehicle_model,
                        is_active=1;
                """, (plate_number.strip().upper(), normalized, owner_name, vehicle_model))
                conn.commit()

            logger.info(f"Matrícula '{plate_number}' ({normalized}) registrada en whitelist.")
            return True

        except Exception as e:
            logger.error(f"Error añadiendo matrícula '{plate_number}': {str(e)}")
            return False

    def delete_plate(self, plate_number: str) -> bool:
        """
        Elimina una matrícula de la base de datos de autorización.
        """
        normalized = self.normalize_plate(plate_number)
        try:
            with self._get_connection() as conn:
                cursor = conn.execute("""
                    DELETE FROM authorized_plates 
                    WHERE normalized_plate = ? OR plate_number = ?;
                """, (normalized, plate_number.strip().upper()))
                conn.commit()
                deleted = cursor.rowcount > 0

            if deleted:
                logger.info(f"Matrícula '{plate_number}' eliminada de la whitelist.")
            return deleted

        except Exception as e:
            logger.error(f"Error eliminando matrícula '{plate_number}': {str(e)}")
            return False

    def is_plate_authorized(self, raw_plate: str) -> bool:
        """
        Verifica si una matrícula extraída por OCR está autorizada y activa.
        Compara tanto la forma normalizada como subcadenas si es necesario.
        """
        normalized = self.normalize_plate(raw_plate)
        if not normalized or len(normalized) < 3:
            return False

        try:
            with self._get_connection() as conn:
                # 1. Coincidencia exacta de matrícula normalizada
                row = conn.execute("""
                    SELECT id FROM authorized_plates
                    WHERE normalized_plate = ? AND is_active = 1
                    LIMIT 1;
                """, (normalized,)).fetchone()

                if row is not None:
                    return True

                # 2. Búsqueda tolerante a prefijos/sufijos menores (ej. letras de país "E", "CH")
                # si la matrícula leída contiene la autorizada o viceversa
                if len(normalized) >= 5:
                    cursor = conn.execute("""
                        SELECT normalized_plate FROM authorized_plates WHERE is_active = 1;
                    """)
                    for record in cursor.fetchall():
                        target = record["normalized_plate"]
                        if target in normalized or normalized in target:
                            return True

            return False

        except Exception as e:
            logger.error(f"Error verificando autorización de matrícula '{raw_plate}': {str(e)}")
            return False

    def check_access(self, plate: str) -> Optional[Dict[str, Any]]:
        """Devuelve los datos del propietario si la matrícula existe y está autorizada, o None."""
        normalized = self.normalize_plate(plate)
        if not normalized:
            return None
        try:
            with self._get_connection() as conn:
                row = conn.execute("""
                    SELECT plate_number, owner_name FROM authorized_plates
                    WHERE normalized_plate = ? AND is_active = 1
                    LIMIT 1;
                """, (normalized,)).fetchone()
                if row:
                    return {"plate": row["plate_number"], "owner": row["owner_name"]}
                return None
        except Exception as e:
            logger.error(f"Error comprobando acceso para matrícula '{plate}': {e}")
            return None

    def get_all_plates(self) -> List[Dict[str, Any]]:
        """Retorna todas las matrículas autorizadas registradas."""
        try:
            with self._get_connection() as conn:
                cursor = conn.execute("""
                    SELECT id, plate_number, normalized_plate, owner_name, vehicle_model, is_active, created_at
                    FROM authorized_plates
                    ORDER BY id DESC;
                """)
                return [dict(row) for row in cursor.fetchall()]
        except Exception as e:
            logger.error(f"Error listando matrículas autorizadas: {str(e)}")
            return []


class ALPRWhitelistDB:
    """
    Gestor SQLite simplificado para whitelist de control de accesos ALPR.
    Permite inicializar la tabla, añadir matrículas con normalización estricta,
    eliminar y verificar el acceso vehicular para activación de barrera.
    """
    def __init__(self, db_path="data/alpr_whitelist.db"):
        self.db_path = db_path
        dir_name = os.path.dirname(self.db_path)
        if dir_name:
            os.makedirs(dir_name, exist_ok=True)
        self.init_db()

    @contextmanager
    def get_db(self):
        conn = sqlite3.connect(self.db_path)
        try:
            yield conn
        finally:
            conn.close()

    def init_db(self):
        with self.get_db() as conn:
            cursor = conn.cursor()
            cursor.execute('''
                CREATE TABLE IF NOT EXISTS whitelist (
                    plate TEXT PRIMARY KEY,
                    owner TEXT NOT NULL,
                    added_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            ''')
            conn.commit()

    def add_plate(self, plate: str, owner: str):
        # Normalización estricta: Mayúsculas y sin espacios
        clean_plate = plate.upper().replace(" ", "").strip()
        with self.get_db() as conn:
            cursor = conn.cursor()
            cursor.execute('''
                INSERT OR REPLACE INTO whitelist (plate, owner) 
                VALUES (?, ?)
            ''', (clean_plate, owner))
            conn.commit()

    def delete_plate(self, plate: str):
        with self.get_db() as conn:
            cursor = conn.cursor()
            cursor.execute("DELETE FROM whitelist WHERE plate = ?", (plate.upper(),))
            conn.commit()

    def check_access(self, plate: str) -> Optional[dict]:
        """Devuelve los datos del propietario si la matrícula existe, o None."""
        clean_plate = plate.upper().replace(" ", "").strip()
        with self.get_db() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT owner FROM whitelist WHERE plate = ?", (clean_plate,))
            result = cursor.fetchone()
            if result:
                return {"plate": clean_plate, "owner": result[0]}
            return None

    def get_all_plates(self) -> list:
        with self.get_db() as conn:
            cursor = conn.cursor()
            # Ordenados por fecha de inserción (los más nuevos primero)
            cursor.execute("SELECT plate, owner, added_at FROM whitelist ORDER BY added_at DESC")
            rows = cursor.fetchall()
            return [{"plate": row[0], "owner": row[1], "added_at": row[2]} for row in rows]


