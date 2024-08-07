from dotenv import load_dotenv
load_dotenv()

import os
from src.views import create_app
from src.utils import setup_logger

logger = setup_logger("Server")

app = create_app()

if __name__ == '__main__':
    logger.info("Starting server")
    app.secret_key = os.urandom(24)
    app.run(host='0.0.0.0', port=5000, debug=False, threaded=True)
