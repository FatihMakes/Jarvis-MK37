# actions/file_controller.py
# File management — create, delete, move, rename, list, find, organize

import shutil
from pathlib import Path
from datetime import datetime
import send2trash


def _confirm(prompt: str, player=None) -> bool:
    """
    Requires explicit user approval before a destructive file operation.
    Falls back to terminal input when no UI player is available.
    """
    if player and hasattr(player, "root"):
        import tkinter.messagebox as mb
        return mb.askyesno(
            "JARVIS — Action Requires Approval",
            prompt,
            parent=player.root
        )
    answer = input(f"[JARVIS SANDBOX] {prompt} [Y/N]: ").strip().lower()
    return answer in ("y", "yes")

def _get_desktop() -> Path:
    """Returns desktop path — works on Windows, Mac, Linux."""
    return Path.home() / "Desktop"


def _get_downloads() -> Path:
    return Path.home() / "Downloads"


def _resolve_path(raw: str) -> Path:
    """
    Resolves a path from user input.
    Supports shortcuts: 'desktop', 'downloads', 'documents', 'home'
    """
    shortcuts = {
        "desktop":   Path.home() / "Desktop",
        "downloads": Path.home() / "Downloads",
        "documents": Path.home() / "Documents",
        "pictures":  Path.home() / "Pictures",
        "music":     Path.home() / "Music",
        "videos":    Path.home() / "Videos",
        "home":      Path.home(),
    }
    lower = raw.strip().lower()
    if lower in shortcuts:
        return shortcuts[lower]
    return Path(raw).expanduser()


def _format_size(bytes_size: int) -> str:
    """Converts bytes to human readable format."""
    for unit in ["B", "KB", "MB", "GB", "TB"]:
        if bytes_size < 1024:
            return f"{bytes_size:.1f} {unit}"
        bytes_size /= 1024
    return f"{bytes_size:.1f} TB"


def list_files(path: str = "desktop", show_hidden: bool = False) -> str:
    """Lists files and folders in a directory."""
    try:
        target = _resolve_path(path)
        if not target.exists():
            return f"Path not found: {target}"
        if not target.is_dir():
            return f"Not a directory: {target}"

        items = []
        for item in sorted(target.iterdir()):
            if not show_hidden and item.name.startswith("."):
                continue
            if item.is_dir():
                items.append(f"📁 {item.name}/")
            else:
                size = _format_size(item.stat().st_size)
                items.append(f"📄 {item.name} ({size})")

        if not items:
            return f"Directory is empty: {target}"

        return f"Contents of {target.name}/ ({len(items)} items):\n" + "\n".join(items)

    except PermissionError:
        return f"Permission denied: {path}"
    except Exception as e:
        return f"Error listing files: {e}"


def create_file(path: str, content: str = "") -> str:
    """Creates a new file with optional content."""
    try:
        target = Path(path).expanduser()
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(content, encoding="utf-8")
        return f"File created: {target.name}"
    except Exception as e:
        return f"Could not create file: {e}"


def create_folder(path: str) -> str:
    """Creates a new folder (and parent folders if needed)."""
    try:
        target = Path(path).expanduser()
        target.mkdir(parents=True, exist_ok=True)
        return f"Folder created: {target}"
    except Exception as e:
        return f"Could not create folder: {e}"


def delete_file(path: str, confirm: bool = True) -> str:
    """
    Deletes a file or folder.
    Moves to Recycle Bin on Windows if possible, otherwise permanent delete.
    """
    try:
        target = Path(path).expanduser()
        if not target.exists():
            return f"Not found: {path}"

        try:

            send2trash.send2trash(str(target))
            return f"Moved to Recycle Bin: {target.name}"
        except ImportError:
            pass

        # Fallback: permanent delete
        if target.is_dir():
            shutil.rmtree(target)
            return f"Folder deleted permanently: {target.name}"
        else:
            target.unlink()
            return f"File deleted permanently: {target.name}"

    except PermissionError:
        return f"Permission denied: {path}"
    except Exception as e:
        return f"Could not delete: {e}"


def move_file(source: str, destination: str) -> str:
    """Moves a file or folder to a new location."""
    try:
        src  = Path(source).expanduser()
        dst  = _resolve_path(destination)

        if not src.exists():
            return f"Source not found: {source}"

        if dst.is_dir():
            dst = dst / src.name

        dst.parent.mkdir(parents=True, exist_ok=True)
        shutil.move(str(src), str(dst))
        return f"Moved: {src.name} → {dst.parent.name}/"

    except Exception as e:
        return f"Could not move: {e}"


