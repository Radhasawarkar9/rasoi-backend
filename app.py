"""
RasoiExpress — Admin Panel (Ultimate Edition)
=================================================
Run:   python app.py
Admin: http://localhost:5000/admin

NEW in v3:
  🎨  Better Login Page Design
  📊  Bigger & Better Charts (Chart.js)
  📱  Mobile Friendly Layout
  🌙  Dark / Light Theme Toggle
  ⚡  Auto Refresh Dashboard
  🔍  Advanced Search & Filters
  📋  Activity Log
  🔔  Real-time Notifications Bell
  ⏰  Session Timer Countdown
  🖥️  Full Screen Mode
  📤  Export PDF Report (print-ready)
  🛡️  Wrong Login Attempt Counter (blocks after 5)
"""

import os, sys, json, hashlib, hmac, re, random, string, functools
import psycopg2
import psycopg2.extras
from datetime import datetime, timedelta, timezone
from flask import Flask, request, jsonify, g, session, render_template_string, redirect

try:
    import jwt
except ImportError:
    print("❌  Run:  pip install Flask PyJWT"); sys.exit(1)

# ═══════════════════════════════════════════════════════════════
#  CONFIG
# ═══════════════════════════════════════════════════════════════
SECRET_KEY        = os.environ.get("SECRET_KEY", "rasoi-express-jwt-secret-2024")
SESSION_SECRET    = os.environ.get("SESSION_SECRET", "rasoi-admin-session-secret-2024")
JWT_EXPIRY_DAYS   = 7
PBKDF2_ITERS      = 260_000
SUPABASE_DB_URL   = os.environ.get("SUPABASE_DB_URL", "")
ADMIN_ID          = "admin123"
_admin_pw         = os.environ.get("ADMIN_PASSWORD", "secure@123")
ADMIN_PASS_HASH   = hashlib.sha256(_admin_pw.encode()).hexdigest()
ADMIN_SESSION_KEY = "admin_ok"
MAX_LOGIN_ATTEMPTS = 5   # lock after this many wrong tries


def _to_pg(sql: str) -> str:
    """Convert SQLite ? placeholders to psycopg2 %s style."""
    return re.sub(r'\?', '%s', sql)

# In-memory attempt tracker  {ip: {count, locked_until}}
login_attempts = {}

