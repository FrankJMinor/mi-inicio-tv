"""Puente Mi Inicio -> TV Hisense VIDAA.

Sirve la pagina "Mi Inicio" por http en la red local y, cuando se toca un tile,
le manda a la TV el comando para abrir la app nativa (con tu sesion) o cambiar
de entrada. Reutiliza el emparejamiento que hizo Sidee (~/.sidee/session.json) y
su logica de renovacion de token, asi que Sidee tiene que estar instalado y la TV
emparejada.

Variables de entorno opcionales:
  PORT       puerto http (por defecto 8080)
  SIDEE_DIR  carpeta donde esta Sidee (por defecto ~/Desktop/sidee-windows/Sidee)
"""
import ipaddress
import json
import os
import sys
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import parse_qs, urlparse

SIDEE_DIR = os.environ.get(
    "SIDEE_DIR", os.path.join(os.path.expanduser("~"), "Desktop", "sidee-windows", "Sidee"))
sys.path.insert(0, SIDEE_DIR)
try:
    from core import client as sidee
    from core import protocol
except ImportError:
    sys.exit(f"No encuentro Sidee en {SIDEE_DIR}. Instalalo y empareja la TV, "
             f"o define la variable SIDEE_DIR con su ruta.")

HERE = os.path.dirname(os.path.abspath(__file__))
# La pagina y el icono viven en la raiz del repo (un nivel arriba de bridge/);
# si se corre en una carpeta plana, estan junto a este script.
ROOT = os.path.dirname(HERE) if os.path.isfile(os.path.join(os.path.dirname(HERE), "index.html")) else HERE
PORT = int(os.environ.get("PORT", "8080"))

# Archivos estaticos: (carpeta, nombre, tipo de contenido).
STATIC = {
    "/": (ROOT, "index.html", "text/html; charset=utf-8"),
    "/index.html": (ROOT, "index.html", "text/html; charset=utf-8"),
    "/icon.png": (ROOT, "icon.png", "image/png"),
    "/config.json": (HERE, "config.json", "application/json; charset=utf-8"),
}

# Solo se pueden lanzar estas apps (id, nombre, url tal como las registra la TV).
# Los ids pueden variar entre modelos: mira tools/tile_manage.py "dump" para los tuyos.
APPS = {
    "netflix": ("1", "Netflix", "netflix"),
    "prime": ("2", "Prime Video", "amazon"),
    "youtube": ("3", "YouTube", "youtube"),
    "disney": ("295", "Disney+", "https://cd-dmgz.bamgrid.com/bbd/hisense_tv/index.html"),
    "hbo": ("2378", "HBO Max", "https://vidaa.play.max.com/"),
    "crunchyroll": ("2372", "Crunchyroll", "https://www.crunchyroll.com/tetsuo/hisense-vidaa/"),
    "vix": ("2152", "VIX", "https://webvidaa.vix.com/"),
}
# Entradas que la TV reporta en su lista de fuentes.
SOURCES = {"TV": "TV", "HDMI1": "HDMI1", "HDMI2": "HDMI2", "AVS": "AV"}


def stamp():
    return time.strftime("%H:%M:%S")


def send_to_tv(topic_suffix, payload, settle=1.5):
    def op(sess, topics):
        sess.publish(topics["ui"] + topic_suffix, payload)
        time.sleep(settle)  # deja salir el mensaje antes de cerrar la conexion
    sidee.run_with_session(op)


class Handler(BaseHTTPRequestHandler):
    server_version = "MiInicioBridge/1.0"

    def log_message(self, fmt, *args):
        print(f"[{stamp()}] {self.client_address[0]} {fmt % args}")

    def _reply(self, code, body, ctype="application/json; charset=utf-8"):
        data = body if isinstance(body, bytes) else json.dumps(body).encode()
        self.send_response(code)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(data)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(data)

    def _lan_only(self):
        try:
            return ipaddress.ip_address(self.client_address[0]).is_private
        except ValueError:
            return False

    def do_GET(self):
        if not self._lan_only():
            return self._reply(403, {"ok": False, "error": "solo red local"})
        path = urlparse(self.path).path
        if path == "/api/ping":
            return self._reply(200, {"ok": True})
        if path in STATIC:
            folder, name, ctype = STATIC[path]
            try:
                with open(os.path.join(folder, name), "rb") as f:
                    return self._reply(200, f.read(), ctype)
            except OSError:
                return self._reply(404, {"ok": False, "error": f"falta {name}"})
        self._reply(404, {"ok": False, "error": "no existe"})

    def do_POST(self):
        if not self._lan_only():
            return self._reply(403, {"ok": False, "error": "solo red local"})
        url = urlparse(self.path)
        query = parse_qs(url.query)
        try:
            if url.path == "/api/launch":
                spec = APPS.get(query.get("app", [""])[0])
                if not spec:
                    return self._reply(404, {"ok": False, "error": "app desconocida"})
                app_id, name, app_url = spec
                print(f"[{stamp()}] abrir {name}")
                send_to_tv("actions/launchapp", protocol.launch_payload(app_id, name, app_url))
                return self._reply(200, {"ok": True})
            if url.path == "/api/source":
                source_id = query.get("id", [""])[0]
                if source_id not in SOURCES:
                    return self._reply(404, {"ok": False, "error": "entrada desconocida"})
                print(f"[{stamp()}] cambiar a {source_id}")
                send_to_tv("actions/changesource",
                           json.dumps({"sourceid": source_id, "sourcename": source_id}))
                return self._reply(200, {"ok": True})
            return self._reply(404, {"ok": False, "error": "no existe"})
        except Exception as e:  # la TV apagada o sin red llega aqui
            print(f"[{stamp()}] error: {e}")
            return self._reply(502, {"ok": False, "error": "la TV no respondio"})


def lan_ip():
    import socket
    s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    try:
        s.connect(("10.255.255.255", 1))
        return s.getsockname()[0]
    except OSError:
        return "127.0.0.1"
    finally:
        s.close()


if __name__ == "__main__":
    if not sidee.Session().load_or_none():
        sys.exit("No hay una TV emparejada. Abre Sidee y empareja la TV primero.")
    server = ThreadingHTTPServer(("0.0.0.0", PORT), Handler)
    ip = lan_ip()
    print(f"Puente listo. Direccion para la TV: http://{ip}:{PORT}/")
    print(f"Instala el tile con:  python ../tools/tile_manage.py install")
    print("Deja esta ventana abierta mientras uses Mi Inicio. Ctrl+C para salir.")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
