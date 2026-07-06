"""Serveur Flask principal : stream video en direct, statut et statistiques de detection.
Un thread worker gere la boucle capture -> inference -> decision -> photo + journal + son BLE.
Tous les reglages viennent de config.yaml ; point d'entree lance par le service systemd."""
import glob
import socket
import sys
import threading
import time
from datetime import datetime
from pathlib import Path

import cv2
from flask import Flask, Response, jsonify, request, send_file

sys.path.append(str(Path(__file__).resolve().parent))
from config import CFG, chemin
from camera import Camera
from detector_eim import PerrucheDetectorEIM
from decision import Decision
from ble_client import BLEGestionnaire
from journal import Journal

D = CFG["detection"]
C = CFG["camera"]
B = CFG["ble"]
BM = CFG["ble_moteur"]
H = CFG.get("horaires", {})
SEUIL = float(D["seuil"])
COOLDOWN_S = float(D["cooldown_s"])
FLOU_MIN = float(D.get("flou_min", 80))
DEBUT_NUIT = int(H.get("debut_nuit", 21))
FIN_NUIT = int(H.get("fin_nuit", 6))
DOSSIER = chemin("detections")

NOM_SON = B["nom"]
NOM_MOTEUR = BM["nom"]

app = Flask(__name__)
ble = BLEGestionnaire(carac_uuid=B["carac_uuid"])
ble.enregistrer(NOM_SON)
ble.enregistrer(NOM_MOTEUR)

_lock = threading.Lock()
_jpeg = None
_seuil_cible = SEUIL
_mode_force = None  # None=auto, "nuit"=force nuit, "jour"=force jour
_status = {
    "present": False, "score": 0.0, "count": 0, "sons": 0, "ble_son": False, "ble_moteur": False,
    "fps": 0.0, "infer_ms": 0, "uptime": 0, "last": None,
    "seuil": SEUIL, "seuil_defaut": SEUIL, "fin_nuit": FIN_NUIT,
    "mode_nuit": False, "mode_force": None,
    "cpu": None, "ram": None, "temp": None,
    "derniere_photo": None,
}


def _est_nuit(heure):
    if _mode_force == "nuit":
        return True
    if _mode_force == "jour":
        return False
    # automatique : suit les horaires
    if DEBUT_NUIT > FIN_NUIT:
        return heure >= DEBUT_NUIT or heure < FIN_NUIT
    return DEBUT_NUIT <= heure < FIN_NUIT


def _est_floue(frame):
    gray = cv2.resize(cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY), (320, 240))
    return cv2.Laplacian(gray, cv2.CV_64F).var() < FLOU_MIN


def _trouver_derniere_photo():
    try:
        photos = sorted(DOSSIER.glob("*.jpg"), key=lambda p: p.stat().st_mtime)
        return photos[-1].name if photos else None
    except Exception:
        return None


def _score_vers_bgr(score):
    """Interpole vert -> jaune -> rouge selon le score (0..1)."""
    s = max(0.0, min(1.0, score))
    if s < 0.5:
        r, g = int(s * 2 * 210), 175
    else:
        r, g = 210, int((1 - (s - 0.5) * 2) * 175)
    return (0, g, r)


def overlay(frame, score, present):
    h, w = frame.shape[:2]
    couleur = _score_vers_bgr(score)
    cv2.rectangle(frame, (0, 0), (w, 70), couleur, -1)
    texte = "PERRUCHE !" if present else "RAS"
    cv2.putText(frame, texte, (20, 50),
                cv2.FONT_HERSHEY_SIMPLEX, 1.4, (255, 255, 255), 3)
    cv2.putText(frame, f"score: {score:.2f}", (20, h - 25),
                cv2.FONT_HERSHEY_SIMPLEX, 0.8, (255, 255, 255), 2)
    larg = int((w - 40) * min(max(score, 0.0), 1.0))
    cv2.rectangle(frame, (20, h - 15), (20 + larg, h - 8), couleur, -1)
    return frame


