import sqlite3
import os
from werkzeug.security import generate_password_hash, check_password_hash
from dotenv import load_dotenv

# Load env variables
load_dotenv()

DATABASE_PATH = os.path.join(os.path.dirname(__file__), "database.db")
DATABASE_URL = os.environ.get("DATABASE_URL")
IS_POSTGRES = False

if DATABASE_URL and (DATABASE_URL.startswith("postgres://") or DATABASE_URL.startswith("postgresql://")):
    IS_POSTGRES = True

# Exception setup
try:
    import pg8000.dbapi
    PG_INTEGRITY_ERROR = pg8000.dbapi.IntegrityError
except ImportError:
    PG_INTEGRITY_ERROR = None

class PGRow:
    def __init__(self, cols, values):
        self._cols = cols
        self._values = values
        self._dict = dict(zip(cols, values))

    def __getitem__(self, key):
        if isinstance(key, int):
            return self._values[key]
        return self._dict[key]

    def keys(self):
        return self._cols

    def get(self, key, default=None):
        return self._dict.get(key, default)

    def __len__(self):
        return len(self._values)

    def __repr__(self):
        return repr(self._dict)

class DBCursorWrapper:
    def __init__(self, cursor, is_postgres=False):
        self.cursor = cursor
        self.is_postgres = is_postgres
        self.description = None

    def execute(self, sql, params=None):
        if self.is_postgres:
            # PostgreSQL compatibility translation
            if "INTEGER PRIMARY KEY AUTOINCREMENT" in sql:
                sql = sql.replace("INTEGER PRIMARY KEY AUTOINCREMENT", "SERIAL PRIMARY KEY")
            translated_sql = sql.replace("?", "%s")
            
            if params is None:
                self.cursor.execute(translated_sql)
            else:
                self.cursor.execute(translated_sql, params)
            self.description = self.cursor.description
        else:
            if params is None:
                self.cursor.execute(sql)
            else:
                self.cursor.execute(sql, params)
            self.description = self.cursor.description
        return self

    def executemany(self, sql, seq_of_params):
        if self.is_postgres:
            translated_sql = sql.replace("?", "%s")
            self.cursor.executemany(translated_sql, seq_of_params)
            self.description = self.cursor.description
        else:
            self.cursor.executemany(sql, seq_of_params)
            self.description = self.cursor.description
        return self

    def fetchall(self):
        rows = self.cursor.fetchall()
        if self.is_postgres and self.description:
            cols = [col[0] for col in self.description]
            return [PGRow(cols, row) for row in rows]
        return rows

    def fetchone(self):
        row = self.cursor.fetchone()
        if not row:
            return None
        if self.is_postgres and self.description:
            cols = [col[0] for col in self.description]
            return PGRow(cols, row)
        return row

class DBConnectionWrapper:
    def __init__(self, conn, is_postgres=False):
        self.conn = conn
        self.is_postgres = is_postgres

    def cursor(self):
        return DBCursorWrapper(self.conn.cursor(), self.is_postgres)

    def execute(self, sql, params=None):
        cur = self.cursor()
        cur.execute(sql, params)
        return cur

    def commit(self):
        self.conn.commit()

    def close(self):
        self.conn.close()

def get_db_connection():
    if IS_POSTGRES:
        from urllib.parse import urlparse
        import pg8000.dbapi
        url = urlparse(DATABASE_URL)
        conn = pg8000.dbapi.connect(
            user=url.username,
            password=url.password,
            host=url.hostname,
            port=url.port or 5432,
            database=url.path[1:]
        )
        return DBConnectionWrapper(conn, is_postgres=True)
    else:
        conn = sqlite3.connect(DATABASE_PATH)
        conn.row_factory = sqlite3.Row
        return conn

