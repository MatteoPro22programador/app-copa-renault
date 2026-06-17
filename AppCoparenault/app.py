from flask import Flask, render_template, request, redirect, session, jsonify
from flask_sqlalchemy import SQLAlchemy
from flask_mail import Mail, Message
from datetime import datetime
import random
import os
import mercadopago

app = Flask(__name__)

# -----------------------------
# CONFIG
# -----------------------------

app.config['SECRET_KEY'] = 'coparenault'

app.config['SQLALCHEMY_DATABASE_URI'] = 'mysql+pymysql://root:MatteoCasal2009@localhost:3306/coparenault'

# GMAIL
app.config['MAIL_SERVER'] = 'smtp.gmail.com'
app.config['MAIL_PORT'] = 587
app.config['MAIL_USE_TLS'] = True
app.config['MAIL_USERNAME'] = 'matteoagustincasals@gmail.com'
app.config['MAIL_PASSWORD'] = 'xggrgqvjdthxvmoc'

# MERCADO PAGO (implementar)
# Reemplazá esto con tu Access Token de https://www.mercadopago.com.ar/developers
#app.config['MP_ACCESS_TOKEN'] = 'TU_ACCESS_TOKEN_DE_MP_ACA'

# CARPETA UPLOADS (para imágenes de productos)
app.config['UPLOAD_FOLDER'] = os.path.join('static', 'uploads')
os.makedirs(app.config['UPLOAD_FOLDER'], exist_ok=True)

ALLOWED_EXTENSIONS = {'png', 'jpg', 'jpeg', 'webp'}

# -----------------------------
# DB Y MAIL
# -----------------------------

db = SQLAlchemy(app)
mail = Mail(app)

# -----------------------------
# MODELOS
# -----------------------------

class Usuario(db.Model):
    id       = db.Column(db.Integer, primary_key=True)
    nombre   = db.Column(db.String(100))
    email    = db.Column(db.String(100))
    password = db.Column(db.String(100))
    admin    = db.Column(db.Boolean, default=False)


class Partido(db.Model):
    id       = db.Column(db.Integer, primary_key=True)
    deporte  = db.Column(db.String(100))
    equipo1  = db.Column(db.String(100))
    equipo2  = db.Column(db.String(100))
    puntos1  = db.Column(db.Integer, default=0)
    puntos2  = db.Column(db.Integer, default=0)
    fecha    = db.Column(db.DateTime)


class SeccionCantina(db.Model):

    id     = db.Column(db.Integer, primary_key=True)
    nombre = db.Column(db.String(100), nullable=False)
    icono  = db.Column(db.String(10), default='🍽️')
    orden  = db.Column(db.Integer, default=0)

    productos = db.relationship('Producto', backref='seccion', lazy=True)


class Producto(db.Model):
    id          = db.Column(db.Integer, primary_key=True)
    nombre      = db.Column(db.String(150), nullable=False)
    descripcion = db.Column(db.String(300))
    precio      = db.Column(db.Float, nullable=False)
    stock       = db.Column(db.Integer, default=0)
    imagen      = db.Column(db.String(200))          # nombre del archivo
    activo      = db.Column(db.Boolean, default=True)
    seccion_id  = db.Column(db.Integer, db.ForeignKey('seccion_cantina.id'))


class Pedido(db.Model):
    """Un pedido completo de un usuario."""
    id           = db.Column(db.Integer, primary_key=True)
    usuario_id   = db.Column(db.Integer, db.ForeignKey('usuario.id'))
    fecha        = db.Column(db.DateTime, default=datetime.utcnow)
    total        = db.Column(db.Float)
    estado       = db.Column(db.String(50), default='pendiente')
    # pendiente | pagado | cancelado
    mp_id        = db.Column(db.String(200))          # ID de pago de MP
    codigo_retiro = db.Column(db.String(10))           # código para mostrar en cantina

    usuario  = db.relationship('Usuario', backref='pedidos')
    items    = db.relationship('PedidoItem', backref='pedido', lazy=True)


class PedidoItem(db.Model):
    id          = db.Column(db.Integer, primary_key=True)
    pedido_id   = db.Column(db.Integer, db.ForeignKey('pedido.id'))
    producto_id = db.Column(db.Integer, db.ForeignKey('producto.id'))
    cantidad    = db.Column(db.Integer)
    precio_unit = db.Column(db.Float)

    producto = db.relationship('Producto')


# -----------------------------
# CREAR TABLAS
# -----------------------------

