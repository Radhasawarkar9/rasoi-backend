"""
routes/menu.py — Menu / Dishes Routes
=======================================
Endpoints:
  GET  /api/menu/items              → List all dishes (with optional filters)
  GET  /api/menu/items/<id>         → Get a single dish by ID
  GET  /api/menu/categories         → List all category names
  POST /api/menu/seed               → (Dev only) Seed sample dishes into the DB

Query params for GET /api/menu/items:
  category  — filter by category name
  type      — "veg" or "nonveg"
  search    — keyword search across name + description
  sort      — "popular" | "price-asc" | "price-desc" | "rating" | "newest"
  max_price — integer upper price limit
"""

import json
from flask import Blueprint, request, jsonify
from database import fetch_all, fetch_one, execute

menu_bp = Blueprint("menu", __name__)


# ─────────────────────────────────────────────────────────────────
#  GET /api/menu/items
# ─────────────────────────────────────────────────────────────────
@menu_bp.route("/items", methods=["GET"])
def list_items():
    """Return all available menu items, with optional filtering."""

    # ── Read query parameters ────────────────────────────────────
    category  = request.args.get("category",  "")
    diet_type = request.args.get("type",       "")       # veg / nonveg
    search    = request.args.get("search",     "").lower()
    sort      = request.args.get("sort",       "popular")
    max_price = request.args.get("max_price",  type=int)

    # ── Build dynamic SQL ─────────────────────────────────────────
    sql    = "SELECT * FROM menu_items WHERE available = 1"
    params = []

    if category and category.lower() != "all":
        sql += " AND category = ?"
        params.append(category)

    if diet_type in ("veg", "nonveg"):
        sql += " AND type = ?"
        params.append(diet_type)

    if search:
        sql += " AND (LOWER(name) LIKE ? OR LOWER(description) LIKE ?)"
        params += [f"%{search}%", f"%{search}%"]

    if max_price:
        sql += " AND price <= ?"
        params.append(max_price)

    # ── Sorting ───────────────────────────────────────────────────
    sort_map = {
        "popular":    "is_best DESC, rating DESC",
        "price-asc":  "price ASC",
        "price-desc": "price DESC",
        "rating":     "rating DESC",
        "newest":     "id DESC",
    }
    sql += f" ORDER BY {sort_map.get(sort, 'is_best DESC, rating DESC')}"

    items = fetch_all(sql, params)

    # ── Convert integer flags to Python booleans for the frontend ─
    for item in items:
        item["is_spicy"] = bool(item["is_spicy"])
        item["is_new"]   = bool(item["is_new"])
        item["is_best"]  = bool(item["is_best"])

    return jsonify({"items": items, "count": len(items)}), 200


# ─────────────────────────────────────────────────────────────────
#  GET /api/menu/items/<id>
# ─────────────────────────────────────────────────────────────────
@menu_bp.route("/items/<int:item_id>", methods=["GET"])
def get_item(item_id):
    """Return one dish by its primary key."""
    item = fetch_one("SELECT * FROM menu_items WHERE id = ?", (item_id,))
    if not item:
        return jsonify({"error": "Dish not found"}), 404
    item["is_spicy"] = bool(item["is_spicy"])
    item["is_new"]   = bool(item["is_new"])
    item["is_best"]  = bool(item["is_best"])
    return jsonify({"item": item}), 200


# ─────────────────────────────────────────────────────────────────
#  GET /api/menu/categories
# ─────────────────────────────────────────────────────────────────
@menu_bp.route("/categories", methods=["GET"])
def list_categories():
    """Return distinct category names and their item counts."""
    rows = fetch_all(
        "SELECT category, COUNT(*) as count FROM menu_items "
        "WHERE available = 1 GROUP BY category ORDER BY category"
    )
    return jsonify({"categories": rows}), 200


# ─────────────────────────────────────────────────────────────────
#  POST /api/menu/seed   (DEV ONLY — seeds sample dishes)
# ─────────────────────────────────────────────────────────────────
@menu_bp.route("/seed", methods=["POST"])
def seed_menu():
    """
    Inserts sample dishes into the DB.
    Call this ONCE after creating the database.
    Safe to call again — uses INSERT OR IGNORE so no duplicates.
    """
    # Check if already seeded
    existing = fetch_one("SELECT COUNT(*) as cnt FROM menu_items")
    if existing and existing["cnt"] > 0:
        return jsonify({"message": f"Already seeded with {existing['cnt']} dishes. Skipping."}), 200

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


    for dish in sample_dishes:
        execute(
            """INSERT INTO menu_items
               (name, description, price, category, type, restaurant, rating,
                image, emoji, is_spicy, is_new, is_best, time)
               VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)
               ON CONFLICT DO NOTHING""",
            dish,
        )

    count = fetch_one("SELECT COUNT(*) as cnt FROM menu_items")
    return jsonify({
        "message": f"✅ Menu seeded successfully with {count['cnt']} dishes!",
    }), 201
