import os
import json
from decimal import Decimal, ROUND_HALF_UP
from datetime import datetime
from functools import wraps
import uuid # Consolidated: Used for generating unique IDs
from supabase import create_client, Client
from dotenv import load_dotenv
from flask import Flask, render_template, request, redirect, url_for, session, make_response, flash, jsonify 
# from num2words import num2words
# --- WeasyPrint/ReportLab Imports (Kept for external dependency safety) ---
try:
    from weasyprint import HTML, CSS
    _WEASYPRINT_AVAILABLE = True
except Exception:
    HTML = None
    CSS = None
    _WEASYPRINT_AVAILABLE = False

try:
    from reportlab.pdfgen import canvas
    from reportlab.lib.pagesizes import letter
    _REPORTLAB_AVAILABLE = True
except Exception:
    _REPORTLAB_AVAILABLE = False
# --- End Imports ---

load_dotenv()

# --- SUPABASE CONFIGURATION ---
SUPABASE_URL = os.getenv("SUPABASE_URL", "https://iunmoiepxcaknummycbj.supabase.co")
SUPABASE_KEY = os.getenv("SUPABASE_KEY", "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJpc3MiOiJzdXBhYmFzZSIsInJlZiI6Iml1bm1vaWVweGNha251bW15Y2JqIiwicm9sZSI6ImFub24iLCJpYXQiOjE3NjE1NjUwNDksImV4cCI6MjA3NzE0MTA0OX0.F77ktSH2Ss-m6jieEToq_I-jA9ACpfk4d8me2DCE0OQ") # ENSURE THIS IS CORRECT


# Initialize Supabase Client
supabase: Client = create_client(SUPABASE_URL, SUPABASE_KEY)

app = Flask(__name__)
app.secret_key = os.urandom(24) 

# --- MOCK SETTINGS DATA ---
DEFAULT_BILLING_SETTINGS = {
    "companyName": "RK Construction", "companyAddress": "123 Hardware Lane, Buildsville, ST 12345", 
    "footerText": "Thank you for your business! All sales are final.",
    "bank_name": "CENTRAL BANK OF INDIA", "account_number": "223900761",
    "tax_rate_cgst": 0.09, "tax_rate_sgst": 0.09
}
DEFAULT_SHOP_SETTINGS = {
        "shop_welcome_text": "Welcome! Browse our comprehensive selection of high-quality materials.",
        "global_font": "Arial, sans-serif"
    }
DEFAULT_ABOUT_SETTINGS = {
    "intro_text": "Content loading error.", "map_url": "Default Address",
    "image_url_1": "", "image_url_2": "", "image_url_3": "", "body_text": ""
}
ABOUT_US_PAGE_DATA = {
    "intro_text": "Your one-stop shop for all hardware needs. Since 1995, we've been proudly serving our community with high-quality products, expert advice, and a commitment to customer satisfaction. Whether you're a professional contractor or a weekend DIY warrior, we have the tools and materials to get the job done right.",
    "image_url_1": "https://placehold.co/400x300/e0f2f1/000?text=Symbol_1", 
    "image_url_2": "https://placehold.co/400x300/e0f2f1/000?text=Symbol_2",
    "image_url_3": "https://placehold.co/400x300/e0f2f1/000?text=Symbol_3",
    "body_text": "Our knowledgeable staff is always on hand to help you find exactly what you're looking for, from the smallest nut and bolt to the most powerful of tools. We believe in building relationships with our customers, not just making sales. Come visit us and experience the RK Construction difference.",
    "map_url": "https://www.google.com/maps/embed?pb=!1m18!1m12!1m3!1d3022.454794254271!2d-73.99049908459468!3d40.74844007932857!2m3!1f0!2f0!3f0!3m2!1i1024!2i768!4f13.1!3m3!1m2!1s0x89c2598a3b8e7e1f%3A0xf63980b1e4f4b2f!2sEmpire%20State%20Building!5e0!3m2!1sen!2sus!4v1612345678901",
}
# --- UTILITY FUNCTIONS ---

def get_cart():
    return session.get('cart', [])

def get_cart_count():
    return sum(item['quantity'] for item in get_cart())

def clear_cart():
    session.pop('cart', None)

def calculate_cart_total(cart_items):
    return sum(item['price'] * item['quantity'] for item in cart_items)

# --- CONTEXT PROCESSOR ---
@app.context_processor
def user_context_processor():
    return dict(
        user_id=session.get('user_id'),
        user_role=session.get('user_role'),
        user_name=session.get('user_name'),
        cart_count=get_cart_count(),
    )

# --- DECORATORS & FILTERS ---

def login_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if 'user_id' not in session:
            return redirect(url_for('login_register'))
        return f(*args, **kwargs)
    return decorated_function

def role_required(role):
    def decorator(f):
        @wraps(f)
        def decorated_function(*args, **kwargs):
            if session.get('user_role') != role:
                flash("Access denied. Insufficient permissions.", 'error')
                return redirect(url_for('shop'))
            return f(*args, **kwargs)
        return decorated_function
    return decorator

def datetimeformat(value):
    if value:
        if isinstance(value, str):
            value = datetime.fromisoformat(value.replace('Z', '+00:00'))
        return value.strftime('%Y-%m-%d')
    return ''

def format_float(value):
    return "%.2f" % value if value is not None else "0.00"

app.jinja_env.filters['datetimeformat'] = datetimeformat
app.jinja_env.filters['format_float'] = format_float


# --- AUTH ROUTES ---

@app.route('/', methods=['GET'])
@app.route('/login', methods=['GET', 'POST'])
def login_register():
    if request.method == 'POST':
        mode = request.form.get('mode')
        email = request.form.get('email')
        password = request.form.get('password')
        error = None

        try:
            if mode == 'login':
                auth_response = supabase.auth.sign_in_with_password({'email': email, 'password': password})
                user_id = auth_response.session.user.id
                profile_res = supabase.table('profiles').select('name, role').eq('id', user_id).single().execute()
                profile = profile_res.data
                
                session['user_id'] = user_id
                session['user_role'] = profile['role']
                session['user_name'] = profile['name']
                session['user_email'] = email

                if profile['role'] == 'admin':
                    return redirect(url_for('admin_dashboard'))
                return redirect(url_for('shop'))

            elif mode == 'register':
                name = request.form.get('name')
                phone = request.form.get('phone')
                address = request.form.get('address')
                
                supabase.auth.sign_up({
                    'email': email,
                    'password': password,
                    'options': {
                        'data': {'name': name, 'phone': phone, 'address': address, 'role': 'customer'}
                    }
                })
                flash("Registration successful! Check your email to verify and log in.", 'success')
                return render_template('auth_login_register.html')

        except Exception as e:
            print(f"Auth Error: {e}")
            error = "Authentication failed. Check credentials or verify email."
            
        return render_template('auth_login_register.html', error=error)

    if 'user_id' in session:
        if session.get('user_role') == 'admin':
            return redirect(url_for('admin_dashboard'))
        return redirect(url_for('shop'))
        
    return render_template('auth_login_register.html')

