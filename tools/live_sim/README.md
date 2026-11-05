# Live Sim

Herramientas para probar la red de juegos homebrew en esta versión de Xenia.

- `live_sim_server.py`: servidor local que responde a la API que usa `XLiveAPI`.
  Solo escucha en `127.0.0.1` y guarda cada petición en `live_sim_log.jsonl`.
- `lanzar_juego.py`: copia el juego a `build/live_sim/juegos/<nombre>`, inicia el
  simulador, abre Xenia y anota en `faltantes.txt` los archivos que no encontró.
- `net_probe/`: `.xex` de prueba de red. Se compila con el XDK y VS2010; el
  resultado no se incluye en este repositorio. Prueba Live, sockets, sesiones y
  una petición HTTP real a `thumbnails.libretro.com`.

## Uso

```bash
python tools/live_sim/lanzar_juego.py "C:\ruta\juego.xex" --perfil-desde "C:\ruta\otro_xenia"
```

`--perfil-desde` solo hace falta la primera vez: copia los perfiles y la
configuración de otra instalación.

El simulador acepta `--fallar REGEX` para hacer fallar rutas y `--latencia MS`
para añadir retardo.

## Ajustes de Xenia

| Ajuste | Valor en esta versión | Efecto |
|---|---|---|
| `allow_game_relative_writes` | `true` | Permite escribir en `game:\` |
| `auto_create_game_dirs` | `true` | Crea carpetas de `game:\` cuando el juego las consulta o escribe dentro de ellas |

`auto_create_game_dirs` trata como carpeta cualquier ruta de `game:\` que no exista
y no tenga extensión, así que un archivo sin extensión podría crearse como carpeta.
Si un juego lo sufre, desactívalo con `--auto_create_game_dirs=false`.
