from flask import Flask, make_response, render_template, redirect, flash, session, request, url_for
from flask_mail import Mail, Message
import sqlite3
import bcrypt
import random
import config
import os
from werkzeug.utils import secure_filename
import razorpay
from utils.pdf_generator import generate_pdf

razorpay_client = razorpay.Client(
    auth=(config.RAZORPAY_KEY_ID, config.RAZORPAY_KEY_SECRET)
)


app = Flask(__name__)
app.config['UPLOAD_FOLDER'] = config.UPLOAD_FOLDER
app.secret_key = config.SECRET_KEY
ADMIN_UPLOAD_FOLDER = 'static/uploads/admin_profiles'
app.config['ADMIN_UPLOAD_FOLDER'] = ADMIN_UPLOAD_FOLDER


app.config['MAIL_SERVER'] = config.MAIL_SERVER
app.config['MAIL_PORT'] = config.MAIL_PORT
app.config['MAIL_USE_TLS'] = config.MAIL_USE_TLS
app.config['MAIL_USERNAME'] = config.MAIL_USERNAME
app.config['MAIL_PASSWORD'] = config.MAIL_PASSWORD
app.config['MAIL_DEFAULT_SENDER'] = config.MAIL_USERNAME

mail = Mail(app)

def get_db_connection():
    conn = sqlite3.connect("smartcart.db")
    conn.row_factory = sqlite3.Row
    return conn

@app.route('/')
def home():
    return redirect('/admin-signup')

@app.route('/admin-about')
def admin_about():
    return render_template('admin/about.html')

@app.route('/admin-contact')
def admin_contact():
    return render_template('admin/contact.html')


@app.route('/admin-signup', methods=['GET', 'POST'])
def admin_signup():

    if request.method == "GET":
        return render_template("admin/admin_signup.html")

    name = request.form['name']
    email = request.form['email']
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT admin_id FROM admin WHERE email=?", (email,))
    existing_admin = cursor.fetchone()
    cursor.close()
    conn.close()

    if existing_admin:
        flash("This email is already registered. Please login instead.", "danger")
        return redirect('/admin-signup')
    session['signup_name'] = name
    session['signup_email'] = email
    otp = random.randint(100000, 999999)
    session['otp'] = otp

    message = Message(
        subject="SmartCart Admin OTP",
        sender=config.MAIL_USERNAME,
        recipients=[email]
    )
    message.body = f"Your OTP for SmartCart Admin Registration is: {otp}"
    mail.send(message)

    flash("OTP sent to your email!", "success")
    return redirect('/verify-otp')

@app.route('/verify-otp', methods=['GET'])
def verify_otp_get():
    return render_template("admin/verify_otp.html")

@app.route('/verify-otp', methods=['POST'])
def verify_otp_post():
    
    user_otp = request.form['otp']
    password = request.form['password']

    if str(session.get('otp')) != str(user_otp):
        flash("Invalid OTP. Try again!", "danger")
        return redirect('/verify-otp')
    hashed_password = bcrypt.hashpw(password.encode('utf-8'), bcrypt.gensalt())

    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute(
        "INSERT INTO admin (name, email, password) VALUES (?, ?, ?)",
        (session['signup_name'], session['signup_email'], hashed_password)
    )
    conn.commit()
    cursor.close()
    conn.close()

    session.pop('otp', None)
    session.pop('signup_name', None)
    session.pop('signup_email', None)

    flash("Admin Registered Successfully!", "success")
    return redirect('/admin-signup')

@app.route('/admin-login', methods=['GET', 'POST'])
def admin_login():

    if request.method == 'GET':
        return render_template("admin/admin_login.html")

    email = request.form['email']
    password = request.form['password']

    conn = get_db_connection()
    cursor = conn.cursor()

    cursor.execute("SELECT * FROM admin WHERE email=?", (email,))
    admin = cursor.fetchone()

    cursor.close()
    conn.close()

    if admin is None:
        flash("Email not found! Please register first.", "danger")
        return redirect('/admin-login')

    stored_hashed_password = admin['password']

    if not bcrypt.checkpw(password.encode('utf-8'), stored_hashed_password):
        flash("Incorrect password! Try again.", "danger")
        return redirect('/admin-login')

    session['admin_id'] = admin['admin_id']
    session['admin_name'] = admin['name']
    session['admin_email'] = admin['email']

    flash("Login Successful!", "success")
    return redirect('/admin-dashboard')

@app.route('/admin-forgot-password', methods=['GET', 'POST'])
def admin_forgot_password():

    if request.method == 'GET':
        return render_template('admin/admin_forgot_password.html')

    email = request.form['email']

    conn = get_db_connection()
    cursor = conn.cursor()

    cursor.execute(
        "SELECT * FROM admin WHERE email=?",
        (email,)
    )

    admin = cursor.fetchone()

    conn.close()

    if not admin:
        flash("Email not found!", "danger")
        return redirect('/admin-forgot-password')

    otp = random.randint(100000, 999999)

    session['admin_reset_email'] = email
    session['admin_reset_otp'] = otp

    message = Message(
        subject="SmartCart Admin Password Reset OTP",
        recipients=[email]
    )

    message.body = f"""
Hello Admin,

Your Password Reset OTP is:

{otp}

Do not share this OTP with anyone.
"""

    mail.send(message)

    flash("OTP sent successfully!", "success")

    return redirect('/admin-reset-password')