@app.route('/logout')
def logout():
    session.clear()
    flash("You have been logged out.", 'info')
    return redirect(url_for('login_register'))


# --- CUSTOMER ROUTES ---

# @app.route('/shop', methods=['GET'])
# @login_required
# def shop():
#     products_res = supabase.table('products').select('*').order('name').execute()
#     products = products_res.data
#     return render_template('shop.html', products=products)

# SITE_SETTINGS = {
#     "shop_welcome_text": "Welcome to RK Construction's online store. Browse our comprehensive selection of high-quality plumbing, hardware, and construction materials needed for your next project.",
#     "global_font": "Arial, sans-serif" # Mock font setting
# }

# --- Update the 'shop' route to use the centralized text ---
# --- CUSTOMER ROUTES ---

# --- In main.py, under CUSTOMER ROUTES ---
@app.route('/shop', methods=['GET'])
@login_required
def shop():
    products_res = supabase.table('products').select('*, category').order('name').execute()
    products = products_res.data
    
    categories = sorted(list(set(p['category'] for p in products if p['category'])))

    # FIX: FETCH shop_settings from DB using its page_key
    PAGE_KEY = 'shop_settings'
    try:
        settings_res = supabase.table('site_settings').select('content').eq('page_key', PAGE_KEY).execute()
        shop_settings = settings_res.data[0]['content'] 
        # if settings_res.data and settings_res.data[0] else DEFAULT_SHOP_SETTINGS
    except Exception as e:
        print(f"Shop Settings Fetch Error: {e}")
        # shop_settings = DEFAULT_SHOP_SETTINGS

    return render_template('shop.html', 
                           products=products,
                           categories=categories,
                           # Pass the text fetched from the DB
                           welcome_text=shop_settings['shop_welcome_text'])
    
    
@app.route('/cart/add', methods=['POST'])
@login_required
def add_to_cart():
    product_id = request.form.get('product_id')
    quantity = int(request.form.get('quantity', 1))
    
    try:
        product_res = supabase.table('products').select('*').eq('id', product_id).single().execute()
        product = product_res.data
    except Exception:
        flash("Product not found.", 'error')
        return redirect(url_for('shop'))
        
    if product['stock'] < quantity:
        flash("Not enough stock available.", 'error')
        return redirect(url_for('shop'))

    cart = get_cart()
    item_found = False
    for item in cart:
        if item['product_id'] == product_id:
            if item['quantity'] + quantity > product['stock']:
                 flash(f"Cannot add more {product['name']}. Stock limit is {product['stock']}.", 'error')
                 return redirect(url_for('shop'))
                 
            item['quantity'] += quantity
            item_found = True
            break
            
    if not item_found:
        image_url = product.get('imageUrl') or product.get('image_url') or 'https://placehold.co/40x40'
        cart_item = {
            'product_id': product_id,
            'quantity': quantity,
            'price': product['price'],
            'name': product['name'],
            'image_url': image_url, 
            'stock': product['stock'],
        }
        cart.append(cart_item)
    session['cart'] = cart
    flash(f"{quantity}x {product['name']} added to cart.", 'success')
    return redirect(url_for('shop'))

@app.route('/cart', methods=['GET', 'POST'])
@login_required
def view_cart():
    cart = get_cart()
    if request.method == 'POST':
        if 'update_cart' in request.form:
            updated_cart = []
            for item in cart:
                new_qty = int(request.form.get(f"qty_{item['product_id']}", 0))
                if new_qty > 0 and new_qty <= item['stock']:
                    item['quantity'] = new_qty
                    updated_cart.append(item)
                elif new_qty > item['stock']:
                    flash(f"Cannot add {item['name']}: stock limit exceeded.", 'error')
                    updated_cart.append(item)
            session['cart'] = updated_cart
            flash("Cart updated.", 'success')
            return redirect(url_for('view_cart'))
        elif 'place_order' in request.form:
            if not cart:
                flash("Your cart is empty.", 'error')
                return redirect(url_for('shop'))
            return redirect(url_for('place_order'))
    total = calculate_cart_total(cart)
    return render_template('cart.html', cart=cart, total=total)


@app.route('/order/place', methods=['GET', 'POST'])
@login_required
def place_order():
    cart = get_cart()
    if not cart:
        flash("Your cart is empty.", 'error')
        return redirect(url_for('shop'))

    user_id = session.get('user_id')
    user_name = session.get('user_name')
    total = calculate_cart_total(cart)
    order_id = f"ord_{os.urandom(8).hex()}" 
    
    try:
        # 1. Create Order Record (orders table - using text ID)
        order_record = {
            "id": order_id, 
            "user_id": user_id,
            "customer_name": user_name,
            "total": total,
            "status": "Pending",
        }
        supabase.table('orders').insert(order_record).execute()
        
        # 2. Process Order Items and Update Stock 
        order_items_records = []
        for item in cart:
            order_items_records.append({
                "id": str(uuid.uuid4()), # FIX: Generating UUID for order_items ID
                "order_id": order_id,
                "product_id": item['product_id'],
                "quantity": item['quantity'],
                "price_at_purchase": item['price'],
                "discount_amount": 0, 
            })
            
            # CALL THE SUPABASE RPC (Requires the SQL function to be created)
            try:
                supabase.rpc('decrement_stock', {
                    'product_id_to_update': item['product_id'],
                    'quantity_to_decrement': item['quantity']
                }).execute()
            except Exception as rpc_error:
                print(f"Stock RPC Error: {rpc_error}")
                raise Exception(f"Failed to update stock for {item['name']}. RPC Error: {rpc_error}")

        supabase.table('order_items').insert(order_items_records).execute()
        
        # 3. Clear Cart
        clear_cart()
        
        flash(f"Order #{order_id[:8]} placed successfully!", 'success')
        return redirect(url_for('my_orders'))

    except Exception as e:
        print(f"Order Placement Critical Failure: {e}")
        flash(f"Order failed. A database error occurred: {e}", 'error')
        return redirect(url_for('view_cart'))


