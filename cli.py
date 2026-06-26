from __future__ import annotations

import sys

from agent.workflow import PrecisoAgentWorkflow
from config import ensure_workspace, get_settings


def main() -> int:
    settings = get_settings()
    ensure_workspace(settings)
    workflow = PrecisoAgentWorkflow(settings)

    print("Preciso Agent")
    print(f"Data: OpenBB SEC + local inbox ({settings.inbox_dir})")
    print(f"Graph engine: Preciso via {settings.preciso_client_mode} backend")
    print("Type 'quit' to exit.\n")

    while True:
        try:
            user_input = input("User: ").strip()
        except EOFError:
            print()
            return 0
        except KeyboardInterrupt:
            print("\nInterrupted.")
            return 0

        if not user_input:
            continue
        if user_input.lower() in {"quit", "exit"}:
            return 0

        try:
            result = workflow.run(user_input)
            print("\nAssistant:")
            print(result.get("final_response", "No response generated."))
            if result.get("errors"):
                print("\nWarnings:")
                for error in result["errors"]:
                    print(f"- {error}")
            print()
        except Exception as exc:
            print(f"\nError: {exc}\n")


if __name__ == "__main__":
    sys.exit(main())