@app.route('/admin-reset-password', methods=['GET', 'POST'])
def admin_reset_password():

    if request.method == 'GET':
        return render_template('admin/admin_reset_password.html')

    otp = request.form['otp']
    password = request.form['password']
    confirm_password = request.form['confirm_password']

    if int(otp) != session.get('admin_reset_otp'):
        flash("Invalid OTP!", "danger")
        return redirect('/admin-reset-password')

    if password != confirm_password:
        flash("Passwords do not match!", "danger")
        return redirect('/admin-reset-password')

    hashed_password = bcrypt.hashpw(
        password.encode('utf-8'),
        bcrypt.gensalt()
    )

    conn = get_db_connection()
    cursor = conn.cursor()

    cursor.execute(
        "UPDATE admin SET password=? WHERE email=?",
        (
            hashed_password,
            session['admin_reset_email']
        )
    )

    conn.commit()
    conn.close()

    session.pop('admin_reset_otp', None)
    session.pop('admin_reset_email', None)

    flash("Password reset successful. Please login.", "success")

    return redirect('/admin-login')

@app.route('/admin-dashboard')
def admin_dashboard():

    if 'admin_id' not in session:
        flash("Please login to access dashboard!", "danger")
        return redirect('/admin-login')

    conn = get_db_connection()
    cursor = conn.cursor()

    # Total Products
    cursor.execute("SELECT COUNT(*) AS total_products FROM products")
    total_products = cursor.fetchone()['total_products']

    # Total Orders
    cursor.execute("SELECT COUNT(*) AS total_orders FROM orders")
    total_orders = cursor.fetchone()['total_orders']

    # Total Customers
    cursor.execute("SELECT COUNT(*) AS total_customers FROM users")
    total_customers = cursor.fetchone()['total_customers']

    # Total Revenue
    cursor.execute("""
        SELECT IFNULL(SUM(amount),0) AS total_revenue
        FROM orders
        WHERE payment_status='Success'
    """)
    total_revenue = cursor.fetchone()['total_revenue']

    # Recent Orders
    cursor.execute("""
        SELECT *
        FROM orders
        ORDER BY order_id DESC
        LIMIT 5
    """)
    recent_orders = cursor.fetchall()

    cursor.close()
    conn.close()

    return render_template(
        "admin/dashboard.html",
        admin_name=session['admin_name'],
        total_products=total_products,
        total_orders=total_orders,
        total_customers=total_customers,
        total_revenue=total_revenue,
        recent_orders=recent_orders
    )

@app.route('/admin-logout')
def admin_logout():

    # Clear admin session
    session.pop('admin_id', None)
    session.pop('admin_name', None)
    session.pop('admin_email', None)

    flash("Logged out successfully.", "success")
    return redirect('/admin-login')

@app.route('/admin/add-item', methods=['GET'])
def add_item_page():

    # Only logged-in admin can access
    if 'admin_id' not in session:
        flash("Please login first!", "danger")
        return redirect('/admin-login')

    return render_template("admin/add_item.html")

@app.route('/admin/add-item', methods=['POST'])
def add_item():

    if 'admin_id' not in session:
        flash("Please login first!", "danger")
        return redirect('/admin-login')

    name = request.form['name']
    description = request.form['description']
    category = request.form['category']
    price = request.form['price']
    image_file = request.files['image']

    if image_file.filename == "":
        flash("Please upload a product image!", "danger")
        return redirect('/admin/add-item')
    filename = secure_filename(image_file.filename)

    image_path = os.path.join(app.config['UPLOAD_FOLDER'], filename)
    image_file.save(image_path)
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute(
        "INSERT INTO products (name, description, category, price, image) VALUES (?, ?, ?, ?, ?)",
        (name, description, category, price, filename)
    )
    conn.commit()
    cursor.close()
    conn.close()

    flash("Product added successfully!", "success")
    return redirect('/admin/item-list')

@app.route('/admin/view-item/<int:item_id>')
def view_item(item_id):
    if 'admin_id' not in session:
        flash("Please login first!", "danger")
        return redirect('/admin-login')

    conn = get_db_connection()
    cursor = conn.cursor()

    cursor.execute("SELECT * FROM products WHERE product_id = ?", (item_id,))
    product = cursor.fetchone()

    cursor.close()
    conn.close()

    if not product:
        flash("Product not found!", "danger")
        return redirect('/admin/item-list')

    return render_template("admin/view_item.html", product=product)

@app.route('/admin/update-item/<int:item_id>', methods=['GET'])
def update_item_page(item_id):

    if 'admin_id' not in session:
        flash("Please login!", "danger")
        return redirect('/admin-login')

    conn = get_db_connection()
    cursor = conn.cursor()

    cursor.execute("SELECT * FROM products WHERE product_id = ?", (item_id,))
    product = cursor.fetchone()

    cursor.close()
    conn.close()

    if not product:
        flash("Product not found!", "danger")
        return redirect('/admin/item-list')

    return render_template("admin/update_item.html", product=product)

