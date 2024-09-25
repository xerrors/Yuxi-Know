from flask import Flask
from flask_cors import CORS
from src.views.common_view import common
from src.views.database_view import db
from src.views.tools_view import tools


def create_app():
    app = Flask(__name__)
    CORS(app, resources=r'/*')

    app.register_blueprint(common)
    app.register_blueprint(db)
    app.register_blueprint(tools)

    return app
