# CASVMS ALPR Training Dataset Structure
Coloca aquí las imágenes de entrenamiento (jpg, png) para el modelo detector de matrículas.
Las anotaciones correspondientes deben residir en `train/labels/` con el mismo nombre base en formato YOLO:
`<class_id> <x_center> <y_center> <width> <height>` (normalizado entre 0.0 y 1.0)
Para clase license_plate: class_id = 0
