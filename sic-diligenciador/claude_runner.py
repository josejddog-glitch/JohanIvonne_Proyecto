"""Wrapper para invocar Claude Code CLI desde Python.

Asume que `claude` está en el PATH y la sesión Pro está activa.
"""
from __future__ import annotations

import shutil
import subprocess
from pathlib import Path


class ClaudeRunnerError(RuntimeError):
    pass


def _resolver_claude() -> str:
    """Resuelve la ruta absoluta del CLI de Claude.

    En Windows, `claude` puede ser `claude.cmd` y subprocess.run no lo encuentra
    si solo se pasa el nombre. shutil.which sí localiza el .cmd.
    """
    ruta = shutil.which("claude") or shutil.which("claude.cmd") or shutil.which("claude.exe")
    if not ruta:
        raise ClaudeRunnerError(
            "No se encontró 'claude' en el PATH. Verifica que Claude Code está instalado "
            "(npm i -g @anthropic-ai/claude-code) y reabre la terminal."
        )
    return ruta


def ejecutar(
    prompt: str,
    cwd: Path,
    timeout: int = 1200,
    skip_permissions: bool = True,
    model: str | None = "sonnet",
    append_system_prompt: str | None = None,
    add_dirs: list[Path] | None = None,
) -> tuple[int, str, str]:
    """Invoca `claude -p` con el prompt y captura stdout/stderr.

    Args:
        prompt: instrucción imperativa concreta para Claude (la "tarea" del usuario).
        cwd: directorio de trabajo.
        timeout: máximo de segundos.
        skip_permissions: si True, agrega --dangerously-skip-permissions
            (equivalente a bypassPermissions, pero la flag canónica). Necesario
            para que Claude pueda escribir archivos en `salida/` sin prompts.
        model: alias del modelo a usar ('sonnet' = más rápido, 'opus' = más potente).
            Default 'sonnet' por velocidad. None = usa el del settings global.
        append_system_prompt: texto que se agrega al system prompt por defecto.
        add_dirs: directorios adicionales a los que Claude puede acceder.

    Returns:
        (returncode, stdout, stderr).
    """
    claude_path = _resolver_claude()
    # --output-format json: envuelve la respuesta en un sobre JSON estructurado
    # ({type, result, session_id, ...}) que evita pérdida de stdout en Windows
    # cuando la respuesta es grande. Mucho más robusto que el modo "text" default.
    cmd: list[str] = [claude_path, "-p", prompt, "--output-format", "json"]
    if skip_permissions:
        cmd.append("--dangerously-skip-permissions")
    if model:
        cmd.extend(["--model", model])
    if append_system_prompt:
        cmd.extend(["--append-system-prompt", append_system_prompt])
    if add_dirs:
        cmd.append("--add-dir")
        cmd.extend(str(d) for d in add_dirs)
    try:
        proc = subprocess.run(
            cmd,
            cwd=str(cwd),
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=timeout,
            shell=False,
        )
    except subprocess.TimeoutExpired as e:
        raise ClaudeRunnerError(f"Timeout tras {timeout}s ejecutando claude CLI") from e

    if proc.returncode != 0:
        raise ClaudeRunnerError(
            f"claude CLI retornó código {proc.returncode}.\nSTDERR:\n{proc.stderr}\nSTDOUT:\n{proc.stdout}"
        )

    return proc.returncode, proc.stdout, proc.stderr