@app.route('/admin/update-item/<int:item_id>', methods=['POST'])
def update_item(item_id):

    if 'admin_id' not in session:
        flash("Please login!", "danger")
        return redirect('/admin-login')

    name = request.form['name']
    description = request.form['description']
    category = request.form['category']
    price = request.form['price']

    new_image = request.files['image']

    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM products WHERE product_id = ?", (item_id,))
    product = cursor.fetchone()

    if not product:
        flash("Product not found!", "danger")
        return redirect('/admin/item-list')

    old_image_name = product['image']

    if new_image and new_image.filename != "":
        
        from werkzeug.utils import secure_filename
        new_filename = secure_filename(new_image.filename)
        new_image_path = os.path.join(app.config['UPLOAD_FOLDER'], new_filename)
        new_image.save(new_image_path)
        old_image_path = os.path.join(app.config['UPLOAD_FOLDER'], old_image_name)
        if os.path.exists(old_image_path):
            os.remove(old_image_path)

        final_image_name = new_filename

    else:
        final_image_name = old_image_name

    cursor.execute("""
        UPDATE products
        SET name=?, description=?, category=?, price=?, image=?
        WHERE product_id=?
    """, (name, description, category, price, final_image_name, item_id))

    conn.commit()
    cursor.close()
    conn.close()

    flash("Product updated successfully!", "success")
    return redirect('/admin/item-list')

@app.route('/admin/delete-item/<int:item_id>')
def delete_item(item_id):

    if 'admin_id' not in session:
        flash("Please login first!", "danger")
        return redirect('/admin-login')

    conn = get_db_connection()
    cursor = conn.cursor()

    # 1️⃣ Fetch product to get image name
    cursor.execute("SELECT image FROM products WHERE product_id=?", (item_id,))
    product = cursor.fetchone()

    if not product:
        flash("Product not found!", "danger")
        return redirect('/admin/item-list')

    image_name = product['image']

    # Delete image from folder
    image_path = os.path.join(app.config['UPLOAD_FOLDER'], image_name)
    if os.path.exists(image_path):
        os.remove(image_path)

    # 2️⃣ Delete product from DB
    cursor.execute("DELETE FROM products WHERE product_id=?", (item_id,))
    conn.commit()

    cursor.close()
    conn.close()

    flash("Product deleted successfully!", "success")
    return redirect('/admin/item-list')

@app.route('/admin/item-list')
def item_list():

    if 'admin_id' not in session:
        flash("Please login!", "danger")
        return redirect('/admin-login')

    search = request.args.get('search', '')
    category_filter = request.args.get('category', '')

    conn = get_db_connection()
    cursor = conn.cursor()

    # 1️⃣ Fetch category list for dropdown
    cursor.execute("SELECT DISTINCT category FROM products")
    categories = cursor.fetchall()

    # 2️⃣ Build dynamic query based on filters
    query = "SELECT * FROM products WHERE 1=1"
    params = []

    if search:
        query += " AND name LIKE ?"
        params.append("%" + search + "%")

    if category_filter:
        query += " AND category = ?"
        params.append(category_filter)

    cursor.execute(query, params)
    products = cursor.fetchall()

    cursor.close()
    conn.close()

    return render_template(
        "admin/item_list.html",
        products=products,
        categories=categories
    )

@app.route('/admin/profile', methods=['GET'])
def admin_profile():

    if 'admin_id' not in session:
        flash("Please login!", "danger")
        return redirect('/admin-login')

    admin_id = session['admin_id']

    conn = get_db_connection()
    cursor = conn.cursor()

    cursor.execute("SELECT * FROM admin WHERE admin_id = ?", (admin_id,))
    admin = cursor.fetchone()

    cursor.close()
    conn.close()

    return render_template("admin/admin_profile.html", admin=admin)

@app.route('/admin/profile', methods=['POST'])
def admin_profile_update():

    if 'admin_id' not in session:
        flash("Please login!", "danger")
        return redirect('/admin-login')

    admin_id = session['admin_id']

    # 1️⃣ Get form data
    name = request.form['name']
    email = request.form['email']
    new_password = request.form['password']
    new_image = request.files['profile_image']

    conn = get_db_connection()
    cursor = conn.cursor()

    # 2️⃣ Fetch old admin data
    cursor.execute("SELECT * FROM admin WHERE admin_id = ", (admin_id,))
    admin = cursor.fetchone()

    old_image_name = admin['profile_image']

    # 3️⃣ Update password only if entered
    if new_password:
        hashed_password = bcrypt.hashpw(new_password.encode('utf-8'), bcrypt.gensalt())
    else:
        hashed_password = admin['password']  # keep old password

    # 4️⃣ Process new profile image if uploaded
    if new_image and new_image.filename != "":
        
        from werkzeug.utils import secure_filename
        new_filename = secure_filename(new_image.filename)

        # Save new image
        image_path = os.path.join(app.config['ADMIN_UPLOAD_FOLDER'], new_filename)
        new_image.save(image_path)

        # Delete old image
        if old_image_name:
            old_image_path = os.path.join(app.config['ADMIN_UPLOAD_FOLDER'], old_image_name)
            if os.path.exists(old_image_path):
                os.remove(old_image_path)

        final_image_name = new_filename
    else:
        final_image_name = old_image_name

    # 5️⃣ Update database
    cursor.execute("""
        UPDATE admin
        SET name=?, email=?, password=?, profile_image=?
        WHERE admin_id=?
    """, (name, email, hashed_password, final_image_name, admin_id))

    conn.commit()
    cursor.close()
    conn.close()

    # Update session name for UI consistency
    session['admin_name'] = name  
    session['admin_email'] = email

    flash("Profile updated successfully!", "success")
    return redirect('/admin/profile')

