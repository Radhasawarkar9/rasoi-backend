"""
RasoiExpress Backend — Supabase PostgreSQL Edition
Uses pg8000 (pure Python) — works on all platforms including Render Free Tier
"""
import os, sys, json, hashlib, hmac, random, string, functools
from datetime import datetime, timedelta, timezone
from flask import Flask, request, jsonify, g, session, render_template_string, redirect

# Load .env file if present
try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass

try:
    import jwt
except ImportError:
    print("ERROR: Run pip install PyJWT"); sys.exit(1)

try:
    import pg8000.native
except ImportError:
    print("ERROR: Run pip install pg8000"); sys.exit(1)

try:
    import urllib.parse as urlparse
except ImportError:
    pass

# ═══════════════════════════════════════════════════════════════
#  CONFIG
# ═══════════════════════════════════════════════════════════════
SECRET_KEY        = os.environ.get("SECRET_KEY",        "rasoi-express-jwt-secret-2024")
SESSION_SECRET    = os.environ.get("SESSION_SECRET",    "rasoi-admin-session-secret-2024")
DATABASE_URL      = os.environ.get("DATABASE_URL",      "")
ADMIN_ID          = os.environ.get("ADMIN_ID",          "admin123")
ADMIN_PASSWORD    = os.environ.get("ADMIN_PASSWORD",    "secure@123")
ALLOWED_ORIGINS   = os.environ.get("ALLOWED_ORIGINS",   "*")
JWT_EXPIRY_DAYS   = 7
PBKDF2_ITERS      = 260_000
ADMIN_SESSION_KEY = "admin_ok"
MAX_LOGIN_ATTEMPTS = 5
ADMIN_PASS_HASH   = hashlib.sha256(ADMIN_PASSWORD.encode()).hexdigest()
login_attempts    = {}

# ═══════════════════════════════════════════════════════════════
#  DATABASE — pg8000 (Pure Python PostgreSQL)
# ═══════════════════════════════════════════════════════════════
def parse_db_url(url):
    """Parse postgres:// URL into connection params."""
    r = urlparse.urlparse(url)
    return {
        "host":     r.hostname,
        "port":     r.port or 5432,
        "database": r.path.lstrip("/"),
        "user":     r.username,
        "password": r.password,
        "ssl_context": True,
    }

def get_db():
    if "db" not in g:
        if not DATABASE_URL:
            raise RuntimeError("DATABASE_URL is not set in environment variables!")
        params = parse_db_url(DATABASE_URL)
        g.db = pg8000.native.Connection(**params)
    return g.db

def close_db(e=None):
    db = g.pop("db", None)
    if db:
        try:
            db.close()
        except Exception:
            pass

def rows_to_dicts(rows, columns):
    """Convert pg8000 rows + column info to list of dicts."""
    if not rows:
        return []
    col_names = [c["name"] for c in columns]
    return [dict(zip(col_names, row)) for row in rows]

def q1(sql, p=None):
    """Return first row as dict, or None."""
    try:
        db   = get_db()
        rows = db.run(sql, **(p or {}))
        cols = db.columns
        result = rows_to_dicts(rows, cols)
        return result[0] if result else None
    except Exception as e:
        print(f"q1 error: {e}, sql={sql}")
        return None

def qa(sql, p=None):
    """Return all rows as list of dicts."""
    try:
        db   = get_db()
        rows = db.run(sql, **(p or {}))
        cols = db.columns
        return rows_to_dicts(rows, cols)
    except Exception as e:
        print(f"qa error: {e}, sql={sql}")
        return []

def run(sql, p=None):
    """Execute INSERT/UPDATE/DELETE, return inserted id if available."""
    try:
        db   = get_db()
        rows = db.run(sql, **(p or {}))
        if rows and rows[0]:
            return rows[0][0]
        return None
    except Exception as e:
        print(f"run error: {e}, sql={sql}")
        return None

def log_action(action, details=""):
    ip = "unknown"
    try:
        ip = request.remote_addr or "unknown"
        run("INSERT INTO activity_log(action, details, ip) VALUES (:action, :details, :ip)",
            {"action": action, "details": details, "ip": ip})
    except Exception:
        pass

# ═══════════════════════════════════════════════════════════════
#  SCHEMA — Create tables in Supabase
# ═══════════════════════════════════════════════════════════════
SCHEMA_STATEMENTS = [
    """CREATE TABLE IF NOT EXISTS users (
        id            SERIAL PRIMARY KEY,
        name          TEXT    NOT NULL,
        email         TEXT    NOT NULL UNIQUE,
        password      TEXT    NOT NULL,
        phone         TEXT    DEFAULT '',
        address       TEXT    DEFAULT '',
        picture       TEXT    DEFAULT '',
        profile_color TEXT    DEFAULT '#1A6FB3',
        is_blocked    BOOLEAN DEFAULT FALSE,
        created_at    TIMESTAMPTZ DEFAULT NOW()
    )""",
    """CREATE TABLE IF NOT EXISTS menu_items (
        id          SERIAL PRIMARY KEY,
        name        TEXT    NOT NULL,
        description TEXT    DEFAULT '',
        price       REAL    NOT NULL,
        category    TEXT    NOT NULL,
        type        TEXT    DEFAULT 'veg',
        restaurant  TEXT    DEFAULT '',
        rating      REAL    DEFAULT 4.0,
        image       TEXT    DEFAULT '',
        emoji       TEXT    DEFAULT '🍛',
        is_spicy    BOOLEAN DEFAULT FALSE,
        is_new      BOOLEAN DEFAULT FALSE,
        is_best     BOOLEAN DEFAULT FALSE,
        time        TEXT    DEFAULT '30 mins',
        available   BOOLEAN DEFAULT TRUE
    )""",
    """CREATE TABLE IF NOT EXISTS orders (
        id           TEXT    PRIMARY KEY,
        user_id      INTEGER NOT NULL,
        items        TEXT    NOT NULL,
        total        REAL    NOT NULL,
        restaurant   TEXT    DEFAULT '',
        address      TEXT    DEFAULT '',
        status       TEXT    DEFAULT 'placed',
        current_step INTEGER DEFAULT 0,
        placed_at    TIMESTAMPTZ DEFAULT NOW()
    )""",
    """CREATE TABLE IF NOT EXISTS activity_log (
        id         SERIAL PRIMARY KEY,
        action     TEXT    NOT NULL,
        details    TEXT    DEFAULT '',
        ip         TEXT    DEFAULT '',
        created_at TIMESTAMPTZ DEFAULT NOW()
    )""",
]

SAMPLE_DISHES = [
    ("Paneer Butter Masala","Rich buttery tomato-cashew gravy with paneer.",260,"Veg Curries","veg","Shree Bhavan",4.8,"https://www.indianhealthyrecipes.com/wp-content/uploads/2021/07/paneer-butter-masala.webp","🧀",False,False,True,"25 mins"),
    ("Dal Makhani","Slow-cooked black lentils in butter and cream.",190,"Veg Curries","veg","Maa Ki Rasoi",4.9,"https://myfoodstory.com/wp-content/uploads/2018/08/Dal-Makhani-New-3.jpg","🫘",False,False,True,"20 mins"),
    ("Palak Paneer","Spinach puree with paneer cubes.",230,"Veg Curries","veg","Shree Bhavan",4.6,"https://www.indianveggiedelight.com/wp-content/uploads/2017/10/palak-paneer-recipe-featured.jpg","🌿",False,False,False,"25 mins"),
    ("Chana Masala","Chickpeas in bold tangy masala.",170,"Veg Curries","veg","Chaat Corner",4.8,"https://encrypted-tbn0.gstatic.com/images?q=tbn:ANd9GcQmtyKzYZir0Tz85yb6Flife9PoIDBw35LHkg&s","🫘",True,False,True,"18 mins"),
    ("Masala Dosa","Crispy crepe with spiced potato filling.",140,"South Indian","veg","South Spice",4.8,"https://www.cookwithmanali.com/wp-content/uploads/2020/05/Masala-Dosa-500x500.jpg","🥞",False,False,True,"18 mins"),
    ("Chicken Biryani","Hyderabadi dum biryani with saffron rice.",330,"Biryani & Rice","nonveg","Biryani Darbar",4.9,"https://www.cubesnjuliennes.com/wp-content/uploads/2020/07/Chicken-Biryani-Recipe.jpg","🍚",True,False,True,"40 mins"),
    ("Veg Biryani","Fragrant basmati with seasonal vegetables.",260,"Biryani & Rice","veg","Biryani Darbar",4.5,"https://encrypted-tbn0.gstatic.com/images?q=tbn:ANd9GcSlg7JYWWJNnY-MJVGm02itthRtcc105HPt4Q&s","🌾",True,False,False,"35 mins"),
    ("Butter Chicken","Tender chicken in silky tomato-butter gravy.",290,"Non-Veg Curries","nonveg","Maa Ki Rasoi",4.9,"https://www.licious.in/blog/wp-content/uploads/2020/10/butter-chicken--600x600.jpg","🍗",False,False,True,"30 mins"),
    ("Mutton Biryani","Tender mutton with aromatic basmati dum.",410,"Biryani & Rice","nonveg","Biryani Darbar",4.8,"https://www.cubesnjuliennes.com/wp-content/uploads/2021/03/Best-Mutton-Biryani-Recipe.jpg","🍖",True,False,False,"50 mins"),
    ("Chole Bhature","Spiced chickpeas with fluffy fried bread.",160,"Street Food","veg","Chaat Corner",4.8,"https://encrypted-tbn0.gstatic.com/images?q=tbn:ANd9GcRyta2FEc05FPDkoHtzey9a8nmlgumGb7lDew&s","🫘",True,True,True,"25 mins"),
    ("Pav Bhaji","Spicy vegetable mash with butter-toasted buns.",160,"Street Food","veg","Chaat Corner",4.7,"https://www.cubesnjuliennes.com/wp-content/uploads/2020/07/Instant-Pot-Mumbai-Pav-Bhaji-Recipe.jpg","🍞",True,False,False,"20 mins"),
    ("Vada Pav","Mumbai spiced potato fritter in pav bun.",70,"Street Food","veg","Street Bites",4.8,"https://blog.swiggy.com/wp-content/uploads/2024/11/Image-1_mumbai-vada-pav-1024x538.png","🍔",True,False,True,"12 mins"),
    ("Paneer Tikka","Marinated paneer grilled in tandoor.",320,"Snacks","veg","Tandoor King",4.8,"https://encrypted-tbn0.gstatic.com/images?q=tbn:ANd9GcRJ2WY2YmIJtXrpmDToEHwJIOAcyBefjpFwXg&s","🍢",True,False,True,"28 mins"),
    ("Gulab Jamun","Milk dumplings in rose-cardamom syrup.",95,"Desserts","veg","Mithaas",4.9,"https://encrypted-tbn0.gstatic.com/images?q=tbn:ANd9GcRD5KYcR79wTcJv7U6nYzIGNIU5iEBK0AoPkQ&s","🍮",False,False,True,"12 mins"),
    ("Mango Lassi","Chilled yogurt with Alphonso mango pulp.",85,"Drinks","veg","Shree Bhavan",4.8,"https://flavorquotient.com/wp-content/uploads/2023/05/Mango-Lassi-FQ-6-1036.jpg","🥭",False,False,True,"10 mins"),
    ("Masala Chai","Aromatic tea with ginger and cardamom.",55,"Drinks","veg","Maa Ki Rasoi",4.9,"https://www.thespicehouse.com/cdn/shop/articles/Chai_Masala_Tea_1200x1200.jpg?v=1606936195","🍵",False,False,False,"10 mins"),
    ("Garlic Naan","Tandoor-baked naan with garlic butter.",75,"Breads","veg","Tandoor King",4.7,"https://i0.wp.com/upbeetanisha.com/wp-content/uploads/2021/07/DSC_7315.jpg?w=1200&ssl=1","🫓",False,False,False,"14 mins"),
    ("Aloo Paratha","Wheat bread stuffed with spiced potato.",130,"Breads","veg","Maa Ki Rasoi",4.8,"https://www.kingarthurbaking.com/sites/default/files/2025-07/Aloo-Paratha-_2025_Lifestyle_H_2435.jpg","🫓",False,False,False,"18 mins"),
    ("Idli Sambar","Steamed rice cakes with tangy sambar.",100,"South Indian","veg","South Spice",4.5,"https://encrypted-tbn0.gstatic.com/images?q=tbn:ANd9GcS3aJyP7SxhdvtHtorSod6skM3K2BTE3N_Ouw&s","🫕",False,False,False,"15 mins"),
    ("Samosa","Crispy pastry with spiced potato filling.",65,"Snacks","veg","Chaat Corner",4.6,"https://prashantbandhu.com/wp-content/uploads/2023/07/DSC_0413-scaled.jpg","🥟",False,False,False,"12 mins"),
]

