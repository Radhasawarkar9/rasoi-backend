"""
RasoiExpress — Admin Panel (Ultimate Edition + Supabase PostgreSQL)
=================================================
Run:   python app.py
Admin: http://localhost:5000/admin

UPDATED:
  🗄️  Supabase PostgreSQL (replaces SQLite)
  🔐  JWT Auth (unchanged)
  🌐  CORS for Netlify + Render
  ♻️  Auto env-var loading via python-dotenv
"""

import os, sys, json, hashlib, hmac, random, string, functools
from datetime import datetime, timedelta, timezone
from flask import Flask, request, jsonify, g, session, render_template_string, redirect
from dotenv import load_dotenv

load_dotenv()  # load .env file if present

try:
    import jwt
except ImportError:
    print("❌  Run:  pip install Flask PyJWT"); sys.exit(1)

try:
    import psycopg2
    import psycopg2.extras
except ImportError:
    print("❌  Run:  pip install psycopg2-binary"); sys.exit(1)

# ═══════════════════════════════════════════════════════════════
#  CONFIG
# ═══════════════════════════════════════════════════════════════
SECRET_KEY         = os.environ.get("SECRET_KEY", "rasoi-express-jwt-secret-2024")
SESSION_SECRET     = os.environ.get("SESSION_SECRET", "rasoi-admin-session-secret-2024")
JWT_EXPIRY_DAYS    = 7
PBKDF2_ITERS       = 260_000
DATABASE_URL       = os.environ.get("DATABASE_URL", "")   # Supabase PostgreSQL connection string
ADMIN_ID           = os.environ.get("ADMIN_ID", "admin123")
ADMIN_PASS_HASH    = hashlib.sha256(os.environ.get("ADMIN_PASSWORD", "secure@123").encode()).hexdigest()
ADMIN_SESSION_KEY  = "admin_ok"
MAX_LOGIN_ATTEMPTS = 5

# In-memory attempt tracker  {ip: {count, locked_until}}
login_attempts = {}

# ═══════════════════════════════════════════════════════════════
#  DATABASE SCHEMA  (PostgreSQL / Supabase)
# ═══════════════════════════════════════════════════════════════
SCHEMA = """
CREATE TABLE IF NOT EXISTS users (
    id            SERIAL PRIMARY KEY,
    name          TEXT    NOT NULL,
    email         TEXT    NOT NULL UNIQUE,
    password      TEXT    NOT NULL,
    phone         TEXT    DEFAULT '',
    address       TEXT    DEFAULT '',
    picture       TEXT    DEFAULT '',
    profile_color TEXT    DEFAULT '#1A6FB3',
    is_blocked    BOOLEAN DEFAULT FALSE,
    created_at    TIMESTAMP WITH TIME ZONE DEFAULT NOW()
);
CREATE TABLE IF NOT EXISTS menu_items (
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
);
CREATE TABLE IF NOT EXISTS orders (
    id           TEXT    PRIMARY KEY,
    user_id      INTEGER NOT NULL REFERENCES users(id),
    items        TEXT    NOT NULL,
    total        REAL    NOT NULL,
    restaurant   TEXT    DEFAULT '',
    address      TEXT    DEFAULT '',
    status       TEXT    DEFAULT 'placed',
    current_step INTEGER DEFAULT 0,
    placed_at    TIMESTAMP WITH TIME ZONE DEFAULT NOW()
);
CREATE TABLE IF NOT EXISTS activity_log (
    id         SERIAL PRIMARY KEY,
    action     TEXT    NOT NULL,
    details    TEXT    DEFAULT '',
    ip         TEXT    DEFAULT '',
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
);
"""