# ═══════════════════════════════════════════════════════════════
#  DATABASE SCHEMA
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
        is_blocked    INTEGER DEFAULT 0,
        created_at    TIMESTAMP DEFAULT NOW()
    )""",
    """CREATE TABLE IF NOT EXISTS menu_items (
        id          SERIAL PRIMARY KEY,
        name        TEXT    NOT NULL,
        description TEXT    DEFAULT '',
        price       FLOAT   NOT NULL,
        category    TEXT    NOT NULL,
        type        TEXT    DEFAULT 'veg',
        restaurant  TEXT    DEFAULT '',
        rating      FLOAT   DEFAULT 4.0,
        image       TEXT    DEFAULT '',
        emoji       TEXT    DEFAULT '🍛',
        is_spicy    INTEGER DEFAULT 0,
        is_new      INTEGER DEFAULT 0,
        is_best     INTEGER DEFAULT 0,
        time        TEXT    DEFAULT '30 mins',
        available   INTEGER DEFAULT 1
    )""",
    """CREATE TABLE IF NOT EXISTS orders (
        id           TEXT    PRIMARY KEY,
        user_id      INTEGER NOT NULL,
        items        TEXT    NOT NULL,
        total        FLOAT   NOT NULL,
        restaurant   TEXT    DEFAULT '',
        address      TEXT    DEFAULT '',
        status       TEXT    DEFAULT 'placed',
        current_step INTEGER DEFAULT 0,
        placed_at    TIMESTAMP DEFAULT NOW(),
        FOREIGN KEY(user_id) REFERENCES users(id)
    )""",
    """CREATE TABLE IF NOT EXISTS activity_log (
        id         SERIAL PRIMARY KEY,
        action     TEXT    NOT NULL,
        details    TEXT    DEFAULT '',
        ip         TEXT    DEFAULT '',
        created_at TIMESTAMP DEFAULT NOW()
    )""",
]

SAMPLE_DISHES = [

    # ── Veg Curries (15) ──
    ('Paneer Butter Masala','Silky-smooth paneer cubes simmered in a rich, buttery tomato-cashew gravy.',260,'Veg Curries','veg','Shree Bhavan',4.8,'https://www.indianhealthyrecipes.com/wp-content/uploads/2021/07/paneer-butter-masala.webp','🧀',0,0,1,'25 mins'),
    ('Dal Makhani','Slow-cooked black lentils in velvety butter and cream — a Delhi legend.',190,'Veg Curries','veg','Maa Ki Rasoi',4.9,'https://myfoodstory.com/wp-content/uploads/2018/08/Dal-Makhani-New-3.jpg','🫘',0,0,1,'20 mins'),
    ('Palak Paneer','Fresh spinach purée with soft paneer cubes, tempered with garlic and cream.',230,'Veg Curries','veg','Shree Bhavan',4.6,'https://www.indianveggiedelight.com/wp-content/uploads/2017/10/palak-paneer-recipe-featured.jpg','🌿',0,0,0,'25 mins'),
    ('Rajma Masala','Red kidney beans slow-cooked in a tangy, aromatic onion-tomato masala.',180,'Veg Curries','veg','Maa Ki Rasoi',4.7,'https://static.vecteezy.com/system/resources/previews/016/287/033/non_2x/palak-rajma-masala-is-an-indian-curry-prepared-with-red-kidney-beans-and-spinach-cooked-with-spices-free-photo.jpg','🫘',1,0,1,'20 mins'),
    ('Aloo Gobi','Dry-spiced potatoes and cauliflower with turmeric, cumin and coriander.',160,'Veg Curries','veg','Desi Tadka',4.5,'https://static01.nyt.com/images/2023/12/21/multimedia/ND-Aloo-Gobi-gkwc/ND-Aloo-Gobi-gkwc-videoSixteenByNineJumbo1600.jpg','🥔',1,0,0,'20 mins'),
    ('Matar Paneer','Green peas and paneer in a fragrant, mildly spiced tomato gravy.',240,'Veg Curries','veg','Shree Bhavan',4.6,'https://www.indianveggiedelight.com/wp-content/uploads/2019/12/matar-paneer-instant-pot-featured.jpg','🫛',0,0,0,'22 mins'),
    ('Chana Masala','Hearty chickpeas stewed in a bold, tangy sauce of onion, tomato and spices.',170,'Veg Curries','veg','Chaat Corner',4.8,'https://encrypted-tbn0.gstatic.com/images?q=tbn:ANd9GcQmtyKzYZir0Tz85yb6Flife9PoIDBw35LHkg&s','🫘',1,0,1,'18 mins'),
    ('Bhindi Masala','Crispy okra tossed with caramelised onions, tomatoes and Indian spices.',155,'Veg Curries','veg','Desi Tadka',4.4,'https://myfoodstory.com/wp-content/uploads/2025/03/Bhindi-Masala-2.jpg','🥦',0,0,0,'18 mins'),
    ('Kadai Paneer','Paneer and capsicum cooked in a wok with freshly ground kadai masala.',270,'Veg Curries','veg','Shree Bhavan',4.7,'https://www.cubesnjuliennes.com/wp-content/uploads/2020/03/Best-Kadai-Paneer-Recipe.jpg','🧀',1,1,0,'28 mins'),
    ('Shahi Paneer','Royal paneer dish cooked in a cream-nut gravy with saffron and cardamom.',290,'Veg Curries','veg','Mughal Darbar',4.7,'https://www.sanjanafeasts.co.uk/wp-content/uploads/2020/01/Restaurant-Style-Shahi-Paneer-735x1103.jpg','🧀',0,0,0,'26 mins'),
    ('Mix Veg Curry','Seasonal mixed vegetables in a lightly spiced coconut-tomato gravy.',165,'Veg Curries','veg','Desi Tadka',4.3,'https://shwetainthekitchen.com/wp-content/uploads/2023/03/mixed-vegetable-curry.jpg','🥕',0,0,0,'20 mins'),
    ('Navratan Korma','Nine-jewel curry with vegetables, paneer and fruits in a mild, sweet gravy.',275,'Veg Curries','veg','Mughal Darbar',4.5,'https://www.jcookingodyssey.com/wp-content/uploads/2025/02/navratan-korma.jpg','🌸',0,0,0,'30 mins'),
    ('Saag Aloo','Mustard greens with potatoes, tempered with garlic and Punjabi spices.',155,'Veg Curries','veg','Maa Ki Rasoi',4.4,'https://rainbowplantlife.com/wp-content/uploads/2024/01/Hero-2-scaled.jpg','🥬',1,0,0,'22 mins'),
    ('Aloo Matar','Simple, comforting potato and peas curry in a light tomato-onion base.',150,'Veg Curries','veg','Desi Tadka',4.3,'https://encrypted-tbn0.gstatic.com/images?q=tbn:ANd9GcT6e7RqeHiz3tAwbOD4SDvmc190waysfoGOgw&s','🥔',0,0,0,'18 mins'),
    ('Methi Malai Paneer','Paneer in a fenugreek-cream gravy with a unique bittersweet flavour profile.',255,'Veg Curries','veg','Shree Bhavan',4.6,'https://d1mxd7n691o8sz.cloudfront.net/static/recipe/recipe/2023-12/Methi-Malai-Paneer-2-3-1f89f6ead16c4b538280f8ca57d75be9_thumbnail_1702631.jpeg','🌿',0,1,0,'24 mins'),
    
    # ── South Indian (15) ──
    ('Masala Dosa','Crispy rice-lentil crepe stuffed with spiced potato filling, served with sambar.',140,'South Indian','veg','South Spice',4.8,'https://www.cookwithmanali.com/wp-content/uploads/2020/05/Masala-Dosa-500x500.jpg','🥞',0,0,1,'18 mins'),
    ('Idli Sambar','Fluffy steamed rice cakes with tangy sambar and two fresh chutneys.',100,'South Indian','veg','South Spice',4.5,'https://encrypted-tbn0.gstatic.com/images?q=tbn:ANd9GcS3aJyP7SxhdvtHtorSod6skM3K2BTE3N_Ouw&s','🫕',0,0,0,'15 mins'),
    ('Medu Vada','Crispy lentil doughnuts with a fluffy interior, served with sambar and coconut chutney.',90,'South Indian','veg','South Spice',4.5,'https://bonmasala.com/wp-content/uploads/2022/12/medu-vada-recipe-500x500.webp','🍩',0,0,0,'15 mins'),
    ('Uttapam','Thick rice pancake topped with onions, tomatoes and green chillies. Served with sambar.',120,'South Indian','veg','South Spice',4.4,'https://encrypted-tbn0.gstatic.com/images?q=tbn:ANd9GcRuiAx67pyaTYtBtBT1qtf7OM30AZg5ngMnaw&s','🥞',0,0,0,'18 mins'),
    ('Pongal','Comforting rice and moong dal cooked with black pepper, cumin and ghee.',110,'South Indian','veg','South Spice',4.4,'https://encrypted-tbn0.gstatic.com/images?q=tbn:ANd9GcQonLqWxFc3-G-HKlsDDhNcvXvIn_XkxYbJ_A&s','🍲',0,0,0,'20 mins'),
    ('Rava Dosa','Paper-thin, lacy semolina crepe — extra crispy with curry leaves and cashews.',130,'South Indian','veg','Udupi Palace',4.7,'https://encrypted-tbn0.gstatic.com/images?q=tbn:ANd9GcQbNs_k00kLfeTMdEf2QXEcLI61RKma4zrghg&s','🥞',0,0,1,'20 mins'),
    ('Chettinad Chicken Curry','Fiery Tamil Nadu curry with freshly ground Chettinad spices — bold and aromatic.',310,'South Indian','nonveg','Chettinad House',4.8,'https://encrypted-tbn0.gstatic.com/images?q=tbn:ANd9GcSSdYkqM5GJLHSlYcwoKA8KiT8ndmgJcamf5A&s','🍗',1,0,1,'35 mins'),
    ('Pesarattu','Green moong dal crepe from Andhra, served with upma stuffing and ginger chutney.',115,'South Indian','veg','South Spice',4.3,'https://i0.wp.com/www.chitrasfoodbook.com/wp-content/uploads/2022/07/pesarattu-allam-pachadi-1.jpg?resize=500%2C533&ssl=1','🥞',0,1,0,'18 mins'),
    ('Appam with Stew','Lacy rice hoppers with a fluffy centre, paired with mild Kerala vegetable stew.',160,'South Indian','veg','Kerala Kitchen',4.6,'https://www.shutterstock.com/image-photo/appam-vegetable-stew-one-famous-600nw-2203037921.jpg','🫕',0,0,0,'22 mins'),
    ('Bisi Bele Bath','Karnataka one-pot dish of rice, lentils and vegetables with tamarind and spice powder.',145,'South Indian','veg','Karnataka Bhavan',4.5,'https://encrypted-tbn0.gstatic.com/images?q=tbn:ANd9GcROUGcJZ_e59MH3ug74bRTqIEuvsKuWn2djfQ&s','🍲',1,0,0,'25 mins'),
    ('Rasam','Thin, peppery tamarind soup with cumin and coriander — a South Indian comfort staple.',75,'South Indian','veg','South Spice',4.5,'https://i0.wp.com/www.chitrasfoodbook.com/wp-content/uploads/2014/12/rasam.jpg?w=1200&ssl=1','🫕',1,0,0,'12 mins'),
    ('Curd Rice','Cooling rice mixed with creamy curd, tempered with mustard seeds and curry leaves.',90,'South Indian','veg','Udupi Palace',4.4,'https://encrypted-tbn0.gstatic.com/images?q=tbn:ANd9GcSbJwtOJEBhlrD5K-0k_deIgMQpsmlT-MoG4Q&s','🍚',0,0,0,'10 mins'),
    ('Kerala Parotta','Layered, flaky flatbread from Kerala — best with egg curry or vegetable kurma.',85,'South Indian','veg','Kerala Kitchen',4.6,'https://encrypted-tbn0.gstatic.com/images?q=tbn:ANd9GcTvYkUrZWQj392J5pVKrR7RGH0ZbWwxDgVllw&s','🫓',0,0,0,'18 mins'),
    ('Prawn Kerala Curry','Succulent prawns slow-cooked in a thick coconut milk curry with raw mango.',380,'South Indian','nonveg','Kerala Kitchen',4.7,'https://www.whiskaffair.com/wp-content/uploads/2020/05/Kerala-Prawn-Curry-2-3.jpg','🦐',1,1,0,'30 mins'),
    ('Sambar Rice','Steamed rice mixed with thick, tangy vegetable sambar. Simple south Indian soul food.',100,'South Indian','veg','South Spice',4.3,'https://encrypted-tbn0.gstatic.com/images?q=tbn:ANd9GcTrjb1mN6MRmfhinIdsUdD4SaVj23h1QfokaA&s','🍚',0,0,0,'15 mins'),
    
    # ── Biryani & Rice (15) ──
    ('Veg Biryani','Fragrant basmati layered with seasonal vegetables and aromatic dum spices.',260,'Biryani & Rice','veg','Biryani Darbar',4.5,'https://encrypted-tbn0.gstatic.com/images?q=tbn:ANd9GcSlg7JYWWJNnY-MJVGm02itthRtcc105HPt4Q&s','🌾',1,0,0,'35 mins'),
    ('Chicken Biryani','Hyderabadi dum biryani — saffron-infused basmati with succulent chicken pieces.',330,'Biryani & Rice','nonveg','Biryani Darbar',4.9,'https://www.cubesnjuliennes.com/wp-content/uploads/2020/07/Chicken-Biryani-Recipe.jpg','🍚',1,0,1,'40 mins'),
    ('Mutton Biryani','Tender mutton layered with aromatic basmati and slow-cooked on dum.',410,'Biryani & Rice','nonveg','Biryani Darbar',4.8,'https://www.cubesnjuliennes.com/wp-content/uploads/2021/03/Best-Mutton-Biryani-Recipe.jpg','🍖',1,0,0,'50 mins'),
    ('Prawn Biryani','Plump prawns dum-cooked with saffron rice, caramelised onions and herbs.',450,'Biryani & Rice','nonveg','Biryani Darbar',4.7,'https://encrypted-tbn0.gstatic.com/images?q=tbn:ANd9GcRPdg8ewaI81KS2VflCoIzAf0Rh-GqMguwDFA&s','🦐',1,1,0,'42 mins'),
    ('Egg Biryani','Fragrant dum biryani with boiled eggs, saffron basmati and caramelised onions.',270,'Biryani & Rice','nonveg','Biryani Darbar',4.5,'https://encrypted-tbn0.gstatic.com/images?q=tbn:ANd9GcRXs2_TY-Vid8Whh5nHA1Hl6WFnOw1HxGRezQ&s','🥚',1,0,0,'35 mins'),
    ('Hyderabadi Veg Biryani','Royal Hyderabadi dum biryani with fresh vegetables, kewra water and fried onions.',290,'Biryani & Rice','veg','Biryani Darbar',4.6,'https://encrypted-tbn0.gstatic.com/images?q=tbn:ANd9GcTa7wtzC0xvsruRVViH0Gece8SOuoNC7FInuw&s','🌾',1,0,0,'38 mins'),
    ('Lucknowi Biryani','Fragrant Awadhi-style dum biryani — mildly spiced with tender mutton and raisins.',380,'Biryani & Rice','nonveg','Mughal Darbar',4.8,'https://encrypted-tbn0.gstatic.com/images?q=tbn:ANd9GcSPTXEICeyoDwisw-4PE-PDps-I5D2mDMFgZQ&s','🍚',0,0,1,'45 mins'),
    ('Jeera Rice','Basmati rice tempered with ghee, cumin seeds and fresh coriander. Simple perfection.',130,'Biryani & Rice','veg','Shree Bhavan',4.4,'https://encrypted-tbn0.gstatic.com/images?q=tbn:ANd9GcQGDD6xataHW-b_UHb36ogu9A6gJasmfilbAw&s','🌾',0,0,0,'18 mins'),
    ('Pulao','Basmati rice cooked with aromatic whole spices and mixed vegetables in a single pot.',180,'Biryani & Rice','veg','Maa Ki Rasoi',4.4,'https://encrypted-tbn0.gstatic.com/images?q=tbn:ANd9GcQJq0MTUWNF_UF09dUv183INUUggDecvAPcNw&s','🌾',0,0,0,'22 mins'),
    ('Fish Biryani','Flaky fish layered with spiced basmati and slow-cooked on dum for deep flavour.',440,'Biryani & Rice','nonveg','Coastal Flavours',4.7,'https://encrypted-tbn0.gstatic.com/images?q=tbn:ANd9GcSLy9fb8GvwXrv0RxczufvyOniy5w4meEuMWg&s','🐟',1,1,0,'42 mins'),
    ('Paneer Fried Rice','Wok-tossed fried rice with paneer cubes, vegetables and Indo-Chinese sauces.',220,'Biryani & Rice','veg','Dragon Chilli',4.3,'https://www.indianveggiedelight.com/wp-content/uploads/2023/09/paneer-fried-rice-featured.jpg','🧀',0,0,0,'20 mins'),
    ('Chicken Fried Rice','Classic Indo-Chinese fried rice with egg, chicken shreds, soy sauce and spring onion.',250,'Biryani & Rice','nonveg','Dragon Chilli',4.4,'https://encrypted-tbn0.gstatic.com/images?q=tbn:ANd9GcT7JR35t1gZFG4S1tE8zACKIm-ZfxjeHKaJmw&s','🍗',0,0,0,'22 mins'),
    ('Thalassery Biryani','Fragrant Kerala-style biryani with short-grain rice, fried chicken and caramelised onion.',360,'Biryani & Rice','nonveg','Kerala Kitchen',4.8,'https://encrypted-tbn0.gstatic.com/images?q=tbn:ANd9GcTzbo-iAPeaIntJjvOk3HHD21CMFrsAGSy4YQ&s','🍚',0,1,0,'45 mins'),
    ('Mushroom Biryani','Earthy mushrooms dum-cooked with fragrant basmati, whole spices and caramelised onions.',250,'Biryani & Rice','veg','Shree Bhavan',4.5,'https://www.whiskaffair.com/wp-content/uploads/2014/07/Mushroom-Biryani-3.jpg','🍄',0,0,0,'32 mins'),
    ('Dal Tadka with Rice','Yellow toor dal tempered with ghee, mustard seeds and dried chilli, served over rice.',170,'Biryani & Rice','veg','Maa Ki Rasoi',4.6,'https://i0.wp.com/upbeetanisha.com/wp-content/uploads/2024/01/IMG_9643.jpg?resize=768%2C1024&ssl=1','🫘',0,0,0,'20 mins'),
    
    # ── Street Food (15) ──
    ('Chole Bhature','Tangy spiced chickpeas with deep-fried fluffy bread. A Punjab favourite.',160,'Street Food','veg','Chaat Corner',4.8,'https://encrypted-tbn0.gstatic.com/images?q=tbn:ANd9GcRyta2FEc05FPDkoHtzey9a8nmlgumGb7lDew&s','🫘',1,1,1,'25 mins'),
    ('Pav Bhaji','Spicy mixed vegetable mash served with butter-toasted pav buns.',160,'Street Food','veg','Chaat Corner',4.7,'https://www.cubesnjuliennes.com/wp-content/uploads/2020/07/Instant-Pot-Mumbai-Pav-Bhaji-Recipe.jpg','🍞',1,0,0,'20 mins'),
    ('Pani Puri (6 pcs)','Hollow crispy puri with tangy tamarind water, potato and chaat masala.',80,'Street Food','veg','Chaat Corner',4.6,'https://image.cdn.shpy.in/321745/1696796256313_SKU-0026_0.png?width=600&format=webp','🫙',1,0,0,'10 mins'),
    ('Bhel Puri','Puffed rice, sev, onion, tomato and tamarind chutney tossed together. Mumbai street classic.',90,'Street Food','veg','Chaat Corner',4.5,'https://www.indianveggiedelight.com/wp-content/uploads/2017/03/bhel-puri-featured-500x500.jpg','🫙',1,0,0,'10 mins'),
    ('Dahi Puri','Hollow puris filled with yogurt, potato, chaat masala and tangy chutneys.',100,'Street Food','veg','Chaat Corner',4.6,'https://www.indianveggiedelight.com/wp-content/uploads/2023/07/dahi-puri-featured.jpg','🫙',0,0,0,'12 mins'),
    ('Aloo Tikki Chaat','Crispy potato patties topped with yogurt, tamarind chutney and chaat masala.',110,'Street Food','veg','Street Bites',4.7,'https://sinfullyspicy.com/wp-content/uploads/2023/03/1-1.jpg','🥔',1,0,1,'15 mins'),
    ('Vada Pav','Mumbai\'s iconic spiced potato fritter in a pav bun with dry coconut chutney.',70,'Street Food','veg','Street Bites',4.8,'https://blog.swiggy.com/wp-content/uploads/2024/11/Image-1_mumbai-vada-pav-1024x538.png','🍔',1,0,1,'12 mins'),
    ('Sev Puri','Flat puris topped with potato, onion, chutneys and a generous layer of crunchy sev.',95,'Street Food','veg','Chaat Corner',4.5,'https://www.indianveggiedelight.com/wp-content/uploads/2023/07/Sev-puri-2.jpg','🫙',0,0,0,'10 mins'),
    ('Dahi Vada','Soft lentil dumplings soaked in yogurt, drizzled with tamarind and mint chutney.',105,'Street Food','veg','Street Bites',4.5,'https://ministryofcurry.com/wp-content/uploads/2016/08/Dahi-Vada-5.jpg','🍮',0,0,0,'12 mins'),
    ('Kachori','Deep-fried pastry stuffed with spicy urad dal or moong dal filling. Rajasthani style.',85,'Street Food','veg','Street Bites',4.4,'https://i0.wp.com/binjalsvegkitchen.com/wp-content/uploads/2023/11/khasta-kachori-H1.jpg?fit=600%2C904&ssl=1','🥟',1,0,0,'14 mins'),
    ('Misal Pav','Spicy sprouted moth curry topped with farsan, onion and pav. Maharashtrian breakfast.',130,'Street Food','veg','Chaat Corner',4.7,'https://myspicetrunk.com/wp-content/uploads/2020/07/WhatsApp-Image-2020-07-19-at-7.28.19-PM-e1607460582997.jpeg?v=1613928650','🫘',1,1,0,'18 mins'),
    ('Ragda Pattice','Potato patties on a bed of spiced white peas ragda, topped with chutneys and sev.',120,'Street Food','veg','Street Bites',4.6,'https://encrypted-tbn0.gstatic.com/images?q=tbn:ANd9GcTA23GQWMYwpoj1AW7FeSyBVt_EUAV1hfSFvQ&s','🍮',0,0,0,'15 mins'),
    ('Papdi Chaat','Crispy wafer discs layered with potato, chickpeas, yogurt and chutneys.',110,'Street Food','veg','Chaat Corner',4.6,'https://encrypted-tbn0.gstatic.com/images?q=tbn:ANd9GcQe27o06zEAbyfzUcPWl6B5SALEvCcqtVHSwQ&s','🫙',0,0,0,'12 mins'),
    ('Egg Roll','Paratha wrap with omelette, onion, green chilli and tangy ketchup. Kolkata street staple.',120,'Street Food','nonveg','Street Bites',4.6,'https://encrypted-tbn0.gstatic.com/images?q=tbn:ANd9GcRqgSc-deUkP-N519PyrV9k9w2yi3ceempqZQ&s','🌯',1,0,0,'14 mins'),
    ('Masala Corn','Sweet corn kernels tossed with chaat masala, butter, lime and red chilli.',75,'Street Food','veg','Chaat Corner',4.4,'https://www.sharmispassions.com/wp-content/uploads/2014/08/masala-corn-recipe4.jpg','🌽',1,0,0,'10 mins'),
    
    # ── Snacks (15) ──
    ('Samosa (2 pcs)','Golden crispy pastry filled with spiced potato and peas. Served with chutney.',65,'Snacks','veg','Chaat Corner',4.6,'https://prashantbandhu.com/wp-content/uploads/2023/07/DSC_0413-scaled.jpg','🥟',0,0,0,'12 mins'),
    ('Gobi Manchurian','Crispy cauliflower florets tossed in a spicy, tangy Indo-Chinese sauce.',175,'Snacks','veg','Dragon Chilli',4.5,'https://www.indianveggiedelight.com/wp-content/uploads/2017/06/gobi-manchurian-featured.jpg','🌸',1,0,0,'22 mins'),
    ('Paneer Tikka','Marinated paneer cubes grilled in tandoor with bell peppers and onion.',320,'Snacks','veg','Tandoor King',4.8,'https://encrypted-tbn0.gstatic.com/images?q=tbn:ANd9GcRJ2WY2YmIJtXrpmDToEHwJIOAcyBefjpFwXg&s','🍢',1,0,1,'28 mins'),
    ('Onion Bhaji (6 pcs)','Golden, crispy onion fritters seasoned with cumin, coriander and green chilli.',110,'Snacks','veg','Chaat Corner',4.5,'https://encrypted-tbn0.gstatic.com/images?q=tbn:ANd9GcQp6mtz1_9wfAKjzvjdCDPR8n1-VlD33frrwg&s','🧅',1,0,0,'15 mins'),
    ('Aloo Bonda','Spiced mashed potato balls dipped in chickpea batter and deep fried until golden.',90,'Snacks','veg','South Spice',4.3,'https://encrypted-tbn0.gstatic.com/images?q=tbn:ANd9GcTbnHHjZZP1Wug2gTQ2rzuClNZbl6G7B3npxg&s','🥔',0,0,0,'14 mins'),
    ('Spring Rolls (4 pcs)','Crispy rolls stuffed with stir-fried vegetables and glass noodles. Indo-Chinese style.',165,'Snacks','veg','Dragon Chilli',4.4,'https://5.imimg.com/data5/SELLER/Default/2024/6/429272154/SH/CH/LE/39612703/mix-veg-spring-rolls-4-inches-500x500.jpg','🥢',0,0,0,'20 mins'),
    ('Paneer Pakora (6 pcs)','Soft paneer slices dipped in spiced gram flour batter and fried to a crispy finish.',200,'Snacks','veg','Tandoor King',4.6,'https://jalojog.com/wp-content/uploads/2024/03/Paneer_Pakora.jpg','🧀',0,0,0,'18 mins'),
    ('Bread Pakora','Bread slices stuffed with spiced potato filling, dipped in besan batter and fried.',95,'Snacks','veg','Maa Ki Rasoi',4.3,'https://www.cubesnjuliennes.com/wp-content/uploads/2020/04/Bread-Pakora-1.jpg','🍞',0,0,0,'14 mins'),
    ('Corn Chaat','Roasted corn tossed with raw mango, coconut, chaat masala and coriander.',100,'Snacks','veg','Chaat Corner',4.4,'https://www.whiskaffair.com/wp-content/uploads/2021/06/Indian-Flavored-Corn-Chaat-2-3.jpg','🌽',0,0,0,'12 mins'),
    ('Dahi Bhalla','Soft urad dal fritters in chilled yogurt with sweet chutney and roasted cumin.',115,'Snacks','veg','Chaat Corner',4.5,'https://ministryofcurry.com/wp-content/uploads/2016/08/Dahi-Vada-5-500x500.jpg','🍮',0,0,0,'12 mins'),
    ('Masala Peanuts','Roasted peanuts coated in spicy besan batter with red chilli and chaat masala.',60,'Snacks','veg','Street Bites',4.2,'https://www.sharmispassions.com/wp-content/uploads/2020/07/MasalaPeanuts5-500x500.jpg','🥜',1,0,0,'8 mins'),
    ('Veg Momos (8 pcs)','Steamed dumplings filled with cabbage, carrot and onion, served with spicy dip.',140,'Snacks','veg','Dragon Chilli',4.6,'https://www.momodelights.com/wp-content/uploads/2023/12/Classic-Veg-Momos.jpg','🥟',0,1,0,'20 mins'),
    ('Cheese Tikki','Cheese-stuffed potato cakes flavoured with herbs and fried until perfectly golden.',155,'Snacks','veg','Street Bites',4.5,'https://i.ytimg.com/vi/Dm_Ybwy2qP8/hq720.jpg?sqp=-oaymwEhCK4FEIIDSFryq4qpAxMIARUAAAAAGAElAADIQj0AgKJD&rs=AOn4CLDftpMdM-gXkGg5ilJ54f5nIyuWRQ','🧀',0,1,0,'16 mins'),
    ('Nachos with Dips','Crispy corn chips with salsa, sour cream and jalapeños. Fusion crowd-pleaser.',180,'Snacks','veg','Dragon Chilli',4.4,'https://encrypted-tbn0.gstatic.com/images?q=tbn:ANd9GcTZqszDOutivM6exOVgWVd3Z-R9Z518BF3A4A&s','🌽',0,0,0,'12 mins'),
    ('Pyaaz Kachori','Flaky pastry stuffed with spiced onion filling. Famous Jaipur street snack.',90,'Snacks','veg','Street Bites',4.5,'https://encrypted-tbn0.gstatic.com/images?q=tbn:ANd9GcT0kYdchp1shmj-R6KNySB2eveg5HrsA_EI5g&s','🧅',1,0,0,'15 mins'),
    
    # ── Breads (15) ──
    ('Aloo Paratha','Whole wheat flatbread stuffed with spiced potato, served with curd and butter.',130,'Breads','veg','Maa Ki Rasoi',4.8,'https://www.kingarthurbaking.com/sites/default/files/2025-07/Aloo-Paratha-_2025_Lifestyle_H_2435.jpg','🫓',0,0,0,'18 mins'),
    ('Garlic Naan','Soft tandoor-baked naan generously brushed with garlic butter and coriander.',75,'Breads','veg','Tandoor King',4.7,'https://i0.wp.com/upbeetanisha.com/wp-content/uploads/2021/07/DSC_7315.jpg?w=1200&ssl=1','🫓',0,0,0,'14 mins'),
    ('Butter Naan','Classic tandoor-baked bread brushed generously with salted butter. Pillowy soft.',65,'Breads','veg','Tandoor King',4.7,'https://encrypted-tbn0.gstatic.com/images?q=tbn:ANd9GcSJjtEHocmcTO20zL7-zQ_obKDR9mry_WgGjQ&s','🫓',0,0,0,'14 mins'),
    ('Puri (4 pcs)','Light, puffed deep-fried whole wheat bread. Best with aloo sabzi or chana.',70,'Breads','veg','Maa Ki Rasoi',4.5,'https://cdn.dotpe.in/longtail/store-items/6056981/2qba2pGy.jpeg','🫓',0,0,0,'12 mins'),
    ('Lachha Paratha','Multi-layered crispy flatbread with ghee — flaky on the outside, soft inside.',85,'Breads','veg','Tandoor King',4.6,'https://www.whiskaffair.com/wp-content/uploads/2020/06/Lachha-Paratha-2-3.jpg','🫓',0,0,0,'15 mins'),
    ('Tandoori Roti','Whole wheat roti cooked directly in a clay tandoor. Rustic and wholesome.',50,'Breads','veg','Tandoor King',4.4,'https://static.toiimg.com/thumb/75542650.cms?imgsize=2236995&width=800&height=800','🫓',0,0,0,'10 mins'),
    ('Cheese Naan','Soft naan stuffed with molten processed cheese and herbs. Ultimate comfort bread.',120,'Breads','veg','Shree Bhavan',4.7,'https://encrypted-tbn0.gstatic.com/images?q=tbn:ANd9GcR3-D5Gn5WonpWc-ePWU-_Org3LXLiNYyqlHg&s','🫓',0,0,0,'16 mins'),
    ('Missi Roti','Spiced chickpea flour flatbread with cumin and ajwain. Nutritious Punjabi staple.',70,'Breads','veg','Maa Ki Rasoi',4.4,'https://encrypted-tbn0.gstatic.com/images?q=tbn:ANd9GcSN8psme5TkvbGEo-0gf9oucWdF1pf7bBmUkw&s','🫓',0,0,0,'12 mins'),
    ('Kulcha','Leavened bread cooked in tandoor, plain or stuffed with potato or paneer filling.',90,'Breads','veg','Amritsar Dhaba',4.6,'https://encrypted-tbn0.gstatic.com/images?q=tbn:ANd9GcSgbtXNcnjA-AKjhc_nyyhnAbfHFo4-aos6tA&s','🫓',0,0,0,'14 mins'),
    ('Methi Paratha','Whole wheat flatbread packed with fresh fenugreek leaves and light spices.',85,'Breads','veg','Maa Ki Rasoi',4.4,'https://sinfullyspicy.com/wp-content/uploads/2015/02/1200-by-1200-images.jpg','🫓',0,0,0,'15 mins'),
    ('Gobi Paratha','Whole wheat flatbread stuffed with spiced grated cauliflower. Punjab favourite.',130,'Breads','veg','Amritsar Dhaba',4.6,'https://zarskitchen.com/wp-content/uploads/2021/02/screenshot-2021-02-21-at-16.04.44.png','🥦',0,0,0,'18 mins'),
    ('Roomali Roti','Wafer-thin, handkerchief-sized roti folded in three — Mughlai dining tradition.',60,'Breads','veg','Mughal Darbar',4.5,'https://encrypted-tbn0.gstatic.com/images?q=tbn:ANd9GcRfSqudX6T-iDHGmZpmABbA3WrHAtz6k1wW0w&s','🫓',0,0,0,'10 mins'),
    ('Bhatura (2 pcs)','Fluffy, puffed deep-fried leavened bread — iconic partner for chole.',80,'Breads','veg','Amritsar Dhaba',4.5,'https://encrypted-tbn0.gstatic.com/images?q=tbn:ANd9GcR-41imt_q7qgA-oiD-0YsbAb2zN2ACAXSkfw&s','🫓',0,0,0,'14 mins'),
    ('Sheermal','Mildly sweet, saffron-flavoured Mughlai flatbread baked in a clay oven.',90,'Breads','veg','Mughal Darbar',4.6,'https://encrypted-tbn0.gstatic.com/images?q=tbn:ANd9GcRP8n2QLS4Ph0JgsLqzKciw28FY3IuXD22BLQ&s','🫓',0,1,0,'18 mins'),
    ('Mooli Paratha','Whole wheat flatbread stuffed with seasoned grated radish. Winter Punjabi staple.',120,'Breads','veg','Amritsar Dhaba',4.3,'https://i0.wp.com/binjalsvegkitchen.com/wp-content/uploads/2014/10/Mooli-Paratha-H1.jpg?fit=600%2C900&ssl=1','🥕',0,0,0,'18 mins'),
   
    # ── Desserts (15) ──
    ('Gulab Jamun (4 pcs)','Soft milk-solid dumplings soaked in rose-cardamom sugar syrup.',95,'Desserts','veg','Mithaas',4.9,'https://encrypted-tbn0.gstatic.com/images?q=tbn:ANd9GcRD5KYcR79wTcJv7U6nYzIGNIU5iEBK0AoPkQ&s','🍮',0,0,1,'12 mins'),
    ('Rasgulla (4 pcs)','Spongy chenna balls poached in light sugar syrup. Bengali classic.',105,'Desserts','veg','Mithaas',4.7,'https://5.imimg.com/data5/SELLER/Default/2022/10/KM/CQ/UT/72770402/rasgulla-500x500.jpeg','🍡',0,0,0,'12 mins'),
    ('Kheer','Creamy rice pudding with saffron, cardamom, almonds and pistachios.',120,'Desserts','veg','Mithaas',4.6,'https://encrypted-tbn0.gstatic.com/images?q=tbn:ANd9GcTBEc0InuxfAjBaPQtlssFn-PIbKkVp1wN6rA&s','🍚',0,1,0,'14 mins'),
    ('Jalebi (250g)','Crispy, syrup-soaked spirals of maida batter. Best served hot with rabri.',110,'Desserts','veg','Mithaas',4.8,'https://myblacktree.com/cdn/shop/files/360OKUK.png?v=1692031846','🍩',0,0,1,'12 mins'),
    ('Rabri','Thickened sweetened milk slow-cooked with cardamom, saffron and pistachios.',150,'Desserts','veg','Mithaas',4.7,'https://encrypted-tbn0.gstatic.com/images?q=tbn:ANd9GcT7QEG8zp8CHUyc5cntjcJa-CIv3-0MoLXp5w&s','🍮',0,0,0,'12 mins'),
    ('Gajar Halwa','Slow-cooked grated carrot in ghee with full-fat milk and cardamom. Winter classic.',140,'Desserts','veg','Mithaas',4.8,'https://encrypted-tbn0.gstatic.com/images?q=tbn:ANd9GcQ7KSjeFFcgNoSOXMebxZ3zTH8eIA6_VUMUdQ&s','🥕',0,1,0,'15 mins'),
    ('Kulfi (2 sticks)','Dense, creamy Indian ice cream with pistachio and cardamom — malai kulfi on a stick.',100,'Desserts','veg','Mithaas',4.7,'https://tiimg.tistatic.com/fp/1/007/555/tastey-sweet-kesar-pista-kulfi-with-11-gm-fat-2-months-shelf-life-754.jpg','🍦',0,0,0,'5 mins'),
    ('Malpua','Soft pan-fried sweet pancakes soaked in saffron syrup with a rabri topping.',120,'Desserts','veg','Mithaas',4.5,'https://www.indianhealthyrecipes.com/wp-content/uploads/2021/12/malpua-recipe.jpg','🥞',0,0,0,'14 mins'),
    ('Shahi Tukda','Fried bread triangles layered with creamy rabri, saffron and silver foil garnish.',165,'Desserts','veg','Mughal Darbar',4.6,'https://www.cubesnjuliennes.com/wp-content/uploads/2019/03/Best-Shahi-Tukda-Recipe.jpg','🍞',0,0,0,'12 mins'),
    ('Phirni','Ground rice dessert set in clay pots with saffron, cardamom and rose water.',130,'Desserts','veg','Mithaas',4.6,'https://encrypted-tbn0.gstatic.com/images?q=tbn:ANd9GcQiK4BCbStotstFmeNgYg-QyFhtFp_NExhiqg&s','🍮',0,0,0,'12 mins'),
    ('Anjeer Barfi','Premium fig and dry fruit fudge with cardamom. Sugar-free option available.',200,'Desserts','veg','Mithaas',4.5,'https://thebaklavabox.com/cdn/shop/products/anjeer-dry-fruit-barfi-523987.jpg?v=1745425379','🍬',0,1,0,'5 mins'),
    ('Motichoor Ladoo (4 pcs)','Delicate ladoos made from tiny besan pearls, sugar and cardamom. Festival favourite.',120,'Desserts','veg','Mithaas',4.7,'https://www.murarisweets.com/cdn/shop/files/MotichoorLaddu4.png?v=1709528857','🟡',0,0,0,'5 mins'),
    ('Ice Cream (2 scoops)','Choice of mango, rose or pistachio ice cream in a waffle cup. Refreshingly creamy.',110,'Desserts','veg','Mithaas',4.5,'https://img.freepik.com/premium-photo/two-scoops-chocolate-ice-cream-with-chocolate-sauce-pink-polka-dot-cup_1077802-451655.jpg?w=360','🍨',0,0,0,'5 mins'),
    ('Basundi','Maharashtrian version of rabri — thick sweetened milk with almonds and cardamom.',145,'Desserts','veg','Mithaas',4.6,'https://www.sharmispassions.com/wp-content/uploads/2014/12/basundi4.jpg','🍮',0,0,0,'12 mins'),
    ('Kaju Katli (4 pcs)','Silky cashew fudge diamond-shaped sweets dusted with silver varak. Diwali classic.',180,'Desserts','veg','Mithaas',4.7,'https://shreevaishnavisweets.com/cdn/shop/files/Shree-Vaishnavi-Sweets-and-Snacks-kaju-katli_47d0eee8-1b3e-4368-bef1-013e4b0d6470.jpg?v=1736592122','🍬',0,0,0,'5 mins'),
   
    # ── Drinks (15) ──
    ('Mango Lassi','Chilled yogurt blended with fresh Alphonso mango pulp and cardamom.',85,'Drinks','veg','Shree Bhavan',4.8,'https://flavorquotient.com/wp-content/uploads/2023/05/Mango-Lassi-FQ-6-1036.jpg','🥭',0,0,1,'10 mins'),
    ('Masala Chai','Aromatic tea brewed with ginger, cardamom, cinnamon and black pepper.',55,'Drinks','veg','Maa Ki Rasoi',4.9,'https://www.thespicehouse.com/cdn/shop/articles/Chai_Masala_Tea_1200x1200.jpg?v=1606936195','🍵',0,0,0,'10 mins'),
    ('Rose Lassi','Thick yogurt blended with rose syrup and cardamom. Falooda strands optional.',90,'Drinks','veg','Amritsar Dhaba',4.7,'https://masalaandchai.com/wp-content/uploads/2022/01/Sweet-Rose-Lassi.jpg','🌹',0,0,0,'10 mins'),
    ('Nimbu Pani','Fresh lime water with black salt, cumin and mint. India\'s perfect summer cooler.',55,'Drinks','veg','Street Bites',4.5,'https://thumbs.dreamstime.com/b/glass-nimbu-pani-refreshing-drink-made-lemon-sugar-water-garnished-mint-leaves-ice-isolated-clean-white-372711746.jpg','🍋',0,0,0,'8 mins'),
    ('Thandai','Chilled spiced milk with almonds, fennel, peppercorn and saffron. Festive drink.',110,'Drinks','veg','Mithaas',4.7,'https://www.cookwithmanali.com/wp-content/uploads/2015/03/Thandai-Indian-Drink-500x500.jpg','🥛',0,0,0,'10 mins'),
    ('Aam Panna','Raw mango cooler with cumin, black salt and mint. Beats the Indian summer heat.',65,'Drinks','veg','Chaat Corner',4.5,'https://www.ruchiskitchen.com/wp-content/uploads/2015/05/aam-ka-panna-1.jpg','🥭',0,0,0,'8 mins'),
    ('Jaljeera','Cumin-mint water with black salt and chilli — a tangy, spicy North Indian appetiser drink.',60,'Drinks','veg','Street Bites',4.4,'https://www.ndtv.com/cooks/images/Iced.Jaljeera-620.jpg','🌿',1,0,0,'8 mins'),
    ('Cold Coffee','Blended iced coffee with full-fat milk and sugar. Strong, creamy and refreshing.',130,'Drinks','veg','Dragon Chilli',4.6,'https://encrypted-tbn0.gstatic.com/images?q=tbn:ANd9GcR7HN8AiGNBnRRMXEzB8ONaK4QJoAW0zhJ49A&s','☕',0,0,0,'10 mins'),
    ('Filter Coffee','Traditional South Indian decoction coffee with frothed milk in a davara tumbler.',65,'Drinks','veg','South Spice',4.9,'https://encrypted-tbn0.gstatic.com/images?q=tbn:ANd9GcQ0GTpDvr6WtWtEtG2-TiGRLdq6iTOhoKhmNQ&s','☕',0,0,1,'8 mins'),
    ('Shikanjvi','Punjab\'s own lemonade with kala namak and roasted cumin. Refreshingly tangy.',70,'Drinks','veg','Amritsar Dhaba',4.5,'https://encrypted-tbn0.gstatic.com/images?q=tbn:ANd9GcSc0tTFRXAKnj4APVn2j02G_h7Hwd9HBt9tRw&s','🍋',0,0,0,'8 mins'),
    ('Sugarcane Juice','Fresh-pressed sugarcane juice with ginger and lime. Cold-pressed on the spot.',60,'Drinks','veg','Street Bites',4.7,'https://encrypted-tbn0.gstatic.com/images?q=tbn:ANd9GcTERkPbMG1xf8F1JjcbH5SjqHUWep9DbJMmxg&s','🌿',0,0,0,'8 mins'),
    ('Sattu Sharbat','Bihar\'s cooling roasted barley drink with black salt and lime. Protein-rich.',80,'Drinks','veg','Amritsar Dhaba',4.4,'https://encrypted-tbn0.gstatic.com/images?q=tbn:ANd9GcTYcl_qVm2GiXvkRIJruJ9jTvunPN4f6xQI6g&s','🥛',0,1,0,'8 mins'),
    ('Sol Kadhi','Kokum and coconut milk drink from Konkan — pink, tangy and gut-cooling.',90,'Drinks','veg','Coastal Flavours',4.6,'https://www.vegrecipesofindia.com/wp-content/uploads/2012/03/sol-kadhi-recipe-1.jpg','🩷',0,0,0,'10 mins'),
    ('Badam Milk','Warm or chilled almond milk with saffron, cardamom and sugar. Nourishing night drink.',100,'Drinks','veg','Mithaas',4.6,'https://encrypted-tbn0.gstatic.com/images?q=tbn:ANd9GcQWpC_dXgZAmOhd6YmxR4g4iJNtk9EVanebDQ&s','🥛',0,0,0,'10 mins'),
    ('Kokum Sherbet','Cooling Goan kokum drink — sweet, tangy and deeply refreshing on a hot day.',75,'Drinks','veg','Coastal Flavours',4.5,'https://encrypted-tbn0.gstatic.com/images?q=tbn:ANd9GcQFlaWMjL9RhFOKkDwIYHQfpVhtEeoK6mPSEA&s','🩷',0,0,0,'8 mins'),
   
    # ── Non-Veg Curries (15) ──
    ('Butter Chicken','Tender chicken pieces in silky, velvety tomato-butter gravy — India\'s most loved.',290,'Non-Veg Curries','nonveg','Maa Ki Rasoi',4.9,'https://www.licious.in/blog/wp-content/uploads/2020/10/butter-chicken--600x600.jpg','🍗',0,0,1,'30 mins'),
    ('Mutton Rogan Josh','Aromatic Kashmiri lamb curry with whole spices and fiery Kashmiri chilli.',390,'Non-Veg Curries','nonveg','Kashmiri Daawat',4.9,'https://static.toiimg.com/thumb/53192600.cms?imgsize=418831&width=800&height=800','🥩',1,0,1,'45 mins'),
    ('Prawn Masala','Juicy prawns simmered in a fiery Goan-style coconut-tomato masala.',440,'Non-Veg Curries','nonveg','Coastal Flavours',4.7,'https://www.gohealthyeverafter.com/wp-content/uploads/2023/02/Prawn-Masala-Fry-23.jpg','🦐',1,1,0,'32 mins'),
    ('Fish Curry','Fresh fish in a tangy Konkani-style coconut curry with tamarind and kokum.',360,'Non-Veg Curries','nonveg','Coastal Flavours',4.7,'https://www.licious.in/blog/wp-content/uploads/2022/03/shutterstock_1891229335-min.jpg','🐟',1,0,0,'30 mins'),
    ('Egg Curry','Boiled eggs halved and dunked in a robust, spicy masala gravy.',200,'Non-Veg Curries','nonveg','Maa Ki Rasoi',4.5,'https://images.services.kitchenstories.io/qxU0BGK_o190HTKyrVkTEFf-cc0=/3840x0/filters:quality(80)/images.kitchenstories.io/wagtailOriginalImages/R2899-photo-final-3x4.jpg','🥚',1,0,0,'20 mins'),
    ('Chicken Korma','Tender chicken in a rich, fragrant Mughlai gravy with yogurt and whole spices.',310,'Non-Veg Curries','nonveg','Mughal Darbar',4.6,'https://www.teaforturmeric.com/wp-content/uploads/2025/09/Chicken-Korma-03.jpg','🍗',0,0,0,'32 mins'),
    ('Chicken Vindaloo','Fiery Goan-style chicken in a tangy, vinegar-based curry — bold and complex.',320,'Non-Veg Curries','nonveg','Goa Coast',4.7,'https://www.whiskaffair.com/wp-content/uploads/2021/05/Chicken-Vindaloo-2-3.jpg','🍗',1,0,0,'30 mins'),
    ('Mutton Kheema','Minced mutton cooked dry with peas, whole spices and a masala base. Rich and hearty.',340,'Non-Veg Curries','nonveg','Mughal Darbar',4.6,'https://yummyindiankitchen.com/wp-content/uploads/2016/01/mutton-keema.jpg','🥩',1,0,0,'30 mins'),
    ('Chicken Saag','Chicken cooked in fresh spinach and fenugreek leaves — earthy, nutritious and flavourful.',300,'Non-Veg Curries','nonveg','Maa Ki Rasoi',4.6,'https://www.cubesnjuliennes.com/wp-content/uploads/2020/09/Palak-Chicken-Saag-Recipe.jpg','🌿',0,0,0,'28 mins'),
    ('Mutton Paya Soup','Slow-simmered lamb trotter soup with aromatic spices — deeply nourishing.',370,'Non-Veg Curries','nonveg','Kashmiri Daawat',4.6,'https://static.toiimg.com/thumb/70361843.cms?imgsize=328990&width=800&height=800','🍲',1,0,0,'50 mins'),
    ('Chicken Chettinad Curry','Spicy South Indian chicken curry with freshly ground kalpasi and marathi mokku.',330,'Non-Veg Curries','nonveg','Chettinad House',4.7,'https://www.whiskaffair.com/wp-content/uploads/2020/09/Chicken-Chettinad-Curry-2-3.jpg','🍗',1,1,0,'35 mins'),
    ('Duck Curry','Tender duck pieces in a thick coconut-based Kerala gravy with roasted spices.',420,'Non-Veg Curries','nonveg','Kerala Kitchen',4.7,'https://blogger.googleusercontent.com/img/b/R29vZ2xl/AVvXsEgzbqhEyq7UkgrBOMGV0wMIL-Pnm4gurD1V5HP1-12kjynp2haT5bzuGTW1u8ig66ZBCBdokhUe-5YWcpIDeGBycLRUfrHXjL4hQpeEEGT6DZS9NMxUrvz9eArM3i5bLKCpcCF4sXvVF8k/s2048/kuttanadu+duck+curry+8.JPG','🦆',1,1,0,'45 mins'),
    ('Chicken Tikka Masala','Chargrilled chicken tikka in a creamy, spiced tomato-fenugreek sauce.',310,'Non-Veg Curries','nonveg','Tandoor King',4.9,'https://www.seriouseats.com/thmb/DbQHUK2yNCALBnZE-H1M2AKLkok=/1500x0/filters:no_upscale():max_bytes(150000):strip_icc()/chicken-tikka-masala-for-the-grill-recipe-hero-2_1-cb493f49e30140efbffec162d5f2d1d7.JPG','🍗',0,0,1,'30 mins'),
    ('Lamb Shank Nihari','Slow-braised lamb shank in a rich, slow-cooked Mughlai gravy with nihari masala.',480,'Non-Veg Curries','nonveg','Mughal Darbar',4.9,'https://images.immediate.co.uk/production/volatile/sites/2/2021/11/2021-11-04_OLI-1221-SlowCookedStews-LambShankNihari_0020-d649c71.jpg?resize=1366,2049','🍖',0,0,1,'60 mins'),
    ('Chicken Kadai','Chicken and capsicum cooked in a wok with freshly pounded kadai spices.',310,'Non-Veg Curries','nonveg','Kashmiri Daawat',4.6,'https://encrypted-tbn0.gstatic.com/images?q=tbn:ANd9GcRiu7hpTeKhbkOWrIrRWActdk8E40NkAuAMxQ&s','🍗',1,0,0,'30 mins'),
   
    # ── Non-Veg Snacks (15) ──
    ('Tandoori Chicken','Whole chicken marinated in yogurt and 12 spices, cooked in a clay tandoor.',420,'Non-Veg Snacks','nonveg','Tandoor King',4.9,'https://www.kitchensanctuary.com/wp-content/uploads/2025/07/Tandoori-Chicken-Square-FS.jpg','🍗',0,0,1,'38 mins'),
    ('Chicken Tikka','Marinated chicken cubes grilled to smoky perfection in the tandoor.',360,'Non-Veg Snacks','nonveg','Tandoor King',4.8,'https://sinfullyspicy.com/wp-content/uploads/2014/03/1200-by-1200-images-2.jpg','🍢',1,0,0,'30 mins'),
    ('Chicken 65','Deep-fried chicken marinated in yogurt, red chilli and spices. South Indian icon.',280,'Non-Veg Snacks','nonveg','Dragon Chilli',4.7,'https://www.indianhealthyrecipes.com/wp-content/uploads/2022/03/chicken-65-swasthi.jpg','🍗',1,0,1,'25 mins'),
    ('Seekh Kebab (4 pcs)','Minced mutton kebabs with herbs on skewers, grilled in the tandoor.',340,'Non-Veg Snacks','nonveg','Tandoor King',4.7,'https://www.bigsams.in/wp-content/uploads/2024/03/3.png','🍢',1,0,0,'28 mins'),
    ('Chicken Kathi Roll','Spicy chicken tikka wrapped in a flaky paratha with onion and green chutney.',210,'Non-Veg Snacks','nonveg','Street Bites',4.6,'https://encrypted-tbn0.gstatic.com/images?q=tbn:ANd9GcQeIJyBlR7ImfQhZ-jW4qXV3zlQ50r7LKd0eg&s','🌯',1,0,0,'18 mins'),
    ('Keema Pav','Spiced minced lamb with peas, served with butter-toasted pav buns.',220,'Non-Veg Snacks','nonveg','Street Bites',4.5,'https://encrypted-tbn0.gstatic.com/images?q=tbn:ANd9GcQzlPkEirVY1QABBcsL-BPf8_cJP79lcyPPdA&s','🍞',1,0,0,'22 mins'),
    ('Fish Tikka','Boneless fish marinated in ajwain-yogurt mix, grilled in tandoor to perfection.',380,'Non-Veg Snacks','nonveg','Coastal Flavours',4.7,'https://encrypted-tbn0.gstatic.com/images?q=tbn:ANd9GcRYvsGm3TWWp3RWfyVeObjOEGqY6T8IyUx41Q&s','🐟',0,1,0,'26 mins'),
    ('Chicken Momos (8 pcs)','Steamed dumplings filled with minced chicken and ginger-garlic, served with fiery sauce.',200,'Non-Veg Snacks','nonveg','Dragon Chilli',4.6,'https://encrypted-tbn0.gstatic.com/images?q=tbn:ANd9GcQb1u4aR5PYbd2sbKApB1mdWCE3U5SAwu-hkQ&s','🥟',0,0,0,'22 mins'),
    ('Mutton Shammi Kebab','Pan-fried patties of minced mutton and chana dal with whole spices and herbs.',380,'Non-Veg Snacks','nonveg','Mughal Darbar',4.7,'https://encrypted-tbn0.gstatic.com/images?q=tbn:ANd9GcQbxURsBcWT1aFE-ds2z0wtdPk7oNpowQST7g&s','🍢',1,0,0,'30 mins'),
    ('Prawn Koliwada','Fried prawns in a spicy Koli-style batter — a beloved Mumbai coastal speciality.',380,'Non-Veg Snacks','nonveg','Coastal Flavours',4.7,'https://encrypted-tbn0.gstatic.com/images?q=tbn:ANd9GcTUxoFp9ZzOhMQhtmiQsFRIjJ0_xaFzKsi2Sw&s','🦐',1,1,0,'24 mins'),
    ('Chicken Malai Tikka','Creamy, melt-in-mouth chicken marinated with cream, cheese and mild spices.',400,'Non-Veg Snacks','nonveg','Tandoor King',4.8,'https://encrypted-tbn0.gstatic.com/images?q=tbn:ANd9GcSl4fnVww2NUBuSe0S-RGbsArx_rlrCPg3nMw&s','🍗',0,0,0,'32 mins'),
    ('Egg Bhurji Pav','Spicy scrambled eggs with onion and tomato, served with toasted pav buns.',150,'Non-Veg Snacks','nonveg','Street Bites',4.6,'https://encrypted-tbn0.gstatic.com/images?q=tbn:ANd9GcQheI9ru4pG-PIOIRlaIgaSw7raXBblxset2Q&s','🥚',1,0,0,'15 mins'),
    ('Amritsari Fish Fry','Crispy batter-fried fish with ajwain and carom seeds — a classic Punjabi starter.',350,'Non-Veg Snacks','nonveg','Coastal Flavours',4.8,'https://images.unsplash.com/photo-1504674900247-0877df9cc836?auto=format&fit=crop&w=480&q=80','🐟',1,0,1,'24 mins'),
    ('Mutton Galouti Kebab','Melt-in-mouth minced mutton kebabs with 100+ spices. Lucknowi royal legacy.',450,'Non-Veg Snacks','nonveg','Mughal Darbar',4.9,'https://sinfullyspicy.com/wp-content/uploads/2022/07/1200-by-1200-images-5.jpg','🥩',0,0,1,'35 mins'),
    ('Chicken Hariyali Tikka','Green marinated chicken with spinach, coriander and mint — fresh, aromatic and smoky.',370,'Non-Veg Snacks','nonveg','Tandoor King',4.7,'https://recipe52.com/wp-content/uploads/2019/11/Haryali-Chicken-tikka-Recipe-1.jpg','🌿',0,1,0,'28 mins'),
   
    # ── International Food (165) ──
    ('Margherita Pizza','Classic Neapolitan pizza with San Marzano tomatoes, fresh mozzarella and basil on thin, crispy crust.',399,'International Food','veg','Bella Italia',4.8,'https://encrypted-tbn0.gstatic.com/images?q=tbn:ANd9GcTGCjja1oF5mPdnjaor57SEgeb69PtKwk3rSw&s','🍕',0,0,1,'25 mins'),
    ('Chicken Shawarma','Slow-roasted chicken with garlic sauce, pickled vegetables and tahini wrapped in warm pita.',279,'International Food','nonveg','Arabian Nights',4.7,'https://kristineskitchenblog.com/wp-content/uploads/2024/07/chicken-shawarma-06-3.jpg','🌯',1,0,1,'18 mins'),
    ('Pad Thai Noodles','Classic Thai stir-fried rice noodles with egg, tofu, shrimp, bean sprouts and roasted peanuts.',329,'International Food','nonveg','Bangkok Street',4.6,'https://www.funfoodfrolic.com/wp-content/uploads/2014/07/Pad-Thai-2.jpg','🍜',1,0,0,'20 mins'),
    ('Beef Burger','Juicy 150g beef patty with cheddar, lettuce, tomato, pickles and special house sauce in a brioche bun.',349,'International Food','nonveg','American Diner',4.8,'https://www.puregoldpineapples.com.au/wp-content/uploads/2020/10/aussie-beef-burger.jpg','🍔',0,0,1,'20 mins'),
    ('Sushi Platter (12 pcs)','Chef\'s selection of 12 premium nigiri and maki rolls with pickled ginger, wasabi and soy sauce.',699,'International Food','nonveg','Tokyo Garden',4.9,'https://c4.wallpaperflare.com/wallpaper/282/207/746/comida-cuenco-japon-pescado-wallpaper-preview.jpg','🍱',0,1,0,'30 mins'),
    ('Falafel Wrap','Crispy chickpea falafel with hummus, tabbouleh and pickled turnip in warm lavash bread.',229,'International Food','veg','Arabian Nights',4.5,'https://static.toiimg.com/thumb/62708678.cms?imgsize=156976&width=800&height=800','🧆',0,0,0,'15 mins'),
    ('Pasta Carbonara','Al dente spaghetti with creamy egg sauce, crispy pancetta and generous shaved Pecorino.',379,'International Food','nonveg','Bella Italia',4.7,'https://www.simplyrecipes.com/thmb/0UeN5LhKq-ze3BcZJ7_Yp803T24=/1500x0/filters:no_upscale():max_bytes(150000):strip_icc()/Simply-Pasta-Carbonara-LEAD-1-c477cc25c7294cd9a3fc51ece176481f.jpg','🍝',0,0,0,'22 mins'),
    ('Tom Yum Soup','Fiery Thai prawn soup with lemongrass, kaffir lime, galangal, mushrooms and chilli paste.',269,'International Food','nonveg','Bangkok Street',4.6,'https://hot-thai-kitchen.com/wp-content/uploads/2013/03/tom-yum-goong-blog.jpg','🍲',1,0,0,'18 mins'),
    ('Tacos (3 pcs)','Three corn tortillas with spiced chicken al pastor, salsa verde, pickled onion and cotija cheese.',299,'International Food','nonveg','Mexican Fiesta',4.6,'https://amindfullmom.com/wp-content/uploads/2019/08/15-minute-Buffalo-Chicken-tacos.jpg','🌮',1,1,0,'18 mins'),
    ('Greek Salad','Crisp cucumber, ripe tomatoes, Kalamata olives, red onion and creamy feta with oregano dressing.',249,'International Food','veg','Mediterranean Blue',4.5,'https://hostessatheart.com/wp-content/uploads/2023/04/IG3.png','🥗',0,0,0,'10 mins'),
    ('Ramen Bowl','Rich tonkotsu broth with hand-pulled noodles, chashu pork, soft-boiled egg and nori.',449,'International Food','nonveg','Tokyo Garden',4.8,'https://encrypted-tbn0.gstatic.com/images?q=tbn:ANd9GcSDb2mrso9DsTL1hqyZGvUlbx3dcD1gIaK5QA&s','🍜',0,0,1,'28 mins'),
    ('Beef Lasagna','Layers of fresh pasta sheets with slow-cooked Bolognese, béchamel and melted Parmigiano.',429,'International Food','nonveg','Bella Italia',4.6,'https://www.allrecipes.com/thmb/n4juPHgQa4dRSL_mjIlRkjhcc4s=/1500x0/filters:no_upscale():max_bytes(150000):strip_icc()/994958-632592e9643145f6a26315215c0086ce.jpg','🫕',0,0,0,'30 mins'),
    ('Nachos Supreme','Crunchy tortilla chips with nacho cheese, jalapeños, sour cream, guacamole and pico de gallo.',319,'International Food','veg','Mexican Fiesta',4.5,'https://encrypted-tbn0.gstatic.com/images?q=tbn:ANd9GcSD9LYAMDm2hRm6Gp-FGRy3G5RDBvEDiI4b1w&s','🧀',1,0,0,'15 mins'),
    ('Dim Sum Basket (8 pcs)','Assorted steamed dumplings — har gow, siu mai and char siu bao with dipping sauces.',359,'International Food','nonveg','Dragon Palace',4.7,'https://m.media-amazon.com/images/I/61N4Dspd-JS.jpg','🥟',0,1,0,'22 mins'),
    ('Fish & Chips','Beer-battered Atlantic cod fillet with crispy thick-cut chips, mushy peas and tartar sauce.',389,'International Food','nonveg','British Bites',4.5,'https://kotanyi-en.imgix.net/wp-content/uploads/2025/10/fish-chips.jpg?auto=format,compress','🐟',0,0,0,'25 mins'),
    ('Risotto ai Funghi','Creamy Arborio rice slow-cooked with porcini mushrooms, white wine, shallots and Parmesan.',449,'International Food','veg','Bella Italia',4.8,'https://www.cooking-vacations.com/wp-content/uploads/2023/06/50.jpeg','🍚',0,0,1,'28 mins'),
    ('Tiramisu','Classic Italian dessert — espresso-soaked ladyfingers layered with mascarpone cream and cocoa.',299,'International Food','veg','Bella Italia',4.9,'https://www.giallozafferano.com/images/283-28392/traditional-tiramisu_1200x800.jpg','🍮',0,0,1,'10 mins'),
    ('Bruschetta al Pomodoro','Grilled sourdough rubbed with garlic, topped with fresh tomatoes, basil and extra virgin olive oil.',199,'International Food','veg','Bella Italia',4.5,'https://healthiersteps.com/wp-content/uploads/2018/01/bruschetta-al-pomodoro-1152x1536-2.jpg','🍅',0,0,0,'10 mins'),
    ('Osso Buco Milanese','Braised veal shanks in white wine and broth with gremolata, served with saffron risotto.',699,'International Food','nonveg','Bella Italia',4.7,'https://www.sacla.co.uk/cdn/shop/articles/SACLA_OSSOBUCO_SHANK.jpg?v=1726839071','🦴',0,1,0,'45 mins'),
    ('Penne Arrabbiata','Penne pasta in a fiery tomato-garlic sauce with fresh chilli and extra virgin olive oil.',329,'International Food','veg','Bella Italia',4.6,'https://recipesblob.oetker.in/assets/4783fdd6cb1b435daf84be42201037cb/1272x764/penne-arrabbiata.webp','🍝',1,0,0,'20 mins'),
    ('Focaccia Genovese','Soft, dimpled flatbread drizzled with olive oil, sea salt and fresh rosemary. Warm from oven.',249,'International Food','veg','Bella Italia',4.5,'https://encrypted-tbn0.gstatic.com/images?q=tbn:ANd9GcQoAwol_ybPYnuKXfbcyNyMmrSxx9h2Q8Qw2qa0cXDhiqKgmH9vFc0nMNfrXcw9yzh5UmI&usqp=CAU','🫓',0,0,0,'18 mins'),
    ('Panna Cotta','Silky vanilla cream set with gelatine, topped with fresh berry coulis and mint.',279,'International Food','veg','Bella Italia',4.7,'https://www.italytravelandlife.com/wp-content/uploads/2021/07/Italian-Panna-Cotta-recipe.jpg','🍮',0,0,0,'10 mins'),
    ('Chicken Cacciatore','Hunter-style braised chicken with tomatoes, olives, capers, bell peppers and white wine.',499,'International Food','nonveg','Bella Italia',4.6,'https://encrypted-tbn0.gstatic.com/images?q=tbn:ANd9GcR1CAj5hPmpXFpHy5fMFLG-6_9887OG23iqtQ&s','🍗',0,0,0,'35 mins'),
    ('Gnocchi Sorrentina','Soft potato gnocchi baked in a fresh tomato-basil sauce with bubbling mozzarella.',379,'International Food','veg','Bella Italia',4.6,'https://cookingmydreams.com/wp-content/uploads/2024/05/Gnocchi-alla-Sorrentina-9.jpg','🥔',0,0,0,'22 mins'),
    ('Cannoli Siciliani','Crispy fried pastry shells filled with sweet ricotta, candied peel and dark chocolate chips.',249,'International Food','veg','Bella Italia',4.7,'https://encrypted-tbn0.gstatic.com/images?q=tbn:ANd9GcQ2GhCW3uMoqGOFKsR9m_jRQE71T5bfcPw1Bw&s','🧁',0,0,0,'8 mins'),
    ('Minestrone Soup','Hearty Italian vegetable soup with borlotti beans, seasonal greens and pasta. Served with crusty bread.',229,'International Food','veg','Bella Italia',4.4,'https://images.immediate.co.uk/production/volatile/sites/30/2021/03/Classic-Minestrone-Soup-13720e5.jpg?resize=768,713','🍲',0,0,0,'20 mins'),
    ('Saltimbocca alla Romana','Pan-fried veal escalopes wrapped in prosciutto and fresh sage in a butter-white wine sauce.',599,'International Food','nonveg','Bella Italia',4.7,'https://www.giallozafferano.com/images/227-22762/saltimbocca-alla-romana-roman-style-veal-cutlets_1200x800.jpg','🥩',0,1,0,'25 mins'),
    ('Margherita Pizza','Classic Neapolitan pizza — San Marzano tomatoes, fresh buffalo mozzarella and basil on thin crust.',399,'International Food','veg','Bella Italia',4.8,'https://cdn.uengage.io/uploads/5/image-342266-1715596630.png','🍕',0,0,1,'25 mins'),
    ('Pasta Carbonara','Al dente spaghetti with silky egg-guanciale sauce and generous shaved Pecorino Romano.',379,'International Food','nonveg','Bella Italia',4.7,'https://www.bakersplus.com/content/v2/binary/image/imageset_simple-spaghetti-carbonara--30_simple-spaghetti-carbonara_evergreen-reshoot_p_22-tkc-0112_b.jpg','🍝',0,0,0,'22 mins'),
    ('Beef Lasagna','Layers of fresh pasta, slow-cooked Bolognese, béchamel sauce and melted Parmigiano-Reggiano.',429,'International Food','nonveg','Bella Italia',4.6,'https://www.tasteofhome.com/wp-content/uploads/2025/07/Best-Lasagna_EXPS_ATBBZ25_36333_DR_07_01_2b.jpg','🫕',0,0,0,'30 mins'),
    ('Chicken Teriyaki Bowl','Glazed chicken thighs in sweet teriyaki sauce over steamed rice with sesame and spring onion.',449,'International Food','nonveg','Tokyo Garden',4.8,'https://playswellwithbutter.com/wp-content/uploads/2024/04/Teriyaki-Chicken-Bowls-9.jpg','🍗',0,0,1,'22 mins'),
    ('Gyoza (8 pcs)','Pan-fried pork and cabbage dumplings with a crispy bottom, served with ponzu dipping sauce.',299,'International Food','nonveg','Tokyo Garden',4.7,'https://www.momodelights.com/wp-content/uploads/2023/12/Chilli-Paneer-Gyoza-Momos.jpg','🥟',0,0,0,'18 mins'),
    ('Tempura Platter','Lightly battered tiger prawns and seasonal vegetables fried to a golden crisp. Served with dashi dip.',549,'International Food','nonveg','Tokyo Garden',4.6,'https://thumbs.dreamstime.com/b/assorted-tempura-shrimp-vegetables-dipping-sauce-delicious-platter-assorted-tempura-featuring-crispy-golden-fried-383392720.jpg','🍤',0,0,0,'25 mins'),
    ('Miso Soup','Traditional dashi-based soup with soft tofu, wakame seaweed and spring onion. Simple and nourishing.',149,'International Food','veg','Tokyo Garden',4.5,'https://encrypted-tbn0.gstatic.com/images?q=tbn:ANd9GcQwMOAhlAHZcU2lV4FcD13V0gmKj2ryjHo1fQ&s','🍵',0,0,0,'10 mins'),
    ('Tonkatsu Set','Panko-crusted fried pork cutlet with tonkatsu sauce, shredded cabbage, rice and miso soup.',499,'International Food','nonveg','Tokyo Garden',4.7,'https://live.staticflickr.com/7160/6751667727_c33014f2a5_b.jpg','🥩',0,0,0,'25 mins'),
    ('Edamame','Steamed young soybeans in the pod with sea salt. Simple, healthy Japanese snack.',179,'International Food','veg','Tokyo Garden',4.4,'https://images.services.kitchenstories.io/P35ZhSf7mNJW3ntmAmX57XxtMEM=/3840x0/filters:quality(80)/images.kitchenstories.io/wagtailOriginalImages/R2958-final-photo-.jpg','🫛',0,0,0,'10 mins'),
    ('Yakitori Platter','Grilled chicken skewers basted with tare sauce — includes thigh, skin and tsukune meatballs.',399,'International Food','nonveg','Tokyo Garden',4.6,'https://encrypted-tbn0.gstatic.com/images?q=tbn:ANd9GcRLF3VKygTO9RWhEqdzNSYMyF6YRvtjw5kV8A&s','🍢',0,0,0,'22 mins'),
    ('Udon Noodle Soup','Thick wheat noodles in kombu-bonito broth with tempura prawn, narutomaki and nori.',379,'International Food','nonveg','Tokyo Garden',4.7,'https://sudachirecipes.com/wp-content/uploads/2025/02/beef-niku-udon-thumb.png','🍜',0,0,0,'20 mins'),
    ('Karaage Chicken','Japanese fried chicken marinated in soy, ginger and sake — juicy inside, crispy outside.',399,'International Food','nonveg','Tokyo Garden',4.8,'https://static01.nyt.com/images/2018/07/25/dining/HK-karaage-horizontal/merlin_141075300_74569dec-9fc2-4174-931d-019dddef3bb8-threeByTwoMediumAt2X.jpg','🍗',0,0,0,'20 mins'),
    ('Sashimi Platter','Premium sliced raw salmon, tuna, yellowtail and mackerel with pickled ginger and wasabi.',799,'International Food','nonveg','Tokyo Garden',4.9,'https://zushi.com.au/wp-content/uploads/2020/12/sashimi-platter-4-e1691215599768.jpg','🐟',0,1,0,'15 mins'),
    ('Matcha Ice Cream','Rich, earthy Japanese green tea ice cream with red bean paste and mochi pieces.',249,'International Food','veg','Tokyo Garden',4.7,'https://www.allrecipes.com/thmb/totJUia-TjrmF6VnYGHOM5hVjqQ=/1500x0/filters:no_upscale():max_bytes(150000):strip_icc()/241759-matcha-green-tea-ice-cream-VAT-003-4x3-01closeup-692d327cc2174abb84b440568f61e29a.jpg','🍦',0,0,0,'8 mins'),
    ('Takoyaki (6 pcs)','Crispy Osaka-style octopus balls topped with mayo, takoyaki sauce and dancing bonito flakes.',299,'International Food','nonveg','Tokyo Garden',4.6,'https://sakuracuisine.co.nz/wp-content/uploads/2021/10/Takoyaki-scaled.jpg','🐙',0,0,0,'18 mins'),
    ('Sushi Platter (12 pcs)','Chef selection of 12 premium nigiri and maki rolls with pickled ginger, wasabi and soy sauce.',699,'International Food','nonveg','Tokyo Garden',4.9,'https://www.sushiya.in/cdn/shop/files/823548NewProductimage_29.png?v=1764412776','🍱',0,1,0,'30 mins'),
    ('Ramen Bowl','Rich tonkotsu broth with hand-pulled noodles, chashu pork, soft-boiled marinated egg and nori.',449,'International Food','nonveg','Tokyo Garden',4.8,'https://www.elmundoeats.com/wp-content/uploads/2021/02/FP-Quick-30-minutes-chicken-ramen-500x500.jpg','🍜',0,0,1,'28 mins'),
    ('California Roll (8 pcs)','Inside-out roll with imitation crab, avocado and cucumber, rolled in sesame seeds.',349,'International Food','nonveg','Tokyo Garden',4.6,'https://images.squarespace-cdn.com/content/v1/5021287084ae954efd31e9f4/1585721783314-R7SO7BPEFD9E6SVGNW7I/California+Roll+4.jpg?format=1000w','🍣',0,0,0,'15 mins'),
    ('Green Curry','Aromatic Thai green curry with chicken, Thai basil, bamboo shoots and coconut milk.',349,'International Food','nonveg','Bangkok Street',4.7,'https://cupfulofkale.com/wp-content/uploads/2020/01/Vegan-Thai-Green-Curry-with-Tofu-and-Vegetables.jpeg','🍲',1,0,1,'25 mins'),
    ('Mango Sticky Rice','Glutinous rice cooked in sweet coconut milk served with fresh ripe mango slices.',249,'International Food','veg','Bangkok Street',4.8,'https://asianinspirations.com.au/wp-content/uploads/2018/11/R00126_Mango-Sticky-Rice.jpg','🥭',0,0,0,'12 mins'),
    ('Som Tam Papaya Salad','Shredded green papaya with lime, fish sauce, palm sugar, chilli and roasted peanuts.',229,'International Food','veg','Bangkok Street',4.5,'https://www.allrecipes.com/thmb/dGUxVcAkDO91Cstmjdiux0cW-Ow=/1500x0/filters:no_upscale():max_bytes(150000):strip_icc()/Som-Tam-Malakor-Green-Papaya-Salad-2000-ec87b4dcd85041c991d11ec6a1ab5f30.jpg','🥗',1,0,0,'12 mins'),
    ('Massaman Curry','Mild, rich curry with beef, potato, peanuts and coconut milk — influenced by Persian cuisine.',379,'International Food','nonveg','Bangkok Street',4.7,'https://www.favfamilyrecipes.com/wp-content/uploads/2023/09/Massaman-chicken-curry.jpg','🥘',0,0,0,'28 mins'),
    ('Thai Spring Rolls (4 pcs)','Crispy fried rolls filled with glass noodles, tofu, carrot and cabbage with sweet chilli sauce.',229,'International Food','veg','Bangkok Street',4.5,'https://encrypted-tbn0.gstatic.com/images?q=tbn:ANd9GcTbKoNtsoCxmkWnmXy-fdcvV-Mxf88Iyx2OHg&s','🥚',0,0,0,'15 mins'),
    ('Khao Pad (Thai Fried Rice)','Wok-tossed jasmine rice with egg, garlic, soy sauce and your choice of chicken or prawn.',299,'International Food','nonveg','Bangkok Street',4.6,'https://khinskitchen.com/wp-content/uploads/2023/02/khao-pad-08.jpg','🍳',0,0,0,'18 mins'),
    ('Satay Chicken (6 pcs)','Grilled chicken skewers marinated in turmeric and coconut milk with creamy peanut sauce.',349,'International Food','nonveg','Bangkok Street',4.7,'https://static01.nyt.com/images/2025/02/13/multimedia/ND-Chicken-Satay-qbkg/ND-Chicken-Satay-qbkg-facebookJumbo.jpg','🍢',0,0,0,'20 mins'),
    ('Tom Kha Gai','Fragrant coconut milk soup with chicken, galangal, lemongrass and kaffir lime leaves.',299,'International Food','nonveg','Bangkok Street',4.6,'https://images.squarespace-cdn.com/content/v1/5ca2fa763a01c7000124feb1/8f76c8d0-00de-44e9-a5c0-0d8453dc485b/IMG_4981.jpg','🍵',0,0,0,'18 mins'),
    ('Pineapple Fried Rice','Wok-fried rice with fresh pineapple, cashews, raisins and prawns, served in a pineapple shell.',319,'International Food','nonveg','Bangkok Street',4.5,'https://encrypted-tbn0.gstatic.com/images?q=tbn:ANd9GcTL88wD_gXCZYtFa1SLhvQIv385VX4_nK9wjQ&s','🍍',0,0,0,'18 mins'),
    ('Thai Basil Chicken','Stir-fried minced chicken with fresh holy basil, garlic, chilli and oyster sauce. Served with rice.',349,'International Food','nonveg','Bangkok Street',4.8,'https://www.allrecipes.com/thmb/NimapCyPk8WQ1gcO-4J5Y6SQgLk=/1500x0/filters:no_upscale():max_bytes(150000):strip_icc()/257938-spicy-thai-basil-chicken-chef-john-4x3-84457b900e2e4ec5823e8ace55df7b34.jpg','🌿',1,0,1,'18 mins'),
    ('Pad See Ew','Wide rice noodles stir-fried with egg, Chinese broccoli and sweet dark soy sauce.',329,'International Food','nonveg','Bangkok Street',4.6,'https://multicarbs.com/wp-content/uploads/2024/11/IMG_2630MODIF_1-1060x1590.jpg.webp','🍜',0,0,0,'18 mins'),
    ('Red Curry with Tofu','Spicy red curry paste cooked with silken tofu, bamboo shoots and Thai basil in coconut milk.',329,'International Food','veg','Bangkok Street',4.5,'https://encrypted-tbn0.gstatic.com/images?q=tbn:ANd9GcTRNoEdmJNTV_CXC7QQgsTH_iFG6-diWr_gxQ&s','🍲',1,0,0,'22 mins'),
    ('Coconut Ice Cream','Creamy homemade coconut ice cream served in a coconut shell with jackfruit and peanuts.',199,'International Food','veg','Bangkok Street',4.6,'https://static.toiimg.com/thumb/84816777.cms?imgsize=196937&width=800&height=800','🥥',0,0,0,'8 mins'),
    ('Tom Yum Soup','Fiery Thai prawn soup with lemongrass, kaffir lime, galangal, mushrooms and chilli paste.',269,'International Food','nonveg','Bangkok Street',4.6,'https://encrypted-tbn0.gstatic.com/images?q=tbn:ANd9GcRotILKXvhbHorce-gM4JYIJe-r6ZhEDwTvdA&s','🍲',1,0,0,'18 mins'),
    ('Pad Thai Noodles','Stir-fried rice noodles with egg, tofu, shrimp, bean sprouts, lime and roasted peanuts.',329,'International Food','nonveg','Bangkok Street',4.6,'https://www.halfbakedharvest.com/wp-content/uploads/2020/02/Better-Than-Takeout-Garlic-Butter-Shrimp-Pad-Thai-1.jpg','🍜',1,0,0,'20 mins'),
    ('Bibimbap','Steamed rice topped with seasoned vegetables, gochujang paste and a fried egg in a stone bowl.',349,'International Food','veg','Seoul Kitchen',4.8,'https://eatlittlebird.com/wp-content/uploads/2024/11/bibimbap-4.jpg.webp','🍲',1,0,1,'22 mins'),
    ('Korean BBQ Chicken','Marinated chicken grilled with gochujang, soy, garlic and sesame. Served with banchan sides.',499,'International Food','nonveg','Seoul Kitchen',4.8,'https://twoplaidaprons.com/wp-content/uploads/2021/06/spicy-Korean-BBQ-chicken-rice-bowl-top-down-view-of-a-spicy-Korean-BBQ-chicken-bowl.jpg','🍗',1,0,1,'28 mins'),
    ('Tteokbokki','Chewy rice cakes in a fiery red gochujang sauce with fish cakes and boiled egg.',279,'International Food','veg','Seoul Kitchen',4.6,'https://images.immediate.co.uk/production/volatile/sites/2/2025/04/SweetSpicyTteokbokkipreview-ecf0187.jpg?quality=90&crop=5px,1020px,2658px,2414px&resize=708,643','🌶️',1,0,0,'18 mins'),
    ('Bulgogi','Thinly sliced marinated beef grilled with pear, soy, garlic and sesame oil. Korean BBQ classic.',549,'International Food','nonveg','Seoul Kitchen',4.8,'https://damndelicious.net/wp-content/uploads/2019/04/240124_DD_korean-beef-bulgogi_274.jpg','🥩',0,0,0,'25 mins'),
    ('Korean Fried Chicken','Double-fried ultra-crispy chicken glazed with soy-garlic or spicy gochujang sauce.',449,'International Food','nonveg','Seoul Kitchen',4.9,'https://www.allrecipes.com/thmb/DGDJfEQw4Zgi01b8mb48hzoyERA=/1500x0/filters:no_upscale():max_bytes(150000):strip_icc()/238844-KoreanFriedChicken-ddmfs-2x1-8801-3adf49ac00f748e3a14add8f8c11e168.jpg','🍗',1,0,1,'25 mins'),
    ('Kimchi Fried Rice','Wok-fried rice with fermented kimchi, sesame oil and gochugaru topped with a fried egg.',299,'International Food','veg','Seoul Kitchen',4.6,'https://static01.nyt.com/images/2021/01/17/dining/kimchi-rice/kimchi-rice-mediumSquareAt3X-v2.jpg','🍳',1,0,0,'15 mins'),
    ('Sundubu Jjigae','Spicy soft tofu stew with clams, pork and egg simmered in an anchovy broth. Served with rice.',329,'International Food','nonveg','Seoul Kitchen',4.7,'https://upload.wikimedia.org/wikipedia/commons/0/02/Sundubu-jjigae.jpg','🍲',1,0,0,'20 mins'),
    ('Gimbap (4 pcs)','Korean seaweed rice rolls with egg, ham, pickled radish and seasoned spinach.',249,'International Food','nonveg','Seoul Kitchen',4.5,'https://jajabakes.com/wp-content/uploads/2018/08/kimbap2.jpg','🍙',0,0,0,'15 mins'),
    ('Haemul Pajeon','Crispy Korean seafood and spring onion pancake with prawn, squid and a soy dipping sauce.',349,'International Food','nonveg','Seoul Kitchen',4.6,'https://encrypted-tbn0.gstatic.com/images?q=tbn:ANd9GcQxgaIh4pHOOljglfevQqDiZrtCnJHZEN3ctw&s','🧅',0,0,0,'20 mins'),
    ('Japchae','Glass noodles stir-fried with beef, spinach, carrot, onion and sesame in a sweet soy sauce.',329,'International Food','nonveg','Seoul Kitchen',4.7,'https://images.getrecipekit.com/20240228032059-andy-20cooks-20-20japchae.jpg?aspect_ratio=16:9&quality=90&','🍜',0,0,0,'22 mins'),
    ('Dakgalbi','Spicy stir-fried chicken with gochujang, sweet potato, cabbage and chewy rice cakes.',449,'International Food','nonveg','Seoul Kitchen',4.7,'https://encrypted-tbn0.gstatic.com/images?q=tbn:ANd9GcR3rLKQj8ck9MiaQe5SmxWNF6rcpV6qLhCzHQ&s','🍗',1,1,0,'25 mins'),
    ('Jajangmyeon','Thick wheat noodles topped with black bean paste sauce with pork and diced vegetables.',299,'International Food','nonveg','Seoul Kitchen',4.5,'https://encrypted-tbn0.gstatic.com/images?q=tbn:ANd9GcR80653ezzbHUOgdrLNp0-UkYShcwE6QPzErQ&s','🍝',0,0,0,'20 mins'),
    ('Doenjang Jjigae','Fermented soybean paste stew with tofu, zucchini, mushrooms and potato. Comfort food staple.',279,'International Food','veg','Seoul Kitchen',4.5,'https://encrypted-tbn0.gstatic.com/images?q=tbn:ANd9GcQPzt-abxFqIk-6Zm3Mpg3LQZD4QDKsVljlQA&s','🍲',0,0,0,'18 mins'),
    ('Bingsu (Shaved Ice)','Korean shaved ice dessert with sweet red bean, condensed milk, mochi and fresh fruit.',299,'International Food','veg','Seoul Kitchen',4.7,'https://kimchimari.com/wp-content/uploads/2016/06/Shaved-ice-dessert-bingsu-with-berries.jpg','🍧',0,0,0,'10 mins'),
    ('Samgyeopsal (Pork Belly)','Thick sliced pork belly grilled at your table with garlic, kimchi and dipping sauces.',599,'International Food','nonveg','Seoul Kitchen',4.8,'https://thesubversivetable.com/wp-content/uploads/2024/05/Samgyeopsal-Gui-retake-16-500x500.jpg','🥓',0,1,0,'25 mins'),
    ('Burrito Bowl','Cilantro-lime rice with seasoned chicken, black beans, pico, guacamole and sour cream.',379,'International Food','nonveg','Mexican Fiesta',4.7,'https://encrypted-tbn0.gstatic.com/images?q=tbn:ANd9GcR2rGI1WaPBP3C4ShDWp3y0H-umPtWyDZXWng&s','🌯',1,0,1,'18 mins'),
    ('Quesadilla','Crispy flour tortilla stuffed with melted cheese, grilled chicken and peppers. Served with salsa.',299,'International Food','nonveg','Mexican Fiesta',4.6,'https://www.julieseatsandtreats.com/wp-content/uploads/2024/10/Chicken-Quesadilla-Square.jpg','🫓',0,0,0,'15 mins'),
    ('Enchiladas Verdes','Corn tortillas filled with chicken, rolled and smothered in tangy tomatillo salsa and cream.',349,'International Food','nonveg','Mexican Fiesta',4.6,'https://hips.hearstapps.com/hmg-prod/images/enchiladas-verdes-recipe-2-1659537049.jpg?crop=0.6666666666666667xw:1xh;center,top&resize=1200:*','🌮',1,0,0,'22 mins'),
    ('Churros with Chocolate','Crispy fried dough sticks rolled in cinnamon sugar, served with rich dark chocolate dipping sauce.',229,'International Food','veg','Mexican Fiesta',4.8,'https://assets.bonappetit.com/photos/58ff5f162278cd3dbd2c069c/1:1/w_2560%2Cc_limit/churros.jpg','🍩',0,0,0,'15 mins'),
    ('Guacamole & Chips','Fresh Hass avocado mashed with lime, cilantro, jalapeño and onion. Served with tortilla chips.',249,'International Food','veg','Mexican Fiesta',4.7,'https://recipecontent.fooby.ch/11662_10-9_480-432@2x.jpg','🥑',0,0,0,'10 mins'),
    ('Chicken Fajitas','Sizzling grilled chicken with bell peppers and onions. Served with warm tortillas and condiments.',399,'International Food','nonveg','Mexican Fiesta',4.7,'https://i2.wp.com/www.downshiftology.com/wp-content/uploads/2020/02/Chicken-Fajitas-main.jpg','🫕',1,0,0,'22 mins'),
    ('Chiles Rellenos','Roasted poblano peppers stuffed with cheese, dipped in egg batter and fried in tomato sauce.',369,'International Food','veg','Mexican Fiesta',4.5,'https://encrypted-tbn0.gstatic.com/images?q=tbn:ANd9GcSScm23-eyyGisltAxGb9VJdcqeNX__7JXpVw&s','🫑',1,0,0,'25 mins'),
    ('Tamales (2 pcs)','Steamed corn masa dough filled with spiced pork and salsa, wrapped in corn husks.',329,'International Food','nonveg','Mexican Fiesta',4.5,'https://www.pittmandavis.com/images/xl/PD25-Tamales.webp?v=4','🌽',0,0,0,'20 mins'),
    ('Tostadas','Crispy flat tortillas topped with refried beans, shredded chicken, lettuce, crema and cheese.',269,'International Food','nonveg','Mexican Fiesta',4.5,'https://encrypted-tbn0.gstatic.com/images?q=tbn:ANd9GcQu44Kn-UUzQAL-_oiumdRlGuuYqWf0naVprQ&s','🥙',0,0,0,'15 mins'),
    ('Tres Leches Cake','Light sponge cake soaked in three milks (whole, condensed, evaporated) with whipped cream.',249,'International Food','veg','Mexican Fiesta',4.8,'https://www.allrecipes.com/thmb/3zjqR0J3EYdaRwZ97AQAZoUSC5o=/1500x0/filters:no_upscale():max_bytes(150000):strip_icc()/7399-tres-leches-milk-cake-ddmfs-beauty-2x1-BG-25702-f42c94b10c914753aa4dcb413658b8bf.jpg','🎂',0,0,0,'10 mins'),
    ('Elote (Mexican Corn)','Grilled corn on the cob slathered with mayo, cotija cheese, chilli powder and lime juice.',199,'International Food','veg','Mexican Fiesta',4.6,'https://www.averiecooks.com/wp-content/uploads/2018/07/elote-6.jpg','🌽',1,0,0,'12 mins'),
    ('Tacos (3 pcs)','Three corn tortillas with spiced chicken al pastor, salsa verde, pickled onion and cotija cheese.',299,'International Food','nonveg','Mexican Fiesta',4.6,'https://d1ralsognjng37.cloudfront.net/40f3de0e-8247-4132-a39d-eebbc43cc94c.jpeg','🌮',1,1,0,'18 mins'),
    ('Nachos Supreme','Crispy chips with nacho cheese, jalapeños, sour cream, guacamole and pico de gallo.',319,'International Food','veg','Mexican Fiesta',4.5,'https://thefoodiebunch.sfo3.digitaloceanspaces.com/wp-content/uploads/2024/12/12175046/Loaded-Nachos-Supreme.png','🧀',1,0,0,'15 mins'),
    ('Pozole Rojo','Traditional Mexican hominy stew with pork, dried chillies, oregano and fresh garnishes.',299,'International Food','nonveg','Mexican Fiesta',4.6,'https://static.wixstatic.com/media/d6fe55_16179d1f19314cf2b8f9d2a892edf3de~mv2.png/v1/fill/w_1000,h_1000,al_c,q_90,usm_0.66_1.00_0.01/d6fe55_16179d1f19314cf2b8f9d2a892edf3de~mv2.png','🍲',1,0,0,'25 mins'),
    ('Mexican Rice Bowl','Tomato-herb rice with black beans, corn, pico de gallo and avocado slices.',279,'International Food','veg','Mexican Fiesta',4.4,'https://www.hintofhealthy.com/wp-content/uploads/2022/01/Mexican-Rice-Bowl.jpg','🍚',0,0,0,'15 mins'),
    ('Nasi Lemak','Malaysia national dish — coconut rice with sambal, fried anchovies, peanuts, egg and cucumber.',299,'International Food','nonveg','Mamak Corner',4.8,'https://upload.wikimedia.org/wikipedia/commons/thumb/5/55/Nasi_Lemak_dengan_Chili_Nasi_Lemak_dan_Sotong_Pedas%2C_di_Penang_Summer_Restaurant.jpg/250px-Nasi_Lemak_dengan_Chili_Nasi_Lemak_dan_Sotong_Pedas%2C_di_Penang_Summer_Restaurant.jpg','🍚',1,0,1,'20 mins'),
    ('Char Kway Teow','Stir-fried flat rice noodles with prawns, bean sprouts, egg and Chinese sausage over high flame.',329,'International Food','nonveg','Mamak Corner',4.7,'https://www.curiousnut.com/wp-content/uploads/2015/11/Char-Kway-Teow-Feat-T.jpg','🍜',1,0,0,'18 mins'),
    ('Laksa','Spicy coconut curry noodle soup with prawns, fish cake, tofu puffs and laksa leaves.',349,'International Food','nonveg','Mamak Corner',4.8,'https://woonheng.com/wp-content/uploads/2020/10/Curry-Laksa-scaled.jpg','🍲',1,0,1,'22 mins'),
    ('Roti Canai','Flaky, crispy layered flatbread served with dal curry and coconut chutney. Malaysian street staple.',149,'International Food','veg','Mamak Corner',4.6,'https://delishglobe.com/wp-content/uploads/2025/04/Roti-Canai.png','🫓',0,0,0,'12 mins'),
    ('Mee Goreng Mamak','Indian-influenced fried yellow noodles with prawn, tofu, egg and a tangy tomato-based sauce.',279,'International Food','nonveg','Mamak Corner',4.6,'https://encrypted-tbn0.gstatic.com/images?q=tbn:ANd9GcTFCAPb-5MhFao3w-G3ePlZ5b6xxiA_VvaRqg&s','🍝',1,0,0,'18 mins'),
    ('Rendang Chicken','Slow-cooked dry curry with chicken in coconut milk, lemongrass and complex spice paste.',399,'International Food','nonveg','Mamak Corner',4.7,'https://rasamalaysia.com/wp-content/uploads/2016/03/chicken-rendang-thumb.jpg','🍗',1,0,0,'35 mins'),
    ('Satay Platter (8 pcs)','Charcoal-grilled chicken and beef skewers with peanut sauce, compressed rice and cucumber.',349,'International Food','nonveg','Mamak Corner',4.7,'https://encrypted-tbn0.gstatic.com/images?q=tbn:ANd9GcT5Bh-a59MrRHBVTa1tmiDjBybgur-lGnZ8dw&s','🍢',0,0,0,'20 mins'),
    ('Hainanese Chicken Rice','Poached chicken with fragrant ginger-garlic rice, chilli sauce and dark soy. Comfort classic.',299,'International Food','nonveg','Mamak Corner',4.8,'https://onehappybite.com/wp-content/uploads/2025/04/DSC05821-2.jpg','🍗',0,0,0,'25 mins'),
    ('Cendol','Shaved ice dessert with green pandan jelly, red bean, coconut milk and palm sugar syrup.',149,'International Food','veg','Mamak Corner',4.7,'https://upload.wikimedia.org/wikipedia/commons/thumb/8/86/Kampung_Paya_Jaras_Tengah%2C_Selangor_20250112_111330.jpg/1280px-Kampung_Paya_Jaras_Tengah%2C_Selangor_20250112_111330.jpg','🍧',0,0,0,'8 mins'),
    ('Teh Tarik','Malaysia favourite pulled tea — condensed milk tea poured from height to create a frothy top.',99,'International Food','veg','Mamak Corner',4.8,'https://woonheng.com/wp-content/uploads/2021/05/Teh-Tarik-1-e1621309599790.jpg','☕',0,0,0,'8 mins'),
    ('Nasi Goreng','Malaysian fried rice with shrimp paste, egg, chicken and crispy shallots. Served with prawn crackers.',279,'International Food','nonveg','Mamak Corner',4.6,'https://www.andy-cooks.com/cdn/shop/articles/20240903050510-andy-20cooks-20-20nasi-20goreng-20recipe.jpg?v=1725927823','🍳',1,0,0,'18 mins'),
    ('Assam Pedas Fish','Tangy tamarind fish curry with lady fingers, tomatoes and torch ginger flower. Nyonya classic.',449,'International Food','nonveg','Mamak Corner',4.7,'https://rasamalaysia.com/wp-content/uploads/2007/01/asam-pedas-thumb.jpg','🐟',1,1,0,'28 mins'),
    ('Popiah (Spring Roll)','Soft fresh spring rolls filled with jicama, carrot, egg, prawn and sweet-spicy sauce.',199,'International Food','veg','Mamak Corner',4.5,'https://encrypted-tbn0.gstatic.com/images?q=tbn:ANd9GcRuf7SiIMzjctLCV-k58JkTbxnsXbT9ZcKRmg&s','🥗',0,0,0,'15 mins'),
    ('Otak-Otak','Spiced fish paste grilled in banana leaf with coconut milk, galangal and kaffir lime.',249,'International Food','nonveg','Mamak Corner',4.6,'https://nomadette.com/wp-content/uploads/2025/01/Authentic-Otak-otak.jpg','🐟',1,0,0,'18 mins'),
    ('Banana Leaf Rice','Basmati rice on banana leaf with rasam, sambar, 3 curries, pickles and papadum.',329,'International Food','nonveg','Mamak Corner',4.7,'https://cdn.tatlerasia.com/asiatatler/i/my/2018/11/06142637-story-image-81638_cover_650x357.jpg','🍃',0,0,0,'20 mins'),
    ('Bratwurst & Sauerkraut','Grilled pork bratwurst sausages with fermented cabbage, mustard and fresh bread roll.',449,'International Food','nonveg','Berlin Bites',4.7,'https://food.fnr.sndimg.com/content/dam/images/food/fullset/2011/11/4/1/CCMPT231_Bratwurst-Stewed-with-Sauerkraut_s4x3.jpg.rend.hgtvcom.1280.960.suffix/1382540721963.webp','🌭',0,0,1,'20 mins'),
    ('Pork Schnitzel','Thinly pounded pork breaded and fried golden — served with lemon, potato salad and lingonberry.',549,'International Food','nonveg','Berlin Bites',4.8,'https://www.allrecipes.com/thmb/bu4s12dq2GNt-kgi9R8sZTrhQYo=/1500x0/filters:no_upscale():max_bytes(150000):strip_icc()/Pork-Schnitzel-ddmfs-3x2-113-7c044e725d604cb0b2a3827b63a7f6f6.jpg','🥩',0,0,1,'25 mins'),
    ('Pretzels & Beer Cheese','Warm soft Bavarian pretzels with coarse salt served with tangy beer-infused cheese dip.',229,'International Food','veg','Berlin Bites',4.6,'https://www.foxandbriar.com/wp-content/uploads/2016/11/Soft-Beer-Pretzels-with-Beer-Cheese-Dip-20-of-23.jpg','🥨',0,0,0,'10 mins'),
    ('Black Forest Cake','Layers of chocolate sponge, Kirsch-soaked cherries and fresh whipped cream. German classic.',329,'International Food','veg','Berlin Bites',4.9,'https://ashbaber.com/wp-content/uploads/2025/05/Black-forest-cake-slice-small.jpg','🎂',0,0,1,'10 mins'),
    ('Beef Rouladen','Thinly sliced beef rolled with mustard, bacon, onion and pickle then braised in red wine gravy.',649,'International Food','nonveg','Berlin Bites',4.7,'https://www.foodandwine.com/thmb/OCw6mKaZwZgF0kCTW4ZLf8gHCTY=/1500x0/filters:no_upscale():max_bytes(150000):strip_icc()/Rouladen-FT-RECIPE0524-4fc8ae2272f74939887d51be6dbcf4fb.jpg','🥩',0,0,0,'40 mins'),
    ('Kartoffelsalat','Bavarian-style warm potato salad with vinegar, mustard, bacon lardons and fresh chives.',249,'International Food','veg','Berlin Bites',4.4,'https://encrypted-tbn0.gstatic.com/images?q=tbn:ANd9GcTf03vfMyDpEMLvjfOfg_lFv4e3f6rsY8mZ8w&s','🥔',0,0,0,'15 mins'),
    ('Currywurst','Berlin street food icon — sliced pork sausage in curried tomato ketchup with crispy fries.',349,'International Food','nonveg','Berlin Bites',4.6,'https://i.imgur.com/vHcVG15.jpeg','🌭',1,0,0,'15 mins'),
    ('Käsespätzle','German egg noodles baked with Emmental cheese and topped with crispy fried onions.',399,'International Food','veg','Berlin Bites',4.7,'https://encrypted-tbn0.gstatic.com/images?q=tbn:ANd9GcRArMkXEd1S8G_UpehL-Wk67x4SDEP7fJ9cHQ&s','🍝',0,0,0,'22 mins'),
    ('Sauerbraten','German pot roast — beef marinated for days in red wine vinegar then slow-braised in rich gravy.',649,'International Food','nonveg','Berlin Bites',4.6,'https://encrypted-tbn0.gstatic.com/images?q=tbn:ANd9GcRto4T50tEEPyEr_Cj7jNGgELYUQfUvzwgzWQ&s','🥩',0,1,0,'45 mins'),
    ('Flammkuchen','Alsatian tarte flambée — crispy thin crust with crème fraîche, onions and smoked lardons.',349,'International Food','nonveg','Berlin Bites',4.6,'https://api.flavournetwork.ca/wp-content/uploads/2023/01/flammkuchen-feat.jpg?w=3840&quality=75','🍕',0,0,0,'18 mins'),
    ('Apfelstrudel','Flaky pastry rolled with cinnamon-spiced apples, raisins and breadcrumbs. Served warm with cream.',279,'International Food','veg','Berlin Bites',4.8,'https://spoonuniversity.com/cdn-cgi/image/width=2173,height=2174,fit=cover,format=auto/wp-content/uploads/2024/10/Apfelstrudel-Apple-Strudel-with-Vanilla-Sauce-evening-sun.jpg','🥐',0,0,0,'10 mins'),
    ('Maultaschen','Swabian pasta parcels filled with pork, spinach and herbs, served in broth or pan-fried.',449,'International Food','nonveg','Berlin Bites',4.5,'https://tarasmulticulturaltable.com/wp-content/uploads/2013/03/Schwabische-Maultaschen-German-Pork-and-Spinach-Dumplings-13-of-13-500x375.jpg','🥟',0,0,0,'22 mins'),
    ('Weißwurst','Bavarian white veal sausage poached in water, served with sweet mustard and soft pretzel.',399,'International Food','nonveg','Berlin Bites',4.5,'https://encrypted-tbn0.gstatic.com/images?q=tbn:ANd9GcTjXcnebm514wYC1YYaVyv0ZDl1AIIaZlTgZQ&s','🌭',0,0,0,'15 mins'),
    ('German Potato Soup','Hearty Kartoffelsuppe with diced potatoes, leek, celery, smoked sausage and marjoram.',249,'International Food','nonveg','Berlin Bites',4.5,'https://images.services.kitchenstories.io/yujxueSJ20A9OKkzjFeDFMXcT5I=/3840x0/filters:quality(80)/images.kitchenstories.io/wagtailOriginalImages/R1787-final-photo-1.jpg','🍲',0,0,0,'22 mins'),
    ('Lebkuchen','Traditional German gingerbread cookies with spices, nuts and chocolate glaze. 6-piece pack.',299,'International Food','veg','Berlin Bites',4.6,'https://www.telegraph.co.uk/multimedia/archive/02416/LEBKUCHEN_2416570b.jpg','🍪',0,0,0,'5 mins'),
    ('Moussaka','Layered aubergine and minced lamb bake topped with thick béchamel sauce and nutmeg.',449,'International Food','nonveg','Mediterranean Blue',4.8,'https://encrypted-tbn0.gstatic.com/images?q=tbn:ANd9GcSLM3UNbSRYpRPH9ZgbUMiEdgftogXwS3Yvkg&s','🫕',0,0,1,'30 mins'),
    ('Souvlaki (4 pcs)','Marinated pork skewers grilled over charcoal with lemon, oregano and olive oil.',399,'International Food','nonveg','Mediterranean Blue',4.7,'https://encrypted-tbn0.gstatic.com/images?q=tbn:ANd9GcQfG1ZU9LanzPO0y8mx-nL9mDCHCURHX09tqg&s','🍢',0,0,0,'22 mins'),
    ('Spanakopita','Crispy filo pastry pie filled with spinach, feta cheese, onion, egg and fresh dill.',299,'International Food','veg','Mediterranean Blue',4.6,'https://www.allrecipes.com/thmb/Xes_ky5_0MJ7JNMp5fzHkoH2y0Y=/1500x0/filters:no_upscale():max_bytes(150000):strip_icc()/18417-spanakopita-greek-spinach-pie-DDMFS-Hero-2x1-24958-1-d1f1939a110d41aca9ff456feb0f8eb9.jpg','🥬',0,0,0,'20 mins'),
    ('Gyros Wrap','Slow-cooked pork or chicken with tzatziki, tomato, onion and fries in warm pita bread.',349,'International Food','nonveg','Mediterranean Blue',4.7,'https://encrypted-tbn0.gstatic.com/images?q=tbn:ANd9GcQnpQvgCqRp79UbdsdJWmFFybCvoY3-MuzFKw&s','🌯',0,0,0,'18 mins'),
    ('Tzatziki & Pita','Thick Greek yogurt dip with cucumber, garlic, dill and olive oil. Served with warm pita bread.',199,'International Food','veg','Mediterranean Blue',4.6,'https://www.foodnetwork.com/content/dam/images/food/fullset/2018/6/25/0/FN_Ina-Garten-Tzatsiki-Toasted-Pita-Chips-H1_s4x3.jpg','🫙',0,0,0,'10 mins'),
    ('Lamb Kleftiko','Slow-roasted lamb sealed in foil with lemon, garlic, potatoes and oregano. Meltingly tender.',699,'International Food','nonveg','Mediterranean Blue',4.8,'https://i0.wp.com/elenisaltas.com/wp-content/uploads/2018/11/DSC_0701.jpg?fit=1920%2C1272&ssl=1','🦴',0,1,0,'45 mins'),
    ('Feta Saganaki','Pan-fried feta slab with a crispy crust, drizzled with honey and sprinkled with sesame seeds.',299,'International Food','veg','Mediterranean Blue',4.7,'https://encrypted-tbn0.gstatic.com/images?q=tbn:ANd9GcTG3WoRB6MW0L9PUjmVnPVYAAwKVjhX5SJsug&s','🧀',0,0,0,'12 mins'),
    ('Dolmades (6 pcs)','Vine leaves stuffed with herbed rice, pine nuts and currants. Served with lemon wedges.',279,'International Food','veg','Mediterranean Blue',4.5,'https://encrypted-tbn0.gstatic.com/images?q=tbn:ANd9GcRKxl5lu0QCKh5USx00wA2ZgpQRJpFcA1toTw&s','🌿',0,0,0,'15 mins'),
    ('Grilled Octopus','Chargrilled Mediterranean octopus with capers, red onion, olive oil and red wine vinegar.',749,'International Food','nonveg','Mediterranean Blue',4.8,'https://encrypted-tbn0.gstatic.com/images?q=tbn:ANd9GcTPOknJXoYUfhuaPT4etHEppnGid9Dg_ncaQQ&s','🐙',0,0,0,'30 mins'),
    ('Baklava','Layers of crispy filo pastry with chopped walnuts, soaked in honey and orange blossom syrup.',249,'International Food','veg','Mediterranean Blue',4.8,'https://encrypted-tbn0.gstatic.com/images?q=tbn:ANd9GcTqcXBktNsIimO0afpqZTFfKzsZaqzk-5FHsQ&s','🍯',0,0,0,'8 mins'),
    ('Greek Salad','Crisp cucumber, ripe tomatoes, Kalamata olives, red onion and creamy feta with oregano dressing.',249,'International Food','veg','Mediterranean Blue',4.5,'https://ichef.bbci.co.uk/food/ic/food_16x9_1600/recipes/greek_salad_16407_16x9.jpg','🥗',0,0,0,'10 mins'),
    ('Galaktoboureko','Crispy filo custard pie with semolina cream filling, drenched in fragrant syrup.',279,'International Food','veg','Mediterranean Blue',4.7,'https://encrypted-tbn0.gstatic.com/images?q=tbn:ANd9GcRwv5RWrYehIxx4iRW0enG9PHGXEi2WgNR3Lg&s','🍮',0,0,0,'10 mins'),
    ('Pastitsio','Greek baked pasta with spiced beef mince and béchamel sauce — the Greek lasagna.',399,'International Food','nonveg','Mediterranean Blue',4.6,'https://www.allrecipes.com/thmb/DqBtUTwo7O0dtCNKTRsFmtkovWs=/1500x0/filters:no_upscale():max_bytes(150000):strip_icc()/23159-pastitsio-mfs-4x3-9e683d6267b4426c9cafface4f22b688.jpg','🫕',0,0,0,'28 mins'),
    ('Loukoumades','Crispy Greek honey doughnuts dusted with cinnamon and crushed walnuts. 6-piece serving.',229,'International Food','veg','Mediterranean Blue',4.7,'https://delishglobe.com/wp-content/uploads/2024/11/Loukoumades-Greek-Honey-Doughnuts.png','🍩',0,0,0,'12 mins'),
    ('Horiatiki Salad','Village salad with large-cut tomato, cucumber, green pepper, olives and a slab of feta.',269,'International Food','veg','Mediterranean Blue',4.5,'https://www.seriouseats.com/thmb/snej3Ib6cSrdjm_HgXQ9qt-C-2Q=/1500x0/filters:no_upscale():max_bytes(150000):strip_icc()/__opt__aboutcom__coeus__resources__content_migration__serious_eats__seriouseats.com__recipes__images__2017__08__20170814-greek-salad-vicky-wasik-8-84d7b60421bc47df8f5292ca3ffddd6f.jpg','🥗',0,0,0,'10 mins'),
    ('Hummus & Pita','Silky smooth chickpea dip with tahini, lemon and olive oil. Served with warm pita triangles.',199,'International Food','veg','Arabian Nights',4.8,'https://www.electroluxarabia.com/globalassets/elux-arabia/inspiration/recipe/hummus-with-pita-bread_x3rl.jpg','🫙',0,0,1,'10 mins'),
    ('Kibbeh (4 pcs)','Crispy bulgur wheat shells filled with spiced lamb, pine nuts and onion. Lebanon national dish.',349,'International Food','nonveg','Arabian Nights',4.7,'https://encrypted-tbn0.gstatic.com/images?q=tbn:ANd9GcRadkeX4HWR-WFuzkrZVxQEiLNhSGfrHN3Tjg&s','🥩',0,0,0,'20 mins'),
    ('Fattoush Salad','Crispy toasted pita with mixed greens, tomato, radish, sumac dressing and pomegranate.',229,'International Food','veg','Arabian Nights',4.5,'https://media.chefdehome.com/740/0/0/fattoush/fattoush-salad-recipe.jpg','🥗',0,0,0,'12 mins'),
    ('Mixed Mezze Platter','Hummus, baba ganoush, labneh, olives, tabbouleh and warm pita — perfect for sharing.',449,'International Food','veg','Arabian Nights',4.8,'https://www.simplyrecipes.com/thmb/qf6TaQLIC6hjm97QGhO3yuS5iZ8=/1500x0/filters:no_upscale():max_bytes(150000):strip_icc()/__opt__aboutcom__coeus__resources__content_migration__simply_recipes__uploads__2019__12__Mezze-Platter-LEAD-04-5850a1457fd845cc97d47b87cffe09bd.jpg','🍽️',0,0,1,'15 mins'),
    ('Chicken Kafta','Minced chicken mixed with parsley, onion and spices, skewered and grilled over charcoal.',379,'International Food','nonveg','Arabian Nights',4.7,'https://www.simplyleb.com/wp-content/uploads/Chicken-Kafta-13.jpg','🍢',0,0,0,'22 mins'),
    ('Tabbouleh','Fresh herb salad with fine bulgur, abundant parsley, mint, tomato and lemon-olive oil dressing.',199,'International Food','veg','Arabian Nights',4.6,'https://i2.wp.com/colorfulrecipes.com/wp-content/uploads/2012/11/fresh-light-authentic-lebanese-tabbouleh-6.jpg?resize=1800%2C1800','🌿',0,0,0,'10 mins'),
    ('Lebanese Lentil Soup','Creamy red lentil soup with cumin, turmeric and a drizzle of olive oil. Served with lemon.',229,'International Food','veg','Arabian Nights',4.5,'https://www.sweetandsavourypursuits.com/wp-content/uploads/2023/03/Lebanese-Red-Lentil-Soup-1200x1200-1.jpg','🍲',0,0,0,'18 mins'),
    ('Manakish Za\'atar','Lebanese flatbread baked with za\'atar herb mix, sesame seeds and generous olive oil.',279,'International Food','veg','Arabian Nights',4.7,'https://encrypted-tbn0.gstatic.com/images?q=tbn:ANd9GcQLqSRh7kJRV0ucplWpYeeQkDsMGIHlWeqLUg&s','🫓',0,0,0,'18 mins'),
    ('Fatayer (3 pcs)','Baked pastry triangles filled with spinach, sumac, onion and pine nuts.',249,'International Food','veg','Arabian Nights',4.5,'https://tapcom-live.ams3.cdn.digitaloceanspaces.com/media/healthy-feast/products/mix-fatayer-3-pcs-FATAYER6961.jpg','🥟',0,0,0,'18 mins'),
    ('Riz a Djej','Lebanese spiced rice with slow-cooked chicken, vermicelli, cinnamon and roasted nuts.',329,'International Food','nonveg','Arabian Nights',4.6,'https://encrypted-tbn0.gstatic.com/images?q=tbn:ANd9GcToAW97axKddjYLDtDHZwuvWryxIWW9L02GtA&s','🍗',0,0,0,'25 mins'),
    ('Knafeh','Warm shredded pastry filled with gooey melted cheese, soaked in rose water syrup.',299,'International Food','veg','Arabian Nights',4.9,'https://static1.squarespace.com/static/56ca92b82e83f84324967441/t/5daf78417e11d179f151e3ea/1572913484669/knafeh.jpg?format=1500w','🍯',0,0,0,'12 mins'),
    ('Baba Ganoush','Smoky roasted aubergine dip with tahini, lemon, garlic and pomegranate seeds.',199,'International Food','veg','Arabian Nights',4.6,'https://static01.nyt.com/images/2024/02/13/multimedia/MRS-Baba-Ganoush-zkpq/MRS-Baba-Ganoush-zkpq-videoSixteenByNineJumbo1600.jpg','🍆',0,0,0,'10 mins'),
    ('Chicken Shawarma','Slow-roasted spiced chicken with garlic sauce, pickled vegetables and tahini in warm pita.',279,'International Food','nonveg','Arabian Nights',4.7,'https://www.allrecipes.com/thmb/DVmGoMWgprFFt5-NLogcbs3rpZ0=/1500x0/filters:no_upscale():max_bytes(150000):strip_icc()/52407-chicken-shawarma-VAT-001-2x1-dfb023c77cc24d57ab0e59ed8648bb0f.jpg','🌯',1,0,1,'18 mins'),
    ('Falafel Wrap','Crispy falafel with hummus, tabbouleh and pickled turnip wrapped in warm lavash.',229,'International Food','veg','Arabian Nights',4.5,'https://static.toiimg.com/thumb/62708678.cms?imgsize=156976&width=800&height=800','🧆',0,0,0,'15 mins'),
    ('Lebanese Baklava','Rose water-scented pistachio baklava layered in finest filo and soaked in amber sugar syrup.',249,'International Food','veg','Arabian Nights',4.8,'https://parade.com/.image/c_fill,g_faces:center/MjA1NTg1NjIyNzY3NzczNTk2/lebanese-baklava.jpg','🍬',0,0,0,'8 mins'),
    ('Croissant & Jam','Buttery, flaky all-butter croissant with strawberry jam and French butter. Freshly baked.',199,'International Food','veg','Café de Paris',4.7,'https://encrypted-tbn0.gstatic.com/images?q=tbn:ANd9GcSUmf5ZRzKIabAUmqyEiYyD4NoaUzkc9kpUhQ&s','🥐',0,0,0,'8 mins'),
    ('French Onion Soup','Caramelised onion broth topped with a crouton and bubbling gruyère cheese crust.',279,'International Food','veg','Café de Paris',4.7,'https://www.familyfoodonthetable.com/wp-content/uploads/2025/01/French-onion-soup-square-1200.jpg','🍲',0,0,0,'22 mins'),
    ('Beef Bourguignon','Slow-braised beef in Burgundy wine with pearl onions, mushrooms, lardons and thyme.',699,'International Food','nonveg','Café de Paris',4.9,'https://www.saveur.com/uploads/2014/03/photo_tristan-deBrauwere_food-styling_fatima-khamise_TD_2025_12_05_016.jpg?format=webp&optimize=high&precrop=1%3A1%2Csmart','🥩',0,0,1,'45 mins'),
    ('Crêpe Suzette','Thin French crêpes in warm orange liqueur butter sauce, flambéed at the table.',299,'International Food','veg','Café de Paris',4.8,'https://encrypted-tbn0.gstatic.com/images?q=tbn:ANd9GcQepUsP-X-Ia8odTrA02bTiEUX4doeYc2CgIQ&s','🥞',0,0,0,'15 mins'),
    ('Quiche Lorraine','Buttery shortcrust pastry tart filled with bacon lardons, egg and cream custard.',349,'International Food','nonveg','Café de Paris',4.6,'https://pekis.net/sites/default/files/styles/325x325/public/2025-02/Quiche%20Lorraine.jpg?itok=7fGt09Ox','🥧',0,0,0,'18 mins'),
    ('Crème Brûlée','Classic vanilla custard topped with a perfectly caramelised crunchy toffee crust.',299,'International Food','veg','Café de Paris',4.9,'https://encrypted-tbn0.gstatic.com/images?q=tbn:ANd9GcTK4BcGTH3Wh-IpOrgdo2DxL5R8q3qQDcL7Og&s','🍮',0,0,1,'10 mins'),
    ('Ratatouille','Provençal oven-baked vegetable medley of courgette, aubergine, pepper and tomato with herbs.',329,'International Food','veg','Café de Paris',4.6,'https://encrypted-tbn0.gstatic.com/images?q=tbn:ANd9GcRdILRRK5eiv-tTurE4qtZDIDxskt0opPKz1g&s','🫕',0,0,0,'25 mins'),
    ('Duck Confit','Duck leg slow-cooked in its own fat until meltingly tender, served with lentils and crispy skin.',749,'International Food','nonveg','Café de Paris',4.8,'https://static01.nyt.com/images/2014/04/01/dining/duck-confit/duck-confit-superJumbo.jpg','🦆',0,1,0,'35 mins'),
    ('Niçoise Salad','Classic salad with tuna, green beans, olives, egg, cherry tomatoes and anchovy dressing.',299,'International Food','nonveg','Café de Paris',4.6,'https://www.allrecipes.com/thmb/i1395ATnYa-0YyrJi962rgUqpaM=/1500x0/filters:no_upscale():max_bytes(150000):strip_icc()/ALR-recipe-14239-salad-nicoise-hero-01-ddmfs-4x3-21eceb81fd1043888fffbada1e0acb9b.jpg','🥗',0,0,0,'12 mins'),
    ('Chocolate Fondant','Warm dark chocolate lava cake with a molten centre, served with vanilla bean ice cream.',329,'International Food','veg','Café de Paris',4.9,'https://encrypted-tbn0.gstatic.com/images?q=tbn:ANd9GcSJ_VFuXymx3yE8g9zTuPbJXECiQhZZrLhX9A&s','🍫',0,0,1,'15 mins'),
    ('Macarons (6 pcs)','Six delicate almond meringue shells with ganache or buttercream — assorted French flavours.',399,'International Food','veg','Café de Paris',4.8,'https://www.fnp.com/images/pr/new-zealand/l/v20220127170921/assorted-macarons-6-pcs_1.jpg','🍪',0,0,0,'8 mins'),
    ('Bouillabaisse','Marseille fish stew with mixed seafood, saffron, fennel and rouille on crusty bread.',649,'International Food','nonveg','Café de Paris',4.8,'https://encrypted-tbn0.gstatic.com/images?q=tbn:ANd9GcRqPAnMW7xOXOE2S7JPTEaZzb6wDmNPx90PLA&s','🦞',0,0,0,'35 mins'),
    ('Tarte Tatin','Upside-down caramelised apple tart with buttery puff pastry. Served warm with crème fraîche.',299,'International Food','veg','Café de Paris',4.7,'https://encrypted-tbn0.gstatic.com/images?q=tbn:ANd9GcTZZV-a_MY3o-WrXFFocZfsaw4ZpBSdqWvSog&s','🥧',0,0,0,'15 mins'),
    ('Soufflé au Fromage','Classic baked French cheese soufflé, light as air with Gruyère and a hint of nutmeg.',349,'International Food','veg','Café de Paris',4.7,'https://encrypted-tbn0.gstatic.com/images?q=tbn:ANd9GcSnIEMABo5IyV8JFyqTi9Jc-DbG4lRkeTL6tQ&s','🧁',0,1,0,'25 mins'),
    ('Escargot au Beurre','Classic Burgundy snails baked in garlic-parsley butter in individual shells. Served with French bread.',499,'International Food','nonveg','Café de Paris',4.6,'https://encrypted-tbn0.gstatic.com/images?q=tbn:ANd9GcRC6oonw8m-1A7h47tgs9QUzrCWnXrjMDCjog&s','🐌',0,0,0,'20 mins'),
]

# ═══════════════════════════════════════════════════════════════
#  DB HELPERS  (psycopg2 / Supabase PostgreSQL)
# ═══════════════════════════════════════════════════════════════
def get_db():
    if "db" not in g:
        g.db = psycopg2.connect(
            SUPABASE_DB_URL,
            cursor_factory=psycopg2.extras.RealDictCursor,
        )
    return g.db

def q1(sql, p=()):
    conn = get_db(); cur = conn.cursor()
    cur.execute(_to_pg(sql), p)
    row = cur.fetchone(); cur.close()
    return dict(row) if row else None

def qa(sql, p=()):
    conn = get_db(); cur = conn.cursor()
    cur.execute(_to_pg(sql), p)
    rows = cur.fetchall(); cur.close()
    return [dict(r) for r in rows]

def run(sql, p=()):
    conn = get_db(); cur = conn.cursor()
    pg_sql = _to_pg(sql)
    is_insert = pg_sql.strip().upper().startswith("INSERT")
    if is_insert and "RETURNING" not in pg_sql.upper():
        pg_sql += " RETURNING id"
    cur.execute(pg_sql, p); conn.commit()
    last_id = None
    if is_insert:
        row = cur.fetchone()
        if row:
            last_id = row["id"] if isinstance(row, dict) else row[0]
    cur.close()
    return last_id

def log_action(action, details=""):
    ip = request.remote_addr or "unknown"
    try:
        run("INSERT INTO activity_log(action,details,ip) VALUES(?,?,?)", (action, details, ip))
    except: pass

# ═══════════════════════════════════════════════════════════════
#  PASSWORD & JWT
# ═══════════════════════════════════════════════════════════════
def hash_pw(plain):
    salt = os.urandom(16)
    dk   = hashlib.pbkdf2_hmac("sha256", plain.encode(), salt, PBKDF2_ITERS)
    return salt.hex() + "$" + dk.hex()

def check_pw(plain, stored):
    try: salt_hex, hash_hex = stored.split("$", 1)
    except: return False
    dk = hashlib.pbkdf2_hmac("sha256", plain.encode(), bytes.fromhex(salt_hex), PBKDF2_ITERS)
    return hmac.compare_digest(dk.hex(), hash_hex)

def make_token(uid, email):
    return jwt.encode({"user_id": uid, "email": email,
        "exp": datetime.now(timezone.utc) + timedelta(days=JWT_EXPIRY_DAYS),
        "iat": datetime.now(timezone.utc)}, SECRET_KEY, algorithm="HS256")

def read_token(tok):
    try: return jwt.decode(tok, SECRET_KEY, algorithms=["HS256"])
    except: return None

def jwt_required(f):
    @functools.wraps(f)
    def w(*a, **kw):
        hdr = request.headers.get("Authorization", "")
        if not hdr.startswith("Bearer "): return jsonify({"error": "Login required"}), 401
        p = read_token(hdr.split(" ", 1)[1])
        if not p: return jsonify({"error": "Token expired"}), 401
        kw["cu"] = p; return f(*a, **kw)
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
app.permanent_session_lifetime = timedelta(hours=2)

@app.teardown_appcontext
def close_db(e=None):
    db = g.pop("db", None)
    if db is not None:
        try:
            db.close()
        except Exception:
            pass

@app.after_request
def cors(r):
    r.headers["Access-Control-Allow-Origin"]  = "*"
    r.headers["Access-Control-Allow-Methods"] = "GET,POST,PUT,DELETE,OPTIONS"
    r.headers["Access-Control-Allow-Headers"] = "Content-Type,Authorization"
    return r

@app.before_request
def preflight():
    if request.method == "OPTIONS":
        return "", 204, {"Access-Control-Allow-Origin": "*",
            "Access-Control-Allow-Methods": "GET,POST,PUT,DELETE,OPTIONS",
            "Access-Control-Allow-Headers": "Content-Type,Authorization"}

with app.app_context():
    try:
        conn = psycopg2.connect(SUPABASE_DB_URL)
        cur = conn.cursor()
        for stmt in SCHEMA_STATEMENTS:
            cur.execute(stmt)
        # Add is_blocked column if it doesn't exist (safe migration)
        cur.execute("""
            ALTER TABLE users ADD COLUMN IF NOT EXISTS is_blocked INTEGER DEFAULT 0
        """)
        conn.commit()
        cur.close()
        conn.close()
        print("✅  Supabase database ready")
    except Exception as e:
        print(f"⚠️  Database init warning: {e}")

# ═══════════════════════════════════════════════════════════════
#  LOGIN HTML  (redesigned)
# ═══════════════════════════════════════════════════════════════
LOGIN_HTML = r"""<!DOCTYPE html>
<html lang="en" data-theme="dark">
<head>
<meta charset="UTF-8"/><meta name="viewport" content="width=device-width,initial-scale=1"/>
<title>RasoiExpress — Admin Login</title>
<style>
*,*::before,*::after{box-sizing:border-box;margin:0;padding:0}
:root{
  --bg:#060c1a;--card:#0d1526;--border:#1a2d47;--text:#f0f4ff;--sub:#5a7a9a;
  --blue:#4f8ef7;--blu:#7cb3ff;--blud:#2563eb;
  --green:#10d98c;--red:#f05060;--yellow:#f5c842;--purple:#9b6dff;
  --glow:rgba(79,142,247,.18);
}
[data-theme="light"]{
  --bg:#eef2f9;--card:#ffffff;--border:#d0dae8;--text:#0a1628;--sub:#5a7a9a;
  --glow:rgba(79,142,247,.1);
}
body{font-family:'Segoe UI',system-ui,sans-serif;background:var(--bg);color:var(--text);
     min-height:100vh;display:flex;align-items:center;justify-content:center;padding:16px;
     transition:background .3s,color .3s;overflow:hidden;position:relative}
