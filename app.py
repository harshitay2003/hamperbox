from flask import Flask, render_template, request, redirect, url_for, session, flash, jsonify
import os
from dotenv import load_dotenv

# Load env variables
load_dotenv()

import db_manager
from functools import wraps
from werkzeug.utils import secure_filename

app = Flask(__name__)
app.secret_key = os.environ.get("SECRET_KEY", "plush_petals_secret_admin_key")

# Configure Image Uploads
UPLOAD_FOLDER = os.path.join(app.root_path, 'static', 'images')
app.config['UPLOAD_FOLDER'] = UPLOAD_FOLDER
ALLOWED_EXTENSIONS = {'png', 'jpg', 'jpeg', 'gif', 'webp', 'svg'}

def allowed_file(filename):
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in ALLOWED_EXTENSIONS

# Initialize Database on Startup
with app.app_context():
    db_manager.db_init()

# Decorator to secure admin routes
def admin_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if not session.get("admin_logged_in"):
            return redirect(url_for("admin_login"))
        return f(*args, **kwargs)
    return decorated_function

# ================= PUBLIC ROUTES =================

@app.route("/")
def home():
    return render_template("index.html")

@app.route("/products")
def products():
    return render_template("products.html")

# ================= REST APIs =================

@app.route("/api/products", methods=["GET"])
def api_products():
    return jsonify(db_manager.get_products())

@app.route("/api/categories", methods=["GET"])
def api_categories():
    return jsonify(db_manager.get_categories())

@app.route("/api/inquire", methods=["POST"])
def api_inquire():
    data = request.get_json() or request.form
    name = data.get("name")
    email = data.get("email", "")
    phone = data.get("phone", "")
    message = data.get("message")
    product_name = data.get("product_name")

    if not name or not message:
        return jsonify({"success": False, "error": "Name and message are required"}), 400

    db_manager.add_inquiry(name, email, phone, message, product_name)
    return jsonify({"success": True})

# ================= ADMIN ROUTES =================

@app.route("/admin/login", methods=["GET", "POST"])
def admin_login():
    if session.get("admin_logged_in"):
        return redirect(url_for("admin_dashboard"))
        
    if request.method == "POST":
        username = request.form.get("username")
        password = request.form.get("password")
        
        if db_manager.authenticate_admin(username, password):
            session["admin_logged_in"] = True
            session["admin_username"] = username
            flash("Welcome back! Successfully logged into Plush Petals.", "success")
            return redirect(url_for("admin_dashboard"))
        else:
            return render_template("admin_login.html", error="Invalid admin credentials.")
            
    return render_template("admin_login.html")

@app.route("/admin/logout")
def admin_logout():
    session.clear()
    flash("You have been securely logged out.", "success")
    return redirect(url_for("admin_login"))

@app.route("/admin")
@admin_required
def admin_dashboard():
    products_list = db_manager.get_products()
    categories_list = db_manager.get_categories()
    inquiries_list = db_manager.get_inquiries()
    
    pending_count = sum(1 for i in inquiries_list if i["status"] == "Pending")
    resolved_count = sum(1 for i in inquiries_list if i["status"] == "Resolved")
    
    return render_template(
        "admin_dashboard.html",
        active_page="dashboard",
        total_products=len(products_list),
        total_categories=len(categories_list),
        pending_inquiries=pending_count,
        resolved_inquiries=resolved_count,
        inquiries=inquiries_list
    )

# Manage Products
@app.route("/admin/products")
@admin_required
def admin_products():
    return render_template(
        "admin_products.html",
        active_page="products",
        products=db_manager.get_products(),
        categories=db_manager.get_categories()
    )