SAMPLE_DISHES = [

    # ── Veg Curries (15) ──
    ('Paneer Butter Masala','Silky-smooth paneer cubes simmered in a rich, buttery tomato-cashew gravy.',260,'Veg Curries','veg','Shree Bhavan',4.8,'https://www.indianhealthyrecipes.com/wp-content/uploads/2021/07/paneer-butter-masala.webp','🧀',False,False,True,'25 mins'),
    ('Dal Makhani','Slow-cooked black lentils in velvety butter and cream — a Delhi legend.',190,'Veg Curries','veg','Maa Ki Rasoi',4.9,'https://myfoodstory.com/wp-content/uploads/2018/08/Dal-Makhani-New-3.jpg','🫘',False,False,True,'20 mins'),
    ('Palak Paneer','Fresh spinach purée with soft paneer cubes, tempered with garlic and cream.',230,'Veg Curries','veg','Shree Bhavan',4.6,'https://www.indianveggiedelight.com/wp-content/uploads/2017/10/palak-paneer-recipe-featured.jpg','🌿',False,False,False,'25 mins'),
    ('Rajma Masala','Red kidney beans slow-cooked in a tangy, aromatic onion-tomato masala.',180,'Veg Curries','veg','Maa Ki Rasoi',4.7,'https://static.vecteezy.com/system/resources/previews/016/287/033/non_2x/palak-rajma-masala-is-an-indian-curry-prepared-with-red-kidney-beans-and-spinach-cooked-with-spices-free-photo.jpg','🫘',True,False,True,'20 mins'),
    ('Aloo Gobi','Dry-spiced potatoes and cauliflower with turmeric, cumin and coriander.',160,'Veg Curries','veg','Desi Tadka',4.5,'https://static01.nyt.com/images/2023/12/21/multimedia/ND-Aloo-Gobi-gkwc/ND-Aloo-Gobi-gkwc-videoSixteenByNineJumbo1600.jpg','🥔',True,False,False,'20 mins'),
    ('Matar Paneer','Green peas and paneer in a fragrant, mildly spiced tomato gravy.',240,'Veg Curries','veg','Shree Bhavan',4.6,'https://www.indianveggiedelight.com/wp-content/uploads/2019/12/matar-paneer-instant-pot-featured.jpg','🫛',False,False,False,'22 mins'),
    ('Chana Masala','Hearty chickpeas stewed in a bold, tangy sauce of onion, tomato and spices.',170,'Veg Curries','veg','Chaat Corner',4.8,'https://encrypted-tbn0.gstatic.com/images?q=tbn:ANd9GcQmtyKzYZir0Tz85yb6Flife9PoIDBw35LHkg&s','🫘',True,False,True,'18 mins'),
    ('Bhindi Masala','Crispy okra tossed with caramelised onions, tomatoes and Indian spices.',155,'Veg Curries','veg','Desi Tadka',4.4,'https://myfoodstory.com/wp-content/uploads/2025/03/Bhindi-Masala-2.jpg','🥦',False,False,False,'18 mins'),
    ('Kadai Paneer','Paneer and capsicum cooked in a wok with freshly ground kadai masala.',270,'Veg Curries','veg','Shree Bhavan',4.7,'https://www.cubesnjuliennes.com/wp-content/uploads/2020/03/Best-Kadai-Paneer-Recipe.jpg','🧀',True,True,False,'28 mins'),
    ('Shahi Paneer','Royal paneer dish cooked in a cream-nut gravy with saffron and cardamom.',290,'Veg Curries','veg','Mughal Darbar',4.7,'https://www.sanjanafeasts.co.uk/wp-content/uploads/2020/01/Restaurant-Style-Shahi-Paneer-735x1103.jpg','🧀',False,False,False,'26 mins'),
    ('Mix Veg Curry','Seasonal mixed vegetables in a lightly spiced coconut-tomato gravy.',165,'Veg Curries','veg','Desi Tadka',4.3,'https://shwetainthekitchen.com/wp-content/uploads/2023/03/mixed-vegetable-curry.jpg','🥕',False,False,False,'20 mins'),
    ('Navratan Korma','Nine-jewel curry with vegetables, paneer and fruits in a mild, sweet gravy.',275,'Veg Curries','veg','Mughal Darbar',4.5,'https://www.jcookingodyssey.com/wp-content/uploads/2025/02/navratan-korma.jpg','🌸',False,False,False,'30 mins'),
    ('Saag Aloo','Mustard greens with potatoes, tempered with garlic and Punjabi spices.',155,'Veg Curries','veg','Maa Ki Rasoi',4.4,'https://rainbowplantlife.com/wp-content/uploads/2024/01/Hero-2-scaled.jpg','🥬',True,False,False,'22 mins'),
    ('Aloo Matar','Simple, comforting potato and peas curry in a light tomato-onion base.',150,'Veg Curries','veg','Desi Tadka',4.3,'https://encrypted-tbn0.gstatic.com/images?q=tbn:ANd9GcT6e7RqeHiz3tAwbOD4SDvmc190waysfoGOgw&s','🥔',False,False,False,'18 mins'),
    ('Methi Malai Paneer','Paneer in a fenugreek-cream gravy with a unique bittersweet flavour profile.',255,'Veg Curries','veg','Shree Bhavan',4.6,'https://d1mxd7n691o8sz.cloudfront.net/static/recipe/recipe/2023-12/Methi-Malai-Paneer-2-3-1f89f6ead16c4b538280f8ca57d75be9_thumbnail_1702631.jpeg','🌿',False,True,False,'24 mins'),

    # ── South Indian (15) ──
    ('Masala Dosa','Crispy rice-lentil crepe stuffed with spiced potato filling, served with sambar.',140,'South Indian','veg','South Spice',4.8,'https://www.cookwithmanali.com/wp-content/uploads/2020/05/Masala-Dosa-500x500.jpg','🥞',False,False,True,'18 mins'),
    ('Idli Sambar','Fluffy steamed rice cakes with tangy sambar and two fresh chutneys.',100,'South Indian','veg','South Spice',4.5,'https://encrypted-tbn0.gstatic.com/images?q=tbn:ANd9GcS3aJyP7SxhdvtHtorSod6skM3K2BTE3N_Ouw&s','🫕',False,False,False,'15 mins'),
    ('Medu Vada','Crispy lentil doughnuts with a fluffy interior, served with sambar and coconut chutney.',90,'South Indian','veg','South Spice',4.5,'https://bonmasala.com/wp-content/uploads/2022/12/medu-vada-recipe-500x500.webp','🍩',False,False,False,'15 mins'),
    ('Uttapam','Thick rice pancake topped with onions, tomatoes and green chillies. Served with sambar.',120,'South Indian','veg','South Spice',4.4,'https://encrypted-tbn0.gstatic.com/images?q=tbn:ANd9GcRuiAx67pyaTYtBtBT1qtf7OM30AZg5ngMnaw&s','🥞',False,False,False,'18 mins'),
    ('Pongal','Comforting rice and moong dal cooked with black pepper, cumin and ghee.',110,'South Indian','veg','South Spice',4.4,'https://encrypted-tbn0.gstatic.com/images?q=tbn:ANd9GcQonLqWxFc3-G-HKlsDDhNcvXvIn_XkxYbJ_A&s','🍲',False,False,False,'20 mins'),
    ('Rava Dosa','Paper-thin, lacy semolina crepe — extra crispy with curry leaves and cashews.',130,'South Indian','veg','Udupi Palace',4.7,'https://encrypted-tbn0.gstatic.com/images?q=tbn:ANd9GcQbNs_k00kLfeTMdEf2QXEcLI61RKma4zrghg&s','🥞',False,False,True,'20 mins'),
    ('Chettinad Chicken Curry','Fiery Tamil Nadu curry with freshly ground Chettinad spices — bold and aromatic.',310,'South Indian','nonveg','Chettinad House',4.8,'https://encrypted-tbn0.gstatic.com/images?q=tbn:ANd9GcSSdYkqM5GJLHSlYcwoKA8KiT8ndmgJcamf5A&s','🍗',True,False,True,'35 mins'),
    ('Pesarattu','Green moong dal crepe from Andhra, served with upma stuffing and ginger chutney.',115,'South Indian','veg','South Spice',4.3,'https://i0.wp.com/www.chitrasfoodbook.com/wp-content/uploads/2022/07/pesarattu-allam-pachadi-1.jpg?resize=500%2C533&ssl=1','🥞',False,True,False,'18 mins'),
    ('Appam with Stew','Lacy rice hoppers with a fluffy centre, paired with mild Kerala vegetable stew.',160,'South Indian','veg','Kerala Kitchen',4.6,'https://www.shutterstock.com/image-photo/appam-vegetable-stew-one-famous-600nw-2203037921.jpg','🫕',False,False,False,'22 mins'),
    ('Bisi Bele Bath','Karnataka one-pot dish of rice, lentils and vegetables with tamarind and spice powder.',145,'South Indian','veg','Karnataka Bhavan',4.5,'https://encrypted-tbn0.gstatic.com/images?q=tbn:ANd9GcROUGcJZ_e59MH3ug74bRTqIEuvsKuWn2djfQ&s','🍲',True,False,False,'25 mins'),
    ('Rasam','Thin, peppery tamarind soup with cumin and coriander — a South Indian comfort staple.',75,'South Indian','veg','South Spice',4.5,'https://i0.wp.com/www.chitrasfoodbook.com/wp-content/uploads/2014/12/rasam.jpg?w=1200&ssl=1','🫕',True,False,False,'12 mins'),
    ('Curd Rice','Cooling rice mixed with creamy curd, tempered with mustard seeds and curry leaves.',90,'South Indian','veg','Udupi Palace',4.4,'https://encrypted-tbn0.gstatic.com/images?q=tbn:ANd9GcSbJwtOJEBhlrD5K-0k_deIgMQpsmlT-MoG4Q&s','🍚',False,False,False,'10 mins'),
    ('Kerala Parotta','Layered, flaky flatbread from Kerala — best with egg curry or vegetable kurma.',85,'South Indian','veg','Kerala Kitchen',4.6,'https://encrypted-tbn0.gstatic.com/images?q=tbn:ANd9GcTvYkUrZWQj392J5pVKrR7RGH0ZbWwxDgVllw&s','🫓',False,False,False,'18 mins'),
    ('Prawn Kerala Curry','Succulent prawns slow-cooked in a thick coconut milk curry with raw mango.',380,'South Indian','nonveg','Kerala Kitchen',4.7,'https://www.whiskaffair.com/wp-content/uploads/2020/05/Kerala-Prawn-Curry-2-3.jpg','🦐',True,True,False,'30 mins'),
    ('Sambar Rice','Steamed rice mixed with thick, tangy vegetable sambar. Simple south Indian soul food.',100,'South Indian','veg','South Spice',4.3,'https://encrypted-tbn0.gstatic.com/images?q=tbn:ANd9GcTrjb1mN6MRmfhinIdsUdD4SaVj23h1QfokaA&s','🍚',False,False,False,'15 mins'),

    # ── Biryani & Rice (15) ──
    ('Veg Biryani','Fragrant basmati layered with seasonal vegetables and aromatic dum spices.',260,'Biryani & Rice','veg','Biryani Darbar',4.5,'https://encrypted-tbn0.gstatic.com/images?q=tbn:ANd9GcSlg7JYWWJNnY-MJVGm02itthRtcc105HPt4Q&s','🌾',True,False,False,'35 mins'),
    ('Chicken Biryani','Hyderabadi dum biryani — saffron-infused basmati with succulent chicken pieces.',330,'Biryani & Rice','nonveg','Biryani Darbar',4.9,'https://www.cubesnjuliennes.com/wp-content/uploads/2020/07/Chicken-Biryani-Recipe.jpg','🍚',True,False,True,'40 mins'),
    ('Mutton Biryani','Tender mutton layered with aromatic basmati and slow-cooked on dum.',410,'Biryani & Rice','nonveg','Biryani Darbar',4.8,'https://www.cubesnjuliennes.com/wp-content/uploads/2021/03/Best-Mutton-Biryani-Recipe.jpg','🍖',True,False,False,'50 mins'),
    ('Prawn Biryani','Plump prawns dum-cooked with saffron rice, caramelised onions and herbs.',450,'Biryani & Rice','nonveg','Biryani Darbar',4.7,'https://encrypted-tbn0.gstatic.com/images?q=tbn:ANd9GcRPdg8ewaI81KS2VflCoIzAf0Rh-GqMguwDFA&s','🦐',True,True,False,'42 mins'),
    ('Egg Biryani','Fragrant dum biryani with boiled eggs, saffron basmati and caramelised onions.',270,'Biryani & Rice','nonveg','Biryani Darbar',4.5,'https://encrypted-tbn0.gstatic.com/images?q=tbn:ANd9GcRXs2_TY-Vid8Whh5nHA1Hl6WFnOw1HxGRezQ&s','🥚',True,False,False,'35 mins'),
    ('Hyderabadi Veg Biryani','Royal Hyderabadi dum biryani with fresh vegetables, kewra water and fried onions.',290,'Biryani & Rice','veg','Biryani Darbar',4.6,'https://encrypted-tbn0.gstatic.com/images?q=tbn:ANd9GcTa7wtzC0xvsruRVViH0Gece8SOuoNC7FInuw&s','🌾',True,False,False,'38 mins'),
    ('Lucknowi Biryani','Fragrant Awadhi-style dum biryani — mildly spiced with tender mutton and raisins.',380,'Biryani & Rice','nonveg','Mughal Darbar',4.8,'https://encrypted-tbn0.gstatic.com/images?q=tbn:ANd9GcSPTXEICeyoDwisw-4PE-PDps-I5D2mDMFgZQ&s','🍚',False,False,True,'45 mins'),
    ('Jeera Rice','Basmati rice tempered with ghee, cumin seeds and fresh coriander. Simple perfection.',130,'Biryani & Rice','veg','Shree Bhavan',4.4,'https://encrypted-tbn0.gstatic.com/images?q=tbn:ANd9GcQGDD6xataHW-b_UHb36ogu9A6gJasmfilbAw&s','🌾',False,False,False,'18 mins'),
    ('Pulao','Basmati rice cooked with aromatic whole spices and mixed vegetables in a single pot.',180,'Biryani & Rice','veg','Maa Ki Rasoi',4.4,'https://encrypted-tbn0.gstatic.com/images?q=tbn:ANd9GcQJq0MTUWNF_UF09dUv183INUUggDecvAPcNw&s','🌾',False,False,False,'22 mins'),
    ('Fish Biryani','Flaky fish layered with spiced basmati and slow-cooked on dum for deep flavour.',440,'Biryani & Rice','nonveg','Coastal Flavours',4.7,'https://encrypted-tbn0.gstatic.com/images?q=tbn:ANd9GcSLy9fb8GvwXrv0RxczufvyOniy5w4meEuMWg&s','🐟',True,True,False,'42 mins'),
    ('Paneer Fried Rice','Wok-tossed fried rice with paneer cubes, vegetables and Indo-Chinese sauces.',220,'Biryani & Rice','veg','Dragon Chilli',4.3,'https://www.indianveggiedelight.com/wp-content/uploads/2023/09/paneer-fried-rice-featured.jpg','🧀',False,False,False,'20 mins'),
    ('Chicken Fried Rice','Classic Indo-Chinese fried rice with egg, chicken shreds, soy sauce and spring onion.',250,'Biryani & Rice','nonveg','Dragon Chilli',4.4,'https://encrypted-tbn0.gstatic.com/images?q=tbn:ANd9GcT7JR35t1gZFG4S1tE8zACKIm-ZfxjeHKaJmw&s','🍗',False,False,False,'22 mins'),
    ('Thalassery Biryani','Fragrant Kerala-style biryani with short-grain rice, fried chicken and caramelised onion.',360,'Biryani & Rice','nonveg','Kerala Kitchen',4.8,'https://encrypted-tbn0.gstatic.com/images?q=tbn:ANd9GcTzbo-iAPeaIntJjvOk3HHD21CMFrsAGSy4YQ&s','🍚',False,True,False,'45 mins'),
    ('Mushroom Biryani','Earthy mushrooms dum-cooked with fragrant basmati, whole spices and caramelised onions.',250,'Biryani & Rice','veg','Shree Bhavan',4.5,'https://www.whiskaffair.com/wp-content/uploads/2014/07/Mushroom-Biryani-3.jpg','🍄',False,False,False,'32 mins'),
    ('Dal Tadka with Rice','Yellow toor dal tempered with ghee, mustard seeds and dried chilli, served over rice.',170,'Biryani & Rice','veg','Maa Ki Rasoi',4.6,'https://i0.wp.com/upbeetanisha.com/wp-content/uploads/2024/01/IMG_9643.jpg?resize=768%2C1024&ssl=1','🫘',False,False,False,'20 mins'),

    # ── Street Food (15) ──
    ('Chole Bhature','Tangy spiced chickpeas with deep-fried fluffy bread. A Punjab favourite.',160,'Street Food','veg','Chaat Corner',4.8,'https://encrypted-tbn0.gstatic.com/images?q=tbn:ANd9GcRyta2FEc05FPDkoHtzey9a8nmlgumGb7lDew&s','🫘',True,True,True,'25 mins'),
    ('Pav Bhaji','Spicy mixed vegetable mash served with butter-toasted pav buns.',160,'Street Food','veg','Chaat Corner',4.7,'https://www.cubesnjuliennes.com/wp-content/uploads/2020/07/Instant-Pot-Mumbai-Pav-Bhaji-Recipe.jpg','🍞',True,False,False,'20 mins'),
    ('Pani Puri (6 pcs)','Hollow crispy puri with tangy tamarind water, potato and chaat masala.',80,'Street Food','veg','Chaat Corner',4.6,'https://image.cdn.shpy.in/321745/1696796256313_SKU-0026_0.png?width=600&format=webp','🫙',True,False,False,'10 mins'),
    ('Bhel Puri','Puffed rice, sev, onion, tomato and tamarind chutney tossed together. Mumbai street classic.',90,'Street Food','veg','Chaat Corner',4.5,'https://www.indianveggiedelight.com/wp-content/uploads/2017/03/bhel-puri-featured-500x500.jpg','🫙',True,False,False,'10 mins'),
    ('Aloo Tikki Chaat','Crispy potato patties topped with yogurt, tamarind chutney and chaat masala.',110,'Street Food','veg','Street Bites',4.7,'https://sinfullyspicy.com/wp-content/uploads/2023/03/1-1.jpg','🥔',True,False,True,'15 mins'),
    ('Vada Pav',"Mumbai's iconic spiced potato fritter in a pav bun with dry coconut chutney.",70,'Street Food','veg','Street Bites',4.8,'https://blog.swiggy.com/wp-content/uploads/2024/11/Image-1_mumbai-vada-pav-1024x538.png','🍔',True,False,True,'12 mins'),
    ('Sev Puri','Flat puris topped with potato, onion, chutneys and a generous layer of crunchy sev.',95,'Street Food','veg','Chaat Corner',4.5,'https://www.indianveggiedelight.com/wp-content/uploads/2023/07/Sev-puri-2.jpg','🫙',False,False,False,'10 mins'),
    ('Dahi Vada','Soft lentil dumplings soaked in yogurt, drizzled with tamarind and mint chutney.',105,'Street Food','veg','Street Bites',4.5,'https://ministryofcurry.com/wp-content/uploads/2016/08/Dahi-Vada-5.jpg','🍮',False,False,False,'12 mins'),
    ('Samosa (2 pcs)','Golden crispy pastry filled with spiced potato and peas. Served with chutney.',65,'Snacks','veg','Chaat Corner',4.6,'https://prashantbandhu.com/wp-content/uploads/2023/07/DSC_0413-scaled.jpg','🥟',False,False,False,'12 mins'),
    ('Paneer Tikka','Marinated paneer cubes grilled in tandoor with bell peppers and onion.',320,'Snacks','veg','Tandoor King',4.8,'https://encrypted-tbn0.gstatic.com/images?q=tbn:ANd9GcRJ2WY2YmIJtXrpmDToEHwJIOAcyBefjpFwXg&s','🍢',True,False,True,'28 mins'),
    ('Gulab Jamun (4 pcs)','Soft milk-solid dumplings soaked in rose-cardamom sugar syrup.',95,'Desserts','veg','Mithaas',4.9,'https://encrypted-tbn0.gstatic.com/images?q=tbn:ANd9GcRD5KYcR79wTcJv7U6nYzIGNIU5iEBK0AoPkQ&s','🍮',False,False,True,'12 mins'),
    ('Mango Lassi','Chilled yogurt blended with fresh Alphonso mango pulp and cardamom.',85,'Drinks','veg','Shree Bhavan',4.8,'https://flavorquotient.com/wp-content/uploads/2023/05/Mango-Lassi-FQ-6-1036.jpg','🥭',False,False,True,'10 mins'),
    ('Masala Chai','Aromatic tea brewed with ginger, cardamom, cinnamon and black pepper.',55,'Drinks','veg','Maa Ki Rasoi',4.9,'https://www.thespicehouse.com/cdn/shop/articles/Chai_Masala_Tea_1200x1200.jpg?v=1606936195','🍵',False,False,False,'10 mins'),
    ('Butter Chicken','Tender chicken pieces in silky, velvety tomato-butter gravy — India\'s most loved.',290,'Non-Veg Curries','nonveg','Maa Ki Rasoi',4.9,'https://www.licious.in/blog/wp-content/uploads/2020/10/butter-chicken--600x600.jpg','🍗',False,False,True,'30 mins'),
    ('Chicken Biryani (Lucknowi)','Fragrant Awadhi dum biryani with saffron rice and tender chicken.',350,'Biryani & Rice','nonveg','Mughal Darbar',4.8,'https://www.cubesnjuliennes.com/wp-content/uploads/2020/07/Chicken-Biryani-Recipe.jpg','🍚',False,True,True,'40 mins'),
]

# ═══════════════════════════════════════════════════════════════
#  DB HELPERS  (PostgreSQL / Supabase via psycopg2)
# ═══════════════════════════════════════════════════════════════
def get_db():
    """Get per-request PostgreSQL connection (stored in Flask g)."""
    if "db" not in g:
        if not DATABASE_URL:
            raise RuntimeError("DATABASE_URL environment variable is not set. "
                               "Please set it to your Supabase PostgreSQL connection string.")
        g.db = psycopg2.connect(DATABASE_URL, cursor_factory=psycopg2.extras.RealDictCursor)
        g.db.autocommit = False
    return g.db

def close_db(e=None):
    db = g.pop("db", None)
    if db is not None:
        db.close()

def q1(sql, p=()):
    """Execute query, return first row as dict or None."""
    cur = get_db().cursor()
    cur.execute(sql, p)
    row = cur.fetchone()
    return dict(row) if row else None

def qa(sql, p=()):
    """Execute query, return all rows as list of dicts."""
    cur = get_db().cursor()
    cur.execute(sql, p)
    return [dict(r) for r in cur.fetchall()]

def run(sql, p=()):
    """Execute INSERT/UPDATE/DELETE, commit and return last inserted id (if any)."""
    db  = get_db()
    cur = db.cursor()
    cur.execute(sql, p)
    db.commit()
    # If query has RETURNING id, fetch the id
    try:
        row = cur.fetchone()
        return row["id"] if row else None
    except Exception:
        return None

def log_action(action, details=""):
    ip = request.remote_addr or "unknown"
    try:
        run("INSERT INTO activity_log(action,details,ip) VALUES(%s,%s,%s)", (action, details, ip))
    except Exception:
        pass

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
app.teardown_appcontext(close_db)