@app.route('/admin/edit-item/<int:item_id>', methods=['GET'])
def edit_item_page(item_id):

    if 'admin_id' not in session:
        flash("Please login!", "danger")
        return redirect('/admin-login')

    conn = get_db_connection()
    cursor = conn.cursor()

    cursor.execute("SELECT * FROM products WHERE product_id = ?", (item_id,))
    product = cursor.fetchone()

    cursor.close()
    conn.close()

    if not product:
        flash("Product not found!", "danger")
        return redirect('/admin/item-list')

    return render_template("admin/edit_item.html", product=product)

@app.route('/admin/edit-item/<int:item_id>', methods=['POST'])
def edit_item(item_id):
    if 'admin_id' not in session:
        flash("Please login!", "danger")
        return redirect('/admin-login')

    name = request.form['name']
    description = request.form['description']
    category = request.form['category']
    price = request.form['price']

    new_image = request.files['image']

    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM products WHERE product_id = ?", (item_id,))
    product = cursor.fetchone()

    if not product:
        flash("Product not found!", "danger")
        return redirect('/admin/item-list')

    old_image_name = product['image']

    if new_image and new_image.filename != "":
        
        from werkzeug.utils import secure_filename
        new_filename = secure_filename(new_image.filename)
        new_image_path = os.path.join(app.config['UPLOAD_FOLDER'], new_filename)
        new_image.save(new_image_path)
        old_image_path = os.path.join(app.config['UPLOAD_FOLDER'], old_image_name)
        if os.path.exists(old_image_path):
            os.remove(old_image_path)

        final_image_name = new_filename

    else:
        final_image_name = old_image_name

    cursor.execute("""
        UPDATE products
        SET name=?, description=?, category=?, price=?, image=?
        WHERE product_id=?
    """, (name, description, category, price, final_image_name, item_id))

    conn.commit()
    cursor.close()
    conn.close()

    flash("Product updated successfully!", "success")
    return redirect('/admin/item-list')

@app.route('/admin/orders')
def admin_orders():

    if 'admin_id' not in session:
        return redirect('/admin-login')

    conn = get_db_connection()
    cursor = conn.cursor()

    cursor.execute("""
        SELECT *
        FROM orders
        ORDER BY order_id DESC
    """)

    orders = cursor.fetchall()

    cursor.close()
    conn.close()

    return render_template(
        'admin/orders.html',
        orders=orders
    )
#--------------------------
# UserModule
#--------------------------
@app.route('/home')
def userhome():
    return render_template("user/home.html")

@app.route('/about')
def about():
    return render_template("user/about.html")


@app.route('/contact', methods=['GET', 'POST'])
def contact():

    if request.method == 'POST':

        name = request.form['name']
        email = request.form['email']
        subject = request.form['subject']
        message = request.form['message']

        
        conn = get_db_connection()
        cursor = conn.cursor()
        cursor.execute(
            "INSERT INTO contact(name,email,subject,message) VALUES(?,?,?,?)",
            (name, email, subject, message)
        )
        conn.commit()
        cursor.close()
        conn.close()

        flash("Your message has been sent successfully!", "success")
        return redirect('/contact')

    return render_template("user/contact.html")

#register user route


@app.route('/register', methods=['GET', 'POST'])
def register():

    if request.method == "GET":
        return render_template("user/register.html")

    name = request.form['username']
    email = request.form['email']

    conn = get_db_connection()
    cursor = conn.cursor()

    cursor.execute(
        "SELECT user_id FROM users WHERE email=?",
        (email,)
    )

    user = cursor.fetchone()

    cursor.close()
    conn.close()

    if user:
        flash("Email already registered. Please login.", "danger")
        return redirect('/register')

    session['user_name'] = name
    session['user_email'] = email

    otp = random.randint(100000,999999)

    session['user_otp'] = otp

    message = Message(
        subject="Smart Card User OTP",
        sender=config.MAIL_USERNAME,
        recipients=[email]
    )

    message.body = f"""
Hello {name},

Your OTP for Smart Card Registration is:

{otp}

Do not share this OTP with anyone.

Thank You.
"""

    mail.send(message)

    flash("OTP has been sent to your email.", "success")

    return redirect('/user-verify-otp')

#otp verification route

# ==========================================================
# USER OTP VERIFICATION (GET + POST)
# ==========================================================

