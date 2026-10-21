# ==============================================================================
# CASVMS - ONVIF Imaging & Shutter Controller for Industrial ALPR
# ==============================================================================
import os
import time
import logging
import threading
from typing import Optional, Dict, Any

logger = logging.getLogger("CASVMS.Gateway.ONVIF")

class ONVIFImagingController:
    """
    Controlador ONVIF para conmutación de perfiles ópticos de cámara (Día / Noche ALPR).
    
    Resuelve el problema de 'Motion Blur' y 'Blooming' en vigilancia nocturna de matrículas:
    - Modo Nocturno ALPR: Quita el filtro mecánico IR-Cut (IrCutFilter='OFF'), fuerza
      obturación ultrarrápida (1/1000s) para congelar vehículos en movimiento y desactiva
      el WDR para evitar imágenes fantasma (ghosting).
    - Modo Diurno: Activa el filtro IR-Cut (IrCutFilter='ON') para color natural, restaura
      exposición automática y reactiva el WDR.
    """

    def __init__(
        self,
        ip: str,
        port: int = 80,
        user: str = "admin",
        password: str = "admin123",
        wsdl_dir: Optional[str] = None
    ):
        self.ip = ip
        self.port = port
        self.user = user
        self.password = password
        
        # Detección de ruta de esquemas WSDL de ONVIF
        self.wsdl_dir = wsdl_dir or self._discover_wsdl_dir()
        
        self.cam = None
        self.media_service = None
        self.imaging_service = None
        self.video_source_token = None
        self._is_initialized = False

    def _discover_wsdl_dir(self) -> str:
        """Localiza el directorio WSDL estándar de python-onvif-zeep."""
        possible_dirs = [
            "/usr/local/lib/python3.10/site-packages/wsdl/",
            "/usr/lib/python3/dist-packages/wsdl/",
            os.path.join(os.path.dirname(__file__), "wsdl")
        ]
        for p in possible_dirs:
            if os.path.exists(p):
                return p
        return "/usr/local/lib/python3.10/site-packages/wsdl/"

    def connect(self) -> bool:
        """Inicializa los servicios Media e Imaging de ONVIF con tolerancia a fallos."""
        try:
            from onvif import ONVIFCamera

            logger.info(f"[{self.ip}] Conectando al servicio ONVIF ({self.ip}:{self.port})...")
            self.cam = ONVIFCamera(self.ip, self.port, self.user, self.password, self.wsdl_dir)
            
            # Servicios requeridos por especificación ONVIF Profile S / Profile T
            self.media_service = self.cam.create_media_service()
            self.imaging_service = self.cam.create_imaging_service()

            # Obtener el VideoSourceToken físico del sensor principal
            profiles = self.media_service.GetProfiles()
            if not profiles or len(profiles) == 0:
                raise ValueError("No se encontraron perfiles de vídeo en la cámara ONVIF.")

            self.video_source_token = profiles[0].VideoSourceConfiguration.SourceToken
            self._is_initialized = True
            logger.info(f"[{self.ip}] Conexión ONVIF exitosa (VideoSourceToken: {self.video_source_token}).")
            return True

        except ImportError:
            logger.warning(f"[{self.ip}] Librería onvif-zeep no disponible. Operando en modo emulación.")
            return False
        except Exception as e:
            logger.warning(f"[{self.ip}] Fallo conectando a cámara ONVIF: {str(e)}")
            self._is_initialized = False
            return False

    def _get_current_settings(self):
        """Retorna el objeto ImagingSettings actual de la cámara."""
        if not self._is_initialized and not self.connect():
            return None
        return self.imaging_service.GetImagingSettings(self.video_source_token)

    def set_night_profile_alpr(self) -> bool:
        """
        Fuerza visión infrarroja monocroma y obturación a 1/1000s para captura de matrículas sin blur.
        """
        logger.info(f"[{self.ip}] Aplicando perfil NOCTURNO ALPR (IR-Cut OFF, Shutter 1/1000s, WDR OFF)...")
        try:
            if not self._is_initialized and not self.connect():
                return False

            request = self.imaging_service.create_type('SetImagingSettings')
            request.VideoSourceToken = self.video_source_token
            request.ImagingSettings = self._get_current_settings()

            # 1. Filtro IR-Cut: 'OFF' retira físicamente el filtro mecánico para capturar luz infrarroja (B/N)
            request.ImagingSettings.IrCutFilter = 'OFF'

            # 2. Control de Exposición manual (1000 microsegundos = 1 ms = 1/1000s)
            if hasattr(request.ImagingSettings, 'Exposure') and request.ImagingSettings.Exposure is not None:
                request.ImagingSettings.Exposure.Mode = 'MANUAL'
                request.ImagingSettings.Exposure.ExposureTime = 1000  # 1/1000s para congelar vehículos
                request.ImagingSettings.Exposure.Gain = 20           # Ganancia controlada para evitar ruido térmico

            # 3. Desactivar Wide Dynamic Range (WDR) para evitar ghosting en objetos en movimiento
            if hasattr(request.ImagingSettings, 'WideDynamicRange') and request.ImagingSettings.WideDynamicRange is not None:
                request.ImagingSettings.WideDynamicRange.Mode = 'OFF'

            self.imaging_service.SetImagingSettings(request)
            logger.info(f"[{self.ip}] Perfil NOCTURNO ALPR aplicado con éxito.")
            return True

        except Exception as e:
            logger.error(f"[{self.ip}] Error aplicando perfil nocturno ONVIF: {str(e)}")
            return False

    def set_day_profile(self) -> bool:
        """
        Restaura el color y la autoexposición para vigilancia normal diurna.
        """
        logger.info(f"[{self.ip}] Aplicando perfil DIURNO (Color, Shutter Auto, WDR ON)...")
        try:
            if not self._is_initialized and not self.connect():
                return False

            request = self.imaging_service.create_type('SetImagingSettings')
            request.VideoSourceToken = self.video_source_token
            request.ImagingSettings = self._get_current_settings()

            # 1. Filtro IR-Cut: 'ON' bloquea el infrarrojo para lograr balance de color natural diurno
            request.ImagingSettings.IrCutFilter = 'ON'

            # 2. Restaurar control de exposición automática
            if hasattr(request.ImagingSettings, 'Exposure') and request.ImagingSettings.Exposure is not None:
                request.ImagingSettings.Exposure.Mode = 'AUTO'

            # 3. Activar Wide Dynamic Range para equilibrar sombras y cielo
            if hasattr(request.ImagingSettings, 'WideDynamicRange') and request.ImagingSettings.WideDynamicRange is not None:
                request.ImagingSettings.WideDynamicRange.Mode = 'ON'

            self.imaging_service.SetImagingSettings(request)
            logger.info(f"[{self.ip}] Perfil DIURNO aplicado con éxito.")
            return True

        except Exception as e:
            logger.error(f"[{self.ip}] Error aplicando perfil diurno ONVIF: {str(e)}")
            return False

    def apply_profile_async(self, mode: str) -> None:
        """Aplica el perfil de forma asíncrona en un hilo daemon para no bloquear el motor VMS."""
        target_fn = self.set_night_profile_alpr if mode.lower() == "night" else self.set_day_profile
        threading.Thread(
            target=target_fn,
            daemon=True,
            name=f"ONVIF-Profile-{mode.upper()}-{self.ip}"
        ).start()