ALLOWED_ORIGINS = os.environ.get("ALLOWED_ORIGINS", "*")

@app.after_request
def cors(r):
    r.headers["Access-Control-Allow-Origin"]  = ALLOWED_ORIGINS
    r.headers["Access-Control-Allow-Methods"] = "GET,POST,PUT,DELETE,OPTIONS"
    r.headers["Access-Control-Allow-Headers"] = "Content-Type,Authorization"
    r.headers["Access-Control-Allow-Credentials"] = "true"
    return r

@app.before_request
def preflight():
    if request.method == "OPTIONS":
        return "", 204, {
            "Access-Control-Allow-Origin":      ALLOWED_ORIGINS,
            "Access-Control-Allow-Methods":     "GET,POST,PUT,DELETE,OPTIONS",
            "Access-Control-Allow-Headers":     "Content-Type,Authorization",
            "Access-Control-Allow-Credentials": "true"
        }

def init_db():
    """Create tables if they don't exist (runs once on startup)."""
    try:
        db  = psycopg2.connect(DATABASE_URL, cursor_factory=psycopg2.extras.RealDictCursor)
        cur = db.cursor()
        # Execute each statement separately
        for stmt in SCHEMA.strip().split(";"):
            stmt = stmt.strip()
            if stmt:
                cur.execute(stmt)
        db.commit()
        print("✅  Supabase PostgreSQL: tables ready")
        # Seed menu if empty
        cur.execute("SELECT COUNT(*) AS c FROM menu_items")
        existing = cur.fetchone()["c"]
        if existing == 0:
            for d in SAMPLE_DISHES:
                cur.execute(
                    "INSERT INTO menu_items(name,description,price,category,type,restaurant,rating,image,emoji,is_spicy,is_new,is_best,time) "
                    "VALUES(%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s) ON CONFLICT DO NOTHING", d)
            db.commit()
            print(f"✅  Menu seeded with {len(SAMPLE_DISHES)} dishes")
        else:
            print(f"✅  Menu already has {existing} dishes")
        db.close()
    except Exception as e:
        print(f"⚠️  DB init warning: {e}")