with app.app_context():
    db.create_all()

# -----------------------------
# HELPERS
# -----------------------------

def allowed_file(filename):
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in ALLOWED_EXTENSIONS

def get_admin():
    """Devuelve True si el usuario en sesión es admin."""
    if 'usuario' not in session:
        return False
    u = Usuario.query.filter_by(nombre=session['usuario']).first()
    return u and u.admin

def usuario_actual():
    if 'usuario' not in session:
        return None
    return Usuario.query.filter_by(nombre=session['usuario']).first()

def generar_codigo():
    return str(random.randint(10000, 99999))

# -----------------------------
# INICIO
# -----------------------------

@app.route('/')
def inicio():
    return render_template('index.html', usuario_admin=get_admin())

# -----------------------------
# FIXTURE
# -----------------------------

@app.route('/fixture')
def fixture():

    # Parámetros que vienen de la URL: ?buscar=...&deporte=...
    buscar  = request.args.get('buscar', '').strip()
    deporte = request.args.get('deporte', '').strip()

    query = Partido.query

    # FILTRO POR DEPORTE (Fútbol / Vóley / Básquet)
    if deporte:
        query = query.filter(Partido.deporte == deporte)

    # BÚSQUEDA POR NOMBRE DE COLEGIO (equipo1 o equipo2)
    if buscar:
        query = query.filter(
            db.or_(
                Partido.equipo1.ilike(f'%{buscar}%'),
                Partido.equipo2.ilike(f'%{buscar}%')
            )
        )

    partidos = query.order_by(Partido.fecha).all()

    return render_template(
        'fixture.html',
        partidos=partidos,
        admin=get_admin(),
        buscar=buscar,
        deporte_activo=deporte
    )

@app.route('/crear_partido', methods=['GET', 'POST'])
def crear_partido():
    if not get_admin():
        return redirect('/login')
    if request.method == 'POST':
        nuevo = Partido(
            deporte=request.form['deporte'],
            equipo1=request.form['equipo1'],
            equipo2=request.form['equipo2'],
            puntos1=request.form['puntos1'],
            puntos2=request.form['puntos2'],
            fecha=datetime.strptime(request.form['fecha'], '%Y-%m-%dT%H:%M')
        )
        db.session.add(nuevo)
        db.session.commit()
        return redirect('/fixture')
    return render_template('crear_partido.html')

@app.route('/editar_partido/<int:id>', methods=['GET', 'POST'])
def editar_partido(id):
    if not get_admin():
        return redirect('/login')
    partido = Partido.query.get_or_404(id)
    if request.method == 'POST':
        partido.deporte = request.form['deporte']
        partido.equipo1 = request.form['equipo1']
        partido.equipo2 = request.form['equipo2']
        partido.puntos1 = request.form['puntos1']
        partido.puntos2 = request.form['puntos2']
        partido.fecha   = datetime.strptime(request.form['fecha'], '%Y-%m-%dT%H:%M')
        db.session.commit()
        return redirect('/fixture')
    return render_template('editar_partido.html', partido=partido)

@app.route('/eliminar_partido/<int:id>')
def eliminar_partido(id):

    if not get_admin():
        return redirect('/login')

    partido = Partido.query.get_or_404(id)

    db.session.delete(partido)
    db.session.commit()

    return redirect('/fixture')
# -----------------------------
# CANTINA PÚBLICA
# -----------------------------

@app.route('/cantina')
def cantina():
    secciones = SeccionCantina.query.order_by(SeccionCantina.orden).all()
    productos  = Producto.query.filter_by(activo=True).all()
    return render_template('cantina.html', secciones=secciones, productos=productos)

# -----------------------------
# CANTINA - CREAR PAGO (MP)
# -----------------------------