def worker():
    global _jpeg
    DOSSIER.mkdir(parents=True, exist_ok=True)
    journal = Journal(chemin("journal"))
    debut = time.time()
    dernier_son = 0.0
    sons = 0
    derniere_detection = None

    with _lock:
        _status["derniere_photo"] = _trouver_derniere_photo()

    while True:
        heure = datetime.now().hour
        if _est_nuit(heure):
            with _lock:
                _status["mode_nuit"] = True
                _status["uptime"] = round(time.time() - debut)
            time.sleep(5)
            continue

        with _lock:
            _status["mode_nuit"] = False
            seuil_courant = _seuil_cible

        # Nouvel objet Decision a chaque reprise de jour (remet l'hysteresis a zero)
        decision = Decision(
            seuil=seuil_courant, n_requis=D["n_requis"],
            fenetre=D["fenetre"], n_perte=D["n_perte"],
        )
        fps = 0.0
        infer_ms = 0.0
        t_prev = time.time()
        score = 0.0
        present = False

        with Camera(width=C["largeur"], height=C["hauteur"], focus=C["focus"]) as cam, \
                PerrucheDetectorEIM() as detector:
            for _ in range(5):
                cam.read()

            while True:
                if _est_nuit(datetime.now().hour):
                    break

                frame = cam.read()
                if frame is None:
                    continue

                with _lock:
                    if _seuil_cible != decision.seuil:
                        decision.seuil = _seuil_cible

                # Frame floue (secousse camera) : recycler le score precedent
                if _est_floue(frame):
                    img = overlay(frame.copy(), score, present)
                    ok, buf = cv2.imencode(".jpg", img, [cv2.IMWRITE_JPEG_QUALITY, 70])
                    now_s = time.time(); dt_s = now_s - t_prev; t_prev = now_s
                    if dt_s > 0:
                        fps = 0.9 * fps + 0.1 * (1.0 / dt_s) if fps else 1.0 / dt_s
                    if ok:
                        with _lock:
                            _jpeg = buf.tobytes()
                            _status["fps"] = round(fps, 1)
                            _status["uptime"] = round(now_s - debut)
                    continue

                t0 = time.time()
                score = detector.predict(frame).get("perruche", 0.0)
                infer = (time.time() - t0) * 1000.0
                infer_ms = 0.85 * infer_ms + 0.15 * infer if infer_ms else infer

                present, evenement = decision.update(score)
                if evenement:
                    son_joue = False
                    if time.time() - dernier_son >= COOLDOWN_S:
                        son_joue = ble.trigger(NOM_SON)
                        ble.trigger(NOM_MOTEUR)
                        if son_joue:
                            dernier_son = time.time()
                            sons += 1
                    ts = datetime.now().strftime("%Y-%m-%d_%H-%M-%S")
                    nom = f"{ts}_perruche_{score:.2f}.jpg"
                    cv2.imwrite(str(DOSSIER / nom), frame)
                    journal.detection(score, son_joue)
                    derniere_detection = time.time()
                    with _lock:
                        _status["count"] += 1
                        _status["derniere_photo"] = nom

                now = time.time()
                dt = now - t_prev
                t_prev = now
                if dt > 0:
                    inst = 1.0 / dt
                    fps = 0.9 * fps + 0.1 * inst if fps else inst

                img = overlay(frame.copy(), score, present)
                ok, buf = cv2.imencode(".jpg", img, [cv2.IMWRITE_JPEG_QUALITY, 70])
                if ok:
                    with _lock:
                        _jpeg = buf.tobytes()
                        _status["score"] = round(score, 3)
                        _status["present"] = present
                        _status["ble_son"] = ble.is_connected(NOM_SON)
                        _status["ble_moteur"] = ble.is_connected(NOM_MOTEUR)
                        _status["fps"] = round(fps, 1)
                        _status["infer_ms"] = round(infer_ms)
                        _status["sons"] = sons
                        _status["uptime"] = round(now - debut)
                        _status["last"] = None if derniere_detection is None else round(now - derniere_detection)
                        _status["seuil"] = round(decision.seuil, 2)

                time.sleep(0.01)


def _sysinfo_worker():
    try:
        import psutil
    except ImportError:
        psutil = None

    # Cherche le premier fichier de temperature disponible
    temp_files = sorted(glob.glob("/sys/class/thermal/thermal_zone*/temp"))

    while True:
        if psutil:
            cpu = psutil.cpu_percent(interval=1)
            ram = psutil.virtual_memory().percent
        else:
            cpu = ram = None

        temp = None
        if temp_files:
            try:
                with open(temp_files[0]) as f:
                    temp = int(f.read().strip()) / 1000.0
            except Exception:
                pass

        with _lock:
            _status["cpu"] = round(cpu) if cpu is not None else None
            _status["ram"] = round(ram) if ram is not None else None
            _status["temp"] = round(temp, 1) if temp is not None else None

        time.sleep(5)


