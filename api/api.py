"""
RGW API service (version/files/cameras/robot control).

Important: this module may be started with CWD=api/ (because it lives in api/api.py).
All file operations for the updater must therefore resolve paths relative to PROJECT_ROOT,
not the current working directory.
"""
from flask import Flask

app = Flask(__name__)


@app.after_request
def after_request(response):
    response.headers.add("Access-Control-Allow-Origin", "*")
    response.headers.add("Access-Control-Allow-Headers", "Content-Type,Authorization")
    response.headers.add("Access-Control-Allow-Methods", "GET,PUT,POST,DELETE,OPTIONS")
    return response


def register_routes(app: Flask) -> None:
    from api.routes.cameras import bp as cameras_bp
    from api.routes.files import bp as files_bp
    from api.routes.robot import bp as robot_bp
    from api.routes.status import bp as status_bp
    from api.routes.version import bp as version_bp

    app.register_blueprint(version_bp)
    app.register_blueprint(files_bp)
    app.register_blueprint(cameras_bp)
    app.register_blueprint(status_bp)
    app.register_blueprint(robot_bp)


def run_api(host="0.0.0.0", port=5000, debug=False):
    register_routes(app)
    app.run(host=host, port=port, debug=debug, threaded=True)


def run():
    import services_manager
    try:
        manager = services_manager.get_services_manager()
        port = int(manager.get_service_parameters("api").get("port", 5000))
    except Exception:
        port = 5000
    # Port may be busy (e.g. after crash/restart). Try a small set.
    ports_to_try = [port] + [p for p in (5000, 5001, 5002, 5003, 5004, 5007, 5008) if p != port]
    last_err = None
    for p in ports_to_try:
        try:
            print(f"Starting API service on port {p}...", flush=True)
            run_api(host="0.0.0.0", port=int(p), debug=False)
            return
        except BaseException as e:
            last_err = e
            try:
                print(f"API port {p} is busy: {e}", flush=True)
            except Exception:
                pass
            continue
    raise RuntimeError(f"Could not bind API ports: {ports_to_try}. Last error: {last_err}")


if __name__ == "__main__":
    run()
