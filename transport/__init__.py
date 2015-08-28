from datetime import datetime
from itertools import permutations
from os.path import abspath, dirname, join
from flask import abort, flash, Flask, jsonify, make_response, redirect, render_template, request, session, url_for
from flask.ext.sqlalchemy import SQLAlchemy
from flask.ext.wtf import Form
from wtforms import TextField, validators
from requests import get, post

# configurations
basedir = abspath(dirname(__file__))
SQLALCHEMY_DATABASE_URI = ''.join(['sqlite:///', join(basedir, '../../data/transport.db')])

TRACSEQ_API_BASE = 'https://mps-mssql.its.unc.edu/DevTracSeq/Internal/Transfers'

app = Flask(__name__)
# do I need a secret key when we have sessions?
app.secret_key = "weliveinasocietypeople"
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
    # separate table with device list
    device_id = db.Column(db.String(120), unique=True, nullable=False)
    timestamp = db.Column(db.DateTime)

    def __init__(self, name, onyen, email, device_id):
        self.name = name
        self.onyen = onyen
        self.email = email
        self.device_id = device_id
        self.timestamp = datetime.now()
    
    
# FORMS
class UserForm(Form):
    name = TextField('name', [validators.Length(max=120)])
    onyen = TextField('onyen', [validators.Length(max=10)])
    email = TextField('email', [validators.Email(), validators.Length(max=120)])
    

class LogInForm(Form):
    name = TextField('name')
    password = TextField('password')

    
# VIEWS
@app.errorhandler(401)
def unauthorized(error):
    # is this right?
    return render_template('401.html', form=UserForm()), 401 #, {'WWW-Authenticate': 'Basic realm="Login Required"'}

# do we need a 403 - forbidden?

@app.errorhandler(404)
def page_not_found(error):
    return render_template('404.html'), 404

@app.errorhandler(500)
def unauthorized(error):
    # is this right?
    return render_template('500.html'), 500 #, {'WWW-Authenticate': 'Basic realm="Login Required"'}

@app.before_request
def get_user():
    # need more logic for add_device (can only be logged in as admin)
    if not request.endpoint in ('add_device', 'login'):
        onyen = request.cookies.get('onyen')
        device_id = request.cookies.get('device_id')
        if onyen and device_id:
    #        user = Users.query.filter_by(onyen=onyen).filter_by(device_id=device_id).first()
# log in user
            pass
        # elif admin:
        #     pass
        else:
            flash("This user's device isn't registered!")
            flash("Please contact an admin to register your device!")
            abort(401)
    
@app.route("/")
def index():
    # look at tracseq first by onyen to see what is waiting
    onyen = request.cookies.get('onyen')
    # error checking around get
    req = get('%s/%s' % (TRACSEQ_API_BASE, onyen))
    current_transfers = [i for i in req.json() if i.get('status') == 'InTransit']
    return render_template('index.html',  current_transfers=current_transfers)

@app.route("/login", methods=['GET', 'POST'])
def login():
    form = LogInForm()
    if form.validate_on_submit():
        return redirect(url_for('add_device'))
    return render_template("login.html", form=form)

# can only get here if logged in
@app.route("/add_device", methods=['GET', 'POST'])
def add_device():
    form = UserForm()
    if form.validate_on_submit():
        response = make_response(redirect(url_for('index')))
        response.set_cookie('onyen', form.onyen.data)
        response.set_cookie('device_id', 'test_cookie')
        return response
    return render_template("add_device.html", form=form)

@app.route("/pickup", methods=['GET',])
def pickup():
    # do some error catching
    req = get('%s/%s' % (TRACSEQ_API_BASE, 'Available'))
    return render_template("pickup.html", data=req.json())

# may want to combin GET and POST 
@app.route("/checkout", methods=['POST'])
def checkout():
    form_data = request.form.to_dict()
    notes = form_data.pop('notes', None)

    payload = {
        'carrier': request.cookies.get('onyen', None),
        'items': map(int, form_data.values()),
        'notes': notes,
        'status': 'InTransit',
        }
       
    # post to tracseq, need error checking
    # this may not be working
    req = post(TRACSEQ_API_BASE, json=payload)
    flash("%d samples checked out!" % len(form_data))
    return redirect("/")

@app.route("/dropoff", methods=['GET',])
def dropoff():
    onyen = request.cookies.get('onyen', None)
    req = get('%s?carrier=%s&status=InTransit' % (TRACSEQ_API_BASE, onyen))
    if req.ok:
        data = req.json()
    else:
        flash("Sorry about this, but there was an error!")
        flash("Please try again, or contact a developer.")
        abort(500)

    if len(data) == 0:
        flash("Please checkout data first!")
        return redirect("/")
    
    print data
    return render_template("dropoff.html", data=data)
                           

@app.route("/confirm", methods=['POST'])
def confirm():
    req = post('%s/%s/status/arrived' % (TRACSEQ_API_BASE, request.form.get('transfer_id', None)))
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
                           transfer_items=transfer.get('items'),
                           newly_available=available,
                           transfer_id=transfer_id)

@app.route("/modconfirm", methods=['POST'])
def confirm_modification():
    # get data and do stuff
    data = request.form.to_dict()
    transfer_id = data.pop('transfer_id', None)

    # just get the data that we want to use and post
    # error checking 
    req = get('%s/%s' % (TRACSEQ_API_BASE, transfer_id))
    transfer = req.json()[0]

    transfer['items'] = map(int, data.values())

    # error checking
    req = post('%s/%s' % (TRACSEQ_API_BASE, transfer_id), json=transfer)

    if req.ok:
        flash("Transaction: %d updated successfully!" % int(transfer_id))
    else:
        flash("Sorry, that didn't work.")
    return redirect("/")

@app.route("/cancel/<int:transfer_id>", methods=['POST'])
def cancel_transfer(transfer_id):
    # how to confirm?  Confirmation page? text input?
    #
    # could simply: confirm it was the user who checked it out, and flash message
    # will need to put back to tracseq to release these samples again
    # transfer = Transfers.query.get(transfer_id)
    # transfer.status = "Cancelled"
    # transfer.date_stop = datetime.now()
    # db.session.commit()


    req = get("%s/%s" % (TRACSEQ_API_BASE, transfer_id))
    transfer = req.json()[0]
    transfer['status'] = 'Cancelled'
    transfer['items'] = []

    # req = post('%s/%d/status/cancelled' % (TRACSEQ_API_BASE, transfer_id))

    req = post("%s/%d" % (TRACSEQ_API_BASE, transfer_id), json=transfer)
    if req.ok:
        flash("Transaction: %d cancelled successfully!" % transfer_id)
    else:
        flash("Sorry, that didn't work.")
    return redirect("/")

# use config parser to import "global" variables
# need logging
# catch all errors and then determine 401, 404, or 500? special error function?
# handle all req as lists not just the first one
