#!/usr/bin/env python3
"""Servidor local que simula el backend de red de Xenia Canary Netplay.

Implementa la API que usa XLiveAPI (rama netplay_canary_experimental). Todo vive
en memoria y solo escucha en 127.0.0.1 por defecto: nada sale a Internet ni
contacta con servicios reales de Xbox.

Cada peticion queda en live_sim_log.jsonl y al cerrar se escribe un resumen en
live_sim_resumen.txt.

Uso: python live_sim_server.py [--host 127.0.0.1] [--port 36100]
     [--fallar REGEX] [--latencia MS]
"""
import argparse
import collections
import json
import os
import re
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import unquote

BASE = os.environ.get("LIVE_SIM_DATA") or os.path.dirname(os.path.abspath(__file__))
LOG_PATH = os.path.join(BASE, "live_sim_log.jsonl")
RESUMEN_PATH = os.path.join(BASE, "live_sim_resumen.txt")

# Resultados que Xenia espera (XLiveAPI.h).
STORAGE_CREATED, STORAGE_FOUND = 0, 1
UPLOAD_OK = 0


class State:
    def __init__(self):
        self.lock = threading.RLock()
        self.players = {}       # xuid -> jugador
        self.sessions = {}      # (title, id) -> sesion
        self.qos = {}           # (title, id) -> bytes
        self.properties = {}    # (title, id) -> lista de propiedades
        self.storage = {}       # ruta -> bytes
        self.settings = {}      # xuid -> ajustes
        self.presence = {}      # xuid -> datos de presencia
        self.stats = {}         # titulo -> filas enviadas
        self.counts = collections.Counter()
        self.unknown = collections.Counter()


STATE = State()
ARGS = None
LOG_LOCK = threading.Lock()


def norm_xuid(value):
    """Xenia envia XUID en hex; normaliza mayusculas y el prefijo 0x."""
    return str(value).lower().removeprefix("0x").zfill(16)


def session_public(session):
    return dict(session)


def add_players(session, entries):
    """Une jugadores sin duplicar y recalcula las plazas ocupadas."""
    current = session.setdefault("players", [])
    known = {norm_xuid(p.get("xuid", "")) for p in current}
    for entry in entries:
        xuid = norm_xuid(entry.get("xuid", ""))
        if xuid not in known:
            current.append(entry)
            known.add(xuid)
    recount(session)


def recount(session):
    public = int(session.get("publicSlotsCount", 0) or 0)
    private = int(session.get("privateSlotsCount", 0) or 0)
    filled = len(session.get("players", []))
    filled_private = min(int(session.get("filledPrivateSlotsCount", 0) or 0), private)
    filled_public = min(max(filled - filled_private, 0), public)
    session["filledPublicSlotsCount"] = filled_public
    session["filledPrivateSlotsCount"] = filled_private
    session["openPublicSlotsCount"] = max(public - filled_public, 0)
    session["openPrivateSlotsCount"] = max(private - filled_private, 0)