class ONVIFScheduleDaemon:
    """
    Hilo daemon astronómico para conmutación automática de perfiles ONVIF Día / Noche ALPR.
    
    Calcula la posición solar exacta para la localización geográfica (ej. Zúrich) usando 'astral'.
    Aplica márgenes de seguridad para el crepúsculo (activando el modo noche 30 min antes del anochecer).
    Evalúa cada 5 minutos (300s) para minimizar ciclos de CPU.
    """

    def __init__(
        self,
        cam_ip: Optional[str] = None,
        cam_port: Optional[int] = None,
        cam_user: Optional[str] = None,
        cam_pass: Optional[str] = None,
        city_name: str = "Zurich",
        timezone_str: str = "Europe/Zurich",
        twilight_offset_minutes: int = 30,
        day_hour: int = 7,       # Fallback si no hay soporte astral
        night_hour: int = 19,    # Fallback si no hay soporte astral
        check_interval_seconds: float = 300.0, # 5 minutos para cálculo solar
        wsdl_dir: Optional[str] = None
    ):
        self.cam_ip = cam_ip or os.getenv("ONVIF_CAMERA_IP", "192.168.1.64")
        self.cam_port = cam_port or int(os.getenv("ONVIF_CAMERA_PORT", "80"))
        self.cam_user = cam_user or os.getenv("ONVIF_CAMERA_USER", "admin")
        self.cam_pass = cam_pass or os.getenv("ONVIF_CAMERA_PASS", "admin123")
        
        self.city_name = os.getenv("ONVIF_LOCATION_CITY", city_name)
        self.timezone_str = os.getenv("ONVIF_TIMEZONE", timezone_str)
        self.twilight_offset = int(os.getenv("ONVIF_TWILIGHT_OFFSET_MINUTES", str(twilight_offset_minutes)))
        
        self.day_hour = int(os.getenv("ONVIF_DAY_HOUR", str(day_hour)))
        self.night_hour = int(os.getenv("ONVIF_NIGHT_HOUR", str(night_hour)))
        self.check_interval = check_interval_seconds

        self.controller = ONVIFImagingController(
            ip=self.cam_ip,
            port=self.cam_port,
            user=self.cam_user,
            password=self.cam_pass,
            wsdl_dir=wsdl_dir
        )

        self._stop_event = threading.Event()
        self._thread: Optional[threading.Thread] = None
        self.current_mode: Optional[str] = None

    def start(self) -> None:
        """Inicia el daemon astronómico en segundo plano."""
        if self._thread is not None and self._thread.is_alive():
            return

        self._stop_event.clear()
        self._thread = threading.Thread(
            target=self._run_loop,
            daemon=True,
            name=f"ONVIF-Solar-Scheduler-{self.cam_ip}"
        )
        self._thread.start()
        logger.info(
            f"ONVIF Solar Daemon iniciado para {self.cam_ip} en {self.city_name} "
            f"({self.timezone_str}, Offset crepúsculo: {self.twilight_offset} min, Ciclo: {self.check_interval}s)."
        )

    def _determine_solar_mode(self) -> str:
        """Calcula si actualmente es de día o de noche según la posición solar astronómica."""
        import datetime
        try:
            from astral.geocoder import database, lookup
            from astral.sun import sun
            from zoneinfo import ZoneInfo

            db = database()
            city = lookup(self.city_name, db)
            tz = ZoneInfo(self.timezone_str)

            # Hora actual Timezone-Aware
            now = datetime.datetime.now(tz)

            # Eventos solares exactos para el día de hoy
            s = sun(city.observer, date=now.date(), tzinfo=tz)
            sunrise = s["sunrise"]
            sunset = s["sunset"]

            # Margen de seguridad: activar noche 30 min antes del anochecer y esperar 30 min tras amanecer
            dawn_threshold = sunrise + datetime.timedelta(minutes=self.twilight_offset)
            dusk_threshold = sunset - datetime.timedelta(minutes=self.twilight_offset)

            if dawn_threshold <= now < dusk_threshold:
                return "DAY"
            else:
                return "NIGHT"

        except Exception as e:
            # Fallback a ventana horaria estática si astral no está disponible
            now = datetime.datetime.now()
            if self.day_hour <= now.hour < self.night_hour:
                return "DAY"
            return "NIGHT"

    def _run_loop(self) -> None:
        """Bucle principal evaluando la posición solar cada 5 minutos."""
        while not self._stop_event.is_set():
            expected_mode = self._determine_solar_mode()

            # Conmutar únicamente si hay cambio de estado
            if self.current_mode != expected_mode:
                logger.info(
                    f"[ONVIF SOLAR] Sincronización astronómica: Transición detectada -> "
                    f"Cambiando a {expected_mode} en {self.cam_ip} ({self.city_name})..."
                )
                try:
                    success = False
                    if expected_mode == "DAY":
                        success = self.controller.set_day_profile()
                    else:
                        success = self.controller.set_night_profile_alpr()

                    if success:
                        self.current_mode = expected_mode
                        logger.info(f"[ONVIF SOLAR] Perfil {expected_mode} aplicado con éxito a {self.cam_ip}.")
                    else:
                        logger.warning(f"[ONVIF SOLAR] No se pudo aplicar perfil {expected_mode} en {self.cam_ip}.")

                except Exception as e:
                    logger.error(f"[ONVIF SOLAR] Excepción comunicando con {self.cam_ip}: {e}")

            # Espera no bloqueante: se interrumpe al instante si se solicita stop()
            interrupted = self._stop_event.wait(timeout=self.check_interval)
            if interrupted or self._stop_event.is_set():
                break

    def stop(self) -> None:
        """Detiene limpiamente el daemon sin esperas."""
        self._stop_event.set()
        logger.info(f"ONVIF Solar Daemon para {self.cam_ip} detenido.")

def camera_schedule_daemon_astral(cam_ip: str, cam_port: int, cam_user: str, cam_pass: str) -> None:
    """Función de entrada directa compatible con el script del usuario."""
    daemon = ONVIFScheduleDaemon(
        cam_ip=cam_ip,
        cam_port=cam_port,
        cam_user=cam_user,
        cam_pass=cam_pass,
        check_interval_seconds=300.0
    )
    daemon._run_loop()


