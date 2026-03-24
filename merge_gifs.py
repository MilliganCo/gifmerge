#!/usr/bin/env python3
"""
Скрипт объединения GIF-файлов из папки в один GIF.
Каждый GIF используется 3 раза, в случайном порядке, без соседних дубликатов.
Сохраняет оригинальные задержки кадров.
"""

import random
from pathlib import Path

from PIL import Image
from tkinter import Tk, filedialog


def _get_ffmpeg_exe() -> tuple[str, str | None] | None:
    """Возвращает (ffmpeg_path, ffprobe_path или None) или None."""
    import shutil
    try:
        import imageio_ffmpeg
        ffmpeg = imageio_ffmpeg.get_ffmpeg_exe()
        ffprobe = str(Path(ffmpeg).parent / ('ffprobe' + Path(ffmpeg).suffix))
        return ffmpeg, ffprobe if Path(ffprobe).exists() else None
    except Exception:
        pass
    if shutil.which('ffmpeg'):
        ffprobe = shutil.which('ffprobe')
        return 'ffmpeg', ffprobe
    return None


def _read_gif_via_ffmpeg(path: Path) -> list[tuple[Image.Image, int]] | None:
    """Читает GIF через ffmpeg (обходит баг Pillow)."""
    import json
    import shutil
    import subprocess
    import tempfile
    exe = _get_ffmpeg_exe()
    if not exe:
        return None
    ffmpeg_exe, ffprobe_exe = exe
    out_dir = None
    try:
        durations = []
        if ffprobe_exe:
            probe = subprocess.run(
                [ffprobe_exe, '-v', 'quiet', '-print_format', 'json',
                 '-show_frames', '-select_streams', 'v:0', str(path)],
                capture_output=True, text=True, timeout=10,
            )
            if probe.returncode == 0 and probe.stdout:
                data = json.loads(probe.stdout)
                for f in data.get('frames', []):
                    t = float(f.get('pkt_duration_time', 0.1) or 0.1)
                    durations.append(int(t * 1000))
        if not durations:
            durations = [100]
        out_dir = Path(tempfile.mkdtemp())
        subprocess.run(
            [ffmpeg_exe, '-y', '-i', str(path), '-vsync', '0',
             str(out_dir / 'frame_%04d.png')],
            capture_output=True, check=True, timeout=60,
        )
        frames_paths = sorted(out_dir.glob('frame_*.png'))
        if not frames_paths:
            return None
        result = []
        for i, fp in enumerate(frames_paths):
            img = Image.open(fp).convert('RGBA')
            dur = durations[min(i, len(durations) - 1)]
            result.append((img, dur))
        return result
    except (FileNotFoundError, subprocess.CalledProcessError, OSError, json.JSONDecodeError):
        return None
    finally:
        if out_dir and out_dir.exists():
            shutil.rmtree(out_dir, ignore_errors=True)


def get_gif_frames(path: Path) -> list[tuple[Image.Image, int]]:
    """Читает все кадры GIF с их задержками. Возвращает [(frame, duration_ms), ...]"""
    img = Image.open(path)
    frames = []
    try:
        while True:
            frame = img.copy()
            if frame.mode != 'RGBA':
                frame = frame.convert('RGBA')
            duration = img.info.get('duration', 100)
            frames.append((frame, duration))
            img.seek(img.tell() + 1)
    except EOFError:
        return frames
    except Exception:
        pass
    # Pillow не справился (баг dispose_extent) — пробуем ffmpeg
    ffmpeg_frames = _read_gif_via_ffmpeg(path)
    if ffmpeg_frames:
        return ffmpeg_frames
    raise RuntimeError(
        f'Не удалось прочитать GIF: {path.name}. '
        'Установите: pip install imageio[ffmpeg]  или ffmpeg (https://ffmpeg.org) в PATH.'
    )


