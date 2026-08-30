from __future__ import annotations

import hashlib

import numpy as np

PRNG_FAMILY = "numpy.random.PCG64DXSM"
SEED_DERIVATION_VERSION = "sha256-v1"


def _seed(*parts: object) -> int:
    material = "\x1f".join(str(part) for part in parts).encode("utf-8")
    return int.from_bytes(hashlib.sha256(material).digest()[:16], "big")


class NamedRandomStreams:
    def __init__(self, run_seed: int, patient_index: int) -> None:
        self.run_seed = run_seed
        self.patient_index = patient_index

    def generator(self, name: str) -> np.random.Generator:
        if not name or any(character.isspace() for character in name):
            raise ValueError("stream name must be a nonempty token")
        bit_generator = np.random.PCG64DXSM(
            _seed(SEED_DERIVATION_VERSION, self.run_seed, self.patient_index, name)
        )
        return np.random.Generator(bit_generator)


def synthetic_id(run_seed: int, kind: str, index: int) -> str:
    digest = hashlib.sha256(
        f"synthetic-id-v1\x1f{run_seed}\x1f{kind}\x1f{index}".encode()
    ).hexdigest()
    return f"syn-{kind}-{digest[:24]}"