@app.route('/my_orders')
@login_required
def my_orders():
    user_id = session.get('user_id')
    try:
        orders_res = supabase.table('orders').select('*, order_items(*)').eq('user_id', user_id).order('date', desc=True).execute()
        orders = orders_res.data
    except Exception as e:
        print(f"Error fetching user orders: {e}")
        flash("Could not retrieve your order history.", 'error')
        orders = []

    product_ids = set()
    for order in orders:
        for item in order.get('order_items', []): 
            product_ids.add(item['product_id'])
    
    products_map = {}
    if product_ids:
        products_res = supabase.table('products').select('id, name').in_('id', list(product_ids)).execute()
        products_map = {p['id']: p['name'] for p in products_res.data}

    for order in orders:
        order['total'] = float(order.get('total', 0.0))
        for item in order.get('order_items', []):
            item['name'] = products_map.get(item['product_id'], 'Product Name Missing')

    return render_template('my_orders.html', orders=orders)


# --- ADMIN ROUTES ---

@app.route('/admin/dashboard')
@login_required
@role_required('admin')
def admin_dashboard():
    orders_res = supabase.table('orders').select('*').execute()
    orders = orders_res.data
    
    total_revenue = sum(o['total'] for o in orders)
    pending_orders = len([o for o in orders if o['status'] == 'Pending'])
    
    users_res = supabase.table('profiles').select('*').execute()
    total_customers = len([u for u in users_res.data if u['role'] == 'customer'])

    context = {
        'total_revenue': total_revenue,
        'total_orders': len(orders),
        'pending_orders': pending_orders,
        'total_customers': total_customers,
        'recent_orders': orders[:5],
    }
    return render_template('admin_dashboard.html', **context)

@app.route('/admin/products')
@login_required
@role_required('admin')
def admin_products():
    products_res = supabase.table('products').select('*').order('created_at', desc=True).execute()
    products = products_res.data
    return render_template('admin_products.html', products=products)


@app.route('/admin/products/add', methods=['GET', 'POST'])
@login_required
@role_required('admin')
def admin_add_product():
    if request.method == 'POST':
        try:
            # Generating unique ID for 'id' column (text type)
            new_product_id = f"prod_{os.urandom(8).hex()}"
            name = request.form.get('name')
            category = request.form.get('category')
            price = float(request.form.get('price'))
            stock = int(request.form.get('stock'))
            description = request.form.get('description')
            image_url_input = request.form.get('image_url')

            supabase.table('products').insert({
                'id': new_product_id, 
                'name': name,
                'category': category,
                'price': price,
                'stock': stock,
                'description': description,
                'imageUrl': image_url_input, 
            }).execute()
            
            flash(f"Product '{name}' added successfully!", 'success')
            return redirect(url_for('admin_products'))
        
        except Exception as e:
            print(f"Product Add Error: {e}")
            flash(f"Failed to add product. Error: {e}", 'error')
            
    return render_template('admin_add_product.html')


@app.route('/admin/orders')
@login_required
@role_required('admin')
def admin_orders():
    orders_res = supabase.table('orders').select('*').order('date', desc=True).execute()
    orders = orders_res.data
    return render_template('admin_orders.html', orders=orders)

@app.route('/admin/orders/<order_id>', methods=['GET'])
@login_required
@role_required('admin')
def admin_order_detail(order_id):
    """Fetches details for a single order to display on the edit page."""
    try:
        # Fetch order and order items
        order_res = supabase.table('orders').select('*, order_items(*)').eq('id', order_id).single().execute()
        order = order_res.data
        
        # Fetch product names for order items
        product_ids = [item['product_id'] for item in order['order_items']]
        products_res = supabase.table('products').select('id, name').in_('id', product_ids).execute()
        products_map = {p['id']: p['name'] for p in products_res.data}
        
        # Enrich items with name (important for display)
        for item in order['order_items']:
            item['name'] = products_map.get(item['product_id'], 'Product Name Missing')

    except Exception as e:
        print(f"Order Detail Fetch Error: {e}")
        flash("Order not found or database error.", 'error')
        return redirect(url_for('admin_orders'))

    return render_template('admin_order_detail.html', order=order)


@app.route('/admin/orders/<order_id>/update_details', methods=['POST'])
@login_required
@role_required('admin')
def update_order_details(order_id):
    """Updates order status, item quantities, and item discounts."""
    new_status = request.form.get('status')
    
    try:
        # 1. Update Order Status
        supabase.table('orders').update({'status': new_status}).eq('id', order_id).execute()
        
        new_total = 0.0
        
        # 2. Iterate through submitted items to update order_items table and recalculate total
        for key, value in request.form.items():
            if key.startswith('qty_'):
                item_id = key.split('qty_')[1]
                quantity = int(value)
                price = float(request.form.get(f'price_{item_id}', 0.0))
                discount = float(request.form.get(f'discount_{item_id}', 0.0))
                
                subtotal = (price * quantity) - discount
                new_total += subtotal
                
                # Update item record in order_items table
                supabase.table('order_items').update({
                    'quantity': quantity,
                    'discount_amount': discount,
                    # NOTE: price_at_purchase should not be changed here unless item price changed globally.
                }).eq('id', item_id).execute()

        # 3. Update Order Total
        supabase.table('orders').update({'total': new_total}).eq('id', order_id).execute()

        flash(f"Order {order_id[:8]} updated! New Total: ₹{new_total:.2f}", 'success')
        
    except Exception as e:
        print(f"Order Details Update Error: {e}")
        flash(f"Failed to update order details. Error: {e}", 'error')

    return redirect(url_for('admin_order_detail', order_id=order_id))

@app.route('/admin/users')
@login_required
@role_required('admin')
def admin_users():
    users_res = supabase.table('profiles').select('id, name, phone, address, role, created_at').order('created_at', desc=True).execute()
    users = users_res.data
    return render_template('admin_users.html', users=users)

