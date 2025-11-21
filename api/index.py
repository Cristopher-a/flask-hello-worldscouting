from flask import Flask, jsonify, request
from flask_cors import CORS
import requests
from requests.auth import HTTPBasicAuth
from supabase import create_client, Client

app = Flask(__name__)
CORS(app)

SUPABASE_URL = "https://rhttqmtzcmwilzshnxwq.supabase.co"
SUPABASE_KEY = "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJpc3MiOiJzdXBhYmFzZSIsInJlZiI6InJodHRxbXR6Y213aWx6c2hueHdxIiwicm9sZSI6ImFub24iLCJpYXQiOjE3NjM1OTUwOTAsImV4cCI6MjA3OTE3MTA5MH0.8dYvM8CBEdqiF9ZZhaYRKhtOin_wYGf4JYrmTTIsX74"

supabase: Client = create_client(SUPABASE_URL, SUPABASE_KEY)


@app.route("/")
def home():
    return "API online"


@app.route("/ranking", methods=["POST"])
def ranking():

    body = request.get_json()
    if not body or "eventCode" not in body:
        return jsonify({"error": "eventCode requerido"}), 400

    eventCode = body["eventCode"]

    try:
        # -------------------------
        # 1️⃣ Cargar datos de Supabase
        # -------------------------
        pits = supabase.table("pits").select("*").execute().data or []
        matches = supabase.table("matches").select("*").execute().data or []

        if not pits or not matches:
            return jsonify([])

        # Indexar pits por (team, region)
        pits_index = {(p["team_number"], p["region"]): p for p in pits}

        # -------------------------
        # 2️⃣ Unir matches + pits SIN PANDAS
        # -------------------------
        unidos = []
        for m in matches:
            key = (m["team_number"], m["regional"])
            pit = pits_index.get(key, {})

            unidos.append({**m, **pit})

        # -------------------------
        # 3️⃣ Calcular score por match
        # -------------------------
        score_cols = [
            'check_inicio', 'count_motiv',
            'count_in_cage_auto', 'count_out_cage_auto',
            'count_in_cage_teleop', 'count_out_cage_teleop',
            'count_rp', 'check_scoring',
            'count_in_cage_endgame', 'count_out_cage_endgame',
            'check_full_park', 'check_partial_park', 'check_high',
            'cycle_number', 'artifacts_number', 'check1'
        ]

        for row in unidos:
            total = 0
            for col in score_cols:
                total += float(row.get(col, 0) or 0)
            row["score"] = total

        # -------------------------
        # 4️⃣ Agrupar por equipo
        # -------------------------
        teams = {}
        for row in unidos:
            t = row["team_number"]
            if t not in teams:
                teams[t] = {
                    "team_number": t,
                    "score_list": [],
                    "auto_in": 0,
                    "teleop_in": 0
                }

            teams[t]["score_list"].append(row["score"])
            teams[t]["auto_in"] += row.get("count_in_cage_auto", 0)
            teams[t]["teleop_in"] += row.get("count_in_cage_teleop", 0)

        # Promedio score
        for t in teams.values():
            t["score"] = round(sum(t["score_list"]) / len(t["score_list"]), 2)

        # -------------------------
        # 5️⃣ Ranking FTC (HTTP)
        # -------------------------
        def ftc_rank(team):
            try:
                url = f"http://ftc-api.firstinspires.org/v2.0/2024/rankings/{eventCode}"
                r = requests.get(url, auth=HTTPBasicAuth(
                    "crisesv4",
                    "E936A6EC-14B0-4904-8DF4-E4916CA4E9BB"
                ))
                r.raise_for_status()
                ranks = r.json().get("rankings", [])
                for item in ranks:
                    if item["teamNumber"] == team:
                        return item.get("rank")
            except:
                return None
            return None

        for t in teams.values():
            t["ftc_rank"] = ftc_rank(t["team_number"])

        # -------------------------
        # 6️⃣ Calcular alliance_score
        # -------------------------
        for t in teams.values():
            eff = (t["auto_in"] + t["teleop_in"]) / (t["score"] + 1)
            frs = 1 / t["ftc_rank"] if t["ftc_rank"] else 0
            t["alliance_score"] = t["score"] * 0.6 + eff * 0.3 + frs * 0.1

        # -------------------------
        # 7️⃣ Ordenar
        # -------------------------
        result = sorted(
            teams.values(),
            key=lambda x: x["alliance_score"],
            reverse=True
        )

        return jsonify(result)

    except Exception as e:
        return jsonify({"error": str(e)}), 500
