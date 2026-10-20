#!/usr/bin/env python3
"""
Biwenger Seg.Aux 2026-27 - Script de ADMINISTRADOR v3.3
Preconfigurado para la liga '10 managers, 0 ideas' (ID 1444772).
Descarga Ranking FIFA, Liga Apertura (ID 137614 con cruces y PJ calculados),
plantillas, goles, asistencias, 11 ideal, mejores fichajes y récords de jornada,
e inyecta automáticamente el JSON actualizado en biwenger-seg-aux-2026-27.html.
"""

import getpass
import json
import os
import re
import sys
from datetime import datetime
from pathlib import Path

import requests

BASE_API = "https://biwenger.as.com/api/v2"
CDN_API = "https://cf.biwenger.com/api/v2"
OUT = Path("salida")
HTML_FILE = Path("biwenger-seg-aux-2026-27.html")
TIMEOUT = 20

LEAGUE_ID = os.environ.get("BIWENGER_LEAGUE", "1444772")
USER_ID = os.environ.get("BIWENGER_USER", "8331187")
VERSION = os.environ.get("BIWENGER_VERSION", "631")


def save(name, data):
    OUT.mkdir(exist_ok=True)
    with open(OUT / name, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)


def headers(token=None, league=None, user=None):
    h = {
        "Accept": "application/json, text/plain, */*",
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)",
        "Referer": "https://biwenger.as.com/",
    }
    if token:
        h["Authorization"] = f"Bearer {token}"
    if league:
        h["X-League"] = str(league)
    if user:
        h["X-User"] = str(user)
    if VERSION:
        h["X-Version"] = str(VERSION)
    return h


def sanitize(obj):
    bad = ("token", "password", "email", "phone", "mail", "secret")
    if isinstance(obj, dict):
        return {k: sanitize(v) for k, v in obj.items() if not any(b in k.lower() for b in bad)}
    if isinstance(obj, list):
        return [sanitize(x) for x in obj]
    return obj


def login():
    token_env = os.environ.get("BIWENGER_TOKEN")
    if token_env:
        print("[OK] Usando BIWENGER_TOKEN de variable de entorno")
        return token_env.strip()

    email = os.environ.get("BIWENGER_EMAIL") or input("Email de Biwenger: ").strip()
    password = os.environ.get("BIWENGER_PASSWORD") or getpass.getpass(
        "Contrasena (no se ve mientras escribes, es normal): "
    )
    r = requests.post(
        f"{BASE_API}/auth/login",
        json={"email": email, "password": password},
        headers=headers(),
        timeout=TIMEOUT,
    )
    if r.status_code != 200:
        sys.exit(f"[ERROR] Login fallido (HTTP {r.status_code}). Revisa email/contrasena.")
    token = r.json().get("token")
    if not token:
        sys.exit("[ERROR] El login no devolvio token.")
    print("[OK] Login correcto")
    return token


def fetch(base, token, league, user, path, params=None, raw_name=None):
    try:
        r = requests.get(
            f"{base}/{path}",
            params=params or {},
            headers=headers(token, league, user),
            timeout=TIMEOUT,
        )
        print(f"  GET {path} -> HTTP {r.status_code}")
        if r.status_code != 200:
            return None
        payload = r.json()
        data = payload.get("data", payload)
        if raw_name:
            save(raw_name, sanitize(data))
        return data
    except Exception as e:
        print(f"  GET {path} -> ERROR: {e}")
        return None


def fetch_laliga_players(score_id=1):
    data = fetch(
        CDN_API, None, None, None,
        "competitions/la-liga/data",
        {"lang": "es", "score": score_id},
        "raw_laliga_players.json",
    )
    if not data:
        return {}, {}
    players = data.get("players", {})
    teams = data.get("teams", {})
    rounds_list = (data.get("season") or {}).get("rounds", [])
    rounds_map = {r.get("id"): r for r in rounds_list if isinstance(r, dict)}

    catalog = {}
    for pid, p in players.items():
        tid = str(p.get("teamID", ""))
        tname = (teams.get(tid) or {}).get("name", "")
        catalog[int(pid)] = {
            "id": int(pid),
            "nombre": p.get("name"),
            "club": tname,
            "posicion": p.get("position"),
            "puntos": p.get("points", 0),
            "precio": p.get("price", 0),
            "incremento": p.get("priceIncrement", 0),
        }
    return catalog, rounds_map