@app.route('/admin/users/add', methods=['GET', 'POST'])
@login_required
@role_required('admin')
def admin_add_user():
    if request.method == 'POST':
        email = request.form.get('email')
        password = request.form.get('password')
        name = request.form.get('name')
        phone = request.form.get('phone')
        address = request.form.get('address')
        role = request.form.get('role')

        try:
            # Use admin.create_user for Service Role Key privileges
            supabase.auth.admin.create_user({
                'email': email,
                'password': password,
                'email_confirm': True,
                'user_metadata': {'name': name, 'phone': phone, 'address': address, 'role': role}
            })
            
            flash(f"User '{name}' ({role}) added successfully!", 'success')
            return redirect(url_for('admin_users'))

        except Exception as e:
            print(f"User Add Error: {e}")
            flash(f"Failed to add user. Check email/password requirements. Error: {e}", 'error')

    return render_template('admin_add_user.html')

@app.route('/admin/users/edit/<user_id>', methods=['GET', 'POST'])
@login_required
@role_required('admin')
def admin_edit_user(user_id):
    try:
        profile_res = supabase.table('profiles').select('*').eq('id', user_id).single().execute()
        profile = profile_res.data
    except Exception:
        flash("User not found.", 'error')
        return redirect(url_for('admin_users'))

    if request.method == 'POST':
        new_name = request.form.get('name')
        new_phone = request.form.get('phone')
        new_address = request.form.get('address')
        new_role = request.form.get('role')

        try:
            supabase.table('profiles').update({
                'name': new_name,
                'phone': new_phone,
                'address': new_address,
                'role': new_role
            }).eq('id', user_id).execute()

            flash(f"Profile for user '{new_name}' updated successfully!", 'success')
            return redirect(url_for('admin_edit_user', user_id=user_id))

        except Exception as e:
            print(f"Profile Update Error: {e}")
            flash(f"Failed to update user profile. Error: {e}", 'error')
            profile_res = supabase.table('profiles').select('*').eq('id', user_id).single().execute()
            profile = profile_res.data
    
    return render_template('admin_edit_user.html', profile=profile)


@app.route('/admin/users/password/<user_id>', methods=['POST'])
@login_required
@role_required('admin')
def admin_change_password(user_id):
    new_password = request.form.get('new_password')
    
    if not new_password or len(new_password) < 6:
        flash("Password must be at least 6 characters long.", 'error')
        return redirect(url_for('admin_edit_user', user_id=user_id))

    try:
        supabase.auth.admin.update_user_by_id(
            user_id,
            {"password": new_password}
        )
        
        flash(f"Password for user {user_id[:8]} updated successfully!", 'success')
        
    except Exception as e:
        print(f"Password Change Error: {e}")
        flash(f"Failed to update password. Error: {e}", 'error')

    return redirect(url_for('admin_edit_user', user_id=user_id))


@app.route('/admin/users/delete/<user_id>', methods=['POST'])
@login_required
@role_required('admin')
def admin_delete_user(user_id):
    try:
        supabase.table('profiles').delete().eq('id', user_id).execute()
        
        # Delete user from Supabase Auth (requires Service Role Key)
        supabase.auth.admin.delete_user(user_id)
        
        flash("User deleted successfully.", 'success')
    except Exception as e:
        print(f"User Delete Error: {e}")
        flash(f"Failed to delete user. Error: {e}", 'error')

    return redirect(url_for('admin_users'))

@app.route('/admin/bill_settings', methods=['GET', 'POST'])
@login_required
@role_required('admin')
def admin_bill_settings():
    PAGE_KEY = 'billing_settings'
    
    if request.method == 'POST':
        # 1. Gather all updated content into a single JSON object
        updated_content = {
       	    "companyName": request.form.get('companyName'),
            "companyAddress": request.form.get('companyAddress'),
            "footerText": request.form.get('footerText'),
            "bank_name": request.form.get('bank_name'),
            "account_number": request.form.get('account_number'),
            "tax_rate_cgst": request.form.get('tax_rate_cgst'),
            "tax_rate_sgst": request.form.get('tax_rate_sgst'),
        }
        
        try:
            # 2. Update the 'content' column in the site_settings table
            supabase.table('site_settings').upsert({'page_key': PAGE_KEY, 'content': updated_content}, on_conflict='page_key').execute()
            
            flash("Billing settings updated successfully!", 'success') # <- Correct message here
            return redirect(url_for('admin_bill_settings'))
            
        except Exception as e:
            print(f"About Us Update Error: {e}")
            flash(f"Failed to update About Us content. Error: {e}", 'error')

    # GET Request: Fetch current settings for the form
    try:
        settings_res = supabase.table('site_settings').select('content').eq('page_key', PAGE_KEY).single().execute()
        current_settings = settings_res.data['content']
    except Exception:
        current_settings = {} # Empty fallback
        
    return render_template('admin_bill_settings.html', settings=current_settings)

# # --- In main.py: generate_order_pdf route (FINAL CORRECTION) ---
# @app.route('/admin/order/<order_id>/pdf')
# @login_required
# def generate_order_pdf(order_id):
#     if session.get('user_role') != 'admin':
#         return "Permission Denied", 403
    
#     DEFAULT_BILLING_SETTINGS = {
#         "companyName": "RK Construction", "companyAddress": "N/A", "footerText": "Thank you!",
#         "bank_name": "Default Bank", "account_number": "000000",
#         "tax_rate_cgst": 0.0, "tax_rate_sgst": 0.0
#     }
    
#     try:
#         # FIX: Using maybe_single() to prevent crash if order ID is not found.
#         order_res = supabase.table('orders').select('*, order_items(*)').eq('id', order_id).maybe_single().execute()
        
#         # Check if the order was actually found
#         if not order_res.data:
#             return "Order not found.", 404
            
#         order_data = order_res.data[0] # Safely get the first/only item
        
#         # Fetch Billing Settings
#         settings_res = supabase.table('site_settings').select('content').eq('page_key', 'billing_settings').maybe_single().execute()
#         bill_settings = settings_res.data[0]['content'] if settings_res.data and settings_res.data[0] else DEFAULT_BILLING_SETTINGS
        
#         # 1. Fetch Product Names for display
#         product_ids = [item['product_id'] for item in order_data['order_items']]
#         products_res = supabase.table('products').select('id, name').in_('id', product_ids).execute()
#         products_map = {p['id']: p['name'] for p in products_res.data}

#         # 2. Dynamic Calculation of Totals
#         gross_sales = 0.0
#         enriched_line_items = []
        
#         CGST_RATE = float(bill_settings.get('tax_rate_cgst', 0.0))
#         SGST_RATE = float(bill_settings.get('tax_rate_sgst', 0.0))
#         TOTAL_TAX_RATE = 1 + CGST_RATE + SGST_RATE

