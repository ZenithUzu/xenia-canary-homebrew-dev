#!/usr/bin/env python3
"""Crea el .zip de release para Windows en build/release, sin publicarlo.

Incluye el ejecutable, las herramientas y las licencias de terceros. Si el
repositorio tiene cambios sin confirmar, el paquete se marca como borrador.

Uso: python tools/live_sim/empaquetar_windows.py
"""
import hashlib
import os
import shutil
import subprocess
import sys
import zipfile

AQUI = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.dirname(os.path.dirname(AQUI))
EXE = os.path.join(REPO, "build", "bin", "Windows", "Release", "xenia_canary_netplay.exe")
SALIDA = os.path.join(REPO, "build", "release")

# Nunca se distribuyen en el paquete.
PROHIBIDAS = (".gba", ".gb", ".gbc", ".nds", ".z64", ".n64", ".v64", ".xex", ".pdb", ".gpd", ".log", ".jsonl")
# No forman parte del ejecutable de Windows: wolfSSL solo se enlaza en Linux, y el resto son
# herramientas de desarrollo, pruebas o codigo para otras arquitecturas.
# ffmpeg-xenia solo es la configuracion de FFmpeg, cuya licencia ya se incluye.
SIN_INCLUIR = {"wolfssl", "binutils", "catch", "clang-format", "cpplint", "xbyak_aarch64", "ffmpeg-xenia"}
# Sin archivo de licencia propio: su aviso esta dentro de estos archivos.
AVISO_EN_ARCHIVO = {
    "cacert": "cacert.pem",
    "crypto": "TinySHA1.hpp",
    "dxbc": "DXBCChecksum.h",
    "microprofile": "README.md",
    "renderdoc": "renderdoc_app.h",
    "stb": "stb_image.h",
}
# zstd tiene doble licencia y aqui se elige BSD.
SOLO_ESTOS = {"zstd": ("LICENSE",)}
ES_LICENCIA = ("licen", "copying", "copyright", "notice", "unlicense")


def git(*argumentos):
    return subprocess.check_output(["git", "-C", REPO, *argumentos], text=True).strip()


def copiar_licencias(destino):
    resumen = []
    raiz = os.path.join(REPO, "third_party")
    for nombre in sorted(os.listdir(raiz)):
        carpeta = os.path.join(raiz, nombre)
        if not os.path.isdir(carpeta) or nombre in SIN_INCLUIR:
            continue
        if nombre in AVISO_EN_ARCHIVO:
            elegidos = [AVISO_EN_ARCHIVO[nombre]]
        elif nombre in SOLO_ESTOS:
            elegidos = list(SOLO_ESTOS[nombre])
        else:
            elegidos = [n for n in os.listdir(carpeta) if n.lower().startswith(ES_LICENCIA)]
        copiados = 0
        for elegido in elegidos:
            origen = os.path.join(carpeta, elegido)
            if os.path.isfile(origen):
                os.makedirs(os.path.join(destino, nombre), exist_ok=True)
                shutil.copy2(origen, os.path.join(destino, nombre, elegido))
                copiados += 1
            elif os.path.isdir(origen):
                shutil.copytree(origen, os.path.join(destino, nombre, elegido), dirs_exist_ok=True)
                copiados += 1
        resumen.append((nombre, copiados))
    return resumen


def main():
    if not os.path.isfile(EXE):
        sys.exit("Falta el ejecutable: compila primero la configuracion Release.")

    commit = git("rev-parse", "HEAD")
    # Compilar puede dejar archivos generados dentro de los submodulos.
    cambios = git("status", "--porcelain", "--ignore-submodules=dirty")
    borrador = bool(cambios)
    nombre = f"xenia-canary-homebrew-dev-windows-{commit[:9]}" + ("-borrador" if borrador else "")
    carpeta = os.path.join(SALIDA, nombre)
    shutil.rmtree(carpeta, ignore_errors=True)
    os.makedirs(carpeta)

    shutil.copy2(EXE, carpeta)
    for archivo in ("LICENSE", "README.md", "CREDITS.md"):
        shutil.copy2(os.path.join(REPO, archivo), carpeta)
    herramientas = os.path.join(carpeta, "tools", "live_sim")
    os.makedirs(herramientas)
    for archivo in ("lanzar_juego.py", "live_sim_server.py", "README.md"):
        shutil.copy2(os.path.join(AQUI, archivo), herramientas)

    resumen = copiar_licencias(os.path.join(carpeta, "THIRD_PARTY_LICENSES"))
    sin_aviso = [n for n, c in resumen if not c]

    with open(os.path.join(carpeta, "BUILD-INFO.txt"), "w", encoding="utf-8") as fh:
        fh.write("Xenia Canary Homebrew Dev para Windows x64\n")
        fh.write("Codigo fuente: https://github.com/ZenithUzu/xenia-canary-homebrew-dev\n")
        fh.write(f"Commit: {commit}\n")
        if borrador:
            fh.write("BORRADOR: creado con cambios sin confirmar; no publicar.\n")
        fh.write("Para recompilar con otras versiones de las librerias, consulta docs/building.md.\n")
        fh.write("Los certificados de cacert son datos de Mozilla, extraidos por el proyecto curl, con licencia MPL 2.0.\n")

    prohibidos = [
        os.path.join(sub, n)
        for sub, _, archivos in os.walk(carpeta)
        for n in archivos
        if n.lower().endswith(PROHIBIDAS)
    ]
    if prohibidos:
        sys.exit("El paquete contiene archivos prohibidos: " + ", ".join(prohibidos))

    ruta_zip = carpeta + ".zip"
    with zipfile.ZipFile(ruta_zip, "w", zipfile.ZIP_DEFLATED, compresslevel=9) as zf:
        for sub, _, archivos in os.walk(carpeta):
            for n in archivos:
                completa = os.path.join(sub, n)
                zf.write(completa, os.path.join(nombre, os.path.relpath(completa, carpeta)))

    sha = hashlib.sha256()
    with open(ruta_zip, "rb") as fh:
        for bloque in iter(lambda: fh.read(1 << 20), b""):
            sha.update(bloque)
    print(f"Paquete: {ruta_zip}")
    print(f"Tamano: {os.path.getsize(ruta_zip)} bytes")
    print(f"SHA-256: {sha.hexdigest()}")
    print(f"Licencias de terceros: {sum(1 for _, c in resumen if c)} dependencias")
    print("Sin aviso encontrado: " + (", ".join(sin_aviso) or "ninguna"))
    if borrador:
        print("BORRADOR: hay cambios sin confirmar.")


if __name__ == "__main__":
    main()