def fetch_tournaments_detail(token, league, user, league_data, user_names_by_id):
    torneos_completos = []
    for t_summary in (league_data or {}).get("tournaments", []):
        if not isinstance(t_summary, dict):
            continue
        tid = t_summary.get("id")
        if not tid:
            continue
        t_detail = fetch(
            BASE_API, token, league, user,
            f"tournaments/{tid}",
            {"fields": "*"},
            f"raw_tournament_{tid}.json",
        )
        if not t_detail or not isinstance(t_detail, dict):
            continue

        # Mapa de nombres de equipos propio del torneo + respaldo de la liga
        teams_map = dict(user_names_by_id)
        for tm in t_detail.get("teams", []):
            if isinstance(tm, dict) and tm.get("id"):
                teams_map[tm["id"]] = tm.get("name", teams_map.get(tm["id"], ""))

        # Procesar rondas y enfrentamientos (ubicados en la raiz de t_detail['rounds'])
        rondas_formateadas = []
        for rnd in t_detail.get("rounds", []):
            if not isinstance(rnd, dict):
                continue
            idx = rnd.get("index", "?")
            r_obj = rnd.get("round") or {}
            r_short = r_obj.get("short") or r_obj.get("name") or ""
            titulo_jornada = f"J.{idx} Torneo ({r_short} Liga)" if r_short else f"J.{idx} Torneo"

            partidos = []
            for fx in rnd.get("fixtures", []):
                if not isinstance(fx, dict):
                    continue
                home = fx.get("home") or {}
                away = fx.get("away") or {}
                h_id = home.get("id")
                a_id = away.get("id")
                h_name = teams_map.get(h_id, f"ID {h_id}")
                a_name = teams_map.get(a_id, f"ID {a_id}")
                h_score = home.get("score")
                a_score = away.get("score")

                partidos.append({
                    "l": h_name,
                    "gl": h_score if h_score is not None else "vs",
                    "v": a_name,
                    "gv": a_score if a_score is not None else "",
                })
            rondas_formateadas.append({"jornada": titulo_jornada, "partidos": partidos})

        t_info = {
            "id": tid,
            "nombre": t_detail.get("name", t_summary.get("name")),
            "tipo": t_detail.get("type"),
            "estado": t_detail.get("status"),
            "fases": [],
        }

        stages_raw = t_detail.get("stages", {})
        stages_iter = stages_raw.items() if isinstance(stages_raw, dict) else enumerate(stages_raw)

        for stage_key, stage in stages_iter:
            if not isinstance(stage, dict):
                continue
            s_info = {
                "nombre": stage.get("name", str(stage_key)),
                "tipo": stage.get("type", str(stage_key)),
                "grupos": [],
                "rondas": rondas_formateadas,
            }
            groups = stage.get("groups", [])
            if not groups and stage.get("standings"):
                groups = [{"name": stage.get("name", "General"), "standings": stage.get("standings")}]

            for grp in groups:
                if not isinstance(grp, dict):
                    continue
                tabla = []
                for pos, st in enumerate(grp.get("standings", []), start=1):
                    if not isinstance(st, dict):
                        continue
                    u_obj = st.get("user") if isinstance(st.get("user"), dict) else st
                    u_id = u_obj.get("id") if isinstance(u_obj, dict) else st.get("user")
                    if not u_id and isinstance(st.get("team"), dict):
                        u_id = st.get("team", {}).get("id")

                    pg = st.get("won", st.get("wins", 0)) or 0
                    pe = st.get("drawn", st.get("ties", 0)) or 0
                    pp = st.get("lost", st.get("losses", 0)) or 0
                    pj = st.get("played", st.get("playedMatches", 0)) or (pg + pe + pp)

                    gf = st.get("goalsFor", st.get("scored", st.get("Scored", 0))) or 0
                    gc = st.get("goalsAgainst", st.get("against", st.get("Against", 0))) or 0
                    eq_nombre = (
                        teams_map.get(u_id)
                        or (u_obj.get("name", "") if isinstance(u_obj, dict) else st.get("name", ""))
                        or f"ID {u_id}"
                    )

                    tabla.append({
                        "posicion": st.get("position", pos),
                        "user_id": u_id,
                        "equipo": eq_nombre,
                        "pj": pj,
                        "pg": pg,
                        "pe": pe,
                        "pp": pp,
                        "gf": gf,
                        "gc": gc,
                        "dg": gf - gc,
                        "pts": st.get("points", 0),
                    })
                s_info["grupos"].append({"nombre": grp.get("name", "A"), "clasificacion": tabla})
            t_info["fases"].append(s_info)

        torneos_completos.append(t_info)
    return torneos_completos


