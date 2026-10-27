"""Revisa, instala o quita el tile 'Mi Inicio' en la TV, y lista las apps de la TV.

Reutiliza el emparejamiento de Sidee (~/.sidee/session.json) y su certificado
(SIDEE_DIR/core/tv-client.bundle). Sidee tiene que estar instalado y la TV
emparejada.

Uso:
  python tile_manage.py check      -> informa si el tile existe
  python tile_manage.py install    -> instala si no existe (no pisa el que ya esta)
  python tile_manage.py dump       -> lista todas las apps de la TV con sus ids/url
  python tile_manage.py launch <clave>  -> abre una app (netflix, prime, youtube...)

Variables de entorno opcionales:
  SIDEE_DIR   carpeta de Sidee (por defecto ~/Desktop/sidee-windows/Sidee)
  BRIDGE_IP   IP del puente para el tile (por defecto se detecta sola)
  BRIDGE_PORT puerto del puente (por defecto 8080)
"""
import base64
import json
import os
import socket
import ssl
import sys
import tempfile
import threading
import time
import zlib

import paho.mqtt.client as mqtt

NAME = "Mi Inicio"
APPID = "miiniciodebug"

SESSION = os.path.join(os.path.expanduser("~"), ".sidee", "session.json")
SIDEE_DIR = os.environ.get(
    "SIDEE_DIR", os.path.join(os.path.expanduser("~"), "Desktop", "sidee-windows", "Sidee"))
BUNDLE = os.path.join(SIDEE_DIR, "core", "tv-client.bundle")
PORT = os.environ.get("BRIDGE_PORT", "8080")

# Las mismas apps que conoce el puente, para "launch".
APPS = {
    "netflix": ("1", "Netflix", "netflix"),
    "prime": ("2", "Prime Video", "amazon"),
    "youtube": ("3", "YouTube", "youtube"),
    "disney": ("295", "Disney+", "https://cd-dmgz.bamgrid.com/bbd/hisense_tv/index.html"),
    "hbo": ("2378", "HBO Max", "https://vidaa.play.max.com/"),
    "crunchyroll": ("2372", "Crunchyroll", "https://www.crunchyroll.com/tetsuo/hisense-vidaa/"),
    "vix": ("2152", "VIX", "https://webvidaa.vix.com/"),
}


def lan_ip():
    s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    try:
        s.connect(("10.255.255.255", 1))
        return s.getsockname()[0]
    except OSError:
        return "127.0.0.1"
    finally:
        s.close()


def load_cert():
    blob = open(BUNDLE, "rb").read()
    data = zlib.decompress(bytes(b ^ b"k3"[i % 2] for i, b in enumerate(base64.b85decode(blob))))
    m = b"-----END CERTIFICATE-----"
    i = data.find(m) + len(m)
    return data[:i] + b"\n", data[i:].strip() + b"\n"


def connect():
    if not os.path.isfile(SESSION):
        sys.exit("No hay sesion de Sidee. Empareja la TV con Sidee primero.")
    if not os.path.isfile(BUNDLE):
        sys.exit(f"No encuentro el certificado en {BUNDLE}. Revisa SIDEE_DIR.")
    s = json.load(open(SESSION, encoding="utf-8"))
    cert_pem, key_pem = load_cert()

    state = {"rc": None, "msgs": []}
    ev = threading.Event()

    def on_connect(c, u, f, rc, *a):
        state["rc"] = getattr(rc, "value", rc)
        ev.set()

    def on_message(c, u, msg):
        state["msgs"].append((msg.topic, msg.payload.decode("utf-8", "replace")))

    try:
        client = mqtt.Client(mqtt.CallbackAPIVersion.VERSION1, client_id=s["client_id"],
                             protocol=mqtt.MQTTv311, reconnect_on_failure=False)
    except Exception:
        client = mqtt.Client(client_id=s["client_id"], protocol=mqtt.MQTTv311)
    ctx = ssl.SSLContext(ssl.PROTOCOL_TLS_CLIENT)
    ctx.check_hostname = False
    ctx.verify_mode = ssl.CERT_NONE
    with tempfile.TemporaryDirectory() as d:
        cp, kp = os.path.join(d, "c.pem"), os.path.join(d, "k.pem")
        open(cp, "wb").write(cert_pem)
        open(kp, "wb").write(key_pem)
        ctx.load_cert_chain(cp, kp)
    client.tls_set_context(ctx)
    client.tls_insecure_set(True)
    client.username_pw_set(s["username"], s["access_token"])
    client.on_connect = on_connect
    client.on_message = on_message
    client.connect(s["host"], 36669, 30)
    client.loop_start()
    ev.wait(10)
    if state["rc"] != 0:
        client.loop_stop()
        sys.exit(f"No conecto (rc={state['rc']}). Si el token vencio, reempareja en Sidee.")
    topics = {
        "ui": f"/remoteapp/tv/ui_service/{s['client_id']}/",
        "reply": f"/remoteapp/mobile/{s['client_id']}/ui_service/data/applist",
    }
    return client, topics, state


