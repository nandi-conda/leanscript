"""Hash functions, bit-for-bit compatible with the C runtime so that hash-based containers iterate
in the same order.
"""

M = 0xC6A4A7935BD1E995
R = 47
MASK = (1 << 64) - 1


def _u64(n):
    return n & MASK


def hash_bytes(data, length, seed):
    """MurmurHash64A of the first `length` bytes of `data`, as `hash_str` computes it.

    `data` is a bytes-like object, indexed to integers.
    """
    h = _u64(seed ^ _u64(length * M))
    blocks = length - (length % 8)
    for i in range(0, blocks, 8):
        k = int.from_bytes(data[i : i + 8], "little")
        k = _u64(k * M)
        k ^= k >> R
        k = _u64(k * M)
        h ^= k
        h = _u64(h * M)
    tail = length % 8
    if tail > 0:
        # The tail is mixed from its last byte to its first, as MurmurHash64A does.
        for i in range(tail - 1, -1, -1):
            h ^= data[blocks + i] << (8 * i)
        h = _u64(h * M)
    h ^= h >> R
    h = _u64(h * M)
    h ^= h >> R
    return h


def mix_hash(h, k):
    """`lean_uint64_mix_hash`, including its `k ^= m` where MurmurHash would multiply."""
    k = _u64(k * M)
    k ^= k >> R
    k ^= M
    h ^= k
    return _u64(h * M)


externs = {
    "mixHash": mix_hash,
}