def fetch_teams_details(token, league, user, standings, catalog):
    record_jornada = {"equipo": "—", "puntos": 0, "jornada": "—"}
    mejores_fichajes = []
    detalles_equipos = []

    for row in standings:
        uid = row["id"]
        udata = fetch(
            BASE_API, token, league, user,
            f"user/{uid}",
            {"fields": "*,account,players(*,owner),lineups(*),seasons,stats"},
        )
        if not udata:
            continue

        lineups = udata.get("lineups", [])
        jornadas_pts = []
        veces_primero_jornada = 0
        max_rnd_equipo = 0

        items_lineup = list(lineups.values()) if isinstance(lineups, dict) else list(lineups)
        for idx_j, lp in enumerate(items_lineup, start=1):
            if not isinstance(lp, dict):
                continue
            pts = lp.get("points") or 0
            if pts > max_rnd_equipo:
                max_rnd_equipo = pts

            pos_j = lp.get("position")
            if pos_j == 1:
                veces_primero_jornada += 1

            rnd = lp.get("round")
            if isinstance(rnd, dict) and rnd.get("name"):
                rname = rnd.get("name")
            elif isinstance(rnd, (int, str)) and str(rnd).isdigit():
                rname = f"Jornada {rnd}"
            else:
                rname = f"Jornada {idx_j}"

            jornadas_pts.append({
                "jornada": rname,
                "puntos": pts,
                "posicion_jornada": pos_j,
                "ideal": lp.get("ideal", lp.get("count")),
            })
            if pts > record_jornada["puntos"]:
                record_jornada = {"equipo": row["equipo"], "puntos": pts, "jornada": rname}

        players = udata.get("players", [])
        plantilla = []
        valor_total = 0
        incremento_total = 0

        for pl in players:
            pid = int(pl.get("id", 0))
            info = catalog.get(pid, {})
            owner_info = pl.get("owner") or {}
            precio_actual = info.get("precio", 0)
            inc_actual = info.get("incremento", 0)
            valor_total += precio_actual
            incremento_total += inc_actual

            entry = {
                "id": pid,
                "nombre": info.get("nombre", f"Jugador #{pid}"),
                "club": info.get("club", ""),
                "posicion": info.get("posicion"),
                "puntos_totales": info.get("puntos", 0),
                "precio_actual": precio_actual,
                "incremento_diario": inc_actual,
                "precio_compra": owner_info.get("price", 0),
                "clausula": owner_info.get("clause", 0),
                "propietario": row["equipo"],
            }
            plantilla.append(entry)
            mejores_fichajes.append(entry)

        row["valor_equipo"] = valor_total or udata.get("teamValue", 0)
        row["incremento_diario"] = incremento_total
        row["num_jugadores"] = len(plantilla)
        row["victorias_jornada"] = veces_primero_jornada

        detalles_equipos.append({
            "id": uid,
            "equipo": row["equipo"],
            "valor_equipo": row["valor_equipo"],
            "incremento_diario": incremento_total,
            "num_jugadores": len(plantilla),
            "victorias_jornada": veces_primero_jornada,
            "max_rnd": max_rnd_equipo,
            "medallas_temporadas": udata.get("seasons", []),
            "stats_perfil": udata.get("stats", {}),
            "jornadas": jornadas_pts,
            "plantilla": sorted(plantilla, key=lambda x: x["puntos_totales"], reverse=True),
        })

    mejores_fichajes.sort(key=lambda x: x["puntos_totales"], reverse=True)
    return detalles_equipos, record_jornada, mejores_fichajes[:15]