def copy_file(source: str, destination: str) -> str:
    """Copies a file or folder."""
    try:
        src = Path(source).expanduser()
        dst = _resolve_path(destination)

        if not src.exists():
            return f"Source not found: {source}"

        if dst.is_dir():
            dst = dst / src.name

        dst.parent.mkdir(parents=True, exist_ok=True)

        if src.is_dir():
            shutil.copytree(str(src), str(dst))
        else:
            shutil.copy2(str(src), str(dst))

        return f"Copied: {src.name} → {dst.parent.name}/"

    except Exception as e:
        return f"Could not copy: {e}"


def rename_file(path: str, new_name: str) -> str:
    """Renames a file or folder."""
    try:
        target   = Path(path).expanduser()
        new_path = target.parent / new_name

        if not target.exists():
            return f"Not found: {path}"
        if new_path.exists():
            return f"A file named '{new_name}' already exists."

        target.rename(new_path)
        return f"Renamed: {target.name} → {new_name}"

    except Exception as e:
        return f"Could not rename: {e}"


def read_file(path: str, max_chars: int = 3000) -> str:
    """Reads and returns the content of a text file."""
    try:
        target = Path(path).expanduser()
        if not target.exists():
            return f"File not found: {path}"
        if not target.is_file():
            return f"Not a file: {path}"

        content = target.read_text(encoding="utf-8", errors="ignore")
        if len(content) > max_chars:
            content = content[:max_chars] + f"\n\n... (truncated, {len(content)} total chars)"
        return content

    except Exception as e:
        return f"Could not read file: {e}"


def write_file(path: str, content: str, append: bool = False) -> str:
    """Writes or appends content to a file."""
    try:
        target = Path(path).expanduser()
        target.parent.mkdir(parents=True, exist_ok=True)
        mode = "a" if append else "w"
        with open(target, mode, encoding="utf-8") as f:
            f.write(content)
        action = "Appended to" if append else "Written to"
        return f"{action}: {target.name}"
    except Exception as e:
        return f"Could not write file: {e}"


def find_files(name: str = "", extension: str = "", path: str = "home",
               max_results: int = 20) -> str:
    """
    Searches for files by name or extension.
    Example: find_files(extension=".pdf", path="documents")
    """
    try:
        search_path = _resolve_path(path)
        if not search_path.exists():
            return f"Search path not found: {path}"

        results = []
        pattern = f"*{extension}" if extension else "*"

        for item in search_path.rglob(pattern):
            if item.is_file():
                if name and name.lower() not in item.name.lower():
                    continue
                size = _format_size(item.stat().st_size)
                results.append(f"📄 {item.name} ({size}) — {item.parent}")
                if len(results) >= max_results:
                    break

        if not results:
            query = name or extension or "files"
            return f"No {query} found in {search_path.name}/"

        return f"Found {len(results)} file(s):\n" + "\n".join(results)

    except Exception as e:
        return f"Search error: {e}"


def get_largest_files(path: str = "home", count: int = 10) -> str:
    """Returns the largest files in a directory."""
    try:
        search_path = _resolve_path(path)
        if not search_path.exists():
            return f"Path not found: {path}"

        files = []
        for item in search_path.rglob("*"):
            if item.is_file():
                try:
                    files.append((item.stat().st_size, item))
                except Exception:
                    continue

        files.sort(reverse=True)
        top = files[:count]

        if not top:
            return "No files found."

        lines = [f"Top {len(top)} largest files in {search_path.name}/:\n"]
        for size, f in top:
            lines.append(f"  {_format_size(size):>10}  {f.name}  ({f.parent})")

        return "\n".join(lines)

    except Exception as e:
        return f"Error: {e}"


def get_disk_usage(path: str = "home") -> str:
    """Returns disk usage information."""
    try:
        target = _resolve_path(path)
        usage  = shutil.disk_usage(target)
        total  = _format_size(usage.total)
        used   = _format_size(usage.used)
        free   = _format_size(usage.free)
        pct    = usage.used / usage.total * 100

        return (
            f"Disk usage for {target}:\n"
            f"  Total : {total}\n"
            f"  Used  : {used} ({pct:.1f}%)\n"
            f"  Free  : {free}"
        )
    except Exception as e:
        return f"Could not get disk usage: {e}"


