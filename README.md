# 👁️ CASVMS / EdgeVMS: Industrial AI Video Management System

Sistema de Gestión de Vídeo (VMS) multiplataforma (Linux, Windows, macOS), de alto rendimiento y arquitectura **Zero-Cloud / Air-Gapped**, diseñado para Mini PCs con procesadores Intel y aceleración gráfica iGPU (Intel Iris Xe / UHD Graphics).

---

## 🏗️ Arquitectura del Sistema

```
                            +---------------------------------------+
                            |       Tauri + React + TypeScript      |
                            |   (UI Estilo Milestone / Synology)    |
                            +-------------------+-------------------+
                                                |
               +--------------------------------+--------------------------------+
               | MJPEG Stream (Sub-100ms)       | SSE Alertas en Tiempo Real     | REST API (Config / Clips)
               v                                v                                v
+---------------------------------------------------------------------------------------------------+
|                                  FastAPI Orchestrator (Backend)                                   |
|   +-------------------------------------------------------------------------------------------+   |
|   |                  IPC Multiprocessing Manager (frame_dict, event_queue)                    |   |
|   +-------------------------------------------------------------------------------------------+   |
+---------------------------------------------------------------------------------------------------+
         |                                        |                                        |
         v                                        v                                        v
+------------------+                    +-------------------+                    +------------------+
| Camera Worker 1  |                    | Camera Worker 2   |                    | Camera Worker N  |
|  - MOG2 Standby  |                    |  - MOG2 Standby   |                    |  - MOG2 Standby  |
|  - YOLOv8 (GPU)  |                    |  - YOLOv8 (GPU)   |                    |  - YOLOv8 (GPU)  |
|  - ByteTrack     |                    |  - ByteTrack      |                    |  - ByteTrack     |
|  - Vector Engine |                    |  - Vector Engine  |                    |  - Vector Engine |
|  - Smart RAM DVR |                    |  - Smart RAM DVR  |                    |  - Smart RAM DVR |
+------------------+                    +-------------------+                    +------------------+
         |                                        |                                        |
         +----------------------------------------+----------------------------------------+
                                                  | Event Queue
                                                  v
                     +----------------------------+----------------------------+
                     |                            |                            |
                     v                            v                            v
          +--------------------+       +---------------------+      +---------------------+
          |    InfluxDB 2.7    |       | Eclipse Mosquitto 2 |      |   Modbus TCP Server |
          | (Line Protocol TS) |       | (Hierarchical MQTT) |      | (Holding Registers) |
          +--------------------+       +---------------------+      +---------------------+
                     |
                     v
          +--------------------+
          |   Grafana Dash     |
          |  (Flux Analytics)  |
          +--------------------+
```

---

## 🚀 Despliegue del Backend e Infraestructura (Docker)

### 1. Variables de Entorno
El archivo [.env](file:///Users/castordfedez/Desktop/CASVMS/.env) incluye los parámetros de configuración listos para producción.

### 2. Iniciar el Stack con Aceleración por Hardware
En cualquier Mini PC Linux (Intel Gen 8/9/10/11/12/13/Ultra):
```bash
# Validar disponibilidad del nodo iGPU
ls -la /dev/dri

# Compilar y arrancar el stack completo
docker compose up -d --build
```

Servicios desplegados:
- **FastAPI / VMS Engine**: `http://localhost:8000` (Docs en `/docs`)
- **Streaming MJPEG**: `http://localhost:8000/stream/{camera_id}`
- **SSE Alertas**: `http://localhost:8000/api/alerts/sse`
- **Modbus TCP Server**: Puerto `5020` (Offset 0 a 5)
- **InfluxDB 2.7**: `http://localhost:8086`
- **Grafana**: `http://localhost:3000` (`admin` / `admin`)
- **Mosquitto MQTT**: Puerto `1883`

---

## 💻 Frontend Nativo (Tauri + React + TypeScript)

### Modo Desarrollo Web:
```bash
cd frontend
npm install
npm run dev
```

### Ejecutar Binario Nativo de Escritorio (Tauri):
```bash
cd frontend
npm run tauri dev
```

---

## ⚙️ Mapeo de Registros Modbus TCP (PLCs / SCADA)

| Dirección | Registro | Tipo | Descripción |
|---|---|---|---|
| `40001` | `0` | INT16 | **Aforo Actual** (Personas dentro del recinto) |
| `40002` | `1` | INT16 | **Alarma Sobre-Aforo** (`1` si Aforo $\ge$ Límite, `0` normal) |
| `40003` | `2` | INT16 | **Contador Total IN** (Entradas acumuladas) |
| `40004` | `3` | INT16 | **Contador Total OUT** (Salidas acumuladas) |
| `40005` | `4` | INT16 | **Alarma de Intrusión Perimetral** (`1` si activa) |
| `40006` | `5` | INT16 | **Límite de Aforo Máximo** (Lectura/Escritura por PLC) |