def flux():
    while True:
        with _lock:
            data = _jpeg
        if data is None:
            time.sleep(0.2)
            continue
        yield (b"--frame\r\nContent-Type: image/jpeg\r\n\r\n" + data + b"\r\n")
        time.sleep(0.05)


PAGE = """<!doctype html>
<html lang="fr"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>Detecteur de perruches</title>
<style>
  body{margin:0;background:#0f1115;color:#e8e8e8;font-family:system-ui,Arial,sans-serif;text-align:center}
  h1{font-weight:600;margin:18px}
  #wrap{max-width:900px;margin:0 auto;padding:0 12px 30px}
  #banner{font-size:34px;font-weight:800;padding:16px;border-radius:12px;margin:12px 0;transition:background .3s}
  .livevid{width:100%;border-radius:12px;border:1px solid #2a2e37}
  .nuit-msg{background:#0d1020;border:2px solid #1a2540;border-radius:12px;padding:48px;
            font-size:22px;color:#4a5580;display:none;margin:8px 0}
  .row{display:flex;gap:10px;justify-content:center;align-items:stretch;flex-wrap:wrap;margin:10px 0}
  .card{background:#1a1d24;border:1px solid #2a2e37;border-radius:10px;padding:10px 16px;font-size:15px}
  .card-wide{background:#1a1d24;border:1px solid #2a2e37;border-radius:10px;padding:12px 16px;
             font-size:14px;flex:1;min-width:260px;box-sizing:border-box;text-align:left}
  button{font-size:15px;padding:9px 16px;border:0;border-radius:8px;background:#3b6ef0;color:#fff;cursor:pointer}
  button.sec{background:#444}
  .dot{height:10px;width:10px;border-radius:50%;display:inline-block;margin-right:5px;background:#888}
  .lbl{text-align:left;font-size:13px;color:#9aa3af;margin:14px 0 4px}
  input[type=range]{flex:1;min-width:80px;accent-color:#3b6ef0;vertical-align:middle}
  table{width:100%;border-collapse:collapse;font-size:13px}
  th{color:#9aa3af;font-weight:500;padding:7px 6px;border-bottom:1px solid #2a2e37;text-align:left}
  td{padding:6px;border-bottom:1px solid #18191f}
  #derniere_img{max-height:220px;width:auto;border-radius:10px;border:1px solid #2a2e37;display:none}
</style></head>
<body><div id="wrap">
  <h1>Detecteur de perruches</h1>
  <div id="banner" style="background:#1f7a1f">...</div>

  <img class="livevid" id="livevid" src="/video" alt="flux camera"
       onerror="setTimeout(()=>{this.src='/video?t='+Date.now()},2000)">
  <div class="nuit-msg" id="nuit_msg">Mode nuit — camera en veille</div>

  <div class="row">
    <div class="card">CPU&nbsp;: <b id="cpu">—</b></div>
    <div class="card">RAM&nbsp;: <b id="ram">—</b></div>
    <div class="card">Temp&nbsp;: <b id="temp">—</b></div>
    <div class="card">Mode&nbsp;: <b id="mode">Jour</b></div>
  </div>

  <div class="row">
    <div class="card">Score&nbsp;: <b id="score">0.00</b></div>
    <div class="card">Seuil&nbsp;: <b id="seuil_act">0.60</b></div>
    <div class="card">FPS&nbsp;: <b id="fps">0</b></div>
    <div class="card">Inference&nbsp;: <b id="infer">0 ms</b></div>
  </div>

  <div class="row">
    <div class="card">Detections&nbsp;: <b id="count">0</b></div>
    <div class="card">Sons joues&nbsp;: <b id="sons">0</b></div>
    <div class="card">Derniere&nbsp;: <b id="last">—</b></div>
    <div class="card">Uptime&nbsp;: <b id="uptime">0s</b></div>
    <div class="card"><span class="dot" id="dot_son"></span>Son <b id="ble_son">?</b></div>
    <div class="card"><span class="dot" id="dot_moteur"></span>Moteur <b id="ble_moteur">?</b></div>
  </div>

  <div class="lbl">Score en direct (ligne pointillee = seuil)</div>
  <canvas id="graph" width="600" height="90"
    style="width:100%;background:#1a1d24;border:1px solid #2a2e37;border-radius:10px"></canvas>

  <div class="row" style="margin-top:14px">
    <button onclick="testSon()">Tester le son</button>
    <button onclick="testMoteur()">Tester le moteur</button>
    <button id="nuit_btn" class="sec" onclick="toggleNuit()">Forcer mode nuit</button>
  </div>

  <div class="lbl">Derniere detection capturee</div>
  <div style="text-align:left">
    <img id="derniere_img" src="" alt="derniere detection">
    <span id="no_photo" style="color:#555;font-size:14px">Aucune detection enregistree</span>
  </div>

  <div class="lbl">10 dernieres detections</div>
  <table>
    <thead><tr><th>Horodatage</th><th>Score</th><th>Son joue</th></tr></thead>
    <tbody id="tbody_rec"><tr><td colspan="3" style="color:#555">Chargement...</td></tr></tbody>
  </table>
</div>

<script>
const hist=[], cv=document.getElementById('graph'), ctx=cv.getContext('2d');
let prevCount=-1, prevPresent=false;

function set(id,v){document.getElementById(id).textContent=v;}
function fmt(s){if(s==null)return'—';const m=Math.floor(s/60),x=s%60;return m?m+'m'+String(x).padStart(2,'0'):x+'s';}

function pushGraph(v,seuil){
  hist.push(v);if(hist.length>80)hist.shift();
  const W=cv.width,H=cv.height;ctx.clearRect(0,0,W,H);
  ctx.strokeStyle='#555';ctx.setLineDash([4,4]);ctx.beginPath();
  const yT=H-seuil*H;ctx.moveTo(0,yT);ctx.lineTo(W,yT);ctx.stroke();ctx.setLineDash([]);
  ctx.strokeStyle='#3b6ef0';ctx.lineWidth=2;ctx.beginPath();
  hist.forEach((val,i)=>{const x=i/Math.max(hist.length-1,1)*W,y=H-val*H;i?ctx.lineTo(x,y):ctx.moveTo(x,y);});
  ctx.stroke();
}

function alerter(){
  document.title='⚠ PERRUCHE !';
  setTimeout(()=>document.title='Detecteur de perruches',4000);
}

async function toggleNuit(){
  try{await fetch('/toggle_nuit',{method:'POST'});}catch(e){}
}

function majBtnNuit(force,nuit){
  const btn=document.getElementById('nuit_btn');
  if(force==='nuit'){btn.textContent='Mode nuit force — reprendre';btn.style.background='#e67e22';}
  else if(force==='jour'){btn.textContent='Mode jour force — reprendre';btn.style.background='#27ae60';}
  else if(nuit){btn.textContent='Forcer mode jour (tests)';btn.style.background='';}
  else{btn.textContent='Forcer mode nuit';btn.style.background='';}
}


function majPhoto(count){
  const img=document.getElementById('derniere_img'),ph=document.getElementById('no_photo');
  if(count>0){img.src='/derniere_photo?t='+Date.now();img.style.display='block';ph.style.display='none';}
}

async function majTableau(){
  try{
    const data=await(await fetch('/journal_recent')).json();
    const tbody=document.getElementById('tbody_rec');
    if(!data.length){tbody.innerHTML='<tr><td colspan="3" style="color:#555">Aucune detection dans le journal</td></tr>';return;}
    tbody.innerHTML=data.map(r=>`<tr><td>${r.horodatage}</td><td>${parseFloat(r.score).toFixed(3)}</td><td>${r.son?'✓':'—'}</td></tr>`).join('');
  }catch(e){}
}

async function maj(){
  try{
    const s=await(await fetch('/status')).json();
    const nuit=s.mode_nuit;
    document.getElementById('livevid').style.display=nuit?'none':'block';
    document.getElementById('nuit_msg').style.display=nuit?'block':'none';

    const b=document.getElementById('banner');
    if(nuit){b.textContent='Mode nuit — reprise a '+s.fin_nuit+'h';b.style.background='#0d1020';}
    else{
      const hue=Math.round((1-s.score)*120);
      b.style.background=`hsl(${hue},75%,26%)`;
      if(s.present)b.textContent='PERRUCHE detectee';
      else if(s.score>=s.seuil)b.textContent='Detection en cours...';
      else b.textContent='Pas de perruche';
    }

    if(s.present&&!prevPresent)alerter();
    prevPresent=s.present;

    set('score',s.score.toFixed(2));set('seuil_act',s.seuil.toFixed(2));
    if(!nuit){const h=Math.round((1-s.score)*120);document.getElementById('score').style.color=`hsl(${h},90%,60%)`;}
    else{document.getElementById('score').style.color='';}
    set('fps',s.fps.toFixed(1));set('infer',s.infer_ms+' ms');
    set('count',s.count);set('sons',s.sons);set('last',fmt(s.last));set('uptime',fmt(s.uptime));
    document.getElementById('ble_son').textContent=s.ble_son?'connecte':'off';
    document.getElementById('dot_son').style.background=s.ble_son?'#2ecc71':'#888';
    document.getElementById('ble_moteur').textContent=s.ble_moteur?'connecte':'off';
    document.getElementById('dot_moteur').style.background=s.ble_moteur?'#2ecc71':'#888';

    set('cpu',s.cpu!==null?s.cpu+'%':'—');
    set('ram',s.ram!==null?s.ram+'%':'—');
    set('temp',s.temp!==null?s.temp+'°C':'—');
    set('mode',nuit?'Nuit':'Jour');

    majBtnNuit(s.mode_force||null,nuit);

    if(s.count!==prevCount){majPhoto(s.count);prevCount=s.count;}
    if(!nuit)pushGraph(s.score,s.seuil);
  }catch(e){}
}

async function testSon(){try{await fetch('/test_son',{method:'POST'});}catch(e){}}
async function testMoteur(){try{await fetch('/test_moteur',{method:'POST'});}catch(e){}}

setInterval(maj,250);
setInterval(majTableau,10000);
maj();majTableau();
</script></body></html>"""