def init_db():
    """Create tables and seed menu on startup."""
    try:
        params = parse_db_url(DATABASE_URL)
        db = pg8000.native.Connection(**params)
        for stmt in SCHEMA_STATEMENTS:
            try:
                db.run(stmt)
            except Exception as e:
                print(f"Schema warning: {e}")
        # Check menu
        rows = db.run("SELECT COUNT(*) as c FROM menu_items")
        count = rows[0][0] if rows else 0
        if count == 0:
            for d in SAMPLE_DISHES:
                try:
                    db.run(
                        "INSERT INTO menu_items(name,description,price,category,type,restaurant,rating,image,emoji,is_spicy,is_new,is_best,time) "
                        "VALUES(:n,:desc,:price,:cat,:tp,:rest,:rat,:img,:em,:sp,:nw,:bs,:tm)",
                        n=d[0],desc=d[1],price=d[2],cat=d[3],tp=d[4],rest=d[5],rat=d[6],
                        img=d[7],em=d[8],sp=d[9],nw=d[10],bs=d[11],tm=d[12]
                    )
                except Exception:
                    pass
            print(f"✅  Menu seeded with {len(SAMPLE_DISHES)} dishes")
        else:
            print(f"✅  Menu already has {count} dishes")
        db.close()
        print("✅  Supabase PostgreSQL: tables ready")
    except Exception as e:
        print(f"⚠️  DB init error: {e}")

# ═══════════════════════════════════════════════════════════════
#  PASSWORD & JWT
# ═══════════════════════════════════════════════════════════════
def hash_pw(plain):
    salt = os.urandom(16)
    dk   = hashlib.pbkdf2_hmac("sha256", plain.encode(), salt, PBKDF2_ITERS)
    return salt.hex() + "$" + dk.hex()

def check_pw(plain, stored):
    try:
        salt_hex, hash_hex = stored.split("$", 1)
    except Exception:
        return False
    dk = hashlib.pbkdf2_hmac("sha256", plain.encode(), bytes.fromhex(salt_hex), PBKDF2_ITERS)
    return hmac.compare_digest(dk.hex(), hash_hex)

def make_token(uid, email):
    return jwt.encode(
        {"user_id": uid, "email": email,
         "exp": datetime.now(timezone.utc) + timedelta(days=JWT_EXPIRY_DAYS),
         "iat": datetime.now(timezone.utc)},
        SECRET_KEY, algorithm="HS256"
    )

def read_token(tok):
    try:
        return jwt.decode(tok, SECRET_KEY, algorithms=["HS256"])
    except Exception:
        return None

def jwt_required(f):
    @functools.wraps(f)
    def w(*a, **kw):
        hdr = request.headers.get("Authorization", "")
        if not hdr.startswith("Bearer "):
            return jsonify({"error": "Login required"}), 401
        p = read_token(hdr.split(" ", 1)[1])
        if not p:
            return jsonify({"error": "Token expired"}), 401
        kw["cu"] = p
        return f(*a, **kw)
    return w

def admin_required(f):
    @functools.wraps(f)
    def w(*a, **kw):
        if not session.get(ADMIN_SESSION_KEY):
            return jsonify({"error": "Access Denied"}), 401
        return f(*a, **kw)
    return w

def admin_page_required(f):
    @functools.wraps(f)
    def w(*a, **kw):
        if not session.get(ADMIN_SESSION_KEY):
            return redirect("/admin")
        return f(*a, **kw)
    return w

# ═══════════════════════════════════════════════════════════════
#  FLASK APP
# ═══════════════════════════════════════════════════════════════
app = Flask(__name__)
app.secret_key = SESSION_SECRET
app.permanent_session_lifetime = timedelta(hours=4)
app.teardown_appcontext(close_db)

@app.after_request
def cors(r):
    r.headers["Access-Control-Allow-Origin"]      = ALLOWED_ORIGINS
    r.headers["Access-Control-Allow-Methods"]     = "GET,POST,PUT,DELETE,OPTIONS"
    r.headers["Access-Control-Allow-Headers"]     = "Content-Type,Authorization"
    r.headers["Access-Control-Allow-Credentials"] = "true"
    return r

@app.before_request
def preflight():
    if request.method == "OPTIONS":
        return "", 204, {
            "Access-Control-Allow-Origin":      ALLOWED_ORIGINS,
            "Access-Control-Allow-Methods":     "GET,POST,PUT,DELETE,OPTIONS",
            "Access-Control-Allow-Headers":     "Content-Type,Authorization",
            "Access-Control-Allow-Credentials": "true",
        }