def normalize_standings(league_data):
    rows = []
    for i, t in enumerate((league_data or {}).get("standings", []), start=1):
        rows.append({
            "posicion": t.get("position", i),
            "cambio_posicion": t.get("positionInc", 0),
            "equipo": t.get("name"),
            "puntos": t.get("points", 0),
            "valor_equipo": t.get("teamValue", 0),
            "incremento_diario": 0,
            "num_jugadores": t.get("teamSize", 0),
            "id": t.get("id"),
            "icono": t.get("icon"),
        })
    return sorted(rows, key=lambda x: (x["posicion"] is None, x["posicion"], -x["puntos"]))


def update_html_in_place(summary):
    if not HTML_FILE.exists():
        print(f"[INFO] No se encontro {HTML_FILE}; solo se genero salida/datos_liga.json.")
        return

    html = HTML_FILE.read_text(encoding="utf-8")

    # Inyectar JSON completo en <script id="biwenger-live-data">
    json_script = (
        f'<script id="biwenger-live-data" type="application/json">\n'
        f'{json.dumps(summary, ensure_ascii=False, indent=2)}\n'
        f'</script>'
    )
    if 'id="biwenger-live-data"' in html:
        html = re.sub(
            r'<script id="biwenger-live-data" type="application/json">.*?</script>',
            lambda _: json_script,
            html,
            flags=re.DOTALL,
        )
    else:
        html = html.replace("</body>", f"{json_script}\n</body>")

    HTML_FILE.write_text(html, encoding="utf-8")
    print(f"[OK] Web actualizada automaticamente en: {HTML_FILE}")


def main():
    token = login()
    league = LEAGUE_ID
    user = USER_ID

    print(f"\nDescargando datos de la liga {league} (usuario {user})...")
    league_data = fetch(
        BASE_API, token, league, user,
        "league",
        {"fields": "*,standings,tournaments,group,settings(description)"},
        "raw_league.json",
    )
    board = fetch(
        BASE_API, token, league, user,
        f"league/{league}/board",
        {"type": "round,market,bonus", "limit": 50},
        "raw_board.json",
    )

    standings = normalize_standings(league_data)
    user_names_by_id = {r["id"]: r["equipo"] for r in standings}

    print("\nDescargando torneos activos (Liga Apertura)...")
    torneos = fetch_tournaments_detail(token, league, user, league_data, user_names_by_id)

    print("\nDescargando catalogo de LaLiga y perfiles completos de los 10 equipos...")
    catalog, _ = fetch_laliga_players(score_id=1)
    equipos_detalle, record_jornada, top_fichajes = fetch_teams_details(
        token, league, user, standings, catalog
    )

    summary = {
        "ultima_actualizacion": datetime.now().strftime("%d/%m/%Y %H:%M"),
        "bote_total_euros": 200,
        "clasificacion": [{k: v for k, v in r.items() if k != "icono"} for r in standings],
        "torneos": torneos,
        "premios_individuales": {
            "record_puntuacion_jornada": record_jornada,
            "top_10_mejores_fichajes": top_fichajes,
        },
        "equipos_detalle": equipos_detalle,
    }
    save("datos_liga.json", summary)

    print("\n=== RANKING FIFA (PICAS AS) ===")
    for r in standings:
        val_fmt = f"{r['valor_equipo']:,}".replace(",", ".")
        inc_fmt = f"{r['incremento_diario']:+,}".replace(",", ".")
        print(
            f"  {r['posicion']:>2}  {r['equipo']:<20} {r['puntos']:>3} pts | "
            f"{val_fmt:>10} EUR ({inc_fmt} EUR) | {r['num_jugadores']} jug."
        )

    if record_jornada["puntos"] > 0:
        print(
            f"\n★ Récord en 1 Jornada: {record_jornada['equipo']} "
            f"con {record_jornada['puntos']} pts ({record_jornada['jornada']})"
        )

    update_html_in_place(summary)
    print("\n[OK] Todo listo. Abre biwenger-seg-aux-2026-27.html en tu navegador.")


if __name__ == "__main__":
    main()