@app.route("/")
def index():
    return PAGE


@app.route("/video")
def video():
    return Response(flux(), mimetype="multipart/x-mixed-replace; boundary=frame")


@app.route("/status")
def status():
    with _lock:
        return jsonify(dict(_status))


@app.route("/test_son", methods=["POST"])
def test_son():
    return jsonify({"ok": ble.trigger(NOM_SON)})


@app.route("/test_moteur", methods=["POST"])
def test_moteur():
    return jsonify({"ok": ble.trigger(NOM_MOTEUR)})


@app.route("/set_seuil", methods=["POST"])
def set_seuil():
    global _seuil_cible
    try:
        val = float(request.get_json(force=True).get("seuil", SEUIL))
        val = max(0.30, min(0.95, val))
    except Exception:
        val = SEUIL
    with _lock:
        _seuil_cible = val
        _status["seuil"] = round(val, 2)
    return jsonify({"ok": True, "seuil": round(val, 2)})


@app.route("/reset_seuil", methods=["POST"])
def reset_seuil():
    global _seuil_cible
    with _lock:
        _seuil_cible = SEUIL
        _status["seuil"] = round(SEUIL, 2)
    return jsonify({"ok": True, "seuil": SEUIL})


@app.route("/toggle_nuit", methods=["POST"])
def toggle_nuit():
    global _mode_force
    if _mode_force is not None:
        # déjà en mode forcé → retour en automatique
        _mode_force = None
    else:
        # automatique → forcer l'opposé de l'heure naturelle
        h = datetime.now().hour
        if DEBUT_NUIT > FIN_NUIT:
            nat_nuit = h >= DEBUT_NUIT or h < FIN_NUIT
        else:
            nat_nuit = DEBUT_NUIT <= h < FIN_NUIT
        _mode_force = "jour" if nat_nuit else "nuit"
    with _lock:
        _status["mode_force"] = _mode_force
    return jsonify({"ok": True, "force": _mode_force})


