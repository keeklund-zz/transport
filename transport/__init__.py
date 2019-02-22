from datetime import datetime
from itertools import permutations
from os.path import abspath, dirname, join
from uuid import uuid4
from flask import abort, flash, Flask, jsonify, make_response, redirect, render_template, request, session, url_for
from flask.ext.sqlalchemy import SQLAlchemy
from flask.ext.wtf import Form
from requests import get, post
from werkzeug.security import check_password_hash, generate_password_hash
from wtforms import TextField, validators

# configurations
basedir = abspath(dirname(__file__))
SQLALCHEMY_DATABASE_URI = ''.join(['sqlite:///', join(basedir, '../../data/transport.db')])

TRACSEQ_API_BASE = ''

app = Flask(__name__)

app.secret_key = ""
app.config['SQLALCHEMY_DATABASE_URI'] = SQLALCHEMY_DATABASE_URI

db = SQLAlchemy(app)

# DATABASE
class Users(db.Model):
    """

    """
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(120), unique=True)
    onyen = db.Column(db.String(10), unique=True, nullable=False)
    email = db.Column(db.String(120), unique=True, nullable=False)
    timestamp = db.Column(db.DateTime)

    def __init__(self, name, onyen, email):
        self.name = name
        self.onyen = onyen
        self.email = email
        self.timestamp = datetime.now()
    
    
class Devices(db.Model):
    """

    """
    id = db.Column(db.Integer, primary_key=True)
    device_id = db.Column(db.String(120), unique=True, nullable=False)
    user = db.relationship('Users', backref=db.backref('device', lazy='dynamic'))
    user_id = db.Column(db.Integer, db.ForeignKey('users.id'))
    timestamp = db.Column(db.DateTime)

    def __init__(self, device_id, user):
        self.device_id = device_id
        self.user = user 
        self.timestamp = datetime.now()

        
class Admin(db.Model):
    """

    """
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(120), unique=True, nullable=False)
    password = db.Column(db.String(120), nullable=False)

    def __init__(self, name, password):
        self.name = name
        self.password = generate_password_hash(password)
        
    def check_password(self, password):
        return check_password_hash(self.password, password)

    
# FORMS
class UserForm(Form):
    name = TextField('name', [validators.Length(max=120), validators.Required()])
    onyen = TextField('onyen', [validators.Length(max=10), validators.Required()])
    email = TextField('email', [validators.Email(), validators.Length(max=120), validators.Required()])
    

class LogInForm(Form):
    name = TextField('name', [validators.Required(),])
    password = TextField('password', [validators.Required(),])

    
# VIEWS
@app.errorhandler(401)
def unauthorized(error):
    flash("This user's device isn't registered!")
    flash("Please contact <a href='mailto:keklund@ad.unc.edu?Subject=Transport%20Registration'>Karl Eklund</a> to register your device!")
    return render_template('401.html', form=UserForm()), 401 #, {'WWW-Authenticate': 'Basic realm="Login Required"'}

# do we need a 403 - forbidden?

@app.errorhandler(404)
def page_not_found(error):
    flash("Sorry, this page doesn't exist, or is under development")
    return render_template('404.html'), 404

@app.errorhandler(500)
def unauthorized(error):
    flash("Sorry about this, but there was an error!")
    flash("Please try again, or contact a developer.")
    return render_template('500.html'), 500 #, {'WWW-Authenticate': 'Basic realm="Login Required"'}

@app.before_request
def get_user():
    if not request.endpoint in ('add_device', 'login'):
        onyen = request.cookies.get('onyen')
        device_id = request.cookies.get('device_id')
        if not onyen and not device_id:
            abort(401)
    elif request.endpoint is 'add_device' and not session.get('logged_in', None) == True:
        abort(401)

                
@app.route("/")
def index():
    onyen = request.cookies.get('onyen')
    # error checking around get
    req = get('%s/%s' % (TRACSEQ_API_BASE, onyen))
    current_transfers = [i for i in req.json() if i.get('status') == 'InTransit']
    return render_template('index.html',  current_transfers=current_transfers)

@app.route("/login", methods=['GET', 'POST'])
def login():
    form = LogInForm()
    if form.validate_on_submit():
        admin = Admin.query.filter_by(name=form.name.data).first()
        if admin.check_password(form.password.data):
            session['logged_in'] = True
            return redirect(url_for('add_device'))
        abort(401)
    return render_template("login.html", form=form)

@app.route("/add_device", methods=['GET', 'POST'])
def add_device():
    form = UserForm()
    if form.validate_on_submit():

        device_id = uuid4().hex
        user = Users.query.filter_by(name=form.name.data).first()

        if not user:
            user = Users(form.name.data, form.onyen.data, form.email.data)
            db.session.add(user)
            db.session.commit()
        
        device = Devices(device_id, user)
        db.session.add(device)
        db.session.commit()

        response = make_response(redirect(url_for('index')))
        today = datetime.today()
        expires = today.replace(year = today.year + 1)
        response.set_cookie('onyen', form.onyen.data, expires=expires)
        response.set_cookie('device_id', device_id, expires=expires)
        return response
    return render_template("add_device.html", form=form)

