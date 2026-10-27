# Mi Inicio

Pantalla de inicio personalizada para una TV **Hisense con VIDAA**. Es una página
web que funciona como launcher: reloj, saludo, tus apps y accesos, navegable con
el control (D-pad), con fondo animado.

Todo el proyecto vive aquí: la página, el puente que abre las apps nativas, el
script que instala el tile en la TV, y esta guía. Así no depende de archivos
sueltos en una PC.

## Qué hace y qué no (importante)

VIDAA solo corre apps web. Esta página se instala como un tile más en el inicio.
Desde dentro, una página web **no puede** abrir apps nativas (Netflix, YouTube…),
cambiar de entrada ni abrir Ajustes. Eso solo se puede por el canal de control de
la TV (MQTT), que necesita un certificado y una sesión que viven en una máquina de
tu red local. Por eso hay dos modos:

| | Dónde corre | Qué abre |
|---|---|---|
| **Con puente** (recomendado) | una PC/mini-PC de tu red, siempre encendida mientras ves TV | apps nativas con tu sesión + cambio de HDMI |
| **Solo web** (GitHub Pages) | nada, está hospedado | solo las versiones web de las apps, sin tus sesiones |

La misma página sirve para los dos: si la abre el puente (http) usa el puente; si
la abres por https (GitHub Pages) cae al modo web. El cambio es automático.

GitHub no puede alcanzar tu TV, así que el puente **tiene que correr en tu red**.
Hoy es tu PC; mañana podría ser una Raspberry Pi siempre encendida.

## Estructura

```
index.html        la página del launcher (GitHub Pages la sirve en la raíz)
icon.png          ícono del tile
bridge/
  bridge.py       el puente: sirve la página por http y manda comandos a la TV
  config.json     tu nombre para el saludo
  iniciar.bat     doble clic para arrancar el puente en Windows
  requirements.txt
tools/
  tile_manage.py  instala / revisa / quita el tile y lista las apps de la TV
```

## Requisitos

- Python 3 (en el PATH) y `pip install -r bridge/requirements.txt` (paho-mqtt).
- [Sidee](https://github.com/Empi9245/Sidee) instalado y la TV **emparejada** con él.
  Sidee genera, en tu equipo, la sesión (`~/.sidee/session.json`) y el certificado
  (`<Sidee>/core/tv-client.bundle`) que el puente reutiliza. **Nada de eso está en
  este repo ni debe subirse** (son credenciales; ver `.gitignore`).

## Puesta en marcha (una vez)

1. **Empareja la TV con Sidee.** Abre Sidee → *Find TV* → *Request code* → escribe
   en Sidee el PIN que aparece en la TV → *Confirm*.
2. **Clona este repo** e instala dependencias:
   ```
   git clone https://github.com/FrankJMinor/mi-inicio-tv.git
   pip install -r mi-inicio-tv/bridge/requirements.txt
   ```
3. **Arranca el puente:** doble clic en `bridge/iniciar.bat` (o `python bridge/bridge.py`).
   Anota la dirección que imprime, por ejemplo `http://192.168.100.52:8080/`.
4. **Instala el tile en la TV:**
   ```
   python tools/tile_manage.py install
   ```
   Detecta la IP de la PC sola y registra el tile apuntando al puente.
5. En la TV, abre **"Mi Inicio"** desde tus apps.

## Uso diario

- Deja `bridge/iniciar.bat` abierto mientras uses el launcher. Si lo cierras, los
  tiles mostrarán "El puente no responde".
- Cambia el nombre del saludo en `bridge/config.json` y reabre el tile.
- Edita el diseño en `index.html`; el puente lo sirve al instante (solo recarga el
  tile). Si cambias `bridge.py`, reinicia el puente.

## Herramientas

```
python tools/tile_manage.py check            ¿el tile está instalado?
python tools/tile_manage.py install          instalarlo (no pisa el que ya está)
python tools/tile_manage.py dump             lista todas las apps de la TV (ids/url)
python tools/tile_manage.py launch netflix   abre una app para probar
```

## Notas y límites

- **La IP de la PC** queda guardada en el tile al instalarlo. Si cambia, borra el
  tile en la TV (mantén OK sobre él → Eliminar) y corre `install` de nuevo. Fíjala
  en tu router para que no cambie.
- **Reinstalar no actualiza el ícono ni la URL** de un tile que ya existe (límite de
  VIDAA). Para cambiarlos, borra el tile en la TV y vuelve a instalar.
- Los **ids de apps** en `bridge.py` y `tools/tile_manage.py` son los de este
  modelo. Si en otra TV una app no abre, corre `dump` y ajusta el id.
- El token de acceso dura ~2 días; el puente lo renueva solo usando la lógica de
  Sidee. Si Sidee deja de reconocer la TV, vuelve a emparejar.

## Crédito

El emparejamiento y el certificado los provee [Sidee](https://github.com/Empi9245/Sidee).
Este repo solo reutiliza esa sesión local para controlar tu propia TV.