@app.route("/derniere_photo")
def derniere_photo():
    with _lock:
        nom = _status.get("derniere_photo")
    if nom:
        chemin_photo = DOSSIER / nom
        if chemin_photo.exists():
            return send_file(str(chemin_photo), mimetype="image/jpeg")
    return "", 404


@app.route("/journal_recent")
def journal_recent():
    try:
        with open(chemin("journal"), "r", encoding="utf-8") as f:
            lignes = f.readlines()
        data = [l.strip().split(",") for l in lignes[1:] if l.strip()]
        recentes = data[-10:][::-1]
        return jsonify([
            {"horodatage": r[0], "score": float(r[1]), "son": int(r[2])}
            for r in recentes if len(r) == 3
        ])
    except Exception:
        return jsonify([])


if __name__ == "__main__":
    # Afficher l'adresse du dashboard au demarrage
    port = CFG["web"]["port"]
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        s.connect(("8.8.8.8", 80))
        ip = s.getsockname()[0]
        s.close()
    except Exception:
        ip = "inconnue"
    print(f"[WEB] Dashboard : http://{ip}:{port}", flush=True)
    print(f"[WEB] Local     : http://localhost:{port}", flush=True)

    ble.start()
    threading.Thread(target=worker, daemon=True).start()
    threading.Thread(target=_sysinfo_worker, daemon=True).start()
    app.run(host="0.0.0.0", port=port, threaded=True, debug=False)
