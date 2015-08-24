from datetime import datetime
from itertools import permutations
from os.path import abspath, dirname, join
from flask import flash, Flask, jsonify, redirect, render_template, request, url_for
from flask.ext.bcrypt import Bcrypt
from flask.ext.sqlalchemy import SQLAlchemy
from requests import get, post

# configurations
basedir = abspath(dirname(__file__))
SQLALCHEMY_DATABASE_URI = ''.join(['sqlite:///', join(basedir, '../../data/transport.db')])

app = Flask(__name__)
app.secret_key = "weliveinasocietypeople"
app.config['SQLALCHEMY_DATABASE_URI'] = SQLALCHEMY_DATABASE_URI

db = SQLAlchemy(app)

bcrypt = Bcrypt(app)

# DATABASE
class Users(db.Model):
    """

    """
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(120), unique=True)
    email = db.Column(db.String(120), unique=True, nullable=False)
    password = db.Column(db.String(120), nullable=False)
    timestamp = db.Column(db.DateTime)

    def __init__(self, name, email, password):
        self.name = name
        self.email = email
        self.password = bcrypt.generate_password_hash(password)
        self.timestamp = datetime.now()
    
    
# need to include the user
class Transfers(db.Model):
    """Class containing meta data for transfers.

    Contains information about the user, location, batch number.

    """
    id = db.Column(db.Integer, primary_key=True)
    status = db.Column(db.String(16), nullable=False)
    start_loc = db.Column(db.String(4), nullable=False)
    stop_loc = db.Column(db.String(4), nullable=False)
    user_id = db.Column(db.Integer, db.ForeignKey('users.id'))
    user = db.relationship('Users', backref=db.backref('transit', lazy='dynamic'))
    date_start = db.Column(db.DateTime)
    date_stop = db.Column(db.DateTime)    

    def __init__(self, start_loc):
        location_mapper = dict([i for i in permutations((unicode('GSB'), unicode('CCC')))])
        self.status = 'In Transit'
        self.start_loc = start_loc
        self.stop_loc = location_mapper.get(start_loc.upper())
        self.date_start = datetime.now() 
        self.user_id = 1


class TransferItems(db.Model):
    """Class outlining specific material with reference to Transit.

    """
    id = db.Column(db.Integer, primary_key=True)
    tracseq_id = db.Column(db.Integer)
    transfer_id = db.Column(db.Integer, db.ForeignKey('transfers.id'))
    transfer = db.relationship('Transfers', backref=db.backref('transfers', lazy='dynamic'))
#    timestamp = db.Column(db.DateTime)

    def __init__(self, transfer_id, tracseq_id):
        self.transfer_id = transfer_id
        self.tracseq_id = tracseq_id
#        self.timestamp = datetime.now()


# VIEWS
@app.route("/")
def index():
    current_transfer = Transfers.query.filter_by(status="In Transit").first()
    return render_template('index.html',  current_transfer=current_transfer)

@app.route("/pickup/<location>", methods=['GET',])
def pickup(location):
    req = get('http://myflaskapp-keklund.apps.unc.edu/pickup/%s' % location)
    return render_template("pickup.html", location=location, data=req.json())

@app.route("/checkout", methods=['POST'])
def checkout():
    form_data = request.form.to_dict()
    location = form_data.pop('location', None)

    transfer = Transfers(location)
    db.session.add(transfer)
    db.session.commit()

    transfer_items = [TransferItems(transfer.id, v) for k,v in form_data.items()]
    db.session.bulk_save_objects(transfer_items)
    db.session.commit()
    
    flash("%d samples checked out!" % len(form_data))
    return redirect("/")

@app.route("/dropoff/<location>", methods=['GET',])
def dropoff(location):
    current_transfer = Transfers.query.\
      filter_by(user_id=1).\
      filter_by(status='In Transit').\
      first()
    if not current_transfer:
        flash("Please checkout data first!")
        return redirect("/")
    return render_template("dropoff.html",
                           location=location,
                           data=current_transfer)

@app.route("/confirm", methods=['POST'])
def confirm():
    now = datetime.now()
    if request.form:
        transfer = Transfers.query.get(request.form.get('transfer_id'))
        transfer.date_stop = datetime.now()
        transfer.status = 'Arrived'
        db.session.add(transfer)
        db.session.commit()
        flash("Transfer: %d's Material has been dropped off!" % int(request.form.get('transfer_id')))
    return redirect("/")

@app.route("/modify/<int:transfer_id>")
def modify(transfer_id):
    transfer = Transfers.query.get(transfer_id)
    if transfer.status != 'In Transit':
        flash("Cannot modify transaction: %d" % transfer_id)
        return redirect("/")

    # Get current list of manifest
    # Get list of available samples
    # make appropriate alterations to tables
    transfer_items = TransferItems.query.filter_by(transfer_id=transfer_id).all()
    req = get('http://myflaskapp-keklund.apps.unc.edu/pickup/GSB')    
    return render_template("modify.html", transfer_items=transfer_items, data=req.json(), transfer_id=transfer_id)

@app.route("/modconfirm", methods=['POST'])
def confirm_modification():
    # get data and do stuff
    data = request.form.to_dict()
    transfer_id = data.pop('transfer_id', None)
    original_transfer_items = TransferItems.query.filter_by(transfer_id=transfer_id).all()

    original_item_ids = set([i.tracseq_id for i in original_transfer_items])
    new_item_ids = set(map(int, data.keys()))
    # what if either of these are length 0?
    print 'orig: ', original_item_ids
    print 'new: ', new_item_ids

    # removal
    for removal_id in original_item_ids.difference(new_item_ids):
        removal_item = TransferItems.query.\
          filter_by(tracseq_id=removal_id).\
          filter_by(transfer_id=transfer_id).\
          first()
        db.session.delete(removal_item)
        db.session.commit()
            
    # can have a key that is already in original_transfer_items - do nothing
    # can have a key that isn't in original_transfer_items - add to transfer
    # can have a key that is in original_transfer_items but not data - remove from transfer

    flash("Transaction updated successfully!")
    return redirect("/")

@app.route("/cancel/<int:transfer_id>", methods=['POST'])
def cancel_transfer(transfer_id):
    # how to confirm?  Confirmation page? text input?
    #
    # could simply: confirm it was the user who checked it out, and flash message
    # will need to put back to tracseq to release these samples again
    transfer = Transfers.query.get(transfer_id)
    transfer.status = "Cancelled"
    transfer.date_stop = datetime.now()
    db.session.commit()
    flash("Transaction cancelled successfully!")
    return redirect("/")