def organize_desktop() -> str:
    """
    Organizes the desktop by grouping files into folders by type.
    Creates folders: Images, Documents, Videos, Music, Archives, Others
    """
    try:
        desktop = _get_desktop()
        type_map = {
            "Images":    [".jpg", ".jpeg", ".png", ".gif", ".bmp", ".webp", ".svg", ".ico"],
            "Documents": [".pdf", ".doc", ".docx", ".txt", ".xls", ".xlsx", ".ppt", ".pptx", ".csv"],
            "Videos":    [".mp4", ".avi", ".mkv", ".mov", ".wmv", ".flv", ".webm"],
            "Music":     [".mp3", ".wav", ".flac", ".aac", ".ogg", ".wma"],
            "Archives":  [".zip", ".rar", ".7z", ".tar", ".gz"],
            "Code":      [".py", ".js", ".html", ".css", ".json", ".xml", ".ts", ".cpp", ".java"],
        }

        moved    = []
        skipped  = []

        for item in desktop.iterdir():

            if item.is_dir() or item.name.startswith("."):
                continue

            ext        = item.suffix.lower()
            target_dir = None

            for folder, extensions in type_map.items():
                if ext in extensions:
                    target_dir = desktop / folder
                    break

            if target_dir is None:
                target_dir = desktop / "Others"

            target_dir.mkdir(exist_ok=True)
            new_path = target_dir / item.name

            if new_path.exists():
                skipped.append(item.name)
                continue

            shutil.move(str(item), str(new_path))
            moved.append(f"{item.name} → {target_dir.name}/")

        result = f"Desktop organized. {len(moved)} files moved."
        if moved:
            result += "\n" + "\n".join(moved[:10])
            if len(moved) > 10:
                result += f"\n... and {len(moved)-10} more."
        if skipped:
            result += f"\n{len(skipped)} files skipped (already exist)."

        return result

    except Exception as e:
        return f"Could not organize desktop: {e}"


def get_file_info(path: str) -> str:
    """Returns detailed information about a file."""
    try:
        target = Path(path).expanduser()
        if not target.exists():
            return f"Not found: {path}"

        stat = target.stat()
        info = {
            "Name":     target.name,
            "Type":     "Folder" if target.is_dir() else "File",
            "Size":     _format_size(stat.st_size),
            "Location": str(target.parent),
            "Created":  datetime.fromtimestamp(stat.st_ctime).strftime("%Y-%m-%d %H:%M"),
            "Modified": datetime.fromtimestamp(stat.st_mtime).strftime("%Y-%m-%d %H:%M"),
            "Extension": target.suffix or "None",
        }

        return "\n".join(f"  {k}: {v}" for k, v in info.items())

    except Exception as e:
        return f"Could not get file info: {e}"

def file_controller(
    parameters: dict,
    response=None,
    player=None,
    session_memory=None
) -> str:
    action  = (parameters or {}).get("action", "").lower().strip()
    path    = (parameters or {}).get("path", "desktop")
    name    = (parameters or {}).get("name", "")
    content = (parameters or {}).get("content", "")

    def _full_path(p: str, n: str) -> str:
        base = _resolve_path(p)
        if n:
            return str(base / n)
        return str(base)

    result = "Unknown action."

    try:
        if action == "list":
            result = list_files(path)

        elif action == "create_file":
            full = _full_path(path, name)
            result = create_file(full, content=content)

        elif action == "create_folder":
            full = _full_path(path, name)
            result = create_folder(full)

        elif action == "delete":
            full = _full_path(path, name)
            approved = _confirm(
                f"JARVIS wants to delete:\n  {full}\n\nAllow?",
                player
            )
            if not approved:
                return "Action blocked by user."
            result = delete_file(full)

        elif action == "move":
            full = _full_path(path, name)
            approved = _confirm(
                f"JARVIS wants to move:\n  {full}\n  -> {parameters.get('destination', '?')}\n\nAllow?",
                player
            )
            if not approved:
                return "Action blocked by user."
            result = move_file(full, parameters.get("destination", ""))

        elif action == "copy":
            full = _full_path(path, name)
            result = copy_file(full, parameters.get("destination", ""))

        elif action == "rename":
            full = _full_path(path, name)
            result = rename_file(full, parameters.get("new_name", ""))

        elif action == "read":
            full = _full_path(path, name)
            result = read_file(full)

        elif action == "write":
            full = _full_path(path, name)
            approved = _confirm(
                f"JARVIS wants to write/overwrite:\n  {full}\n\nAllow?",
                player
            )
            if not approved:
                return "Action blocked by user."
            result = write_file(
                full,
                content=content,
                append=parameters.get("append", False)
            )

        elif action == "find":
            result = find_files(
                name=name or parameters.get("name", ""),
                extension=parameters.get("extension", ""),
                path=path,
                max_results=parameters.get("max_results", 20)
            )

        elif action == "largest":
            result = get_largest_files(
                path=path,
                count=parameters.get("count", 10)
            )

        elif action == "disk_usage":
            result = get_disk_usage(path)

        elif action == "organize_desktop":
            approved = _confirm(
                "JARVIS wants to organize your Desktop by moving files into folders.\n\nAllow?",
                player
            )
            if not approved:
                return "Action blocked by user."
            result = organize_desktop()

        elif action == "info":
            full = _full_path(path, name)
            result = get_file_info(full)

        else:
            result = f"Unknown action: '{action}'"

    except Exception as e:
        result = f"File controller error: {e}"

    if player:
        player.write_log(f"[file] {result[:60]}")

    return result