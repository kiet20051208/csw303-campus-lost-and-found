import argparse
from wsgiref.simple_server import make_server

from campus_lost_found import create_app


def main() -> None:
    parser = argparse.ArgumentParser(description="Run Campus Lost & Found locally")
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8000)
    parser.add_argument("--database", default=None)
    args = parser.parse_args()
    app = create_app(args.database)
    print(f"Campus Lost & Found running at http://{args.host}:{args.port}")
    with make_server(args.host, args.port, app) as server:
        server.serve_forever()


if __name__ == "__main__":
    main()