class Handler(BaseHTTPRequestHandler):
    protocol_version = "HTTP/1.1"
    server_version = "XeniaLiveSim/1.0"

    def log_message(self, *_):
        pass

    # ---- utilidades ----
    def body(self):
        if getattr(self, "_body", None) is None:
            length = int(self.headers.get("Content-Length") or 0)
            self._body = self.rfile.read(length) if length else b""
        return self._body

    def json_body(self):
        try:
            data = json.loads(self.body().rstrip(b"\0") or b"{}")
            return data if isinstance(data, (dict, list)) else {}
        except ValueError:
            return {}

    def send(self, status, payload=b"", content_type="application/json"):
        if isinstance(payload, (dict, list)):
            payload = json.dumps(payload).encode()
        elif isinstance(payload, str):
            payload = payload.encode()
        self.send_response(status)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(payload)))
        self.end_headers()
        if self.command != "HEAD":
            self.wfile.write(payload)
        self._status = status
        self._out = len(payload)

    def record(self, route, started):
        entry = {
            "t": round(time.time(), 3),
            "ms": round((time.time() - started) * 1000, 1),
            "cliente": self.client_address[0],
            "metodo": self.command,
            "ruta": self.path,
            "tipo": route,
            "estado": getattr(self, "_status", 0),
            "bytes_in": len(self._body or b""),
            "bytes_out": getattr(self, "_out", 0),
        }
        if self._body and len(self._body) <= 4096:
            try:
                entry["json"] = json.loads(self._body.rstrip(b"\0"))
            except ValueError:
                entry["hex"] = self._body[:64].hex()
        with LOG_LOCK:
            with open(LOG_PATH, "a", encoding="utf-8") as fh:
                fh.write(json.dumps(entry, ensure_ascii=False) + "\n")
        print(f"{time.strftime('%H:%M:%S')} {entry['estado']} {self.command:6} {self.path}  [{route}]",
              flush=True)

    # ---- despacho ----
    def dispatch(self):
        started = time.time()
        self._body = None
        path = unquote(self.path.split("?", 1)[0]).strip("/")
        route = "desconocida"
        try:
            self.body()
            if ARGS.latencia:
                time.sleep(ARGS.latencia / 1000)
            for pattern, name, func in ROUTES:
                match = re.fullmatch(pattern, path, re.I)
                if match and self.command in name[1]:
                    route = name[0]
                    with STATE.lock:
                        STATE.counts[route] += 1
                    if ARGS.fallar and re.search(ARGS.fallar, path, re.I):
                        self.send(503, {"message": "fallo inyectado por --fallar"})
                    else:
                        with STATE.lock:
                            func(self, *match.groups())
                    return
            with STATE.lock:
                STATE.unknown[f"{self.command} {path}"] += 1
            self.send(404, {"message": f"ruta no simulada: {path}"})
        except Exception as exc:  # El simulador no debe caerse por una peticion rara.
            route = f"error:{type(exc).__name__}"
            self.send(500, {"message": str(exc)})
        finally:
            self.record(route, started)
            # Se reescribe en cada peticion porque el lanzador cierra el proceso sin Ctrl+C.
            with STATE.lock:
                write_summary()

    do_GET = do_POST = do_DELETE = do_HEAD = do_PUT = lambda self: self.dispatch()


def r_probe_result(h):
    """Guarda el informe que envia net_probe.xex."""
    with open(os.path.join(BASE, "net_probe_resultado.txt"), "wb") as fh:
        fh.write(h.body())
    h.send(201, {})


# ---- jugadores ----
def r_root(h):
    h.send(200, {"message": "Xenia Live Sim"})


def r_whoami(h):
    h.send(200, {"address": h.client_address[0]})


def r_ports(h, _title):
    h.send(200, {"connect": [], "bind": []})


def r_player_create(h):
    data = h.json_body()
    data["xuid"] = str(data.get("xuid", ""))
    STATE.players[norm_xuid(data["xuid"])] = data
    h.send(201, data)


def r_player_find(h):
    address = h.json_body().get("hostAddress", "")
    for player in reversed(list(STATE.players.values())):
        if player.get("hostAddress") == address:
            h.send(201, player)
            return
    h.send(404, {"message": "jugador no encontrado"})


def r_delete_profiles(h):
    removed = {key: p.get("gamertag", "") for key, p in STATE.players.items()
               if p.get("hostAddress") == h.client_address[0]}
    for key in removed:
        del STATE.players[key]
    h.send(200, removed)


def r_findusers(h):
    found = []
    wanted = h.json_body()
    items = wanted.get("UsersInfo", []) if isinstance(wanted, dict) else wanted
    for item in items:
        xuid = norm_xuid(item.get("xuid", "")) if isinstance(item, dict) else ""
        name = item.get("gamertag", "") if isinstance(item, dict) else ""
        for player in STATE.players.values():
            if norm_xuid(player.get("xuid", "")) == xuid or (name and player.get("gamertag") == name):
                found.append({"xuid": player["xuid"], "gamertag": player.get("gamertag", "")})
    h.send(201, found)


