#!/usr/bin/env python3
"""Quick command line client for the Groq API with key fallback.

Usage:
    groq-cli "your question"
    echo "text" | groq-cli
    groq-cli --status     show every key and whether it is available
    groq-cli --reset      clear all cooldowns
"""
import sys

from groq import APIError

from groq_pool import AllKeysExhausted, DEFAULT_MODEL, KeyPool


def main():
    args = sys.argv[1:]

    try:
        pool = KeyPool()
    except RuntimeError as exc:
        sys.exit(f"Error: {exc}")

    if args and args[0] == "--status":
        print(f"Model: {DEFAULT_MODEL}")
        for index, masked, note in pool.status():
            print(f"  #{index:<3} {masked}  {note}")
        return

    if args and args[0] == "--reset":
        pool.reset()
        print("Cooldowns cleared.")
        return

    question = " ".join(args).strip()
    if not question and not sys.stdin.isatty():
        question = sys.stdin.read().strip()
    if not question:
        sys.exit('Usage: groq-cli "your question"\n       echo "text" | groq-cli')

    try:
        for chunk in pool.stream([{"role": "user", "content": question}]):
            if chunk.choices:
                print(chunk.choices[0].delta.content or "", end="", flush=True)
        print()
    except AllKeysExhausted as exc:
        sys.exit(f"\nError: {exc}")
    except APIError as exc:
        sys.exit(f"\nAPI error: {exc}")
    except KeyboardInterrupt:
        sys.exit(130)


if __name__ == "__main__":
    main()