@app.route("/admin/products/add", methods=["POST"])
@admin_required
def admin_products_add():
    name = request.form.get("name")
    category_slug = request.form.get("category_slug")
    price = int(request.form.get("price", 0))
    rating = request.form.get("rating", "★★★★★")
    tag = request.form.get("tag", "")
    description = request.form.get("description", "")
    
    # Image resolution priority: 1. File Upload, 2. Text Input, 3. Default placeholder
    image_filename = "cat-hampers.jpg"
    image_file = request.files.get("image_file")
    
    if image_file and allowed_file(image_file.filename):
        filename = secure_filename(image_file.filename)
        # Ensure directories exist
        os.makedirs(app.config['UPLOAD_FOLDER'], exist_ok=True)
        image_file.save(os.path.join(app.config['UPLOAD_FOLDER'], filename))
        image_filename = filename
    elif request.form.get("image_name"):
        image_filename = request.form.get("image_name")
        
    db_manager.add_product(name, category_slug, price, rating, tag, image_filename, description)
    flash(f"Successfully added '{name}' to the catalog.", "success")
    return redirect(url_for("admin_products"))

@app.route("/admin/products/edit", methods=["POST"])
@admin_required
def admin_products_edit():
    prod_id = int(request.form.get("id"))
    name = request.form.get("name")
    category_slug = request.form.get("category_slug")
    price = int(request.form.get("price", 0))
    rating = request.form.get("rating", "★★★★★")
    tag = request.form.get("tag", "")
    description = request.form.get("description", "")
    
    # Keep current image if no file or name was changed
    current_product = db_manager.get_product(prod_id)
    image_filename = current_product["image"] if current_product else "cat-hampers.jpg"
    
    image_file = request.files.get("image_file")
    if image_file and allowed_file(image_file.filename):
        filename = secure_filename(image_file.filename)
        os.makedirs(app.config['UPLOAD_FOLDER'], exist_ok=True)
        image_file.save(os.path.join(app.config['UPLOAD_FOLDER'], filename))
        image_filename = filename
    elif request.form.get("image_name"):
        image_filename = request.form.get("image_name")
        
    db_manager.update_product(prod_id, name, category_slug, price, rating, tag, image_filename, description)
    flash(f"Successfully updated product '{name}'.", "success")
    return redirect(url_for("admin_products"))

@app.route("/admin/products/delete/<int:prod_id>")
@admin_required
def admin_products_delete(prod_id):
    db_manager.delete_product(prod_id)
    flash("Product successfully removed from catalog.", "success")
    return redirect(url_for("admin_products"))

# Manage Categories (Collections)
@app.route("/admin/categories")
@admin_required
def admin_categories():
    return render_template(
        "admin_categories.html",
        active_page="categories",
        categories=db_manager.get_categories()
    )

@app.route("/admin/categories/add", methods=["POST"])
@admin_required
def admin_categories_add():
    name = request.form.get("name")
    slug = request.form.get("slug")
    
    if db_manager.add_category(slug, name):
        flash(f"Collection '{name}' successfully created.", "success")
    else:
        flash(f"Error: Category slug '{slug}' already exists.", "error")
        
    return redirect(url_for("admin_categories"))

@app.route("/admin/categories/delete/<string:slug>")
@admin_required
def admin_categories_delete(slug):
    db_manager.delete_category(slug)
    flash(f"Collection '{slug}' and all its products were successfully deleted.", "success")
    return redirect(url_for("admin_categories"))

# Manage Inquiries
@app.route("/admin/inquiries")
@admin_required
def admin_inquiries():
    return render_template(
        "admin_inquiries.html",
        active_page="inquiries",
        inquiries=db_manager.get_inquiries()
    )

@app.route("/admin/inquiries/toggle/<int:inq_id>")
@admin_required
def admin_inquiries_toggle(inq_id):
    inquiries = db_manager.get_inquiries()
    inq = next((i for i in inquiries if i["id"] == inq_id), None)
    if inq:
        new_status = "Resolved" if inq["status"] == "Pending" else "Pending"
        db_manager.update_inquiry_status(inq_id, new_status)
        flash(f"Inquiry for {inq['name']} marked as {new_status}.", "success")
    return redirect(url_for("admin_inquiries"))

# Run the Flask App
if __name__ == "__main__":
    app.run(
        host="0.0.0.0",
        port=int(os.environ.get("PORT", 5000)),
        debug=True
    )