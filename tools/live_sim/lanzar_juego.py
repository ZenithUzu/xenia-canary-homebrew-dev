#!/usr/bin/env python3
"""Abre un .xex en esta version de Xenia, con el simulador de red local.

Trabaja sobre una copia del juego en build/live_sim/juegos/<nombre>, nunca sobre
el original. Xenia crea las carpetas de game:\\ que el juego pida; los archivos
que falten no se inventan: se anotan en faltantes.txt, y se pueden aportar con
--extra CARPETA.

Uso: python lanzar_juego.py juego.xex [--extra CARPETA] [--segundos N]
                            [--exe RUTA] [--perfil-desde CARPETA_DE_XENIA]
"""
import argparse
import glob
import os
import re
import shutil
import socket
import subprocess
import sys
import time

AQUI = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.dirname(os.path.dirname(AQUI))
DATOS = os.path.join(REPO, "build", "live_sim")
PUERTO_SIM = 36100
CONFIG = "xenia-canary-netplay.config.toml"
RUTA = re.compile(r"(?:game:\\|\\Device\\Harddisk0\\Partition1\\)([^,)\r\n]*)", re.I)
LLAMADA = re.compile(r"Nt(?:CreateFile|OpenFile|QueryFullAttributesFile|QueryAttributesFile)\(")


def buscar_exe(indicado):
    if indicado:
        return indicado
    candidatos = glob.glob(os.path.join(REPO, "build", "bin", "Windows", "*", "xenia_canary_netplay.exe"))
    if not candidatos:
        sys.exit("No encuentro el .exe compilado: usa 'xb build' o indica --exe.")
    return max(candidatos, key=os.path.getmtime)


def simulador_activo():
    with socket.socket() as s:
        s.settimeout(0.5)
        return s.connect_ex(("127.0.0.1", PUERTO_SIM)) == 0


def iniciar_simulador():
    if simulador_activo():
        return None
    entorno = dict(os.environ, LIVE_SIM_DATA=DATOS)
    proceso = subprocess.Popen(
        [sys.executable, "-I", os.path.join(AQUI, "live_sim_server.py")],
        cwd=DATOS, env=entorno, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
        creationflags=subprocess.CREATE_NO_WINDOW)
    for _ in range(20):
        if simulador_activo():
            return proceso
        time.sleep(0.25)
    proceso.terminate()
    sys.exit("No se pudo iniciar el simulador de red.")


def preparar_copia(xex, extra):
    nombre = os.path.splitext(os.path.basename(xex))[0]
    destino = os.path.join(DATOS, "juegos", nombre)
    origen = os.path.dirname(os.path.abspath(xex))
    os.makedirs(destino, exist_ok=True)
    # Si el .xex esta dentro de la carpeta de datos, copiarla la meteria dentro de si misma.
    dentro = os.path.normcase(destino).startswith(os.path.normcase(origen) + os.sep)
    entradas = [] if dentro else os.listdir(origen)
    shutil.copy2(xex, destino)
    # Copia el resto de la carpeta sin pisar lo que el juego ya haya guardado.
    for entrada in entradas:
        de, a = os.path.join(origen, entrada), os.path.join(destino, entrada)
        if os.path.exists(a) or entrada.lower().endswith(".xex"):
            continue
        if os.path.isfile(de):
            shutil.copy2(de, a)
        elif os.path.isdir(de):
            shutil.copytree(de, a)
    if extra:
        shutil.copytree(extra, destino, dirs_exist_ok=True)
    return destino, os.path.join(destino, os.path.basename(xex))


def importar_perfil(origen):
    """Copia perfiles y configuracion de otra instalacion, solo la primera vez."""
    contenido = os.path.join(DATOS, "content")
    if not os.path.isdir(contenido):
        shutil.copytree(os.path.join(origen, "content"), contenido)
    config = os.path.join(DATOS, CONFIG)
    if not os.path.exists(config) and os.path.exists(os.path.join(origen, CONFIG)):
        shutil.copy2(os.path.join(origen, CONFIG), config)


def rutas_pedidas(log):
    rutas = set()
    with open(log, encoding="utf-8", errors="replace") as fh:
        for linea in fh:
            if LLAMADA.search(linea):
                for ruta in RUTA.findall(linea):
                    ruta = ruta.strip().strip("\\")
                    if ruta and ".." not in ruta.split("\\"):
                        rutas.add(ruta)
    return rutas


def ejecutar(exe, xex, log, segundos):
    argumentos = [
        exe, xex,
        f"--storage_root={DATOS}",
        f"--content_root={os.path.join(DATOS, 'content')}",
        f"--api_address=127.0.0.1:{PUERTO_SIM}/",
        "--network_mode=2",
        "--upnp=false",
        # Una configuracion importada podria traer estos ajustes con otros valores.
        "--allow_game_relative_writes=true",
        "--auto_create_game_dirs=true",
        "--auto_check_updates=false",
        "--log_level=3",
        "--log_mask_ips=false",
    ]
    with open(log, "wb") as salida:
        proceso = subprocess.Popen(argumentos, cwd=DATOS, stdout=salida, stderr=subprocess.STDOUT)
        try:
            proceso.wait(segundos)
            return f"se cerro (codigo {proceso.returncode:#x})"
        except subprocess.TimeoutExpired:
            proceso.kill()
            proceso.wait()
            return f"seguia abierto tras {segundos} s"


def main():
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("xex")
    parser.add_argument("--exe", help="ruta del ejecutable de Xenia")
    parser.add_argument("--extra", help="carpeta cuyos archivos se copian junto al juego")
    parser.add_argument("--perfil-desde", help="carpeta de otra instalacion de Xenia con perfiles")
    parser.add_argument("--segundos", type=int, help="cerrar Xenia tras N segundos, para pruebas")
    args = parser.parse_args()
    if not os.path.isfile(args.xex):
        sys.exit(f"No existe {args.xex}")

    exe = buscar_exe(args.exe)
    os.makedirs(DATOS, exist_ok=True)
    if args.perfil_desde:
        importar_perfil(args.perfil_desde)
    juego, xex = preparar_copia(args.xex, args.extra)
    log = os.path.join(juego, "xenia_salida.log")
    simulador = iniciar_simulador()
    try:
        print("Xenia: " + ejecutar(exe, xex, log, args.segundos), flush=True)
    finally:
        if simulador:
            simulador.terminate()

    faltan = sorted(r for r in rutas_pedidas(log) if not os.path.exists(os.path.join(juego, r)))
    with open(os.path.join(juego, "faltantes.txt"), "w", encoding="utf-8") as fh:
        fh.write("\n".join(faltan) + ("\n" if faltan else ""))
    print(f"Juego: {juego}")
    print("Archivos pedidos que no existen: " + (", ".join(faltan) or "ninguno"))


if __name__ == "__main__":
    main()
