#!/usr/bin/env python3
"""
Fieldbase Go-live - Demo Launcher
Usage:
    python run_demo.py                  # Starts the web console on http://127.0.0.1:8000
    python run_demo.py --port 8080      # Starts on custom port
"""

import argparse
import sys
import uvicorn

def main():
    parser = argparse.ArgumentParser(description="Fieldbase Go-live Demo Server")
    parser.add_argument("--host", default="127.0.0.1", help="Host interface to bind (default: 127.0.0.1)")
    parser.add_argument("--port", type=int, default=8000, help="Port to bind (default: 8000)")
    parser.add_argument("--reload", action="store_true", default=True, help="Enable auto-reload")

    args = parser.parse_args()

    print("=================================================================")
    print("Fieldbase Go-live Implementation Agent Demo")
    print(f"Web Console available at: http://{args.host}:{args.port}")
    print("=================================================================")

    uvicorn.run("app.main:app", host=args.host, port=args.port, reload=args.reload)

if __name__ == "__main__":
    main()
