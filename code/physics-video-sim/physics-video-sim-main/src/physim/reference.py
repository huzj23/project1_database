"""Import the vendored Kubric fork from an unmodified PhyCo-Sim checkout."""

from __future__ import annotations

import importlib
import importlib.util
import os
import shutil
import sys
import types
from pathlib import Path


def _install_tensorflow_io_compat() -> None:
    """Provide Kubric's small local-file TensorFlow surface when TF is absent.

    The PhyCo-Sim fork imports TensorFlow for ``tf.io.gfile`` even though the
    rolling physics and GUI-preview paths only use ordinary local files.  A
    full TensorFlow install is unnecessary for those paths, so keep this shim
    project-side and leave the vendored checkout unchanged.
    """
    if "tensorflow" in sys.modules or importlib.util.find_spec("tensorflow") is not None:
        return

    tensorflow = types.ModuleType("tensorflow")
    tensorflow.__spec__ = importlib.util.spec_from_loader("tensorflow", loader=None)
    gfile = types.SimpleNamespace(
        GFile=open,
        copy=lambda source, target, overwrite=False: _copy_file(
            source, target, overwrite=overwrite
        ),
        exists=os.path.exists,
        isdir=os.path.isdir,
        listdir=os.listdir,
        makedirs=lambda path: os.makedirs(path, exist_ok=True),
        remove=os.remove,
        rename=os.replace,
        glob=__import__("glob").glob,
        walk=os.walk,
    )
    tensorflow.io = types.SimpleNamespace(gfile=gfile)  # type: ignore[attr-defined]
    sys.modules["tensorflow"] = tensorflow


def _copy_file(source, target, overwrite: bool = False) -> None:
    target = Path(target)
    if target.exists() and not overwrite:
        raise FileExistsError(target)
    target.parent.mkdir(parents=True, exist_ok=True)
    shutil.copyfile(source, target)


def load_phyco_kubric(phyco_sim_root: str | Path):
    kubric_root = Path(phyco_sim_root).resolve() / "kubric"
    package = kubric_root / "kubric" / "__init__.py"
    if not package.is_file():
        raise FileNotFoundError(f"PhyCo-Sim Kubric package not found: {package}")
    root_text = str(kubric_root)
    if root_text not in sys.path:
        sys.path.insert(0, root_text)
    _install_tensorflow_io_compat()
    module = importlib.import_module("kubric")
    loaded = Path(module.__file__).resolve()
    if kubric_root not in loaded.parents:
        raise RuntimeError(f"Loaded Kubric from {loaded}, expected below {kubric_root}")
    return module