def r_presence(h):
    data = h.json_body()
    xuids = data.get("xuids", []) if isinstance(data, dict) else []
    result = []
    for xuid in xuids:
        player = STATE.players.get(norm_xuid(xuid))
        if not player:
            continue
        item = {"xuid": player["xuid"], "gamertag": player.get("gamertag", ""),
                "state": 1, "sessionId": "0000000000000000", "titleId": "00000000",
                "stateChangeTime": 0, "richPresence": ""}
        item.update(STATE.presence.get(norm_xuid(xuid), {}))
        result.append(item)
    h.send(201, result)


def r_setpresence(h):
    data = h.json_body()
    items = data.get("presence", data.get("players", [])) if isinstance(data, dict) else data
    for item in items if isinstance(items, list) else []:
        if isinstance(item, dict) and "xuid" in item:
            STATE.presence[norm_xuid(item["xuid"])] = {
                k: item[k] for k in ("state", "sessionId", "titleId", "richPresence", "stateChangeTime") if k in item}
    h.send(201, {})


def r_setsettings(h):
    data = h.json_body()
    if isinstance(data, dict):
        STATE.settings["__ultimo__"] = data
    h.send(201, {})


def r_getsettings(h):
    h.send(201, {"settings": []})


# ---- sesiones ----
def key(title, sid):
    return title.upper(), sid.lower()


def r_session_create(h, title):
    data = h.json_body()
    sid = str(data.get("sessionId", data.get("id", ""))).lower()
    if not sid:
        h.send(400, {"message": "falta sessionId"})
        return
    data["id"] = data["sessionId"] = sid
    data.setdefault("players", [])
    data.setdefault("hostAddress", h.client_address[0])
    xuid = data.get("xuid")
    if xuid:
        add_players(data, [{"xuid": xuid}])
    recount(data)
    STATE.sessions[key(title, sid)] = data
    h.send(201, data)


def r_session_search(h, title):
    data = h.json_body()
    limit = int(data.get("resultsCount", 0) or 0) if isinstance(data, dict) else 0
    found = [session_public(s) for (t, _), s in STATE.sessions.items()
             if t == title.upper() and (s.get("openPublicSlotsCount", 0) or s.get("openPrivateSlotsCount", 0))]
    h.send(201, found[:limit] if limit else found)


def r_session_get(h, title, sid):
    session = STATE.sessions.get(key(title, sid))
    if session:
        h.send(200, session_public(session))
    else:
        h.send(404, {"message": "sesion no encontrada"})


def r_session_delete(h, title, sid):
    k = key(title, sid)
    STATE.sessions.pop(k, None)
    STATE.qos.pop(k, None)
    STATE.properties.pop(k, None)
    h.send(200, {})


def with_session(h, title, sid):
    session = STATE.sessions.get(key(title, sid))
    if session is None:
        h.send(404, {"message": "sesion no encontrada"})
    return session


def r_session_join(h, title, sid):
    session = with_session(h, title, sid)
    if session is None:
        return
    data = h.json_body()
    entries = data.get("xuids", data.get("players", [])) if isinstance(data, dict) else []
    add_players(session, [e if isinstance(e, dict) else {"xuid": e} for e in entries])
    h.send(201, {})


def r_session_leave(h, title, sid):
    session = with_session(h, title, sid)
    if session is None:
        return
    data = h.json_body()
    entries = data.get("xuids", data.get("players", [])) if isinstance(data, dict) else []
    leaving = {norm_xuid(e.get("xuid", "") if isinstance(e, dict) else e) for e in entries}
    session["players"] = [p for p in session.get("players", []) if norm_xuid(p.get("xuid", "")) not in leaving]
    recount(session)
    h.send(201, {})


def r_session_modify(h, title, sid):
    session = with_session(h, title, sid)
    if session is None:
        return
    data = h.json_body()
    if isinstance(data, dict):
        for field in ("flags", "publicSlotsCount", "privateSlotsCount"):
            if field in data:
                session[field] = data[field]
        recount(session)
    h.send(201, {})


def r_session_migrate(h, title, sid):
    session = with_session(h, title, sid)
    if session is None:
        return
    data = h.json_body()
    if isinstance(data, dict):
        for field in ("xuid", "hostAddress", "macAddress", "port"):
            if field in data:
                session[field] = data[field]
    h.send(201, session_public(session))


