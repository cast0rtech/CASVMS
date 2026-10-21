#!/usr/bin/env python3
# ==============================================================================
# CASVMS - Dataset Validator for ALPR Training (YOLO Format)
# ==============================================================================
import os
import sys
try:
    import yaml
except ImportError:
    yaml = None

def validate_dataset(data_yaml_path: str = "vms_training/data.yaml") -> bool:
    print(f"-> Analizando configuración de dataset: {data_yaml_path}")
    if not os.path.exists(data_yaml_path):
        print(f"[ERROR] No se encontró el archivo {data_yaml_path}")
        return False

    cfg = {}
    if yaml is not None:
        with open(data_yaml_path, "r", encoding="utf-8") as f:
            cfg = yaml.safe_load(f) or {}
    else:
        # Parser básico de respaldo sin dependencias externas
        cfg = {}
        with open(data_yaml_path, "r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line or line.startswith("#"):
                    continue
                if ":" in line:
                    k, v = line.split(":", 1)
                    k, v = k.strip(), v.strip().split("#")[0].strip()
                    if v:
                        cfg[k] = v
        if "names" not in cfg:
            cfg["names"] = {0: "license_plate"}
        elif isinstance(cfg["names"], str) and cfg["names"].startswith("["):
            import ast
            try:
                cfg["names"] = ast.literal_eval(cfg["names"])
            except Exception:
                pass

    base_dir = os.path.dirname(os.path.abspath(data_yaml_path))
    dataset_root = cfg.get("path", base_dir)
    if not os.path.isabs(dataset_root):
        dataset_root = os.path.normpath(os.path.join(base_dir, dataset_root))

    train_img_dir = os.path.join(dataset_root, cfg.get("train", "train/images"))
    val_img_dir = os.path.join(dataset_root, cfg.get("val", "valid/images"))
    classes = cfg.get("names", {})

    print(f"   Directorio raíz: {dataset_root}")
    print(f"   Clases declaradas: {classes}")

    def check_split(split_name: str, img_dir: str):
        label_dir = img_dir.replace("images", "labels")
        if not os.path.exists(img_dir):
            print(f"   [AVISO] Carpeta de imágenes '{split_name}' vacía o pendiente: {img_dir}")
            return 0, 0

        valid_exts = {".jpg", ".jpeg", ".png", ".bmp", ".webp"}
        images = [f for f in os.listdir(img_dir) if os.path.splitext(f)[1].lower() in valid_exts]
        labels = [f for f in os.listdir(label_dir) if f.endswith(".txt")] if os.path.exists(label_dir) else []

        print(f"   Split '{split_name}': {len(images)} imágenes encontradas, {len(labels)} archivos de etiquetas.")
        return len(images), len(labels)

    check_split("Entrenamiento (train)", train_img_dir)
    check_split("Validación (valid)", val_img_dir)

    print("-> Verificación de estructura del dataset completada.")
    return True

if __name__ == "__main__":
    path = sys.argv[1] if len(sys.argv) > 1 else "vms_training/data.yaml"
    validate_dataset(path)
