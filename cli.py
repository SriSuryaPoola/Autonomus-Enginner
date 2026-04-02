#!/usr/bin/env python3
"""
CLI — AI Autonomous Engineer
Terminal interface for the Agentic Testing Platform.

Usage:
  python cli.py run --repo "https://github.com/owner/repo" --task "Write QA tests for src/app.py"
  python cli.py run --workspace "/path/to/local/repo" --task "Analyze core.py"
  python cli.py projects list
  python cli.py projects get <project-id>
  python cli.py status <project-id>
"""

import argparse
import json
import sys
import time

try:
    import requests
except ImportError:
    sys.exit("❌  Missing dependency: pip install requests")

BASE_URL = "http://localhost:8000"
POLL_INTERVAL = 3   # seconds between convergence polls


# ─── Helpers ─────────────────────────────────────────────────────────────────

def _check_backend():
    try:
        r = requests.get(f"{BASE_URL}/health", timeout=3)
        r.raise_for_status()
    except Exception:
        sys.exit(
            "❌  Cannot reach the backend at http://localhost:8000\n"
            "   Start it first:  python -m uvicorn server.app:app --reload"
        )


def _print_json(data: dict):
    print(json.dumps(data, indent=2))


def _color(text: str, code: str) -> str:
    return f"\033[{code}m{text}\033[0m"


def green(t):  return _color(t, "32")
def cyan(t):   return _color(t, "36")
def yellow(t): return _color(t, "33")
def red(t):    return _color(t, "31")
def bold(t):   return _color(t, "1")


# ─── Commands ────────────────────────────────────────────────────────────────

def cmd_run(args):
    """Create a project and dispatch a task, then stream convergence updates."""
    _check_backend()

    # 1. Create project
    payload = {
        "name": args.name or f"CLI Project",
        "description": args.task[:80],
    }
    if args.repo:
        payload["repository_url"] = args.repo

    print(bold("\n┌─ AI Autonomous Engineer CLI ──────────────────────────────"))
    print(bold("│") + f" 📂  Creating project: {payload['name']}")

    r = requests.post(f"{BASE_URL}/api/projects", json=payload)
    if not r.ok:
        sys.exit(f"❌  Failed to create project: {r.text}")

    proj = r.json()
    proj_id = proj["id"]
    print(bold("│") + f" ✅  Project ID: {cyan(proj_id)}")

    # 2. Dispatch task
    task_payload = {
        "project_id": proj_id,
        "prompt": args.task,
    }
    if args.workspace:
        task_payload["workspace"] = args.workspace

    print(bold("│") + f" 🚀  Dispatching task: {yellow(args.task[:70])}")
    r = requests.post(f"{BASE_URL}/api/tasks", json=task_payload)
    if not r.ok:
        sys.exit(f"❌  Failed to dispatch task: {r.text}")

    print(bold("│") + f" ⚙️   Status: {green('STARTED')}")
    print(bold("│"))

    # 3. Stream convergence updates
    print(bold("│") + "  LIVE CONVERGENCE MONITOR  (Ctrl+C to exit)")
    print(bold("│") + "─" * 52)

    last_state = None
    try:
        for _ in range(200):  # max ~10 minutes of polling
            r = requests.get(
                f"{BASE_URL}/api/projects/{proj_id}/convergence", timeout=5
            )
            if not r.ok:
                time.sleep(POLL_INTERVAL)
                continue

            data = r.json()
            state   = data.get("state", "UNKNOWN")
            cov     = data.get("coverage", {})
            cov_pct = cov.get("percentage", None)
            iters   = data.get("iterations", "…")
            heals   = data.get("self_heals", "…")

            cov_str  = f"{cov_pct:.1f}%" if isinstance(cov_pct, (int, float)) else "—"

            state_colored = {
                "RUNNING":   yellow(state),
                "CONVERGED": green(state),
                "ESCALATED": red(state),
                "AWAITING":  cyan(state),
            }.get(state, state)

            line = (
                f"\r{bold('│')}  State: {state_colored:20s} "
                f"Coverage: {cyan(cov_str):8s} "
                f"Iterations: {iters}  "
                f"Self-heals: {heals}   "
            )
            print(line, end="", flush=True)

            if state != last_state:
                last_state = state

            if state in ("CONVERGED", "ESCALATED"):
                print()  # newline after final state
                break

            time.sleep(POLL_INTERVAL)

    except KeyboardInterrupt:
        print()

    # 4. Final summary
    print(bold("│"))
    if last_state == "CONVERGED":
        print(bold("│") + f" {green('✅  CONVERGED')} — All tests passed & coverage met.")
    elif last_state == "ESCALATED":
        print(bold("│") + f" {red('⚠️  ESCALATED')} — Could not converge after max retries.")
        print(bold("│") + f"    Check memory/projects/{proj_id}/test_failures.json for details.")
    else:
        print(bold("│") + f" ⏸   Final state: {last_state}")

    print(bold("│"))
    print(bold("│") + f" 📋  Dashboard: http://localhost:3000")
    print(bold("│") + f" 🔍  Project ID: {proj_id}")
    print(bold("└") + "─" * 52 + "\n")