#         for item in order_data['order_items']:
#             product_name = products_map.get(item['product_id'], 'Product Name Missing')
#             item_price_at_purchase = float(item['price_at_purchase'])
#             quantity = int(item['quantity'])
#             discount = float(item['discount_amount'])
            
#             line_total_tax_inclusive = item_price_at_purchase * quantity
#             line_net_total = line_total_tax_inclusive - discount
            
#             taxable_subtotal = line_net_total / TOTAL_TAX_RATE
            
#             gross_sales += line_net_total
            
#             enriched_line_items.append({
#                 'name': product_name, 'quantity': quantity, 'price_at_purchase': item_price_at_purchase,
#                 'discountAmount': discount, 'line_net_total': line_net_total, 'taxable_value': taxable_subtotal
#             })
            
#         taxable_sum = sum(item['taxable_value'] for item in enriched_line_items)

#         order_data['line_items'] = enriched_line_items
#         order_data['calculated_totals'] = {
#             'taxable_value': taxable_sum, 'cgst_amount': taxable_sum * CGST_RATE,
#             'sgst_amount': taxable_sum * SGST_RATE, 'grand_total': gross_sales
#         }

#         # 3. Render HTML Template (PDF Generation)
#         rendered_html = render_template(
#             'bill_template.html', order=order_data, bill_settings=bill_settings, totals=order_data['calculated_totals']
#         )
        
#         if _WEASYPRINT_AVAILABLE and HTML is not None:
#             html = HTML(string=rendered_html)
#             css_path = os.path.join(app.root_path, 'static', 'index.css')
            
#             stylesheets = []
#             if os.path.exists(css_path): stylesheets.append(CSS(filename=css_path))
                
#             pdf_bytes = html.write_pdf(stylesheets=stylesheets)

#             response = make_response(pdf_bytes)
#             response.headers['Content-Type'] = 'application/pdf'
#             response.headers['Content-Disposition'] = f'attachment; filename=invoice-{order_id[:8]}.pdf'
#             return response
#         else:
#             return "PDF generation failed: WeasyPrint not available.", 500

#     except Exception as e:
#         print(f"CRITICAL PDF ROUTE ERROR: {e}")
#         # This catch is now only for unexpected connection/processing errors, not missing data
#         return f"Error: Failed to process order data. Ensure the order ID is valid.", 500
# @app.route("/admin/order/<order_id>/pdf")
# @login_required
# @role_required("admin")
# def generate_order_pdf(order_id):
#     """Generate a downloadable invoice PDF for an order."""
#     try:
#         # 1️⃣ Fetch the order
#         order_response = supabase.table("orders").select("*").eq("id", order_id).execute()
#         if not order_response.data:
#             return "Order not found", 404
#         order_data = order_response.data[0]

#         # 2️⃣ Fetch order items
#         items_response = supabase.table("order_items").select("*").eq("order_id", order_id).execute()
#         order_items = items_response.data if items_response.data else []

#         # 3️⃣ Fetch billing settings dynamically from site_settings
#         settings_response = supabase.table("site_settings").select("content").eq("page_key", "billing_settings").execute()
#         if not settings_response.data:
#             return "Billing settings not found in site_settings", 404

#         bill_settings = settings_response.data[0]["content"]
#         company_name = bill_settings.get("companyName", "RK Construction")
#         company_address = bill_settings.get("companyAddress", "N/A")
#         bank_name = bill_settings.get("bank_name", "State Bank of India")
#         account_number = bill_settings.get("account_number", "1234567890")
#         footer_text = bill_settings.get("footerText", "Thank you for your business!")

#         tax_rate_cgst = float(bill_settings.get("tax_rate_cgst", 0.09))
#         tax_rate_sgst = float(bill_settings.get("tax_rate_sgst", 0.09))

#         # 4️⃣ Normalize item fields
#         def safe_float(val, default=0.0):
#             try:
#                 return float(val)
#             except (ValueError, TypeError):
#                 return default

#         for it in order_items:
#             it["product_name"] = it.get("product_name") or it.get("name") or it.get("product") or "Item"
#             it["price_at_purchase"] = safe_float(it.get("price_at_purchase") or it.get("price", 0))
#             it["discount_amount"] = safe_float(it.get("discount_amount") or it.get("discount", 0))
#             it["quantity"] = safe_float(it.get("quantity", 1))
#             it["line_total"] = safe_float(it.get("line_total", (it["price_at_purchase"] * it["quantity"]) - it["discount_amount"]))

#         order_data["line_items"] = order_items

#         # 5️⃣ Totals using Supabase tax rates
#         from decimal import Decimal, ROUND_HALF_UP

#         subtotal = sum(Decimal(str(it["line_total"])) for it in order_items)
#         taxable_value = subtotal
#         cgst = (taxable_value * Decimal(str(tax_rate_cgst))).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
#         sgst = (taxable_value * Decimal(str(tax_rate_sgst))).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
#         grand_total = (taxable_value + cgst + sgst).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)

#         order_data["calculated_totals"] = {
#             "taxable_value": float(taxable_value),
#             "cgst_amount": float(cgst),
#             "sgst_amount": float(sgst),
#             "grand_total": float(grand_total),
#         }

#         # 6️⃣ Render HTML
#         rendered_html = render_template(
#             "admin_order_invoice.html",
#             order=order_data,
#             bill_settings={
#                 "companyName": company_name,
#                 "companyAddress": company_address,
#                 "bank_name": bank_name,
#                 "account_number": account_number,
#                 "footerText": footer_text
#             },
#             preview_mode=False
#         )

#         # 7️⃣ Try WeasyPrint PDF
#         if _WEASYPRINT_AVAILABLE and HTML is not None:
#             html = HTML(string=rendered_html)
#             css_path = os.path.join(app.root_path, "static", "index.css")
#             stylesheets = [CSS(filename=css_path)] if os.path.exists(css_path) else []
#             pdf_bytes = html.write_pdf(stylesheets=stylesheets)
#             response = make_response(pdf_bytes)
#             response.headers["Content-Type"] = "application/pdf"
#             response.headers["Content-Disposition"] = f"attachment; filename=invoice-{order_id[:8]}.pdf"
#             return response

#         # 8️⃣ ReportLab fallback
#         import io
#         from reportlab.pdfgen import canvas
#         from reportlab.lib.pagesizes import letter

#         buffer = io.BytesIO()
#         c = canvas.Canvas(buffer, pagesize=letter)
#         width, height = letter
#         y = height - 50

