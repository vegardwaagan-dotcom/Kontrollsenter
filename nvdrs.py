"""Windows: skriv DLSS-innstillinger i NVIDIA-driverens globale profil (NVAPI DRS – som NVIDIA-appen gjør).

Brukes av gpu.win_drs_apply:  python nvdrs.py 0xID=VERDI 0xID=- ...   («-» = tilbake til driverens standard)
Avslutter med 0 = OK, 3 = trenger administrator, 2 = annen feil.
"""
import ctypes
import sys
from ctypes import POINTER, Structure, Union, byref, c_float, c_int, c_uint8, c_uint16, c_uint32, c_uint64, c_void_p

# funksjons-ID-er fra NVIDIA sin nvapi_interface.h
F = {"init": 0x0150E828, "create": 0x0694D52E, "destroy": 0xDAD9CFF8, "load": 0x375DBD6B, "save": 0xFCBC7E14,
     "base": 0xDA8466A0, "set": 0x577DD202, "delete": 0xE4A26362}
NO_PRIVILEGE, NOT_FOUND = -137, -160


class _Bin(Structure):
    _fields_ = [("length", c_uint32), ("data", c_uint8 * 4096)]


class _Val(Union):
    _fields_ = [("u32", c_uint32), ("bin", _Bin), ("wsz", c_uint16 * 2048), ("u64", c_uint64), ("f32", c_float)]


class Setting(Structure):
    _fields_ = [("version", c_uint32), ("name", c_uint16 * 2048), ("id", c_uint32), ("type", c_int),
                ("location", c_int), ("is_current_predefined", c_uint32), ("is_predefined_valid", c_uint32),
                ("predefined", _Val), ("current", _Val)]


VERSION = ctypes.sizeof(Setting) | (1 << 16)


def parse(args):
    out = {}
    for a in args:
        k, v = a.split("=", 1)
        out[int(k, 16)] = None if v == "-" else int(v)
    return out


def main(args):
    want = parse(args)
    lib = ctypes.WinDLL("nvapi64.dll" if ctypes.sizeof(c_void_p) == 8 else "nvapi.dll")
    qi = lib.nvapi_QueryInterface
    qi.restype, qi.argtypes = c_void_p, [c_uint32]

    def fn(name, *argtypes):
        return ctypes.CFUNCTYPE(c_int, *argtypes)(qi(F[name]))
    if fn("init")():
        return 2
    h, prof = c_void_p(), c_void_p()
    if fn("create", POINTER(c_void_p))(byref(h)):
        return 2
    try:
        rc = fn("load", c_void_p)(h) or fn("base", c_void_p, POINTER(c_void_p))(h, byref(prof))
        if rc:
            return 3 if rc == NO_PRIVILEGE else 2
        set_ = fn("set", c_void_p, c_void_p, POINTER(Setting))
        delete = fn("delete", c_void_p, c_void_p, c_uint32)
        for sid, val in want.items():
            if val is None:
                rc = delete(h, prof, sid)
                rc = 0 if rc == NOT_FOUND else rc
            else:
                s = Setting(version=VERSION, id=sid, type=0)       # 0 = DWORD
                s.current.u32 = val
                rc = set_(h, prof, byref(s))
            if rc:
                return 3 if rc == NO_PRIVILEGE else 2
        rc = fn("save", c_void_p)(h)
        return 0 if not rc else 3 if rc == NO_PRIVILEGE else 2
    finally:
        fn("destroy", c_void_p)(h)


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