def cmd_projects_list(args):
    _check_backend()
    r = requests.get(f"{BASE_URL}/api/projects")
    if not r.ok:
        sys.exit(f"❌  {r.text}")
    projects = r.json()
    if not projects:
        print("No projects found.")
        return
    print(f"\n{'ID':12s}  {'Name':30s}  Description")
    print("─" * 80)
    for p in projects:
        print(f"{p['id']:12s}  {p['name']:30s}  {p.get('description','')[:40]}")
    print()


def cmd_projects_get(args):
    _check_backend()
    r = requests.get(f"{BASE_URL}/api/projects/{args.project_id}")
    if not r.ok:
        sys.exit(f"❌  Project not found: {args.project_id}")
    _print_json(r.json())


def cmd_status(args):
    _check_backend()
    r = requests.get(f"{BASE_URL}/api/projects/{args.project_id}/convergence")
    if not r.ok:
        sys.exit(f"❌  Could not get status: {r.text}")
    data = r.json()
    state = data.get("state", "UNKNOWN")
    cov   = data.get("coverage", {}).get("percentage", None)
    print(f"\nProject: {bold(args.project_id)}")
    print(f"  State:       {green(state) if state=='CONVERGED' else yellow(state)}")
    print(f"  Coverage:    {f'{cov:.1f}%' if isinstance(cov,(int,float)) else '—'}")
    print(f"  Iterations:  {data.get('iterations','—')}")
    print(f"  Self-heals:  {data.get('self_heals','—')}\n")


# ─── Argument Parser ──────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(
        prog="cli.py",
        description="🤖  AI Autonomous Engineer — Terminal CLI",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  python cli.py run --repo https://github.com/pallets/flask --task "Write QA tests for app.py"
  python cli.py run --workspace C:/myproject --task "Analyze auth.py and fix failing tests"
  python cli.py projects list
  python cli.py status <project-id>
        """
    )

    sub = parser.add_subparsers(dest="command")

    # run
    run_p = sub.add_parser("run", help="Create a project and run a task")
    run_p.add_argument("--task",      required=True, help="Natural language task description")
    run_p.add_argument("--repo",      help="GitHub repository URL")
    run_p.add_argument("--workspace", help="Local path to the repository")
    run_p.add_argument("--name",      help="Project name (auto-generated if omitted)")

    # projects
    proj_p = sub.add_parser("projects", help="Manage projects")
    proj_sub = proj_p.add_subparsers(dest="proj_command")
    proj_sub.add_parser("list", help="List all projects")
    get_p = proj_sub.add_parser("get",  help="Get a single project")
    get_p.add_argument("project_id")

    # status
    stat_p = sub.add_parser("status", help="Check live convergence status of a project")
    stat_p.add_argument("project_id")

    args = parser.parse_args()

    if args.command == "run":
        cmd_run(args)
    elif args.command == "projects":
        if args.proj_command == "list":
            cmd_projects_list(args)
        elif args.proj_command == "get":
            cmd_projects_get(args)
        else:
            proj_p.print_help()
    elif args.command == "status":
        cmd_status(args)
    else:
        parser.print_help()


if __name__ == "__main__":
    main()
