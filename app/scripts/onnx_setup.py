#!/usr/bin/env python3
"""Download the ALL_MINILM_L12_V2 ONNX model and load it into Oracle.

Runs once during Codespace post-create after `bootstrap.py`. Idempotent.

After this step the AGENT schema has a mining model named ALL_MINILM_L12_V2
that the workshop's notebook uses through `OracleEmbeddings`:

    embeddings = OracleEmbeddings(
        conn=oracle_client,
        params={"provider": "database", "model": "ALL_MINILM_L12_V2"},
    )

The model produces 384-dim float vectors.
"""

from __future__ import annotations

import os
import sys
import urllib.request
from pathlib import Path

import oracledb
from langchain_oracledb import OracleEmbeddings


# Public, pre-converted ONNX model from OCI's GenAI samples (same one
# the reference enterprise_data_agent_harness_workshop uses).
ONNX_URL = os.environ.get(
    "ONNX_URL",
    "https://objectstorage.us-ashburn-1.oraclecloud.com/p/"
    "fsSt0g4PNHevuJxd6t2qBNcyAfbF0Pf6cAKi6pSjUUjpvWQVdsiDjGdjFXFnstxC/n/"
    "adwc4pm/b/OML-Resources/o/all_MiniLM_L12_v2_augmented.zip",
)
MODEL_NAME = os.environ.get("ONNX_EMBED_MODEL", "ALL_MINILM_L12_V2")
ONNX_FILENAME = os.environ.get("ONNX_FILENAME", "all_MiniLM_L12_v2.onnx")

CACHE_DIR = Path(os.environ.get("ONNX_CACHE_DIR", "/tmp/onnx_models"))
ORACLE_DIR_NAME = os.environ.get("ONNX_ORACLE_DIRECTORY", "ONNX_DUMP")

AGENT_USER = os.environ.get("AGENT_USER", "AGENT")
AGENT_PASSWORD = os.environ.get("AGENT_PASSWORD", "AgentPwd_2025")
DSN = os.environ.get("ORACLE_DSN", "localhost:1521/FREEPDB1")


def _model_already_loaded(conn) -> bool:
    cur = conn.cursor()
    cur.execute(
        "SELECT COUNT(*) FROM user_mining_models WHERE model_name = :n",
        n=MODEL_NAME,
    )
    (n,) = cur.fetchone()
    return n > 0


def _download_and_extract() -> Path:
    """Download the model zip and return the path to the .onnx file."""
    CACHE_DIR.mkdir(parents=True, exist_ok=True)
    onnx_path = CACHE_DIR / ONNX_FILENAME
    if onnx_path.exists() and onnx_path.stat().st_size > 0:
        print(f"[onnx_setup] reusing cached {onnx_path} ({onnx_path.stat().st_size:,} bytes).")
        return onnx_path

    zip_path = CACHE_DIR / "model.zip"
    print(f"[onnx_setup] downloading {ONNX_URL} → {zip_path} …")
    urllib.request.urlretrieve(ONNX_URL, zip_path)

    print(f"[onnx_setup] extracting {ONNX_FILENAME} from {zip_path} …")
    import zipfile
    with zipfile.ZipFile(zip_path) as zf:
        candidates = [n for n in zf.namelist() if n.endswith(".onnx")]
        if not candidates:
            raise RuntimeError(f"no .onnx file in archive {zip_path}")
        chosen = candidates[0]
        with zf.open(chosen) as src, open(onnx_path, "wb") as dst:
            dst.write(src.read())
    print(f"[onnx_setup] extracted to {onnx_path} ({onnx_path.stat().st_size:,} bytes).")
    return onnx_path


def main() -> int:
    print("=" * 60)
    print("Supply-chain demand-planning workshop — ONNX model load")
    print("=" * 60)

    conn = oracledb.connect(user=AGENT_USER, password=AGENT_PASSWORD, dsn=DSN)

    if _model_already_loaded(conn):
        print(f"[onnx_setup] model {MODEL_NAME!r} already loaded — skipping.")
        return 0

    onnx_path = _download_and_extract()

    # Ensure an Oracle DIRECTORY object points at the model's parent directory
    # so DBMS_VECTOR.LOAD_ONNX_MODEL can read it. CREATE OR REPLACE is fine.
    cur = conn.cursor()
    print(f"[onnx_setup] CREATE OR REPLACE DIRECTORY {ORACLE_DIR_NAME} AS '{onnx_path.parent}'")
    try:
        cur.execute(
            f"CREATE OR REPLACE DIRECTORY {ORACLE_DIR_NAME} AS '{onnx_path.parent}'"
        )
    except oracledb.DatabaseError as e:
        print(f"[onnx_setup] FATAL: cannot create directory ({e}). "
              "AGENT needs CREATE ANY DIRECTORY; bootstrap.py grants it.",
              file=sys.stderr)
        raise

    print(f"[onnx_setup] loading {ONNX_FILENAME} into Oracle as model {MODEL_NAME} …")
    OracleEmbeddings.load_onnx_model(
        conn=conn,
        dir=ORACLE_DIR_NAME,
        onnx_file=onnx_path.name,
        model_name=MODEL_NAME,
    )
    print(f"✅ ONNX model {MODEL_NAME} loaded ({onnx_path.stat().st_size:,} bytes).")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
