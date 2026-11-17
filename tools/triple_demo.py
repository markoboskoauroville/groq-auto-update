#!/usr/bin/env python3
"""Visible Triple Chat demo helpers: Macro Recorder is the only hand. usage: triple_demo.py click X Y | type TEXT | key KEY | shot NAME | front | ocr"""
import subprocess, sys, time, re
D = "/Users/markobosko/Developer/groq_ai_studio/docs/triple-demo/"
def sh(*a): return subprocess.run(a, capture_output=True, text=True).stdout
def frontapp(): return sh("osascript", "-e", 'tell application "System Events" to name of first process whose frontmost is true').strip()
def winid():
    for l in sh("macro", "win-list").splitlines():
        if l.startswith("Queen\t"): return l.split("#")[-1]
def origin():
    for l in sh("macro", "win-list").splitlines():
        if l.startswith("Queen\t"): f = l.split("\t"); return int(f[2]), int(f[3])
def front():
    x, y = origin(); sh("macro", "do", f"Click {x+400}, {y+12}"); time.sleep(.6)   # title bar of the Queen window
    return frontapp()
def ahk(code):
    if frontapp() != "GroqAIStudio": front()
    assert frontapp() == "GroqAIStudio", frontapp()
    return sh("macro", "do", code)
def click(x, y):
    ox, oy = origin(); x, y = int(x)+ox, int(y)+oy; ahk(f"MouseMove {x}, {y}, 20\nSleep 400\nClick {x}, {y}")
def typ(t):
    t = t.replace('"', '`"')
    ahk(f'SetKeyDelay 70\nSendEvent "{{Text}}{t}"')
def key(k): ahk(f"Send \"{k}\"")
def shot(n):
    f = D + n + ".png"; sh("screencapture", "-x", "-l", winid(), f); sh("sips", "-Z", "900", f); return f
def ocr(): return sh("macro", "ocr", "window:Queen")
if __name__ == "__main__":
    c, a = sys.argv[1], sys.argv[2:]
    r = {"click": lambda: click(*a), "type": lambda: typ(" ".join(a)), "key": lambda: key(a[0]),
         "shot": lambda: shot(a[0]), "front": front, "ocr": ocr}[c]()
    if r: print(r)
