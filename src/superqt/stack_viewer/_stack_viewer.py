from __future__ import annotations

from collections import defaultdict
from enum import Enum
from itertools import cycle
from typing import TYPE_CHECKING, Iterable, Mapping, Sequence, cast

import cmap
import numpy as np
from qtpy.QtWidgets import QHBoxLayout, QLabel, QPushButton, QVBoxLayout, QWidget

from superqt.collapsible import QCollapsible
from superqt.elidable import QElidingLabel
from superqt.iconify import QIconifyIcon
from superqt.utils import ensure_main_thread, qthrottled

from ._backends import get_canvas
from ._dims_slider import DimsSliders
from ._indexing import is_xarray_dataarray, isel_async
from ._lut_control import LutControl

if TYPE_CHECKING:
    from concurrent.futures import Future
    from typing import Any, Callable, Hashable, TypeAlias

    from ._dims_slider import DimKey, Indices, Sizes
    from ._protocols import PCanvas, PImageHandle

    ImgKey: TypeAlias = Hashable
    # any mapping of dimensions to sizes
    SizesLike: TypeAlias = Sizes | Iterable[int | tuple[DimKey, int] | Sequence]

MID_GRAY = "#888888"
GRAYS = cmap.Colormap("gray")
COLORMAPS = [cmap.Colormap("green"), cmap.Colormap("magenta"), cmap.Colormap("cyan")]
MAX_CHANNELS = 16
ALL_CHANNELS = slice(None)


class ChannelMode(str, Enum):
    COMPOSITE = "composite"
    MONO = "mono"

    def __str__(self) -> str:
        return self.value


class ChannelModeButton(QPushButton):
    def __init__(self, parent: QWidget | None = None):
        super().__init__(parent)
        self.setCheckable(True)
        self.toggled.connect(self.next_mode)

    def next_mode(self) -> None:
        if self.isChecked():
            self.setMode(ChannelMode.MONO)
        else:
            self.setMode(ChannelMode.COMPOSITE)

    def mode(self) -> ChannelMode:
        return ChannelMode.MONO if self.isChecked() else ChannelMode.COMPOSITE

    def setMode(self, mode: ChannelMode) -> None:
        # we show the name of the next mode, not the current one
        other = ChannelMode.COMPOSITE if mode is ChannelMode.MONO else ChannelMode.MONO
        self.setText(str(other))
        self.setChecked(mode == ChannelMode.MONO)