@app.route('/user-verify-otp', methods=['GET', 'POST'])
def user_verify_otp():

    # Check if user came from registration
    if 'user_email' not in session:
        flash("Please register first.", "danger")
        return redirect('/register')

    # ------------------ GET ------------------
    if request.method == "GET":
        return render_template(
            "user/otppage.html",
            email=session['user_email']
        )

    # ------------------ POST ------------------

    entered_otp = request.form['otp']
    password = request.form['password']
    confirm_password = request.form['confirm_password']

    # OTP Validation
    if str(session.get('user_otp')) != entered_otp:
        flash("Invalid OTP.", "danger")
        return redirect('/user-verify-otp')

    # Password Validation
    if password != confirm_password:
        flash("Passwords do not match.", "danger")
        return redirect('/user-verify-otp')

    # Hash Password
    hashed_password = bcrypt.hashpw(
        password.encode('utf-8'),
        bcrypt.gensalt()
    )

    # Save User
    conn = get_db_connection()
    cursor = conn.cursor()

    cursor.execute("""
        INSERT INTO users(name, email, password)
        VALUES(?, ?, ?)
    """, (
        session['user_name'],
        session['user_email'],
        hashed_password
    ))

    conn.commit()
    cursor.close()
    conn.close()

    # Clear Session
    session.pop('user_name', None)
    session.pop('user_email', None)
    session.pop('user_otp', None)

    flash("Registration Successful! Please Login.", "success")

    return redirect('/login')


#resend otp route


@app.route('/resend-otp')
def resend_otp():

    if 'user_email' not in session:
        return redirect('/register')

    otp = random.randint(100000,999999)

    session['user_otp'] = otp

    message = Message(

        subject="Smart Card OTP",

        sender=config.MAIL_USERNAME,

        recipients=[session['user_email']]

    )

    message.body = f"""
Hello,

Your New OTP is:

{otp}
"""

    mail.send(message)

    flash("OTP Resent Successfully.", "success")

    return redirect('/user-verify-otp')



# ==========================================================
# USER LOGIN (GET + POST)
# ==========================================================

@app.route('/login', methods=['GET', 'POST'])
def login():
    # Show Login Page
    if request.method == "GET":
        return render_template("user/user_login.html")
    # Get form data
    email = request.form['email']
    password = request.form['password']
    # Database connection
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute(
        "SELECT * FROM users WHERE email=?",
        (email,)
    )
    user = cursor.fetchone()
    cursor.close()
    conn.close()
    # Email not found
    if user is None:
        flash("Email not found. Please register first.", "danger")
        return redirect('/login')
    # Verify password
    stored_password = user['password']
    if not bcrypt.checkpw(password.encode('utf-8'), stored_password):
        flash("Incorrect password.", "danger")
        return redirect('/login')
    # Create session
    session['user_id'] = user['user_id']
    session['user_name'] = user['name']
    session['user_email'] = user['email']
    flash("Login Successful!", "success")
    return redirect('/dashboard')


@app.route('/profile', methods=['GET'])
def profile():

    if 'user_id' not in session:
        return redirect(url_for('login'))

    conn = get_db_connection()
    cursor = conn.cursor()

    cursor.execute(
        "SELECT * FROM users WHERE user_id=?",
        (session['user_id'],)
    )

    user = cursor.fetchone()

    cursor.close()
    conn.close()

    return render_template(
        'user/profile.html',
        user=user
    )


@app.route('/profile', methods=['POST'])
def update_profile():

    if 'user_id' not in session:
        return redirect(url_for('login'))

    user_id = session['user_id']

    name = request.form['name']
    email = request.form['email']
    new_password = request.form['password']
    new_image = request.files['profile_image']

    conn = get_db_connection()
    cursor = conn.cursor()

    cursor.execute(
        "SELECT * FROM users WHERE user_id=?",
        (user_id,)
    )

    user = cursor.fetchone()

    old_image = user['profile_image']

    # Password
    if new_password:

        hashed_password = bcrypt.hashpw(
            new_password.encode('utf-8'),
            bcrypt.gensalt()
        )

    else:
        hashed_password = user['password']

    # Image
    if new_image and new_image.filename != "":

        filename = secure_filename(
            new_image.filename
        )

        image_path = os.path.join(
            app.config['PROFILE_UPLOAD_FOLDER'],
            filename
        )

        new_image.save(image_path)

        if old_image:

            old_path = os.path.join(
                app.config['PROFILE_UPLOAD_FOLDER'],
                old_image
            )

            if os.path.exists(old_path):
                os.remove(old_path)

        final_image = filename

    else:
        final_image = old_image

    cursor.execute("""
        UPDATE users
        SET name=?,
            email=?,
            password=?,
            profile_image=?
        WHERE user_id=?
    """,
    (
        name,
        email,
        hashed_password,
        final_image,
        user_id
    ))

    conn.commit()

    cursor.close()
    conn.close()

    session['user_name'] = name
    session['email'] = email

    flash(
        "Profile updated successfully!",
        "success"
    )

    return redirect('/profile')