@app.route('/cantina/crear_pago', methods=['POST'])
def crear_pago():
    if 'usuario' not in session:
        return jsonify({'error': 'No estás logueado'}), 401

    data  = request.get_json()
    items_req = data.get('items', [])

    if not items_req:
        return jsonify({'error': 'Carrito vacío'}), 400

    usuario = usuario_actual()
    total   = 0
    items_mp = []
    pedido_items = []

    for item in items_req:
        prod = Producto.query.get(item['id'])
        if not prod or not prod.activo:
            continue
        cantidad = int(item['cantidad'])
        if prod.stock < cantidad:
            return jsonify({'error': f'Stock insuficiente para {prod.nombre}'}), 400

        total += prod.precio * cantidad
        items_mp.append({
            'id': str(prod.id),
            'title': prod.nombre,
            'quantity': cantidad,
            'unit_price': float(prod.precio),
            'currency_id': 'ARS'
        })
        pedido_items.append({'producto': prod, 'cantidad': cantidad})

    # Crear pedido en DB
    codigo = generar_codigo()
    pedido = Pedido(
        usuario_id=usuario.id,
        total=total,
        estado='pendiente',
        codigo_retiro=codigo
    )
    db.session.add(pedido)
    db.session.flush()  # para tener pedido.id

    for pi in pedido_items:
        db.session.add(PedidoItem(
            pedido_id=pedido.id,
            producto_id=pi['producto'].id,
            cantidad=pi['cantidad'],
            precio_unit=pi['producto'].precio
        ))

    db.session.commit()

    # Crear preferencia en Mercado Pago
    sdk = mercadopago.SDK(app.config['MP_ACCESS_TOKEN'])

    preference_data = {
        'items': items_mp,
        'back_urls': {
            'success': f'https://TU_DOMINIO.com/cantina/pago_exitoso/{pedido.id}',
            'failure': f'https://TU_DOMINIO.com/cantina/pago_fallido/{pedido.id}',
            'pending': f'https://TU_DOMINIO.com/cantina/pago_pendiente/{pedido.id}'
        },
        'auto_return': 'approved',
        'external_reference': str(pedido.id),
        'notification_url': 'https://TU_DOMINIO.com/cantina/webhook_mp',
        'statement_descriptor': 'Copa Renault'
    }

    preference = sdk.preference().create(preference_data)

    if preference['status'] == 201:
        return jsonify({'init_point': preference['response']['init_point']})
    else:
        db.session.delete(pedido)
        db.session.commit()
        return jsonify({'error': 'Error al crear preferencia MP'}), 500

# -----------------------------
# CANTINA - CALLBACKS MP
# -----------------------------

# @app.route('/cantina/pago_exitoso/<int:pedido_id>')
# def pago_exitoso(pedido_id):
#     pedido = Pedido.query.get_or_404(pedido_id)

#     # Verificar que sea del usuario logueado
#     usuario = usuario_actual()
#     if not usuario or pedido.usuario_id != usuario.id:
#         return redirect('/')

#     # Marcar como pagado y descontar stock
#     if pedido.estado == 'pendiente':
#         pedido.estado = 'pagado'
#         for item in pedido.items:
#             item.producto.stock -= item.cantidad
#         db.session.commit()

#         # Enviar recibo por email
#         _enviar_recibo(pedido, usuario)

#     return render_template('recibo.html', pedido=pedido, usuario=usuario)


# @app.route('/cantina/pago_fallido/<int:pedido_id>')
# def pago_fallido(pedido_id):
#     pedido = Pedido.query.get_or_404(pedido_id)
#     pedido.estado = 'cancelado'
#     db.session.commit()
#     return render_template('pago_fallido.html')


# @app.route('/cantina/pago_pendiente/<int:pedido_id>')
# def pago_pendiente(pedido_id):
#     return render_template('pago_pendiente.html')


# @app.route('/cantina/webhook_mp', methods=['POST'])
# def webhook_mp():
#     """MP notifica acá cuando cambia el estado de un pago."""
#     data = request.get_json()
#     if data and data.get('type') == 'payment':
#         payment_id = data['data']['id']
#         sdk = mercadopago.SDK(app.config['MP_ACCESS_TOKEN'])
#         payment = sdk.payment().get(payment_id)

#         if payment['status'] == 200:
#             pago = payment['response']
#             pedido_id = pago.get('external_reference')
#             estado_mp = pago.get('status')  # approved, rejected, pending

#             if pedido_id:
#                 pedido = Pedido.query.get(int(pedido_id))
#                 if pedido and pedido.estado == 'pendiente':
#                     if estado_mp == 'approved':
#                         pedido.estado = 'pagado'
#                         pedido.mp_id  = str(payment_id)
#                         for item in pedido.items:
#                             item.producto.stock -= item.cantidad
#                         db.session.commit()
#                     elif estado_mp == 'rejected':
#                         pedido.estado = 'cancelado'
#                         db.session.commit()

#     return '', 200

# -----------------------------
# CANTINA - MIS PEDIDOS
# -----------------------------