# ═══════════════════════════════════════════════════════════════
#  ADMIN LOGIN HTML
# ═══════════════════════════════════════════════════════════════
LOGIN_HTML = r"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>RasoiExpress Admin</title>
<style>
  *{box-sizing:border-box;margin:0;padding:0}
  body{font-family:'Segoe UI',sans-serif;background:linear-gradient(135deg,#0f172a 0%,#1e293b 50%,#0f172a 100%);
       min-height:100vh;display:flex;align-items:center;justify-content:center}
  .card{background:rgba(255,255,255,.05);backdrop-filter:blur(20px);border:1px solid rgba(255,255,255,.1);
        border-radius:24px;padding:48px 40px;width:100%;max-width:420px;box-shadow:0 25px 50px rgba(0,0,0,.5)}
  .logo{text-align:center;margin-bottom:32px}
  .logo-icon{font-size:3rem;display:block;margin-bottom:8px}
  .logo h1{color:#fff;font-size:1.6rem;font-weight:800;letter-spacing:-.5px}
  .logo p{color:rgba(255,255,255,.5);font-size:.85rem;margin-top:4px}
  .badge{display:inline-block;background:linear-gradient(135deg,#f97316,#ef4444);
         color:#fff;font-size:.7rem;font-weight:700;padding:3px 10px;border-radius:20px;
         letter-spacing:.5px;margin-top:8px}
  label{display:block;color:rgba(255,255,255,.7);font-size:.8rem;font-weight:600;
        text-transform:uppercase;letter-spacing:.8px;margin-bottom:8px}
  .input-wrap{position:relative;margin-bottom:20px}
  input{width:100%;background:rgba(255,255,255,.08);border:1px solid rgba(255,255,255,.15);
        border-radius:12px;padding:14px 16px;color:#fff;font-size:.95rem;outline:none;transition:all .2s}
  input::placeholder{color:rgba(255,255,255,.3)}
  input:focus{border-color:#f97316;background:rgba(249,115,22,.08);box-shadow:0 0 0 3px rgba(249,115,22,.15)}
  .eye-btn{position:absolute;right:14px;top:50%;transform:translateY(-50%);
           background:none;border:none;color:rgba(255,255,255,.4);cursor:pointer;font-size:1.1rem;
           transition:color .2s;line-height:1}
  .eye-btn:hover{color:rgba(255,255,255,.8)}
  .btn{width:100%;padding:15px;background:linear-gradient(135deg,#f97316,#ef4444);
       border:none;border-radius:12px;color:#fff;font-size:1rem;font-weight:700;
       cursor:pointer;transition:all .25s;letter-spacing:.3px;margin-top:4px}
  .btn:hover{transform:translateY(-2px);box-shadow:0 8px 25px rgba(249,115,22,.4)}
  .btn:active{transform:translateY(0)}
  .btn:disabled{opacity:.6;cursor:not-allowed;transform:none}
  .alert{padding:12px 16px;border-radius:10px;font-size:.85rem;margin-bottom:20px;display:none;font-weight:500}
  .alert.show{display:block}
  .alert.err{background:rgba(239,68,68,.15);border:1px solid rgba(239,68,68,.3);color:#fca5a5}
  .alert.warn{background:rgba(245,158,11,.15);border:1px solid rgba(245,158,11,.3);color:#fcd34d}
  .alert.info{background:rgba(59,130,246,.15);border:1px solid rgba(59,130,246,.3);color:#93c5fd}
  .divider{border:none;border-top:1px solid rgba(255,255,255,.08);margin:24px 0}
  .status-bar{display:flex;align-items:center;gap:8px;justify-content:center}
  .sdot{width:8px;height:8px;border-radius:50%;background:#94a3b8}
  .sdot.ok{background:#22c55e;box-shadow:0 0 8px #22c55e}
  .sdot.err{background:#ef4444}
  .sdot.check{background:#f59e0b;animation:pulse 1s infinite}
  @keyframes pulse{0%,100%{opacity:1}50%{opacity:.4}}
  #apiStatus{color:rgba(255,255,255,.5);font-size:.78rem}
  .lock-notice{background:rgba(239,68,68,.1);border:1px solid rgba(239,68,68,.2);
               border-radius:10px;padding:12px;text-align:center;color:#fca5a5;font-size:.82rem;margin-bottom:16px}
  .attempts-left{color:rgba(255,255,255,.4);font-size:.75rem;text-align:center;margin-top:10px}
</style>
</head>
<body>
<div class="card">
  <div class="logo">
    <span class="logo-icon">🍛</span>
    <h1>RasoiExpress</h1>
    <p>Admin Control Panel</p>
    <span class="badge">ADMIN ACCESS</span>
  </div>
  {% if error %}
  <div class="alert show err" id="loginAlert">⚠️ {{ error }}</div>
  {% elif locked %}
  <div class="lock-notice">🔒 Too many failed attempts. Try again in {{ locked_mins }} minute(s).</div>
  {% else %}
  <div class="alert" id="loginAlert"></div>
  {% endif %}
  <form onsubmit="doLogin(event)" autocomplete="off">
    <label for="adminId">Admin ID</label>
    <div class="input-wrap">
      <input type="text" id="adminId" value="{{ username or '' }}" placeholder="Enter admin ID" required autofocus>
    </div>
    <label for="adminPass">Password</label>
    <div class="input-wrap">
      <input type="password" id="adminPass" placeholder="Enter password" required>
      <button type="button" class="eye-btn" onclick="togglePw()" id="eyeBtn" title="Show/Hide password">👁</button>
    </div>
    <button class="btn" type="submit" id="loginBtn">🔐 Sign In to Admin Panel</button>
    {% if attempts and attempts > 0 %}
    <p class="attempts-left">⚠️ {{ attempts }} failed attempt(s) — {{ 5 - attempts }} remaining before lockout</p>
    {% endif %}
  </form>
  <hr class="divider">
  <div class="status-bar">
    <div class="sdot" id="apiDot"></div>
    <span id="apiStatus">Checking backend…</span>
  </div>
</div>
<script>
function togglePw(){
  const i=document.getElementById('adminPass'), b=document.getElementById('eyeBtn');
  i.type = i.type==='password' ? 'text' : 'password';
  b.textContent = i.type==='password' ? '👁' : '🙈';
}
function showAlert(msg,t,icon=''){
  const a=document.getElementById('loginAlert');
  if(!a)return;
  a.textContent=icon?' '+icon+' '+msg:msg;
  a.className=`alert show ${t}`;
}
function clrAlert(){const a=document.getElementById('loginAlert');if(a)a.className='alert';}
function setLoad(id,l){const b=document.getElementById(id);if(!b)return;b.disabled=l;if(l)b.textContent='⏳ Signing in…';else b.textContent='🔐 Sign In to Admin Panel';}

async function checkBackend(){
  const dot=document.getElementById('apiDot'), lbl=document.getElementById('apiStatus');
  if(!dot||!lbl)return;
  dot.className='sdot check'; lbl.textContent='Checking backend…';
  try{
    const r=await fetch(window.location.origin+'/api/health',{signal:AbortSignal.timeout(4000)});
    if(r.ok){dot.className='sdot ok';lbl.textContent='✅ Backend Online';lbl.style.color='#22c55e';return true;}
  }catch(e){}
  dot.className='sdot err'; lbl.textContent='❌ Backend Offline'; lbl.style.color='#ef4444'; return false;
}

async function doLogin(e){
  e.preventDefault(); clrAlert();
  const username=document.getElementById('adminId').value.trim();
  const password=document.getElementById('adminPass').value;
  if(!username||!password){showAlert('Both Admin ID and Password are required.','err','⚠️');return;}
  setLoad('loginBtn',true);
  try{
    const r=await fetch('/admin/login',{method:'POST',headers:{'Content-Type':'application/json'},
                         body:JSON.stringify({username,password})});
    const d=await r.json();
    if(r.ok){window.location.href='/admin/dashboard';}
    else{showAlert(d.error||'Login failed','err','❌');}
  }catch(err){showAlert('Cannot reach server. Is backend running?','err','🔌');}
  finally{setLoad('loginBtn',false);}
}
checkBackend();
</script>
</body>
</html>"""

# ═══════════════════════════════════════════════════════════════
#  ADMIN DASHBOARD HTML
# ═══════════════════════════════════════════════════════════════
DASH_HTML = r"""<!DOCTYPE html>
<html lang="en" data-theme="dark">
<head>
<meta charset="UTF-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>RasoiExpress — Admin Panel</title>
<script src="https://cdn.jsdelivr.net/npm/chart.js"></script>
<style>
:root{
  --bg:#0f172a;--card:#1e293b;--border:#334155;--text:#f1f5f9;--sub:#94a3b8;
  --blue:#3b82f6;--green:#22c55e;--red:#ef4444;--orange:#f97316;--yellow:#eab308;
  --r:14px;--rs:8px;--shadow:0 4px 20px rgba(0,0,0,.3)
}
[data-theme="light"]{
  --bg:#f8fafc;--card:#ffffff;--border:#e2e8f0;--text:#0f172a;--sub:#64748b;
  --shadow:0 4px 20px rgba(0,0,0,.08)
}
*{box-sizing:border-box;margin:0;padding:0}
body{font-family:'Segoe UI',system-ui,sans-serif;background:var(--bg);color:var(--text);min-height:100vh;overflow-x:hidden}
.sidebar{position:fixed;left:0;top:0;width:240px;height:100vh;background:var(--card);border-right:1px solid var(--border);
         display:flex;flex-direction:column;z-index:100;transition:transform .3s}
.sidebar-logo{padding:20px 18px;border-bottom:1px solid var(--border);display:flex;align-items:center;gap:10px}
.sidebar-logo span{font-size:1.5rem}
.sidebar-logo h2{font-size:1rem;font-weight:800;color:var(--orange)}
.nav-item{display:flex;align-items:center;gap:10px;padding:11px 18px;cursor:pointer;
          border-radius:var(--rs);margin:2px 8px;font-size:.85rem;font-weight:600;
          color:var(--sub);transition:all .2s;border:none;background:none;width:calc(100% - 16px);text-align:left}
.nav-item:hover{background:rgba(248,113,18,.08);color:var(--orange)}
.nav-item.active{background:rgba(248,113,18,.12);color:var(--orange)}
.nav-item span:first-child{font-size:1rem;width:20px;text-align:center}
.sidebar-footer{margin-top:auto;padding:12px;border-top:1px solid var(--border)}
.main{margin-left:240px;padding:24px;min-height:100vh}
.topbar{display:flex;align-items:center;justify-content:space-between;margin-bottom:24px;
        background:var(--card);border:1px solid var(--border);border-radius:var(--r);padding:14px 20px}
.topbar-left{display:flex;align-items:center;gap:12px}
.page-title{font-size:1.15rem;font-weight:800}
.topbar-right{display:flex;align-items:center;gap:10px}
.icon-btn{background:none;border:1px solid var(--border);border-radius:var(--rs);
          color:var(--sub);cursor:pointer;padding:7px 10px;font-size:1rem;transition:all .2s}
.icon-btn:hover{border-color:var(--blue);color:var(--blue)}
.section{display:none}.section.active{display:block}
.stats-grid{display:grid;grid-template-columns:repeat(auto-fit,minmax(200px,1fr));gap:16px;margin-bottom:24px}
.stat-card{background:var(--card);border:1px solid var(--border);border-radius:var(--r);padding:20px;position:relative;overflow:hidden}
.stat-card::before{content:'';position:absolute;top:0;left:0;right:0;height:3px;background:var(--c,var(--blue))}
.stat-val{font-size:2rem;font-weight:800;line-height:1}
.stat-lbl{color:var(--sub);font-size:.78rem;margin-top:6px;font-weight:600;text-transform:uppercase;letter-spacing:.5px}
.stat-ico{position:absolute;right:16px;top:50%;transform:translateY(-50%);font-size:2rem;opacity:.15}
.card{background:var(--card);border:1px solid var(--border);border-radius:var(--r);padding:20px}
.card-header{display:flex;align-items:center;justify-content:space-between;margin-bottom:16px}
.card-title{font-size:.95rem;font-weight:700}
table{width:100%;border-collapse:collapse;font-size:.82rem}
th{padding:10px 12px;text-align:left;font-size:.72rem;font-weight:700;text-transform:uppercase;
   letter-spacing:.5px;color:var(--sub);border-bottom:2px solid var(--border);white-space:nowrap}
td{padding:10px 12px;border-bottom:1px solid var(--border);vertical-align:middle}
tr:last-child td{border-bottom:none}
tr:hover td{background:rgba(255,255,255,.02)}
.badge{display:inline-flex;align-items:center;gap:4px;padding:3px 10px;border-radius:20px;
       font-size:.7rem;font-weight:700;letter-spacing:.3px}
.badge.green{background:rgba(34,197,94,.12);color:var(--green)}
.badge.red{background:rgba(239,68,68,.12);color:var(--red)}
.badge.orange{background:rgba(249,115,22,.12);color:var(--orange)}
.badge.blue{background:rgba(59,130,246,.12);color:var(--blue)}
.badge.yellow{background:rgba(234,179,8,.12);color:var(--yellow)}
.btn{padding:7px 14px;border-radius:var(--rs);border:none;font-size:.78rem;font-weight:700;cursor:pointer;transition:all .2s;font-family:inherit}
.btn-primary{background:var(--blue);color:#fff}.btn-primary:hover{opacity:.85}
.btn-danger{background:var(--red);color:#fff}.btn-danger:hover{opacity:.85}
.btn-warn{background:var(--orange);color:#fff}.btn-warn:hover{opacity:.85}
.btn-sm{padding:4px 10px;font-size:.72rem}
.btn:disabled{opacity:.5;cursor:not-allowed}
.search-bar{display:flex;gap:10px;margin-bottom:16px;flex-wrap:wrap}
.search-input{flex:1;min-width:200px;background:var(--bg);border:1px solid var(--border);
              border-radius:var(--rs);padding:9px 14px;color:var(--text);font-size:.85rem;outline:none;font-family:inherit}
.search-input:focus{border-color:var(--blue)}
select.search-input{cursor:pointer}
.modal-overlay{position:fixed;inset:0;background:rgba(0,0,0,.7);z-index:200;display:flex;
               align-items:center;justify-content:center;opacity:0;pointer-events:none;transition:opacity .25s}
.modal-overlay.show{opacity:1;pointer-events:all}
.modal{background:var(--card);border:1px solid var(--border);border-radius:var(--r);
       padding:28px;width:90%;max-width:500px;max-height:85vh;overflow-y:auto;
       transform:scale(.95);transition:transform .25s}
.modal-overlay.show .modal{transform:scale(1)}
.modal h3{font-size:1rem;font-weight:800;margin-bottom:20px}
.form-row{margin-bottom:14px}
.form-row label{display:block;color:var(--sub);font-size:.75rem;font-weight:600;
                text-transform:uppercase;letter-spacing:.5px;margin-bottom:6px}
.form-row input,.form-row select,.form-row textarea{width:100%;background:var(--bg);
  border:1px solid var(--border);border-radius:var(--rs);padding:9px 12px;color:var(--text);
  font-size:.85rem;outline:none;font-family:inherit;transition:border-color .2s}
.form-row input:focus,.form-row select:focus,.form-row textarea:focus{border-color:var(--blue)}
.form-row textarea{resize:vertical;min-height:70px}
.modal-footer{display:flex;gap:10px;justify-content:flex-end;margin-top:20px;padding-top:16px;border-top:1px solid var(--border)}
.toast{position:fixed;bottom:24px;right:24px;background:var(--card);border:1px solid var(--border);
       border-radius:var(--r);padding:14px 20px;font-size:.85rem;font-weight:600;
       box-shadow:var(--shadow);z-index:300;transform:translateX(120%);transition:transform .3s}
.toast.show{transform:translateX(0)}
.toast.success{border-left:4px solid var(--green)}
.toast.error{border-left:4px solid var(--red)}
.auto-refresh-badge{background:rgba(34,197,94,.12);color:var(--green);font-size:.7rem;
                    font-weight:700;padding:3px 8px;border-radius:20px;display:flex;align-items:center;gap:4px}
.sdot{width:8px;height:8px;border-radius:50%;background:var(--sub)}
.sdot.ok{background:var(--green);box-shadow:0 0 8px var(--green)}
.sdot.err{background:var(--red)}
.sdot.check{background:var(--yellow);animation:pulse 1s infinite}
@keyframes pulse{0%,100%{opacity:1}50%{opacity:.3}}
.loading-row td{text-align:center;color:var(--sub);padding:32px;font-size:.9rem}
.empty-state{text-align:center;padding:48px 20px;color:var(--sub)}
.empty-state .emoji{font-size:3rem;margin-bottom:12px}
.charts-grid{display:grid;grid-template-columns:1fr 1fr;gap:16px;margin-bottom:24px}
.chart-card{background:var(--card);border:1px solid var(--border);border-radius:var(--r);padding:20px}
@media(max-width:900px){.charts-grid{grid-template-columns:1fr}}
.activity-item{display:flex;gap:12px;padding:10px 0;border-bottom:1px solid var(--border)}
.activity-item:last-child{border-bottom:none}
.activity-dot{width:8px;height:8px;border-radius:50%;background:var(--blue);margin-top:6px;flex-shrink:0}
.activity-text{font-size:.82rem;flex:1}
.activity-time{font-size:.72rem;color:var(--sub);white-space:nowrap}
.session-timer{background:rgba(249,115,22,.1);border:1px solid rgba(249,115,22,.2);
               border-radius:var(--rs);padding:5px 12px;font-size:.78rem;color:var(--orange);font-weight:700}
.notif-badge{background:var(--red);color:#fff;border-radius:50%;width:18px;height:18px;
             font-size:.6rem;font-weight:700;display:inline-flex;align-items:center;justify-content:center;
             margin-left:4px;vertical-align:top}
.sw-tog{width:36px;height:20px;border-radius:10px;background:var(--border);border:none;cursor:pointer;
        position:relative;transition:background .2s;flex-shrink:0}
.sw-tog::after{content:'';position:absolute;left:3px;top:3px;width:14px;height:14px;
               border-radius:50%;background:#fff;transition:transform .2s}
.sw-tog.on{background:var(--green)}.sw-tog.on::after{transform:translateX(16px)}
.pw-wrap{position:relative}
.pw-wrap input{padding-right:40px}
.pw-eye{position:absolute;right:10px;top:50%;transform:translateY(-50%);background:none;
        border:none;color:var(--sub);cursor:pointer;font-size:.95rem;padding:0;line-height:1;transition:color .18s}
.pw-eye:hover{color:var(--text)}
.fullscreen-btn{background:none;border:1px solid var(--border);border-radius:var(--rs);
               padding:7px 10px;cursor:pointer;font-size:1rem;color:var(--sub);transition:all .2s}
.fullscreen-btn:hover{border-color:var(--blue);color:var(--blue)}
@media(max-width:768px){
  .sidebar{transform:translateX(-100%)}
  .sidebar.open{transform:translateX(0)}
  .main{margin-left:0}
  .charts-grid{grid-template-columns:1fr}
  .stats-grid{grid-template-columns:1fr 1fr}
}
.mobile-menu-btn{display:none;background:none;border:none;color:var(--text);font-size:1.4rem;cursor:pointer;padding:4px}
@media(max-width:768px){.mobile-menu-btn{display:block}}
</style>
</head>
<body>

<!-- Sidebar -->
<nav class="sidebar" id="sidebar">
  <div class="sidebar-logo">
    <span>🍛</span>
    <div><h2>RasoiExpress</h2><div style="font-size:.65rem;color:var(--sub)">Admin Panel</div></div>
  </div>
  <div style="padding:10px 8px;flex:1;overflow-y:auto">
    <button class="nav-item active" onclick="showTab('dashboard',this)"><span>📊</span><span>Dashboard</span></button>
    <button class="nav-item" onclick="showTab('users',this)"><span>👥</span><span>Users</span></button>
    <button class="nav-item" onclick="showTab('orders',this)"><span>📦</span><span>Orders</span></button>
    <button class="nav-item" onclick="showTab('menu',this)"><span>🍽️</span><span>Menu Items</span></button>
    <button class="nav-item" onclick="showTab('activity',this)"><span>📋</span><span>Activity Log</span></button>
    <button class="nav-item" onclick="showTab('reports',this)"><span>📈</span><span>Reports</span></button>
  </div>
  <div class="sidebar-footer">
    <div style="font-size:.72rem;color:var(--sub);margin-bottom:8px;padding:0 10px">
      Session: <strong id="loginTimeDisplay">{{ login_time }}</strong>
    </div>
    <button class="nav-item" onclick="doLogout()" style="color:var(--red)"><span>🚪</span><span>Logout</span></button>
  </div>
</nav>

<!-- Main Content -->
<div class="main" id="mainContent">
  <!-- Topbar -->
  <div class="topbar">
    <div class="topbar-left">
      <button class="mobile-menu-btn" onclick="document.getElementById('sidebar').classList.toggle('open')">☰</button>
      <div>
        <div class="page-title" id="pageTitle">📊 Dashboard</div>
        <div style="font-size:.72rem;color:var(--sub)" id="pageSubtitle">Overview & Analytics</div>
      </div>
    </div>
    <div class="topbar-right">
      <div class="auto-refresh-badge" id="refreshBadge"><div class="sdot ok" id="liveStatusDot"></div><span id="liveStatusText">Live</span></div>
      <div class="session-timer" id="sessionTimer">⏱ --:--</div>
      <button class="icon-btn" onclick="toggleTheme()" id="themeBtn" title="Toggle Theme">🌙</button>
      <button class="fullscreen-btn" onclick="toggleFullscreen()" title="Fullscreen">⛶</button>
      <button class="icon-btn" onclick="refreshCurrent()" title="Refresh Data">🔄</button>
    </div>
  </div>

  <!-- DASHBOARD -->
  <div class="section active" id="sec-dashboard">
    <div class="stats-grid">
      <div class="stat-card" style="--c:var(--blue)"><div class="stat-val" id="statUsers">—</div><div class="stat-lbl">Total Users</div><div class="stat-ico">👥</div></div>
      <div class="stat-card" style="--c:var(--green)"><div class="stat-val" id="statOrders">—</div><div class="stat-lbl">Total Orders</div><div class="stat-ico">📦</div></div>
      <div class="stat-card" style="--c:var(--orange)"><div class="stat-val" id="statRevenue">—</div><div class="stat-lbl">Total Revenue</div><div class="stat-ico">💰</div></div>
      <div class="stat-card" style="--c:var(--yellow)"><div class="stat-val" id="statMenu">—</div><div class="stat-lbl">Menu Items</div><div class="stat-ico">🍽️</div></div>
    </div>
    <div class="charts-grid">
      <div class="chart-card"><div class="card-header"><div class="card-title">📊 Order Status Distribution</div></div><canvas id="chartStatus" height="200"></canvas></div>
      <div class="chart-card"><div class="card-header"><div class="card-title">🍽️ Menu by Category</div></div><canvas id="chartMenu" height="200"></canvas></div>
    </div>
    <div class="card"><div class="card-header"><div class="card-title">📋 Recent Activity</div><button class="btn btn-sm" onclick="loadActivity()">Refresh</button></div><div id="activityFeed"><div style="color:var(--sub);font-size:.82rem">Loading…</div></div></div>
  </div>

  <!-- USERS -->
  <div class="section" id="sec-users">
    <div class="card">
      <div class="card-header">
        <div class="card-title">👥 All Users</div>
        <div style="display:flex;gap:8px">
          <button class="btn btn-primary btn-sm" onclick="loadUsers()">🔄 Refresh</button>
        </div>
      </div>
      <div class="search-bar">
        <input type="text" class="search-input" id="userSearch" placeholder="🔍 Search users…" oninput="filterUsers()">
        <select class="search-input" id="userFilter" onchange="filterUsers()" style="max-width:160px">
          <option value="">All Status</option>
          <option value="active">Active</option>
          <option value="blocked">Blocked</option>
        </select>
      </div>
      <div style="overflow-x:auto">
        <table id="usersTable">
          <thead><tr><th>ID</th><th>Name</th><th>Email</th><th>Phone</th><th>Orders</th><th>Status</th><th>Joined</th><th>Actions</th></tr></thead>
          <tbody id="usersTbody"><tr class="loading-row"><td colspan="8">⏳ Loading users…</td></tr></tbody>
        </table>
      </div>
    </div>
  </div>

  <!-- ORDERS -->
  <div class="section" id="sec-orders">
    <div class="card">
      <div class="card-header">
        <div class="card-title">📦 All Orders</div>
        <button class="btn btn-primary btn-sm" onclick="loadOrders()">🔄 Refresh</button>
      </div>
      <div class="search-bar">
        <input type="text" class="search-input" id="orderSearch" placeholder="🔍 Search orders…" oninput="filterOrders()">
        <select class="search-input" id="orderStatusFilter" onchange="filterOrders()" style="max-width:160px">
          <option value="">All Status</option>
          <option value="placed">Placed</option>
          <option value="preparing">Preparing</option>
          <option value="on_the_way">On the Way</option>
          <option value="nearby">Nearby</option>
          <option value="delivered">Delivered</option>
        </select>
      </div>
      <div style="overflow-x:auto">
        <table>
          <thead><tr><th>Order ID</th><th>User</th><th>Items</th><th>Total</th><th>Status</th><th>Time</th><th>Actions</th></tr></thead>
          <tbody id="ordersTbody"><tr class="loading-row"><td colspan="7">⏳ Loading orders…</td></tr></tbody>
        </table>
      </div>
    </div>
  </div>

  <!-- MENU -->
  <div class="section" id="sec-menu">
    <div class="card">
      <div class="card-header">
        <div class="card-title">🍽️ Menu Items</div>
        <div style="display:flex;gap:8px">
          <button class="btn btn-primary btn-sm" onclick="openAddMenu()">➕ Add Item</button>
          <button class="btn btn-sm" style="background:var(--border)" onclick="seedMenu()">🌱 Seed Menu</button>
          <button class="btn btn-primary btn-sm" onclick="loadMenu()">🔄 Refresh</button>
        </div>
      </div>
      <div class="search-bar">
        <input type="text" class="search-input" id="menuSearch" placeholder="🔍 Search menu…" oninput="filterMenu()">
        <select class="search-input" id="menuCatFilter" onchange="filterMenu()" style="max-width:180px">
          <option value="">All Categories</option>
          <option>Veg Curries</option><option>South Indian</option><option>Biryani &amp; Rice</option>
          <option>Street Food</option><option>Snacks</option><option>Breads</option>
          <option>Desserts</option><option>Drinks</option><option>Non-Veg Curries</option>
          <option>Continental</option><option>Chinese</option>
        </select>
        <select class="search-input" id="menuTypeFilter" onchange="filterMenu()" style="max-width:120px">
          <option value="">All Types</option><option value="veg">Veg</option><option value="nonveg">Non-Veg</option>
        </select>
      </div>
      <div style="overflow-x:auto">
        <table>
          <thead><tr><th>ID</th><th>Name</th><th>Category</th><th>Price</th><th>Rating</th><th>Type</th><th>Tags</th><th>Actions</th></tr></thead>
          <tbody id="menuTbody"><tr class="loading-row"><td colspan="8">⏳ Loading menu…</td></tr></tbody>
        </table>
      </div>
    </div>
  </div>

  <!-- ACTIVITY LOG -->
  <div class="section" id="sec-activity">
    <div class="card">
      <div class="card-header">
        <div class="card-title">📋 Activity Log</div>
        <div style="display:flex;gap:8px">
          <button class="btn btn-sm btn-primary" onclick="loadActivity()">🔄 Refresh</button>
          <button class="btn btn-sm btn-danger" onclick="clearActivity()">🗑️ Clear All</button>
        </div>
      </div>
      <div style="overflow-x:auto">
        <table>
          <thead><tr><th>ID</th><th>Action</th><th>Details</th><th>IP</th><th>Time</th></tr></thead>
          <tbody id="activityTbody"><tr class="loading-row"><td colspan="5">⏳ Loading…</td></tr></tbody>
        </table>
      </div>
    </div>
  </div>

  <!-- REPORTS -->
  <div class="section" id="sec-reports">
    <div class="card"><div class="card-header"><div class="card-title">📈 Export Reports</div></div>
      <div style="display:grid;grid-template-columns:repeat(auto-fit,minmax(200px,1fr));gap:16px;margin-top:8px">
        <div style="background:var(--bg);border:1px solid var(--border);border-radius:var(--r);padding:20px;cursor:pointer;transition:all .2s" onclick="printReport('summary')" onmouseover="this.style.borderColor='var(--blue)'" onmouseout="this.style.borderColor='var(--border)'">
          <div style="font-size:2rem;margin-bottom:8px">📊</div><div style="font-weight:700;margin-bottom:4px">Summary Report</div>
          <div style="font-size:.78rem;color:var(--sub)">Overall stats & KPIs</div>
        </div>
        <div style="background:var(--bg);border:1px solid var(--border);border-radius:var(--r);padding:20px;cursor:pointer;transition:all .2s" onclick="printReport('users')" onmouseover="this.style.borderColor='var(--blue)'" onmouseout="this.style.borderColor='var(--border)'">
          <div style="font-size:2rem;margin-bottom:8px">👥</div><div style="font-weight:700;margin-bottom:4px">Users Report</div>
          <div style="font-size:.78rem;color:var(--sub)">All registered users</div>
        </div>
        <div style="background:var(--bg);border:1px solid var(--border);border-radius:var(--r);padding:20px;cursor:pointer;transition:all .2s" onclick="printReport('orders')" onmouseover="this.style.borderColor='var(--blue)'" onmouseout="this.style.borderColor='var(--border)'">
          <div style="font-size:2rem;margin-bottom:8px">📦</div><div style="font-weight:700;margin-bottom:4px">Orders Report</div>
          <div style="font-size:.78rem;color:var(--sub)">Full order history</div>
        </div>
      </div>
    </div>
  </div>
</div><!-- /main -->

<!-- Edit User Modal -->
<div class="modal-overlay" id="editUserModal">
  <div class="modal">
    <h3>✏️ Edit User</h3>
    <input type="hidden" id="editUserId">
    <div class="form-row"><label>Name</label><input type="text" id="editUserName"></div>
    <div class="form-row"><label>Email</label><input type="email" id="editUserEmail"></div>
    <div class="form-row"><label>Phone</label><input type="text" id="editUserPhone"></div>
    <div class="form-row"><label>New Password (leave blank to keep)</label>
      <div class="pw-wrap"><input type="password" id="editUserPw" placeholder="New password…">
      <button type="button" class="pw-eye" onclick="togglePwEdit()">👁</button></div>
    </div>
    <div class="modal-footer">
      <button class="btn" style="background:var(--border)" onclick="closeModal('editUserModal')">Cancel</button>
      <button class="btn btn-primary" onclick="saveUser()">💾 Save Changes</button>
    </div>
  </div>
</div>

<!-- Edit Menu Modal -->
<div class="modal-overlay" id="editMenuModal">
  <div class="modal">
    <h3 id="menuModalTitle">✏️ Edit Menu Item</h3>
    <input type="hidden" id="editMenuId">
    <div class="form-row"><label>Name</label><input type="text" id="editMenuName"></div>
    <div class="form-row"><label>Description</label><textarea id="editMenuDesc"></textarea></div>
    <div style="display:grid;grid-template-columns:1fr 1fr;gap:12px">
      <div class="form-row"><label>Price (₹)</label><input type="number" id="editMenuPrice"></div>
      <div class="form-row"><label>Rating</label><input type="number" step=".1" min="1" max="5" id="editMenuRating"></div>
    </div>
    <div style="display:grid;grid-template-columns:1fr 1fr;gap:12px">
      <div class="form-row"><label>Category</label>
        <select id="editMenuCat">
          <option>Veg Curries</option><option>South Indian</option><option>Biryani &amp; Rice</option>
          <option>Street Food</option><option>Snacks</option><option>Breads</option>
          <option>Desserts</option><option>Drinks</option><option>Non-Veg Curries</option>
          <option>Continental</option><option>Chinese</option>
        </select>
      </div>
      <div class="form-row"><label>Type</label>
        <select id="editMenuType"><option value="veg">Veg</option><option value="nonveg">Non-Veg</option></select>
      </div>
    </div>
    <div class="form-row"><label>Restaurant</label><input type="text" id="editMenuRest"></div>
    <div class="form-row"><label>Image URL</label><input type="text" id="editMenuImg"></div>
    <div class="form-row"><label>Emoji</label><input type="text" id="editMenuEmoji" maxlength="2"></div>
    <div class="form-row"><label>Prep Time</label><input type="text" id="editMenuTime" placeholder="e.g. 25 mins"></div>
    <div style="display:flex;gap:16px;margin-top:8px">
      <label style="display:flex;align-items:center;gap:7px;cursor:pointer;font-size:.79rem;color:var(--sub)"><button type="button" class="sw-tog" id="swBest" onclick="this.classList.toggle('on')"></button>⭐ Bestseller</label>
      <label style="display:flex;align-items:center;gap:7px;cursor:pointer;font-size:.79rem;color:var(--sub)"><button type="button" class="sw-tog" id="swNew" onclick="this.classList.toggle('on')"></button>✨ New</label>
      <label style="display:flex;align-items:center;gap:7px;cursor:pointer;font-size:.79rem;color:var(--sub)"><button type="button" class="sw-tog" id="swSpicy" onclick="this.classList.toggle('on')"></button>🌶️ Spicy</label>
    </div>
    <div class="modal-footer">
      <button class="btn" style="background:var(--border)" onclick="closeModal('editMenuModal')">Cancel</button>
      <button class="btn btn-primary" onclick="saveMenu()">💾 Save Item</button>
    </div>
  </div>
</div>

<!-- Toast -->
<div class="toast" id="toast"></div>

<script>
const API = window.location.origin;
let allUsers=[], allOrders=[], allMenu=[], autoRefreshTimer, sessionSeconds=7200;
let charts = {};

// ── THEME ──────────────────────────────────────────
function toggleTheme(){
  const h=document.documentElement, t=h.getAttribute('data-theme');
  h.setAttribute('data-theme', t==='dark'?'light':'dark');
  document.getElementById('themeBtn').textContent = t==='dark'?'☀️':'🌙';
  localStorage.setItem('adminTheme', t==='dark'?'light':'dark');
}
(function(){
  const t=localStorage.getItem('adminTheme');
  if(t){ document.documentElement.setAttribute('data-theme',t);
    document.getElementById('themeBtn').textContent = t==='dark'?'🌙':'☀️';}
})();

// ── FULLSCREEN ──────────────────────────────────────
function toggleFullscreen(){
  if(!document.fullscreenElement) document.documentElement.requestFullscreen().catch(()=>{});
  else document.exitFullscreen();
}

// ── SESSION TIMER ───────────────────────────────────
function startTimer(){
  setInterval(()=>{
    if(sessionSeconds<=0){showToast('Session expired. Redirecting…','error'); setTimeout(()=>window.location='/admin',2000); return;}
    sessionSeconds--;
    const m=String(Math.floor(sessionSeconds/60)).padStart(2,'0'), s=String(sessionSeconds%60).padStart(2,'0');
    const el=document.getElementById('sessionTimer');
    if(el) el.textContent=`⏱ ${m}:${s}`;
    if(sessionSeconds===300) showToast('⚠️ Session expires in 5 minutes','error');
  },1000);
}
startTimer();

// ── TOAST ───────────────────────────────────────────
function showToast(msg, type='success'){
  const t=document.getElementById('toast');
  if(!t)return;
  t.textContent=msg; t.className=`toast show ${type}`;
  setTimeout(()=>t.className='toast',3200);
}

// ── TABS ────────────────────────────────────────────
function showTab(name,btn){
  document.querySelectorAll('.section').forEach(s=>s.classList.remove('active'));
  document.querySelectorAll('.nav-item').forEach(b=>b.classList.remove('active'));
  document.getElementById('sec-'+name).classList.add('active');
  if(btn) btn.classList.add('active');
  const titles={dashboard:'📊 Dashboard',users:'👥 Users',orders:'📦 Orders',
                menu:'🍽️ Menu',activity:'📋 Activity Log',reports:'📈 Reports'};
  const subs={dashboard:'Overview & Analytics',users:'Manage registered users',
              orders:'View & manage orders',menu:'Manage food items',
              activity:'System activity log',reports:'Export & print reports'};
  document.getElementById('pageTitle').textContent=titles[name]||name;
  document.getElementById('pageSubtitle').textContent=subs[name]||'';
  if(name==='users') loadUsers();
  else if(name==='orders') loadOrders();
  else if(name==='menu') loadMenu();
  else if(name==='activity') loadActivity();
  else if(name==='dashboard') loadDashboard();
}

function refreshCurrent(){
  const active=document.querySelector('.section.active');
  if(!active)return;
  const id=active.id.replace('sec-','');
  showTab(id, document.querySelector(`.nav-item.active`));
}

// ── AUTO REFRESH ─────────────────────────────────────
let arInterval=null;
function startAutoRefresh(){
  if(arInterval) clearInterval(arInterval);
  arInterval = setInterval(()=>{ refreshCurrent(); }, 30000);
}
startAutoRefresh();

// ── FETCH HELPER ─────────────────────────────────────
async function apiFetch(path, opts={}){
  const r = await fetch(API+path, {
    ...opts,
    headers:{'Content-Type':'application/json',...(opts.headers||{}),
             'X-Admin-Session':'1'}
  });
  return r;
}

// ── DASHBOARD ────────────────────────────────────────
async function loadDashboard(){
  try{
    const r = await apiFetch('/api/admin/stats');
    const d = await r.json();
    document.getElementById('statUsers').textContent   = d.users??'—';
    document.getElementById('statOrders').textContent  = d.orders??'—';
    document.getElementById('statRevenue').textContent = d.revenue!=null?'₹'+Number(d.revenue).toLocaleString('en-IN'):'—';
    document.getElementById('statMenu').textContent    = d.menu??'—';
    if(d.order_status) renderStatusChart(d.order_status);
    if(d.menu_categories) renderMenuChart(d.menu_categories);
  }catch(e){ console.warn('Dashboard load error',e); }
  loadActivity();
}

function renderStatusChart(data){
  const ctx=document.getElementById('chartStatus');
  if(!ctx)return;
  if(charts.status) charts.status.destroy();
  const labels=Object.keys(data).map(k=>k.replace('_',' ').replace(/\b\w/g,c=>c.toUpperCase()));
  charts.status=new Chart(ctx,{type:'doughnut',data:{labels,
    datasets:[{data:Object.values(data),backgroundColor:['#3b82f6','#f97316','#eab308','#8b5cf6','#22c55e'],borderWidth:0}]},
    options:{responsive:true,plugins:{legend:{position:'bottom',labels:{color:'var(--sub)',font:{size:11}}}}}});
}

function renderMenuChart(data){
  const ctx=document.getElementById('chartMenu');
  if(!ctx)return;
  if(charts.menu) charts.menu.destroy();
  charts.menu=new Chart(ctx,{type:'bar',data:{
    labels:Object.keys(data),
    datasets:[{label:'Items',data:Object.values(data),backgroundColor:'rgba(249,115,22,.7)',borderRadius:6}]},
    options:{responsive:true,plugins:{legend:{display:false}},
             scales:{x:{ticks:{color:'var(--sub)',font:{size:10}},grid:{display:false}},
                     y:{ticks:{color:'var(--sub)'},grid:{color:'var(--border)'}}}}});
}

// ── USERS ────────────────────────────────────────────
async function loadUsers(){
  document.getElementById('usersTbody').innerHTML='<tr class="loading-row"><td colspan="8">⏳ Loading…</td></tr>';
  try{
    const r=await apiFetch('/api/admin/users'); const d=await r.json();
    allUsers=d.users||[];
    renderUsers(allUsers);
  }catch(e){ document.getElementById('usersTbody').innerHTML='<tr class="loading-row"><td colspan="8">❌ Failed to load users</td></tr>'; }
}

function renderUsers(users){
  const tb=document.getElementById('usersTbody');
  if(!users.length){tb.innerHTML='<tr><td colspan="8"><div class="empty-state"><div class="emoji">👻</div><div>No users found</div></div></td></tr>';return;}
  tb.innerHTML=users.map(u=>`<tr>
    <td><span style="color:var(--sub);font-family:monospace">#${u.id}</span></td>
    <td><strong>${esc(u.name)}</strong></td>
    <td style="color:var(--sub)">${esc(u.email)}</td>
    <td>${esc(u.phone||'—')}</td>
    <td><span class="badge blue">${u.order_count||0} orders</span></td>
    <td>${u.is_blocked?'<span class="badge red">🔒 Blocked</span>':'<span class="badge green">✅ Active</span>'}</td>
    <td style="color:var(--sub);font-size:.75rem">${fmtDate(u.created_at)}</td>
    <td>
      <button class="btn btn-sm btn-primary" onclick="editUser(${u.id})" style="margin-right:4px">✏️</button>
      <button class="btn btn-sm btn-warn" onclick="toggleBlock(${u.id},${u.is_blocked})" style="margin-right:4px">${u.is_blocked?'🔓':'🔒'}</button>
      <button class="btn btn-sm btn-danger" onclick="delUser(${u.id})">🗑️</button>
    </td>
  </tr>`).join('');
}

function filterUsers(){
  const q=document.getElementById('userSearch').value.toLowerCase();
  const f=document.getElementById('userFilter').value;
  let u=allUsers.filter(u=>{
    const m=!q||(u.name||'').toLowerCase().includes(q)||(u.email||'').toLowerCase().includes(q);
    const s=!f||(f==='blocked'?u.is_blocked:!u.is_blocked);
    return m&&s;
  });
  renderUsers(u);
}

async function editUser(id){
  const u=allUsers.find(x=>x.id===id);
  if(!u)return;
  document.getElementById('editUserId').value=id;
  document.getElementById('editUserName').value=u.name||'';
  document.getElementById('editUserEmail').value=u.email||'';
  document.getElementById('editUserPhone').value=u.phone||'';
  document.getElementById('editUserPw').value='';
  document.getElementById('editUserModal').classList.add('show');
}

async function saveUser(){
  const id=document.getElementById('editUserId').value;
  const body={name:document.getElementById('editUserName').value,
               email:document.getElementById('editUserEmail').value,
               phone:document.getElementById('editUserPhone').value};
  const pw=document.getElementById('editUserPw').value;
  if(pw) body.password=pw;
  const r=await apiFetch(`/api/admin/users/${id}`,{method:'PUT',body:JSON.stringify(body)});
  if(r.ok){showToast('✅ User updated');closeModal('editUserModal');loadUsers();}
  else showToast('❌ Update failed','error');
}

function togglePwEdit(){
  const i=document.getElementById('editUserPw');
  i.type=i.type==='password'?'text':'password';
}

async function toggleBlock(id,blocked){
  if(!confirm(blocked?'Unblock this user?':'Block this user?'))return;
  const r=await apiFetch(`/api/admin/users/${id}/block`,{method:'POST',body:JSON.stringify({block:!blocked})});
  if(r.ok){showToast(blocked?'✅ User unblocked':'🔒 User blocked');loadUsers();}
  else showToast('❌ Action failed','error');
}

async function delUser(id){
  if(!confirm('Permanently delete this user?'))return;
  const r=await apiFetch(`/api/admin/users/${id}`,{method:'DELETE'});
  if(r.ok){showToast('🗑️ User deleted');loadUsers();}
  else showToast('❌ Delete failed','error');
}

// ── ORDERS ────────────────────────────────────────────
async function loadOrders(){
  document.getElementById('ordersTbody').innerHTML='<tr class="loading-row"><td colspan="7">⏳ Loading…</td></tr>';
  try{
    const r=await apiFetch('/api/admin/orders'); const d=await r.json();
    allOrders=d.orders||[];
    renderOrders(allOrders);
  }catch(e){ document.getElementById('ordersTbody').innerHTML='<tr class="loading-row"><td colspan="7">❌ Failed to load orders</td></tr>'; }
}

const ORDER_STATUS_BADGES={'placed':'blue','preparing':'orange','on_the_way':'yellow','nearby':'yellow','delivered':'green'};

function renderOrders(orders){
  const tb=document.getElementById('ordersTbody');
  if(!orders.length){tb.innerHTML='<tr><td colspan="7"><div class="empty-state"><div class="emoji">📭</div><div>No orders found</div></div></td></tr>';return;}
  tb.innerHTML=orders.map(o=>`<tr>
    <td><span style="font-family:monospace;font-size:.78rem;color:var(--blue)">${esc(o.id)}</span></td>
    <td>${esc(o.user_name||'User #'+o.user_id)}</td>
    <td style="color:var(--sub);font-size:.78rem">${Array.isArray(o.items)?o.items.slice(0,2).map(i=>i.name||'').join(', ')+(o.items.length>2?'…':''):o.items||'—'}</td>
    <td><strong>₹${Number(o.total).toLocaleString('en-IN')}</strong></td>
    <td><span class="badge ${ORDER_STATUS_BADGES[o.status]||'blue'}">${(o.status||'').replace('_',' ').replace(/\b\w/g,c=>c.toUpperCase())}</span></td>
    <td style="color:var(--sub);font-size:.75rem">${fmtDate(o.placed_at)}</td>
    <td>
      ${o.current_step<4?`<button class="btn btn-sm btn-primary" onclick="advanceOrder('${o.id}')">▶ Advance</button>`:'<span class="badge green">Done</span>'}
    </td>
  </tr>`).join('');
}

function filterOrders(){
  const q=document.getElementById('orderSearch').value.toLowerCase();
  const s=document.getElementById('orderStatusFilter').value;
  renderOrders(allOrders.filter(o=>{
    const m=!q||o.id.toLowerCase().includes(q)||(o.user_name||'').toLowerCase().includes(q);
    const sf=!s||o.status===s;
    return m&&sf;
  }));
}

async function advanceOrder(id){
  const r=await apiFetch(`/api/admin/orders/${id}/step`,{method:'PUT'});
  if(r.ok){showToast('✅ Order advanced');loadOrders();}
  else showToast('❌ Failed','error');
}

// ── MENU ─────────────────────────────────────────────
async function loadMenu(){
  document.getElementById('menuTbody').innerHTML='<tr class="loading-row"><td colspan="8">⏳ Loading…</td></tr>';
  try{
    const r=await apiFetch('/api/admin/menu'); const d=await r.json();
    allMenu=d.items||[];
    renderMenu(allMenu);
  }catch(e){ document.getElementById('menuTbody').innerHTML='<tr class="loading-row"><td colspan="8">❌ Failed to load menu</td></tr>'; }
}

function renderMenu(items){
  const tb=document.getElementById('menuTbody');
  if(!items.length){tb.innerHTML='<tr><td colspan="8"><div class="empty-state"><div class="emoji">🍽️</div><div>No items found</div></div></td></tr>';return;}
  tb.innerHTML=items.map(m=>`<tr>
    <td style="color:var(--sub)">#${m.id}</td>
    <td><strong>${esc(m.name)}</strong><div style="font-size:.72rem;color:var(--sub)">${esc(m.restaurant||'')}</div></td>
    <td><span class="badge blue">${esc(m.category)}</span></td>
    <td><strong>₹${m.price}</strong></td>
    <td>⭐ ${m.rating}</td>
    <td><span class="badge ${m.type==='veg'?'green':'orange'}">${m.type==='veg'?'🌿 Veg':'🍗 Non-Veg'}</span></td>
    <td style="font-size:.78rem">${m.is_best?'⭐ Best ':''} ${m.is_new?'✨ New ':''} ${m.is_spicy?'🌶️ ':''}</td>
    <td>
      <button class="btn btn-sm btn-primary" onclick="editMenuItem(${m.id})" style="margin-right:4px">✏️</button>
      <button class="btn btn-sm btn-danger" onclick="delMenu(${m.id})">🗑️</button>
    </td>
  </tr>`).join('');
}

function filterMenu(){
  const q=document.getElementById('menuSearch').value.toLowerCase();
  const cat=document.getElementById('menuCatFilter').value;
  const tp=document.getElementById('menuTypeFilter').value;
  renderMenu(allMenu.filter(m=>{
    const mq=!q||(m.name||'').toLowerCase().includes(q)||(m.category||'').toLowerCase().includes(q);
    const mc=!cat||m.category===cat;
    const mt=!tp||m.type===tp;
    return mq&&mc&&mt;
  }));
}

function openAddMenu(){
  document.getElementById('menuModalTitle').textContent='➕ Add Menu Item';
  document.getElementById('editMenuId').value='';
  ['editMenuName','editMenuDesc','editMenuRest','editMenuImg','editMenuEmoji','editMenuTime'].forEach(id=>document.getElementById(id).value='');
  document.getElementById('editMenuPrice').value='';
  document.getElementById('editMenuRating').value='4.0';
  document.getElementById('editMenuCat').value='Veg Curries';
  document.getElementById('editMenuType').value='veg';
  document.getElementById('editMenuEmoji').value='🍛';
  ['swBest','swNew','swSpicy'].forEach(id=>document.getElementById(id).classList.remove('on'));
  document.getElementById('editMenuModal').classList.add('show');
}

async function editMenuItem(id){
  const m=allMenu.find(x=>x.id===id);
  if(!m)return;
  document.getElementById('menuModalTitle').textContent='✏️ Edit Menu Item';
  document.getElementById('editMenuId').value=id;
  document.getElementById('editMenuName').value=m.name||'';
  document.getElementById('editMenuDesc').value=m.description||'';
  document.getElementById('editMenuPrice').value=m.price||'';
  document.getElementById('editMenuRating').value=m.rating||4.0;
  document.getElementById('editMenuCat').value=m.category||'Veg Curries';
  document.getElementById('editMenuType').value=m.type||'veg';
  document.getElementById('editMenuRest').value=m.restaurant||'';
  document.getElementById('editMenuImg').value=m.image||'';
  document.getElementById('editMenuEmoji').value=m.emoji||'🍛';
  document.getElementById('editMenuTime').value=m.time||'30 mins';
  document.getElementById('swBest').classList.toggle('on',!!m.is_best);
  document.getElementById('swNew').classList.toggle('on',!!m.is_new);
  document.getElementById('swSpicy').classList.toggle('on',!!m.is_spicy);
  document.getElementById('editMenuModal').classList.add('show');
}

async function saveMenu(){
  const id=document.getElementById('editMenuId').value;
  const body={
    name:document.getElementById('editMenuName').value,
    description:document.getElementById('editMenuDesc').value,
    price:parseFloat(document.getElementById('editMenuPrice').value)||0,
    rating:parseFloat(document.getElementById('editMenuRating').value)||4.0,
    category:document.getElementById('editMenuCat').value,
    type:document.getElementById('editMenuType').value,
    restaurant:document.getElementById('editMenuRest').value,
    image:document.getElementById('editMenuImg').value,
    emoji:document.getElementById('editMenuEmoji').value,
    time:document.getElementById('editMenuTime').value,
    is_best:document.getElementById('swBest').classList.contains('on'),
    is_new:document.getElementById('swNew').classList.contains('on'),
    is_spicy:document.getElementById('swSpicy').classList.contains('on'),
  };
  const method=id?'PUT':'POST';
  const path=id?`/api/admin/menu/${id}`:'/api/admin/menu';
  const r=await apiFetch(path,{method,body:JSON.stringify(body)});
  if(r.ok){showToast(id?'✅ Item updated':'✅ Item added');closeModal('editMenuModal');loadMenu();}
  else showToast('❌ Save failed','error');
}

async function delMenu(id){
  if(!confirm('Delete this menu item?'))return;
  const r=await apiFetch(`/api/admin/menu/${id}`,{method:'DELETE'});
  if(r.ok){showToast('🗑️ Item deleted');loadMenu();}
  else showToast('❌ Delete failed','error');
}

async function seedMenu(){
  if(!confirm('Re-seed the menu? This will add missing items.'))return;
  const r=await apiFetch('/api/menu/seed',{method:'POST'});
  if(r.ok){const d=await r.json();showToast('🌱 '+d.message);loadMenu();}
  else showToast('❌ Seed failed','error');
}

// ── ACTIVITY ──────────────────────────────────────────
async function loadActivity(){
  try{
    const r=await apiFetch('/api/admin/log'); const d=await r.json();
    const rows=d.logs||[];
    // Feed in dashboard
    const feed=document.getElementById('activityFeed');
    if(feed) feed.innerHTML=rows.slice(0,8).map(l=>`
      <div class="activity-item">
        <div class="activity-dot"></div>
        <div class="activity-text"><strong>${esc(l.action)}</strong><br><span style="color:var(--sub)">${esc(l.details||'')}</span></div>
        <div class="activity-time">${fmtDate(l.created_at)}</div>
      </div>`).join('')||'<div style="color:var(--sub);padding:12px;font-size:.82rem">No activity yet.</div>';
    // Table in activity tab
    const tb=document.getElementById('activityTbody');
    if(tb){
      if(!rows.length){tb.innerHTML='<tr><td colspan="5"><div class="empty-state"><div class="emoji">📋</div><div>No logs yet</div></div></td></tr>';return;}
      tb.innerHTML=rows.map(l=>`<tr>
        <td style="color:var(--sub)">#${l.id}</td>
        <td><strong>${esc(l.action)}</strong></td>
        <td style="color:var(--sub)">${esc(l.details||'—')}</td>
        <td style="font-family:monospace;font-size:.75rem">${esc(l.ip||'—')}</td>
        <td style="color:var(--sub);font-size:.75rem">${fmtDate(l.created_at)}</td>
      </tr>`).join('');
    }
  }catch(e){ console.warn('Activity load error',e); }
}

async function clearActivity(){
  if(!confirm('Clear all activity logs?'))return;
  const r=await apiFetch('/api/admin/log',{method:'DELETE'});
  if(r.ok){showToast('🗑️ Logs cleared');loadActivity();}
  else showToast('❌ Failed','error');
}

// ── REPORTS ───────────────────────────────────────────
async function printReport(type){
  const statsR=await apiFetch('/api/admin/stats'); const stats=await statsR.json();
  let html=`<html><head><title>RasoiExpress Report — ${type}</title><style>
    body{font-family:Arial,sans-serif;padding:32px;color:#1e293b}
    h1{color:#f97316;border-bottom:2px solid #f97316;padding-bottom:12px}
    table{width:100%;border-collapse:collapse;margin-top:16px}
    th{background:#f97316;color:#fff;padding:10px;text-align:left}
    td{padding:9px;border-bottom:1px solid #e2e8f0}
    .kpi{display:inline-block;background:#f1f5f9;padding:16px 24px;border-radius:12px;margin:8px;text-align:center}
    .kpi-val{font-size:2rem;font-weight:800;color:#f97316}
    .kpi-lbl{font-size:.8rem;color:#64748b;margin-top:4px}
  </style></head><body>
  <h1>🍛 RasoiExpress Admin Report</h1>
  <p style="color:#64748b">Generated: ${new Date().toLocaleString()}</p>
  <div>
    <div class="kpi"><div class="kpi-val">${stats.users}</div><div class="kpi-lbl">Users</div></div>
    <div class="kpi"><div class="kpi-val">${stats.orders}</div><div class="kpi-lbl">Orders</div></div>
    <div class="kpi"><div class="kpi-val">₹${Number(stats.revenue||0).toLocaleString('en-IN')}</div><div class="kpi-lbl">Revenue</div></div>
  </div>`;
  if(type==='users'){
    html+=`<h2>Users</h2><table><tr><th>ID</th><th>Name</th><th>Email</th><th>Phone</th><th>Status</th><th>Joined</th></tr>`;
    allUsers.forEach(u=>{html+=`<tr><td>#${u.id}</td><td>${u.name}</td><td>${u.email}</td><td>${u.phone||'—'}</td><td>${u.is_blocked?'Blocked':'Active'}</td><td>${fmtDate(u.created_at)}</td></tr>`;});
    html+='</table>';
  } else if(type==='orders'){
    html+=`<h2>Orders</h2><table><tr><th>ID</th><th>User</th><th>Total</th><th>Status</th><th>Time</th></tr>`;
    allOrders.forEach(o=>{html+=`<tr><td>${o.id}</td><td>${o.user_name||o.user_id}</td><td>₹${o.total}</td><td>${o.status}</td><td>${fmtDate(o.placed_at)}</td></tr>`;});
    html+='</table>';
  }
  html+='</body></html>';
  const w=window.open('','_blank'); w.document.write(html); w.document.close(); w.print();
}

// ── LOGOUT ────────────────────────────────────────────
async function doLogout(){
  await apiFetch('/admin/logout');
  window.location='/admin';
}

// ── HELPERS ───────────────────────────────────────────
function closeModal(id){ document.getElementById(id).classList.remove('show'); }
function esc(s){ if(!s)return''; return String(s).replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;').replace(/"/g,'&quot;'); }
function fmtDate(s){ if(!s)return'—'; try{ return new Date(s).toLocaleString('en-IN',{day:'2-digit',month:'short',year:'numeric',hour:'2-digit',minute:'2-digit'}); }catch{ return s; } }

// ── INIT ──────────────────────────────────────────────
window.addEventListener('click', e=>{ if(e.target.classList.contains('modal-overlay')) e.target.classList.remove('show'); });
loadDashboard();
</script>
</body>
</html>"""

# ═══════════════════════════════════════════════════════════════
#  ADMIN ROUTES
# ═══════════════════════════════════════════════════════════════
def get_ip(): return request.remote_addr or "unknown"

@app.route("/admin")
def admin_page():
    if session.get(ADMIN_SESSION_KEY): return redirect("/admin/dashboard")
    ip = get_ip()
    attempt_data = login_attempts.get(ip, {})
    locked_until  = attempt_data.get("locked_until")
    now = datetime.now(timezone.utc)
    if locked_until and now < locked_until:
        mins = int((locked_until - now).total_seconds() // 60) + 1
        return render_template_string(LOGIN_HTML, error=None, username="", locked=True, locked_mins=mins, attempts=0)
    return render_template_string(LOGIN_HTML, error=None, username="", locked=False, locked_mins=0,
                                  attempts=attempt_data.get("count", 0))

@app.route("/admin/login", methods=["POST"])
def admin_login():
    d = request.get_json() or {}
    username = (d.get("username") or "").strip()
    password  = d.get("password", "")
    ip = get_ip()
    now = datetime.now(timezone.utc)

    attempt_data = login_attempts.setdefault(ip, {"count": 0, "locked_until": None})
    if attempt_data.get("locked_until") and now < attempt_data["locked_until"]:
        mins = int((attempt_data["locked_until"] - now).total_seconds() // 60) + 1
        return jsonify({"error": f"Too many attempts. Locked for {mins} min(s)."}), 429

    pw_hash = hashlib.sha256(password.encode()).hexdigest()
    if username == ADMIN_ID and pw_hash == ADMIN_PASS_HASH:
        attempt_data["count"] = 0
        attempt_data["locked_until"] = None
        session[ADMIN_SESSION_KEY] = True
        session["login_time"] = datetime.now().strftime("%d %b %Y, %I:%M %p")
        session.permanent = True
        log_action("Admin Login", f"IP: {ip}")
        return jsonify({"message": "OK"})
    else:
        attempt_data["count"] = attempt_data.get("count", 0) + 1
        if attempt_data["count"] >= MAX_LOGIN_ATTEMPTS:
            attempt_data["locked_until"] = now + timedelta(minutes=15)
            log_action("Admin Locked", f"IP: {ip} after {MAX_LOGIN_ATTEMPTS} attempts")
            return jsonify({"error": "Too many failed attempts. Locked for 15 minutes."}), 429
        rem = MAX_LOGIN_ATTEMPTS - attempt_data["count"]
        return jsonify({"error": f"Invalid credentials. {rem} attempt(s) remaining."}), 401

@app.route("/admin/dashboard")
@admin_page_required
def admin_dashboard():
    return render_template_string(DASH_HTML, login_time=session.get("login_time", "—"))

@app.route("/admin/logout")
def admin_logout():
    session.clear()
    return redirect("/admin")

# ═══════════════════════════════════════════════════════════════
#  API ROUTES
# ═══════════════════════════════════════════════════════════════
@app.route("/api/health")
def health():
    return jsonify({"status": "ok", "db": "supabase_postgresql", "time": datetime.now().isoformat()})

@app.route("/api/admin/stats")
@admin_required
def admin_stats():
    users   = q1("SELECT COUNT(*) AS c FROM users")["c"]
    orders  = q1("SELECT COUNT(*) AS c FROM orders")["c"]
    revenue = q1("SELECT COALESCE(SUM(total),0) AS r FROM orders")["r"]
    menu    = q1("SELECT COUNT(*) AS c FROM menu_items")["c"]
    status_rows = qa("SELECT status, COUNT(*) AS c FROM orders GROUP BY status")
    order_status = {r["status"]: r["c"] for r in status_rows}
    cat_rows = qa("SELECT category, COUNT(*) AS c FROM menu_items GROUP BY category ORDER BY c DESC LIMIT 8")
    menu_categories = {r["category"]: r["c"] for r in cat_rows}
    return jsonify({"users": users, "orders": orders, "revenue": float(revenue),
                    "menu": menu, "order_status": order_status, "menu_categories": menu_categories})

@app.route("/api/admin/users")
@admin_required
def admin_users():
    rows = qa("""SELECT u.id,u.name,u.email,u.phone,u.address,u.picture,u.profile_color,
                        u.is_blocked,u.created_at,
                        COUNT(o.id) AS order_count
                 FROM users u LEFT JOIN orders o ON o.user_id=u.id
                 GROUP BY u.id ORDER BY u.id DESC""")
    return jsonify({"users": rows, "count": len(rows)})

@app.route("/api/admin/users/<int:uid>")
@admin_required
def admin_get_user(uid):
    u = q1("SELECT * FROM users WHERE id=%s", (uid,))
    if not u: return jsonify({"error": "Not found"}), 404
    return jsonify({"user": u})

@app.route("/api/admin/users/<int:uid>", methods=["PUT"])
@admin_required
def admin_upd_user(uid):
    d = request.get_json() or {}
    cur = q1("SELECT * FROM users WHERE id=%s", (uid,))
    if not cur: return jsonify({"error": "Not found"}), 404
    name  = (d.get("name")  or cur["name"]).strip()
    email = (d.get("email") or cur["email"]).strip().lower()
    phone = (d.get("phone") or cur.get("phone") or "").strip()
    pw    = d.get("password", "")
    if pw:
        run("UPDATE users SET name=%s,email=%s,phone=%s,password=%s WHERE id=%s",
            (name, email, phone, hash_pw(pw), uid))
    else:
        run("UPDATE users SET name=%s,email=%s,phone=%s WHERE id=%s", (name, email, phone, uid))
    log_action("Admin Edit User", f"uid={uid}")
    return jsonify({"message": "Updated ✅"})

@app.route("/api/admin/users/<int:uid>/block", methods=["POST"])
@admin_required
def admin_block_user(uid):
    d = request.get_json() or {}
    block = bool(d.get("block", True))
    run("UPDATE users SET is_blocked=%s WHERE id=%s", (block, uid))
    log_action("Admin Block/Unblock", f"uid={uid} blocked={block}")
    return jsonify({"message": "Blocked" if block else "Unblocked"})

@app.route("/api/admin/users/<int:uid>", methods=["DELETE"])
@admin_required
def admin_del_user(uid):
    run("DELETE FROM orders WHERE user_id=%s", (uid,))
    run("DELETE FROM users WHERE id=%s", (uid,))
    log_action("Admin Delete User", f"uid={uid}")
    return jsonify({"message": "Deleted"})

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
    o = q1("SELECT current_step FROM orders WHERE id=%s", (oid,))
    if not o: return jsonify({"error": "Not found"}), 404
    ns = min((o["current_step"] or 0) + 1, 4)
    run("UPDATE orders SET current_step=%s,status=%s WHERE id=%s", (ns, SM[ns], oid))
    return jsonify({"message": SM[ns]})

@app.route("/api/admin/menu")
@admin_required
def admin_menu():
    items = qa("SELECT * FROM menu_items ORDER BY id DESC")
    return jsonify({"items": items, "count": len(items)})

@app.route("/api/admin/menu", methods=["POST"])
@admin_required
def admin_add_menu():
    d = request.get_json() or {}
    new_id = run("""INSERT INTO menu_items(name,description,price,category,type,restaurant,rating,image,emoji,is_spicy,is_new,is_best,time)
                    VALUES(%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s) RETURNING id""",
                (d.get("name",""), d.get("description",""), float(d.get("price",0)), d.get("category",""),
                 d.get("type","veg"), d.get("restaurant",""), float(d.get("rating",4.0)),
                 d.get("image",""), d.get("emoji","🍛"), bool(d.get("is_spicy")),
                 bool(d.get("is_new")), bool(d.get("is_best")), d.get("time","30 mins")))
    log_action("Admin Add Menu", d.get("name",""))
    return jsonify({"message": "Added ✅", "id": new_id}), 201

@app.route("/api/admin/menu/<int:mid>", methods=["PUT"])
@admin_required
def admin_upd_menu(mid):
    d = request.get_json() or {}
    cur = q1("SELECT * FROM menu_items WHERE id=%s", (mid,))
    if not cur: return jsonify({"error": "Not found"}), 404
    run("""UPDATE menu_items SET name=%s,description=%s,price=%s,category=%s,type=%s,
           restaurant=%s,rating=%s,image=%s,emoji=%s,is_spicy=%s,is_new=%s,is_best=%s,time=%s
           WHERE id=%s""",
        (d.get("name", cur["name"]), d.get("description", cur["description"]),
         float(d.get("price", cur["price"])), d.get("category", cur["category"]),
         d.get("type", cur["type"]), d.get("restaurant", cur["restaurant"]),
         float(d.get("rating", cur["rating"])), d.get("image", cur["image"]),
         d.get("emoji", cur["emoji"]), bool(d.get("is_spicy", cur["is_spicy"])),
         bool(d.get("is_new", cur["is_new"])), bool(d.get("is_best", cur["is_best"])),
         d.get("time", cur["time"]), mid))
    log_action("Admin Edit Menu", f"mid={mid}")
    return jsonify({"message": "Updated ✅"})

@app.route("/api/admin/menu/<int:mid>", methods=["DELETE"])
@admin_required
def admin_del_menu(mid):
    run("DELETE FROM menu_items WHERE id=%s", (mid,))
    log_action("Admin Delete Menu", f"mid={mid}")
    return jsonify({"message": "Deleted"})

@app.route("/api/admin/menu/<int:mid>")
@admin_required
def admin_menu_item(mid):
    item = q1("SELECT * FROM menu_items WHERE id=%s", (mid,))
    if not item: return jsonify({"error": "Not found"}), 404
    return jsonify({"item": item})

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
#  AUTH ROUTES
# ═══════════════════════════════════════════════════════════════
@app.route("/api/auth/signup", methods=["POST"])
def signup():
    d = request.get_json() or {}
    name  = (d.get("name")  or "").strip()
    email = (d.get("email") or "").strip().lower()
    pw    = (d.get("password") or "")
    if not name:    return jsonify({"error": "Name required"}), 400
    if "@" not in email: return jsonify({"error": "Valid email required"}), 400
    if len(pw) < 6: return jsonify({"error": "Password 6+ chars"}), 400
    if q1("SELECT id FROM users WHERE email=%s", (email,)):
        return jsonify({"error": "Email already registered"}), 400
    uid = run("INSERT INTO users(name,email,password) VALUES(%s,%s,%s) RETURNING id",
              (name, email, hash_pw(pw)))
    log_action("User Signup", email)
    return jsonify({"message": f"Welcome, {name.split()[0]}! 🎉",
                    "token": make_token(uid, email),
                    "user": {"id": uid, "name": name, "email": email,
                             "picture": "", "profile_color": "#1A6FB3", "phone": "", "address": ""}}), 201

@app.route("/api/auth/login", methods=["POST"])
def user_login():
    d = request.get_json() or {}
    email = (d.get("email") or "").strip().lower()
    pw    = (d.get("password") or "")
    if not email or not pw: return jsonify({"error": "Email and password required"}), 400
    user = q1("SELECT * FROM users WHERE email=%s", (email,))
    if not user or not check_pw(pw, user["password"]):
        return jsonify({"error": "Invalid email or password"}), 401
    if user.get("is_blocked"):
        return jsonify({"error": "Account blocked. Contact support."}), 403
    log_action("User Login", email)
    return jsonify({"message": f"Welcome back, {user['name'].split()[0]}! 🎉",
                    "token": make_token(user["id"], user["email"]),
                    "user": {"id": user["id"], "name": user["name"], "email": user["email"],
                             "picture": user["picture"] or "", "profile_color": user["profile_color"] or "#1A6FB3",
                             "phone": user["phone"] or "", "address": user["address"] or ""}})

@app.route("/api/auth/me")
@jwt_required
def me(cu):
    user = q1("SELECT id,name,email,phone,address,picture,profile_color FROM users WHERE id=%s AND is_blocked=FALSE",
              (cu["user_id"],))
    if not user: return jsonify({"error": "Not found or blocked"}), 404
    cnt = q1("SELECT COUNT(*) AS c FROM orders WHERE user_id=%s", (cu["user_id"],))
    user["total_orders"] = cnt["c"] if cnt else 0
    return jsonify({"user": user})

@app.route("/api/auth/logout", methods=["POST"])
def user_logout(): return jsonify({"message": "Logged out"})

# ═══════════════════════════════════════════════════════════════
#  MENU ROUTES
# ═══════════════════════════════════════════════════════════════
@app.route("/api/menu/items")
def menu_items():
    cat   = request.args.get("category", "")
    dt    = request.args.get("type", "")
    srch  = request.args.get("search", "").lower()
    sort  = request.args.get("sort", "popular")
    mp    = request.args.get("max_price", type=int)
    page  = max(1, request.args.get("page", 1, type=int))
    limit = min(100, max(10, request.args.get("limit", 50, type=int)))

    conditions = ["available=TRUE"]
    params = []
    if cat and cat.lower() not in ("all", ""):
        conditions.append("category=%s"); params.append(cat)
    if dt in ("veg", "nonveg"):
        conditions.append("type=%s"); params.append(dt)
    if srch:
        conditions.append("(LOWER(name) LIKE %s OR LOWER(description) LIKE %s)")
        params += [f"%{srch}%", f"%{srch}%"]
    if mp:
        conditions.append("price<=%s"); params.append(mp)

    where = " AND ".join(conditions)
    sql   = f"SELECT * FROM menu_items WHERE {where}"
    sql  += {"popular": " ORDER BY is_best DESC,rating DESC",
             "price-asc": " ORDER BY price ASC",
             "price-desc": " ORDER BY price DESC",
             "rating": " ORDER BY rating DESC",
             "newest": " ORDER BY id DESC"}.get(sort, " ORDER BY is_best DESC,rating DESC")

    total = q1(f"SELECT COUNT(*) AS c FROM menu_items WHERE {where}", params)["c"]
    sql  += f" LIMIT {limit} OFFSET {(page-1)*limit}"
    items = qa(sql, params)

    return jsonify({"items": items, "count": len(items), "total": total,
                    "page": page, "limit": limit,
                    "total_pages": (total + limit - 1) // limit,
                    "has_next": page * limit < total, "has_prev": page > 1})

@app.route("/api/menu/seed", methods=["POST"])
def seed_menu():
    force = request.args.get("force", "") == "1"
    ex    = q1("SELECT COUNT(*) AS c FROM menu_items")
    if ex and ex["c"] > 0 and not force:
        return jsonify({"message": f"Already seeded with {ex['c']} dishes. Use ?force=1 to re-seed."})
    if force:
        run("DELETE FROM menu_items")
    for d in SAMPLE_DISHES:
        run("""INSERT INTO menu_items(name,description,price,category,type,restaurant,rating,image,emoji,is_spicy,is_new,is_best,time)
               VALUES(%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s) ON CONFLICT DO NOTHING""", d)
    c = q1("SELECT COUNT(*) AS c FROM menu_items")["c"]
    return jsonify({"message": f"✅ Menu seeded with {c} dishes!"}), 201

# ═══════════════════════════════════════════════════════════════
#  ORDER ROUTES
# ═══════════════════════════════════════════════════════════════
SM = {0:"placed",1:"preparing",2:"on_the_way",3:"nearby",4:"delivered"}

@app.route("/api/orders/place", methods=["POST"])
@jwt_required
def place_order(cu):
    d    = request.get_json() or {}
    items = d.get("items", [])
    addr  = (d.get("address") or "").strip()
    if not items: return jsonify({"error": "Cart empty"}), 400
    if not addr:  return jsonify({"error": "Address required"}), 400
    sub = sum(i.get("price", 0) * i.get("qty", 1) for i in items)
    dl  = 0 if sub >= 500 else 49
    tax = round(sub * .05)
    tot = sub + dl + tax
    oid = f"RE-{datetime.now().year}-{''.join(random.choices(string.ascii_uppercase+string.digits,k=8))}"
    rest = items[0].get("restaurant", "") if items else ""
    run("INSERT INTO orders(id,user_id,items,total,restaurant,address,status,current_step) VALUES(%s,%s,%s,%s,%s,%s,'placed',0)",
        (oid, cu["user_id"], json.dumps(items), tot, rest, addr))
    now = datetime.now()
    log_action("Order Placed", f"oid={oid} user={cu['user_id']}")
    return jsonify({"message": f"Order {oid} placed! 🎉",
                    "order": {"id": oid, "status": "placed", "current_step": 0, "eta": "30 mins",
                              "items": [i.get("name","") for i in items], "restaurant": rest,
                              "time": now.strftime("%I:%M %p"), "total": tot, "subtotal": sub,
                              "delivery": dl, "taxes": tax, "address": addr,
                              "placed_at": now.isoformat()}}), 201

@app.route("/api/orders/my-orders")
@jwt_required
def my_orders(cu):
    rows = qa("SELECT * FROM orders WHERE user_id=%s ORDER BY placed_at DESC", (cu["user_id"],))
    for r in rows:
        try: r["items"] = json.loads(r["items"])
        except: r["items"] = []
    return jsonify({"orders": rows, "count": len(rows)})

@app.route("/api/orders/<oid>")
@jwt_required
def get_order(oid, cu):
    o = q1("SELECT * FROM orders WHERE id=%s AND user_id=%s", (oid, cu["user_id"]))
    if not o: return jsonify({"error": "Not found"}), 404
    try: o["items"] = json.loads(o["items"])
    except: o["items"] = []
    return jsonify({"order": o})

@app.route("/api/orders/<oid>/step", methods=["PUT"])
@jwt_required
def step(oid, cu):
    o = q1("SELECT * FROM orders WHERE id=%s AND user_id=%s", (oid, cu["user_id"]))
    if not o: return jsonify({"error": "Not found"}), 404
    s  = (o["current_step"] or 0)
    ns = min(s + 1, 4)
    run("UPDATE orders SET current_step=%s,status=%s WHERE id=%s", (ns, SM[ns], oid))
    return jsonify({"message": SM[ns].replace("_"," ").title(), "current_step": ns, "status": SM[ns]})

# ═══════════════════════════════════════════════════════════════
#  PROFILE ROUTES
# ═══════════════════════════════════════════════════════════════
@app.route("/api/profile")
@jwt_required
def get_profile(cu):
    u = q1("SELECT id,name,email,phone,address,picture,profile_color FROM users WHERE id=%s", (cu["user_id"],))
    if not u: return jsonify({"error": "Not found"}), 404
    s = q1("SELECT COUNT(*) AS t, COALESCE(SUM(total),0) AS sp FROM orders WHERE user_id=%s", (cu["user_id"],))
    u["total_orders"] = s["t"] if s else 0
    u["total_spent"]  = s["sp"] if s else 0
    return jsonify({"user": u})

@app.route("/api/profile", methods=["PUT"])
@jwt_required
def upd_profile(cu):
    d   = request.get_json() or {}
    cur = q1("SELECT * FROM users WHERE id=%s", (cu["user_id"],))
    if not cur: return jsonify({"error": "Not found"}), 404
    name  = (d.get("name")          or cur["name"]).strip()
    phone = (d.get("phone")         or cur.get("phone") or "").strip()
    addr  = (d.get("address")       or cur.get("address") or "").strip()
    pic   = (d.get("picture")       or cur.get("picture") or "")
    color = (d.get("profile_color") or cur.get("profile_color") or "#1A6FB3")
    run("UPDATE users SET name=%s,phone=%s,address=%s,picture=%s,profile_color=%s WHERE id=%s",
        (name, phone, addr, pic, color, cu["user_id"]))
    u = q1("SELECT id,name,email,phone,address,picture,profile_color FROM users WHERE id=%s", (cu["user_id"],))
    return jsonify({"message": "Updated ✅", "user": u})

@app.route("/api/profile/password", methods=["PUT"])
@jwt_required
def chg_pw(cu):
    d  = request.get_json() or {}
    op = d.get("current_password", "")
    np = d.get("new_password", "")
    if not op or not np: return jsonify({"error": "Both required"}), 400
    if len(np) < 6:      return jsonify({"error": "New password 6+ chars"}), 400
    u = q1("SELECT password FROM users WHERE id=%s", (cu["user_id"],))
    if not u or not check_pw(op, u["password"]):
        return jsonify({"error": "Current password incorrect"}), 401
    run("UPDATE users SET password=%s WHERE id=%s", (hash_pw(np), cu["user_id"]))
    return jsonify({"message": "Password changed 🔒"})

# ═══════════════════════════════════════════════════════════════
#  ENTRYPOINT
# ═══════════════════════════════════════════════════════════════
if __name__ == "__main__":
    if not DATABASE_URL:
        print("⚠️  WARNING: DATABASE_URL not set. Please create a .env file.")
        print("   Copy .env.example to .env and fill in your Supabase credentials.")
    else:
        init_db()

    PORT = int(os.environ.get("PORT", 5000))
    print("\n" + "="*55)
    print("  🍛  RasoiExpress — Supabase Edition")
    print("="*55)
    print(f"  📡  API   : http://localhost:{PORT}")
    print(f"  🔐  ADMIN : http://localhost:{PORT}/admin")
    print(f"  👤  ID    : {ADMIN_ID}")
    print(f"  🗄️  DB    : Supabase PostgreSQL")
    print("="*55+"\n")
    app.run(debug=False, host="0.0.0.0", port=PORT)