def db_init():
    conn = get_db_connection()
    cursor = conn.cursor()
    
    # 1. Create tables
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS users (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        username TEXT UNIQUE NOT NULL,
        password_hash TEXT NOT NULL
    )
    """)
    
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS categories (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        slug TEXT UNIQUE NOT NULL,
        name TEXT NOT NULL
    )
    """)
    
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS products (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        name TEXT NOT NULL,
        category_slug TEXT NOT NULL,
        price INTEGER NOT NULL,
        rating TEXT NOT NULL,
        tag TEXT NOT NULL,
        image TEXT NOT NULL,
        description TEXT NOT NULL,
        FOREIGN KEY (category_slug) REFERENCES categories (slug)
    )
    """)
    
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS inquiries (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        name TEXT NOT NULL,
        email TEXT NOT NULL,
        phone TEXT NOT NULL,
        message TEXT NOT NULL,
        product_name TEXT,
        status TEXT NOT NULL DEFAULT 'Pending',
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
    )
    """)
    
    # 2. Seed default admin if not exists
    cursor.execute("SELECT COUNT(*) FROM users")
    if cursor.fetchone()[0] == 0:
        default_pwd = generate_password_hash("admin123")
        cursor.execute("INSERT INTO users (username, password_hash) VALUES (?, ?)", ("admin", default_pwd))
        
    # 3. Seed default categories if not exists
    cursor.execute("SELECT COUNT(*) FROM categories")
    if cursor.fetchone()[0] == 0:
        default_cats = [
            ("hampers", "Gift Hampers"),
            ("platters", "Ring Platters"),
            ("haldi", "Haldi Jewellery"),
            ("packing", "Wedding Packing"),
            ("bridal", "Bridal Trunks"),
            ("custom", "Custom Gifts"),
            ("festive", "Festive Trays"),
            ("baby", "Baby Shower")
        ]
        cursor.executemany("INSERT INTO categories (slug, name) VALUES (?, ?)", default_cats)
        
    # 4. Seed default products if not exists
    cursor.execute("SELECT COUNT(*) FROM products")
    if cursor.fetchone()[0] == 0:
        default_prods = [
            # 1. Gift Hampers (hampers)
            ("The Royal Ivory Hamper", "hampers", 8500, "★★★★★", "Best Seller", "cat-hampers.jpg", "An ultra-premium hamper featuring exotic dry fruits, premium copper containers, customized ceramic mugs, and organic forest honey."),
            ("Golden Aura Saffron & Tea Trunk", "hampers", 11000, "★★★★★", "Limited Edition", "gal-2.jpg", "An elegant leatherette storage case hosting fine Kashmiri saffron, premium organic tea leaves, brass tea strainer, and brass mugs."),
            ("Majestic Rosewood Hamper", "hampers", 9800, "★★★★★", "Signature", "cat-hampers.jpg", "Fine solid rosewood hamper box filled with imported chocolate truffles, organic honey, custom incense burner, and dry fruit jars."),
            ("Gourmet Artisan Treat Box", "hampers", 4500, "★★★★☆", "Deluxe", "cat-hampers.jpg", "Artisanal keepsake chest filled with hand-rolled cookies, premium seed mix, organic floral teas, and luxury soy wax candle."),
            
            # 2. Ring Platters (platters)
            ("Classic Satin Ring Platter", "platters", 2400, "★★★★☆", "Popular", "cat-ring-platter.jpg", "Exquisite hand-wrapped satin ring holder platter adorned with pearls, golden embroidery, and fresh-looking faux white roses."),
            ("Blossom Glass Dome Platter", "platters", 3100, "★★★★★", "New", "gal-3.jpg", "Minimalist modern glass-dome platter showcasing delicate shola floral arrangements and a velvet slots ring-box."),
            ("Royal Velvet Double Ring Tray", "platters", 3800, "★★★★★", "Luxury", "cat-ring-platter.jpg", "Exquisite double ring holder nestled in a deep maroon velvet base with brass handle borders and pearl tassels."),
            ("Vintage Pearl & Rose Platter", "platters", 2900, "★★★★☆", "Handcrafted", "cat-ring-platter.jpg", "Ornate gold-finished ring tray surrounded by layered pearls, baby's breath blossoms, and matching velvet ring boxes."),
            
            # 3. Haldi Jewellery (haldi)
            ("Floral Kundan Choker Set", "haldi", 1800, "★★★★☆", "Traditions", "cat-haldi.jpg", "Charming floral neckpiece with matching earrings and wristlet handcrafted for the bride's Haldi or Mehendi ceremony."),
            ("Pearl Gota Patti Jewellery Set", "haldi", 1200, "★★★★☆", "Crafted", "gal-4.jpg", "Vibrant yellow and pink gota-patti jewelry ensemble complete with necklaces, heavy matha-patti, and matching rings."),
            ("Marigold Floral Kaleeras & Bangles", "haldi", 1500, "★★★★☆", "Traditions", "cat-haldi.jpg", "Adorable lightweight artificial marigold floral kaleeras with attached pearl-beaded bangles for pre-wedding fun."),
            ("Rosebud Jasmine Haathphool Set", "haldi", 1650, "★★★★★", "Best Seller", "cat-haldi.jpg", "Elegant jasmine and rosebud-styled haathphools with delicate pearl strings, perfect for an organic, fresh haldi bridal look."),
            
            # 4. Wedding Packing (packing)
            ("Bespoke Trousseau Packing Box", "packing", 3200, "★★★★★", "Signature", "cat-packing.jpg", "Hardbound luxury keepsake box covered in rich wine velvet, highlighted with golden foil detailing and customized initials."),
            ("Zari Velvet Shagun Envelopes", "packing", 950, "★★★★☆", "Essentials", "gal-5.jpg", "Set of 10 ultra-luxury heavy velvet cash envelopes hand-embroidered with detailed zardozi work for wedding blessings."),
            ("Sari Organza Wrap Sleeves", "packing", 1100, "★★★★☆", "Set of 6", "cat-packing.jpg", "Elegant semi-sheer organza sleeves with gold border trims to wrap sarees neatly for wedding trousseau displays."),
            ("Brocade Wedding Gift Potlis", "packing", 1450, "★★★★☆", "Set of 10", "cat-packing.jpg", "Luxurious banarasi brocade gift pouches with braided gold drawstrings, perfect for dry fruits or wedding favors."),
            
            # 5. Bridal Trunks (bridal)
            ("The Empress Bridal Trunk", "bridal", 12500, "★★★★★", "Luxury", "cat-bridal.jpg", "A heritage leatherette bridal trunk complete with velvet sections, jewelry dividers, silk robe, and a custom gold-plated keepsake."),
            ("The Heirloom Trousseau Hamper", "bridal", 14500, "★★★★★", "Royal", "cat-bridal.jpg", "Premium large wedding trousseau chest containing rich silk packaging wrappers, satin pouches, and personalized letterheads."),
            ("Satin & Lace Bridal Trousseau Box", "bridal", 8900, "★★★★★", "Exquisite", "cat-bridal.jpg", "Classic satin covered packaging box with delicate lace borders, custom partition inserts, and soft interior padding."),
            ("Maharani Velvet Bridal Hamper", "bridal", 13800, "★★★★★", "Royal Collection", "cat-bridal.jpg", "Opulent velvet-clad wooden trousseau chest featuring gold corner guards, customized name plaques, and satin organizers."),
            
            # 6. Customized Gifts (custom)
            ("Monogrammed Acrylic Tray Set", "custom", 2100, "★★★★☆", "Custom", "cat-custom.jpg", "Sleek transparent acrylic trays featuring gold leaf borders and custom calligraphy monogramming for modern homes."),
            ("Custom Engraved Crystal Glasses Set", "custom", 6200, "★★★★☆", "Personalized", "cat-custom.jpg", "Pair of crystal whiskey glasses custom monogrammed with names, nested in an elegant satin-lined wooden box."),
            ("Personalized Leather Passport Sleeves", "custom", 2800, "★★★★☆", "Couple Set", "cat-custom.jpg", "Set of two genuine leather passport cases monogrammed with initials in gold leaf, perfect wedding couple gift."),
            ("Bespoke Calligraphy Journal Box", "custom", 3400, "★★★★★", "Signature", "cat-custom.jpg", "Handcrafted personalized wooden gift box enclosing a leather-bound journal and a classic metallic feather quill pen."),
            
            # 7. Festive Trays (festive)
            ("Gilded Shubh Labh Diwali Platter", "festive", 4800, "★★★★★", "Festive", "cat-festive.jpg", "Stunning hand-painted brass platter with custom-crafted terracota diyas, organic dry fruit jars, and handcrafted shola wood flowers."),
            ("Vedic Harvest Dry Fruit Platter", "festive", 2900, "★★★★☆", "Gourmet", "cat-festive.jpg", "Premium handcrafted wooden platter with gold inlay work, filled with top-grade almonds, cashews, raisins, and dry figs."),
            ("Brass Diya & Marigold Festive Tray", "festive", 3600, "★★★★★", "Heritage", "cat-festive.jpg", "A traditional copper-plated hammered tray styled with brass diyas, dry fruit jars, and vibrant marigold flower arrangements."),
            ("Shahi Kaju Katli Silver Gift Box", "festive", 2200, "★★★★☆", "Sweets", "cat-festive.jpg", "Decorative metal gift box featuring silver-coated cashew sweets, premium raisins, and a custom greeting card."),
            
            # 8. Baby Shower (baby)
            ("Sweet Dreams Baby Hamper", "baby", 3500, "★★★★☆", "Newborn", "gal-1.jpg", "Curated gift set featuring organic cotton babywear, hand-crocheted rattle toy, milestone cards, and a soft flannel blanket."),
            ("Welcome Little One Luxury Basket", "baby", 5400, "★★★★★", "Deluxe Baby", "gal-1.jpg", "Woven basket filled with organic baby bath products, bamboo towel, plush teddy bear, and customized baby milestone book."),
            ("Organic Cotton Baby Swaddle Set", "baby", 2700, "★★★★☆", "Organic", "gal-1.jpg", "Set of three GOTS certified organic muslin swaddle cloths in aesthetic pastel shades, gift-wrapped in custom flower box."),
            ("Newborn Knitted Toys & Booties Box", "baby", 3100, "★★★★☆", "Baby Gift", "gal-1.jpg", "A customized keepsake box with premium hand-knitted woolen booties, soft rabbit toy, and wooden teething rings.")
        ]
        cursor.executemany("""
        INSERT INTO products (name, category_slug, price, rating, tag, image, description)
        VALUES (?, ?, ?, ?, ?, ?, ?)
        """, default_prods)
        
    conn.commit()
    conn.close()

