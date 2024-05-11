from __future__ import annotations

import sys
from concurrent.futures import Future, InvalidStateError
from contextlib import suppress
from threading import Thread
from typing import TYPE_CHECKING, cast

import numpy as np

if TYPE_CHECKING:
    from typing import Any, Protocol, TypeGuard

    import dask.array as da
    import numpy.typing as npt
    import tensorstore as ts
    import xarray as xr

    from ._dims_slider import Index, Indices

    class SupportsIndexing(Protocol):
        def __getitem__(self, key: Index | tuple[Index, ...]) -> npt.ArrayLike: ...
        @property
        def shape(self) -> tuple[int, ...]: ...


def is_xarray_dataarray(obj: Any) -> TypeGuard[xr.DataArray]:
    if (xr := sys.modules.get("xarray")) and isinstance(obj, xr.DataArray):
        return True
    return False


def is_dask_array(obj: Any) -> TypeGuard[da.Array]:
    if (da := sys.modules.get("dask.array")) and isinstance(obj, da.Array):
        return True
    return False


def is_tensorstore(obj: Any) -> TypeGuard[ts.TensorStore]:
    if (ts := sys.modules.get("tensorstore")) and isinstance(obj, ts.TensorStore):
        return True
    return False


def is_duck_array(obj: Any) -> TypeGuard[SupportsIndexing]:
    if (
        isinstance(obj, np.ndarray)
        or hasattr(obj, "__array_function__")
        or hasattr(obj, "__array_namespace__")
    ):
        return True
    return False


# TODO: Change this factory function on a wrapper class so we
# don't have to check the type of the object every time we call
def isel(store: Any, indexers: Indices) -> np.ndarray:
    """Select a slice from a data store using (possibly) named indices.

    For xarray.DataArray, use the built-in isel method.
    For any other duck-typed array, use numpy-style indexing, where indexers
    is a mapping of axis to slice objects or indices.
    """
    if is_xarray_dataarray(store):
        return cast("np.ndarray", store.isel(indexers).to_numpy())
    if is_tensorstore(store):
        return isel_tensorstore(store, indexers)
    if is_duck_array(store):
        return isel_np_array(store, indexers)
    raise NotImplementedError(f"Don't know how to index into type {type(store)}")


def isel_tensorstore(store: ts.TensorStore, indexers: Indices) -> np.ndarray:
    import tensorstore

    return store[tensorstore.d[*indexers][*indexers.values()]].read().result()


def isel_async(store: Any, indexers: Indices) -> Future[tuple[Indices, np.ndarray]]:
    """Asynchronous version of isel."""
    fut: Future[tuple[Indices, np.ndarray]] = Future()

    def _thread_target() -> None:
        data = isel(store, indexers)
        with suppress(InvalidStateError):
            fut.set_result((indexers, data))

    thread = Thread(target=_thread_target)
    thread.start()
    return fut


def isel_np_array(data: SupportsIndexing, indexers: Indices) -> np.ndarray:
    idx = tuple(indexers.get(k, slice(None)) for k in range(len(data.shape)))
    return np.asarray(data[idx])