@app.route('/mis_pedidos')
def mis_pedidos():
    if 'usuario' not in session:
        return redirect('/login')
    usuario = usuario_actual()
    pedidos = Pedido.query.filter_by(usuario_id=usuario.id).order_by(Pedido.fecha.desc()).all()
    return render_template('mis_pedidos.html', pedidos=pedidos)

# -----------------------------
# ADMIN CANTINA
# -----------------------------

@app.route('/cantina_admin')
def cantina_admin():
    if not get_admin():
        return redirect('/login')
    secciones = SeccionCantina.query.order_by(SeccionCantina.orden).all()
    productos  = Producto.query.all()
    pedidos_hoy = Pedido.query.filter(
        Pedido.fecha >= datetime.utcnow().replace(hour=0, minute=0, second=0)
    ).all()
    return render_template('cantina_admin.html',
                           secciones=secciones,
                           productos=productos,
                           pedidos_hoy=pedidos_hoy)


# SECCIONES -------

@app.route('/cantina_admin/crear_seccion', methods=['POST'])
def crear_seccion():
    if not get_admin(): return redirect('/login')
    s = SeccionCantina(
        nombre=request.form['nombre'],
        icono=request.form.get('icono', '/static/assets/cantina_tc.png'),
        orden=int(request.form.get('orden', 0))
    )
    db.session.add(s)
    db.session.commit()
    return redirect('/cantina_admin')

@app.route('/cantina_admin/eliminar_seccion/<int:id>')
def eliminar_seccion(id):
    if not get_admin(): return redirect('/login')
    s = SeccionCantina.query.get_or_404(id)
    db.session.delete(s)
    db.session.commit()
    return redirect('/cantina_admin')


# PRODUCTOS -------

@app.route('/cantina_admin/crear_producto', methods=['GET', 'POST'])
def crear_producto():
    if not get_admin(): return redirect('/login')
    secciones = SeccionCantina.query.all()

    if request.method == 'POST':
        imagen_nombre = None

        if 'imagen' in request.files:
            f = request.files['imagen']
            if f and f.filename and allowed_file(f.filename):
                ext = f.filename.rsplit('.', 1)[1].lower()
                imagen_nombre = f'prod_{random.randint(100000,999999)}.{ext}'
                f.save(os.path.join(app.config['UPLOAD_FOLDER'], imagen_nombre))

        p = Producto(
            nombre=request.form['nombre'],
            descripcion=request.form.get('descripcion', ''),
            precio=float(request.form['precio']),
            stock=int(request.form.get('stock', 0)),
            imagen=imagen_nombre,
            activo='activo' in request.form,
            seccion_id=int(request.form['seccion_id'])
        )
        db.session.add(p)
        db.session.commit()
        return redirect('/cantina_admin')

    return render_template('crear_producto.html', secciones=secciones)


@app.route('/cantina_admin/editar_producto/<int:id>', methods=['GET', 'POST'])
def editar_producto(id):
    if not get_admin(): return redirect('/login')
    prod      = Producto.query.get_or_404(id)
    secciones = SeccionCantina.query.all()

    if request.method == 'POST':
        prod.nombre      = request.form['nombre']
        prod.descripcion = request.form.get('descripcion', '')
        prod.precio      = float(request.form['precio'])
        prod.stock       = int(request.form.get('stock', 0))
        prod.activo      = 'activo' in request.form
        prod.seccion_id  = int(request.form['seccion_id'])

        if 'imagen' in request.files:
            f = request.files['imagen']
            if f and f.filename and allowed_file(f.filename):
                # Borrar imagen vieja
                if prod.imagen:
                    ruta_vieja = os.path.join(app.config['UPLOAD_FOLDER'], prod.imagen)
                    if os.path.exists(ruta_vieja):
                        os.remove(ruta_vieja)
                ext = f.filename.rsplit('.', 1)[1].lower()
                nuevo_nombre = f'prod_{random.randint(100000,999999)}.{ext}'
                f.save(os.path.join(app.config['UPLOAD_FOLDER'], nuevo_nombre))
                prod.imagen = nuevo_nombre

        db.session.commit()
        return redirect('/cantina_admin')

    return render_template('editar_producto.html', prod=prod, secciones=secciones)


@app.route('/cantina_admin/eliminar_producto/<int:id>')
def eliminar_producto(id):
    if not get_admin(): return redirect('/login')
    prod = Producto.query.get_or_404(id)
    if prod.imagen:
        ruta = os.path.join(app.config['UPLOAD_FOLDER'], prod.imagen)
        if os.path.exists(ruta):
            os.remove(ruta)
    db.session.delete(prod)
    db.session.commit()
    return redirect('/cantina_admin')


