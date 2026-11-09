#!/usr/bin/env python3
"""
Fieldbase Go-live - Live Model Evaluation & Demo Runner
Usage:
    python scripts/run_live.py --scenario contoso --mode live
    python scripts/run_live.py --scenario northwind --mode fake
"""

import argparse
from datetime import datetime, timezone
import json
import os
import sys
from pathlib import Path
import httpx

PROJECT_ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

def main():
    parser = argparse.ArgumentParser(description="Run Go-live Scenario Evaluation")
    parser.add_argument(
        "--scenario",
        default="contoso",
        choices=["northwind", "contoso", "fabrik", "northwind_retry"],
        help="Scenario to run (default: contoso)",
    )
    parser.add_argument(
        "--mode",
        default="fake",
        choices=["fake", "live"],
        help="Model mode (default: fake)",
    )
    parser.add_argument(
        "--url",
        default="http://127.0.0.1:8000",
        help="Base URL of running server (default: http://127.0.0.1:8000)",
    )

    args = parser.parse_args()

    print("=================================================================")
    print(f"Executing scenario: '{args.scenario}' in mode: '{args.mode}'")
    print(f"Target URL: {args.url}")
    print("=================================================================\n")

    try:
        with httpx.Client(base_url=args.url, timeout=60.0) as client:
            resp = client.post("/api/demo/run", json={"scenario": args.scenario, "mode": args.mode})
            if resp.status_code != 200:
                print(f"Run failed ({resp.status_code}): {resp.text}")
                sys.exit(1)

            data = resp.json()
    except httpx.ConnectError:
        print(f"Error: Could not connect to server at {args.url}.")
        print("Please ensure the server is running (e.g. 'python run_demo.py').")
        sys.exit(1)

    print(f"Run ID: {data['runId']}")
    print(f"Stopped Reason: {data['stoppedReason']}")
    print(f"Scenario Message: {data['message']}\n")

    print("Steps Executed:")
    steps = data.get("steps", [])
    error_codes = []
    step_descriptions = []

    for s in steps:
        idx = s["stepIndex"]
        tool = s["toolName"]
        status = s["httpStatus"]
        code = s.get("errorCode") or "ok"
        replayed = " [Replayed]" if s.get("replayed") else ""

        step_descriptions.append(f"{tool}({json.dumps(s.get('arguments', {}))})")
        if s.get("errorCode"):
            error_codes.append(s["errorCode"])

        print(f"  Step {idx}: {tool}{replayed} -> HTTP {status} ({code})")

    tenant = data.get("tenant", {})
    print(f"\nFinal Tenant Status: {tenant.get('status')}")
    print(f"Is Live: {tenant.get('live')}")
    print(f"Enabled Modules: {tenant.get('modules')}")

    today_str = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    model_name = os.environ.get("LLM_MODEL", "FakeModel" if args.mode == "fake" else "unknown")

    print("\n-----------------------------------------------------------------")
    print("Markdown template for docs/09-demo-and-resume.md:")
    print("-----------------------------------------------------------------")
    print(f"- Date: {today_str}")
    print(f"- Model id: {model_name}")
    print(f"- Scenario: {args.scenario}")
    print(f"- Steps the model actually called: {', '.join(step_descriptions)}")
    print(f"- Any MODULE_NOT_PURCHASED or other error codes: {', '.join(error_codes) if error_codes else 'none'}")
    print(f"- Did the final text claim the account was live: {'no' if not tenant.get('live') else 'yes'}")
    print(f"- Token usage, or \"not reported\": not reported")
    print("-----------------------------------------------------------------")

if __name__ == "__main__":
    main()
