import pandas as pd
from libmetgem.filter import filter_data_multi
from libmetgem.mgf import read as read_mgf
from libmetgem.msp import read as read_msp

from metgem.workers.base import BaseWorker
from metgem.workers.options import ScoreComputationOptions
from metgem.utils.read_data import guess_file_format


class NoSpectraError(Exception):
    pass


class FileEmptyError(Exception):
    pass


class ReadDataWorker(BaseWorker):

    def __init__(self, filename, options: ScoreComputationOptions):
        super().__init__()
        self.filename = filename
        self.options = options
        self.max = 0
        self.iterative_update = True
        self.desc = 'Reading data file...'

    def run(self):
        mzs = []
        spectra = []
        ids = []

        use_filtering = self.options.use_filtering
        use_min_mz_filter = self.options.use_min_mz_filter if use_filtering else False
        use_min_intensity_filter = self.options.use_min_intensity_filter if use_filtering else False
        use_parent_filter = self.options.use_parent_filter if use_filtering else False
        use_window_rank_filter = self.options.use_window_rank_filter if use_filtering else False
        min_mz = self.options.min_mz if use_min_mz_filter else 0
        min_intensity = self.options.min_intensity if use_min_intensity_filter else 0
        parent_filter_tolerance = self.options.parent_filter_tolerance if use_parent_filter else 0
        matched_peaks_window = self.options.matched_peaks_window if use_window_rank_filter else 0
        min_matched_peaks_search = self.options.min_matched_peaks_search if use_window_rank_filter else 0
        is_ms1_data = self.options.is_ms1_data
        scoring = self.options.scoring
        square_root = scoring == 'cosine'
        norm = 'dot' if scoring == 'cosine' else 'sum'

        fmt = guess_file_format(self.filename)
        if fmt == 'mgf':
            read = read_mgf
            mz_keys = ['pepmass']
            id_key = 'feature_id'
        elif fmt == 'msp':
            read = read_msp
            mz_keys = ['precursormz', 'exactmass', 'mw']
            id_key = None
        else:
            self.error.emit(NotImplementedError())
            return

        for i, (params, data) in enumerate(read(self.filename, ignore_unknown=True)):
            if self.isStopped():
                self.canceled.emit()
                return

            id_ = params.get(id_key, i+1) if id_key is not None else i+1
            if not is_ms1_data:
                mz_parent = 0
                for key in mz_keys:
                    try:
                        mz_parent = params[key]
                    except KeyError as e:
                        pass
                mzs.append(mz_parent)
            else:
                mzs.append(0)

            try:
                # noinspection PyUnboundLocalVariable
                self.error.emit(e)
                return
            except UnboundLocalError:
                pass

            spectra.append(data)
            ids.append(id_)

        if not spectra:
            self.error.emit(FileEmptyError())
            return

        # Even if use_filtering is False, filtering should be done with neutral parameters
        # because last step of filtering is to normalize spectra
        spectra = filter_data_multi(mzs, spectra, min_intensity, parent_filter_tolerance,
                                    matched_peaks_window, min_matched_peaks_search,
                                    mz_min=min_mz, square_root=square_root, norm=norm)

        if not spectra:
            self.error.emit(NoSpectraError())
            return

        mzs = pd.Series(mzs, index=ids)

        return mzs, spectra
