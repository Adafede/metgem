from .base import BaseWorker

from libmetgem.mgf import read as read_mgf
from libmetgem.msp import read as read_msp
from libmetgem.filter import filter_data_multi

import os


class ReadDataWorker(BaseWorker):
    
    def __init__(self, filename, options):
        super().__init__()
        self.filename = filename
        self.ext = os.path.splitext(filename)[1]
        self.options = options
        self.iterative_update = True
        self.max = 0
        self.desc = 'Reading data file...'

    def run(self):
        mzs = []
        spectra = []

        min_intensity = self.options.min_intensity
        parent_filter_tolerance = self.options.parent_filter_tolerance
        matched_peaks_window = self.options.matched_peaks_window
        min_matched_peaks_search = self.options.min_matched_peaks_search

        if self.ext == '.mgf':
            read = read_mgf
            mz_key = 'pepmass'
        elif self.ext == '.msp':
            read = read_msp
            mz_key = 'precursormz'
        else:
            raise NotImplementedError

        for params, data in read(self.filename, ignore_unknown=True):
            if self.isStopped():
                self.canceled.emit()
                return

            try:
                mz_parent = params[mz_key]
            except KeyError as e:
                self.error.emit(e)
                return

            spectra.append(data)
            mzs.append(mz_parent)

        spectra = filter_data_multi(mzs, spectra, min_intensity, parent_filter_tolerance,
                                    matched_peaks_window, min_matched_peaks_search)
            
        return mzs, spectra