# ==========================================================
# USER DASHBOARD
# ==========================================================
@app.route('/dashboard')
def dashboard():
    if 'user_id' not in session:
        flash("Please login first.", "danger")
        return redirect('/login')

    search = request.args.get('search', '')
    category = request.args.get('category', '')
    conn = get_db_connection()
    cursor = conn.cursor()

    cursor.execute("SELECT DISTINCT category FROM products")
    categories = cursor.fetchall()

    query = "SELECT * FROM products WHERE 1=1"
    params = []

    if search:
        query += " AND name LIKE ?"
        params.append("%" + search + "%")

    if category:
        query += " AND category = ?"
        params.append(category)

    query += " ORDER BY product_id DESC"

    cursor.execute(query, params)
    products = cursor.fetchall()
    cursor.close()
    conn.close()
    return render_template(
        "user/dashboard.html",
        products=products,
        categories=categories,
        user_name=session['user_name']
    )
# ==========================================================
# USER LOGOUT
# ==========================================================
@app.route('/logout')
def logout():

    session.pop('user_id', None)
    session.pop('user_name', None)
    session.pop('user_email', None)

    flash("Logged out successfully.", "success")

    return redirect('/login')

# ==========================================================
# USER FORGOT PASSWORD (SEND OTP)
# ==========================================================
@app.route('/forgot-password', methods=['GET', 'POST'])
def forgot_password():

    if request.method == "GET":
        return render_template("user/forgot.html")

    email = request.form['email']

    conn = get_db_connection()
    cursor = conn.cursor()

    cursor.execute(
        "SELECT * FROM users WHERE email=?",
        (email,)
    )

    user = cursor.fetchone()

    cursor.close()
    conn.close()

    if user is None:
        flash("Email is not registered.", "danger")
        return redirect('/forgot-password')

    # Store email in session
    session['reset_email'] = email

    # Generate OTP
    otp = random.randint(100000, 999999)
    session['reset_otp'] = otp

    # Send Email
    message = Message(
        subject="Smart Card Password Reset OTP",
        sender=config.MAIL_USERNAME,
        recipients=[email]
    )

    message.body = f"""
Hello,

Your OTP for resetting your Smart Card password is:

{otp}

Do not share this OTP with anyone.

Thank You.
"""

    mail.send(message)

    flash("OTP sent successfully to your email.", "success")

    return redirect('/reset-password')


# ==========================================================
# USER RESET PASSWORD
# ==========================================================
@app.route('/reset-password', methods=['GET', 'POST'])
def reset_password():

    # Check if forgot password process was started
    if 'reset_email' not in session:
        flash("Please use the Forgot Password page first.", "danger")
        return redirect('/forgot-password')

    # Show Reset Password Page
    if request.method == "GET":
        return render_template("user/reset_password.html")

    # Get form data
    otp = request.form['otp']
    password = request.form['password']
    confirm_password = request.form['confirm_password']

    # Verify OTP
    if str(session.get('reset_otp')) != otp:
        flash("Invalid OTP.", "danger")
        return redirect('/reset-password')

    # Verify Password
    if password != confirm_password:
        flash("Passwords do not match.", "danger")
        return redirect('/reset-password')

    # Hash Password
    hashed_password = bcrypt.hashpw(
        password.encode('utf-8'),
        bcrypt.gensalt()
    )

    # Update Password
    conn = get_db_connection()
    cursor = conn.cursor()

    cursor.execute(
        """
        UPDATE users
        SET password = ?
        WHERE email = ?
        """,
        (
            hashed_password,
            session['reset_email']
        )
    )

    conn.commit()
    cursor.close()
    conn.close()

    # Clear Session
    session.pop('reset_email', None)
    session.pop('reset_otp', None)

    flash("Password updated successfully. Please login.", "success")

    return redirect('/login')


#==========================================================
# USER PRODUCT DETAILS PAGE
#===========================================================

@app.route('/product/<int:product_id>')
def product_details(product_id):

    if 'user_id' not in session:
        flash("Please login first.", "danger")
        return redirect('/login')

    conn = get_db_connection()
    cursor = conn.cursor()

    cursor.execute(
        "SELECT * FROM products WHERE product_id=?",
        (product_id,)
    )

    product = cursor.fetchone()

    cursor.close()
    conn.close()

    if product is None:
        flash("Product not found.", "danger")
        return redirect('/dashboard')

    return render_template(
        "user/product_details.html",
        product=product
    )



@app.route('/buy-now/<int:product_id>')
def buy_now(product_id):

    conn = get_db_connection()
    cursor = conn.cursor()

    cursor.execute(
        "SELECT * FROM products WHERE product_id=?",
        (product_id,)
    )

    product = cursor.fetchone()

    cursor.close()
    conn.close()

    # Create temporary cart with only this product
    session['cart'] = {
        str(product_id): {
            'product_id': product['product_id'],
            'name': product['name'],
            'price': float(product['price']),
            'image': product['image'],
            'quantity': 1
        }
    }

    session.modified = True

    return redirect(url_for('checkout'))


#=========================================================
#add to cart route
#=========================================================
@app.route('/add-to-cart/<int:product_id>')
def add_to_cart(product_id):

    conn = get_db_connection()
    cursor = conn.cursor()

    cursor.execute(
        "SELECT * FROM products WHERE product_id=?",
        (product_id,)
    )

    product = cursor.fetchone()

    cursor.close()
    conn.close()

    cart = session.get('cart', {})

    pid = str(product_id)

    if pid in cart:
        cart[pid]['quantity'] += 1
    else:
        cart[pid] = {
            'product_id': product['product_id'],
            'name': product['name'],
            'price': float(product['price']),
            'image': product['image'],
            'quantity': 1
        }

    session['cart'] = cart
    session.modified = True
    print("CART AFTER ADD =", session['cart'])

    flash("Product added to cart!", "success")
    return redirect('/dashboard')

