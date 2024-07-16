from flask import Flask
from flask_cors import CORS
from views.common_view import common
from views.database_view import db


def create_app():
    app = Flask(__name__)
    CORS(app, resources=r'/*')

    app.register_blueprint(common)
    app.register_blueprint(db)

    return app