/* Animated background */
.bg-orbs{position:fixed;inset:0;pointer-events:none;z-index:0;overflow:hidden}
.orb{position:absolute;border-radius:50%;filter:blur(80px);animation:orbFloat 8s ease-in-out infinite}
.orb1{width:420px;height:420px;background:rgba(79,142,247,.12);top:-100px;right:-80px;animation-delay:0s}
.orb2{width:320px;height:320px;background:rgba(155,109,255,.1);bottom:-60px;left:-60px;animation-delay:3s}
.orb3{width:250px;height:250px;background:rgba(16,217,140,.07);top:40%;left:30%;animation-delay:5s}
@keyframes orbFloat{0%,100%{transform:translateY(0) scale(1)}50%{transform:translateY(-30px) scale(1.05)}}
.wrap{position:relative;z-index:1;width:100%;max-width:1000px;display:grid;
      grid-template-columns:1.1fr 1fr;border-radius:24px;overflow:hidden;
      box-shadow:0 32px 80px rgba(0,0,0,.5),0 0 0 1px var(--border),inset 0 1px 0 rgba(255,255,255,.05);
      min-height:580px;backdrop-filter:blur(2px)}
/* Left branding */
.left{background:linear-gradient(155deg,#0b1635 0%,#060f25 60%,#0a1520 100%);
      padding:56px 48px;display:flex;flex-direction:column;justify-content:center;position:relative;overflow:hidden}
.left::after{content:'';position:absolute;inset:0;background:url("data:image/svg+xml,%3Csvg width='60' height='60' viewBox='0 0 60 60' xmlns='http://www.w3.org/2000/svg'%3E%3Cg fill='none' fill-rule='evenodd'%3E%3Cg fill='%234f8ef7' fill-opacity='0.03'%3E%3Cpath d='M36 34v-4h-2v4h-4v2h4v4h2v-4h4v-2h-4zm0-30V0h-2v4h-4v2h4v4h2V6h4V4h-4zM6 34v-4H4v4H0v2h4v4h2v-4h4v-2H6zM6 4V0H4v4H0v2h4v4h2V6h4V4H6z'/%3E%3C/g%3E%3C/g%3E%3C/svg%3E");pointer-events:none}
.brand-ico{font-size:3rem;margin-bottom:10px;display:block;animation:float 3s ease-in-out infinite}
@keyframes float{0%,100%{transform:translateY(0)}50%{transform:translateY(-8px)}}
.brand-title{font-family:Georgia,serif;font-size:2rem;font-weight:900;color:#fff;line-height:1.15;margin-bottom:10px}
.brand-title em{background:linear-gradient(90deg,var(--blu),var(--purple));-webkit-background-clip:text;-webkit-text-fill-color:transparent;font-style:italic}
.brand-sub{font-size:.83rem;color:rgba(255,255,255,.38);line-height:1.7;margin-bottom:34px}
.perks{list-style:none}
.perk{display:flex;align-items:center;gap:12px;margin-bottom:14px;font-size:.82rem;color:rgba(255,255,255,.55);font-weight:600;animation:slideIn .5s ease both}
.perk:nth-child(1){animation-delay:.1s}.perk:nth-child(2){animation-delay:.2s}
.perk:nth-child(3){animation-delay:.3s}.perk:nth-child(4){animation-delay:.4s}
@keyframes slideIn{from{opacity:0;transform:translateX(-20px)}to{opacity:1;transform:none}}
.pio{width:34px;height:34px;border-radius:10px;background:linear-gradient(135deg,rgba(79,142,247,.25),rgba(155,109,255,.15));
     display:flex;align-items:center;justify-content:center;font-size:.9rem;flex-shrink:0;
     border:1px solid rgba(79,142,247,.25);box-shadow:0 4px 12px rgba(79,142,247,.15)}
.lock-warn{margin-top:28px;padding:12px 15px;background:rgba(240,80,96,.08);
           border:1px solid rgba(240,80,96,.2);border-radius:10px;font-size:.71rem;
           color:rgba(255,120,130,.75);display:flex;align-items:center;gap:8px;line-height:1.5}
/* Right form */
.right{background:var(--card);padding:56px 48px;display:flex;flex-direction:column;justify-content:center;position:relative}
.theme-toggle-login{position:absolute;top:18px;right:18px;background:none;border:1px solid var(--border);
                    border-radius:8px;color:var(--sub);cursor:pointer;padding:7px 10px;font-size:1rem;transition:all .2s}
.theme-toggle-login:hover{border-color:var(--blue);color:var(--blue)}
.rtag{font-size:.64rem;font-weight:800;text-transform:uppercase;letter-spacing:.14em;
      color:var(--blue);margin-bottom:6px;display:flex;align-items:center;gap:7px}
.rtag-dot{width:6px;height:6px;border-radius:50%;background:var(--green);animation:pulse 2s infinite}
@keyframes pulse{0%,100%{opacity:1;transform:scale(1)}50%{opacity:.5;transform:scale(.8)}}
.rh{font-size:1.65rem;font-weight:900;margin-bottom:4px;letter-spacing:-.02em}
.rsub{font-size:.79rem;color:var(--sub);margin-bottom:28px}
/* Attempt counter */
.attempt-bar{display:flex;align-items:center;gap:8px;padding:9px 13px;background:rgba(240,80,96,.07);
             border:1px solid rgba(240,80,96,.18);border-radius:9px;margin-bottom:16px;font-size:.76rem;
             color:rgba(255,120,130,.9);display:none}
.attempt-bar.show{display:flex}
.attempt-dots{display:flex;gap:4px;margin-left:auto}
.adot{width:9px;height:9px;border-radius:50%;background:rgba(240,80,96,.25);transition:background .3s}
.adot.used{background:var(--red)}
/* Error */
.err-box{background:rgba(240,80,96,.1);border:1px solid rgba(240,80,96,.28);border-radius:10px;
         padding:11px 14px;font-size:.82rem;font-weight:600;color:#ff8090;
         display:flex;align-items:center;gap:8px;margin-bottom:16px;animation:shake .4s ease}
@keyframes shake{0%,100%{transform:translateX(0)}25%{transform:translateX(-6px)}75%{transform:translateX(6px)}}
/* Fields */
.field{margin-bottom:18px}
.field label{display:block;font-size:.67rem;font-weight:800;text-transform:uppercase;
             letter-spacing:.1em;color:var(--sub);margin-bottom:7px}
.iw{position:relative}
.iico{position:absolute;left:14px;top:50%;transform:translateY(-50%);font-size:.9rem;pointer-events:none;
      color:var(--sub);transition:color .2s}
.iw:focus-within .iico{color:var(--blue)}
.iw input{width:100%;padding:13px 14px 13px 42px;background:rgba(79,142,247,.04);
          border:1.5px solid var(--border);border-radius:10px;color:var(--text);
          font-size:.9rem;font-family:inherit;outline:none;transition:all .25s}
.iw input:focus{border-color:var(--blue);background:rgba(79,142,247,.07);box-shadow:0 0 0 4px rgba(79,142,247,.1)}
.iw input::placeholder{color:var(--sub)}
.pw-eye{position:absolute;right:13px;top:50%;transform:translateY(-50%);background:none;
        border:none;color:var(--sub);cursor:pointer;font-size:.95rem;padding:0;line-height:1;transition:color .18s}
.pw-eye:hover{color:var(--blue)}
/* Submit */
.lbtn{width:100%;padding:14px;background:linear-gradient(135deg,var(--blue) 0%,var(--blud) 100%);
      color:#fff;border:none;border-radius:10px;font-size:.95rem;font-weight:800;cursor:pointer;
      transition:all .25s;font-family:inherit;box-shadow:0 6px 24px rgba(79,142,247,.4);
      margin-top:6px;display:flex;align-items:center;justify-content:center;gap:9px;position:relative;overflow:hidden}
.lbtn::before{content:'';position:absolute;inset:0;background:linear-gradient(135deg,#fff 0%,transparent 100%);
              opacity:0;transition:opacity .25s}
.lbtn:hover{transform:translateY(-2px);box-shadow:0 10px 32px rgba(79,142,247,.5)}
.lbtn:hover::before{opacity:.06}
.lbtn:active{transform:scale(.98)}
.lbtn:disabled{opacity:.6;cursor:not-allowed;transform:none}
.lbtn .sp{width:16px;height:16px;border:2px solid rgba(255,255,255,.4);border-top-color:#fff;
          border-radius:50%;animation:spin .7s linear infinite;display:none}
.lbtn.loading .sp{display:block}.lbtn.loading .btxt{display:none}
@keyframes spin{to{transform:rotate(360deg)}}
.locked-msg{text-align:center;margin-top:12px;font-size:.77rem;color:var(--red);font-weight:600;display:none}
.locked-msg.show{display:block}
/* Locked countdown */
.lock-countdown{font-size:1.1rem;font-weight:900;color:var(--red)}
@media(max-width:700px){.wrap{grid-template-columns:1fr;min-height:auto}.left{display:none}.right{padding:36px 24px}}
</style>
</head>
<body>
<div class="bg-orbs"><div class="orb orb1"></div><div class="orb orb2"></div><div class="orb orb3"></div></div>
<div class="wrap">
  <!-- Left -->
  <div class="left">
    <span class="brand-ico">🍛</span>
    <div class="brand-title">Rasoi<em>Express</em><br>Admin Panel</div>
    <p class="brand-sub">Secure administrator control center.<br>Authorised personnel only.</p>
    <ul class="perks">
      <li class="perk"><div class="pio">📊</div>Live charts & revenue analytics</li>
      <li class="perk"><div class="pio">👤</div>Manage all users & orders</li>
      <li class="perk"><div class="pio">📋</div>Full activity log & audit trail</li>
      <li class="perk"><div class="pio">🛡️</div>Brute-force protected login</li>
    </ul>
    <div class="lock-warn">🔐 Restricted access. {{ attempts_left }} attempts remaining before lockout.</div>
  </div>
  <!-- Right -->
  <div class="right">
    <button class="theme-toggle-login" onclick="toggleTheme()" title="Toggle theme">🌙</button>
    <div class="rtag"><span class="rtag-dot"></span>Administrator Access</div>
    <div class="rh">Admin Login</div>
    <p class="rsub">Enter your credentials to access the dashboard.</p>

    {% if attempts_used > 0 %}
    <div class="attempt-bar show">
      <span>⚠️ {{ attempts_used }} failed attempt{{ 's' if attempts_used != 1 else '' }}</span>
      <div class="attempt-dots">
        {% for i in range(5) %}<div class="adot {% if i < attempts_used %}used{% endif %}"></div>{% endfor %}
      </div>
    </div>
    {% endif %}

    {% if error %}
    <div class="err-box">🚫 {{ error }}</div>
    {% endif %}

    {% if locked %}
    <div style="text-align:center;padding:24px;background:rgba(240,80,96,.08);border:1px solid rgba(240,80,96,.25);border-radius:12px;margin-bottom:16px">
      <div style="font-size:2rem;margin-bottom:8px">🔒</div>
      <div style="font-size:.9rem;font-weight:700;color:var(--red);margin-bottom:6px">Account Locked</div>
      <div style="font-size:.78rem;color:var(--sub)">Too many failed attempts. Try again in <span class="lock-countdown" id="lockTimer">{{ lock_seconds }}</span>s</div>
    </div>
    <script>
    let t={{ lock_seconds }};
    const iv=setInterval(()=>{t--;if(document.getElementById('lockTimer'))document.getElementById('lockTimer').textContent=t;if(t<=0){clearInterval(iv);location.reload()}},1000);
    </script>
    {% else %}
    <form method="POST" action="/admin/login" id="loginForm">
      <div class="field">
        <label>Admin ID</label>
        <div class="iw"><span class="iico">👤</span>
          <input type="text" name="username" placeholder="Enter admin ID"
                 value="{{ username or '' }}" required autofocus autocomplete="username"/>
        </div>
      </div>
      <div class="field">
        <label>Password</label>
        <div class="iw"><span class="iico">🔒</span>
          <input type="password" id="pwInp" name="password" placeholder="Enter admin password" required autocomplete="current-password"/>
          <button type="button" class="pw-eye" onclick="togglePw()">👁</button>
        </div>
      </div>
      <button type="submit" class="lbtn" id="subBtn">
        <div class="sp"></div><span class="btxt">🔐 Access Dashboard</span>
      </button>
    </form>
    {% endif %}
  </div>
</div>
<script>
function toggleTheme(){const h=document.documentElement;h.dataset.theme=h.dataset.theme==='dark'?'light':'dark';document.querySelector('.theme-toggle-login').textContent=h.dataset.theme==='dark'?'🌙':'☀️'}
function togglePw(){const i=document.getElementById('pwInp');const b=document.querySelector('.pw-eye');i.type=i.type==='password'?'text':'password';b.textContent=i.type==='password'?'👁':'🙈'}
document.getElementById('loginForm')?.addEventListener('submit',e=>{const b=document.getElementById('subBtn');b.classList.add('loading');b.disabled=true})
</script>
</body></html>"""

# ═══════════════════════════════════════════════════════════════
#  DASHBOARD HTML  (full feature set)
# ═══════════════════════════════════════════════════════════════
DASH_HTML = r"""<!DOCTYPE html>
<html lang="en" data-theme="dark">
<head>
<meta charset="UTF-8"/><meta name="viewport" content="width=device-width,initial-scale=1"/>
<title>RasoiExpress — Admin</title>
<script src="https://cdn.jsdelivr.net/npm/chart.js@4.4.0/dist/chart.umd.min.js"></script>
<style>
*,*::before,*::after{box-sizing:border-box;margin:0;padding:0}
:root{
  --bg:#060c1a;--card:#0d1526;--card2:#111e33;--border:#1a2d47;
  --text:#f0f4ff;--sub:#5a7a9a;--muted:#2a3f5a;
  --blue:#4f8ef7;--blu:#7cb3ff;--blud:#2563eb;
  --green:#10d98c;--red:#f05060;--yellow:#f5c842;--purple:#9b6dff;--orange:#ff8c42;
  --r:12px;--rs:8px;
}
[data-theme="light"]{
  --bg:#eef2f9;--card:#ffffff;--card2:#f4f7fc;--border:#d0dae8;
  --text:#0a1628;--sub:#5a7a9a;--muted:#d0dae8;
}
body{font-family:'Segoe UI',system-ui,sans-serif;background:var(--bg);color:var(--text);min-height:100vh;transition:background .3s,color .3s}
@keyframes spin{to{transform:rotate(360deg)}}
@keyframes pulse{0%,100%{opacity:1}50%{opacity:.4}}
@keyframes slideDown{from{opacity:0;transform:translateY(-10px)}to{opacity:1;transform:none}}
@keyframes mop{from{opacity:0;transform:scale(.95) translateY(12px)}to{opacity:1;transform:none}}
@keyframes fadeIn{from{opacity:0}to{opacity:1}}

/* ── TOPBAR ── */
.topbar{background:var(--card);border-bottom:1px solid var(--border);padding:0 24px;
        display:flex;align-items:center;justify-content:space-between;position:sticky;top:0;z-index:200;
        height:56px;gap:10px}
.tbl{display:flex;align-items:center;gap:12px;flex-shrink:0}
.brand{font-size:.98rem;font-weight:900;white-space:nowrap}
.brand span{color:var(--blu)}
.tbadge{padding:3px 8px;border-radius:20px;font-size:.59rem;font-weight:800;text-transform:uppercase;
        background:rgba(240,80,96,.14);color:#ff8090;border:1px solid rgba(240,80,96,.24);white-space:nowrap}
.sdot{width:8px;height:8px;border-radius:50%;background:var(--green);box-shadow:0 0 6px var(--green);animation:pulse 2s infinite}
/* Global search */
.gsearch-wrap{flex:1;max-width:360px;position:relative}
.gsearch-ico{position:absolute;left:12px;top:50%;transform:translateY(-50%);font-size:.85rem;pointer-events:none;color:var(--sub)}
.gsearch{width:100%;padding:8px 14px 8px 35px;background:var(--card2);border:1.5px solid var(--border);
         border-radius:50px;color:var(--text);font-size:.82rem;font-family:inherit;outline:none;transition:all .2s}
.gsearch:focus{border-color:var(--blue);box-shadow:0 0 0 3px rgba(79,142,247,.12)}
.gsearch::placeholder{color:var(--sub)}
/* Topbar right */
.tbright{display:flex;align-items:center;gap:8px;flex-shrink:0}
/* Session timer */
.sess-timer{display:flex;align-items:center;gap:5px;padding:5px 11px;border-radius:20px;
            background:rgba(245,200,66,.08);border:1px solid rgba(245,200,66,.2);
            font-size:.7rem;font-weight:700;color:var(--yellow);white-space:nowrap}
.sess-timer.warn{background:rgba(240,80,96,.1);border-color:rgba(240,80,96,.25);color:var(--red)}
/* Notification bell */
.notif-wrap{position:relative}
.notif-btn{background:none;border:1px solid var(--border);border-radius:var(--rs);
           padding:7px 9px;cursor:pointer;font-size:1rem;position:relative;color:var(--sub);transition:all .2s}
.notif-btn:hover{border-color:var(--blue);color:var(--blue)}
.notif-cnt{position:absolute;top:-5px;right:-5px;width:17px;height:17px;border-radius:50%;
           background:var(--red);color:#fff;font-size:.58rem;font-weight:900;
           display:none;align-items:center;justify-content:center;border:2px solid var(--card)}
.notif-cnt.show{display:flex}
.notif-panel{position:absolute;top:calc(100%+8px);right:0;width:300px;background:var(--card);
             border:1px solid var(--border);border-radius:var(--r);box-shadow:0 16px 48px rgba(0,0,0,.4);
             z-index:300;display:none;animation:slideDown .2s ease}
.notif-panel.open{display:block}
.npanel-hdr{padding:12px 16px;border-bottom:1px solid var(--border);display:flex;align-items:center;justify-content:space-between}
.npanel-title{font-size:.84rem;font-weight:800}
.npanel-clear{font-size:.71rem;color:var(--blue);cursor:pointer;font-weight:700}
.notif-list{max-height:280px;overflow-y:auto}
.notif-item{padding:11px 15px;border-bottom:1px solid rgba(26,45,71,.4);
            display:flex;gap:10px;animation:fadeIn .3s ease}
.notif-item.unread{background:rgba(79,142,247,.04)}
.notif-ico{font-size:1.05rem;flex-shrink:0;margin-top:1px}
.notif-msg{font-size:.78rem;font-weight:600;color:var(--text)}
.notif-time{font-size:.67rem;color:var(--sub);margin-top:2px}
.notif-empty{padding:22px;text-align:center;color:var(--sub);font-size:.8rem}
/* Auto refresh badge */
.ar-badge{display:none;align-items:center;gap:5px;padding:4px 10px;border-radius:20px;
          font-size:.66rem;font-weight:800;background:rgba(16,217,140,.1);
          color:var(--green);border:1px solid rgba(16,217,140,.22)}
.ar-badge.show{display:flex}
.ar-dot{width:5px;height:5px;border-radius:50%;background:var(--green);animation:pulse 1.5s infinite}
/* Auto refresh progress */
.ar-bar{height:2px;background:var(--border);overflow:hidden;display:none}
.ar-bar.show{display:block}
.ar-fill{height:100%;background:linear-gradient(90deg,var(--blue),var(--purple));transition:width 1s linear}
/* Topbar buttons */
.tbtn{padding:6px 11px;border-radius:var(--rs);border:1px solid var(--border);background:none;
      color:var(--sub);font-size:.74rem;font-weight:700;cursor:pointer;transition:all .18s;font-family:inherit;white-space:nowrap}
.tbtn:hover{border-color:var(--blue);color:var(--blue)}
.tbtn.on{border-color:rgba(16,217,140,.3);color:var(--green)}
.tbav{width:30px;height:30px;border-radius:50%;background:linear-gradient(135deg,var(--blue),var(--blud));
      display:flex;align-items:center;justify-content:center;font-size:.72rem;font-weight:900;color:#fff;border:2px solid var(--border)}
.tbname{font-size:.8rem;font-weight:800}
.tbrole{font-size:.6rem;color:var(--blu);font-weight:700;text-transform:uppercase}
.out-btn{padding:5px 12px;border-radius:var(--rs);border:1px solid rgba(240,80,96,.28);
         background:rgba(240,80,96,.07);color:#ff8090;font-size:.72rem;font-weight:700;cursor:pointer;font-family:inherit}
.out-btn:hover{background:rgba(240,80,96,.18)}

/* ── LAYOUT ── */
.layout{display:grid;grid-template-columns:220px 1fr;min-height:calc(100vh - 56px)}
.sidebar{background:var(--card);border-right:1px solid var(--border);padding:18px 10px;
         overflow-y:auto;position:sticky;top:56px;height:calc(100vh - 56px)}
.nlabel{font-size:.59rem;font-weight:800;text-transform:uppercase;letter-spacing:.13em;
        color:var(--sub);padding:0 10px;margin:16px 0 5px}
.nbtn{width:100%;text-align:left;padding:9px 12px;border-radius:var(--rs);border:none;background:none;
      color:var(--sub);font-size:.82rem;font-weight:600;cursor:pointer;display:flex;align-items:center;
      gap:8px;transition:all .18s;margin-bottom:2px;font-family:inherit}
.nbtn:hover{background:rgba(79,142,247,.07);color:var(--text)}
.nbtn.active{background:rgba(79,142,247,.12);color:var(--blue);border:1px solid rgba(79,142,247,.2)}
.nbadge{margin-left:auto;background:var(--border);color:var(--sub);font-size:.59rem;font-weight:800;padding:2px 6px;border-radius:10px}
.nbtn.active .nbadge{background:rgba(79,142,247,.2);color:var(--blue)}
.main{padding:22px;overflow-x:auto}

/* ── SECTION ── */
.sh{display:flex;align-items:center;justify-content:space-between;margin-bottom:18px;flex-wrap:wrap;gap:9px}
.sh-l{display:flex;align-items:center;gap:8px}
.sh-title{font-size:1.05rem;font-weight:800}
.sh-cnt{font-size:.64rem;background:rgba(79,142,247,.15);color:var(--blu);padding:3px 9px;border-radius:20px;font-weight:800}
.sh-r{display:flex;gap:7px;flex-wrap:wrap}

/* ── STAT CARDS ── */
.sg{display:grid;grid-template-columns:repeat(auto-fill,minmax(148px,1fr));gap:12px;margin-bottom:20px}
.sc{background:var(--card);border:1px solid var(--border);border-radius:var(--r);padding:16px 18px;
    position:relative;overflow:hidden;transition:transform .2s,box-shadow .2s;cursor:default}
.sc:hover{transform:translateY(-3px);box-shadow:0 12px 40px rgba(0,0,0,.3)}
.sc::before{content:'';position:absolute;top:0;left:0;right:0;height:3px}
.sc.bl::before{background:linear-gradient(90deg,var(--blue),var(--blu))}
.sc.gr::before{background:linear-gradient(90deg,var(--green),#4dffc3)}
.sc.ye::before{background:linear-gradient(90deg,var(--yellow),#fde68a)}
.sc.pu::before{background:linear-gradient(90deg,var(--purple),#c4b5fd)}
.sc.re::before{background:linear-gradient(90deg,var(--red),#fca5a5)}
.sc.or::before{background:linear-gradient(90deg,var(--orange),#fed7aa)}
.sn{font-size:1.8rem;font-weight:900;line-height:1.1;margin-bottom:3px}
.sl{font-size:.62rem;color:var(--sub);font-weight:700;text-transform:uppercase;letter-spacing:.07em}
.si{position:absolute;bottom:10px;right:12px;font-size:1.35rem;opacity:.1}

/* ── CHARTS ── */
.charts-row{display:grid;grid-template-columns:2fr 1fr 1fr;gap:14px;margin-bottom:16px}
.charts-row2{display:grid;grid-template-columns:1fr 1fr;gap:14px;margin-bottom:20px}
.chart-card{background:var(--card);border:1px solid var(--border);border-radius:var(--r);padding:18px}
.chart-title{font-size:.8rem;font-weight:800;margin-bottom:12px;display:flex;align-items:center;gap:6px}
.chart-wrap{position:relative}

/* ── DATE FILTER ── */
.date-bar{display:flex;gap:7px;align-items:center;flex-wrap:wrap;padding:10px 13px;
          background:var(--card);border:1px solid var(--border);border-radius:var(--r);margin-bottom:13px}
.date-bar label{font-size:.67rem;font-weight:800;color:var(--sub);text-transform:uppercase;letter-spacing:.08em;white-space:nowrap}
.date-inp{padding:6px 9px;background:var(--card2);border:1px solid var(--border);border-radius:var(--rs);
          color:var(--text);font-size:.78rem;font-family:inherit;outline:none;transition:border-color .2s}
.date-inp:focus{border-color:var(--blue)}
.dpill{padding:4px 10px;border-radius:20px;border:1px solid var(--border);background:none;
       color:var(--sub);font-size:.69rem;font-weight:700;cursor:pointer;transition:all .18s;font-family:inherit}
.dpill:hover,.dpill.on{border-color:var(--blue);color:var(--blue);background:rgba(79,142,247,.07)}

/* ── BUTTONS ── */
.btn{padding:7px 13px;border-radius:var(--rs);border:1px solid var(--border);background:var(--card);
     color:var(--sub);font-size:.74rem;font-weight:700;cursor:pointer;transition:all .18s;
     font-family:inherit;display:inline-flex;align-items:center;gap:5px;white-space:nowrap}
.btn:hover{border-color:var(--blue);color:var(--blue)}
.btn.g{border-color:rgba(16,217,140,.3);color:var(--green)}.btn.g:hover{background:rgba(16,217,140,.07)}
.btn.r{border-color:rgba(240,80,96,.3);color:#ff8090}.btn.r:hover{background:rgba(240,80,96,.07)}
.btn.pr{background:linear-gradient(135deg,var(--blue),var(--blud));color:#fff;border-color:transparent;box-shadow:0 4px 14px rgba(79,142,247,.3)}
.btn.pr:hover{transform:translateY(-1px)}

/* ── SEARCH/FILTER ── */
.sw{position:relative}
.si2{position:absolute;left:10px;top:50%;transform:translateY(-50%);font-size:.8rem;color:var(--sub);pointer-events:none}
.srch{padding:7px 10px 7px 29px;background:var(--card2);border:1px solid var(--border);
      border-radius:var(--rs);color:var(--text);font-size:.79rem;font-family:inherit;outline:none;
      transition:border-color .18s;width:190px}
.srch:focus{border-color:var(--blue)}
.srch::placeholder{color:var(--sub)}
.fsel{padding:7px 9px;background:var(--card2);border:1px solid var(--border);border-radius:var(--rs);
      color:var(--text);font-size:.77rem;cursor:pointer;outline:none;font-family:inherit}

/* ── TABLE ── */
.tw{background:var(--card);border:1px solid var(--border);border-radius:var(--r);overflow:hidden;margin-bottom:20px}
table{width:100%;border-collapse:collapse;font-size:.79rem}
thead{background:var(--bg)}
th{padding:11px 13px;text-align:left;font-size:.59rem;font-weight:800;text-transform:uppercase;
   letter-spacing:.1em;color:var(--sub);white-space:nowrap;border-bottom:1px solid var(--border)}
td{padding:12px 13px;border-top:1px solid rgba(26,45,71,.5);vertical-align:middle}
tr:hover td{background:rgba(79,142,247,.03)}
.mono{font-family:'Courier New',monospace;font-size:.76rem;color:var(--blu)}
.mu{color:var(--sub);font-size:.72rem}
.uc{display:flex;align-items:center;gap:8px}
.uav{width:31px;height:31px;border-radius:50%;display:inline-flex;align-items:center;
     justify-content:center;font-size:.68rem;font-weight:900;color:#fff;flex-shrink:0;border:2px solid var(--border)}
.pill{display:inline-flex;align-items:center;gap:3px;padding:2px 8px;border-radius:20px;font-size:.61rem;font-weight:800;white-space:nowrap}
.pp{background:rgba(245,200,66,.12);color:#fcd34d;border:1px solid rgba(245,200,66,.25)}
.ppr{background:rgba(255,140,66,.12);color:#fdba74;border:1px solid rgba(255,140,66,.25)}
.po{background:rgba(79,142,247,.12);color:#7cb3ff;border:1px solid rgba(79,142,247,.25)}
.pn{background:rgba(16,217,140,.12);color:#4dffc3;border:1px solid rgba(16,217,140,.25)}
.pd{background:rgba(16,217,140,.1);color:#86efac;border:1px solid rgba(16,217,140,.2)}
.pa{background:rgba(79,142,247,.1);color:#93c5fd;border:1px solid rgba(79,142,247,.2)}
.p0{background:rgba(90,122,154,.1);color:var(--sub);border:1px solid rgba(90,122,154,.2)}
.pblk{background:rgba(240,80,96,.1);color:#fca5a5;border:1px solid rgba(240,80,96,.2)}
.sbar{display:flex;gap:2px;align-items:center}
.sd{width:7px;height:7px;border-radius:50%;background:var(--muted)}
.sd.dn{background:var(--green)}.sd.ac{background:var(--blue);box-shadow:0 0 4px var(--blue)}
.ab{padding:4px 9px;border-radius:6px;border:1px solid var(--border);background:none;
    color:var(--sub);font-size:.67rem;font-weight:700;cursor:pointer;transition:all .18s;font-family:inherit}
.ab:hover{border-color:var(--blue);color:var(--blue)}
.ab.d:hover{border-color:var(--red);color:var(--red)}
.ab.g:hover{border-color:var(--green);color:var(--green)}
.ab.y:hover{border-color:var(--yellow);color:var(--yellow)}
.ar2{display:flex;gap:3px;flex-wrap:wrap}

/* ── LOADING ── */
.lb{text-align:center;padding:46px 20px;color:var(--sub);font-size:.84rem}
.sp{width:26px;height:26px;border:3px solid var(--border);border-top-color:var(--blue);
    border-radius:50%;animation:spin .7s linear infinite;margin:0 auto 11px}

/* ── MODAL ── */
.mo{position:fixed;inset:0;background:rgba(0,0,0,.75);z-index:500;display:none;
    align-items:center;justify-content:center;padding:18px;backdrop-filter:blur(6px)}
.mo.open{display:flex}
.modal{background:var(--card);border:1px solid var(--border);border-radius:var(--r);
       width:100%;max-width:580px;max-height:92vh;overflow-y:auto;
       box-shadow:0 24px 64px rgba(0,0,0,.7);animation:mop .22s ease}
.mhdr{padding:17px 21px 13px;border-bottom:1px solid var(--border);display:flex;
      align-items:center;justify-content:space-between;position:sticky;top:0;background:var(--card);z-index:5}
.mttl{font-size:.92rem;font-weight:800}
.mclose{background:none;border:none;color:var(--sub);font-size:1.1rem;cursor:pointer;
        padding:3px 6px;border-radius:6px;transition:all .18s}
.mclose:hover{background:rgba(240,80,96,.1);color:var(--red)}
.mbody{padding:19px 21px}
.mftr{padding:12px 21px;border-top:1px solid var(--border);display:flex;gap:8px;
      justify-content:flex-end;position:sticky;bottom:0;background:var(--card)}
.mbtn{padding:8px 17px;border-radius:var(--rs);border:none;font-size:.81rem;font-weight:700;cursor:pointer;transition:all .2s;font-family:inherit}
.mbtn.pr{background:linear-gradient(135deg,var(--blue),var(--blud));color:#fff}
.mbtn.gh{background:var(--card2);color:var(--sub);border:1px solid var(--border)}
.mbtn.gh:hover{border-color:var(--blue);color:var(--blue)}
.mbtn.dn{background:rgba(240,80,96,.1);color:#ff8090;border:1px solid rgba(240,80,96,.25)}
.mbtn.dn:hover{background:rgba(240,80,96,.2)}
.mfield{margin-bottom:13px}
.mfield label{display:block;font-size:.67rem;font-weight:800;text-transform:uppercase;letter-spacing:.08em;color:var(--sub);margin-bottom:5px}
.mfield input,.mfield select,.mfield textarea{width:100%;padding:9px 13px;background:var(--card2);
  border:1.5px solid var(--border);border-radius:var(--rs);color:var(--text);font-size:.84rem;font-family:inherit;outline:none;transition:border-color .2s}
.mfield input:focus,.mfield select:focus,.mfield textarea:focus{border-color:var(--blue)}
.mfield textarea{resize:vertical;min-height:68px}
.mrow{display:grid;grid-template-columns:1fr 1fr;gap:11px}
.dr{display:flex;justify-content:space-between;align-items:flex-start;padding:9px 0;
    border-bottom:1px solid rgba(26,45,71,.45);gap:12px}
.dr:last-child{border-bottom:none}
.dl{font-size:.67rem;font-weight:700;color:var(--sub);text-transform:uppercase;flex-shrink:0}
.dv{font-size:.81rem;font-weight:600;color:var(--text);text-align:right;max-width:320px;word-break:break-all}
/* Switch toggle */
.sw-tog{width:34px;height:18px;border-radius:9px;background:var(--border);position:relative;
        cursor:pointer;transition:background .2s;flex-shrink:0;border:none;outline:none}
.sw-tog.on{background:var(--blue)}
.sw-tog::after{content:'';position:absolute;top:2px;left:2px;width:14px;height:14px;
               border-radius:50%;background:#fff;transition:transform .2s}
.sw-tog.on::after{transform:translateX(16px)}
/* Status steps */
.sstep{text-align:center;padding:10px 6px;border-radius:8px;border:1.5px solid var(--border);
       background:var(--bg);cursor:pointer;transition:all .2s;color:var(--sub)}
.sstep:hover,.sstep.sel{border-color:var(--blue);background:rgba(79,142,247,.1);color:var(--blue)}
.sstep.dn{border-color:var(--green);background:rgba(16,217,140,.07);color:var(--green)}

/* ── ACTIVITY LOG ── */
.log-item{display:flex;gap:12px;padding:10px 0;border-bottom:1px solid rgba(26,45,71,.4);animation:fadeIn .3s ease}
.log-item:last-child{border-bottom:none}
.log-ico{width:28px;height:28px;border-radius:8px;display:flex;align-items:center;justify-content:center;
         font-size:.8rem;flex-shrink:0;background:rgba(79,142,247,.1);border:1px solid rgba(79,142,247,.2)}
.log-action{font-size:.8rem;font-weight:700;color:var(--text)}
.log-detail{font-size:.72rem;color:var(--sub);margin-top:1px}
.log-time{font-size:.67rem;color:var(--sub);margin-left:auto;white-space:nowrap;flex-shrink:0}

/* ── PRINT / PDF ── */
@media print{
  body>*:not(#pdfArea){display:none!important}
  #pdfArea{display:block!important}
  body{background:#fff;color:#000}
}
#pdfArea{display:none}
.pdf-doc{background:#fff;color:#111;padding:40px;max-width:750px;margin:0 auto;font-family:'Segoe UI',sans-serif}
.pdf-hdr{display:flex;justify-content:space-between;align-items:flex-start;margin-bottom:28px;border-bottom:3px solid #0a1628;padding-bottom:20px}
.pdf-brand{font-size:1.5rem;font-weight:900;color:#0a1628}
.pdf-brand em{color:#4f8ef7;font-style:italic}
.pdf-meta{text-align:right;font-size:.8rem;color:#475569}
.pdf-stl{font-size:.67rem;font-weight:800;text-transform:uppercase;letter-spacing:.1em;color:#64748b;margin-bottom:7px;border-bottom:1px solid #e2e8f0;padding-bottom:4px;margin-top:16px}
.pdf-row{display:flex;justify-content:space-between;padding:5px 0;font-size:.82rem;border-bottom:1px solid #f1f5f9}
.pdf-total{display:flex;justify-content:space-between;padding:9px 0;font-weight:800;font-size:.92rem;border-top:2px solid #0a1628;margin-top:6px}
.pdf-footer{text-align:center;margin-top:24px;color:#64748b;font-size:.76rem;border-top:1px solid #e2e8f0;padding-top:14px}

/* ── TOAST ── */
#toast{position:fixed;bottom:20px;right:20px;background:var(--card);border:1px solid var(--border);
       border-radius:10px;padding:10px 14px;font-size:.79rem;color:var(--text);font-weight:600;
       box-shadow:0 20px 60px rgba(0,0,0,.5);transform:translateY(60px);opacity:0;
       transition:all .3s;z-index:1000;max-width:280px}
#toast.show{transform:translateY(0);opacity:1}

/* ── PANELS ── */
.panel{display:none}.panel.active{display:block}

/* ── RESPONSIVE ── */
@media(max-width:900px){
  .layout{grid-template-columns:1fr}
  .sidebar{position:static;height:auto;display:flex;flex-wrap:wrap;gap:3px;padding:8px;border-right:none;border-bottom:1px solid var(--border)}
  .nlabel{display:none}
  .charts-row{grid-template-columns:1fr}
  .charts-row2{grid-template-columns:1fr}
  .srch{width:100%}
  .gsearch-wrap{display:none}
  .main{padding:13px}
  .sg{grid-template-columns:repeat(2,1fr)}
  .mrow{grid-template-columns:1fr}
}
</style>
</head>
<body>

<!-- TOPBAR -->
<div class="topbar">
  <div class="tbl">
    <div class="brand">🍛 Rasoi<span>Express</span></div>
    <span class="tbadge">🔐 Admin</span>
    <span class="sdot"></span>
    <span class="ar-badge" id="arBadge"><span class="ar-dot"></span>LIVE</span>
  </div>
  <!-- Global Search -->
  <div class="gsearch-wrap">
    <span class="gsearch-ico">🔍</span>
    <input class="gsearch" id="gSearch" placeholder="Search users, orders, dishes…" oninput="doGlobalSearch(this.value)" autocomplete="off"/>
    <div id="gSearchResults" style="position:absolute;top:calc(100%+6px);left:0;right:0;background:var(--card);border:1px solid var(--border);border-radius:var(--r);box-shadow:0 16px 40px rgba(0,0,0,.4);display:none;z-index:300;max-height:300px;overflow-y:auto"></div>
  </div>
  <div class="tbright">
    <div class="sess-timer" id="sessTimer">⏰ <span id="sessCountdown">2:00:00</span></div>
    <!-- Notification Bell -->
    <div class="notif-wrap">
      <button class="notif-btn" id="notifBtn" onclick="toggleNotif()">🔔<div class="notif-cnt" id="notifCnt">0</div></button>
      <div class="notif-panel" id="notifPanel">
        <div class="npanel-hdr"><div class="npanel-title">🔔 Notifications</div><div class="npanel-clear" onclick="clearNotifs()">Clear all</div></div>
        <div class="notif-list" id="notifList"><div class="notif-empty">No notifications yet</div></div>
      </div>
    </div>
    <!-- Theme toggle -->
    <button class="tbtn" id="themeBtn" onclick="toggleTheme()" title="Toggle theme">🌙</button>
    <!-- Fullscreen -->
    <button class="tbtn" id="fsBtn" onclick="toggleFS()" title="Full screen">⛶</button>
    <!-- Auto refresh -->
    <button class="tbtn" id="arBtn" onclick="toggleAR()">↺ Auto: OFF</button>
    <!-- User -->
    <div class="tbav">A</div>
    <div><div class="tbname">admin123</div><div class="tbrole">Super Admin</div></div>
    <a href="/admin/logout" class="out-btn">↩ Logout</a>
  </div>
</div>
<!-- Auto refresh progress bar -->
<div class="ar-bar" id="arBar"><div class="ar-fill" id="arFill" style="width:100%"></div></div>

<div class="layout">
  <!-- Sidebar -->
  <aside class="sidebar">
    <div class="nlabel">Dashboard</div>
    <button class="nbtn active" id="nb-ov"     onclick="showPanel('ov')">📊 Overview</button>
    <div class="nlabel">Database</div>
    <button class="nbtn" id="nb-users"  onclick="showPanel('users')">👤 Users <span class="nbadge" id="nc-users">—</span></button>
    <button class="nbtn" id="nb-orders" onclick="showPanel('orders')">📦 Orders <span class="nbadge" id="nc-orders">—</span></button>
    <button class="nbtn" id="nb-menu"   onclick="showPanel('menu')">🍽️ Menu <span class="nbadge" id="nc-menu">—</span></button>
    <div class="nlabel">Reports</div>
    <button class="nbtn" id="nb-log"    onclick="showPanel('log')">📋 Activity Log</button>
    <button class="nbtn" id="nb-pdf"    onclick="showPanel('pdf')">📤 Export PDF</button>
    <div class="nlabel">Actions</div>
    <button class="nbtn" id="nb-seed"   onclick="seedMenu()">🌱 Seed Menu</button>
  </aside>

  <main class="main">

    <!-- OVERVIEW PANEL -->
    <div class="panel active" id="panel-ov">
      <div class="sh">
        <div class="sh-l"><div class="sh-title">📊 Dashboard Overview</div></div>
        <div class="sh-r">
          <button class="btn g" onclick="exportUsersCSV()">📤 Users CSV</button>
          <button class="btn g" onclick="exportOrdersCSV()">📤 Orders CSV</button>
          <button class="btn" onclick="refreshAll()">↻ Refresh</button>
        </div>
      </div>
      <div class="sg" id="sGrid"><div class="sc bl"><div class="sp" style="width:20px;height:20px;margin:4px auto 0"></div><div class="sl">Loading…</div></div></div>
      <!-- Charts row 2 -->
      <div class="charts-row2">
        <div class="chart-card">
          <div class="chart-title">📈 Revenue — Last 14 Days</div>
          <div class="chart-wrap" style="height:240px"><canvas id="revChart"></canvas></div>
        </div>
<div class="chart-card">
          <div class="chart-title">🍽️ Top 6 Most Ordered Dishes</div>
          <div class="chart-wrap" style="height:220px"><canvas id="dishChart"></canvas></div>
        </div>
      </div>
      <!-- Charts row 2 -->
      <div class="charts-row2">
              <div class="chart-card">
          <div class="chart-title">📦 Orders by Status</div>
          <div class="chart-wrap" style="height:240px"><canvas id="statusChart"></canvas></div>
        </div>
        
        <div class="chart-card">
          <div class="chart-title">🥗 Veg vs Non-Veg</div>
          <div class="chart-wrap" style="height:240px"><canvas id="vegChart"></canvas></div>
        </div>
      </div>
    </div>

    <!-- USERS PANEL -->
    <div class="panel" id="panel-users">
      <div class="sh">
        <div class="sh-l"><div class="sh-title">👤 All Users</div><span class="sh-cnt" id="uCnt">…</span></div>
        <div class="sh-r">
          <div class="sw"><span class="si2">🔍</span><input class="srch" id="uSrch" placeholder="Search name, email…" oninput="filterU(this.value)"/></div>
          <select class="fsel" id="uSF" onchange="filterU($('uSrch').value)">
            <option value="">All Users</option>
            <option value="active">✅ Active</option>
            <option value="blocked">🚫 Blocked</option>
          </select>
          <button class="btn g" onclick="exportUsersCSV()">📤 CSV</button>
          <button class="btn" onclick="loadUsers()">↻</button>
        </div>
      </div>
      <div class="tw"><table>
        <thead><tr><th>#</th><th>User</th><th>Email</th><th>Phone</th><th>Orders</th><th>Spent</th><th>Status</th><th>Joined</th><th>Actions</th></tr></thead>
        <tbody id="uBody"><tr><td colspan="9"><div class="lb"><div class="sp"></div>Loading…</div></td></tr></tbody>
      </table></div>
    </div>

    <!-- ORDERS PANEL -->
    <div class="panel" id="panel-orders">
      <div class="sh">
        <div class="sh-l"><div class="sh-title">📦 All Orders</div><span class="sh-cnt" id="oCnt">…</span></div>
        <div class="sh-r">
          <div class="sw"><span class="si2">🔍</span><input class="srch" id="oSrch" placeholder="Search order ID…" oninput="filterO()"/></div>
          <select class="fsel" id="oSF" onchange="filterO()">
            <option value="">All Status</option>
            <option value="placed">🟡 Placed</option>
            <option value="preparing">🟠 Preparing</option>
            <option value="on_the_way">🔵 On the Way</option>
            <option value="nearby">🟢 Nearby</option>
            <option value="delivered">✅ Delivered</option>
          </select>
          <button class="btn g" onclick="exportOrdersCSV()">📤 CSV</button>
          <button class="btn" onclick="loadOrders()">↻</button>
        </div>
      </div>
      <div class="date-bar">
        <label>📅 Date:</label>
        <input type="date" class="date-inp" id="dFrom" onchange="filterO()"/>
        <span style="color:var(--sub);font-size:.78rem">to</span>
        <input type="date" class="date-inp" id="dTo" onchange="filterO()"/>
        <button class="dpill on" id="dp-all"   onclick="setDP('all')">All</button>
        <button class="dpill" id="dp-today" onclick="setDP('today')">Today</button>
        <button class="dpill" id="dp-week"  onclick="setDP('week')">This Week</button>
        <button class="dpill" id="dp-month" onclick="setDP('month')">This Month</button>
        <button class="btn r" onclick="clearDates()" style="margin-left:auto;padding:4px 9px">✕</button>
      </div>
      <div class="tw"><table>
        <thead><tr><th>Order ID</th><th>Customer</th><th>Status</th><th>Step</th><th>Items</th><th>Total</th><th>Date</th><th>Actions</th></tr></thead>
        <tbody id="oBody"><tr><td colspan="8"><div class="lb"><div class="sp"></div>Loading…</div></td></tr></tbody>
      </table></div>
    </div>

    <!-- MENU PANEL -->
    <div class="panel" id="panel-menu">
      <div class="sh">
        <div class="sh-l"><div class="sh-title">🍽️ Menu Items</div><span class="sh-cnt" id="mCnt">…</span></div>
        <div class="sh-r">
          <div class="sw"><span class="si2">🔍</span><input class="srch" id="mSrch" placeholder="Search dish…" oninput="filterM(this.value)"/></div>
          <select class="fsel" id="mCF" onchange="filterM($('mSrch').value)"><option value="">All Categories</option></select>
          <button class="btn pr" onclick="openAddDish()">➕ Add Dish</button>
          <button class="btn" onclick="loadMenu()">↻</button>
        </div>
      </div>
      <div class="tw"><table>
        <thead><tr><th>ID</th><th>Dish</th><th>Category</th><th>Type</th><th>Price</th><th>Rating</th><th>Status</th><th>Actions</th></tr></thead>
        <tbody id="mBody"><tr><td colspan="8"><div class="lb"><div class="sp"></div>Loading…</div></td></tr></tbody>
      </table>
      <div id="menuPager"></div>
      </div>
    </div>

    <!-- ACTIVITY LOG PANEL -->
    <div class="panel" id="panel-log">
      <div class="sh">
        <div class="sh-l"><div class="sh-title">📋 Activity Log</div><span class="sh-cnt" id="logCnt">…</span></div>
        <div class="sh-r">
          <div class="sw"><span class="si2">🔍</span><input class="srch" id="logSrch" placeholder="Search actions…" oninput="filterLog(this.value)"/></div>
          <button class="btn r" onclick="clearLog()">🗑️ Clear Log</button>
          <button class="btn" onclick="loadLog()">↻</button>
        </div>
      </div>
      <div class="tw" id="logWrap" style="padding:14px 18px">
        <div class="lb"><div class="sp"></div>Loading activity log…</div>
      </div>
    </div>

    <!-- PDF EXPORT PANEL -->
    <div class="panel" id="panel-pdf">
      <div class="sh"><div class="sh-l"><div class="sh-title">📤 Export PDF Report</div></div></div>
      <div style="display:grid;grid-template-columns:repeat(auto-fill,minmax(240px,1fr));gap:14px;margin-bottom:20px">
        <div style="background:var(--card);border:1px solid var(--border);border-radius:var(--r);padding:20px;cursor:pointer;transition:all .2s" onclick="printReport('summary')" onmouseover="this.style.borderColor='var(--blue)'" onmouseout="this.style.borderColor='var(--border)'">
          <div style="font-size:2rem;margin-bottom:8px">📊</div>
          <div style="font-weight:800;margin-bottom:5px">Summary Report</div>
          <div style="font-size:.78rem;color:var(--sub)">Stats, revenue overview, totals — 1 page</div>
          <button class="btn pr" style="margin-top:12px;width:100%;justify-content:center">🖨️ Print / Save PDF</button>
        </div>
        <div style="background:var(--card);border:1px solid var(--border);border-radius:var(--r);padding:20px;cursor:pointer;transition:all .2s" onclick="printReport('users')" onmouseover="this.style.borderColor='var(--blue)'" onmouseout="this.style.borderColor='var(--border)'">
          <div style="font-size:2rem;margin-bottom:8px">👤</div>
          <div style="font-weight:800;margin-bottom:5px">Users Report</div>
          <div style="font-size:.78rem;color:var(--sub)">All user details, orders & spending</div>
          <button class="btn pr" style="margin-top:12px;width:100%;justify-content:center">🖨️ Print / Save PDF</button>
        </div>
        <div style="background:var(--card);border:1px solid var(--border);border-radius:var(--r);padding:20px;cursor:pointer;transition:all .2s" onclick="printReport('orders')" onmouseover="this.style.borderColor='var(--blue)'" onmouseout="this.style.borderColor='var(--border)'">
          <div style="font-size:2rem;margin-bottom:8px">📦</div>
          <div style="font-weight:800;margin-bottom:5px">Orders Report</div>
          <div style="font-size:.78rem;color:var(--sub)">All orders with status & revenue</div>
          <button class="btn pr" style="margin-top:12px;width:100%;justify-content:center">🖨️ Print / Save PDF</button>
        </div>
      </div>
      <div style="padding:14px 18px;background:rgba(79,142,247,.06);border:1px solid rgba(79,142,247,.18);border-radius:var(--r);font-size:.78rem;color:var(--sub)">
        💡 Click any card → Browser print dialog opens → Select <strong style="color:var(--text)">Save as PDF</strong> in destination
      </div>
    </div>

  </main>
</div>

<!-- ── MODALS ── -->

<!-- User Detail Modal -->
<div class="mo" id="uModal">
  <div class="modal">
    <div class="mhdr"><div class="mttl" id="uMTitle">👤 User Details</div><button class="mclose" onclick="closeM('uModal')">✕</button></div>
    <div class="mbody" id="uMBody"></div>
    <div class="mftr">
      <button class="mbtn dn" onclick="preDel()">🗑️ Delete</button>
      <button class="mbtn gh" onclick="openEdit(viewId)">✏️ Edit</button>
      <button class="mbtn gh" onclick="openPw(viewId)">🔑 Reset PW</button>
      <button class="mbtn gh" onclick="closeM('uModal')">Close</button>
    </div>
  </div>
</div>

<!-- Edit User Modal -->
<div class="mo" id="editModal">
  <div class="modal" style="max-width:520px">
    <div class="mhdr"><div class="mttl">✏️ Edit User</div><button class="mclose" onclick="closeM('editModal')">✕</button></div>
    <div class="mbody">
      <input type="hidden" id="eUid"/>
      <div class="mrow">
        <div class="mfield"><label>Full Name</label><input id="eName" placeholder="Priya Sharma"/></div>
        <div class="mfield"><label>Phone</label><input id="ePhone" placeholder="+91 98765 43210"/></div>
      </div>
      <div class="mfield"><label>Email</label><input id="eEmail" type="email"/></div>
      <div class="mfield"><label>Address</label><textarea id="eAddr"></textarea></div>
    </div>
    <div class="mftr">
      <button class="mbtn gh" onclick="closeM('editModal')">Cancel</button>
      <button class="mbtn pr" onclick="saveEdit()">💾 Save Changes</button>
    </div>
  </div>
</div>

<!-- Reset Password Modal -->
<div class="mo" id="pwModal">
  <div class="modal" style="max-width:440px">
    <div class="mhdr"><div class="mttl">🔑 Reset Password</div><button class="mclose" onclick="closeM('pwModal')">✕</button></div>
    <div class="mbody">
      <div style="background:rgba(245,200,66,.08);border:1px solid rgba(245,200,66,.22);border-radius:9px;padding:10px 13px;margin-bottom:14px;font-size:.78rem;color:var(--yellow)">⚠️ This immediately changes the user's password.</div>
      <input type="hidden" id="pwUid"/>
      <div class="mfield"><label>New Password (6+ chars)</label><input type="password" id="newPw" placeholder="Enter new password"/></div>
      <div class="mfield"><label>Confirm Password</label><input type="password" id="newPwC" placeholder="Re-enter new password"/></div>
    </div>
    <div class="mftr">
      <button class="mbtn gh" onclick="closeM('pwModal')">Cancel</button>
      <button class="mbtn pr" onclick="saveReset()">🔑 Reset Password</button>
    </div>
  </div>
</div>

<!-- Order Status Modal -->
<div class="mo" id="oStModal">
  <div class="modal" style="max-width:460px">
    <div class="mhdr"><div class="mttl">📦 Update Order Status</div><button class="mclose" onclick="closeM('oStModal')">✕</button></div>
    <div class="mbody">
      <div style="font-size:.81rem;color:var(--sub);margin-bottom:11px">Order: <span class="mono" id="oStId"></span></div>
      <div style="display:grid;grid-template-columns:repeat(5,1fr);gap:6px;margin-bottom:13px">
        <div class="sstep" onclick="selSt(0)"><div style="font-size:1rem;margin-bottom:3px">🧾</div><div style="font-size:.61rem;font-weight:700">Placed</div></div>
        <div class="sstep" onclick="selSt(1)"><div style="font-size:1rem;margin-bottom:3px">👨‍🍳</div><div style="font-size:.61rem;font-weight:700">Preparing</div></div>
        <div class="sstep" onclick="selSt(2)"><div style="font-size:1rem;margin-bottom:3px">🛵</div><div style="font-size:.61rem;font-weight:700">On the Way</div></div>
        <div class="sstep" onclick="selSt(3)"><div style="font-size:1rem;margin-bottom:3px">📍</div><div style="font-size:.61rem;font-weight:700">Nearby</div></div>
        <div class="sstep" onclick="selSt(4)"><div style="font-size:1rem;margin-bottom:3px">🏠</div><div style="font-size:.61rem;font-weight:700">Delivered</div></div>
      </div>
      <div id="oStLbl" style="padding:9px 13px;background:var(--bg);border-radius:var(--rs);border:1px solid var(--border);font-size:.8rem;font-weight:700;color:var(--blue)">— Select status above —</div>
    </div>
    <div class="mftr"><button class="mbtn gh" onclick="closeM('oStModal')">Cancel</button><button class="mbtn pr" onclick="confirmOSt()">✅ Update</button></div>
  </div>
</div>

<!-- Add/Edit Dish Modal -->
<div class="mo" id="dishModal">
  <div class="modal">
    <div class="mhdr"><div class="mttl" id="dMTitle">➕ Add New Dish</div><button class="mclose" onclick="closeM('dishModal')">✕</button></div>
    <div class="mbody">
      <input type="hidden" id="dId"/>
      <div class="mrow">
        <div class="mfield"><label>Dish Name *</label><input id="dName" placeholder="Butter Paneer Masala"/></div>
        <div class="mfield"><label>Emoji</label><input id="dEmoji" placeholder="🍛" maxlength="2"/></div>
      </div>
      <div class="mfield"><label>Description</label><textarea id="dDesc" placeholder="Describe the dish…"></textarea></div>
      <div class="mrow">
        <div class="mfield"><label>Price (₹) *</label><input id="dPrice" type="number" placeholder="280"/></div>
        <div class="mfield"><label>Rating</label><input id="dRating" type="number" step="0.1" min="1" max="5" placeholder="4.5"/></div>
      </div>
      <div class="mrow">
        <div class="mfield"><label>Category *</label>
          <select id="dCat"><option value="">— Select —</option><option>Veg Curries</option><option>Non-Veg Curries</option><option>Biryani & Rice</option><option>South Indian</option><option>Street Food</option><option>Snacks</option><option>Breads</option><option>Desserts</option><option>Drinks</option></select>
        </div>
        <div class="mfield"><label>Type</label>
          <select id="dType"><option value="veg">🟢 Vegetarian</option><option value="nonveg">🔴 Non-Veg</option></select>
        </div>
      </div>
      <div class="mrow">
        <div class="mfield"><label>Restaurant</label><input id="dRest" placeholder="Spice Garden"/></div>
        <div class="mfield"><label>Delivery Time</label><input id="dTime" placeholder="30 mins"/></div>
      </div>
      <div style="display:flex;gap:16px;margin-top:8px;flex-wrap:wrap">
        <label style="display:flex;align-items:center;gap:7px;cursor:pointer;font-size:.79rem;color:var(--sub)"><button type="button" class="sw-tog" id="swBest" onclick="this.classList.toggle('on')"></button>⭐ Bestseller</label>
        <label style="display:flex;align-items:center;gap:7px;cursor:pointer;font-size:.79rem;color:var(--sub)"><button type="button" class="sw-tog" id="swNew" onclick="this.classList.toggle('on')"></button>✨ New</label>
        <label style="display:flex;align-items:center;gap:7px;cursor:pointer;font-size:.79rem;color:var(--sub)"><button type="button" class="sw-tog" id="swSpicy" onclick="this.classList.toggle('on')"></button>🌶️ Spicy</label>
      </div>
    </div>
    <div class="mftr"><button class="mbtn gh" onclick="closeM('dishModal')">Cancel</button><button class="mbtn pr" onclick="saveDish()">💾 Save Dish</button></div>
  </div>
</div>

<!-- Confirm Delete Modal -->
<div class="mo" id="cModal">
  <div class="modal" style="max-width:380px">
    <div class="mhdr"><div class="mttl">⚠️ Confirm Delete</div><button class="mclose" onclick="closeM('cModal')">✕</button></div>
    <div class="mbody" style="text-align:center;padding:22px">
      <div style="font-size:2.5rem;margin-bottom:12px">🗑️</div>
      <div style="font-size:.88rem;font-weight:700;margin-bottom:6px" id="cMsg">Are you sure?</div>
      <div style="font-size:.78rem;color:var(--sub)">This is <strong style="color:var(--red)">permanent</strong>. All their orders will also be deleted.</div>
    </div>
    <div class="mftr"><button class="mbtn gh" onclick="closeM('cModal')">Cancel</button><button class="mbtn dn" id="cBtn" onclick="execDel()">🗑️ Yes, Delete</button></div>
  </div>
</div>

<!-- PDF print area -->
<div id="pdfArea"><div class="pdf-doc" id="pdfContent"></div></div>

<div id="toast"></div>

<script>
/* ════════════════════════════════════════
   STATE & HELPERS
════════════════════════════════════════ */
const $=id=>document.getElementById(id);
let allU=[],allO=[],allM=[],allLog=[],viewId=null,delId=null,editOId=null,selStStep=null;
let charts={};
let arOn=false,arTimer=null,arFillTimer=null,arPct=100;
let notifs=[],notifOpen=false;
let sessSeconds=7200; // 2h in seconds

function toast(m,t='ok'){
  const e=$('toast');e.textContent=m;
  e.style.borderColor=t==='err'?'rgba(240,80,96,.4)':'#1a2d47';
  e.style.color=t==='err'?'#ff8090':'#f0f4ff';
  e.classList.add('show');clearTimeout(e._t);e._t=setTimeout(()=>e.classList.remove('show'),3500)
}
function fmtD(s){if(!s)return'—';try{return new Date(s).toLocaleString('en-IN',{day:'2-digit',month:'short',year:'numeric',hour:'2-digit',minute:'2-digit',hour12:true})}catch{return s}}
function fmtDate(s){if(!s)return'';try{return new Date(s).toLocaleDateString('en-IN')}catch{return''}}
function ini(n){return(n||'?').split(' ').map(w=>w[0]).join('').substring(0,2).toUpperCase()}
function spill(s){const L={placed:'🟡 Placed',preparing:'🟠 Preparing',on_the_way:'🔵 On Way',nearby:'🟢 Nearby',delivered:'✅ Done'};const C={placed:'pp',preparing:'ppr',on_the_way:'po',nearby:'pn',delivered:'pd'};return`<span class="pill ${C[s]||'pa'}">${L[s]||s||'—'}</span>`}
function sbar(step){const s=step??0;return`<div class="sbar">${[0,1,2,3,4].map(i=>`<div class="sd ${i<s?'dn':i===s?'ac':''}"></div>`).join('')}<span style="font-size:.61rem;color:var(--sub);margin-left:3px">${s}/4</span></div>`}
function ilist(items){if(!items)return'—';let a;try{a=typeof items==='string'?JSON.parse(items):items}catch{return'—'}if(!Array.isArray(a))return'—';const n=a.map(i=>typeof i==='string'?i:(i.name||'?'));return n.length?n.slice(0,2).join(', ')+(n.length>2?` <span class="mu">+${n.length-2}</span>`:''):'—'}
function inames(items){if(!items)return[];let a;try{a=typeof items==='string'?JSON.parse(items):items}catch{return[]}return Array.isArray(a)?a.map(i=>typeof i==='string'?i:(i.name||'?')):[]}
function csvE(v){const s=String(v||'');return s.includes(',')||s.includes('"')||s.includes('\n')?`"${s.replace(/"/g,'""')}"`:s}
function dlCSV(fn,rows,hdrs){const csv=[hdrs.join(','),...rows.map(r=>r.map(csvE).join(','))].join('\n');const a=document.createElement('a');a.href='data:text/csv;charset=utf-8,'+encodeURIComponent(csv);a.download=fn;a.click();toast(`📤 ${fn} downloaded!`)}
function getSw(id){return $(id)?.classList.contains('on')?1:0}
function setSw(id,v){$(id)?.classList.toggle('on',!!v)}

/* ── Theme ── */
function toggleTheme(){const h=document.documentElement;const isDark=h.dataset.theme==='dark';h.dataset.theme=isDark?'light':'dark';$('themeBtn').textContent=isDark?'🌙':'☀️';// Rebuild charts for theme change
  loadOv()}

/* ── Fullscreen ── */
function toggleFS(){if(!document.fullscreenElement){document.documentElement.requestFullscreen();$('fsBtn').textContent='⛶ Exit'}else{document.exitFullscreen();$('fsBtn').textContent='⛶'}}

/* ── Session Timer ── */
function startSessTimer(){
  const tick=()=>{
    sessSeconds--;
    const h=Math.floor(sessSeconds/3600),m=Math.floor((sessSeconds%3600)/60),s=sessSeconds%60;
    const str=`${h}:${String(m).padStart(2,'0')}:${String(s).padStart(2,'0')}`;
    if($('sessCountdown'))$('sessCountdown').textContent=str;
    const timer=$('sessTimer');
    if(sessSeconds<=600&&timer)timer.classList.add('warn');
    if(sessSeconds<=0){clearInterval(sessIv);location.href='/admin/logout'}
  };
  const sessIv=setInterval(tick,1000);
}
startSessTimer();

/* ── Auto Refresh ── */
function toggleAR(){
  arOn=!arOn;
  const btn=$('arBtn'),bar=$('arBar'),badge=$('arBadge');
  btn.textContent=`↺ Auto: ${arOn?'ON':'OFF'}`;
  btn.classList.toggle('on',arOn);
  bar.classList.toggle('show',arOn);
  badge.classList.toggle('show',arOn);
  if(arOn){startARCycle();pushNotif('⚡ Auto refresh ON — every 30s','✅')}
  else{clearInterval(arTimer);clearInterval(arFillTimer);toast('Auto refresh OFF')}
}
function startARCycle(){
  arPct=100;if($('arFill'))$('arFill').style.width='100%';
  clearInterval(arFillTimer);
  arFillTimer=setInterval(()=>{arPct=Math.max(0,arPct-100/30);if($('arFill'))$('arFill').style.width=arPct+'%'},1000);
  clearInterval(arTimer);
  arTimer=setInterval(async()=>{
    const prev=allO.length;await refreshAll();arPct=100;if($('arFill'))$('arFill').style.width='100%';
    if(allO.length>prev)pushNotif(`📦 ${allO.length-prev} new order(s) received!`,'🔔');
  },30000);
}

/* ── Notifications ── */
function pushNotif(msg,ico='📢'){
  notifs.unshift({msg,ico,time:new Date(),unread:true});
  const cnt=notifs.filter(n=>n.unread).length;
  if($('notifCnt')){$('notifCnt').textContent=cnt;$('notifCnt').classList.toggle('show',cnt>0)}
  renderNotifList();
}
function renderNotifList(){
  if(!$('notifList'))return;
  if(!notifs.length){$('notifList').innerHTML='<div class="notif-empty">No notifications yet</div>';return}
  $('notifList').innerHTML=notifs.slice(0,10).map(n=>`<div class="notif-item ${n.unread?'unread':''}"><div class="notif-ico">${n.ico}</div><div><div class="notif-msg">${n.msg}</div><div class="notif-time">${n.time.toLocaleTimeString('en-IN',{hour:'2-digit',minute:'2-digit',hour12:true})}</div></div></div>`).join('')
}
function toggleNotif(){
  notifOpen=!notifOpen;$('notifPanel').classList.toggle('open',notifOpen);
  if(notifOpen){notifs.forEach(n=>n.unread=false);if($('notifCnt'))$('notifCnt').classList.remove('show')}
}
function clearNotifs(){notifs=[];if($('notifCnt'))$('notifCnt').classList.remove('show');renderNotifList()}
document.addEventListener('click',e=>{
  if(!e.target.closest('.notif-wrap')){notifOpen=false;$('notifPanel')?.classList.remove('open')}
  if(!e.target.closest('.gsearch-wrap')){if($('gSearchResults'))$('gSearchResults').style.display='none'}
  if(e.target.classList.contains('mo'))e.target.classList.remove('open')
});

/* ── Global Search ── */
function doGlobalSearch(q){
  const res=$('gSearchResults');if(!q||q.length<2){res.style.display='none';return}
  res.style.display='block';const f=q.toLowerCase();
  const uRes=allU.filter(u=>(u.name||'').toLowerCase().includes(f)||(u.email||'').toLowerCase().includes(f)).slice(0,4);
  const oRes=allO.filter(o=>(o.id||'').toLowerCase().includes(f)||(o.user_name||'').toLowerCase().includes(f)).slice(0,4);
  const mRes=allM.filter(i=>(i.name||'').toLowerCase().includes(f)).slice(0,3);
  let html='';
  if(!uRes.length&&!oRes.length&&!mRes.length){html='<div class="notif-empty">No results found</div>'}
  if(uRes.length){html+=`<div style="padding:7px 14px 3px;font-size:.6rem;font-weight:800;text-transform:uppercase;color:var(--sub);letter-spacing:.1em">👤 Users</div>`+uRes.map(u=>`<div style="padding:9px 14px;cursor:pointer;display:flex;align-items:center;gap:9px;font-size:.81rem;transition:background .15s" onmouseover="this.style.background='rgba(79,142,247,.07)'" onmouseout="this.style.background=''" onclick="showPanel('users');$('gSearch').value='';$('gSearchResults').style.display='none'"><span>${ini(u.name)}</span><div><div style="font-weight:700">${u.name}</div><div style="font-size:.7rem;color:var(--sub)">${u.email}</div></div></div>`).join('')}
  if(oRes.length){html+=`<div style="padding:7px 14px 3px;font-size:.6rem;font-weight:800;text-transform:uppercase;color:var(--sub);letter-spacing:.1em">📦 Orders</div>`+oRes.map(o=>`<div style="padding:9px 14px;cursor:pointer;display:flex;align-items:center;gap:9px;font-size:.81rem;transition:background .15s" onmouseover="this.style.background='rgba(79,142,247,.07)'" onmouseout="this.style.background=''" onclick="showPanel('orders');$('gSearch').value='';$('gSearchResults').style.display='none'"><span>📦</span><div><div style="font-weight:700;font-family:monospace;font-size:.76rem">${o.id}</div><div style="font-size:.7rem;color:var(--sub)">${o.user_name||''} · ₹${o.total||0}</div></div></div>`).join('')}
  if(mRes.length){html+=`<div style="padding:7px 14px 3px;font-size:.6rem;font-weight:800;text-transform:uppercase;color:var(--sub);letter-spacing:.1em">🍽️ Menu</div>`+mRes.map(m=>`<div style="padding:9px 14px;cursor:pointer;display:flex;align-items:center;gap:9px;font-size:.81rem;transition:background .15s" onmouseover="this.style.background='rgba(79,142,247,.07)'" onmouseout="this.style.background=''" onclick="showPanel('menu');$('gSearch').value='';$('gSearchResults').style.display='none'"><span>${m.emoji||'🍛'}</span><div><div style="font-weight:700">${m.name}</div><div style="font-size:.7rem;color:var(--sub)">₹${m.price} · ${m.category}</div></div></div>`).join('')}
  res.innerHTML=html;
}

/* ── Panel Navigation ── */
function showPanel(n){
  document.querySelectorAll('.panel').forEach(p=>p.classList.remove('active'));
  document.querySelectorAll('.nbtn').forEach(b=>b.classList.remove('active'));
  $(`panel-${n}`)?.classList.add('active');$(`nb-${n}`)?.classList.add('active');
  if(n==='ov')loadOv();if(n==='users')loadUsers();if(n==='orders')loadOrders();
  if(n==='menu')loadMenu();if(n==='log')loadLog();
}

async function refreshAll(){await Promise.all([loadOv(),loadUsers(),loadOrders(),loadMenu()])}

/* ── Charts ── */
function mkChart(id,cfg){if(charts[id])charts[id].destroy();const ctx=$(id);if(!ctx)return;charts[id]=new Chart(ctx,cfg)}
const isDark=()=>document.documentElement.dataset.theme==='dark';
const subC=()=>isDark()?'#5a7a9a':'#94a3b8';
const gridC=()=>isDark()?'rgba(26,45,71,.5)':'rgba(200,210,220,.4)';

/* ── Overview ── */
async function loadOv(){
  try{
    const[sr,or,mr]=await Promise.all([fetch('/api/admin/stats'),fetch('/api/admin/orders'),fetch('/api/admin/menu')]);
    if(sr.status===401){location.href='/admin';return}
    const s=await sr.json(),od=await or.json(),md=await mr.json();
    const orders=od.orders||[],menu=md.items||[];

    $('sGrid').innerHTML=`
      <div class="sc bl"><div class="sn" style="color:var(--blu)">${s.total_users}</div><div class="sl">Total Users</div><div class="si">👤</div></div>
      <div class="sc gr"><div class="sn" style="color:var(--green)">${s.total_orders}</div><div class="sl">Total Orders</div><div class="si">📦</div></div>
      <div class="sc ye"><div class="sn" style="color:var(--yellow);font-size:1.4rem">₹${Number(s.total_revenue||0).toLocaleString('en-IN')}</div><div class="sl">Revenue</div><div class="si">💰</div></div>
      <div class="sc pu"><div class="sn" style="color:var(--purple)">${s.total_menu}</div><div class="sl">Menu Items</div><div class="si">🍽️</div></div>
      <div class="sc gr"><div class="sn" style="color:#86efac">${s.delivered}</div><div class="sl">Delivered</div><div class="si">✅</div></div>
      <div class="sc or"><div class="sn" style="color:var(--orange)">${s.active_orders}</div><div class="sl">Active</div><div class="si">🔄</div></div>
      <div class="sc re"><div class="sn" style="color:#fca5a5">${s.blocked_users||0}</div><div class="sl">Blocked Users</div><div class="si">🚫</div></div>`;

    /* Revenue - 14 days */
    const today=new Date();
    const days14=Array.from({length:14},(_,i)=>{const d=new Date(today);d.setDate(d.getDate()-13+i);return d});
    const dLabels=days14.map(d=>d.toLocaleDateString('en-IN',{day:'2-digit',month:'short'}));
    const dRev=days14.map(d=>{const ds=d.toISOString().substring(0,10);return orders.filter(o=>o.placed_at&&o.placed_at.substring(0,10)===ds).reduce((s,o)=>s+(o.total||0),0)});
    const hasRev=dRev.some(v=>v>0);
    const revData=hasRev?dRev:[80,160,240,180,320,280,400,350,480,420,560,500,640,580];
    mkChart('revChart',{type:'line',data:{labels:dLabels,datasets:[{label:'₹',data:revData,borderColor:'#4f8ef7',backgroundColor:'rgba(79,142,247,.08)',fill:true,tension:.4,pointBackgroundColor:'#4f8ef7',pointRadius:3,pointHoverRadius:6,borderWidth:2.5}]},options:{responsive:true,maintainAspectRatio:false,interaction:{mode:'index',intersect:false},plugins:{legend:{display:false},tooltip:{callbacks:{label:c=>`₹ ${c.parsed.y.toLocaleString('en-IN')}`}}},scales:{x:{ticks:{color:subC(),font:{size:9}},grid:{color:gridC()}},y:{ticks:{color:subC(),font:{size:9},callback:v=>`₹${v}`},grid:{color:gridC()}}}}});

    /* Status doughnut */
    const sc2={placed:0,preparing:0,on_the_way:0,nearby:0,delivered:0};
    orders.forEach(o=>sc2[o.status]=(sc2[o.status]||0)+1);
    mkChart('statusChart',{type:'doughnut',data:{labels:['Placed','Preparing','On the Way','Nearby','Delivered'],datasets:[{data:Object.values(sc2),backgroundColor:['#f5c842','#ff8c42','#4f8ef7','#10d98c','#86efac'],borderWidth:0,hoverOffset:6}]},options:{responsive:true,maintainAspectRatio:false,plugins:{legend:{position:'bottom',labels:{color:subC(),font:{size:9},boxWidth:10,padding:8}}}}});

    /* Veg pie */
    const veg=menu.filter(i=>i.type==='veg').length;
    mkChart('vegChart',{type:'doughnut',data:{labels:['🟢 Veg','🔴 Non-Veg'],datasets:[{data:[veg,menu.length-veg],backgroundColor:['#10d98c','#f05060'],borderWidth:0,hoverOffset:6}]},options:{responsive:true,maintainAspectRatio:false,plugins:{legend:{position:'bottom',labels:{color:subC(),font:{size:10},boxWidth:12,padding:8}}}}});

    /* Most ordered dishes */
    const dc={};orders.forEach(o=>inames(o.items).forEach(n=>{dc[n]=(dc[n]||0)+1}));
    const top6=Object.entries(dc).sort((a,b)=>b[1]-a[1]).slice(0,6);
    mkChart('dishChart',{type:'bar',data:{labels:top6.map(x=>x[0].length>15?x[0].slice(0,15)+'…':x[0]),datasets:[{data:top6.map(x=>x[1]),backgroundColor:['#4f8ef7','#9b6dff','#ff8c42','#10d98c','#f5c842','#f05060'],borderRadius:6,borderWidth:0}]},options:{indexAxis:'y',responsive:true,maintainAspectRatio:false,plugins:{legend:{display:false}},scales:{x:{ticks:{color:subC(),font:{size:9}},grid:{color:gridC()}},y:{ticks:{color:subC(),font:{size:9}},grid:{display:false}}}}});
  }catch(e){console.error(e)}
}

/* ── Users ── */
async function loadUsers(){
  $('uBody').innerHTML=`<tr><td colspan="9"><div class="lb"><div class="sp"></div>Loading…</div></td></tr>`;
  try{
    const r=await fetch('/api/admin/users');if(r.status===401){location.href='/admin';return}
    const d=await r.json();allU=d.users||[];
    $('uCnt').textContent=`${allU.length} users`;$('nc-users').textContent=allU.length;
    renderU(allU);
  }catch(e){$('uBody').innerHTML=`<tr><td colspan="9"><div class="lb" style="color:#ff8090">❌ ${e.message}</div></td></tr>`}
}
function renderU(rows){
  if(!rows.length){$('uBody').innerHTML=`<tr><td colspan="9" style="text-align:center;padding:36px;color:var(--sub)">No users.</td></tr>`;return}
  $('uBody').innerHTML=rows.map((u,i)=>`<tr>
    <td class="mu">${i+1}</td>
    <td><div class="uc"><div class="uav" style="background:linear-gradient(135deg,${u.profile_color||'#1d4ed8'},#0369a1);${u.is_blocked?'opacity:.5':''}">${ini(u.name)}</div>
      <div><div style="font-weight:700">${u.name}</div><div class="mu">ID #${u.id}</div></div></div></td>
    <td><span class="mono">${u.email}</span></td>
    <td>${u.phone||'<span class="mu">—</span>'}</td>
    <td><span class="pill ${u.total_orders>0?'pa':'p0'}">${u.total_orders} order${u.total_orders!==1?'s':''}</span></td>
    <td><strong style="color:var(--yellow)">₹${Number(u.total_spent||0).toLocaleString('en-IN')}</strong></td>
    <td>${u.is_blocked?'<span class="pill pblk">🚫 Blocked</span>':'<span class="pill pd">✅ Active</span>'}</td>
    <td class="mu">${fmtDate(u.created_at)}</td>
    <td><div class="ar2">
      <button class="ab" onclick="openU(${u.id})">🔍</button>
      <button class="ab y" onclick="openEdit(${u.id})">✏️</button>
      <button class="ab" onclick="openPw(${u.id})">🔑</button>
      <button class="ab ${u.is_blocked?'g':'y'}" onclick="toggleBlock(${u.id},${u.is_blocked})">${u.is_blocked?'✅':'🚫'}</button>
      <button class="ab d" onclick="startDel(${u.id},'${u.name.replace(/'/g,"\\'")}')">🗑️</button>
    </div></td>
  </tr>`).join('')
}
function filterU(q){const f=q.toLowerCase();const sf=$('uSF').value;renderU(allU.filter(u=>(!f||(u.name||'').toLowerCase().includes(f)||(u.email||'').toLowerCase().includes(f))&&(!sf||(sf==='blocked'?u.is_blocked:!u.is_blocked))))}
function exportUsersCSV(){if(!allU.length){toast('No data','err');return}dlCSV('users.csv',allU.map(u=>[u.id,u.name,u.email,u.phone||'',u.address||'',u.total_orders,u.total_spent,u.is_blocked?'Blocked':'Active',fmtD(u.created_at)]),['ID','Name','Email','Phone','Address','Orders','Spent','Status','Joined'])}

/* User Detail */
async function openU(uid){
  viewId=uid;$('uMTitle').textContent=`👤 User #${uid}`;$('uMBody').innerHTML=`<div class="lb"><div class="sp"></div>Loading…</div>`;openM('uModal');
  try{
    const r=await fetch(`/api/admin/users/${uid}`);if(!r.ok)throw new Error('Not found');
    const{user}=await r.json();
    const oRows=(user.orders||[]).slice(0,5).map(o=>`<div style="display:flex;justify-content:space-between;align-items:center;padding:7px 0;border-bottom:1px solid rgba(26,45,71,.4);font-size:.77rem;gap:10px">
      <div><span class="mono" style="font-size:.68rem">${o.id}</span><div class="mu">${o.restaurant||'—'}</div></div>
      ${spill(o.status)}
      <div style="text-align:right"><strong style="color:var(--yellow)">₹${o.total}</strong><div class="mu">${fmtDate(o.placed_at)}</div></div>
    </div>`).join('');
    $('uMBody').innerHTML=`
      <div style="display:flex;align-items:center;gap:12px;margin-bottom:15px;padding:13px;background:var(--card2);border-radius:10px;border:1px solid var(--border)">
        <div style="width:44px;height:44px;border-radius:50%;background:linear-gradient(135deg,${user.profile_color||'#1d4ed8'},#0369a1);display:flex;align-items:center;justify-content:center;font-size:.9rem;font-weight:900;color:#fff;flex-shrink:0;border:3px solid var(--border)">${ini(user.name)}</div>
        <div><div style="font-size:.96rem;font-weight:900">${user.name}</div><div class="mono" style="font-size:.73rem">${user.email}</div>
          <div style="margin-top:4px">${user.is_blocked?'<span class="pill pblk">🚫 Blocked</span>':'<span class="pill pd">✅ Active</span>'}</div></div></div>
      <div class="dr"><div class="dl">User ID</div><div class="dv"><span class="mono">#${user.id}</span></div></div>
      <div class="dr"><div class="dl">Phone</div><div class="dv">${user.phone||'Not provided'}</div></div>
      <div class="dr"><div class="dl">Address</div><div class="dv">${user.address||'Not provided'}</div></div>
      <div class="dr"><div class="dl">Total Orders</div><div class="dv">${user.orders?.length||0}</div></div>
      <div class="dr"><div class="dl">Joined</div><div class="dv">${fmtD(user.created_at)}</div></div>
      ${user.orders?.length?`<div style="margin-top:14px;font-size:.66rem;font-weight:800;text-transform:uppercase;letter-spacing:.09em;color:var(--sub);margin-bottom:7px">📦 Recent Orders</div>${oRows}`:
      '<div style="margin-top:12px;text-align:center;color:var(--sub);font-size:.78rem;padding:12px;background:var(--card2);border-radius:8px">No orders yet.</div>'}`;
  }catch(e){$('uMBody').innerHTML=`<div style="color:#ff8090;padding:15px">Error: ${e.message}</div>`}
}

/* Edit user */
function openEdit(uid){const u=allU.find(x=>x.id===uid);if(!u)return;$('eUid').value=uid;$('eName').value=u.name||'';$('ePhone').value=u.phone||'';$('eEmail').value=u.email||'';$('eAddr').value=u.address||'';openM('editModal')}
async function saveEdit(){
  const uid=$('eUid').value,name=$('eName').value.trim(),phone=$('ePhone').value.trim(),email=$('eEmail').value.trim(),addr=$('eAddr').value.trim();
  if(!name||!email.includes('@')){toast('Valid name and email required','err');return}
  try{const r=await fetch(`/api/admin/users/${uid}`,{method:'PUT',headers:{'Content-Type':'application/json'},body:JSON.stringify({name,phone,email,address:addr})});
    const d=await r.json();if(!r.ok){toast(d.error||'Failed','err');return}
    toast('✅ User updated!');closeM('editModal');loadUsers();pushNotif(`✏️ User #${uid} updated`,'✏️')}
  catch(e){toast('Error: '+e.message,'err')}
}

/* Reset password */
function openPw(uid){$('pwUid').value=uid;$('newPw').value='';$('newPwC').value='';openM('pwModal')}
async function saveReset(){
  const uid=$('pwUid').value,pw=$('newPw').value,pwc=$('newPwC').value;
  if(pw.length<6){toast('Password 6+ chars','err');return}if(pw!==pwc){toast('Passwords do not match','err');return}
  try{const r=await fetch(`/api/admin/users/${uid}/reset-password`,{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({new_password:pw})});
    const d=await r.json();if(!r.ok){toast(d.error||'Failed','err');return}
    toast('🔑 Password reset!');closeM('pwModal');pushNotif(`🔑 Password reset for user #${uid}`,'🔑')}
  catch(e){toast('Error: '+e.message,'err')}
}

/* Block/Unblock */
async function toggleBlock(uid,isBlocked){
  try{const r=await fetch(`/api/admin/users/${uid}/block`,{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({action:isBlocked?'unblock':'block'})});
    const d=await r.json();if(!r.ok){toast(d.error||'Failed','err');return}
    toast(isBlocked?'✅ User unblocked!':'🚫 User blocked!');loadUsers();
    pushNotif(isBlocked?`✅ User #${uid} unblocked`:`🚫 User #${uid} blocked`,isBlocked?'✅':'🚫')}
  catch(e){toast('Error: '+e.message,'err')}
}

/* Delete */
function preDel(){if(viewId){const u=allU.find(x=>x.id===viewId);startDel(viewId,u?.name||`#${viewId}`)}}
function startDel(uid,name){delId=uid;$('cMsg').textContent=`Delete "${name}" (ID #${uid})?`;openM('cModal')}
async function execDel(){
  if(!delId)return;$('cBtn').textContent='⏳…';$('cBtn').disabled=true;
  try{const r=await fetch(`/api/admin/users/${delId}`,{method:'DELETE'});const d=await r.json();
    if(!r.ok){toast(d.error||'Failed','err');return}
    toast(`✅ ${d.message}`);closeM('cModal');closeM('uModal');refreshAll();pushNotif(`🗑️ User deleted`,'🗑️')}
  catch(e){toast('Error: '+e.message,'err')}
  finally{$('cBtn').textContent='🗑️ Yes, Delete';$('cBtn').disabled=false;delId=null}
}

/* ── Orders ── */
async function loadOrders(){
  $('oBody').innerHTML=`<tr><td colspan="8"><div class="lb"><div class="sp"></div>Loading…</div></td></tr>`;
  try{const r=await fetch('/api/admin/orders');if(r.status===401){location.href='/admin';return}
    const d=await r.json();allO=d.orders||[];
    $('oCnt').textContent=`${allO.length} orders · ₹${Number(d.total_revenue||0).toLocaleString('en-IN')}`;$('nc-orders').textContent=allO.length;
    renderO(allO)}catch(e){$('oBody').innerHTML=`<tr><td colspan="8"><div class="lb" style="color:#ff8090">❌ ${e.message}</div></td></tr>`}
}
function renderO(orders){
  if(!orders.length){$('oBody').innerHTML=`<tr><td colspan="8" style="text-align:center;padding:36px;color:var(--sub)">No orders.</td></tr>`;return}
  $('oBody').innerHTML=orders.map(o=>`<tr>
    <td><span class="mono">${o.id}</span></td>
    <td><div style="font-weight:700;font-size:.79rem">${o.user_name||'—'}</div><div class="mu">${o.user_email||''}</div></td>
    <td>${spill(o.status)}</td><td>${sbar(o.current_step)}</td>
    <td style="max-width:130px;overflow:hidden;text-overflow:ellipsis;white-space:nowrap">${ilist(o.items)}</td>
    <td><strong style="color:var(--yellow)">₹${(o.total||0).toLocaleString('en-IN')}</strong></td>
    <td class="mu">${fmtDate(o.placed_at)}</td>
    <td><div class="ar2">
      <button class="ab y" onclick="openOSt('${o.id}',${o.current_step||0})" title="Update Status">📦</button>
      <button class="ab" onclick="printInvoice('${o.id}')" title="Print Invoice">🖨️</button>
    </div></td>
  </tr>`).join('')
}
function filterO(){
  const q=($('oSrch')?.value||'').toLowerCase(),sf=$('oSF').value,from=$('dFrom').value,to=$('dTo').value;
  renderO(allO.filter(o=>{
    if(q&&!(o.id||'').toLowerCase().includes(q)&&!(o.user_name||'').toLowerCase().includes(q))return false;
    if(sf&&o.status!==sf)return false;
    if(from&&o.placed_at&&o.placed_at.substring(0,10)<from)return false;
    if(to&&o.placed_at&&o.placed_at.substring(0,10)>to)return false;
    return true
  }))
}
function setDP(p){document.querySelectorAll('.dpill').forEach(b=>b.classList.remove('on'));$(`dp-${p}`)?.classList.add('on');const t=new Date().toISOString().substring(0,10);if(p==='all'){$('dFrom').value='';$('dTo').value=''}else if(p==='today'){$('dFrom').value=t;$('dTo').value=t}else if(p==='week'){const d=new Date();d.setDate(d.getDate()-6);$('dFrom').value=d.toISOString().substring(0,10);$('dTo').value=t}else if(p==='month'){const d=new Date();d.setDate(1);$('dFrom').value=d.toISOString().substring(0,10);$('dTo').value=t}filterO()}
function clearDates(){$('dFrom').value='';$('dTo').value='';setDP('all')}
function exportOrdersCSV(){if(!allO.length){toast('No data','err');return}dlCSV('orders.csv',allO.map(o=>[o.id,o.user_id,o.user_name||'',o.user_email||'',o.status,o.current_step,ilist(o.items).replace(/<[^>]*>/g,''),o.total,o.restaurant,o.address,fmtD(o.placed_at)]),['Order ID','User ID','Name','Email','Status','Step','Items','Total','Restaurant','Address','Placed At'])}

/* Order Status */
function openOSt(oid,step){editOId=oid;selStStep=null;$('oStId').textContent=oid;document.querySelectorAll('.sstep').forEach((el,i)=>{el.classList.toggle('dn',i<step);el.classList.toggle('sel',i===step)});$('oStLbl').textContent='— Select status above —';openM('oStModal')}
function selSt(n){selStStep=n;document.querySelectorAll('.sstep').forEach((el,i)=>el.classList.toggle('sel',i===n));const L=['🧾 Placed','👨‍🍳 Preparing','🛵 On the Way','📍 Nearby','🏠 Delivered'];$('oStLbl').textContent=`Step ${n}: ${L[n]}`}
async function confirmOSt(){
  if(selStStep===null){toast('Select a status first','err');return}
  const o=allO.find(x=>x.id===editOId);if(!o)return;const diff=selStStep-(o.current_step||0);
  if(diff===0){toast('Already at this step','err');return}if(diff<0){toast('Cannot go back','err');return}
  try{for(let i=0;i<diff;i++){const r=await fetch(`/api/admin/orders/${editOId}/step`,{method:'PUT'});if(!r.ok)break}
    toast('✅ Order status updated!');closeM('oStModal');loadOrders();loadOv();pushNotif(`📦 Order ${editOId} status updated`,'📦')}
  catch(e){toast('Error: '+e.message,'err')}
}

/* Invoice Print */
async function printInvoice(oid){
  const o=allO.find(x=>x.id===oid);if(!o){toast('Load orders first','err');return}
  const names=inames(o.items);let items=[];try{items=typeof o.items==='string'?JSON.parse(o.items):o.items}catch{}
  const sub=o.total?Math.round(o.total/1.05):0;const taxes=o.total?o.total-sub:0;const del=sub>=500?0:49;
  $('pdfContent').innerHTML=`
    <div class="pdf-hdr"><div><div class="pdf-brand">🍛 Rasoi<em>Express</em></div><div style="font-size:.77rem;color:#64748b;margin-top:3px">India's Authentic Food Delivery</div></div>
      <div class="pdf-meta"><strong style="font-size:.92rem">INVOICE</strong><br>Order: ${o.id}<br>${fmtD(o.placed_at)}<br>Status: ${(o.status||'').toUpperCase()}</div></div>
    <div style="display:grid;grid-template-columns:1fr 1fr;gap:20px;margin-bottom:18px">
      <div><div class="pdf-stl">From</div><div style="font-size:.81rem;color:#374151">${o.restaurant||'RasoiExpress'}<br>India</div></div>
      <div><div class="pdf-stl">To</div><div style="font-size:.81rem;color:#374151">${o.user_name||'Customer'}<br>${o.address||'—'}</div></div></div>
    <div class="pdf-stl">Items Ordered</div>
    ${names.map((n,i)=>{const it=Array.isArray(items)&&typeof items[i]==='object'?items[i]:null;const p=it?.price||0;const q=it?.qty||1;return`<div class="pdf-row"><span>${n}${q>1?` × ${q}`:''}</span><span>${p?`₹${(p*q).toLocaleString('en-IN')}`:''}</span></div>`}).join('')}
    <div class="pdf-stl" style="margin-top:14px">Bill Summary</div>
    <div class="pdf-row"><span>Subtotal</span><span>₹${sub.toLocaleString('en-IN')}</span></div>
    <div class="pdf-row"><span>Delivery Fee</span><span>${del===0?'FREE':'₹'+del}</span></div>
    <div class="pdf-row"><span>GST (5%)</span><span>₹${Math.round(taxes).toLocaleString('en-IN')}</span></div>
    <div class="pdf-total"><span>Total Paid</span><span>₹${(o.total||0).toLocaleString('en-IN')}</span></div>
    <div class="pdf-footer">Thank you for ordering from RasoiExpress 🍛 · support@rasoiexpress.in</div>`;
  $('pdfArea').style.display='block';window.print();setTimeout(()=>$('pdfArea').style.display='none',1000)
}

/* ── Menu ── */
async function loadMenu(){
  $('mBody').innerHTML=`<tr><td colspan="8"><div class="lb"><div class="sp"></div>Loading…</div></td></tr>`;
  try{const r=await fetch('/api/admin/menu');if(r.status===401){location.href='/admin';return}
    const d=await r.json();allM=d.items||[];
    $('mCnt').textContent=`${allM.length} dishes`;$('nc-menu').textContent=allM.length;
    const cats=[...new Set(allM.map(i=>i.category))].sort();
    $('mCF').innerHTML=`<option value="">All</option>`+cats.map(c=>`<option value="${c}">${c}</option>`).join('');
    renderM(allM)}catch(e){$('mBody').innerHTML=`<tr><td colspan="8"><div class="lb" style="color:#ff8090">❌ ${e.message}</div></td></tr>`}
}
function renderM(items){
  if(!items.length){$('mBody').innerHTML=`<tr><td colspan="8" style="text-align:center;padding:36px;color:var(--sub)">No items.</td></tr>`;return}
  $('mBody').innerHTML=items.map(it=>`<tr>
    <td class="mu">${it.id}</td>
    <td><div style="display:flex;align-items:center;gap:8px"><span style="font-size:1.1rem">${it.emoji||'🍛'}</span>
      <div><div style="font-weight:700">${it.name}</div><div class="mu" style="max-width:140px;overflow:hidden;text-overflow:ellipsis;white-space:nowrap">${it.description||''}</div></div></div></td>
    <td><span class="pill pa">${it.category}</span></td>
    <td><span class="pill ${it.type==='veg'?'pd':'re'}">${it.type==='veg'?'🟢 Veg':'🔴 Non-Veg'}</span></td>
    <td><strong style="color:var(--yellow)">₹${it.price}</strong></td>
    <td><span style="color:var(--yellow)">★</span> ${it.rating}</td>
    <td>${it.available?'<span class="pill pd">✅ On</span>':'<span class="pill p0">❌ Off</span>'}</td>
    <td><div class="ar2">
      <button class="ab y" onclick="openEditDish(${it.id})">✏️</button>
      <button class="ab ${it.available?'d':'g'}" onclick="toggleDish(${it.id},${it.available})">${it.available?'🚫':'✅'}</button>
      <button class="ab d" onclick="delDish(${it.id},'${it.name.replace(/'/g,"\\'")}')">🗑️</button>
    </div></td>
  </tr>`).join('')
}
function filterM(q){const f=(q||'').toLowerCase();const cat=$('mCF').value;renderM(allM.filter(i=>(!cat||i.category===cat)&&(!f||(i.name||'').toLowerCase().includes(f))))}
function openAddDish(){$('dMTitle').textContent='➕ Add New Dish';$('dId').value='';['dName','dDesc','dRest','dTime'].forEach(id=>$(id).value='');$('dEmoji').value='🍛';$('dPrice').value='';$('dRating').value='4.5';$('dTime').value='30 mins';$('dCat').value='';$('dType').value='veg';setSw('swBest',0);setSw('swNew',0);setSw('swSpicy',0);openM('dishModal')}
async function openEditDish(id){let it=allM.find(i=>i.id===id);
  if(!it){try{const r=await fetch(`/api/admin/menu/${id}`);if(r.ok){const d=await r.json();it=d.item}}catch{}}
  if(!it)return;$('dMTitle').textContent='✏️ Edit Dish';$('dId').value=it.id;$('dName').value=it.name||'';$('dDesc').value=it.description||'';$('dPrice').value=it.price||'';$('dRating').value=it.rating||'';$('dRest').value=it.restaurant||'';$('dTime').value=it.time||'';$('dEmoji').value=it.emoji||'🍛';$('dCat').value=it.category||'';$('dType').value=it.type||'veg';setSw('swBest',it.is_best);setSw('swNew',it.is_new);setSw('swSpicy',it.is_spicy);openM('dishModal')}
async function saveDish(){
  const id=$('dId').value,name=$('dName').value.trim(),price=parseFloat($('dPrice').value),cat=$('dCat').value;
  if(!name||!price||price<=0||!cat){toast('Name, price and category required','err');return}
  const body={name,description:$('dDesc').value.trim(),price,category:cat,type:$('dType').value,restaurant:$('dRest').value.trim(),rating:parseFloat($('dRating').value)||4.5,emoji:$('dEmoji').value||'🍛',time:$('dTime').value||'30 mins',is_best:getSw('swBest'),is_new:getSw('swNew'),is_spicy:getSw('swSpicy'),available:1};
  const url=id?`/api/admin/menu/${id}`:'/api/admin/menu';const method=id?'PUT':'POST';
  try{const r=await fetch(url,{method,headers:{'Content-Type':'application/json'},body:JSON.stringify(body)});
    const d=await r.json();if(!r.ok){toast(d.error||'Failed','err');return}
    toast(id?`✅ "${name}" updated!`:`✅ "${name}" added!`);closeM('dishModal');loadMenu();loadOv();
    pushNotif(id?`✏️ Dish "${name}" updated`:`➕ Dish "${name}" added`,id?'✏️':'➕')}
  catch(e){toast('Error: '+e.message,'err')}
}
async function toggleDish(id,cur){try{const r=await fetch(`/api/admin/menu/${id}`,{method:'PUT',headers:{'Content-Type':'application/json'},body:JSON.stringify({available:cur?0:1})});if(!r.ok)throw new Error();toast(cur?'🚫 Dish hidden':'✅ Dish visible');loadMenu()}catch{toast('Failed','err')}}
async function delDish(id,name){if(!confirm(`Delete "${name}"?`))return;try{const r=await fetch(`/api/admin/menu/${id}`,{method:'DELETE'});if(!r.ok)throw new Error();toast(`🗑️ "${name}" deleted`);loadMenu();loadOv()}catch{toast('Failed','err')}}

/* ── Seed Menu ── */
async function seedMenu(){
  const btn=$('nb-seed');btn.disabled=true;
  btn.textContent='⏳ Seeding…';
  try{
    // First try normal seed
    let r=await fetch('/api/menu/seed',{method:'POST'});
    let d=await r.json();
    // If already seeded with old count, force re-seed
    if(d.message&&d.message.includes('Already seeded')&&!d.message.includes('315')){
      if(confirm('Menu has old data. Re-seed with 315 dishes?')){
        r=await fetch('/api/menu/seed?force=1',{method:'POST'});
        d=await r.json();
      }
    }
    toast('🌱 '+(d.message||'Seeded!'));
    loadMenu(1);loadOv();
  }catch{toast('Seed failed','err')}
  finally{btn.disabled=false;btn.textContent='🌱 Seed Menu'}
}

/* ── Activity Log ── */
async function loadLog(){
  $('logWrap').innerHTML=`<div class="lb"><div class="sp"></div>Loading activity log…</div>`;
  try{const r=await fetch('/api/admin/log');const d=await r.json();allLog=d.logs||[];
    $('logCnt').textContent=`${allLog.length} entries`;renderLog(allLog)}
  catch(e){$('logWrap').innerHTML=`<div style="color:#ff8090">❌ ${e.message}</div>`}
}
function renderLog(logs){
  if(!logs.length){$('logWrap').innerHTML=`<div style="text-align:center;padding:36px;color:var(--sub)">No activity recorded yet.</div>`;return}
  const icons={'Admin Login':'🔑','Admin Logout':'🚪','User Deleted':'🗑️','User Updated':'✏️','Password Reset':'🔑','User Blocked':'🚫','User Unblocked':'✅','Dish Added':'➕','Dish Updated':'✏️','Dish Deleted':'🗑️','Order Updated':'📦'};
  $('logWrap').innerHTML=logs.map(l=>`<div class="log-item">
    <div class="log-ico">${icons[l.action]||'📋'}</div>
    <div style="flex:1"><div class="log-action">${l.action}</div><div class="log-detail">${l.details||''} ${l.ip?`• IP: ${l.ip}`:''}</div></div>
    <div class="log-time">${fmtD(l.logged_at)}</div>
  </div>`).join('')
}
function filterLog(q){const f=q.toLowerCase();renderLog(allLog.filter(l=>(l.action||'').toLowerCase().includes(f)||(l.details||'').toLowerCase().includes(f)))}
async function clearLog(){if(!confirm('Clear all activity logs?'))return;try{const r=await fetch('/api/admin/log',{method:'DELETE'});if(!r.ok)throw new Error();toast('🗑️ Activity log cleared');loadLog()}catch{toast('Failed','err')}}

/* ── PDF Reports ── */
function printReport(type){
  let html='';
  const now=new Date().toLocaleString('en-IN');
  const hdr=`<div class="pdf-hdr"><div><div class="pdf-brand">🍛 Rasoi<em>Express</em></div><div style="font-size:.77rem;color:#64748b">Admin Report — Generated ${now}</div></div><div class="pdf-meta"><strong>${type.toUpperCase()} REPORT</strong></div></div>`;
  if(type==='summary'){
    const total=allO.reduce((s,o)=>s+(o.total||0),0);const del=allO.filter(o=>o.status==='delivered').length;
    html=hdr+`<div class="pdf-stl">Platform Summary</div>
      <div class="pdf-row"><span>Total Registered Users</span><span>${allU.length}</span></div>
      <div class="pdf-row"><span>Total Orders Placed</span><span>${allO.length}</span></div>
      <div class="pdf-row"><span>Orders Delivered</span><span>${del}</span></div>
      <div class="pdf-row"><span>Active Orders</span><span>${allO.length-del}</span></div>
      <div class="pdf-row"><span>Total Menu Items</span><span>${allM.length}</span></div>
      <div class="pdf-total"><span>Total Revenue</span><span>₹${total.toLocaleString('en-IN')}</span></div>
      <div class="pdf-footer">RasoiExpress Admin Report</div>`;
  } else if(type==='users'){
    html=hdr+`<div class="pdf-stl">All Registered Users (${allU.length})</div>`+
      allU.map(u=>`<div class="pdf-row"><span>#${u.id} ${u.name} (${u.email})</span><span>${u.total_orders} orders · ₹${u.total_spent}</span></div>`).join('')+
      `<div class="pdf-footer">Total Users: ${allU.length}</div>`;
  } else if(type==='orders'){
    const total=allO.reduce((s,o)=>s+(o.total||0),0);
    html=hdr+`<div class="pdf-stl">All Orders (${allO.length})</div>`+
      allO.map(o=>`<div class="pdf-row"><span>${o.id} — ${o.user_name||'—'}</span><span>${o.status} · ₹${o.total}</span></div>`).join('')+
      `<div class="pdf-total"><span>Total Revenue</span><span>₹${total.toLocaleString('en-IN')}</span></div>
      <div class="pdf-footer">Total Orders: ${allO.length}</div>`;
  }
  $('pdfContent').innerHTML=html;$('pdfArea').style.display='block';window.print();setTimeout(()=>$('pdfArea').style.display='none',1000)
}

/* ── Modals ── */
function openM(id){$(id).classList.add('open')}
function closeM(id){$(id).classList.remove('open');viewId=null}

/* ── Boot ── */
pushNotif('🎉 Admin Panel loaded!','🎉');
refreshAll();
</script>
</body></html>"""

# ═══════════════════════════════════════════════════════════════
#  ADMIN ROUTES
# ═══════════════════════════════════════════════════════════════
def get_ip(): return request.remote_addr or "unknown"

@app.route("/admin")
def admin_page():
    if session.get(ADMIN_SESSION_KEY): return redirect("/admin/dashboard")
    ip = get_ip()
    info = login_attempts.get(ip, {"count": 0, "locked_until": None})
    locked = info.get("locked_until") and info["locked_until"] > datetime.now()
    lock_seconds = max(0, int((info.get("locked_until", datetime.now()) - datetime.now()).total_seconds())) if locked else 0
    return render_template_string(LOGIN_HTML,
        error=None, username="", attempts_used=info.get("count", 0),
        attempts_left=MAX_LOGIN_ATTEMPTS - info.get("count", 0),
        locked=locked, lock_seconds=lock_seconds)

@app.route("/admin/login", methods=["POST"])
def admin_login():
    ip = get_ip()
    info = login_attempts.get(ip, {"count": 0, "locked_until": None})

    # Check if locked
    if info.get("locked_until") and info["locked_until"] > datetime.now():
        remaining = int((info["locked_until"] - datetime.now()).total_seconds())
        return render_template_string(LOGIN_HTML, error=None, username="",
            attempts_used=MAX_LOGIN_ATTEMPTS, attempts_left=0, locked=True, lock_seconds=remaining), 429

    username = (request.form.get("username") or "").strip()
    password = (request.form.get("password") or "")
    ok = (username == ADMIN_ID and hashlib.sha256(password.encode()).hexdigest() == ADMIN_PASS_HASH)

    if not ok:
        info["count"] = info.get("count", 0) + 1
        if info["count"] >= MAX_LOGIN_ATTEMPTS:
            info["locked_until"] = datetime.now() + timedelta(minutes=5)
            info["count"] = MAX_LOGIN_ATTEMPTS
            log_action("Login Blocked", f"IP {ip} locked after {MAX_LOGIN_ATTEMPTS} failed attempts")
        else:
            log_action("Failed Login", f"Username: {username}, IP: {ip}, Attempt: {info['count']}")
        login_attempts[ip] = info
        locked = info.get("locked_until") and info["locked_until"] > datetime.now()
        lock_seconds = int((info["locked_until"] - datetime.now()).total_seconds()) if locked else 0
        error_msg = f"Access Denied — {MAX_LOGIN_ATTEMPTS - info['count']} attempt(s) remaining." if not locked else "Account locked for 5 minutes."
        return render_template_string(LOGIN_HTML, error=error_msg, username=username,
            attempts_used=info["count"], attempts_left=max(0, MAX_LOGIN_ATTEMPTS - info["count"]),
            locked=locked, lock_seconds=lock_seconds), 401

    # Success — clear attempts
    login_attempts.pop(ip, None)
    session.clear()
    session[ADMIN_SESSION_KEY] = True
    session["admin"] = ADMIN_ID
    session["login_time"] = datetime.now().strftime("%I:%M %p, %d %b %Y")
    session.permanent = True
    log_action("Admin Login", f"Successful login from IP: {ip}")
    return redirect("/admin/dashboard")

@app.route("/admin/dashboard")
@admin_page_required
def admin_dashboard():
    return render_template_string(DASH_HTML, login_time=session.get("login_time", "—"))

@app.route("/admin/logout")
def admin_logout():
    log_action("Admin Logout", f"IP: {get_ip()}")
    session.clear(); return redirect("/admin")

# ─── Admin API ───────────────────────────────────────────────
@app.route("/api/health")
def health(): return jsonify({"status": "ok", "msg": "RasoiExpress 🍛"})

@app.route("/api/admin/stats")
@admin_required
def admin_stats():
    return jsonify({
        "total_users":   q1("SELECT COUNT(*) AS c FROM users")["c"],
        "total_orders":  q1("SELECT COUNT(*) AS c FROM orders")["c"],
        "total_menu":    q1("SELECT COUNT(*) AS c FROM menu_items WHERE available=1")["c"],
        "total_revenue": round(q1("SELECT COALESCE(SUM(total),0) AS r FROM orders")["r"], 2),
        "delivered":     q1("SELECT COUNT(*) AS c FROM orders WHERE status='delivered'")["c"],
        "active_orders": q1("SELECT COUNT(*) AS c FROM orders WHERE status!='delivered'")["c"],
        "blocked_users": q1("SELECT COUNT(*) AS c FROM users WHERE is_blocked=1")["c"],
    })

@app.route("/api/admin/users")
@admin_required
def admin_users():
    users = qa("""SELECT u.id,u.name,u.email,u.phone,u.address,u.profile_color,u.is_blocked,u.created_at,
                         COUNT(o.id) AS total_orders, COALESCE(SUM(o.total),0) AS total_spent
                  FROM users u LEFT JOIN orders o ON o.user_id=u.id
                  GROUP BY u.id ORDER BY u.created_at DESC""")
    return jsonify({"users": users, "count": len(users)})

@app.route("/api/admin/users/<int:uid>")
@admin_required
def admin_user_detail(uid):
    user = q1("SELECT id,name,email,phone,address,profile_color,is_blocked,created_at FROM users WHERE id=?", (uid,))
    if not user: return jsonify({"error": "Not found"}), 404
    orders = qa("SELECT id,items,total,restaurant,address,status,current_step,placed_at FROM orders WHERE user_id=? ORDER BY placed_at DESC", (uid,))
    for o in orders:
        try: o["items"] = json.loads(o["items"])
        except: o["items"] = []
    user["orders"] = orders
    return jsonify({"user": user})

@app.route("/api/admin/users/<int:uid>", methods=["PUT"])
@admin_required
def admin_edit_user(uid):
    d = request.get_json() or {}
    user = q1("SELECT * FROM users WHERE id=?", (uid,))
    if not user: return jsonify({"error": "Not found"}), 404
    name  = (d.get("name")    or user["name"]).strip()
    phone = (d.get("phone")   or user["phone"] or "").strip()
    email = (d.get("email")   or user["email"]).strip().lower()
    addr  = (d.get("address") or user["address"] or "").strip()
    if not name or "@" not in email: return jsonify({"error": "Valid name and email required"}), 400
    ex = q1("SELECT id FROM users WHERE email=? AND id!=?", (email, uid))
    if ex: return jsonify({"error": "Email already in use"}), 400
    run("UPDATE users SET name=?,phone=?,email=?,address=? WHERE id=?", (name, phone, email, addr, uid))
    log_action("User Updated", f"User #{uid} ({name})")
    return jsonify({"message": "User updated."})

@app.route("/api/admin/users/<int:uid>/reset-password", methods=["POST"])
@admin_required
def admin_reset_pw(uid):
    d = request.get_json() or {}
    pw = d.get("new_password", "")
    if len(pw) < 6: return jsonify({"error": "Password 6+ chars"}), 400
    user = q1("SELECT id,name FROM users WHERE id=?", (uid,))
    if not user: return jsonify({"error": "Not found"}), 404
    run("UPDATE users SET password=? WHERE id=?", (hash_pw(pw), uid))
    log_action("Password Reset", f"User #{uid} ({user['name']})")
    return jsonify({"message": f"Password reset for #{uid}."})

@app.route("/api/admin/users/<int:uid>/block", methods=["POST"])
@admin_required
def admin_toggle_block(uid):
    d = request.get_json() or {}
    action = d.get("action", "block")
    user = q1("SELECT id,name FROM users WHERE id=?", (uid,))
    if not user: return jsonify({"error": "Not found"}), 404
    blocked = 1 if action == "block" else 0
    run("UPDATE users SET is_blocked=? WHERE id=?", (blocked, uid))
    log_action(f"User {'Blocked' if blocked else 'Unblocked'}", f"User #{uid} ({user['name']})")
    return jsonify({"message": f"User {'blocked' if blocked else 'unblocked'}."})

@app.route("/api/admin/users/<int:uid>", methods=["DELETE"])
@admin_required
def admin_delete_user(uid):
    user = q1("SELECT id,name FROM users WHERE id=?", (uid,))
    if not user: return jsonify({"error": "Not found"}), 404
    run("DELETE FROM orders WHERE user_id=?", (uid,))
    run("DELETE FROM users  WHERE id=?", (uid,))
    log_action("User Deleted", f"User #{uid} ({user['name']})")
    return jsonify({"message": f"User '{user['name']}' deleted."})

@app.route("/api/admin/orders")
@admin_required
def admin_orders():
    orders = qa("""SELECT o.id,o.user_id,o.items,o.total,o.restaurant,o.address,
                          o.status,o.current_step,o.placed_at,
                          u.name AS user_name, u.email AS user_email
                   FROM orders o LEFT JOIN users u ON u.id=o.user_id
                   ORDER BY o.placed_at DESC""")
    for o in orders:
        try: raw = json.loads(o["items"]); o["items"] = [i if isinstance(i, str) else i.get("name", "?") for i in raw]
        except: o["items"] = []
    return jsonify({"orders": orders, "count": len(orders),
                    "total_revenue": round(sum(o["total"] or 0 for o in orders), 2)})

@app.route("/api/admin/orders/<oid>/step", methods=["PUT"])
@admin_required
def admin_step(oid):
    SM = {0:"placed",1:"preparing",2:"on_the_way",3:"nearby",4:"delivered"}
    o = q1("SELECT * FROM orders WHERE id=?", (oid,))
    if not o: return jsonify({"error": "Not found"}), 404
    ns = min((o["current_step"] or 0) + 1, 4)
    run("UPDATE orders SET current_step=?,status=? WHERE id=?", (ns, SM[ns], oid))
    log_action("Order Updated", f"Order {oid} → {SM[ns]}")
    return jsonify({"message": SM[ns].replace("_"," ").title(), "current_step": ns})

@app.route("/api/admin/menu")
@admin_required
def admin_menu():
    page  = max(1, request.args.get("page", 1, type=int))
    limit = min(100, max(20, request.args.get("limit", 60, type=int)))
    cat   = request.args.get("category", "")
    srch  = request.args.get("search", "").lower()

    sql, p = "SELECT * FROM menu_items WHERE 1=1", []
    if cat: sql += " AND category=?"; p.append(cat)
    if srch: sql += " AND LOWER(name) LIKE ?"; p.append(f"%{srch}%")
    sql += " ORDER BY category, name"

    total = q1(sql.replace("SELECT *","SELECT COUNT(*) AS c",1), p)["c"]
    sql  += f" LIMIT {limit} OFFSET {(page-1)*limit}"
    items = qa(sql, p)
    for i in items:
        i["is_spicy"] = bool(i["is_spicy"])
        i["is_new"]   = bool(i["is_new"])
        i["is_best"]  = bool(i["is_best"])
    return jsonify({
        "items": items, "count": len(items),
        "total": total, "page": page, "limit": limit,
        "total_pages": (total+limit-1)//limit,
        "has_next": page*limit < total,
    })

@app.route("/api/admin/menu", methods=["POST"])
@admin_required
def admin_add_dish():
    d = request.get_json() or {}
    name = d.get("name","").strip(); price = d.get("price",0); cat = d.get("category","")
    if not name or not price or not cat: return jsonify({"error": "Name, price, category required"}), 400
    uid = run("INSERT INTO menu_items(name,description,price,category,type,restaurant,rating,emoji,time,is_best,is_new,is_spicy,available) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,1)",
        (name,d.get("description",""),price,cat,d.get("type","veg"),d.get("restaurant",""),d.get("rating",4.5),d.get("emoji","🍛"),d.get("time","30 mins"),d.get("is_best",0),d.get("is_new",0),d.get("is_spicy",0)))
    log_action("Dish Added", f"'{name}' in {cat}")
    return jsonify({"message": f"'{name}' added.", "id": uid}), 201

@app.route("/api/admin/menu/<int:mid>", methods=["PUT"])
@admin_required
def admin_update_dish(mid):
    d = request.get_json() or {}
    item = q1("SELECT * FROM menu_items WHERE id=?", (mid,))
    if not item: return jsonify({"error": "Not found"}), 404
    fields = [("name",d.get("name",item["name"])),("description",d.get("description",item["description"])),
              ("price",d.get("price",item["price"])),("category",d.get("category",item["category"])),
              ("type",d.get("type",item["type"])),("restaurant",d.get("restaurant",item["restaurant"])),
              ("rating",d.get("rating",item["rating"])),("emoji",d.get("emoji",item["emoji"])),
              ("time",d.get("time",item["time"])),("is_best",d.get("is_best",item["is_best"])),
              ("is_new",d.get("is_new",item["is_new"])),("is_spicy",d.get("is_spicy",item["is_spicy"])),
              ("available",d.get("available",item["available"]))]
    run("UPDATE menu_items SET "+",".join(f"{k}=?" for k,_ in fields)+" WHERE id=?", [v for _,v in fields]+[mid])
    log_action("Dish Updated", f"ID #{mid}")
    return jsonify({"message": "Dish updated."})

@app.route("/api/admin/menu/<int:mid>", methods=["DELETE"])
@admin_required
def admin_delete_dish(mid):
    item = q1("SELECT id,name FROM menu_items WHERE id=?", (mid,))
    if not item: return jsonify({"error": "Not found"}), 404
    run("DELETE FROM menu_items WHERE id=?", (mid,))
    log_action("Dish Deleted", f"'{item['name']}'")
    return jsonify({"message": f"'{item['name']}' deleted."})

@app.route("/api/admin/log")
@admin_required
def get_log():
    logs = qa("SELECT * FROM activity_log ORDER BY id DESC LIMIT 200")
    return jsonify({"logs": logs, "count": len(logs)})

@app.route("/api/admin/log", methods=["DELETE"])
@admin_required
def clear_log():
    run("DELETE FROM activity_log")
    return jsonify({"message": "Activity log cleared."})

# ═══════════════════════════════════════════════════════════════
#  USER AUTH  (JWT)
# ═══════════════════════════════════════════════════════════════
@app.route("/api/auth/signup", methods=["POST"])
def signup():
    d=request.get_json() or {}
    name=(d.get("name") or "").strip(); email=(d.get("email") or "").strip().lower(); pw=(d.get("password") or "")
    if not name: return jsonify({"error":"Name required"}),400
    if "@" not in email: return jsonify({"error":"Valid email required"}),400
    if len(pw)<6: return jsonify({"error":"Password 6+ chars"}),400
    if q1("SELECT id FROM users WHERE email=?",(email,)): return jsonify({"error":"Email already registered"}),400
    uid=run("INSERT INTO users(name,email,password) VALUES(?,?,?)",(name,email,hash_pw(pw)))
    return jsonify({"message":f"Welcome, {name.split()[0]}! 🎉","token":make_token(uid,email),
                    "user":{"id":uid,"name":name,"email":email,"picture":"","profile_color":"#1A6FB3","phone":"","address":""}}),201

@app.route("/api/auth/login", methods=["POST"])
def user_login():
    d=request.get_json() or {}; email=(d.get("email") or "").strip().lower(); pw=(d.get("password") or "")
    if not email or not pw: return jsonify({"error":"Email and password required"}),400
    user=q1("SELECT * FROM users WHERE email=?",(email,))
    if not user or not check_pw(pw,user["password"]): return jsonify({"error":"Invalid email or password"}),401
    if user.get("is_blocked"): return jsonify({"error":"Account blocked. Contact support."}),403
    return jsonify({"message":f"Welcome back, {user['name'].split()[0]}! 🎉","token":make_token(user["id"],user["email"]),
                    "user":{"id":user["id"],"name":user["name"],"email":user["email"],
                            "picture":user["picture"] or "","profile_color":user["profile_color"] or "#1A6FB3",
                            "phone":user["phone"] or "","address":user["address"] or ""}})

@app.route("/api/auth/me")
@jwt_required
def me(cu):
    user=q1("SELECT id,name,email,phone,address,picture,profile_color FROM users WHERE id=? AND is_blocked=0",(cu["user_id"],))
    if not user: return jsonify({"error":"Not found or blocked"}),404
    cnt=q1("SELECT COUNT(*) as c FROM orders WHERE user_id=?",(cu["user_id"],))
    user["total_orders"]=cnt["c"] if cnt else 0
    return jsonify({"user":user})

@app.route("/api/auth/logout", methods=["POST"])
def user_logout(): return jsonify({"message":"Logged out"})

@app.route("/api/menu/items")
def menu_items():
    cat   = request.args.get("category","")
    dt    = request.args.get("type","")
    srch  = request.args.get("search","").lower()
    sort  = request.args.get("sort","popular")
    mp    = request.args.get("max_price", type=int)
    page  = max(1, request.args.get("page", 1, type=int))
    limit = min(100, max(10, request.args.get("limit", 50, type=int)))

    sql, p = "SELECT * FROM menu_items WHERE available=1", []
    if cat and cat.lower() not in ("all",""):
        sql += " AND category=?"; p.append(cat)
    if dt in ("veg","nonveg"):
        sql += " AND type=?"; p.append(dt)
    if srch:
        sql += " AND (LOWER(name) LIKE ? OR LOWER(description) LIKE ?)"; p += [f"%{srch}%", f"%{srch}%"]
    if mp:
        sql += " AND price<=?"; p.append(mp)
    sql += {"popular":" ORDER BY is_best DESC,rating DESC",
            "price-asc":" ORDER BY price ASC",
            "price-desc":" ORDER BY price DESC",
            "rating":" ORDER BY rating DESC",
            "newest":" ORDER BY id DESC"}.get(sort, " ORDER BY is_best DESC,rating DESC")

    # Total count for pagination
    count_sql = sql.replace("SELECT *", "SELECT COUNT(*) AS c", 1)
    total = q1(count_sql, p)["c"]

    # Apply pagination
    sql += f" LIMIT {limit} OFFSET {(page-1)*limit}"
    items = qa(sql, p)
    for i in items:
        i["is_spicy"] = bool(i["is_spicy"])
        i["is_new"]   = bool(i["is_new"])
        i["is_best"]  = bool(i["is_best"])

    return jsonify({
        "items":       items,
        "count":       len(items),
        "total":       total,
        "page":        page,
        "limit":       limit,
        "total_pages": (total + limit - 1) // limit,
        "has_next":    page * limit < total,
        "has_prev":    page > 1,
    })

@app.route("/api/menu/seed", methods=["POST"])
def seed_menu():
    force = request.args.get("force","") == "1"
    ex = q1("SELECT COUNT(*) as c FROM menu_items")
    if ex and ex["c"] > 0 and not force:
        return jsonify({"message": f"Already seeded with {ex['c']} dishes. Use ?force=1 to re-seed."})
    if force:
        run("DELETE FROM menu_items")
    for d in SAMPLE_DISHES:
        run("INSERT INTO menu_items(name,description,price,category,type,restaurant,rating,image,emoji,is_spicy,is_new,is_best,time) VALUES(%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s) ON CONFLICT DO NOTHING", d)
    c = q1("SELECT COUNT(*) as c FROM menu_items")["c"]
    return jsonify({"message": f"✅ Menu seeded with {c} dishes!"}), 201

SM={0:"placed",1:"preparing",2:"on_the_way",3:"nearby",4:"delivered"}

@app.route("/api/orders/place", methods=["POST"])
@jwt_required
def place_order(cu):
    d=request.get_json() or {}; items=d.get("items",[]); addr=(d.get("address") or "").strip()
    if not items: return jsonify({"error":"Cart empty"}),400
    if not addr: return jsonify({"error":"Address required"}),400
    sub=sum(i.get("price",0)*i.get("qty",1) for i in items); dl=0 if sub>=500 else 49; tax=round(sub*.05); tot=sub+dl+tax
    oid=f"RE-{datetime.now().year}-{''.join(random.choices(string.ascii_uppercase+string.digits,k=8))}"
    rest=items[0].get("restaurant","") if items else ""
    run("INSERT INTO orders(id,user_id,items,total,restaurant,address,status,current_step) VALUES(?,?,?,?,?,?,'placed',0)",(oid,cu["user_id"],json.dumps(items),tot,rest,addr))
    now=datetime.now()
    return jsonify({"message":f"Order {oid} placed! 🎉","order":{"id":oid,"status":"placed","current_step":0,"eta":"30 mins","items":[i.get("name","") for i in items],"restaurant":rest,"time":now.strftime("%I:%M %p"),"total":tot,"subtotal":sub,"delivery":dl,"taxes":tax,"address":addr,"placed_at":now.isoformat()}}),201

@app.route("/api/orders/my-orders")
@jwt_required
def my_orders(cu):
    rows=qa("SELECT * FROM orders WHERE user_id=? ORDER BY placed_at DESC",(cu["user_id"],))
    for r in rows:
        try: r["items"]=json.loads(r["items"])
        except: r["items"]=[]
    return jsonify({"orders":rows,"count":len(rows)})

@app.route("/api/orders/<oid>")
@jwt_required
def get_order(oid,cu):
    o=q1("SELECT * FROM orders WHERE id=? AND user_id=?",(oid,cu["user_id"]))
    if not o: return jsonify({"error":"Not found"}),404
    try: o["items"]=json.loads(o["items"])
    except: o["items"]=[]
    return jsonify({"order":o})

@app.route("/api/orders/<oid>/step", methods=["PUT"])
@jwt_required
def step(oid,cu):
    o=q1("SELECT * FROM orders WHERE id=? AND user_id=?",(oid,cu["user_id"]))
    if not o: return jsonify({"error":"Not found"}),404
    s=(o["current_step"] or 0); ns=min(s+1,4)
    run("UPDATE orders SET current_step=?,status=? WHERE id=?",(ns,SM[ns],oid))
    return jsonify({"message":SM[ns].replace("_"," ").title(),"current_step":ns,"status":SM[ns]})

@app.route("/api/profile")
@jwt_required
def get_profile(cu):
    u=q1("SELECT id,name,email,phone,address,picture,profile_color FROM users WHERE id=?",(cu["user_id"],))
    if not u: return jsonify({"error":"Not found"}),404
    s=q1("SELECT COUNT(*) as t,COALESCE(SUM(total),0) as sp FROM orders WHERE user_id=?",(cu["user_id"],))
    u["total_orders"]=s["t"] if s else 0; u["total_spent"]=s["sp"] if s else 0
    return jsonify({"user":u})

@app.route("/api/profile", methods=["PUT"])
@jwt_required
def upd_profile(cu):
    d=request.get_json() or {}; cur=q1("SELECT * FROM users WHERE id=?",(cu["user_id"],))
    if not cur: return jsonify({"error":"Not found"}),404
    name=(d.get("name") or cur["name"]).strip(); phone=(d.get("phone") or cur["phone"] or "").strip()
    addr=(d.get("address") or cur["address"] or "").strip(); pic=(d.get("picture") or cur["picture"] or ""); color=(d.get("profile_color") or cur["profile_color"] or "#1A6FB3")
    run("UPDATE users SET name=?,phone=?,address=?,picture=?,profile_color=? WHERE id=?",(name,phone,addr,pic,color,cu["user_id"]))
    return jsonify({"message":"Updated ✅","user":q1("SELECT id,name,email,phone,address,picture,profile_color FROM users WHERE id=?",(cu["user_id"],))})

@app.route("/api/profile/password", methods=["PUT"])
@jwt_required
def chg_pw(cu):
    d=request.get_json() or {}; op=d.get("current_password",""); np=d.get("new_password","")
    if not op or not np: return jsonify({"error":"Both required"}),400
    if len(np)<6: return jsonify({"error":"New password 6+ chars"}),400
    u=q1("SELECT password FROM users WHERE id=?",(cu["user_id"],))
    if not u or not check_pw(op,u["password"]): return jsonify({"error":"Current password incorrect"}),401
    run("UPDATE users SET password=? WHERE id=?",(hash_pw(np),cu["user_id"]))
    return jsonify({"message":"Password changed 🔒"})

@app.route("/api/admin/menu/<int:mid>")
@admin_required
def admin_menu_item(mid):
    item = q1("SELECT * FROM menu_items WHERE id=?", (mid,))
    if not item: return jsonify({"error": "Not found"}), 404
    item["is_spicy"] = bool(item["is_spicy"])
    item["is_new"]   = bool(item["is_new"])
    item["is_best"]  = bool(item["is_best"])
    return jsonify({"item": item})

@app.errorhandler(404)
def e404(e): return jsonify({"error":"Not found"}),404
@app.errorhandler(500)
def e500(e): return jsonify({"error":"Server error","detail":str(e)}),500

if __name__=="__main__":
    with app.app_context():
        existing = q1("SELECT COUNT(*) as c FROM menu_items")["c"]
        if existing == 0:
            for d in SAMPLE_DISHES:
                run("INSERT INTO menu_items(name,description,price,category,type,restaurant,rating,image,emoji,is_spicy,is_new,is_best,time) VALUES(%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s) ON CONFLICT DO NOTHING", d)
            print(f"✅  Menu seeded with {len(SAMPLE_DISHES)} dishes")
        elif existing < 300:
            # Old DB with fewer dishes — auto upgrade
            run("DELETE FROM menu_items")
            for d in SAMPLE_DISHES:
                run("INSERT INTO menu_items(name,description,price,category,type,restaurant,rating,image,emoji,is_spicy,is_new,is_best,time) VALUES(%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s) ON CONFLICT DO NOTHING", d)
            print(f"✅  Menu upgraded to {len(SAMPLE_DISHES)} dishes")
        else:
            print(f"✅  Menu already has {existing} dishes")
    print("\n"+"="*55)
    print("  🍛  RasoiExpress — Admin Panel")
    print("="*55)
    print("  📡  API   : http://localhost:5000")
    print("  🔐  ADMIN : http://localhost:5000/admin")
    print("  👤  ID    : admin123")
    print("  🔑  Pass  : secure@123")
    print("="*55+"\n")
    app.run(debug=True, host="0.0.0.0", port=5000)