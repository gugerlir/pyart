"""
Additional classes and functions for reading and writing data from a number
of file formats.

These auxiliary input/output routines are not as well polished as those in
:mod:`pyart.io`. They may require addition dependencies beyond those required
for a standard Py-ART install, use non-standard function parameter and naming,
are not supported by the :py:func:`pyart.io.read` function and are not fully
tested if tested at all. Please use these at your own risk.

Bugs in these function should be reported but fixing them may not be a
priority.

"""

from .arm_vpt import read_kazr  # noqa
from .d3r_gcpex_nc import read_d3r_gcpex_nc  # noqa
from .edge_netcdf import read_edge_netcdf  # noqa
from .gamic_hdf5 import read_gamic  # noqa
from .noxp_iphex_nc import read_noxp_iphex_nc  # noqa
from .odim_h5 import read_odim_h5  # noqa
from .pattern import read_pattern  # noqa
from .radx import read_radx  # noqa
from .rainbow_wrl import read_rainbow_wrl  # noqa
from .metranet_reader import read_metranet  # noqa
from .odim_h5_writer import write_odim_grid_h5, write_odim_h5  # noqa
from .odim_h5 import read_odim_grid_h5, read_odim_h5  # noqa
from .rad4alp_bin_reader import read_bin # noqa
from .rad4alp_gif_reader import read_gif # noqa
from .rad4alp_iq_reader import read_iq, read_iq_data # noqa
from .sinarame_h5 import read_sinarame_h5, write_sinarame_cfradial  # noqa

__all__ = [s for s in dir() if not s.startswith("_")]