# ═══════════════════════════════════════════════════════════════
#  ADMIN LOGIN PAGE
# ═══════════════════════════════════════════════════════════════
LOGIN_HTML = """<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>RasoiExpress Admin</title>
<style>
*{box-sizing:border-box;margin:0;padding:0}
body{font-family:'Segoe UI',sans-serif;background:linear-gradient(135deg,#0f172a,#1e293b);
     min-height:100vh;display:flex;align-items:center;justify-content:center}
.card{background:rgba(255,255,255,.05);backdrop-filter:blur(20px);border:1px solid rgba(255,255,255,.1);
      border-radius:24px;padding:48px 40px;width:100%;max-width:420px;box-shadow:0 25px 50px rgba(0,0,0,.5)}
.logo{text-align:center;margin-bottom:32px}
.logo span{font-size:3rem;display:block;margin-bottom:8px}
.logo h1{color:#fff;font-size:1.6rem;font-weight:800}
.logo p{color:rgba(255,255,255,.5);font-size:.85rem;margin-top:4px}
label{display:block;color:rgba(255,255,255,.7);font-size:.8rem;font-weight:600;
      text-transform:uppercase;letter-spacing:.8px;margin-bottom:8px}
.iw{position:relative;margin-bottom:20px}
input{width:100%;background:rgba(255,255,255,.08);border:1px solid rgba(255,255,255,.15);
      border-radius:12px;padding:14px 46px 14px 16px;color:#fff;font-size:.95rem;outline:none;transition:all .2s}
input::placeholder{color:rgba(255,255,255,.3)}
input:focus{border-color:#f97316;background:rgba(249,115,22,.08)}
.eye{position:absolute;right:14px;top:50%;transform:translateY(-50%);background:none;
     border:none;color:rgba(255,255,255,.4);cursor:pointer;font-size:1.1rem;padding:0}
.eye:hover{color:#fff}
.btn{width:100%;padding:15px;background:linear-gradient(135deg,#f97316,#ef4444);border:none;
     border-radius:12px;color:#fff;font-size:1rem;font-weight:700;cursor:pointer;transition:all .25s;margin-top:4px}
.btn:hover{transform:translateY(-2px);box-shadow:0 8px 25px rgba(249,115,22,.4)}
.btn:disabled{opacity:.6;cursor:not-allowed;transform:none}
.alert{padding:12px 16px;border-radius:10px;font-size:.85rem;margin-bottom:20px;display:none;font-weight:500}
.alert.show{display:block}
.err{background:rgba(239,68,68,.15);border:1px solid rgba(239,68,68,.3);color:#fca5a5}
.ok{background:rgba(34,197,94,.15);border:1px solid rgba(34,197,94,.3);color:#86efac}
hr{border:none;border-top:1px solid rgba(255,255,255,.08);margin:24px 0}
.status{display:flex;align-items:center;gap:8px;justify-content:center;font-size:.78rem;color:rgba(255,255,255,.5)}
.dot{width:8px;height:8px;border-radius:50%;background:#94a3b8}
.dot.ok{background:#22c55e;box-shadow:0 0 8px #22c55e}
.dot.err{background:#ef4444}
@keyframes pulse{0%,100%{opacity:1}50%{opacity:.3}}
.dot.check{background:#f59e0b;animation:pulse 1s infinite}
</style>
</head>
<body>
<div class="card">
  <div class="logo">
    <span>🍛</span>
    <h1>RasoiExpress</h1>
    <p>Admin Control Panel</p>
  </div>
  {% if error %}<div class="alert err show">❌ {{ error }}</div>{% endif %}
  <div class="alert" id="msg"></div>
  <form onsubmit="doLogin(event)">
    <label>Admin ID</label>
    <div class="iw"><input type="text" id="uid" placeholder="admin123" value="{{ username or '' }}" required autofocus></div>
    <label>Password</label>
    <div class="iw">
      <input type="password" id="upw" placeholder="Your password" required>
      <button type="button" class="eye" onclick="toggleEye()">👁</button>
    </div>
    <button class="btn" type="submit" id="loginBtn">🔐 Sign In</button>
  </form>
  <hr>
  <div class="status"><div class="dot check" id="dot"></div><span id="statusLbl">Checking server…</span></div>
</div>
<script>
function toggleEye(){
  const i=document.getElementById('upw');
  i.type=i.type==='password'?'text':'password';
  document.querySelector('.eye').textContent=i.type==='password'?'👁':'🙈';
}
function showMsg(m,t){
  const a=document.getElementById('msg');
  a.textContent=m; a.className='alert show '+t;
}
async function checkServer(){
  const dot=document.getElementById('dot'),lbl=document.getElementById('statusLbl');
  try{
    const r=await fetch(window.location.origin+'/api/health',{signal:AbortSignal.timeout(5000)});
    if(r.ok){dot.className='dot ok';lbl.textContent='✅ Server Online';return;}
  }catch(e){}
  dot.className='dot err';lbl.textContent='❌ Server Offline';
}
async function doLogin(e){
  e.preventDefault();
  const uid=document.getElementById('uid').value.trim();
  const pw=document.getElementById('upw').value;
  if(!uid||!pw){showMsg('Both fields required','err');return;}
  const btn=document.getElementById('loginBtn');
  btn.disabled=true; btn.textContent='⏳ Signing in…';
  try{
    const r=await fetch('/admin/login',{method:'POST',headers:{'Content-Type':'application/json'},
                        body:JSON.stringify({username:uid,password:pw})});
    const d=await r.json();
    if(r.ok){showMsg('✅ Success! Loading dashboard…','ok');setTimeout(()=>location.href='/admin/dashboard',800);}
    else showMsg(d.error||'Login failed','err');
  }catch(err){showMsg('Cannot reach server','err');}
  finally{btn.disabled=false;btn.textContent='🔐 Sign In';}
}
checkServer();
</script>
</body>
</html>"""