def get_products():
    conn = get_db_connection()
    products = conn.execute("SELECT * FROM products ORDER BY id ASC").fetchall()
    conn.close()
    return [dict(p) for p in products]

def get_product(prod_id):
    conn = get_db_connection()
    product = conn.execute("SELECT * FROM products WHERE id = ?", (prod_id,)).fetchone()
    conn.close()
    return dict(product) if product else None

def add_product(name, category_slug, price, rating, tag, image, description):
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("""
    INSERT INTO products (name, category_slug, price, rating, tag, image, description)
    VALUES (?, ?, ?, ?, ?, ?, ?)
    """, (name, category_slug, price, rating, tag, image, description))
    conn.commit()
    conn.close()

def update_product(prod_id, name, category_slug, price, rating, tag, image, description):
    conn = get_db_connection()
    conn.execute("""
    UPDATE products
    SET name = ?, category_slug = ?, price = ?, rating = ?, tag = ?, image = ?, description = ?
    WHERE id = ?
    """, (name, category_slug, price, rating, tag, image, description, prod_id))
    conn.commit()
    conn.close()

def delete_product(prod_id):
    conn = get_db_connection()
    conn.execute("DELETE FROM products WHERE id = ?", (prod_id,))
    conn.commit()
    conn.close()

def get_categories():
    conn = get_db_connection()
    categories = conn.execute("SELECT * FROM categories ORDER BY name ASC").fetchall()
    conn.close()
    return [dict(c) for c in categories]