#         def line(text, step=14):
#             nonlocal y
#             c.drawString(40, y, text)
#             y -= step

#         c.setFont("Helvetica-Bold", 12)
#         line(f"Invoice: {order_id[:8]}")
#         c.setFont("Helvetica", 10)
#         line(company_name)
#         line(company_address)
#         line("")
#         line(f"Customer: {order_data.get('customer_name', 'N/A')}")
#         line(f"Date: {order_data.get('date', 'N/A')}")
#         line("")

#         c.setFont("Helvetica-Bold", 10)
#         line("Items:")
#         c.setFont("Helvetica", 10)
#         for it in order_items:
#             pname = it["product_name"]
#             qty = it["quantity"]
#             price = it["price_at_purchase"]
#             disc = it["discount_amount"]
#             total = it["line_total"]
#             line(f" - {pname} x{qty:.0f} @ ₹{price:.2f} (-₹{disc:.2f}) = ₹{total:.2f}")
#             if y < 80:
#                 c.showPage()
#                 y = height - 50

#         c.setFont("Helvetica-Bold", 10)
#         line("")
#         line(f"Taxable Value: ₹{taxable_value:.2f}")
#         # line(f"CGST ({tax_rate_cgst*100:.1f}%): ₹{cgst:.2f}")
#         # line(f"SGST ({tax_rate_sgst*100:.1f}%): ₹{sgst:.2f}")
#         line(f"CGST ₹{cgst:.2f}")
#         line(f"SGST ₹{sgst:.2f}")
#         line(f"Grand Total: ₹{grand_total:.2f}")
#         c.setFont("Helvetica", 10)
#         line("")
#         line("Bank Details:")
#         line(f"Bank: {bank_name}")
#         line(f"Account: {account_number}")
#         line("")
#         line(footer_text)

#         c.showPage()
#         c.save()
#         pdf_bytes = buffer.getvalue()
#         buffer.close()

#         response = make_response(pdf_bytes)
#         response.headers["Content-Type"] = "application/pdf"
#         response.headers["Content-Disposition"] = f"attachment; filename=invoice-{order_id[:8]}.pdf"
#         return response

#     except Exception as e:
#         return f"Error generating invoice: {str(e)}", 500


# @app.route("/admin/order/<order_id>/bill")
# @login_required
# @role_required("admin")
# def view_order_bill(order_id):
#     """Preview invoice before downloading PDF."""
#     try:
#         order_response = supabase.table("orders").select("*").eq("id", order_id).execute()
#         if not order_response.data:
#             return "Order not found", 404
#         order_data = order_response.data[0]

#         items_response = supabase.table("order_items").select("*").eq("order_id", order_id).execute()
#         order_items = items_response.data if items_response.data else []
#         order_data["line_items"] = order_items

#         settings_response = supabase.table("site_settings").select("content").eq("page_key", "billing_settings").execute()
#         bill_settings = settings_response.data[0]["content"] if settings_response.data else {}

#         tax_rate_cgst = float(bill_settings.get("tax_rate_cgst", 0.09))
#         tax_rate_sgst = float(bill_settings.get("tax_rate_sgst", 0.09))

#         subtotal = sum(float(it.get("line_total", 0)) for it in order_items)
#         cgst = subtotal * tax_rate_cgst
#         sgst = subtotal * tax_rate_sgst
#         grand_total = subtotal + cgst + sgst
#         order_data["calculated_totals"] = {
#             "taxable_value": subtotal,
#             "cgst_amount": cgst,
#             "sgst_amount": sgst,
#             "grand_total": grand_total,
#         }

#         return render_template("admin_order_invoice.html",
#                                order=order_data,
#                                bill_settings=bill_settings,
#                                preview_mode=True)
#     except Exception as e:
#         return f"Error displaying bill: {str(e)}", 500

def _safe_float(v, default=0.0):
    try:
        return float(v)
    except (TypeError, ValueError):
        return default

def _fetch_billing_settings():
    # site_settings(page_key='billing_settings') -> content (jsonb)
    resp = supabase.table("site_settings").select("content").eq("page_key", "billing_settings").execute()
    content = resp.data[0]["content"] if resp.data else {}
    # Ensure required keys exist
    content.setdefault("companyName", "RK Construction")
    content.setdefault("companyAddress", "N/A")
    content.setdefault("bank_name", "State Bank of India")
    content.setdefault("account_number", "1234567890")
    content.setdefault("footerText", "Thank you for your business!")
    # Percent values as strings or numbers (e.g., "1", 2.0)
    content["tax_rate_cgst"] = _safe_float(content.get("tax_rate_cgst", 0.0))
    content["tax_rate_sgst"] = _safe_float(content.get("tax_rate_sgst", 0.0))
    return content

def _load_order_and_items(order_id: str):
    # Load order
    order_res = supabase.table("orders").select("*").eq("id", order_id).execute()
    if not order_res.data:
        return None, []

    order = order_res.data[0]

    # Try table fetch first
    items = []
    try:
        ir = supabase.table("order_items").select("*").eq("order_id", order_id).execute()
        items = ir.data or []
    except Exception:
        items = []

    # If still empty, try embedded arrays
    if not items:
        embedded = order.get("line_items") or order.get("order_items") or order.get("items") or []
        if isinstance(embedded, list):
            items = embedded

    # Normalize fields
    norm = []
    for it in items:
        price = _safe_float(it.get("price_at_purchase", it.get("price", 0)))
        qty   = _safe_float(it.get("quantity", 0))
        disc  = _safe_float(it.get("discount_amount", it.get("discount", 0)))
        subtotal = _safe_float(it.get("line_total", price * qty - disc))
        norm.append({
            "product_name": it.get("product_name") or it.get("name") or it.get("product") or "Item",
            "price_at_purchase": price,
            "quantity": qty,
            "discount_amount": disc,
            "line_total": subtotal
        })
    return order, norm

def _calc_totals_percent(line_items, cgst_percent: float, sgst_percent: float):
    """
    cgst_percent, sgst_percent are percent values (e.g., 1.0, 2.0, 9.0)
    """
    dec = Decimal
    subtotal = sum(dec(str(i["line_total"])) for i in line_items)
    cgst = (subtotal * dec(str(cgst_percent)) / dec("100")).quantize(dec("0.01"), rounding=ROUND_HALF_UP)
    sgst = (subtotal * dec(str(sgst_percent)) / dec("100")).quantize(dec("0.01"), rounding=ROUND_HALF_UP)
    grand_total = (subtotal + cgst + sgst).quantize(dec("0.01"), rounding=ROUND_HALF_UP)
    return float(subtotal), float(cgst), float(sgst), float(grand_total)

