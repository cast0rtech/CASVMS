#!/usr/bin/env python3
# ==============================================================================
# CASVMS - Standalone ONVIF Imaging Controller (CLI & Module)
# ==============================================================================
import sys
import argparse
import datetime
import time

try:
    from onvif import ONVIFCamera
except ImportError:
    ONVIFCamera = None

class ONVIFImagingController:
    def __init__(self, ip, port, user, password, wsdl_dir="/usr/local/lib/python3.10/site-packages/wsdl/"):
        self.ip = ip
        if ONVIFCamera is None:
            raise ImportError(
                "La librería 'onvif-zeep' no está instalada. "
                "Ejecute: pip install onvif-zeep"
            )
        # Inicializar el cliente ONVIF (Tarda un par de segundos en parsear los WSDL)
        self.cam = ONVIFCamera(ip, port, user, password, wsdl_dir)
        
        # Servicios requeridos
        self.media_service = self.cam.create_media_service()
        self.imaging_service = self.cam.create_imaging_service()
        
        # Obtener el Token del Sensor Físico (Suele ser el índice 0)
        profiles = self.media_service.GetProfiles()
        if not profiles:
            raise ValueError(f"[{self.ip}] No se obtuvieron perfiles de vídeo.")
        self.video_source_token = profiles[0].VideoSourceConfiguration.SourceToken

    def _get_current_settings(self):
        # Retorna el objeto ImagingSettings actual de la cámara
        return self.imaging_service.GetImagingSettings(self.video_source_token)

    def set_night_profile_alpr(self):
        """Fuerza Blanco y Negro (IR) y exposición rápida para matrículas."""
        print(f"[{self.ip}] Aplicando perfil NOCTURNO (IR ON, Shutter 1/1000)...")
        
        request = self.imaging_service.create_type('SetImagingSettings')
        request.VideoSourceToken = self.video_source_token
        request.ImagingSettings = self._get_current_settings()
        
        # 1. Filtro IR-Cut (Modo Noche)
        # 'ON' significa que el filtro que bloquea el infrarrojo está ACTIVO (Modo Día en algunas marcas) 
        # ATENCIÓN: El estándar ONVIF suele usar 'OFF' para quitar el filtro y dejar pasar el IR (Blanco/Negro).
        request.ImagingSettings.IrCutFilter = 'OFF'
        
        # 2. Control de Exposición (Depende de la implementación del fabricante Hikvision/Dahua)
        if hasattr(request.ImagingSettings, 'Exposure') and request.ImagingSettings.Exposure is not None:
            request.ImagingSettings.Exposure.Mode = 'MANUAL'
            # El valor de ExposureTime suele venir en microsegundos o milisegundos.
            # 1000 microsegundos = 1 milisegundo (1/1000s).
            request.ImagingSettings.Exposure.ExposureTime = 1000 
            request.ImagingSettings.Exposure.Gain = 20 # Ganancia moderada
            
        # Opcional: Desactivar Wide Dynamic Range para evitar Ghosting
        if hasattr(request.ImagingSettings, 'WideDynamicRange') and request.ImagingSettings.WideDynamicRange is not None:
            request.ImagingSettings.WideDynamicRange.Mode = 'OFF'

        self.imaging_service.SetImagingSettings(request)
        print(f"[{self.ip}] Perfil NOCTURNO aplicado con éxito.")

    def set_day_profile(self):
        """Restaura el color y la autoexposición para vigilancia normal diurna."""
        print(f"[{self.ip}] Aplicando perfil DIURNO (Color, Auto Shutter)...")
        
        request = self.imaging_service.create_type('SetImagingSettings')
        request.VideoSourceToken = self.video_source_token
        request.ImagingSettings = self._get_current_settings()
        
        # Poner el filtro IR para bloquear la luz infrarroja (Visión en Color)
        request.ImagingSettings.IrCutFilter = 'ON'
        
        if hasattr(request.ImagingSettings, 'Exposure') and request.ImagingSettings.Exposure is not None:
            request.ImagingSettings.Exposure.Mode = 'AUTO'
            
        if hasattr(request.ImagingSettings, 'WideDynamicRange') and request.ImagingSettings.WideDynamicRange is not None:
            request.ImagingSettings.WideDynamicRange.Mode = 'ON'

        self.imaging_service.SetImagingSettings(request)
        print(f"[{self.ip}] Perfil DIURNO aplicado con éxito.")

def camera_schedule_daemon_astral(cam_ip, cam_port, cam_user, cam_pass, wsdl_dir="/usr/local/lib/python3.10/site-packages/wsdl/"):
    """
    Demonio astronómico para sincronización de perfiles ONVIF Día / Noche ALPR
    basado en las efemérides solares exactas de Zúrich (astral + zoneinfo).
    """
    # Instanciar el controlador ONVIF definido previamente
    controller = ONVIFImagingController(cam_ip, cam_port, cam_user, cam_pass, wsdl_dir=wsdl_dir)
    
    # 1. Cargar la base de datos astronómica y localizar Zúrich
    try:
        from astral.geocoder import database, lookup
        from astral.sun import sun
        from zoneinfo import ZoneInfo
    except ImportError:
        print("[CRON ERROR] Se requiere la librería 'astral'. Instale con: pip install astral")
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
    parser = argparse.ArgumentParser(description="Control de Perfiles Ópticos ONVIF (Día/Noche ALPR)")
    parser.add_argument("--ip", default="192.168.1.64", help="Dirección IP de la cámara IP")
    parser.add_argument("--port", type=int, default=80, help="Puerto ONVIF (default: 80 o 8000)")
    parser.add_argument("--user", default="admin", help="Usuario ONVIF")
    parser.add_argument("--password", default="admin123", help="Contraseña ONVIF")
    parser.add_argument("--mode", choices=["day", "night", "solar", "daemon"], default="night", help="Perfil o demonio a aplicar")
    parser.add_argument("--wsdl", default="/usr/local/lib/python3.10/site-packages/wsdl/", help="Ruta WSDL")
    
    args = parser.parse_args()

    try:
        if args.mode in ["solar", "daemon"]:
            camera_schedule_daemon_astral(
                cam_ip=args.ip,
                cam_port=args.port,
                cam_user=args.user,
                cam_pass=args.password,
                wsdl_dir=args.wsdl
            )
        else:
            controller = ONVIFImagingController(
                ip=args.ip,
                port=args.port,
                user=args.user,
                password=args.password,
                wsdl_dir=args.wsdl
            )
            if args.mode == "night":
                controller.set_night_profile_alpr()
            else:
                controller.set_day_profile()
    except KeyboardInterrupt:
        print("\n[ONVIF] Demonio solar detenido por el usuario.")
    except Exception as e:
        print(f"[ERROR] No se pudo configurar la cámara: {e}")
        sys.exit(1)
