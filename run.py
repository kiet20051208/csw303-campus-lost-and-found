import argparse
import os
from wsgiref.simple_server import make_server

from campus_lost_found import create_app
from campus_lost_found.demo_data import seed_demo_data


def main() -> None:
    parser = argparse.ArgumentParser(description="Run Campus Lost & Found")
    parser.add_argument("--host", default="0.0.0.0")
    parser.add_argument(
        "--port",
        type=int,
        default=int(os.environ.get("PORT", "8000")),
    )
    parser.add_argument("--database", default=None)

    args = parser.parse_args()

    app = create_app(args.database)
    if os.environ.get("CAMPUS_LF_AUTO_SEED", "1") != "0":
        seed_demo_data(app.store)
    print(f"Campus Lost & Found running at http://{args.host}:{args.port}")

    with make_server(args.host, args.port, app) as server:
        server.serve_forever()


if __name__ == "__main__":
    main()