def r_session_arbitration(h, title, sid):
    session = with_session(h, title, sid)
    if session is None:
        return
    players = session.get("players", [])
    machine = str(session.get("machineId", "0000000000000000"))
    h.send(200, {"totalPlayers": len(players),
                 "machines": [{"id": machine, "players": [{"xuid": p.get("xuid", "")} for p in players]}]})


def r_session_qos(h, title, sid):
    k = key(title, sid)
    if h.command == "POST":
        STATE.qos[k] = h.body()
        h.send(201, {})
    elif STATE.qos.get(k):
        h.send(200, STATE.qos[k], "application/octet-stream")
    else:
        h.send(204)


def r_session_properties(h, title, sid):
    k = key(title, sid)
    data = h.json_body()
    STATE.properties[k] = data.get("properties", []) if isinstance(data, dict) else []
    h.send(201, {})


def r_session_properties_get(h, title, sid, _query):
    h.send(200, {"properties": STATE.properties.get(key(title, sid), [])})


def r_ok201(h, *_):
    h.send(201, {})


def r_session_stats(h, title, _sid):
    STATE.stats.setdefault(title.upper(), []).append(h.json_body())
    h.send(201, {})


def r_delete_all(h, mac=None):
    for k, session in list(STATE.sessions.items()):
        same_host = session.get("hostAddress") == h.client_address[0]
        same_mac = mac is None or str(session.get("macAddress", "")).lower() == mac.lower()
        if same_host and same_mac:
            del STATE.sessions[k]
    h.send(200, {})


# ---- servicios y marcadores ----
def r_empty_array(h, *_):
    h.send(200, [])


def r_services(h, _title):
    h.send(200, {"services": [], "querysearch": []})


def r_leaderboards(h):
    h.send(201, {"views": []})


def r_estimate_rank(h):
    data = h.json_body()
    count = len(data.get("requests", [])) if isinstance(data, dict) else 0
    h.send(201, {"ranks": [1] * count})


# ---- XStorage ----
def r_storage_enum(h, path):
    prefix = path.lower()
    limit = 0
    data = h.json_body()
    if isinstance(data, dict):
        limit = int(data.get("max_items", 0) or 0)
    items = [{"path": name, "title_id": 0, "title_version": 0, "owner_puid": 0, "country_id": 0,
              "content_type": 0, "storage_size": len(blob), "installed_size": len(blob),
              "created": 0.0, "last_modified": 0.0}
             for name, blob in STATE.storage.items() if name.lower().startswith(prefix)]
    h.send(201, {"total_num_items": len(items), "items": items[:limit] if limit else items})


def r_storage(h, path):
    if h.command == "GET":
        blob = STATE.storage.get(path)
        if blob is None:
            h.send(404, {"message": "archivo no encontrado"})
        else:
            h.send(200, blob, "application/octet-stream")
    elif h.command == "DELETE":
        STATE.storage.pop(path, None)
        h.send(200, {})
    elif h.body():
        STATE.storage[path] = h.body()
        h.send(201, str(UPLOAD_OK), "text/plain")
    else:
        # Sin cuerpo es XStorageBuildServerPath: comprueba o crea la ruta.
        result = STORAGE_FOUND if path in STATE.storage else STORAGE_CREATED
        h.send(201, str(result), "text/plain")


