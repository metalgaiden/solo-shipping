import os
import pygame
from glob import glob

SOUNDS_DIR = os.path.join(os.path.dirname(__file__), "sounds")

_bgm_path = None
_sfx = {}
_initialized = False
_music_volume = 0.6
_sfx_volume = 1.0

def init_audio():
    global _initialized, _bgm_path, _sfx
    if _initialized:
        return
    try:
        pygame.mixer.pre_init(44100, -16, 2, 512)
        pygame.init()
        pygame.mixer.init()
    except Exception:
        return

    for path in glob(os.path.join(SOUNDS_DIR, "*")):
        name = os.path.basename(path).lower()
        # heuristics to find the BGM file
        if ("solo" in name and ("bgm" in name or "music" in name)) or "solo shipping" in name:
            _bgm_path = path
        # alert nearby guard sfx
        if "alert" in name and "guard" in name:
            try:
                _sfx["alert_guard"] = pygame.mixer.Sound(path)
            except Exception:
                pass
        # game over SFX
        if ("game" in name and "over" in name) or "gameover" in name or "game_over" in name:
            try:
                _sfx["game_over"] = pygame.mixer.Sound(path)
            except Exception:
                pass
        # level clear SFX
        if ("level" in name and "clear" in name) or "levelclear" in name or "level_clear" in name:
            try:
                _sfx["level_clear"] = pygame.mixer.Sound(path)
            except Exception:
                pass
        # magic / spell SFX
        if "magic" in name or "spell" in name:
            try:
                _sfx["magic"] = pygame.mixer.Sound(path)
            except Exception:
                pass

    _initialized = True

def get_music_volume() -> float:
    return _music_volume

def set_music_volume(vol: float) -> None:
    global _music_volume
    _music_volume = max(0.0, min(1.0, round(vol, 1)))
    try:
        pygame.mixer.music.set_volume(_music_volume)
    except Exception:
        pass

def get_sfx_volume() -> float:
    return _sfx_volume

def set_sfx_volume(vol: float) -> None:
    global _sfx_volume
    _sfx_volume = max(0.0, min(1.0, round(vol, 1)))

def play_bgm(loop=-1):
    if not _initialized:
        init_audio()
    if _bgm_path:
        try:
            pygame.mixer.music.load(_bgm_path)
            pygame.mixer.music.set_volume(_music_volume)
            pygame.mixer.music.play(loop)
        except Exception:
            pass

def stop_bgm():
    try:
        pygame.mixer.music.stop()
    except Exception:
        pass

def play_sfx(name, volume=1.0):
    if not _initialized:
        init_audio()
    s = _sfx.get(name)
    if s:
        s.set_volume(volume * _sfx_volume)
        try:
            s.play()
        except Exception:
            pass