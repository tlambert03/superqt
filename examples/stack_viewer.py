from __future__ import annotations

from re import X

import dask.array as da
import numpy as np
from qtpy import QtWidgets

from superqt import QStackViewer

dask_arr = da.random.random((1000, 24, 3, 512, 512), chunks=(1, 1, 1, 512, 512))

numpy_arr = np.empty((64, 3, 8, 128, 128))
for pidx, ppp in enumerate(np.linspace(0, np.pi * 2, 64)):
    for aidx, a in enumerate(np.linspace(0, np.pi * 2, 3)):
        for fidx, f in enumerate(np.linspace(1, 8, 8)):
            # Create a 2D grid of a sine wave, angled by angle
            X, Y = np.meshgrid(np.linspace(-1, 1, 128), np.linspace(-1, 1, 128))
            Z = np.sin(
                2 * np.pi * f * (X * np.cos(np.pi / 3 * a) + Y * np.sin(np.pi / 3 * a))
                + ppp
            )
            Z -= Z.min()
            numpy_arr[pidx, aidx, fidx] = Z * 255


if __name__ == "__main__":
    qapp = QtWidgets.QApplication([])
    wdg = QtWidgets.QWidget()
    layout = QtWidgets.QGridLayout(wdg)
    layout.setContentsMargins(0, 0, 0, 0)
    layout.addWidget(QStackViewer(dask_arr), 0, 0, 1, 1)
    layout.addWidget(QStackViewer(numpy_arr), 0, 1, 1, 1)

    wdg.show()
    qapp.exec()