T = r"([0-9A-Fa-f]{8})"
S = r"([0-9A-Fa-f]{16})"
G, P, D = ("GET", "HEAD"), ("POST",), ("DELETE",)
ROUTES = [
    (r"", ("raiz", G), r_root),
    (r"whoami", ("whoami", G), r_whoami),
    (r"probe/resultado", ("probe_resultado", P), r_probe_result),
    (r"players", ("jugador_registrar", P), r_player_create),
    (r"players/find", ("jugador_buscar", P), r_player_find),
    (r"players/deletemyprofiles", ("jugador_borrar_perfiles", G), r_delete_profiles),
    (r"players/findusers", ("jugador_findusers", P), r_findusers),
    (r"players/presence", ("presencia_leer", P), r_presence),
    (r"players/setpresence", ("presencia_escribir", P), r_setpresence),
    (r"players/setsettings", ("ajustes_escribir", P), r_setsettings),
    (r"players/getsettings", ("ajustes_leer", P), r_getsettings),
    (r"DeleteSessions", ("sesiones_borrar_todas", D), r_delete_all),
    (r"DeleteSessions/([^/]+)", ("sesiones_borrar_mac", D), r_delete_all),
    (rf"title/{T}/ports", ("puertos", G), r_ports),
    (rf"title/{T}/servers", ("xlsp_servidores", G), r_empty_array),
    (rf"title/{T}/services", ("servicios", G), r_services),
    (rf"title/{T}/sessions", ("sesion_crear", P), r_session_create),
    (rf"title/{T}/sessions/search", ("sesion_buscar", P), r_session_search),
    (rf"title/{T}/sessions/{S}", ("sesion_leer", G), r_session_get),
    (rf"title/{T}/sessions/{S}", ("sesion_borrar", D), r_session_delete),
    (rf"title/{T}/sessions/{S}/details", ("sesion_detalles", G), r_session_get),
    (rf"title/{T}/sessions/{S}/join", ("sesion_unir", P), r_session_join),
    (rf"title/{T}/sessions/{S}/prejoin", ("sesion_preunir", P), r_ok201),
    (rf"title/{T}/sessions/{S}/leave", ("sesion_salir", P), r_session_leave),
    (rf"title/{T}/sessions/{S}/modify", ("sesion_modificar", P), r_session_modify),
    (rf"title/{T}/sessions/{S}/migrate", ("sesion_migrar", P), r_session_migrate),
    (rf"title/{T}/sessions/{S}/arbitration", ("sesion_arbitraje", G), r_session_arbitration),
    (rf"title/{T}/sessions/{S}/qos", ("qos", G + P), r_session_qos),
    (rf"title/{T}/sessions/{S}/properties", ("propiedades_escribir", P), r_session_properties),
    (rf"title/{T}/sessions/{S}/properties/(\d+)", ("propiedades_leer", G), r_session_properties_get),
    (rf"title/{T}/sessions/{S}/leaderboards", ("marcador_enviar", P), r_session_stats),
    (r"leaderboards/(?:find|enumerate)", ("marcador_leer", P), r_leaderboards),
    (r"leaderboards/estimate-rank", ("marcador_rango", P), r_estimate_rank),
    (r"xstorage/enumerate/(.+)", ("xstorage_listar", P), r_storage_enum),
    (r"(.*?xstorage/.+|title/[0-9A-Fa-f]{8}/.+|user/[0-9A-Fa-f]{16}/title/.+|clips/title/.+)",
     ("xstorage", G + P + D), r_storage),
]


def write_summary():
    routes = sorted({name[0] for _, name, _ in ROUTES})
    lines = ["Resumen del simulador de red", "", "Rutas usadas:"]
    lines += [f"  {STATE.counts[r]:6}  {r}" for r in routes if STATE.counts[r]]
    lines += ["", "Rutas simuladas que no se usaron:"]
    lines += [f"          {r}" for r in routes if not STATE.counts[r]]
    lines += ["", "Peticiones sin simular (faltan en el servidor):"]
    lines += [f"  {n:6}  {r}" for r, n in STATE.unknown.most_common()] or ["          ninguna"]
    with open(RESUMEN_PATH, "w", encoding="utf-8") as fh:
        fh.write("\n".join(lines) + "\n")


def main():
    global ARGS
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=36100)
    parser.add_argument("--fallar", help="regex de rutas que deben responder 503, para probar errores")
    parser.add_argument("--latencia", type=int, default=0, help="retardo en ms por peticion")
    ARGS = parser.parse_args()
    server = ThreadingHTTPServer((ARGS.host, ARGS.port), Handler)
    print(f"Simulador de red en http://{ARGS.host}:{ARGS.port}/  (Ctrl+C para salir)", flush=True)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        write_summary()
        print(f"Resumen en {RESUMEN_PATH}", flush=True)


if __name__ == "__main__":
    main()
