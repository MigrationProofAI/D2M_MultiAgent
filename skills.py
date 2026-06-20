"""Skills with PROGRESSIVE DISCLOSURE. Three levels of cost:

  index   -- only name + description per skill. ALWAYS in context. Tiny.
  body    -- the SKILL.md instructions. Loaded ONLY when the skill is triggered (load_skill).
  scripts -- EXECUTED, never read. Only their stdout enters context (~0 cost), never the source.

A skill is a folder: skills/<name>/SKILL.md (frontmatter: name, description, when_to_trigger,
verification) + optional linked files + optional scripts/."""
import os
import re
import sys
import subprocess
from pathlib import Path

SKILLS_DIR = Path(os.getenv("RIG_SKILLS_DIR", "skills"))


def _parse(md_path: Path):
    text = md_path.read_text(encoding="utf-8")
    m = re.match(r"^---\s*\n(.*?)\n---\s*\n(.*)$", text, re.S)
    if not m:
        return {}, text.strip()
    fm = {}
    for line in m.group(1).splitlines():
        if ":" in line:
            k, v = line.split(":", 1)
            fm[k.strip()] = v.strip()
    return fm, m.group(2).strip()


class Skill:
    def __init__(self, path: Path):
        self.dir = path
        self.name = path.name
        self.frontmatter, self._body = _parse(path / "SKILL.md")
        self.description = self.frontmatter.get("description", "")
        self.when = self.frontmatter.get("when_to_trigger", "")

    def body(self) -> str:
        return self._body

    def scripts(self):
        sd = self.dir / "scripts"
        return [p.name for p in sd.glob("*.py")] if sd.exists() else []


class SkillRegistry:
    def __init__(self, skills_dir=SKILLS_DIR):
        self._base = Path(skills_dir)
        self.skills = {}
        self._scan()
        self.loaded = {}              # name -> body (only triggered skills land here)
        self.script_result_chars = 0  # cumulative chars of script OUTPUT that entered context

    def _scan(self):
        self.skills = {}
        if self._base.exists():
            for p in sorted(self._base.iterdir()):
                if p.is_dir() and (p / "SKILL.md").exists():
                    self.skills[p.name] = Skill(p)

    def refresh(self):
        """Re-scan skills/ so a freshly PROMOTED skill is in the index + load_skill-able THIS turn
        (the index is re-injected from the live registry every turn). Keeps already-loaded bodies."""
        self._scan()
        return sorted(self.skills)

    def index(self) -> str:
        """The ALWAYS-in-context index: name + description only. Load a body with load_skill(name)."""
        lines = ["AVAILABLE SKILLS (call load_skill(name) to load a skill's full instructions ONLY when "
                 "it applies; the body is not in context until then):"]
        for s in self.skills.values():
            lines.append(f"- {s.name}: {s.description}")
        return "\n".join(lines)

    def load_body(self, name: str) -> str:
        s = self.skills.get(name)
        if not s:
            return f"ERROR: no skill '{name}' (available: {', '.join(self.skills)})"
        self.loaded[name] = s.body()       # progressive disclosure: now (and only now) it's in context
        return s.body()

    def run_script(self, name: str, script: str, args=None) -> str:
        """EXECUTE a skill's script; return only its stdout. The source NEVER enters context."""
        s = self.skills.get(name)
        if not s:
            return f"ERROR: no skill '{name}'"
        path = s.dir / "scripts" / script
        if not path.exists():
            return f"ERROR: no script '{script}' in skill '{name}'"
        try:
            proc = subprocess.run([sys.executable, str(path)] + [str(a) for a in (args or [])],
                                  capture_output=True, text=True, timeout=90, cwd=os.getcwd())
            out = (proc.stdout or proc.stderr or "").strip()[:1000]
            self.script_result_chars += len(out)
            return out or f"(script exited {proc.returncode} with no output)"
        except Exception as e:
            return f"ERROR running {script}: {type(e).__name__}: {e}"

    def meter(self, ntok) -> str:
        idx = ntok(self.index())
        loaded = sum(ntok(b) for b in self.loaded.values())
        full = sum(ntok(s.body()) for s in self.skills.values())
        return (f"skills: {len(self.skills)} | index: {idx} tok (always in context) | "
                f"bodies loaded: {len(self.loaded)}/{len(self.skills)} ({loaded} tok) | "
                f"full-disclosure would cost: {full} tok | scripts: result-only (~{self.script_result_chars // 4} tok)")