def shuffle_no_consecutive(items: list) -> list:
    """
    Перемешивает список так, чтобы одинаковые элементы не шли подряд.
    Использует жадный алгоритм: на каждом шаге выбираем случайный элемент,
    отличный от предыдущего.
    """
    if not items:
        return []
    if len(items) == 1:
        return items

    # Группируем по идентичности (для нас важен путь к GIF)
    pool = list(items)
    random.shuffle(pool)

    result = [pool.pop()]
    last = result[0]

    while pool:
        # Собираем кандидатов, отличных от last
        candidates = [i for i, x in enumerate(pool) if x != last]
        if not candidates:
            # Все оставшиеся совпадают с last — берём любого, нарушение неизбежно
            idx = random.randint(0, len(pool) - 1)
        else:
            idx = random.choice(candidates)
        item = pool.pop(idx)
        result.append(item)
        last = item

    return result


def select_folder() -> Path | None:
    """Открывает диалог выбора папки."""
    root = Tk()
    root.withdraw()
    root.attributes('-topmost', True)
    path = filedialog.askdirectory(title='Выберите папку с GIF-файлами')
    root.destroy()
    return Path(path) if path else None


def _merge_via_ffmpeg_concat(
    shuffled: list[Path], out_path: Path
) -> bool:
    """Объединяет GIF через ffmpeg concat (без загрузки в память)."""
    import subprocess
    import tempfile
    exe = _get_ffmpeg_exe()
    if not exe:
        return False
    ffmpeg_exe = exe[0]
    list_path = None
    try:
        with tempfile.NamedTemporaryFile(
            mode='w', suffix='.txt', delete=False, encoding='utf-8'
        ) as f:
            for p in shuffled:
                path_str = str(p.resolve()).replace("'", "'\\''")
                f.write(f"file '{path_str}'\n")
            list_path = f.name
        r = subprocess.run(
            [ffmpeg_exe, '-y', '-f', 'concat', '-safe', '0', '-i', list_path,
             '-c', 'copy', str(out_path)],
            capture_output=True, timeout=600,
        )
        if r.returncode != 0:
            # Разные размеры/форматы — перекодируем (всё ещё стриминг)
            subprocess.run(
                [ffmpeg_exe, '-y', '-f', 'concat', '-safe', '0', '-i', list_path,
                 str(out_path)],
                capture_output=True, check=True, timeout=600,
            )
        return True
    except (subprocess.CalledProcessError, OSError):
        return False
    finally:
        if list_path:
            Path(list_path).unlink(missing_ok=True)


def main() -> None:
    folder = select_folder()
    if not folder or not folder.exists():
        print('Папка не выбрана.')
        return

    gif_files = sorted(folder.glob('*.gif'))
    if not gif_files:
        print(f'В папке {folder} нет GIF-файлов.')
        return

    if len(gif_files) == 1:
        print('Один GIF в папке — невозможно избежать соседних дубликатов.')
        return

    # Каждый GIF по 3 раза
    gif_paths = [gif_files[i] for i in range(len(gif_files)) for _ in range(3)]
    shuffled = shuffle_no_consecutive(gif_paths)
    out_path = folder / 'merged.gif'

    # Сначала пробуем ffmpeg concat — без загрузки кадров в память
    if _merge_via_ffmpeg_concat(shuffled, out_path):
        print(f'Готово: {out_path}')
        print(f'Объединено {len(gif_files)} GIF в один файл.')
        return

    # Fallback: Pillow (загружает все кадры в память — может быть 16+ ГБ)
    print('FFmpeg недоступен. Используем Pillow — потребуется много RAM!')
    print('Рекомендуется: pip install imageio[ffmpeg]')
    all_frames: list[Image.Image] = []
    all_durations: list[int] = []

    for path in shuffled:
        frames_data = get_gif_frames(path)
        for frame, duration in frames_data:
            all_frames.append(frame)
            all_durations.append(duration)

    if not all_frames:
        print('Не удалось прочитать кадры из GIF.')
        return

    first = all_frames[0]
    rest = all_frames[1:]
    first.save(
        out_path,
        save_all=True,
        append_images=rest,
        duration=all_durations,
        loop=0,
    )

    print(f'Готово: {out_path}')
    print(f'Объединено {len(gif_files)} GIF в {len(all_frames)} кадров.')


if __name__ == '__main__':
    main()
