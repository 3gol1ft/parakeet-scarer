"""Acces a la webcam Logitech C920 via OpenCV et V4L2.
Detecte automatiquement le peripherique par identifiant USB, fixe la mise au point
et la balance des blancs via v4l2-ctl pour garantir des images stables."""
import glob
import os
import subprocess

import cv2


def find_camera_device():
    cands = sorted(glob.glob("/dev/v4l/by-id/*C920*-video-index0"))
    if not cands:
        cands = sorted(glob.glob("/dev/v4l/by-id/*Webcam*-video-index0"))
    if not cands:
        raise RuntimeError("Aucune webcam detectee (verifie le branchement).")
    return os.path.realpath(cands[0])


def _reglages_stables(device, focus):
    for ctrl in ("focus_automatic_continuous=0", f"focus_absolute={focus}",
                 "white_balance_automatic=0", "power_line_frequency=1"):
        subprocess.run(["v4l2-ctl", "-d", device, "--set-ctrl", ctrl],
                       stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)


class Camera:
    def __init__(self, device=None, width=1280, height=720, focus=20):
        self.device = os.path.realpath(device) if device else find_camera_device()
        self.width = width
        self.height = height
        self.focus = focus
        self.cap = None

    def open(self):
        self.cap = cv2.VideoCapture(self.device, cv2.CAP_V4L2)
        if not self.cap.isOpened():
            raise RuntimeError(f"Impossible d'ouvrir la camera : {self.device}")
        self.cap.set(cv2.CAP_PROP_FOURCC, cv2.VideoWriter_fourcc(*"MJPG"))
        self.cap.set(cv2.CAP_PROP_FRAME_WIDTH, self.width)
        self.cap.set(cv2.CAP_PROP_FRAME_HEIGHT, self.height)
        _reglages_stables(self.device, self.focus)
        return self

    def read(self):
        ok, frame = self.cap.read()
        return frame if ok else None

    def release(self):
        if self.cap is not None:
            self.cap.release()
            self.cap = None

    def __enter__(self):
        return self.open()

    def __exit__(self, *args):
        self.release()