@app.route("/admin/order/<order_id>/bill")
@login_required
@role_required("admin")
def view_order_bill(order_id):
    """HTML preview before download."""
    try:
        order, items = _load_order_and_items(order_id)
        if not order:
            return "Order not found", 404

        bill = _fetch_billing_settings()

        taxable, cgst, sgst, grand = _calc_totals_percent(
            items, bill["tax_rate_cgst"], bill["tax_rate_sgst"]
        )

        order["line_items"] = items
        order["calculated_totals"] = {
            "taxable_value": taxable,
            "cgst_amount": cgst,
            "sgst_amount": sgst,
            "grand_total": grand,
        }

        return render_template(
            "admin_order_invoice.html",
            order=order,
            bill_settings=bill,
            preview_mode=True
        )
    except Exception as e:
        return f"Error displaying bill: {e}", 500

@app.route("/admin/order/<order_id>/pdf")
@login_required
@role_required("admin")
def generate_order_pdf(order_id):
    """Generate a clean black-and-white invoice PDF (WeasyPrint first, ReportLab fallback)."""
    try:
        # 1️⃣ Load order and items
        order, items = _load_order_and_items(order_id)
        if not order:
            return "Order not found", 404

        # 2️⃣ Fetch billing settings (includes GST rates)
        bill = _fetch_billing_settings()

        # 3️⃣ Calculate totals using percent-based GST
        taxable, cgst, sgst, grand = _calc_totals_percent(
            items, bill["tax_rate_cgst"], bill["tax_rate_sgst"]
        )

        order["line_items"] = items
        order["calculated_totals"] = {
            "taxable_value": taxable,
            "cgst_amount": cgst,
            "sgst_amount": sgst,
            "grand_total": grand,
        }

        # 4️⃣ Render HTML invoice
        rendered_html = render_template(
            "admin_order_invoice.html",
            order=order,
            bill_settings=bill,
            preview_mode=False
        )

        # 5️⃣ Try WeasyPrint first — import safely
        try:
            from weasyprint import HTML, CSS

            # ✅ Force white background and black text
            force_white_css = CSS(string="""
                @page { background: #ffffff; color: #000000; }
                html, body {
                    background: #ffffff !important;
                    color: #000000 !important;
                    font-family: Arial, sans-serif;
                    margin: 25px;
                }
                * {
                    background: #ffffff !important;
                    color: #000000 !important;
                    border-color: #000000 !important;
                    box-shadow: none !important;
                }
                th {
                    background: #f2f2f2 !important;
                }
                a, .btn, .btn-download {
                    background: #000000 !important;
                    color: #ffffff !important;
                }
            """)

            # ✅ Generate PDF (ignore Tailwind/global CSS)
            pdf_bytes = HTML(string=rendered_html).write_pdf(stylesheets=[force_white_css])

            response = make_response(pdf_bytes)
            response.headers["Content-Type"] = "application/pdf"
            response.headers["Content-Disposition"] = f"attachment; filename=invoice-{order_id[:8]}.pdf"
            return response

        except ImportError:
            # Fall back to ReportLab if WeasyPrint not available
            pass

        # 6️⃣ ReportLab fallback (if WeasyPrint import failed)
        import io
        from reportlab.pdfgen import canvas
        from reportlab.lib.pagesizes import letter

        buf = io.BytesIO()
        c = canvas.Canvas(buf, pagesize=letter)
        width, height = letter
        y = height - 50

        def line(text, step=14):
            nonlocal y
            c.drawString(40, y, str(text))
            y -= step

        # Header
        c.setFont("Helvetica-Bold", 12)
        line(f"Invoice: {order_id[:8]}")
        c.setFont("Helvetica", 10)
        line(bill["companyName"])
        line(bill["companyAddress"])
        line("")
        line(f"Customer: {order.get('customer_name', 'N/A')}")
        line(f"Date: {order.get('date', 'N/A')}")
        line("")

        # Items
        c.setFont("Helvetica-Bold", 10)
        line("Items:")
        c.setFont("Helvetica", 10)
        for it in items:
            line(f" - {it['product_name']} x{int(it['quantity'])} @ ₹{it['price_at_purchase']:.2f} "
                 f"(-₹{it['discount_amount']:.2f}) = ₹{it['line_total']:.2f}")
            if y < 80:
                c.showPage()
                y = height - 50

        # Totals
        c.setFont("Helvetica-Bold", 10)
        line("")
        line(f"Taxable Value: ₹{taxable:.2f}")
        line(f"CGST ({bill['tax_rate_cgst']:.2f}%): ₹{cgst:.2f}")
        line(f"SGST ({bill['tax_rate_sgst']:.2f}%): ₹{sgst:.2f}")
        line(f"Grand Total: ₹{grand:.2f}")

        # Footer
        c.setFont("Helvetica", 10)
        line("")
        line("Bank Details:")
        line(f"Bank: {bill['bank_name']}")
        line(f"Account: {bill['account_number']}")
        line(bill["footerText"])

        c.showPage()
        c.save()

        pdf_data = buf.getvalue()
        buf.close()

        resp = make_response(pdf_data)
        resp.headers["Content-Type"] = "application/pdf"
        resp.headers["Content-Disposition"] = f"attachment; filename=invoice-{order_id[:8]}.pdf"
        return resp

    except Exception as e:
        return f"Error generating invoice: {e}", 500


@app.route('/admin/site_settings', methods=['GET', 'POST'])
@login_required
@role_required('admin')
def admin_site_settings():
    """Allows admin to edit all content on the About Us page."""
    
    PAGE_KEY = 'shop_settings'
    
    if request.method == 'POST':
        # 1. Gather all updated content into a single JSON object
        updated_content = {
            "shop_welcome_text": request.form.get('shop_welcome_text'),
            "global_font": request.form.get('global_font'),
        }
        
        try:
            # 2. Update the 'content' column in the site_settings table
            supabase.table('site_settings').upsert({'page_key': PAGE_KEY, 'content': updated_content}, on_conflict='page_key').execute()
            
            flash("About Us content updated successfully!", 'success')
            return redirect(url_for('admin_site_settings'))
            
        except Exception as e:
            print(f"About Us Update Error: {e}")
            flash(f"Failed to update About Us content. Error: {e}", 'error')

    # GET Request: Fetch current settings for the form
    try:
        settings_res = supabase.table('site_settings').select('content').eq('page_key', PAGE_KEY).single().execute()
        current_settings = settings_res.data['content']
    except Exception:
        current_settings = DEFAULT_SHOP_SETTINGS
        
    return render_template('admin_site_settings.html', settings=current_settings)