#=========================================================
#view cart route
#=========================================================
@app.route('/cart')
def cart():

    cart = session.get('cart', {})

    cart_items = list(cart.values())

    grand_total = sum(
        item['price'] * item['quantity']
        for item in cart_items
    )

    return render_template(
        'user/cart.html',
        cart_items=cart_items,
        grand_total=grand_total
    )

#=========================================================
#cart count context processor
#=========================================================

@app.context_processor
def cart_count():

    count = 0

    cart = session.get('cart', {})

    for item in cart.values():
        count += item['quantity']

    return dict(cart_count=count)
#=========================================================
#decrease quantity route
#=========================================================

@app.route('/decrease-quantity/<int:product_id>')
def decrease_quantity(product_id):

    cart = session.get('cart', {})

    pid = str(product_id)

    if pid in cart:

        if cart[pid]['quantity'] > 1:
            cart[pid]['quantity'] -= 1
        else:
            del cart[pid]

    session['cart'] = cart
    session.modified = True

    return redirect(url_for('cart'))

#=========================================================
#increase quantity route
#=========================================================
@app.route('/increase-quantity/<int:product_id>')
def increase_quantity(product_id):

    cart = session.get('cart', {})

    pid = str(product_id)

    print("BEFORE =", cart)

    if pid in cart:
        cart[pid]['quantity'] += 1

    session['cart'] = cart
    session.modified = True

    print("AFTER =", cart)

    return redirect(url_for('cart'))
#=========================================================
#remove item from cart route
#=========================================================

@app.route('/remove-cart-item/<int:product_id>')
def remove_cart_item(product_id):

    cart = session.get('cart', {})

    pid = str(product_id)

    if pid in cart:
        del cart[pid]

    session['cart'] = cart
    session.modified = True
    flash("Item removed from cart.", "success")

    return redirect(url_for('cart'))


@app.route('/checkout', methods=['GET', 'POST'])
def checkout():

    if 'user_id' not in session:
        flash("Please login first!", "danger")
        return redirect('/login')

    user_id = session['user_id']

    # SAVE NEW ADDRESS
    if request.method == 'POST':

        full_name = request.form['full_name']
        mobile = request.form['mobile']
        address = request.form['address']
        city = request.form['city']
        state = request.form['state']
        pincode = request.form['pincode']

        conn = get_db_connection()
        cursor = conn.cursor()

        cursor.execute("""
            INSERT INTO addresses
            (user_id, full_name, mobile, address, city, state, pincode)
            VALUES (?,?,?,?,?,?,?)
        """,
        (
            user_id,
            full_name,
            mobile,
            address,
            city,
            state,
            pincode
        ))

        conn.commit()
        cursor.close()
        conn.close()

        flash("Address saved successfully!", "success")
        return redirect('/checkout')

    # GET SAVED ADDRESSES
    conn = get_db_connection()
    cursor = conn.cursor()

    cursor.execute("""
        SELECT *
        FROM addresses
        WHERE user_id=?
        ORDER BY address_id DESC
    """, (user_id,))

    addresses = cursor.fetchall()

    cursor.close()
    conn.close()

    return render_template(
        'user/checkout.html',
        addresses=addresses
    )


@app.route('/products')
def products():

    if 'user_id' not in session:
        return redirect('/login')

    search = request.args.get('search', '')
    category = request.args.get('category', '')

    conn = get_db_connection()
    cursor = conn.cursor()

    cursor.execute("SELECT DISTINCT category FROM products")
    categories = cursor.fetchall()

    query = "SELECT * FROM products WHERE 1=1"
    params = []

    if search:
        query += " AND name LIKE ?"
        params.append(f"%{search}%")

    if category:
        query += " AND category=?"
        params.append(category)

    cursor.execute(query, params)
    products = cursor.fetchall()

    cursor.close()
    conn.close()

    return render_template(
        'user/products.html',
        products=products,
        categories=categories
    )



@app.route('/user/pay')
def user_pay():

    if 'user_id' not in session:
        return redirect('/login')

    address_id = request.args.get('address_id')

    conn = get_db_connection()
    cursor = conn.cursor()

    # Get selected address
    cursor.execute(
        "SELECT * FROM addresses WHERE address_id=?",
        (address_id,)
    )

    address = cursor.fetchone()

    # Store selected address in session
    session['selected_address'] = {
        'full_name': address['full_name'],
        'mobile': address['mobile'],
        'address': address['address'],
        'city': address['city'],
        'state': address['state'],
        'pincode': address['pincode']
    }

    cursor.close()
    conn.close()

    cart = session.get('cart', {})

    if not cart:
        flash("Cart is empty!", "danger")
        return redirect('/cart')

    total_amount = sum(
        item['price'] * item['quantity']
        for item in cart.values()
    )

    razorpay_amount = int(total_amount * 100)

    razorpay_order = razorpay_client.order.create({
        "amount": razorpay_amount,
        "currency": "INR",
        "payment_capture": "1"
    })

    return render_template(
        'user/payment.html',
        amount=total_amount,
        key_id=config.RAZORPAY_KEY_ID,
        order_id=razorpay_order['id']
    )



