import os
import sys
import builtins
import traceback
import threading

import keyboard
import pyperclip

# Working directory = the directory this executor file lives in.
SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
os.chdir(SCRIPT_DIR)

# Guard against re-entrancy (e.g. holding the hotkey down).
_running = False
_lock = threading.Lock()


def execute_clipboard() -> None:
    global _running
    with _lock:
        if _running:
            return
        _running = True

    try:
        code = pyperclip.paste()
        if not code or not code.strip():
            print("[executor] Clipboard is empty — nothing to run.")
            return

        print("\n" + "=" * 70)
        print("[executor] Running clipboard script...")
        print("=" * 70)

        # Fresh globals each run, but with useful dunders set so the script
        # behaves like a normal file located in SCRIPT_DIR.
        exec_globals = {
            "__name__": "__main__",
            "__file__": os.path.join(SCRIPT_DIR, "clipboard_script.py"),
            "__builtins__": builtins,
        }

        try:
            compiled = compile(code, "<clipboard>", "exec")
            exec(compiled, exec_globals)
        except SystemExit:
            print("[executor] Clipboard script called sys.exit() — ignored.")
        except BaseException:
            traceback.print_exc()
        finally:
            # flush so the output interleaves nicely with the executor banner
            sys.stdout.flush()
            sys.stderr.flush()

        print("=" * 70)
        print("[executor] Done. Press Ctrl+Shift+X to run the clipboard again.")
        print("=" * 70 + "\n")
    finally:
        with _lock:
            _running = False


def main() -> None:
    print(f"[executor] Watching for Ctrl+Shift+X")
    print(f"[executor] Working directory: {SCRIPT_DIR}")
    print("[executor] Press Ctrl+C in this console to stop.\n")

    keyboard.add_hotkey("ctrl+shift+x", execute_clipboard, suppress=False)

    try:
        keyboard.wait()  # block forever
    except KeyboardInterrupt:
        pass
    finally:
        keyboard.unhook_all()
        print("\n[executor] Stopped.")


if __name__ == "__main__":
    main()