# ═══════════════════════════════════════════════════════════════
#  ADMIN DASHBOARD HTML
# ═══════════════════════════════════════════════════════════════
DASH_HTML = """<!DOCTYPE html>
<html lang="en" data-theme="dark">
<head>
<meta charset="UTF-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>RasoiExpress Admin Dashboard</title>
<script src="https://cdn.jsdelivr.net/npm/chart.js"></script>
<style>
:root{--bg:#0f172a;--card:#1e293b;--border:#334155;--text:#f1f5f9;--sub:#94a3b8;
      --blue:#3b82f6;--green:#22c55e;--red:#ef4444;--orange:#f97316;--yellow:#eab308;--r:14px}
[data-theme=light]{--bg:#f8fafc;--card:#fff;--border:#e2e8f0;--text:#0f172a;--sub:#64748b}
*{box-sizing:border-box;margin:0;padding:0}
body{font-family:'Segoe UI',sans-serif;background:var(--bg);color:var(--text);min-height:100vh}
.sidebar{position:fixed;left:0;top:0;width:230px;height:100vh;background:var(--card);
         border-right:1px solid var(--border);display:flex;flex-direction:column;z-index:100}
.slogo{padding:20px 18px;border-bottom:1px solid var(--border);display:flex;align-items:center;gap:10px}
.slogo h2{font-size:1rem;font-weight:800;color:var(--orange)}
.nav{display:flex;align-items:center;gap:10px;padding:11px 18px;cursor:pointer;border-radius:8px;
     margin:2px 8px;font-size:.85rem;font-weight:600;color:var(--sub);transition:all .2s;
     border:none;background:none;width:calc(100% - 16px);text-align:left}
.nav:hover,.nav.active{background:rgba(249,115,22,.1);color:var(--orange)}
.sfoot{margin-top:auto;padding:12px;border-top:1px solid var(--border)}
.main{margin-left:230px;padding:24px;min-height:100vh}
.topbar{display:flex;align-items:center;justify-content:space-between;margin-bottom:24px;
        background:var(--card);border:1px solid var(--border);border-radius:var(--r);padding:14px 20px}
.sec{display:none}.sec.active{display:block}
.sgrid{display:grid;grid-template-columns:repeat(auto-fit,minmax(190px,1fr));gap:16px;margin-bottom:24px}
.sc{background:var(--card);border:1px solid var(--border);border-radius:var(--r);padding:20px;position:relative;overflow:hidden}
.sc::before{content:'';position:absolute;top:0;left:0;right:0;height:3px;background:var(--c,var(--blue))}
.sv{font-size:2rem;font-weight:800}.sl{color:var(--sub);font-size:.75rem;margin-top:6px;font-weight:600;text-transform:uppercase}
.si{position:absolute;right:16px;top:50%;transform:translateY(-50%);font-size:2rem;opacity:.12}
.card{background:var(--card);border:1px solid var(--border);border-radius:var(--r);padding:20px}
.ch{display:flex;align-items:center;justify-content:space-between;margin-bottom:16px}
.ct{font-size:.95rem;font-weight:700}
table{width:100%;border-collapse:collapse;font-size:.82rem}
th{padding:10px 12px;text-align:left;font-size:.72rem;font-weight:700;text-transform:uppercase;
   letter-spacing:.5px;color:var(--sub);border-bottom:2px solid var(--border)}
td{padding:10px 12px;border-bottom:1px solid var(--border);vertical-align:middle}
tr:last-child td{border-bottom:none}
.badge{display:inline-flex;align-items:center;padding:3px 10px;border-radius:20px;font-size:.7rem;font-weight:700}
.b-green{background:rgba(34,197,94,.12);color:var(--green)}
.b-red{background:rgba(239,68,68,.12);color:var(--red)}
.b-blue{background:rgba(59,130,246,.12);color:var(--blue)}
.b-orange{background:rgba(249,115,22,.12);color:var(--orange)}
.b-yellow{background:rgba(234,179,8,.12);color:var(--yellow)}
.btn{padding:7px 14px;border-radius:8px;border:none;font-size:.78rem;font-weight:700;cursor:pointer;transition:all .2s;font-family:inherit}
.bp{background:var(--blue);color:#fff}.bp:hover{opacity:.85}
.bd{background:var(--red);color:#fff}.bd:hover{opacity:.85}
.bw{background:var(--orange);color:#fff}.bw:hover{opacity:.85}
.bs{padding:4px 10px;font-size:.72rem}
.btn:disabled{opacity:.5;cursor:not-allowed}
.srch{display:flex;gap:10px;margin-bottom:16px;flex-wrap:wrap}
.si2{flex:1;min-width:180px;background:var(--bg);border:1px solid var(--border);
     border-radius:8px;padding:9px 14px;color:var(--text);font-size:.85rem;outline:none;font-family:inherit}
.si2:focus{border-color:var(--blue)}
.mo{position:fixed;inset:0;background:rgba(0,0,0,.7);z-index:200;display:none;align-items:center;justify-content:center}
.mo.open{display:flex}
.md{background:var(--card);border:1px solid var(--border);border-radius:var(--r);
    padding:28px;width:90%;max-width:480px;max-height:85vh;overflow-y:auto}
.md h3{font-size:1rem;font-weight:800;margin-bottom:20px}
.fr{margin-bottom:14px}
.fr label{display:block;color:var(--sub);font-size:.75rem;font-weight:600;text-transform:uppercase;letter-spacing:.5px;margin-bottom:6px}
.fr input,.fr select,.fr textarea{width:100%;background:var(--bg);border:1px solid var(--border);
  border-radius:8px;padding:9px 12px;color:var(--text);font-size:.85rem;outline:none;font-family:inherit}
.fr input:focus,.fr select:focus,.fr textarea:focus{border-color:var(--blue)}
.fr textarea{resize:vertical;min-height:65px}
.mf{display:flex;gap:10px;justify-content:flex-end;margin-top:20px;padding-top:16px;border-top:1px solid var(--border)}
.toast{position:fixed;bottom:24px;right:24px;background:var(--card);border:1px solid var(--border);
       border-radius:var(--r);padding:14px 20px;font-size:.85rem;font-weight:600;
       box-shadow:0 4px 20px rgba(0,0,0,.3);z-index:300;transform:translateX(120%);transition:transform .3s}
.toast.show{transform:translateX(0)}
.toast.success{border-left:4px solid var(--green)}.toast.error{border-left:4px solid var(--red)}
.pw-w{position:relative}
.pw-w input{padding-right:40px}
.pw-e{position:absolute;right:10px;top:50%;transform:translateY(-50%);background:none;border:none;
      color:var(--sub);cursor:pointer;font-size:.95rem;padding:0;line-height:1}
.sw{width:36px;height:20px;border-radius:10px;background:var(--border);border:none;cursor:pointer;
    position:relative;transition:background .2s}
.sw::after{content:'';position:absolute;left:3px;top:3px;width:14px;height:14px;
           border-radius:50%;background:#fff;transition:transform .2s}
.sw.on{background:var(--green)}.sw.on::after{transform:translateX(16px)}
.lrow td{text-align:center;color:var(--sub);padding:32px}
.ibt{background:none;border:1px solid var(--border);border-radius:8px;color:var(--sub);
     cursor:pointer;padding:7px 10px;font-size:1rem;transition:all .2s}
.ibt:hover{border-color:var(--blue);color:var(--blue)}
.ar{background:rgba(34,197,94,.1);color:var(--green);font-size:.7rem;font-weight:700;
    padding:3px 8px;border-radius:20px;display:flex;align-items:center;gap:4px}
.dot{width:8px;height:8px;border-radius:50%}
.dot.ok{background:var(--green);box-shadow:0 0 6px var(--green)}
@keyframes lp{0%,100%{opacity:1}50%{opacity:.3}}
.dot.ok{animation:lp 2s infinite}
@media(max-width:768px){.sidebar{display:none}.main{margin-left:0}}
</style>
</head>
<body>
<nav class="sidebar">
  <div class="slogo"><span style="font-size:1.5rem">🍛</span><div><h2>RasoiExpress</h2><div style="font-size:.65rem;color:var(--sub)">Admin Panel</div></div></div>
  <div style="padding:10px 8px;flex:1;overflow-y:auto">
    <button class="nav active" onclick="tab('dash',this)">📊 Dashboard</button>
    <button class="nav" onclick="tab('users',this)">👥 Users</button>
    <button class="nav" onclick="tab('orders',this)">📦 Orders</button>
    <button class="nav" onclick="tab('menu',this)">🍽️ Menu</button>
    <button class="nav" onclick="tab('log',this)">📋 Activity Log</button>
  </div>
  <div class="sfoot">
    <div style="font-size:.72rem;color:var(--sub);margin-bottom:8px;padding:0 10px">Login: {{ login_time }}</div>
    <button class="nav" onclick="logout()" style="color:var(--red)">🚪 Logout</button>
  </div>
</nav>
<div class="main">
  <div class="topbar">
    <div><div style="font-size:1.1rem;font-weight:800" id="ptitle">📊 Dashboard</div><div style="font-size:.72rem;color:var(--sub)" id="psub">Overview</div></div>
    <div style="display:flex;gap:10px;align-items:center">
      <div class="ar"><div class="dot ok"></div>Live</div>
      <button class="ibt" onclick="toggleTheme()" id="thBtn">🌙</button>
      <button class="ibt" onclick="refreshCurrent()">🔄</button>
    </div>
  </div>

  <!-- DASHBOARD -->
  <div class="sec active" id="sec-dash">
    <div class="sgrid" id="statsGrid"><div class="sc" style="grid-column:1/-1;text-align:center;color:var(--sub)">⏳ Loading stats…</div></div>
    <div class="card"><div class="ch"><div class="ct">📋 Recent Activity</div><button class="btn bp bs" onclick="loadLog()">Refresh</button></div><div id="actFeed" style="color:var(--sub);font-size:.82rem">Loading…</div></div>
  </div>

  <!-- USERS -->
  <div class="sec" id="sec-users">
    <div class="card">
      <div class="ch"><div class="ct">👥 All Users</div><button class="btn bp bs" onclick="loadUsers()">🔄 Refresh</button></div>
      <div class="srch">
        <input class="si2" id="uSrch" placeholder="🔍 Search users…" oninput="filterUsers()">
        <select class="si2" id="uFilt" onchange="filterUsers()" style="max-width:150px">
          <option value="">All Status</option><option value="active">Active</option><option value="blocked">Blocked</option>
        </select>
      </div>
      <div style="overflow-x:auto"><table><thead><tr><th>ID</th><th>Name</th><th>Email</th><th>Phone</th><th>Status</th><th>Joined</th><th>Actions</th></tr></thead>
      <tbody id="uBody"><tr class="lrow"><td colspan="7">⏳ Loading…</td></tr></tbody></table></div>
    </div>
  </div>

  <!-- ORDERS -->
  <div class="sec" id="sec-orders">
    <div class="card">
      <div class="ch"><div class="ct">📦 All Orders</div><button class="btn bp bs" onclick="loadOrders()">🔄 Refresh</button></div>
      <div class="srch">
        <input class="si2" id="oSrch" placeholder="🔍 Search orders…" oninput="filterOrders()">
        <select class="si2" id="oFilt" onchange="filterOrders()" style="max-width:150px">
          <option value="">All Status</option>
          <option value="placed">Placed</option><option value="preparing">Preparing</option>
          <option value="on_the_way">On the Way</option><option value="delivered">Delivered</option>
        </select>
      </div>
      <div style="overflow-x:auto"><table><thead><tr><th>Order ID</th><th>User</th><th>Total</th><th>Status</th><th>Time</th><th>Action</th></tr></thead>
      <tbody id="oBody"><tr class="lrow"><td colspan="6">⏳ Loading…</td></tr></tbody></table></div>
    </div>
  </div>

  <!-- MENU -->
  <div class="sec" id="sec-menu">
    <div class="card">
      <div class="ch"><div class="ct">🍽️ Menu Items</div>
        <div style="display:flex;gap:8px">
          <button class="btn bp bs" onclick="openAdd()">➕ Add</button>
          <button class="btn bs" style="background:var(--border)" onclick="seedMenu()">🌱 Seed</button>
          <button class="btn bp bs" onclick="loadMenu()">🔄 Refresh</button>
        </div>
      </div>
      <div class="srch">
        <input class="si2" id="mSrch" placeholder="🔍 Search menu…" oninput="filterMenu()">
        <select class="si2" id="mCat" onchange="filterMenu()" style="max-width:170px">
          <option value="">All Categories</option>
          <option>Veg Curries</option><option>South Indian</option><option>Biryani &amp; Rice</option>
          <option>Street Food</option><option>Snacks</option><option>Breads</option>
          <option>Desserts</option><option>Drinks</option><option>Non-Veg Curries</option>
        </select>
      </div>
      <div style="overflow-x:auto"><table><thead><tr><th>ID</th><th>Name</th><th>Category</th><th>Price</th><th>Type</th><th>Actions</th></tr></thead>
      <tbody id="mBody"><tr class="lrow"><td colspan="6">⏳ Loading…</td></tr></tbody></table></div>
    </div>
  </div>

  <!-- ACTIVITY LOG -->
  <div class="sec" id="sec-log">
    <div class="card">
      <div class="ch"><div class="ct">📋 Activity Log</div>
        <div style="display:flex;gap:8px">
          <button class="btn bp bs" onclick="loadLog()">🔄 Refresh</button>
          <button class="btn bd bs" onclick="clearLog()">🗑️ Clear</button>
        </div>
      </div>
      <div style="overflow-x:auto"><table><thead><tr><th>Action</th><th>Details</th><th>IP</th><th>Time</th></tr></thead>
      <tbody id="lBody"><tr class="lrow"><td colspan="4">⏳ Loading…</td></tr></tbody></table></div>
    </div>
  </div>
</div>

<!-- Edit User Modal -->
<div class="mo" id="moUser">
  <div class="md">
    <h3>✏️ Edit User</h3>
    <input type="hidden" id="eUid">
    <div class="fr"><label>Name</label><input type="text" id="eUname"></div>
    <div class="fr"><label>Email</label><input type="email" id="eUemail"></div>
    <div class="fr"><label>Phone</label><input type="text" id="eUphone"></div>
    <div class="fr"><label>New Password (blank = keep same)</label>
      <div class="pw-w"><input type="password" id="eUpw" placeholder="Leave blank to keep"><button type="button" class="pw-e" onclick="tglPw('eUpw')">👁</button></div>
    </div>
    <div class="mf">
      <button class="btn bs" style="background:var(--border)" onclick="closeM('moUser')">Cancel</button>
      <button class="btn bp bs" onclick="saveUser()">💾 Save</button>
    </div>
  </div>
</div>

<!-- Edit Menu Modal -->
<div class="mo" id="moMenu">
  <div class="md">
    <h3 id="mTitle">✏️ Edit Item</h3>
    <input type="hidden" id="eMid">
    <div class="fr"><label>Name</label><input type="text" id="eMname"></div>
    <div class="fr"><label>Description</label><textarea id="eMdesc"></textarea></div>
    <div style="display:grid;grid-template-columns:1fr 1fr;gap:12px">
      <div class="fr"><label>Price ₹</label><input type="number" id="eMprice"></div>
      <div class="fr"><label>Rating</label><input type="number" step=".1" min="1" max="5" id="eMrating"></div>
    </div>
    <div style="display:grid;grid-template-columns:1fr 1fr;gap:12px">
      <div class="fr"><label>Category</label>
        <select id="eMcat"><option>Veg Curries</option><option>South Indian</option><option>Biryani &amp; Rice</option>
          <option>Street Food</option><option>Snacks</option><option>Breads</option>
          <option>Desserts</option><option>Drinks</option><option>Non-Veg Curries</option></select>
      </div>
      <div class="fr"><label>Type</label>
        <select id="eMtype"><option value="veg">Veg 🌿</option><option value="nonveg">Non-Veg 🍗</option></select>
      </div>
    </div>
    <div class="fr"><label>Restaurant</label><input type="text" id="eMrest"></div>
    <div class="fr"><label>Image URL</label><input type="text" id="eMimg"></div>
    <div style="display:grid;grid-template-columns:1fr 1fr;gap:12px">
      <div class="fr"><label>Emoji</label><input type="text" id="eMoji" maxlength="2"></div>
      <div class="fr"><label>Prep Time</label><input type="text" id="eMtime" placeholder="25 mins"></div>
    </div>
    <div style="display:flex;gap:16px;margin-top:8px;flex-wrap:wrap">
      <label style="display:flex;align-items:center;gap:6px;font-size:.8rem;color:var(--sub);cursor:pointer"><button type="button" class="sw" id="swBest" onclick="this.classList.toggle('on')"></button>⭐ Bestseller</label>
      <label style="display:flex;align-items:center;gap:6px;font-size:.8rem;color:var(--sub);cursor:pointer"><button type="button" class="sw" id="swNew" onclick="this.classList.toggle('on')"></button>✨ New</label>
      <label style="display:flex;align-items:center;gap:6px;font-size:.8rem;color:var(--sub);cursor:pointer"><button type="button" class="sw" id="swSpicy" onclick="this.classList.toggle('on')"></button>🌶️ Spicy</label>
    </div>
    <div class="mf">
      <button class="btn bs" style="background:var(--border)" onclick="closeM('moMenu')">Cancel</button>
      <button class="btn bp bs" onclick="saveMenu()">💾 Save</button>
    </div>
  </div>
</div>

<div class="toast" id="toast"></div>

<script>
const API = window.location.origin;
let allUsers=[], allOrders=[], allMenu=[], curTab='dash';

function $(id){return document.getElementById(id);}
function esc(s){return String(s||'').replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;');}
function fmt(s){try{return new Date(s).toLocaleString('en-IN',{day:'2-digit',month:'short',year:'numeric',hour:'2-digit',minute:'2-digit'});}catch{return s||'—';}}
function toast(m,t='success'){const el=$('toast');el.textContent=m;el.className='toast show '+t;setTimeout(()=>el.className='toast',3200);}
function tglPw(id){const i=$(id);i.type=i.type==='password'?'text':'password';}
function closeM(id){$(id).classList.remove('open');}
function openM(id){$(id).classList.add('open');}
document.addEventListener('click',e=>{if(e.target.classList.contains('mo'))e.target.classList.remove('open');});

function toggleTheme(){
  const h=document.documentElement,t=h.getAttribute('data-theme');
  h.setAttribute('data-theme',t==='dark'?'light':'dark');
  $('thBtn').textContent=t==='dark'?'☀️':'🌙';
}

function tab(name,btn){
  document.querySelectorAll('.sec').forEach(s=>s.classList.remove('active'));
  document.querySelectorAll('.nav').forEach(b=>b.classList.remove('active'));
  $('sec-'+name).classList.add('active');
  if(btn)btn.classList.add('active');
  curTab=name;
  const titles={dash:'📊 Dashboard',users:'👥 Users',orders:'📦 Orders',menu:'🍽️ Menu',log:'📋 Activity Log'};
  $('ptitle').textContent=titles[name]||name;
  if(name==='dash')loadStats();
  else if(name==='users')loadUsers();
  else if(name==='orders')loadOrders();
  else if(name==='menu')loadMenu();
  else if(name==='log')loadLog();
}

function refreshCurrent(){tab(curTab,document.querySelector('.nav.active'));}
setInterval(refreshCurrent, 30000);

async function af(path,opts={}){
  return fetch(API+path,{...opts,headers:{'Content-Type':'application/json',...(opts.headers||{})},credentials:'include'});
}

async function loadStats(){
  try{
    const r=await af('/api/admin/stats');const s=await r.json();
    $('statsGrid').innerHTML=`
      <div class="sc" style="--c:var(--blue)"><div class="sv">${s.users??0}</div><div class="sl">Total Users</div><div class="si">👥</div></div>
      <div class="sc" style="--c:var(--green)"><div class="sv">${s.orders??0}</div><div class="sl">Total Orders</div><div class="si">📦</div></div>
      <div class="sc" style="--c:var(--orange)"><div class="sv">₹${Number(s.revenue||0).toLocaleString('en-IN')}</div><div class="sl">Revenue</div><div class="si">💰</div></div>
      <div class="sc" style="--c:var(--yellow)"><div class="sv">${s.menu??0}</div><div class="sl">Menu Items</div><div class="si">🍽️</div></div>`;
    loadLog();
  }catch(e){$('statsGrid').innerHTML='<div class="sc" style="color:var(--red);grid-column:1/-1">❌ Failed to load stats</div>';}
}

async function loadUsers(){
  $('uBody').innerHTML='<tr class="lrow"><td colspan="7">⏳ Loading…</td></tr>';
  try{
    const r=await af('/api/admin/users');const d=await r.json();
    allUsers=d.users||[];renderUsers(allUsers);
  }catch{$('uBody').innerHTML='<tr class="lrow"><td colspan="7">❌ Error loading users</td></tr>';}
}
function renderUsers(users){
  if(!users.length){$('uBody').innerHTML='<tr class="lrow"><td colspan="7">No users found</td></tr>';return;}
  $('uBody').innerHTML=users.map(u=>`<tr>
    <td style="color:var(--sub)">#${u.id}</td>
    <td><strong>${esc(u.name)}</strong></td>
    <td style="color:var(--sub);font-size:.78rem">${esc(u.email)}</td>
    <td>${esc(u.phone||'—')}</td>
    <td>${u.is_blocked?'<span class="badge b-red">🔒 Blocked</span>':'<span class="badge b-green">✅ Active</span>'}</td>
    <td style="font-size:.75rem;color:var(--sub)">${fmt(u.created_at)}</td>
    <td style="display:flex;gap:4px;flex-wrap:wrap">
      <button class="btn bp bs" onclick="editUser(${u.id})">✏️</button>
      <button class="btn bw bs" onclick="blockUser(${u.id},${u.is_blocked})">${u.is_blocked?'🔓':'🔒'}</button>
      <button class="btn bd bs" onclick="delUser(${u.id})">🗑️</button>
    </td>
  </tr>`).join('');
}
function filterUsers(){
  const q=$('uSrch').value.toLowerCase(),f=$('uFilt').value;
  renderUsers(allUsers.filter(u=>{
    const m=!q||(u.name||'').toLowerCase().includes(q)||(u.email||'').toLowerCase().includes(q);
    const s=!f||(f==='blocked'?u.is_blocked:!u.is_blocked);
    return m&&s;
  }));
}
function editUser(id){
  const u=allUsers.find(x=>x.id===id);if(!u)return;
  $('eUid').value=id;$('eUname').value=u.name||'';$('eUemail').value=u.email||'';$('eUphone').value=u.phone||'';$('eUpw').value='';
  openM('moUser');
}
async function saveUser(){
  const id=$('eUid').value;
  const body={name:$('eUname').value,email:$('eUemail').value,phone:$('eUphone').value};
  const pw=$('eUpw').value;if(pw)body.password=pw;
  const r=await af(`/api/admin/users/${id}`,{method:'PUT',body:JSON.stringify(body)});
  if(r.ok){toast('✅ User updated');closeM('moUser');loadUsers();}else toast('❌ Update failed','error');
}
async function blockUser(id,blocked){
  if(!confirm(blocked?'Unblock this user?':'Block this user?'))return;
  const r=await af(`/api/admin/users/${id}/block`,{method:'POST',body:JSON.stringify({block:!blocked})});
  if(r.ok){toast(blocked?'🔓 Unblocked':'🔒 Blocked');loadUsers();}else toast('❌ Failed','error');
}
async function delUser(id){
  if(!confirm('Delete this user permanently?'))return;
  const r=await af(`/api/admin/users/${id}`,{method:'DELETE'});
  if(r.ok){toast('🗑️ Deleted');loadUsers();}else toast('❌ Failed','error');
}

async function loadOrders(){
  $('oBody').innerHTML='<tr class="lrow"><td colspan="6">⏳ Loading…</td></tr>';
  try{
    const r=await af('/api/admin/orders');const d=await r.json();
    allOrders=d.orders||[];renderOrders(allOrders);
  }catch{$('oBody').innerHTML='<tr class="lrow"><td colspan="6">❌ Error</td></tr>';}
}
const SB={placed:'b-blue',preparing:'b-orange',on_the_way:'b-yellow',nearby:'b-yellow',delivered:'b-green'};
function renderOrders(orders){
  if(!orders.length){$('oBody').innerHTML='<tr class="lrow"><td colspan="6">No orders found</td></tr>';return;}
  $('oBody').innerHTML=orders.map(o=>`<tr>
    <td style="font-family:monospace;font-size:.78rem;color:var(--blue)">${esc(o.id)}</td>
    <td>${esc(o.user_name||'#'+o.user_id)}</td>
    <td><strong>₹${Number(o.total).toLocaleString('en-IN')}</strong></td>
    <td><span class="badge ${SB[o.status]||'b-blue'}">${(o.status||'').replace('_',' ')}</span></td>
    <td style="font-size:.75rem;color:var(--sub)">${fmt(o.placed_at)}</td>
    <td>${o.current_step<4?`<button class="btn bp bs" onclick="advOrder('${o.id}')">▶ Advance</button>`:'<span class="badge b-green">Done</span>'}</td>
  </tr>`).join('');
}
function filterOrders(){
  const q=$('oSrch').value.toLowerCase(),s=$('oFilt').value;
  renderOrders(allOrders.filter(o=>{
    const m=!q||o.id.toLowerCase().includes(q)||(o.user_name||'').toLowerCase().includes(q);
    return m&&(!s||o.status===s);
  }));
}
async function advOrder(id){
  const r=await af(`/api/admin/orders/${id}/step`,{method:'PUT'});
  if(r.ok){toast('✅ Order advanced');loadOrders();}else toast('❌ Failed','error');
}

async function loadMenu(){
  $('mBody').innerHTML='<tr class="lrow"><td colspan="6">⏳ Loading…</td></tr>';
  try{
    const r=await af('/api/admin/menu');const d=await r.json();
    allMenu=d.items||[];renderMenu(allMenu);
  }catch{$('mBody').innerHTML='<tr class="lrow"><td colspan="6">❌ Error</td></tr>';}
}
function renderMenu(items){
  if(!items.length){$('mBody').innerHTML='<tr class="lrow"><td colspan="6">No items found</td></tr>';return;}
  $('mBody').innerHTML=items.map(m=>`<tr>
    <td style="color:var(--sub)">#${m.id}</td>
    <td><strong>${esc(m.name)}</strong><div style="font-size:.72rem;color:var(--sub)">${esc(m.restaurant||'')}</div></td>
    <td><span class="badge b-blue">${esc(m.category)}</span></td>
    <td><strong>₹${m.price}</strong></td>
    <td><span class="badge ${m.type==='veg'?'b-green':'b-orange'}">${m.type==='veg'?'🌿 Veg':'🍗 Non-Veg'}</span></td>
    <td style="display:flex;gap:4px">
      <button class="btn bp bs" onclick="editMenu(${m.id})">✏️</button>
      <button class="btn bd bs" onclick="delMenu(${m.id})">🗑️</button>
    </td>
  </tr>`).join('');
}
function filterMenu(){
  const q=$('mSrch').value.toLowerCase(),c=$('mCat').value;
  renderMenu(allMenu.filter(m=>(!q||(m.name||'').toLowerCase().includes(q))&&(!c||m.category===c)));
}
function openAdd(){
  $('mTitle').textContent='➕ Add Item';$('eMid').value='';
  ['eMname','eMdesc','eMrest','eMimg','eMoji','eMtime'].forEach(id=>$(id).value='');
  $('eMprice').value='';$('eMrating').value='4.0';$('eMcat').value='Veg Curries';$('eMtype').value='veg';$('eMoji').value='🍛';
  ['swBest','swNew','swSpicy'].forEach(id=>$(id).classList.remove('on'));
  openM('moMenu');
}
function editMenu(id){
  const m=allMenu.find(x=>x.id===id);if(!m)return;
  $('mTitle').textContent='✏️ Edit Item';$('eMid').value=id;
  $('eMname').value=m.name||'';$('eMdesc').value=m.description||'';$('eMprice').value=m.price||'';
  $('eMrating').value=m.rating||4.0;$('eMcat').value=m.category||'Veg Curries';$('eMtype').value=m.type||'veg';
  $('eMrest').value=m.restaurant||'';$('eMimg').value=m.image||'';$('eMoji').value=m.emoji||'🍛';$('eMtime').value=m.time||'30 mins';
  $('swBest').classList.toggle('on',!!m.is_best);$('swNew').classList.toggle('on',!!m.is_new);$('swSpicy').classList.toggle('on',!!m.is_spicy);
  openM('moMenu');
}
async function saveMenu(){
  const id=$('eMid').value;
  const body={name:$('eMname').value,description:$('eMdesc').value,price:parseFloat($('eMprice').value)||0,
    rating:parseFloat($('eMrating').value)||4.0,category:$('eMcat').value,type:$('eMtype').value,
    restaurant:$('eMrest').value,image:$('eMimg').value,emoji:$('eMoji').value,time:$('eMtime').value,
    is_best:$('swBest').classList.contains('on'),is_new:$('swNew').classList.contains('on'),is_spicy:$('swSpicy').classList.contains('on')};
  const r=await af(id?`/api/admin/menu/${id}`:'/api/admin/menu',{method:id?'PUT':'POST',body:JSON.stringify(body)});
  if(r.ok){toast(id?'✅ Updated':'✅ Added');closeM('moMenu');loadMenu();}else toast('❌ Save failed','error');
}
async function delMenu(id){
  if(!confirm('Delete this item?'))return;
  const r=await af(`/api/admin/menu/${id}`,{method:'DELETE'});
  if(r.ok){toast('🗑️ Deleted');loadMenu();}else toast('❌ Failed','error');
}
async function seedMenu(){
  if(!confirm('Seed menu with sample dishes?'))return;
  const r=await af('/api/menu/seed',{method:'POST'});
  if(r.ok){const d=await r.json();toast('🌱 '+d.message);loadMenu();}else toast('❌ Failed','error');
}

async function loadLog(){
  try{
    const r=await af('/api/admin/log');const d=await r.json();const logs=d.logs||[];
    const feed=$('actFeed');
    if(feed)feed.innerHTML=logs.slice(0,8).map(l=>`
      <div style="display:flex;gap:10px;padding:10px 0;border-bottom:1px solid var(--border)">
        <div style="width:8px;height:8px;border-radius:50%;background:var(--blue);margin-top:6px;flex-shrink:0"></div>
        <div style="flex:1;font-size:.82rem"><strong>${esc(l.action)}</strong> <span style="color:var(--sub)">${esc(l.details||'')}</span></div>
        <div style="font-size:.72rem;color:var(--sub);white-space:nowrap">${fmt(l.created_at)}</div>
      </div>`).join('')||'<div style="color:var(--sub);padding:12px;font-size:.82rem">No activity yet.</div>';
    const tb=$('lBody');
    if(tb){
      if(!logs.length){tb.innerHTML='<tr class="lrow"><td colspan="4">No logs yet</td></tr>';return;}
      tb.innerHTML=logs.map(l=>`<tr>
        <td><strong>${esc(l.action)}</strong></td>
        <td style="color:var(--sub)">${esc(l.details||'—')}</td>
        <td style="font-family:monospace;font-size:.75rem">${esc(l.ip||'—')}</td>
        <td style="color:var(--sub);font-size:.75rem">${fmt(l.created_at)}</td>
      </tr>`).join('');
    }
  }catch(e){console.warn('Log error',e);}
}
async function clearLog(){
  if(!confirm('Clear all activity logs?'))return;
  const r=await af('/api/admin/log',{method:'DELETE'});
  if(r.ok){toast('🗑️ Cleared');loadLog();}else toast('❌ Failed','error');
}
async function logout(){await af('/admin/logout');window.location='/admin';}

// Init
loadStats();
</script>
</body>
</html>"""

