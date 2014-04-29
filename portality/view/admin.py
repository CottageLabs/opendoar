from flask import Blueprint, request, flash, abort, make_response
from flask import render_template, redirect, url_for
from flask.ext.login import current_user, login_required

from portality.core import app, ssl_required

blueprint = Blueprint('admin', __name__)

# build an admin page where things can be done
@blueprint.route('/')
@login_required
@ssl_required
def index():
    return render_template('admin/index.html')