class QStackViewer(QWidget):
    """A viewer for ND arrays."""

    def __init__(
        self,
        data: Any,
        *,
        parent: QWidget | None = None,
        channel_axis: DimKey | None = None,
        channel_mode: ChannelMode = ChannelMode.MONO,
    ):
        super().__init__(parent=parent)

        # ATTRIBUTES ----------------------------------------------------

        # dimensions of the data in the datastore
        self._sizes: Sizes = {}
        # mapping of key to a list of objects that control image nodes in the canvas
        self._img_handles: defaultdict[ImgKey, list[PImageHandle]] = defaultdict(list)
        # mapping of same keys to the LutControl objects control image display props
        self._lut_ctrls: dict[ImgKey, LutControl] = {}
        # the set of dimensions we are currently visualizing (e.g. XY)
        # this is used to control which dimensions have sliders and the behavior
        # of isel when selecting data from the datastore
        self._visualized_dims: set[DimKey] = set()
        # the axis that represents the channels in the data
        self._channel_axis = channel_axis
        self._channel_mode: ChannelMode = None  # type: ignore # set in set_channel_mode
        # colormaps that will be cycled through when displaying composite images
        # TODO: allow user to set this
        self._cmaps = cycle(COLORMAPS)

        # WIDGETS ----------------------------------------------------

        # the button that controls the display mode of the channels
        self._channel_mode_btn = ChannelModeButton()
        self._channel_mode_btn.clicked.connect(self.set_channel_mode)
        # button to reset the zoom of the canvas
        self._set_range_btn = QPushButton(
            QIconifyIcon("fluent:full-screen-maximize-24-filled"), ""
        )
        self._set_range_btn.clicked.connect(self._on_set_range_clicked)

        # place to display dataset summary
        self._data_info = QElidingLabel("")
        # place to display arbitrary text
        self._hover_info = QLabel("")
        # the canvas that displays the images
        self._canvas: PCanvas = get_canvas()(self._hover_info.setText)
        # the sliders that control the index of the displayed image
        self._dims_sliders = DimsSliders()
        self._dims_sliders.valueChanged.connect(
            qthrottled(self._update_data_for_index, 20, leading=True)
        )

        self._lut_drop = QCollapsible("LUTs")
        self._lut_drop.setCollapsedIcon(QIconifyIcon("bi:chevron-down", color=MID_GRAY))
        self._lut_drop.setExpandedIcon(QIconifyIcon("bi:chevron-up", color=MID_GRAY))
        lut_layout = cast("QVBoxLayout", self._lut_drop.layout())
        lut_layout.setContentsMargins(0, 1, 0, 1)
        lut_layout.setSpacing(0)
        if (
            hasattr(self._lut_drop, "_content")
            and (layout := self._lut_drop._content.layout()) is not None
        ):
            layout.setContentsMargins(0, 0, 0, 0)
            layout.setSpacing(0)

        # LAYOUT -----------------------------------------------------

        self._btns = btns = QHBoxLayout()
        btns.setContentsMargins(0, 0, 0, 0)
        btns.setSpacing(0)
        btns.addStretch()
        btns.addWidget(self._channel_mode_btn)
        btns.addWidget(self._set_range_btn)

        layout = QVBoxLayout(self)
        layout.setSpacing(2)
        layout.setContentsMargins(6, 6, 6, 6)
        layout.addWidget(self._data_info)
        layout.addWidget(self._canvas.qwidget(), 1)
        layout.addWidget(self._hover_info)
        layout.addWidget(self._dims_sliders)
        layout.addWidget(self._lut_drop)
        layout.addLayout(btns)

        # SETUP ------------------------------------------------------

        self.set_channel_mode(channel_mode)
        self.set_data(data)

    # ------------------- PUBLIC API ----------------------------

    @property
    def data(self) -> Any:
        """Return the data backing the view."""
        return self._data

    @property
    def dims_sliders(self) -> DimsSliders:
        """Return the DimsSliders widget."""
        return self._dims_sliders

    @property
    def sizes(self) -> Sizes:
        """Return sizes {dimkey: int} of the dimensions in the datastore."""
        return self._sizes

    def set_data(
        self, data: Any, sizes: SizesLike | None = None, channel_axis: int | None = None
    ) -> None:
        """Set the datastore, and, optionally, the sizes of the data."""
        if sizes is None:
            if (sz := getattr(data, "sizes", None)) and isinstance(sz, Mapping):
                sizes = sz
            elif (shp := getattr(data, "shape", None)) and isinstance(shp, tuple):
                sizes = shp
        self._sizes = _to_sizes(sizes)
        self._data = data
        if channel_axis is not None:
            self._channel_axis = channel_axis
        elif self._channel_axis is None:
            self._channel_axis = self._guess_channel_axis(data)
        self.set_visualized_dims(list(self._sizes)[-2:])
        self.update_slider_ranges()
        self.setIndex({})

        package = getattr(data, "__module__", "").split(".")[0]
        info = f"{package}.{getattr(type(data), '__qualname__', '')}"

        if self._sizes:
            if all(isinstance(x, int) for x in self._sizes):
                size_str = repr(tuple(self._sizes.values()))
            else:
                size_str = ", ".join(f"{k}:{v}" for k, v in self._sizes.items())
                size_str = f"({size_str})"
            info += f" {size_str}"
        if dtype := getattr(data, "dtype", ""):
            info += f", {dtype}"
        if nbytes := getattr(data, "nbytes", 0) / 1e6:
            info += f", {nbytes:.2f}MB"
        self._data_info.setText(info)

    def set_visualized_dims(self, dims: Iterable[DimKey]) -> None:
        """Set the dimensions that will be visualized.

        This dims will NOT have sliders associated with them.
        """
        self._visualized_dims = set(dims)
        for d in self._dims_sliders._sliders:
            self._dims_sliders.set_dimension_visible(d, d not in self._visualized_dims)
        for d in self._visualized_dims:
            self._dims_sliders.set_dimension_visible(d, False)

    def update_slider_ranges(
        self, mins: SizesLike | None = None, maxes: SizesLike | None = None
    ) -> None:
        """Set the maximum values of the sliders.

        If `sizes` is not provided, sizes will be inferred from the datastore.
        This is mostly here as a public way to reset the
        """
        if maxes is None:
            maxes = self.sizes
        maxes = _to_sizes(maxes)
        self._dims_sliders.setMaxima({k: v - 1 for k, v in maxes.items()})
        if mins is not None:
            self._dims_sliders.setMinima(_to_sizes(mins))

        # FIXME: this needs to be moved and made user-controlled
        for dim in list(maxes.keys())[-2:]:
            self._dims_sliders.set_dimension_visible(dim, False)

    def set_channel_mode(self, mode: ChannelMode | None = None) -> None:
        """Set the mode for displaying the channels.

        In "composite" mode, the channels are displayed as a composite image, using
        self._channel_axis as the channel axis. In "grayscale" mode, each channel is
        displayed separately. (If mode is None, the current value of the
        channel_mode_picker button is used)
        """
        if mode is None or isinstance(mode, bool):
            mode = self._channel_mode_btn.mode()
        else:
            mode = ChannelMode(mode)
            self._channel_mode_btn.setMode(mode)
        if mode == getattr(self, "_channel_mode", None):
            return

        self._channel_mode = mode
        self._cmaps = cycle(COLORMAPS)  # reset the colormap cycle
        if self._channel_axis is not None:
            # set the visibility of the channel slider
            self._dims_sliders.set_dimension_visible(
                self._channel_axis, mode != ChannelMode.COMPOSITE
            )

        if self._img_handles:
            self._clear_images()
            self._update_data_for_index(self._dims_sliders.value())

    def setIndex(self, index: Indices) -> None:
        """Set the index of the displayed image."""
        self._dims_sliders.setValue(index)

    # ------------------- PRIVATE METHODS ----------------------------

    def _guess_channel_axis(self, data: Any) -> DimKey | None:
        """Guess the channel axis from the data."""
        if is_xarray_dataarray(data):
            for d in data.dims:
                if str(d).lower() in ("channel", "ch", "c"):
                    return cast("DimKey", d)
        if isinstance(shp := getattr(data, "shape", None), Sequence):
            # for numpy arrays, use the smallest dimension as the channel axis
            if min(shp) <= MAX_CHANNELS:
                return shp.index(min(shp))
        return None

    def _on_set_range_clicked(self) -> None:
        # using method to swallow the parameter passed by _set_range_btn.clicked
        self._canvas.set_range()

    def _image_key(self, index: Indices) -> ImgKey:
        """Return the key for image handle(s) corresponding to `index`."""
        if self._channel_mode == ChannelMode.COMPOSITE:
            val = index.get(self._channel_axis, 0)
            if isinstance(val, slice):
                return (val.start, val.stop)
            return val
        return 0

    def _update_data_for_index(self, index: Indices) -> None:
        """Retrieve data for `index` from datastore and update canvas image(s).

        This will pull the data from the datastore using the given index, and update
        the image handle(s) with the new data.  This method is *asynchronous*.  It
        makes a request for the new data slice and queues _on_data_future_done to be
        called when the data is ready.
        """
        if self._channel_axis and self._channel_mode == ChannelMode.COMPOSITE:
            index = {**index, self._channel_axis: ALL_CHANNELS}

        self._isel(index).add_done_callback(self._on_data_slice_ready)

    def _isel(self, index: Indices) -> Future[tuple[Indices, np.ndarray]]:
        """Select data from the datastore using the given index."""
        idx = {k: v for k, v in index.items() if k not in self._visualized_dims}
        try:
            return isel_async(self._data, idx)
        except Exception as e:
            raise type(e)(f"Failed to index data with {idx}: {e}") from e

    @ensure_main_thread  # type: ignore
    def _on_data_slice_ready(self, future: Future[tuple[Indices, np.ndarray]]) -> None:
        """Update the displayed image for the given index.

        Connected to the future returned by _isel.
        """
        index, data = future.result()
        # assume that if we have channels remaining, that they are the first axis
        # FIXME: this is a bad assumption
        data = iter(data) if index.get(self._channel_axis) is ALL_CHANNELS else [data]
        for i, datum in enumerate(data):
            self._update_canvas_data(datum, {**index, self._channel_axis: i})
        self._canvas.refresh()

    def _update_canvas_data(self, data: np.ndarray, index: Indices) -> None:
        """Actually update the image handle(s) with the (sliced) data.

        By this point, data should be sliced from the underlying datastore.  Any
        dimensions remaining that are more than the number of visualized dimensions
        (currently just 2D) will be reduced using max intensity projection (currently).
        """
        imkey = self._image_key(index)
        datum = self._reduce_data_for_display(data)
        if handles := self._img_handles[imkey]:
            for handle in handles:
                handle.data = datum
            if ctrl := self._lut_ctrls.get(imkey, None):
                ctrl.update_autoscale()
        else:
            cm = (
                next(self._cmaps)
                if self._channel_mode == ChannelMode.COMPOSITE
                else GRAYS
            )
            handles.append(self._canvas.add_image(datum, cmap=cm))
            if imkey not in self._lut_ctrls:
                channel_name = f"Ch {imkey}"  # TODO: get name from user
                self._lut_ctrls[imkey] = c = LutControl(channel_name, handles)
                self._lut_drop.addWidget(c)

    def _reduce_data_for_display(
        self, data: np.ndarray, reductor: Callable[..., np.ndarray] = np.max
    ) -> np.ndarray:
        """Reduce the number of dimensions in the data for display.

        This function takes a data array and reduces the number of dimensions to
        the max allowed for display. The default behavior is to reduce the smallest
        dimensions, using np.max.  This can be improved in the future.

        This also coerces 64-bit data to 32-bit data.
        """
        # TODO
        # - allow for 3d data
        # - allow dimensions to control how they are reduced (as opposed to just max)
        # - for better way to determine which dims need to be reduced (currently just
        #   the smallest dims)
        data = data.squeeze()
        visualized_dims = 2
        if extra_dims := data.ndim - visualized_dims:
            shapes = sorted(enumerate(data.shape), key=lambda x: x[1])
            smallest_dims = tuple(i for i, _ in shapes[:extra_dims])
            return reductor(data, axis=smallest_dims)

        if data.dtype.itemsize > 4:  # More than 32 bits
            if np.issubdtype(data.dtype, np.integer):
                data = data.astype(np.int32)
            else:
                data = data.astype(np.float32)
        return data

    def _clear_images(self) -> None:
        """Remove all images from the canvas."""
        for handles in self._img_handles.values():
            for handle in handles:
                handle.remove()
        self._img_handles.clear()

        # clear the current LutControls as well
        for c in self._lut_ctrls.values():
            cast("QVBoxLayout", self.layout()).removeWidget(c)
            c.deleteLater()
        self._lut_ctrls.clear()


def _to_sizes(sizes: SizesLike | None) -> Sizes:
    """Coerce `sizes` to a {dimKey -> int} mapping."""
    if sizes is None:
        return {}
    if isinstance(sizes, Mapping):
        return {k: int(v) for k, v in sizes.items()}
    if not isinstance(sizes, Iterable):
        raise TypeError(f"SizeLike must be an iterable or mapping, not: {type(sizes)}")
    _sizes: dict[Hashable, int] = {}
    for i, val in enumerate(sizes):
        if isinstance(val, int):
            _sizes[i] = val
        elif isinstance(val, Sequence) and len(val) == 2:
            _sizes[val[0]] = int(val[1])
        else:
            raise ValueError(f"Invalid size: {val}. Must be an int or a 2-tuple.")
    return _sizes