@app.route('/cantina_admin/ajustar_stock/<int:id>', methods=['POST'])
def ajustar_stock(id):
    """Sumar o restar stock manualmente."""
    if not get_admin(): return redirect('/login')
    prod = Producto.query.get_or_404(id)
    delta = int(request.form.get('delta', 0))
    prod.stock = max(0, prod.stock + delta)
    db.session.commit()
    return redirect('/cantina_admin')


# PEDIDOS DEL DÍA -------

@app.route('/cantina_admin/pedidos')
def admin_pedidos():
    if not get_admin(): return redirect('/login')
    pedidos = Pedido.query.order_by(Pedido.fecha.desc()).all()
    return render_template('admin_pedidos.html', pedidos=pedidos)


@app.route('/cantina_admin/marcar_entregado/<int:id>')
def marcar_entregado(id):
    if not get_admin(): return redirect('/login')
    p = Pedido.query.get_or_404(id)
    p.estado = 'entregado'
    db.session.commit()
    return redirect('/cantina_admin/pedidos')

# -----------------------------
# HELPER EMAIL RECIBO
# -----------------------------

# def _enviar_recibo(pedido, usuario):
#     try:
#         items_txt = '\n'.join([
#             f"  {pi.cantidad}x {pi.producto.nombre}  ${pi.precio_unit * pi.cantidad:.0f}"
#             for pi in pedido.items
#         ])
#         msg = Message(
#             subject='✅ Pedido confirmado – Copa Renault',
#             sender=app.config['MAIL_USERNAME'],
#             recipients=[usuario.email]
#         )
#         msg.body = f"""
# Hola {usuario.nombre}!

# Tu pedido fue pagado. Mostrá este código en la cantina para retirarlo:



# Detalle:
# {items_txt}

# Total: ${pedido.total:.0f}

# ¡Disfrutalo!
# Copa Renault
# """
#         mail.send(msg)
#     except Exception as e:
#         print(f'Error enviando recibo: {e}')

# -----------------------------
# LOGIN / LOGOUT / REGISTER
# -----------------------------

@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        usuario = Usuario.query.filter_by(
            email=request.form['email'],
            password=request.form['password']
        ).first()
        if usuario:
            session['usuario'] = usuario.nombre
            return redirect('/')
        return 'Correo o contraseña incorrectos'
    return render_template('login.html')

@app.route('/logout')
def logout():
    session.pop('usuario', None)
    return redirect('/')

@app.route('/register', methods=['GET', 'POST'])
def register():
    if request.method == 'POST':
        codigo = random.randint(100000, 999999)
        session['codigo']   = str(codigo)
        session['nombre']   = request.form['nombre']
        session['email']    = request.form['email']
        session['password'] = request.form['password']

        msg = Message('Código de verificación',
                      sender=app.config['MAIL_USERNAME'],
                      recipients=[request.form['email']])
        msg.body = f'Tu código de verificación es: {codigo}'
        mail.send(msg)
        return redirect('/verificar')
    return render_template('register.html')

@app.route('/verificar', methods=['GET', 'POST'])
def verificar():
    if request.method == 'POST':
        if request.form['codigo'] == session.get('codigo'):
            u = Usuario(
                nombre=session['nombre'],
                email=session['email'],
                password=session['password']
            )
            db.session.add(u)
            db.session.commit()
            return redirect('/login')
        return 'Código incorrecto'
    return render_template('verificar.html')

# -----------------------------
# OTRAS PÁGINAS
# -----------------------------

@app.route('/sponsors')
def sponsors():
    return render_template('sponsors.html')

@app.route('/admin')
def admin():
    if not get_admin():
        return redirect('/login')
    return render_template('admin.html')

#----------------------------------------
# CREAR SECCION
#----------------------------------------
@app.route('/crear_secciones_test')
def crear_secciones_test():

    comidas = SeccionCantina(
        nombre='Comidas',
        icono='🍔'
    )

    bebidas = SeccionCantina(
        nombre='Bebidas',
        icono='/static/assets/refresco.png'
    )

    snacks = SeccionCantina(
        nombre='Snacks',
        icono='🍟'
    )

    db.session.add(comidas)
    db.session.add(bebidas)
    db.session.add(snacks)

    db.session.commit()

    return "Secciones creadas"
# -----------------------------
# RUN
# -----------------------------

if __name__ == '__main__':
    app.run(debug=True)