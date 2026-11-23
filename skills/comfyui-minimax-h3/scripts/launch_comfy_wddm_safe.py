#!/usr/bin/env python3
"""Safe ComfyUI Launcher for Windows WDDM Dual-Instance Setups.
Caps per-instance MAX_PINNED_MEMORY via MAX_PIN_GB (e.g. 22 + 18 = 40 GiB << 64 GiB OS limit on 128 GB RAM)
right after comfy.model_management initializes, without modifying ComfyUI source files.
"""
import importlib.abc
import os
import runpy
import sys

comfy_dir = os.environ.get("COMFY_DIR", r"E:\ComfyUI-app")
sys.path.insert(0, comfy_dir)
os.chdir(comfy_dir)

max_pin_gb = float(os.environ.get("MAX_PIN_GB", "22"))
_patched = False


class _PinCapFinder(importlib.abc.MetaPathFinder):
    def find_spec(self, fullname, path, target=None):
        global _patched
        if not _patched and fullname in ("nodes", "execution", "server", "comfy.sd"):
            mm = sys.modules.get("comfy.model_management")
            if mm is not None and getattr(mm, "MAX_PINNED_MEMORY", -1) > 0:
                mm.MAX_PINNED_MEMORY = int(max_pin_gb * (1024 ** 3))
                _patched = True
                print(
                    f"[WDDMPinGuard] Capped MAX_PINNED_MEMORY to {max_pin_gb:.1f} GiB "
                    f"({mm.MAX_PINNED_MEMORY // (1024 * 1024)} MiB)",
                    flush=True,
                )
        return None


sys.meta_path.insert(0, _PinCapFinder())
runpy.run_path(os.path.join(comfy_dir, "main.py"), run_name="__main__")
