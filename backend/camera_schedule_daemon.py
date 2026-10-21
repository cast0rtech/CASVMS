#!/usr/bin/env python3
# ==============================================================================
# CASVMS - Daemon Astronómico ONVIF para ALPR (Zúrich / Solar Schedule)
# ==============================================================================
import os
import sys
import datetime
import time
from zoneinfo import ZoneInfo

# Asegurar importación de ONVIFImagingController desde gateways o onvif_controller
try:
    from gateways.onvif_imaging import ONVIFImagingController
except ImportError:
    try:
        from onvif_controller import ONVIFImagingController
    except ImportError:
        # Fallback inline si se ejecuta de forma completamente aislada
        try:
            from onvif import ONVIFCamera
        except ImportError:
            ONVIFCamera = None

        class ONVIFImagingController:
            def __init__(self, ip, port, user, password, wsdl_dir="/usr/local/lib/python3.10/site-packages/wsdl/"):
                self.ip = ip
                if ONVIFCamera is None:
                    raise ImportError("Se requiere 'onvif-zeep'. Ejecute: pip install onvif-zeep")
                self.cam = ONVIFCamera(ip, port, user, password, wsdl_dir)
                self.media_service = self.cam.create_media_service()
                self.imaging_service = self.cam.create_imaging_service()
                profiles = self.media_service.GetProfiles()
                self.video_source_token = profiles[0].VideoSourceConfiguration.SourceToken

            def _get_current_settings(self):
                return self.imaging_service.GetImagingSettings(self.video_source_token)

            def set_night_profile_alpr(self):
                print(f"[{self.ip}] Aplicando perfil NOCTURNO (IR ON, Shutter 1/1000s, WDR OFF)...")
                req = self.imaging_service.create_type('SetImagingSettings')
                req.VideoSourceToken = self.video_source_token
                req.ImagingSettings = self._get_current_settings()
                req.ImagingSettings.IrCutFilter = 'OFF'
                if hasattr(req.ImagingSettings, 'Exposure') and req.ImagingSettings.Exposure is not None:
                    req.ImagingSettings.Exposure.Mode = 'MANUAL'
                    req.ImagingSettings.Exposure.ExposureTime = 1000
                    req.ImagingSettings.Exposure.Gain = 20
                if hasattr(req.ImagingSettings, 'WideDynamicRange') and req.ImagingSettings.WideDynamicRange is not None:
                    req.ImagingSettings.WideDynamicRange.Mode = 'OFF'
                self.imaging_service.SetImagingSettings(req)
                print(f"[{self.ip}] Perfil NOCTURNO aplicado con éxito.")

            def set_day_profile(self):
                print(f"[{self.ip}] Aplicando perfil DIURNO (Color, Auto Shutter, WDR ON)...")
                req = self.imaging_service.create_type('SetImagingSettings')
                req.VideoSourceToken = self.video_source_token
                req.ImagingSettings = self._get_current_settings()
                req.ImagingSettings.IrCutFilter = 'ON'
                if hasattr(req.ImagingSettings, 'Exposure') and req.ImagingSettings.Exposure is not None:
                    req.ImagingSettings.Exposure.Mode = 'AUTO'
                if hasattr(req.ImagingSettings, 'WideDynamicRange') and req.ImagingSettings.WideDynamicRange is not None:
                    req.ImagingSettings.WideDynamicRange.Mode = 'ON'
                self.imaging_service.SetImagingSettings(req)
                print(f"[{self.ip}] Perfil DIURNO aplicado con éxito.")

try:
    from astral.geocoder import database, lookup
    from astral.sun import sun
except ImportError:
    database = None
    lookup = None
    sun = None

def camera_schedule_daemon_astral(cam_ip, cam_port, cam_user, cam_pass):
    # Instanciar el controlador ONVIF definido previamente
    controller = ONVIFImagingController(cam_ip, cam_port, cam_user, cam_pass)
    
    # 1. Cargar la base de datos astronómica y localizar Zúrich
    if database is None or lookup is None or sun is None:
        print("[CRON ERROR] La librería 'astral' no está instalada.")
        print("             Instale las dependencias con: pip install -r requirements.txt (o pip install astral)")
        return

    db = database()
    city = lookup("Zurich", db)
    tz = ZoneInfo("Europe/Zurich")
    
    current_mode = None 

    print(f"[CRON] Demonio Solar ONVIF iniciado para {city.name} ({city.region})")

    while True:
        # Obtener hora actual con consciencia de zona horaria (Timezone-Aware)
        now = datetime.datetime.now(tz)
        
        # 2. Calcular los eventos solares exactos para el día de HOY
        s = sun(city.observer, date=now.date(), tzinfo=tz)
        sunrise = s['sunrise']
        sunset = s['sunset']
        
        # 3. Aplicar offset de seguridad (Crepúsculo)
        # La cámara necesita activar el modo noche antes de que oscurezca por completo
        dusk_threshold = sunset - datetime.timedelta(minutes=30)
        dawn_threshold = sunrise + datetime.timedelta(minutes=30)
        
        if dawn_threshold <= now < dusk_threshold:
            expected_mode = "DAY"
        else:
            expected_mode = "NIGHT"
            
        # 4. Ejecutar el comando SOAP solo si hay un cambio de estado
        if current_mode != expected_mode:
            try:
                if expected_mode == "DAY":
                    controller.set_day_profile()
                else:
                    controller.set_night_profile_alpr()
                
                current_mode = expected_mode
                print(f"[ONVIF] Sincronización solar: Cambiado a {expected_mode}. Próximo atardecer calculado a las {sunset.strftime('%H:%M')}")
            except Exception as e:
                print(f"[ONVIF] Error al comunicar con la cámara {cam_ip}: {e}")
        
        # El sol se mueve lento. Evaluar cada 5 minutos (300 segundos) ahorra CPU.
        time.sleep(300)

if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser(description="Demonio Solar ONVIF para ALPR (Efemérides Astronómicas de Zúrich)")
    parser.add_argument("--ip", default=os.getenv("ONVIF_CAMERA_IP", "192.168.1.64"), help="IP de la cámara ONVIF")
    parser.add_argument("--port", type=int, default=int(os.getenv("ONVIF_CAMERA_PORT", "80")), help="Puerto ONVIF")
    parser.add_argument("--user", default=os.getenv("ONVIF_CAMERA_USER", "admin"), help="Usuario ONVIF")
    parser.add_argument("--password", default=os.getenv("ONVIF_CAMERA_PASS", "admin123"), help="Contraseña ONVIF")

    args = parser.parse_args()

    try:
        camera_schedule_daemon_astral(
            cam_ip=args.ip,
            cam_port=args.port,
            cam_user=args.user,
            cam_pass=args.password
        )
    except KeyboardInterrupt:
        print("\n[CRON] Demonio Solar ONVIF detenido correctamente por el usuario.")
        sys.exit(0)