def fetch_apps(client, topics, state):
    since = len(state["msgs"])
    client.publish(topics["ui"] + "actions/applist", "0")
    end = time.time() + 8
    while time.time() < end:
        for t, p in state["msgs"][since:]:
            if t.endswith("ui_service/data/applist"):
                try:
                    return json.loads(p)
                except Exception:
                    return []
        time.sleep(0.3)
    return []


def find_tile(apps):
    for a in apps:
        if isinstance(a, dict) and str(a.get("appId", "")).lower() == APPID.lower():
            return a
    return None


def main():
    mode = sys.argv[1] if len(sys.argv) > 1 else "check"
    client, topics, state = connect()
    client.subscribe([(topics["reply"], 0)])
    time.sleep(0.4)
    try:
        if mode == "dump":
            for a in fetch_apps(client, topics, state):
                if isinstance(a, dict):
                    print(a.get("name"), "|", a.get("appId"), "|",
                          a.get("url") or a.get("appUrl") or a.get("URL"))
            return
        if mode == "launch":
            key = sys.argv[2] if len(sys.argv) > 2 else ""
            spec = APPS.get(key)
            if not spec:
                sys.exit(f"app desconocida: {key}. Opciones: {', '.join(APPS)}")
            app_id, nm, url = spec
            client.publish(topics["ui"] + "actions/launchapp", json.dumps(
                {"appId": app_id, "name": nm, "url": url, "urlType": 37, "appName": nm, "appUrl": url}))
            time.sleep(3)
            print("lanzado:", nm)
            return

        tile = find_tile(fetch_apps(client, topics, state))
        if mode == "check":
            print("TILE EXISTE" if tile else "TILE NO EXISTE", "->", tile.get("url") if tile else "")
            return
        if mode == "install":
            if tile:
                print("Ya existe (apunta al puente, sirve la version actual). No lo reinstalo.")
                print("Para forzar imagen/URL nuevas: borra el tile en la TV (manten OK, Eliminar) y repite.")
                return
            ip = os.environ.get("BRIDGE_IP", lan_ip())
            url = f"http://{ip}:{PORT}/"
            image = f"http://{ip}:{PORT}/icon.png"
            payload = json.dumps({"type": "app_install", "app_info": {
                "Title": NAME, "StoreType": 99, "mediaId": APPID, "Id": APPID,
                "Image": image, "URL": url, "configUrlDownload": 0, "configUrl": ""}})
            client.publish(topics["ui"] + "actions/uievent", payload)
            print(f"instalando tile -> {url}")
            time.sleep(8)
            tile = find_tile(fetch_apps(client, topics, state))
            print("INSTALADO OK" if tile else "NO aparecio tras instalar")
            return
        sys.exit(f"modo desconocido: {mode}")
    finally:
        client.loop_stop()
        client.disconnect()


if __name__ == "__main__":
    main()
