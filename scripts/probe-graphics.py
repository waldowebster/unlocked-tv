"""Verify real GBM/EGL initialization without taking ownership of an HDMI display."""
import ctypes
import json
import os
from pathlib import Path


def probe():
    nodes = sorted(Path("/dev/dri").glob("renderD*"))
    if not nodes:
        raise RuntimeError("No DRM render device is available")
    gbm = ctypes.CDLL("libgbm.so.1")
    gbm.gbm_create_device.argtypes = [ctypes.c_int]
    gbm.gbm_create_device.restype = ctypes.c_void_p
    gbm.gbm_device_destroy.argtypes = [ctypes.c_void_p]
    egl = ctypes.CDLL("libEGL.so.1")
    egl.eglGetPlatformDisplay.argtypes = [ctypes.c_uint, ctypes.c_void_p, ctypes.c_void_p]
    egl.eglGetPlatformDisplay.restype = ctypes.c_void_p
    egl.eglInitialize.argtypes = [ctypes.c_void_p, ctypes.POINTER(ctypes.c_int), ctypes.POINTER(ctypes.c_int)]
    egl.eglInitialize.restype = ctypes.c_uint
    egl.eglTerminate.argtypes = [ctypes.c_void_p]
    fd = os.open(nodes[0], os.O_RDWR | os.O_CLOEXEC)
    device = None
    display = None
    try:
        device = gbm.gbm_create_device(fd)
        if not device:
            raise RuntimeError("GBM backend initialization failed; check GBM_BACKENDS_PATH")
        display = egl.eglGetPlatformDisplay(0x31D7, device, None)  # EGL_PLATFORM_GBM_KHR
        major, minor = ctypes.c_int(), ctypes.c_int()
        if not display or not egl.eglInitialize(display, ctypes.byref(major), ctypes.byref(minor)):
            raise RuntimeError(f"EGL initialization failed: 0x{egl.eglGetError():04x}")
        return {"device": str(nodes[0]), "gbm": "initialized", "egl": f"{major.value}.{minor.value}",
                "backend_path": os.environ.get("GBM_BACKENDS_PATH"), "physical_display_tested": False}
    finally:
        if display:
            egl.eglTerminate(display)
        if device:
            gbm.gbm_device_destroy(device)
        os.close(fd)


if __name__ == "__main__":
    print(json.dumps(probe(), indent=2))
