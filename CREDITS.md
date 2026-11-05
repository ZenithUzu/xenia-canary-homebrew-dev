# Créditos

Esta versión para desarrollo homebrew se basa en el trabajo de estos proyectos.
Sus commits se conservan en el historial, con sus autores originales.

| Proyecto | Autores | Aporta | Licencia |
|---|---|---|---|
| [Xenia](https://github.com/xenia-project/xenia) | Ben Vanik y colaboradores | El emulador | BSD de 3 cláusulas ([LICENSE](LICENSE)) |
| [Xenia Canary](https://github.com/xenia-canary/xenia-canary) | Equipo y colaboradores de Xenia Canary | Base de este fork | BSD de 3 cláusulas |
| [Xenia Canary Netplay](https://github.com/AdrianCassar/xenia-canary) | Adrian Cassar y colaboradores | `XLiveAPI`, red, sesiones, QoS, XHTTP y UPnP, integrados desde `netplay_canary_experimental` | BSD de 3 cláusulas |
| [Xenia Web Services](https://github.com/AdrianCassar/Xenia-WebServices) | Adrian Cassar y colaboradores | Servicio cuya API imita `tools/live_sim` desde el lado del cliente; no se copia su código | Ver su repositorio |

## Dependencias añadidas con Netplay

Se incluyen como submódulos en `third_party`, cada uno con su propia licencia:

- [libcurl](https://github.com/curl/curl)
- [miniupnp](https://github.com/miniupnp/miniupnp)
- [wolfSSL](https://github.com/wolfSSL/wolfssl)

wolfSSL se ofrece bajo GPL o con licencia comercial. Antes de publicar binarios,
revisa qué obligaciones añade la versión incluida.

## Herramientas de este fork

`tools/live_sim`, `allow_game_relative_writes` activo por defecto y
`auto_create_game_dirs` se añadieron en este fork para probar juegos homebrew.

El Xbox 360 SDK de Microsoft solo se usa para compilar `net_probe` y no forma parte
de este repositorio.