def add_category(slug, name):
    conn = get_db_connection()
    errors = (sqlite3.IntegrityError, PG_INTEGRITY_ERROR) if PG_INTEGRITY_ERROR else (sqlite3.IntegrityError,)
    try:
        conn.execute("INSERT INTO categories (slug, name) VALUES (?, ?)", (slug, name))
        conn.commit()
        return True
    except errors:
        return False
    finally:
        conn.close()

def delete_category(slug):
    conn = get_db_connection()
    conn.execute("DELETE FROM categories WHERE slug = ?", (slug,))
    conn.execute("DELETE FROM products WHERE category_slug = ?", (slug,))
    conn.commit()
    conn.close()

def get_inquiries():
    conn = get_db_connection()
    inquiries = conn.execute("SELECT * FROM inquiries ORDER BY created_at DESC").fetchall()
    conn.close()
    return [dict(i) for i in inquiries]

def add_inquiry(name, email, phone, message, product_name=None):
    conn = get_db_connection()
    conn.execute("""
    INSERT INTO inquiries (name, email, phone, message, product_name)
    VALUES (?, ?, ?, ?, ?)
    """, (name, email, phone, message, product_name))
    conn.commit()
    conn.close()

def update_inquiry_status(inquiry_id, status):
    conn = get_db_connection()
    conn.execute("UPDATE inquiries SET status = ? WHERE id = ?", (status, inquiry_id))
    conn.commit()
    conn.close()

def authenticate_admin(username, password):
    conn = get_db_connection()
    user = conn.execute("SELECT * FROM users WHERE username = ?", (username,)).fetchone()
    conn.close()
    if user and check_password_hash(user["password_hash"], password):
        return True
    return False

def update_admin_password(username, new_password):
    conn = get_db_connection()
    pwd_hash = generate_password_hash(new_password)
    conn.execute("UPDATE users SET password_hash = ? WHERE username = ?", (pwd_hash, username))
    conn.commit()
    conn.close()
