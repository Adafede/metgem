from PySide6.QtCore import QSettings

from metgem.models.metadata import NodesModel
from metgem.workers.base import BaseWorker
from metgem.workers.gui.errors import NoDataError
from metgem.utils.network import Network


class ExportMetadataWorker(BaseWorker):

    def __init__(self, filename, network: Network, sep=None, selected_rows=None):
        super().__init__()
        self.filename = filename
        self.network = network
        self.sep = sep if sep is not None else ','
        self.selected_rows = selected_rows

        self.max = network.infos.shape[0] if network.infos is not None else 0
        self.iterative_update = True
        self.desc = 'Exporting Metadata...'

    def run(self):
        ncolumns = self.network.infos.shape[1] + 2
        nrows = self.network.infos.shape[0]

        if ncolumns <= 0 or nrows <= 0:
            self.error.emit(NoDataError())
            return

        try:
            df = self.network.infos.copy()
            df.insert(loc=NodesModel.MZCol, column='m/z parent',
                      value=self.network.mzs)
            df = df.iloc[self.selected_rows]

            results = []
            for row in self.selected_rows:
                try:
                    val = self.network.db_results[row]
                except KeyError:
                    results.append('N/A')
                else:
                    try:
                        current = val['current']
                    except KeyError:
                        current = 0
                    results.append(val['standards'][current].text)
            df.insert(loc=NodesModel.DBResultsCol, column='Database search results',
                      value=results)
            if hasattr(self.network, 'mappings'):
                for key, map_cols in self.network.mappings.items():
                    col_subset = [col for map_col in map_cols for col in df.columns if col.startswith(map_col)]
                    df[key] = df[col_subset].sum(axis=1)

            float_precision = QSettings().value('Metadata/float_precision', 4, type=int)

            with open(self.filename, 'w', encoding='utf-8', newline='') as f:
                # Monkey patch write function to update progressbar during CSV export
                _write = f.write
                f.write = lambda *args, **kwargs: (self.updated.emit(len(args)), _write(*args, **kwargs))
                df.to_csv(f, sep=self.sep, index_label='id', float_format=f'%.{float_precision}f')
            return True
        except (FileNotFoundError, IOError, ValueError) as e:
            self.error.emit(e)
            return