@app.route("/pickup", methods=['GET',])
def pickup():
    # do some error catching
    req = get('%s/%s' % (TRACSEQ_API_BASE, 'Available'))
    return render_template("pickup.html", data=req.json())

# may want to combine GET and POST 
@app.route("/checkout", methods=['POST'])
def checkout():
    form_data = request.form.to_dict()
    # try:
    #     additional_items = int(form_data.pop('additional_items', 0))
    # except ValueError:
    #     flash('Additional Items must be a number')
    #     return redirect(url_for('pickup'))

    notes = form_data.pop('notes', None)

    # notes = '%s, additional_items:%d' % (notes, additional_items)
    
    payload = {
        'carrier': request.cookies.get('onyen', None),
        'items': map(int, form_data.values()),
        'notes': notes,
        'status': 'InTransit',
        }

    if len(payload.get('items')) < 1: # + additional_items < 1:
        flash("Sorry, can't checkout %d items." % len(payload.get('items')))
        return redirect("/")

    # post to tracseq, need error checking
    # this may not be working
    req = post(TRACSEQ_API_BASE, json=payload)
    flash("%d sample%s checked out!" % (len(form_data), 's' if len(form_data) > 1 else ''))
    return redirect("/")

@app.route("/dropoff", methods=['GET',])
def dropoff():
    onyen = request.cookies.get('onyen', None)
    req = get('%s?carrier=%s' % (TRACSEQ_API_BASE, onyen))
    if not req.ok:
        abort(500)

    data = [d for d in req.json() if d.get('status', None) == 'InTransit']
    if len(data) == 0:
        flash("Please checkout data first!")
        return redirect("/")
    return render_template("dropoff.html", data=data)
                           
@app.route("/confirm", methods=['POST'])
def confirm():
    form_data = request.form.to_dict()
    standard_drop_off = form_data.pop('standard_drop_off', None)
    transfer_id = form_data.pop('transfer_id', None)
    notes = form_data.pop('notes', None)

    if not standard_drop_off and not notes:
        flash("Sorry, but a non-standard drop off requires notes!")
        return redirect(url_for('dropoff'))

    payload = {
        'carrier': request.cookies.get('onyen', None),
        'items': map(int, form_data.values()),
        'notes': notes,
        'status': 'Arrived',
        }

    req = post('%s/%s/status/Arrived' % (TRACSEQ_API_BASE, transfer_id), json=payload)
    if req.ok:
        flash("Transfer: %d's Material has been dropped off!" % int(request.form.get('transfer_id')))
    else:
        flash("Sorry about this, but there was an error!")
        flash("Please try again, or contact a developer.")
    return redirect("/")

@app.route("/modify/<int:transfer_id>")
def modify(transfer_id):

    req = get("%s/%d" % (TRACSEQ_API_BASE, transfer_id))
    transfers = req.json()
    transfer = transfers[0] if transfers else None

    if transfer.get('status') != 'InTransit':
        flash("Cannot modify transaction: %d" % transfer_id)
        return redirect("/")

    # items not being marked as checked out
    # need to talk to rob
    # also error checking
    req = get('%s/%s' % (TRACSEQ_API_BASE, 'Available'))
    available = req.json()
    return render_template("modify.html",
            transfer=transfer,
            newly_available=available)

@app.route("/modconfirm", methods=['POST'])
def confirm_modification():
    # get data and do stuff
    data = request.form.to_dict()
    transfer_id = data.pop('transfer_id', None)
    # try:
    #     additional_items = int(data.pop('additional_items', 0))
    # except ValueError:
    #     flash('Additional Items must be a number')
    #     return redirect(url_for('modify', transfer_id=transfer_id))

    notes = data.pop('notes', None)

    # notes = '%s, additional_items:%d' % (notes, additional_items)
    
    # just get the data that we want to use and post
    # error checking 
    req = get('%s/%s' % (TRACSEQ_API_BASE, transfer_id))
    transfer = req.json()[0]

    transfer['items'] = map(int, data.keys())
    transfer['notes'] = notes

    # error checking
    req = post('%s/%s' % (TRACSEQ_API_BASE, transfer_id), json=transfer)

    if req.ok:
        flash("Transaction: %d updated successfully!" % int(transfer_id))
    else:
        flash("Sorry, that didn't work.")
    return redirect("/")

@app.route("/cancel/<int:transfer_id>", methods=['POST'])
def cancel_transfer(transfer_id):

    # error checking 
    req = get("%s/%s" % (TRACSEQ_API_BASE, transfer_id))

    transfer = req.json()[0]
    transfer['status'] = 'Cancelled'
    transfer['items'] = []

    req = post("%s/%d" % (TRACSEQ_API_BASE, transfer_id), json=transfer)

    if req.ok:
        flash("Transaction: %d cancelled successfully!" % transfer_id)
    else:
        flash("Sorry, that didn't work.")
    return redirect("/")

# use config parser to import "global" variables
# need logging
# handle all req as lists not just the first one
