# ==============================================================================
# CASVMS - ONVIF WS-Discovery & RTSP Diagnostics Service
# ==============================================================================
import re
import time
import socket
import uuid
import logging
from typing import List, Dict, Any

logger = logging.getLogger("CASVMS.Discovery")

def discover_onvif_devices(timeout: float = 2.5) -> List[Dict[str, Any]]:
    """
    Realiza un sondeo WS-Discovery estándar (UDP Multicast 239.255.255.250:3702)
    para descubrir cámaras y dispositivos ONVIF en la red local.
    """
    discovered: List[Dict[str, Any]] = []
    seen_ips = set()

    probe_uuid = str(uuid.uuid4())
    soap_probe = f"""<?xml version="1.0" encoding="utf-8"?>
<Envelope xmlns:dn="http://www.onvif.org/ver10/network/wsdl"
          xmlns="http://www.w3.org/2003/05/soap-envelope">
  <Header>
    <wsa:MessageID xmlns:wsa="http://schemas.xmlsoap.org/ws/2004/08/addressing">uuid:{probe_uuid}</wsa:MessageID>
    <wsa:To xmlns:wsa="http://schemas.xmlsoap.org/ws/2004/08/addressing">urn:schemas-xmlsoap-org:ws:2005:04:discovery</wsa:To>
    <wsa:Action xmlns:wsa="http://schemas.xmlsoap.org/ws/2004/08/addressing">http://schemas.xmlsoap.org/ws/2005/04/discovery/Probe</wsa:Action>
  </Header>
  <Body>
    <Probe xmlns="http://schemas.xmlsoap.org/ws/2005/04/discovery">
      <Types>dn:NetworkVideoTransmitter</Types>
    </Probe>
  </Body>
</Envelope>"""

    try:
        sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM, socket.IPPROTO_UDP)
        sock.setsockopt(socket.SOL_SOCKET, socket.SO_BROADCAST, 1)
        sock.settimeout(timeout)

        # Enviar sondeo a multicast ONVIF
        sock.sendto(soap_probe.encode("utf-8"), ("239.255.255.250", 3702))
        
        start_time = time.time()
        while time.time() - start_time < timeout:
            try:
                data, addr = sock.recvfrom(65535)
                ip = addr[0]
                if ip in seen_ips:
                    continue
                seen_ips.add(ip)

                xml_str = data.decode("utf-8", errors="ignore")
                
                # Extraer XAddrs si existen
                xaddrs = ""
                xaddr_match = re.search(r"<(?:\w+:)?XAddrs>(.*?)</(?:\w+:)?XAddrs>", xml_str)
                if xaddr_match:
                    xaddrs = xaddr_match.group(1).strip()

                # Extraer modelo / fabricante si existe en scopes
                model_name = "Cámara ONVIF"
                scopes_match = re.search(r"<(?:\w+:)?Scopes>(.*?)</(?:\w+:)?Scopes>", xml_str)
                if scopes_match:
                    scopes = scopes_match.group(1)
                    # Buscar patrones comunes onvif://www.onvif.org/name/... o /hardware/...
                    hw_match = re.search(r"hardware/([^ \t\r\n]+)", scopes)
                    name_match = re.search(r"name/([^ \t\r\n]+)", scopes)
                    if name_match:
                        model_name = name_match.group(1).replace("%20", " ")
                    elif hw_match:
                        model_name = hw_match.group(1).replace("%20", " ")

                device_info = {
                    "ip": ip,
                    "service_url": xaddrs.split()[0] if xaddrs else f"http://{ip}/onvif/device_service",
                    "model": model_name,
                    "suggested_rtsp": f"rtsp://admin:admin123@{ip}:554/cam/realmonitor?channel=1&subtype=0",
                    "discovered_at": time.time()
                }
                discovered.append(device_info)
                logger.info(f"Dispositivo ONVIF detectado en {ip}: {model_name}")

            except socket.timeout:
                break
            except Exception as rx_err:
                logger.warning(f"Error recibiendo respuesta WS-Discovery: {rx_err}")
                break

    except Exception as e:
        logger.error(f"Error ejecutando WS-Discovery: {e}")
    finally:
        try:
            sock.close()
        except Exception:
            pass

    return discovered


def test_rtsp_connection(rtsp_url: str, timeout_seconds: float = 3.0) -> Dict[str, Any]:
    """
    Verifica la conectividad de un stream RTSP o sintético,
    obteniendo resolución, FPS y estado de salud.
    """
    if not rtsp_url:
        return {"online": False, "error": "URL de stream no proporcionada."}

    if rtsp_url.lower() == "demo":
        return {
            "online": True,
            "stream_type": "synthetic_simulation",
            "resolution": "1280x720",
            "fps": 25.0,
            "latency_ms": 1.2,
            "message": "Stream de simulación industrial activo (Zero-Config)."
        }

    # Probar apertura rápida con OpenCV
    try:
        import cv2
        t0 = time.time()
        # En Linux/Docker usamos timeout en ffmpeg
        os.environ["OPENCV_FFMPEG_CAPTURE_OPTIONS"] = f"timeout;{int(timeout_seconds * 1000000)}"
        cap = cv2.VideoCapture(rtsp_url, cv2.CAP_FFMPEG)
        
        if not cap.isOpened():
            return {
                "online": False,
                "error": "No se pudo establecer conexión RTSP con la cámara (verifique IP, credenciales y puerto 554)."
            }

        ret, frame = cap.read()
        latency = round((time.time() - t0) * 1000, 1)
        
        if not ret or frame is None:
            cap.release()
            return {
                "online": False,
                "error": "Conexión establecida pero no se reciben frames de vídeo."
            }

        h, w = frame.shape[:2]
        fps = cap.get(cv2.CAP_PROP_FPS) or 25.0
        cap.release()

        return {
            "online": True,
            "resolution": f"{w}x{h}",
            "fps": round(fps, 1),
            "latency_ms": latency,
            "message": "Stream RTSP en línea y decodificando correctamente."
        }

    except Exception as e:
        return {
            "online": False,
            "error": f"Error verificando stream RTSP: {str(e)}"
        }