@app.route('/admin/products/edit/<product_id>', methods=['GET', 'POST'])
@login_required
@role_required('admin')
def admin_edit_product(product_id):
    """Handles displaying and processing the form to edit an existing product."""
    
    # 1. Fetch current product data
    try:
        product_res = supabase.table('products').select('*').eq('id', product_id).single().execute()
        product = product_res.data
    except Exception:
        flash("Product not found.", 'error')
        return redirect(url_for('admin_products'))

    if request.method == 'POST':
        try:
            # 2. Gather updated data
            name = request.form.get('name')
            category = request.form.get('category')
            price = float(request.form.get('price'))
            stock = int(request.form.get('stock'))
            description = request.form.get('description')
            image_url_input = request.form.get('image_url')
            
            # 3. Update the record in Supabase
            supabase.table('products').update({
                'name': name,
                'category': category,
                'price': price,
                'stock': stock,
                'description': description,
                'imageUrl': image_url_input, # Use correct casing
            }).eq('id', product_id).execute()
            
            flash(f"Product '{name}' updated successfully!", 'success')
            return redirect(url_for('admin_products'))
        
        except Exception as e:
            print(f"Product Update Error: {e}")
            flash(f"Failed to update product. Error: {e}", 'error')
            # Re-fetch data to display current state in form if submission failed
            product_res = supabase.table('products').select('*').eq('id', product_id).single().execute()
            product = product_res.data
            
    # GET request: Display the pre-filled edit form
    return render_template('admin_edit_product.html', product=product)

@app.route('/admin/products/delete/<product_id>', methods=['POST'])
@login_required
@role_required('admin')
def admin_delete_product(product_id):
    """Deletes a product and redirects to the product list."""
    try:
        # Delete product from the 'products' table
        supabase.table('products').delete().eq('id', product_id).execute()
        flash("Product deleted successfully!", 'success')
    except Exception as e:
        print(f"Product Delete Error: {e}")
        flash("Failed to delete product.", 'error')

    return redirect(url_for('admin_products'))

# -----------------------------------------
#  CUSTOM BILLING DASHBOARD SECTION
# -----------------------------------------
@app.route("/admin/custom-bills")
@login_required
@role_required("admin")
def admin_custom_bills():
    """Display all custom billing records for the admin dashboard."""
    try:
        result = supabase.table("custom_billing_data").select("*").order("last_updated", desc=True).execute()
        records = result.data or []
        return render_template("admin_custom_bills.html", records=records)  # ✅ use base.html inside
    except Exception as e:
        return f"Error fetching records: {str(e)}", 500


@app.route("/admin/custom-bills/add", methods=["POST"])
@login_required
@role_required("admin")
def admin_custom_bill_add():
    """Add new custom billing entry."""
    try:
        form = request.form
        data = {
            "person_name": form.get("person_name"),
            "phone_number": form.get("phone_number"),
            "address": form.get("address"),
            "amount_pending": float(form.get("amount_pending") or 0),
            "short_note": form.get("short_note"),
        }
        supabase.table("custom_billing_data").insert(data).execute()
        flash("New record added successfully!", "success")
        return redirect(url_for("admin_custom_bills"))
    except Exception as e:
        flash(f"Error adding record: {str(e)}", "danger")
        return redirect(url_for("admin_custom_bills"))


@app.route("/admin/custom-bills/update/<uuid:record_id>", methods=["POST"])
@login_required
@role_required("admin")
def admin_custom_bill_update(record_id):
    """Edit existing custom billing entry inline."""
    try:
        form = request.form
        data = {
            "person_name": form.get("person_name"),
            "phone_number": form.get("phone_number"),
            "address": form.get("address"),
            "amount_pending": float(form.get("amount_pending") or 0),
            "short_note": form.get("short_note"),
        }
        supabase.table("custom_billing_data").update(data).eq("id", str(record_id)).execute()
        flash("Record updated successfully!", "success")
        return redirect(url_for("admin_custom_bills"))
    except Exception as e:
        flash(f"Error updating record: {str(e)}", "danger")
        return redirect(url_for("admin_custom_bills"))
        
        
@app.route('/admin/about_us', methods=['GET', 'POST'])
@login_required
@role_required('admin')
def admin_about_us():
    """Allows admin to edit all content on the About Us page."""
    
    PAGE_KEY = 'about_us_content'
    
    if request.method == 'POST':
        # 1. Gather all updated content into a single JSON object
        updated_content = {
            "intro_text": request.form.get('intro_text'),
            "image_url_1": request.form.get('image_url_1'),
            "image_url_2": request.form.get('image_url_2'),
            "image_url_3": request.form.get('image_url_3'),
            "body_text": request.form.get('body_text'),
            "map_url": request.form.get('map_url'),
        }
        
        try:
            # 2. Update the 'content' column in the site_settings table
            supabase.table('site_settings').upsert({'page_key': PAGE_KEY, 'content': updated_content}, on_conflict='page_key').execute()
            
            flash("About Us content updated successfully!", 'success')
            return redirect(url_for('admin_about_us'))
            
        except Exception as e:
            print(f"About Us Update Error: {e}")
            flash(f"Failed to update About Us content. Error: {e}", 'error')

    # GET Request: Fetch current settings for the form
    try:
        settings_res = supabase.table('site_settings').select('content').eq('page_key', PAGE_KEY).single().execute()
        current_settings = settings_res.data['content']
    except Exception:
        current_settings = ABOUT_US_PAGE_DATA
        
    return render_template('admin_about_us.html', settings=current_settings)

# --- Update Public View Route (/about) ---
@app.route('/about')
def about():
    # Fetch content from the new site_settings table
    try:
        settings_res = supabase.table('site_settings').select('content').eq('page_key', 'about_us_content').single().execute()
        # The content is a JSON object stored in the 'content' column
        page_data = settings_res.data['content']
    except Exception:
        # Fallback if the database call fails
        page_data = {"intro_text": "Content loading error.", "map_url": "Default Address"}
        
    return render_template('about.html', page_data=page_data)

if __name__ == '__main__':
    app.run(debug=True, port=8000)