"""Zappa lifecycle hook -- see zappa_settings.json's "callbacks": {"zip": ...}.

backend/optimization_cpsat.py and backend/utils.py both do a bare
`import model_common`, resolved locally via project/settings.py's
sys.path.insert(0, SERVER_DIR) trick, which points at the *sibling*
code/server/ directory. That works fine for local `manage.py runserver`
(code/server/ sits right there on disk next to code/client/), but Zappa
only zips up the directory it's run from -- code/client/, since that's
this stage's project_path -- so code/server/ never makes it into the
Lambda package. Every request then 500s at Django's URLconf import time
(backend/urls.py -> views.py -> utils.py -> "from model_common import
student_type_key"), which is why even a bare GET / fails.

This hook runs right before Zappa builds the deployment zip and copies
code/server/model_common.py into code/client/ itself, next to manage.py.
That location *is* inside the package and *is* on sys.path at Lambda
runtime, so the same bare `import model_common` resolves there too. The
copy is regenerated on every deploy/update and is gitignored --
code/server/model_common.py stays the one real source of truth; nothing
here is meant to be hand-edited.
"""
import shutil
from pathlib import Path


def pre_zip(zappa_cli=None):
    client_dir = Path(__file__).resolve().parent
    src = client_dir.parent / "server" / "model_common.py"
    dst = client_dir / "model_common.py"
    shutil.copy2(src, dst)
    print(f"[deploy_hooks] synced {src} -> {dst}")