@app.route('/payment-success')
def payment_success():

    if 'user_id' not in session:
        return redirect('/login')

    payment_id = request.args.get('payment_id')
    razorpay_order_id = request.args.get('order_id')

    user_id = session['user_id']
    cart = session.get('cart', {})
    address = session.get('selected_address')

    total_amount = sum(
        item['price'] * item['quantity']
        for item in cart.values()
    )

    conn = get_db_connection()
    cursor = conn.cursor()

    # Create Order
    cursor.execute("""
        INSERT INTO orders
        (
            user_id,
            razorpay_order_id,
            razorpay_payment_id,
            amount,
            payment_status
        )
        VALUES (?,?,?,?,?)
    """,
    (
        user_id,
        razorpay_order_id,
        payment_id,
        total_amount,
        "Success",
    ))

    order_db_id = cursor.lastrowid

    # Save Order Items
    for item in cart.values():

        cursor.execute("""
            INSERT INTO order_items
            (
                order_id,
                product_id,
                product_name,
                quantity,
                price
            )
            VALUES (?,?,?,?,?)
        """,
        (
            order_db_id,
            item['product_id'],
            item['name'],
            item['quantity'],
            item['price']
        ))

    conn.commit()
    cursor.close()
    conn.close()

    session.pop('cart', None)

    return redirect(
        url_for(
            'order_success',
            order_db_id=order_db_id
        )
    )





@app.route('/save-address', methods=['POST'])
def save_address():

    session['address'] = {
        'fullname': request.form['fullname'],
        'phone': request.form['phone'],
        'address': request.form['address'],
        'city': request.form['city'],
        'state': request.form['state'],
        'pincode': request.form['pincode']
    }

    return redirect('/user/pay')


@app.route('/verify-payment', methods=['POST'])
def verify_payment():

    data = request.get_json()

    payment_id = data['razorpay_payment_id']
    order_id = data['razorpay_order_id']

    cart = session.get('cart', {})
    user_id = session['user_id']

    total_amount = sum(
        item['price'] * item['quantity']
        for item in cart.values()
    )

    conn = get_db_connection()
    cursor = conn.cursor()

    # Save order
    cursor.execute("""
        INSERT INTO orders
        (
            user_id,
            razorpay_order_id,
            razorpay_payment_id,
            amount,
            payment_status
        )
        VALUES (?,?,?,?,?)
    """, (
        user_id,
        order_id,
        payment_id,
        total_amount,
        'SUCCESS'
    ))

    conn.commit()

    order_db_id = cursor.lastrowid

    # Save order items
    for item in cart.values():

        cursor.execute("""
            INSERT INTO order_items
            (
                order_id,
                product_id,
                product_name,
                quantity,
                price
            )
            VALUES (?,?,?,?,?)
        """, (
            order_db_id,
            item['product_id'],
            item['name'],
            item['quantity'],
            item['price']
        ))

    conn.commit()

    cursor.close()
    conn.close()

    # Clear cart
    session.pop('cart', None)
    session.modified = True

    return {
        "redirect_url":
        url_for(
            'order_success',
            order_db_id=order_db_id
        )
    }


@app.route('/user/order-success/<int:order_db_id>')
def order_success(order_db_id):

    conn = get_db_connection()
    cursor = conn.cursor()

    cursor.execute(
        "SELECT * FROM orders WHERE order_id=?",
        (order_db_id,)
    )

    order = cursor.fetchone()

    cursor.close()
    conn.close()

    address = session.get('selected_address')

    return render_template(
        'user/order_success.html',
        order=order,
        address=address
    )



@app.route('/user/my-orders')
def my_orders():

    if 'user_id' not in session:
        return redirect('/login')

    conn = get_db_connection()
    cursor = conn.cursor()

    cursor.execute("""
        SELECT *
        FROM orders
        WHERE user_id=?
        ORDER BY order_id DESC
    """, (session['user_id'],))

    orders = cursor.fetchall()

    cursor.close()
    conn.close()

    return render_template(
        'user/my_orders.html',
        orders=orders
    )


@app.route('/user/download-invoice/<int:order_id>')
def download_invoice(order_id):

    conn = get_db_connection()
    cursor = conn.cursor()

    cursor.execute("""
        SELECT *
        FROM orders
        WHERE order_id=?
    """, (order_id,))

    order = cursor.fetchone()

    cursor.execute("""
        SELECT *
        FROM order_items
        WHERE order_id=?
    """, (order_id,))

    order_items = cursor.fetchall()

    cursor.close()
    conn.close()

    address = session.get('selected_address')

    html = render_template(
        'user/invoice.html',
        order=order,
        order_items=order_items,
        address=address
    )

    pdf = generate_pdf(html)

    response = make_response(pdf.getvalue())

    response.headers['Content-Type'] = 'application/pdf'

    response.headers['Content-Disposition'] = (
        f'attachment; filename=invoice_{order_id}.pdf'
    )

    return response



if __name__ == '__main__':
    app.run(debug=True)