# ═══════════════════════════════════════════════════════════════
#  ADMIN ROUTES
# ═══════════════════════════════════════════════════════════════
@app.route("/admin")
def admin_page():
    if session.get(ADMIN_SESSION_KEY):
        return redirect("/admin/dashboard")
    ip = request.remote_addr or "unknown"
    data = login_attempts.get(ip, {})
    locked_until = data.get("locked_until")
    now = datetime.now(timezone.utc)
    if locked_until and now < locked_until:
        mins = int((locked_until - now).total_seconds() // 60) + 1
        return render_template_string(LOGIN_HTML, error=f"Too many attempts. Wait {mins} min(s).", username="")
    return render_template_string(LOGIN_HTML, error=None, username="")

@app.route("/admin/login", methods=["POST"])
def admin_login():
    d = request.get_json() or {}
    username = (d.get("username") or "").strip()
    password  = d.get("password", "")
    ip = request.remote_addr or "unknown"
    now = datetime.now(timezone.utc)
    data = login_attempts.setdefault(ip, {"count": 0, "locked_until": None})
    if data.get("locked_until") and now < data["locked_until"]:
        return jsonify({"error": "Too many attempts. Please wait."}), 429
    pw_hash = hashlib.sha256(password.encode()).hexdigest()
    if username == ADMIN_ID and pw_hash == ADMIN_PASS_HASH:
        data["count"] = 0
        data["locked_until"] = None
        session[ADMIN_SESSION_KEY] = True
        session["login_time"] = datetime.now().strftime("%d %b %Y, %I:%M %p")
        session.permanent = True
        log_action("Admin Login", f"IP:{ip}")
        return jsonify({"message": "OK"})
    data["count"] = data.get("count", 0) + 1
    if data["count"] >= MAX_LOGIN_ATTEMPTS:
        data["locked_until"] = now + timedelta(minutes=15)
        return jsonify({"error": "Locked for 15 minutes."}), 429
    return jsonify({"error": f"Wrong credentials. {MAX_LOGIN_ATTEMPTS - data['count']} tries left."}), 401

@app.route("/admin/dashboard")
@admin_page_required
def admin_dashboard():
    return render_template_string(DASH_HTML, login_time=session.get("login_time", "—"))

@app.route("/admin/logout")
def admin_logout():
    session.clear()
    return redirect("/admin")

# ═══════════════════════════════════════════════════════════════
#  API — HEALTH
# ═══════════════════════════════════════════════════════════════
@app.route("/api/health")
def health():
    return jsonify({"status": "ok", "db": "supabase_postgresql", "time": datetime.now().isoformat()})

# ═══════════════════════════════════════════════════════════════
#  API — ADMIN STATS
# ═══════════════════════════════════════════════════════════════
@app.route("/api/admin/stats")
@admin_required
def admin_stats():
    users   = (q1("SELECT COUNT(*) AS c FROM users") or {}).get("c", 0)
    orders  = (q1("SELECT COUNT(*) AS c FROM orders") or {}).get("c", 0)
    revenue = (q1("SELECT COALESCE(SUM(total),0) AS r FROM orders") or {}).get("r", 0)
    menu    = (q1("SELECT COUNT(*) AS c FROM menu_items") or {}).get("c", 0)
    return jsonify({"users": users, "orders": orders, "revenue": float(revenue or 0), "menu": menu})

# ═══════════════════════════════════════════════════════════════
#  API — ADMIN USERS
# ═══════════════════════════════════════════════════════════════
@app.route("/api/admin/users")
@admin_required
def admin_users():
    rows = qa("""SELECT u.id,u.name,u.email,u.phone,u.is_blocked,u.created_at,
                        COUNT(o.id) AS order_count
                 FROM users u LEFT JOIN orders o ON o.user_id=u.id
                 GROUP BY u.id,u.name,u.email,u.phone,u.is_blocked,u.created_at
                 ORDER BY u.id DESC""")
    return jsonify({"users": rows, "count": len(rows)})

@app.route("/api/admin/users/<int:uid>", methods=["PUT"])
@admin_required
def admin_upd_user(uid):
    d = request.get_json() or {}
    cur = q1("SELECT * FROM users WHERE id=:id", {"id": uid})
    if not cur: return jsonify({"error": "Not found"}), 404
    name  = (d.get("name")  or cur["name"]).strip()
    email = (d.get("email") or cur["email"]).strip().lower()
    phone = (d.get("phone") or cur.get("phone") or "").strip()
    pw    = d.get("password", "")
    if pw:
        run("UPDATE users SET name=:n,email=:e,phone=:p,password=:pw WHERE id=:id",
            {"n": name, "e": email, "p": phone, "pw": hash_pw(pw), "id": uid})
    else:
        run("UPDATE users SET name=:n,email=:e,phone=:p WHERE id=:id",
            {"n": name, "e": email, "p": phone, "id": uid})
    log_action("Admin Edit User", f"uid={uid}")
    return jsonify({"message": "Updated ✅"})

@app.route("/api/admin/users/<int:uid>/block", methods=["POST"])
@admin_required
def admin_block_user(uid):
    d = request.get_json() or {}
    block = bool(d.get("block", True))
    run("UPDATE users SET is_blocked=:b WHERE id=:id", {"b": block, "id": uid})
    log_action("Admin Block/Unblock", f"uid={uid} blocked={block}")
    return jsonify({"message": "Blocked" if block else "Unblocked"})

@app.route("/api/admin/users/<int:uid>", methods=["DELETE"])
@admin_required
def admin_del_user(uid):
    run("DELETE FROM orders WHERE user_id=:id", {"id": uid})
    run("DELETE FROM users WHERE id=:id", {"id": uid})
    log_action("Admin Delete User", f"uid={uid}")
    return jsonify({"message": "Deleted"})

# ═══════════════════════════════════════════════════════════════
#  API — ADMIN ORDERS
# ═══════════════════════════════════════════════════════════════
@app.route("/api/admin/orders")
@admin_required
def admin_orders():
    rows = qa("""SELECT o.*,u.name AS user_name FROM orders o
                 LEFT JOIN users u ON u.id=o.user_id
                 ORDER BY o.placed_at DESC LIMIT 500""")
    for r in rows:
        try: r["items"] = json.loads(r["items"])
        except: pass
    return jsonify({"orders": rows, "count": len(rows)})

@app.route("/api/admin/orders/<oid>/step", methods=["PUT"])
@admin_required
def admin_order_step(oid):
    SM = {0:"placed",1:"preparing",2:"on_the_way",3:"nearby",4:"delivered"}
    o = q1("SELECT current_step FROM orders WHERE id=:id", {"id": oid})
    if not o: return jsonify({"error": "Not found"}), 404
    ns = min((o["current_step"] or 0) + 1, 4)
    run("UPDATE orders SET current_step=:s,status=:st WHERE id=:id", {"s": ns, "st": SM[ns], "id": oid})
    return jsonify({"message": SM[ns]})

# ═══════════════════════════════════════════════════════════════
#  API — ADMIN MENU
# ═══════════════════════════════════════════════════════════════
@app.route("/api/admin/menu")
@admin_required
def admin_menu():
    items = qa("SELECT * FROM menu_items ORDER BY id DESC")
    return jsonify({"items": items, "count": len(items)})

@app.route("/api/admin/menu", methods=["POST"])
@admin_required
def admin_add_menu():
    d = request.get_json() or {}
    new_id = run(
        "INSERT INTO menu_items(name,description,price,category,type,restaurant,rating,image,emoji,is_spicy,is_new,is_best,time) "
        "VALUES(:n,:desc,:price,:cat,:tp,:rest,:rat,:img,:em,:sp,:nw,:bs,:tm) RETURNING id",
        {"n":d.get("name",""),"desc":d.get("description",""),"price":float(d.get("price",0)),
         "cat":d.get("category",""),"tp":d.get("type","veg"),"rest":d.get("restaurant",""),
         "rat":float(d.get("rating",4.0)),"img":d.get("image",""),"em":d.get("emoji","🍛"),
         "sp":bool(d.get("is_spicy")),"nw":bool(d.get("is_new")),"bs":bool(d.get("is_best")),
         "tm":d.get("time","30 mins")})
    log_action("Admin Add Menu", d.get("name",""))
    return jsonify({"message": "Added ✅", "id": new_id}), 201

@app.route("/api/admin/menu/<int:mid>", methods=["PUT"])
@admin_required
def admin_upd_menu(mid):
    d = request.get_json() or {}
    cur = q1("SELECT * FROM menu_items WHERE id=:id", {"id": mid})
    if not cur: return jsonify({"error": "Not found"}), 404
    run("""UPDATE menu_items SET name=:n,description=:desc,price=:price,category=:cat,type=:tp,
           restaurant=:rest,rating=:rat,image=:img,emoji=:em,is_spicy=:sp,is_new=:nw,is_best=:bs,time=:tm
           WHERE id=:id""",
        {"n":d.get("name",cur["name"]),"desc":d.get("description",cur["description"]),
         "price":float(d.get("price",cur["price"])),"cat":d.get("category",cur["category"]),
         "tp":d.get("type",cur["type"]),"rest":d.get("restaurant",cur["restaurant"]),
         "rat":float(d.get("rating",cur["rating"])),"img":d.get("image",cur["image"]),
         "em":d.get("emoji",cur["emoji"]),"sp":bool(d.get("is_spicy",cur["is_spicy"])),
         "nw":bool(d.get("is_new",cur["is_new"])),"bs":bool(d.get("is_best",cur["is_best"])),
         "tm":d.get("time",cur["time"]),"id":mid})
    log_action("Admin Edit Menu", f"mid={mid}")
    return jsonify({"message": "Updated ✅"})

@app.route("/api/admin/menu/<int:mid>", methods=["DELETE"])
@admin_required
def admin_del_menu(mid):
    run("DELETE FROM menu_items WHERE id=:id", {"id": mid})
    log_action("Admin Delete Menu", f"mid={mid}")
    return jsonify({"message": "Deleted"})

# ═══════════════════════════════════════════════════════════════
#  API — ACTIVITY LOG
# ═══════════════════════════════════════════════════════════════
@app.route("/api/admin/log")
@admin_required
def admin_log():
    logs = qa("SELECT * FROM activity_log ORDER BY id DESC LIMIT 200")
    return jsonify({"logs": logs, "count": len(logs)})

@app.route("/api/admin/log", methods=["DELETE"])
@admin_required
def admin_clear_log():
    run("DELETE FROM activity_log")
    return jsonify({"message": "Cleared"})

# ═══════════════════════════════════════════════════════════════
#  API — AUTH
# ═══════════════════════════════════════════════════════════════
@app.route("/api/auth/signup", methods=["POST"])
def signup():
    d     = request.get_json() or {}
    name  = (d.get("name")     or "").strip()
    email = (d.get("email")    or "").strip().lower()
    pw    = (d.get("password") or "")
    if not name:         return jsonify({"error": "Name required"}), 400
    if "@" not in email: return jsonify({"error": "Valid email required"}), 400
    if len(pw) < 6:      return jsonify({"error": "Password 6+ chars"}), 400
    if q1("SELECT id FROM users WHERE email=:e", {"e": email}):
        return jsonify({"error": "Email already registered"}), 400
    uid = run("INSERT INTO users(name,email,password) VALUES(:n,:e,:p) RETURNING id",
              {"n": name, "e": email, "p": hash_pw(pw)})
    log_action("User Signup", email)
    return jsonify({"message": f"Welcome, {name.split()[0]}! 🎉",
                    "token": make_token(uid, email),
                    "user": {"id": uid, "name": name, "email": email,
                             "picture": "", "profile_color": "#1A6FB3", "phone": "", "address": ""}}), 201

@app.route("/api/auth/login", methods=["POST"])
def user_login():
    d     = request.get_json() or {}
    email = (d.get("email")    or "").strip().lower()
    pw    = (d.get("password") or "")
    if not email or not pw: return jsonify({"error": "Email and password required"}), 400
    user = q1("SELECT * FROM users WHERE email=:e", {"e": email})
    if not user or not check_pw(pw, user["password"]):
        return jsonify({"error": "Invalid email or password"}), 401
    if user.get("is_blocked"):
        return jsonify({"error": "Account blocked. Contact support."}), 403
    log_action("User Login", email)
    return jsonify({"message": f"Welcome back, {user['name'].split()[0]}! 🎉",
                    "token": make_token(user["id"], user["email"]),
                    "user": {"id": user["id"], "name": user["name"], "email": user["email"],
                             "picture": user.get("picture") or "",
                             "profile_color": user.get("profile_color") or "#1A6FB3",
                             "phone": user.get("phone") or "",
                             "address": user.get("address") or ""}})

@app.route("/api/auth/me")
@jwt_required
def me(cu):
    user = q1("SELECT id,name,email,phone,address,picture,profile_color FROM users WHERE id=:id AND is_blocked=FALSE",
              {"id": cu["user_id"]})
    if not user: return jsonify({"error": "Not found or blocked"}), 404
    cnt = q1("SELECT COUNT(*) AS c FROM orders WHERE user_id=:id", {"id": cu["user_id"]})
    user["total_orders"] = (cnt or {}).get("c", 0)
    return jsonify({"user": user})

@app.route("/api/auth/logout", methods=["POST"])
def user_logout(): return jsonify({"message": "Logged out"})

# ═══════════════════════════════════════════════════════════════
#  API — MENU
# ═══════════════════════════════════════════════════════════════
@app.route("/api/menu/items")
def menu_items():
    cat   = request.args.get("category", "")
    dt    = request.args.get("type", "")
    srch  = request.args.get("search", "").lower()
    srt   = request.args.get("sort", "popular")
    page  = max(1, request.args.get("page", 1, type=int))
    limit = min(100, max(10, request.args.get("limit", 50, type=int)))

    where  = "available=TRUE"
    params = {}
    if cat and cat.lower() not in ("all", ""):
        where += " AND category=:cat"; params["cat"] = cat
    if dt in ("veg", "nonveg"):
        where += " AND type=:dt"; params["dt"] = dt
    if srch:
        where += " AND (LOWER(name) LIKE :srch OR LOWER(description) LIKE :srch)"
        params["srch"] = f"%{srch}%"

    order = {"popular":"is_best DESC,rating DESC","price-asc":"price ASC",
             "price-desc":"price DESC","rating":"rating DESC","newest":"id DESC"}.get(srt,"is_best DESC,rating DESC")

    total = (q1(f"SELECT COUNT(*) AS c FROM menu_items WHERE {where}", params) or {}).get("c", 0)
    params["lim"] = limit
    params["off"] = (page - 1) * limit
    items = qa(f"SELECT * FROM menu_items WHERE {where} ORDER BY {order} LIMIT :lim OFFSET :off", params)

    return jsonify({"items": items, "count": len(items), "total": total,
                    "page": page, "total_pages": (total + limit - 1) // limit,
                    "has_next": page * limit < total, "has_prev": page > 1})

@app.route("/api/menu/seed", methods=["POST"])
def seed_menu():
    ex = (q1("SELECT COUNT(*) AS c FROM menu_items") or {}).get("c", 0)
    if ex > 0:
        return jsonify({"message": f"Already seeded with {ex} dishes."})
    for d in SAMPLE_DISHES:
        try:
            run("INSERT INTO menu_items(name,description,price,category,type,restaurant,rating,image,emoji,is_spicy,is_new,is_best,time) "
                "VALUES(:n,:desc,:price,:cat,:tp,:rest,:rat,:img,:em,:sp,:nw,:bs,:tm)",
                {"n":d[0],"desc":d[1],"price":d[2],"cat":d[3],"tp":d[4],"rest":d[5],
                 "rat":d[6],"img":d[7],"em":d[8],"sp":d[9],"nw":d[10],"bs":d[11],"tm":d[12]})
        except Exception:
            pass
    c = (q1("SELECT COUNT(*) AS c FROM menu_items") or {}).get("c", 0)
    return jsonify({"message": f"✅ Menu seeded with {c} dishes!"}), 201

# ═══════════════════════════════════════════════════════════════
#  API — ORDERS
# ═══════════════════════════════════════════════════════════════
SM = {0:"placed",1:"preparing",2:"on_the_way",3:"nearby",4:"delivered"}

@app.route("/api/orders/place", methods=["POST"])
@jwt_required
def place_order(cu):
    d     = request.get_json() or {}
    items = d.get("items", [])
    addr  = (d.get("address") or "").strip()
    if not items: return jsonify({"error": "Cart empty"}), 400
    if not addr:  return jsonify({"error": "Address required"}), 400
    sub  = sum(i.get("price", 0) * i.get("qty", 1) for i in items)
    dl   = 0 if sub >= 500 else 49
    tax  = round(sub * .05)
    tot  = sub + dl + tax
    oid  = f"RE-{datetime.now().year}-{''.join(random.choices(string.ascii_uppercase+string.digits,k=8))}"
    rest = items[0].get("restaurant", "") if items else ""
    run("INSERT INTO orders(id,user_id,items,total,restaurant,address,status,current_step) VALUES(:id,:uid,:it,:tot,:rest,:addr,'placed',0)",
        {"id":oid,"uid":cu["user_id"],"it":json.dumps(items),"tot":tot,"rest":rest,"addr":addr})
    now = datetime.now()
    log_action("Order Placed", f"oid={oid}")
    return jsonify({"message": f"Order {oid} placed! 🎉",
                    "order": {"id": oid, "status": "placed", "current_step": 0, "eta": "30 mins",
                              "items": [i.get("name","") for i in items], "restaurant": rest,
                              "time": now.strftime("%I:%M %p"), "total": tot, "subtotal": sub,
                              "delivery": dl, "taxes": tax, "address": addr,
                              "placed_at": now.isoformat()}}), 201

@app.route("/api/orders/my-orders")
@jwt_required
def my_orders(cu):
    rows = qa("SELECT * FROM orders WHERE user_id=:id ORDER BY placed_at DESC", {"id": cu["user_id"]})
    for r in rows:
        try: r["items"] = json.loads(r["items"])
        except: r["items"] = []
    return jsonify({"orders": rows, "count": len(rows)})

@app.route("/api/orders/<oid>")
@jwt_required
def get_order(oid, cu):
    o = q1("SELECT * FROM orders WHERE id=:id AND user_id=:uid", {"id": oid, "uid": cu["user_id"]})
    if not o: return jsonify({"error": "Not found"}), 404
    try: o["items"] = json.loads(o["items"])
    except: o["items"] = []
    return jsonify({"order": o})

@app.route("/api/orders/<oid>/step", methods=["PUT"])
@jwt_required
def step(oid, cu):
    o = q1("SELECT * FROM orders WHERE id=:id AND user_id=:uid", {"id": oid, "uid": cu["user_id"]})
    if not o: return jsonify({"error": "Not found"}), 404
    ns = min((o["current_step"] or 0) + 1, 4)
    run("UPDATE orders SET current_step=:s,status=:st WHERE id=:id", {"s": ns, "st": SM[ns], "id": oid})
    return jsonify({"message": SM[ns].replace("_"," ").title(), "current_step": ns, "status": SM[ns]})

# ═══════════════════════════════════════════════════════════════
#  API — PROFILE
# ═══════════════════════════════════════════════════════════════
@app.route("/api/profile")
@jwt_required
def get_profile(cu):
    u = q1("SELECT id,name,email,phone,address,picture,profile_color FROM users WHERE id=:id", {"id": cu["user_id"]})
    if not u: return jsonify({"error": "Not found"}), 404
    s = q1("SELECT COUNT(*) AS t, COALESCE(SUM(total),0) AS sp FROM orders WHERE user_id=:id", {"id": cu["user_id"]})
    u["total_orders"] = (s or {}).get("t", 0)
    u["total_spent"]  = (s or {}).get("sp", 0)
    return jsonify({"user": u})

@app.route("/api/profile", methods=["PUT"])
@jwt_required
def upd_profile(cu):
    d   = request.get_json() or {}
    cur = q1("SELECT * FROM users WHERE id=:id", {"id": cu["user_id"]})
    if not cur: return jsonify({"error": "Not found"}), 404
    name  = (d.get("name")          or cur["name"]).strip()
    phone = (d.get("phone")         or cur.get("phone") or "").strip()
    addr  = (d.get("address")       or cur.get("address") or "").strip()
    pic   = (d.get("picture")       or cur.get("picture") or "")
    color = (d.get("profile_color") or cur.get("profile_color") or "#1A6FB3")
    run("UPDATE users SET name=:n,phone=:p,address=:a,picture=:pic,profile_color=:c WHERE id=:id",
        {"n":name,"p":phone,"a":addr,"pic":pic,"c":color,"id":cu["user_id"]})
    u = q1("SELECT id,name,email,phone,address,picture,profile_color FROM users WHERE id=:id", {"id": cu["user_id"]})
    return jsonify({"message": "Updated ✅", "user": u})

@app.route("/api/profile/password", methods=["PUT"])
@jwt_required
def chg_pw(cu):
    d  = request.get_json() or {}
    op = d.get("current_password", "")
    np = d.get("new_password", "")
    if not op or not np: return jsonify({"error": "Both required"}), 400
    if len(np) < 6:      return jsonify({"error": "New password 6+ chars"}), 400
    u = q1("SELECT password FROM users WHERE id=:id", {"id": cu["user_id"]})
    if not u or not check_pw(op, u["password"]):
        return jsonify({"error": "Current password incorrect"}), 401
    run("UPDATE users SET password=:p WHERE id=:id", {"p": hash_pw(np), "id": cu["user_id"]})
    return jsonify({"message": "Password changed 🔒"})

# ═══════════════════════════════════════════════════════════════
#  STARTUP
# ═══════════════════════════════════════════════════════════════
if __name__ == "__main__":
    if DATABASE_URL:
        init_db()
    else:
        print("⚠️  DATABASE_URL not set!")
    PORT = int(os.environ.get("PORT", 5000))
    print(f"\n🍛  RasoiExpress running on port {PORT}")
    print(f"📡  API: http://localhost:{PORT}/api/health")
    print(f"🔐  Admin: http://localhost:{PORT}/admin\n")
    app.run(host="0.0.0.0", port=PORT, debug=False)
