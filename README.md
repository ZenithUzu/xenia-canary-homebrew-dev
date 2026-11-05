<p align="center">
    <a href="https://github.com/xenia-canary/xenia-canary/tree/canary_experimental/assets/icon">
        <img height="256px" src="https://raw.githubusercontent.com/xenia-canary/xenia/master/assets/icon/256.png" />
    </a>
</p>

<h1 align="center">Xenia Canary Homebrew Dev - Xbox 360 Emulator</h1>

Fork de [Xenia Canary](https://github.com/xenia-canary/xenia-canary) para desarrollar y probar juegos homebrew de Xbox 360 en el PC, sin consola. Incluye la red de [Xenia Canary Netplay](https://github.com/AdrianCassar/xenia-canary) y añade herramientas para probar conexiones y carpetas de juego.

## Qué añade

| Función | Para qué sirve |
|---|---|
| **Red real** | El juego puede usar sockets, DNS e Internet a través del PC, incluido HTTPS si trae su propia librería TLS. |
| **Live simulado** | [`tools/live_sim`](tools/live_sim/README.md) responde en local a las funciones de Live, como sesiones y jugadores, y registra cada petición. |
| **Pruebas de fallos** | El simulador puede añadir retardo o hacer fallar las rutas que elijas. |
| **Escritura en `game:\`** | `allow_game_relative_writes` viene activado. |
| **Carpetas automáticas** | `auto_create_game_dirs` crea las carpetas de `game:\` que el juego pide. |
| **Archivos faltantes** | El lanzador anota en `faltantes.txt` los archivos que el juego pidió y no encontró. |
| **Compatibilidad con [xSDK](https://github.com/ZenithUzu/xsdk)** | Xenia responde a los registros del controlador de pantalla que usa xSDK e implementa `GetTimeZoneInformation`. |

De Netplay también llegan las sesiones por Xenia Web Services, Systemlink, UPnP, amigos y XStorage. El aviso de actualizaciones viene desactivado porque apunta a las versiones de Netplay.

## Probar un juego

El lanzador funciona en Windows. Trabaja sobre una copia del juego en `build/live_sim/juegos`, sin tocar el original:

```bash
python tools/live_sim/lanzar_juego.py "C:\ruta\juego.xex"
```

Para que el juego tenga una sesión iniciada, importa los perfiles de otra instalación de Xenia la primera vez con `--perfil-desde "C:\ruta\otro_xenia"`. Las demás opciones están en la [guía de `tools/live_sim`](tools/live_sim/README.md).

## Compilar

Este fork aún no publica versiones compiladas. En Windows necesitas Visual Studio 2022 o posterior con C++, CMake, Windows 11 SDK, Python 3 de 64 bits y Vulkan SDK. Los detalles están en [docs/building.md](docs/building.md).

```bash
git submodule update --init --depth=1
python xenia-build.py build --config=Release --target=xenia-app
```

El ejecutable queda en `build\bin\Windows\Release\xenia_canary_netplay.exe`.

## Estado

Probado en una compilación Release para Windows:

| Prueba | Resultado |
|---|---|
| `net_probe`, incluida una petición HTTP real | 36 de 38 comprobaciones correctas; `XSessionStart` y `XSessionEnd` fallan porque la prueba no registra el arbitraje |
| AdvanXe360 | Abre, crea `Roms` y conecta con GitHub por HTTPS; la descarga de portadas no se ha probado en este fork |
| `sm64coopdx` | Crea `save`, abre la pantalla y dibuja su menú; pide la ROM, así que la partida y su red no se han probado |
| xDS360 | Abre la pantalla y presenta frames; pide `game.nds`, así que la emulación no se ha probado |

## Límites

- **No conecta con el Xbox Live real.** Live se simula en local o mediante un servidor de Xenia Web Services.
- **No permite jugar contra una Xbox 360 con juegos comerciales.** Xenia no implementa la red segura de la consola.
- **La conexión con una consola modificada no está probada.** Podría funcionar con homebrew que use sockets inseguros.
- **`auto_create_game_dirs` puede equivocarse.** Trata como carpeta cualquier ruta de `game:\` que no exista y no tenga extensión. Se desactiva con `--auto_create_game_dirs=false`.

## Créditos y licencia

Este proyecto se basa en Xenia, Xenia Canary y Xenia Canary Netplay. Los autores y las dependencias están en [CREDITS.md](CREDITS.md), y la licencia en [LICENSE](LICENSE).
