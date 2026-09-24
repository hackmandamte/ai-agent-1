def ask_approval(action: str) -> bool:
    print("\n⚠️  APPROVAL REQUIRED")
    print(action)

    try:
        answer = input("Approve? [y/N]: ").strip().lower()
    except (EOFError, KeyboardInterrupt):
        print("\nApproval unavailable. Denying action.")
        return False

    return answer in {"y", "yes"}
