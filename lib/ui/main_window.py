import sys
import os
import json

from pyteomics.auxiliary import PyteomicsError
from requests import ConnectionError

import numpy as np
import igraph as ig

from PyQt5.QtWidgets import (QDialog, QFileDialog,
                             QMessageBox, QWidget,
                             QMenu, QToolButton, QActionGroup,
                             QAction, QDockWidget, QWIDGETSIZE_MAX, qApp)
from PyQt5.QtCore import QSettings, Qt, QSize, QCoreApplication
from PyQt5.QtGui import QPainter, QImage, QCursor, QColor

from PyQt5 import uic

from .. import config, ui, utils, workers, errors
from ..utils.network import Network

UI_FILE = os.path.join(os.path.dirname(__file__), 'main_window.ui')
if getattr(sys, 'frozen', False):
    MAIN_UI_FILE = os.path.join(sys._MEIPASS, UI_FILE)

MainWindowUI, MainWindowBase = uic.loadUiType(UI_FILE, from_imports='lib.ui', import_from='lib.ui')


class MainWindow(MainWindowBase, MainWindowUI):

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

        # Keep track of unsaved changes
        self._has_unsaved_changes = False

        # Opened file
        self.fname = None

        # Workers' references
        self._workers = workers.WorkerSet(self, ui.ProgressDialog(self))

        # Setup User interface
        self.setupUi(self)
        self.gvNetwork.setFocus()

        # Activate first tab of tab widget
        self.tabWidget.setCurrentIndex(0)

        # Create a corner button to hide/show pages of tab widget
        w = QToolButton(self)
        w.setArrowType(Qt.DownArrow)
        w.setIconSize(QSize(12, 12))
        w.setAutoRaise(True)
        self.tabWidget.setCornerWidget(w, Qt.TopRightCorner)

        # Add model to table views
        self.tvNodes.setModel(ui.widgets.NodesModel(self))
        self.tvEdges.setModel(ui.widgets.EdgesModel(self))

        # Init project's objects
        self.init_project()

        # Move search layout to search toolbar
        w = QWidget()
        self.layoutSearch.setParent(None)
        w.setLayout(self.layoutSearch)
        self.tbSearch.addWidget(w)

        # Reorganise export as image actions
        self.tbExport.removeAction(self.actionExportAsImage)
        self.tbExport.removeAction(self.actionExportCurrentViewAsImage)
        export_button = ui.widgets.ToolBarMenu()
        export_button.setDefaultAction(self.actionExportAsImage)
        export_button.addAction(self.actionExportAsImage)
        export_button.addAction(self.actionExportCurrentViewAsImage)
        self.tbExport.addWidget(export_button)

        # Add a Jupyter widget
        if config.EMBED_JUPYTER:
            from qtconsole.rich_jupyter_widget import RichJupyterWidget
            from qtconsole.inprocess import QtInProcessKernelManager

            kernel_manager = QtInProcessKernelManager()
            kernel_manager.start_kernel()

            kernel_client = kernel_manager.client()
            kernel_client.start_channels()

            self.jupyter_widget = RichJupyterWidget()
            self.jupyter_widget.kernel_manager = kernel_manager
            self.jupyter_widget.kernel_client = kernel_client

            def stop():
                kernel_client.stop_channels()
                kernel_manager.shutdown_kernel()

            self.jupyter_widget.exit_requested.connect(stop)
            qApp.aboutToQuit.connect(stop)

            dock_widget = QDockWidget()
            dock_widget.setObjectName('jupyter')
            dock_widget.setWindowTitle('Jupyter Console')
            dock_widget.setWidget(self.jupyter_widget)

            self.addDockWidget(Qt.BottomDockWidgetArea, dock_widget)
            kernel_manager.kernel.shell.push({'app': qApp, 'win': self})

        # Connect events
        self.tvNodes.customContextMenuRequested.connect(self.on_nodes_table_contextmenu)
        self.btUseColumnsForPieCharts.clicked.connect(lambda: self.on_use_columns_for('pie charts'))
        self.btUseColumnForLabels.clicked.connect(lambda: self.on_use_columns_for('labels'))

        self.gvNetwork.scene().selectionChanged.connect(self.on_scene_selection_changed)
        self.gvTSNE.scene().selectionChanged.connect(self.on_scene_selection_changed)
        self.gvNetwork.showSpectrumTriggered.connect(lambda node: self.on_show_spectrum_triggered('show', node))
        self.gvTSNE.showSpectrumTriggered.connect(lambda node: self.on_show_spectrum_triggered('show', node))
        self.gvNetwork.compareSpectrumTriggered.connect(lambda node: self.on_show_spectrum_triggered('compare', node))
        self.gvTSNE.compareSpectrumTriggered.connect(lambda node: self.on_show_spectrum_triggered('compare', node))

        self.actionQuit.triggered.connect(self.close)
        self.actionAbout.triggered.connect(self.on_about_triggered)
        self.actionAboutQt.triggered.connect(self.on_about_qt_triggered)
        self.actionProcessFile.triggered.connect(self.on_process_file_triggered)
        self.actionImportMetadata.triggered.connect(self.on_import_metadata_triggered)
        self.actionCurrentParameters.triggered.connect(self.on_current_parameters_triggered)
        self.actionSettings.triggered.connect(self.on_settings_triggered)
        self.actionZoomIn.triggered.connect(lambda: self.current_view.scaleView(1.2))
        self.actionZoomOut.triggered.connect(lambda: self.current_view.scaleView(1 / 1.2))
        self.actionZoomToFit.triggered.connect(lambda: self.current_view.zoomToFit())
        self.actionZoomSelectedRegion.triggered.connect(
            lambda: self.current_view.fitInView(self.current_view.scene().selectedNodesBoundingRect(),
                                                Qt.KeepAspectRatio))
        self.leSearch.textChanged.connect(self.on_do_search)
        self.leSearch.returnPressed.connect(self.on_do_search)
        self.actionNewProject.triggered.connect(self.on_new_project_triggered)
        self.actionOpen.triggered.connect(self.on_open_project_triggered)
        self.actionSave.triggered.connect(self.on_save_project_triggered)
        self.actionSaveAs.triggered.connect(self.on_save_project_as_triggered)

        self.actionFullScreen.triggered.connect(self.on_full_screen_triggered)
        self.actionHideSelected.triggered.connect(self.current_view.scene().hideSelectedItems)
        self.actionShowAll.triggered.connect(self.current_view.scene().showAllItems)
        self.actionNeighbors.triggered.connect(
            lambda: self.on_select_first_neighbors_triggered(self.current_view.scene().selectedNodes()))
        self.actionExportToCytoscape.triggered.connect(self.on_export_to_cytoscape_triggered)
        self.actionExportAsImage.triggered.connect(lambda: self.on_export_as_image_triggered('full'))
        self.actionExportCurrentViewAsImage.triggered.connect(lambda: self.on_export_as_image_triggered('current'))

        self.actionDownloadDatabases.triggered.connect(self.on_download_databases_triggered)
        self.actionViewDatabases.triggered.connect(self.on_view_databases_triggered)

        self.btNetworkOptions.clicked.connect(lambda: self.on_edit_options_triggered('network'))
        self.btTSNEOptions.clicked.connect(lambda: self.on_edit_options_triggered('t-sne'))

        self.tabWidget.cornerWidget(Qt.TopRightCorner).clicked.connect(self.minimize_tabwidget)
        self.tabWidget.currentChanged.connect(self.update_search_menu)

        self.sliderNetworkScale.valueChanged.connect(lambda val: self.on_scale_changed('network', val))
        self.sliderTSNEScale.valueChanged.connect(lambda val: self.on_scale_changed('t-sne', val))

        # Add a menu to show/hide toolbars
        popup_menu = self.createPopupMenu()
        popup_menu.setTitle("Toolbars")
        self.menuView.addMenu(popup_menu)

        # Build research bar
        self.update_search_menu()

    def init_project(self):
        # Create an object to store all computed objects
        self.network = Network()

        # Create graph
        self._network.graph = ig.Graph()

        # Set default options
        self._network.options = utils.AttrDict({'cosine': workers.CosineComputationOptions(),
                                                'network': workers.NetworkVisualizationOptions(),
                                                'tsne': workers.TSNEVisualizationOptions()})

    @property
    def window_title(self):
        if self.fname is not None:
            if self.has_unsaved_changes:
                return QCoreApplication.applicationName() + ' - ' + self.fname + '*'
            else:
                return QCoreApplication.applicationName() + ' - ' + self.fname
        else:
            return QCoreApplication.applicationName()

    @property
    def has_unsaved_changes(self):
        return self._has_unsaved_changes

    @has_unsaved_changes.setter
    def has_unsaved_changes(self, value):
        if value:
            self.actionSave.setEnabled(True)
        else:
            self.actionSave.setEnabled(False)

        self._has_unsaved_changes = value
        self.setWindowTitle(self.window_title)

    @property
    def current_view(self):
        for view in (self.gvNetwork, self.gvTSNE):
            if view.hasFocus():
                return view
        return self.gvNetwork

    @property
    def network(self):
        return self._network

    @network.setter
    def network(self, network):
        network.infosAboutToChange.connect(self.tvNodes.model().sourceModel().beginResetModel)
        network.infosChanged.connect(self.tvNodes.model().sourceModel().endResetModel)
        network.interactionsAboutToChange.connect(self.tvEdges.model().sourceModel().beginResetModel)
        network.interactionsChanged.connect(self.tvEdges.model().sourceModel().endResetModel)
        self._network = network

    def load_project(self, filename):
        worker = self.prepare_load_project_worker(filename)
        if worker is not None:
            self._workers.add(worker)

    def save_project(self, filename):
        worker = self.prepare_save_project_worker(filename)
        if worker is not None:
            self._workers.add(worker)

    def update_search_menu(self):
        childs = self.tabWidget.currentWidget().children()
        if self.tvNodes in childs:
            table = self.tvNodes
        elif self.tvEdges in childs:
            table = self.tvEdges
        else:
            return False
        model = table.model()

        menu = QMenu(self)
        group = QActionGroup(menu, exclusive=True)

        for index in range(model.columnCount() + 1):
            text = "All" if index == 0 else model.headerData(index - 1, Qt.Horizontal, Qt.DisplayRole)
            action = group.addAction(QAction(str(text), checkable=True))
            action.setData(index)
            menu.addAction(action)
            if index == 0:
                action.setChecked(True)
                menu.addSeparator()

        self.btSearch.setMenu(menu)
        self.btSearch.setPopupMode(QToolButton.InstantPopup)
        group.triggered.connect(lambda action: table.model().setFilterKeyColumn(action.data() - 1))
        model.setFilterKeyColumn(-1)

    def keyPressEvent(self, event):
        key = event.key()

        if key == Qt.Key_M:  # Show/hide minimap
            view = self.current_view
            view.minimap.setVisible(not view.minimap.isVisible())

    def showEvent(self, event):
        self.load_settings()
        super().showEvent(event)

    def closeEvent(self, event):
        if not config.DEBUG and self._workers:
            reply = QMessageBox.question(self, None,
                                         "There is process running. Do you really want to exit?",
                                         QMessageBox.Close | QMessageBox.Cancel)
        else:
            reply = QMessageBox.Close

        if reply == QMessageBox.Close:
            event.accept()
            self.save_settings()
        else:
            event.ignore()

    def on_scene_selection_changed(self):
        view = self.current_view
        nodes_idx = [item.index() for item in view.scene().selectedNodes()]
        edges_idx = [item.index() for item in view.scene().selectedEdges()]
        self.tvNodes.model().setSelection(nodes_idx)
        self.tvEdges.model().setSelection(edges_idx)

        if self.actionLinkViews.isChecked():
            if view == self.gvNetwork:
                with utils.SignalBlocker(self.gvTSNE.scene()):
                    self.gvTSNE.scene().setNodesSelection(nodes_idx)
            elif view == self.gvTSNE:
                with utils.SignalBlocker(self.gvNetwork.scene()):
                    self.gvNetwork.scene().setNodesSelection(nodes_idx)

    def on_do_search(self):
        childs = self.tabWidget.currentWidget().children()
        if self.tvNodes in childs:
            table = self.tvNodes
        elif self.tvEdges in childs:
            table = self.tvEdges
        else:
            return False
        table.model().setFilterRegExp(str(self.leSearch.text()))

    def on_new_project_triggered(self):
        reply = QMessageBox.Yes
        if self.has_unsaved_changes:
            if self.fname is not None:
                message = f"There is unsaved changes in {self.fname}. Would you like to save them?"
            else:
                message = f"Current work has not been saved. Would you like to save now?"
            reply = QMessageBox.question(self, QCoreApplication.applicationName(),
                                         message, QMessageBox.Yes | QMessageBox.No | QMessageBox.Cancel)

            if reply == QMessageBox.Yes:
                self.on_save_project_triggered()

        if reply != QMessageBox.Cancel:
            self.fname = None
            self.has_unsaved_changes = False
            self.tvNodes.model().sourceModel().beginResetModel()
            self.tvEdges.model().sourceModel().beginResetModel()
            self.init_project()
            self.tvNodes.model().sourceModel().endResetModel()
            self.tvEdges.model().sourceModel().endResetModel()
            self.sliderNetworkScale.resetValue()
            self.sliderTSNEScale.resetValue()
            self.gvNetwork.scene().clear()
            self.gvTSNE.scene().clear()
            self.cvSpectrum.set_spectrum1(None)
            self.cvSpectrum.set_spectrum2(None)
            self.update_search_menu()

    def on_open_project_triggered(self):
        dialog = QFileDialog(self)
        dialog.setFileMode(QFileDialog.ExistingFile)
        dialog.setNameFilters([f"{QCoreApplication.applicationName()} Files (*{config.FILE_EXTENSION})",
                               "All files (*.*)"])
        if dialog.exec_() == QDialog.Accepted:
            filename = dialog.selectedFiles()[0]
            self.load_project(filename)

    def on_save_project_triggered(self):
        if self.fname is None:
            self.on_save_project_as_triggered()
        else:
            self.save_project(self.fname)

    def on_save_project_as_triggered(self):
        dialog = QFileDialog(self)
        dialog.setAcceptMode(QFileDialog.AcceptSave)
        dialog.setNameFilters([f"{QCoreApplication.applicationName()} Files (*{config.FILE_EXTENSION})",
                               "All files (*.*)"])
        if dialog.exec_() == QDialog.Accepted:
            filename = dialog.selectedFiles()[0]
            self.save_project(filename)

    def on_about_triggered(self):
        message = (f'Version: {QCoreApplication.applicationVersion()}',
                   '',
                   'Should say something here.')
        QMessageBox.about(self, f'About {QCoreApplication.applicationName()}',
                          '\n'.join(message))

    def on_about_qt_triggered(self):
        QMessageBox.aboutQt(self)

    def on_export_to_cytoscape_triggered(self):
        try:
            from py2cytoscape.data.cyrest_client import CyRestClient

            view = self.current_view

            cy = CyRestClient()

            # Create exportable copy of the graph object
            g = self.network.graph.copy()
            for attr in g.vs.attributes():
                if attr.startswith('__'):
                    del g.vs[attr]
                else:
                    g.vs[attr] = [str(x) for x in g.vs[attr]]
            if view == self.gvTSNE:
                g.delete_edges(g.es)  # in a t-SNE layout, edges does not makes any sense
            else:
                for attr in g.es.attributes():
                    if attr.startswith('__'):
                        del g.es[attr]
                    else:
                        g.es[attr] = [str(x) for x in g.es[attr]]

            # cy.session.delete()
            g_cy = cy.network.create_from_igraph(g)

            layout = np.empty((g.vcount(), 2))
            for item in view.scene().nodes():
                layout[item.index()] = (item.x(), item.y())
            positions = [(suid, x, y) for suid, (x, y) in zip(g_cy.get_nodes()[::-1], layout)]
            cy.layout.apply_from_presets(network=g_cy, positions=positions)

            with open('styles.json', 'r') as f:
                style_js = json.load(f)
            style = cy.style.create('cyREST style', style_js)
            cy.style.apply(style, g_cy)
        except (ConnectionRefusedError, ConnectionError):
            QMessageBox.information(self, None,
                                    'Please launch Cytoscape before trying to export.')
        except json.decoder.JSONDecodeError:
            QMessageBox.information(self, None,
                                    'Cytoscape was not ready to receive data. Please try again.')
        except ImportError:
            QMessageBox.information(self, None,
                                    'py2tocytoscape is required for this action (https://pypi.python.org/pypi/py2cytoscape).')
        except FileNotFoundError:
            QMessageBox.warning(self, None,
                                f'styles.json not found. You may have to reinstall {QCoreApplication.applicationName()}')

    def on_export_as_image_triggered(self, type_):
        filter_ = ["PNG - Portable Network Graphics (*.png)",
                   "JPEG - Joint Photographic Experts Group (*.JPEG)",
                   "SVG - Scalable Vector Graphics (*.svg)",
                   "BMP - Windows Bitmap (*.bmp)"]
        if type_ == 'current':
            filter_.remove("SVG - Scalable Vector Graphics (*.svg)")

        filename, filter_ = QFileDialog.getSaveFileName(self, "Save image",
                                                        filter=";;".join(filter_))
        if filename:
            view = self.current_view
            if filter_.endswith("(*.svg)"):
                try:
                    from PyQt5.QtSvg import QSvgGenerator
                except ImportError:
                    print('QtSvg was not found on your system. It is needed for SVG export.')
                else:
                    svg_gen = QSvgGenerator()

                    svg_gen.setFileName(filename)
                    rect = view.scene().sceneRect()
                    svg_gen.setViewBox(rect)
                    svg_gen.setSize(rect.size().toSize())
                    svg_gen.setTitle("SVG Generator Example Drawing")
                    svg_gen.setDescription("An SVG drawing created by the SVG Generator.")

                    painter = QPainter(svg_gen)
                    view.scene().render(painter, target=rect)
                    painter.end()
            else:
                use_transparency = filter_.endswith('(*.png)')
                rect = view.viewport().rect() if type_ == 'current' else view.scene().sceneRect().toRect()
                format = QImage.Format_ARGB32 if use_transparency else QImage.Format_RGB32
                size = rect.size() * 4 if type_ == 'current' else rect.size()
                image = QImage(size, format)
                image.fill(Qt.transparent) if use_transparency else image.fill(Qt.white)
                painter = QPainter(image)
                painter.setRenderHint(QPainter.Antialiasing)
                view.render(painter, source=rect) if type_ == 'current' else view.scene().render(painter)
                image.save(filename)

    def on_show_spectrum_triggered(self, type_, node):
        if self.network.spectra is not None:
            try:
                data = self.network.spectra[node.index()].human_readable_data
            except KeyError:
                dialog = QDialog(self)
                dialog.warning(self, None, 'Selected spectrum does not exists.')
            else:
                # Set data as first or second spectrum
                if type_ == 'compare':
                    self.cvSpectrum.set_spectrum2(data, node.index()+1)
                else:
                    self.cvSpectrum.set_spectrum1(data, node.index()+1)

                # Show spectrum tab
                self.tabWidget.setCurrentIndex(self.tabWidget.indexOf(self.cvSpectrum))

    def on_select_first_neighbors_triggered(self, nodes):
        view = self.current_view
        neighbors = [v.index for node in nodes for v in self.network.graph.vs[node.index()].neighbors()]
        if view == self.gvNetwork:
            self.gvNetwork.scene().setNodesSelection(neighbors)
        elif view == self.gvTSNE:
            self.gvTSNE.scene().setNodesSelection(neighbors)

    def on_use_columns_for(self, type_):
        selected_columns_ids = self.tvNodes.selectionModel().selectedColumns(0)
        len_ = len(selected_columns_ids)
        if type_ == "pie charts":
            if len_ > 0:
                ids = [index.column() for index in selected_columns_ids]
                self.set_nodes_pie_chart_values(ids)
            else:
                reply = QMessageBox.question(self, None,
                                             "No column selected. Do you want to remove pie charts?",
                                             QMessageBox.Yes | QMessageBox.No)
                if reply == QMessageBox.Yes:
                    self.set_nodes_pie_chart_values(None)
        elif type_ == "labels":
            if len_ > 1:
              QMessageBox.information(self, None, "Please select only one column.")
            elif len_ == 1:
                id_ = selected_columns_ids[0].column()
                self.set_nodes_label(id_)
            else:
                reply = QMessageBox.question(self, None,
                                             "No column selected. Do you want to reset labels?",
                                             QMessageBox.Yes | QMessageBox.No)
                if reply == QMessageBox.Yes:
                    self.set_nodes_label(None)

    def on_nodes_table_contextmenu(self, event):
        selected_column_index = self.tvNodes.columnAt(event.x())
        selected_row_index = self.tvNodes.rowAt(event.y())
        if selected_column_index != -1 and selected_row_index != -1:
            menu = QMenu(self)
            action = QAction("Highlight selected nodes", self)
            menu.addAction(action)
            menu.popup(QCursor.pos())
            action.triggered.connect(lambda: self.highlight_selected_nodes())

    def highlight_selected_nodes(self):
        selected_indexes = self.tvNodes.model().mapSelectionToSource(
            self.tvNodes.selectionModel().selection()).indexes()
        selected = tuple(index.row() for index in selected_indexes)
        with utils.SignalBlocker(self.gvNetwork.scene(), self.gvTSNE.scene()):
            self.gvNetwork.scene().setNodesSelection(selected)
            self.gvTSNE.scene().setNodesSelection(selected)

    def on_current_parameters_triggered(self):
        dialog = ui.CurrentParametersDialog(self, options=self.network.options)
        dialog.exec_()

    def on_settings_triggered(self):
        dialog = ui.SettingsDialog(self)
        dialog.exec_()

    def on_full_screen_triggered(self):
        if not self.isFullScreen():
            self.setWindowFlags(Qt.Window)
            self.showFullScreen()
        else:
            self.setWindowFlags(Qt.Widget)
            self.showNormal()

    def on_process_file_triggered(self):
        dialog = ui.ProcessMgfDialog(self, options=self.network.options)
        if dialog.exec_() == QDialog.Accepted:
            self.fname = None
            self.has_unsaved_changes = True
            self.gvNetwork.scene().clear()
            self.gvTSNE.scene().clear()

            process_file, use_metadata, metadata_file, metadata_options, \
            compute_options, tsne_options, network_options = dialog.getValues()
            self.network.options.cosine = compute_options
            self.network.options.tsne = tsne_options
            self.network.options.network = network_options

            worker = self.prepare_read_mgf_worker(process_file, metadata_file, metadata_options)
            if worker is not None:
                self._workers.add(worker)

    def on_import_metadata_triggered(self):
        dialog = ui.ImportMetadataDialog(self)
        if dialog.exec_() == QDialog.Accepted:
            metadata_file, options = dialog.getValues()
            worker = self.prepare_read_metadata_worker(metadata_file, options)
            if worker is not None:
                self._workers.add(worker)

    def on_edit_options_triggered(self, type_):
        if hasattr(self.network, 'scores'):
            if type_ == 'network':
                dialog = ui.EditNetworkOptionsDialog(self, options=self.network.options)
                if dialog.exec_() == QDialog.Accepted:
                    options = dialog.getValues()
                    if options != self.network.options.network:
                        self.network.options.network = options
                        self.has_unsaved_changes = True

                        self.network.interactions = None
                        self.create_graph()
                        self.draw(which='network')
                        self.update_search_menu()
            elif type_ == 't-sne':
                dialog = ui.EditTSNEOptionsDialog(self, options=self.network.options)
                if dialog.exec_() == QDialog.Accepted:
                    options = dialog.getValues()
                    if options != self.network.options.tsne:
                        self.network.options.tsne = options
                        self.has_unsaved_changes = True

                        self.draw(which='t-sne')
                        self.update_search_menu()
        else:
            QMessageBox.information(self, None, "No network found, please open a file first.")

    def on_download_databases_triggered(self):
        dialog = ui.DownloadDatabasesDialog(self, base_path=config.DATABASES_PATH)
        dialog.exec_()

    def on_view_databases_triggered(self):
        path = os.path.join(config.DATABASES_PATH, 'spectra.sqlite')
        if os.path.exists(path) and os.path.isfile(path) and os.path.getsize(path) > 0:
            dialog = ui.ViewDatabasesDialog(self, base_path=config.DATABASES_PATH)
            dialog.exec_()
        else:
            QMessageBox.information(self, None, "No databases found, please download one or more database first.")

    def on_scale_changed(self, type_, scale):
        if type_ == 'network':
            self.gvNetwork.scene().setScale(scale / self.sliderNetworkScale.defaultValue())
        elif type_ == 't-sne':
                self.gvTSNE.scene().setScale(scale / self.sliderNetworkScale.defaultValue())

    def show_items(self, items):
        for item in items:
            item.show()

    def hide_items(self, items):
        for item in items:
            item.hide()

    def minimize_tabwidget(self):
        w = self.tabWidget.cornerWidget(Qt.TopRightCorner)
        if w.arrowType() == Qt.DownArrow:
            w.setArrowType(Qt.UpArrow)
            self.tabWidget.setMaximumHeight(self.tabWidget.tabBar().height())
            self.tabWidget.setDocumentMode(True)
        else:
            w.setArrowType(Qt.DownArrow)
            self.tabWidget.setDocumentMode(False)
            self.tabWidget.setMaximumHeight(QWIDGETSIZE_MAX)

    def set_nodes_label(self, column_id):
        if column_id is not None:
            model = self.tvNodes.model().sourceModel()
            self.gvNetwork.scene().setLabelsFromModel(model, column_id, ui.widgets.LabelRole)
            self.gvTSNE.scene().setLabelsFromModel(model, column_id, ui.widgets.LabelRole)
        else:
            self.gvNetwork.scene().resetLabels()
            self.gvTSNE.scene().resetLabels()

    def set_nodes_pie_chart_values(self, column_ids):
        model = self.tvNodes.model().sourceModel()
        if column_ids is not None:
            colors = utils.generate_colors(len(column_ids))
            self.gvNetwork.scene().setPieColors(colors)
            self.gvTSNE.scene().setPieColors(colors)
            for column in range(model.columnCount()):
                model.setHeaderData(column, Qt.Horizontal, None, role=Qt.BackgroundColorRole)
            for column, color in zip(column_ids, colors):
                color = QColor(color)
                color.setAlpha(128)
                model.setHeaderData(column, Qt.Horizontal, color, role=Qt.BackgroundColorRole)
            self.gvNetwork.scene().setPieChartsFromModel(model, column_ids)
            self.gvTSNE.scene().setPieChartsFromModel(model, column_ids)
        else:
            for column in range(model.columnCount()):
                model.setHeaderData(column, Qt.Horizontal, None, role=Qt.BackgroundColorRole)
            self.gvNetwork.scene().resetPieCharts()
            self.gvTSNE.scene().resetPieCharts()


    def save_settings(self):
        settings = QSettings()
        settings.beginGroup('MainWindow')
        settings.setValue('Geometry', self.saveGeometry())
        settings.setValue('State', self.saveState())
        settings.setValue('TabWidget/State',
                          self.tabWidget.cornerWidget(Qt.TopRightCorner).arrowType() == Qt.UpArrow)
        settings.endGroup()

    def load_settings(self):
        settings = QSettings()
        settings.beginGroup('MainWindow')
        setting = settings.value('Geometry')
        if setting is not None:
            self.restoreGeometry(setting)
        setting = settings.value('State')
        if setting is not None:
            self.restoreState(setting)
        setting = settings.value('TabWidget/State', type=bool)
        if setting:
            self.minimize_tabwidget()

    def create_graph(self):
        # Delete all previously created edges and nodes
        self.network.graph.delete_edges(self.network.graph.es)
        self.network.graph.delete_vertices(self.network.graph.vs)

        nodes_idx = np.arange(self.network.scores.shape[0])
        self.network.graph.add_vertices(nodes_idx.tolist())
        self.network.graph.add_edges(zip(self.network.interactions['Source'], self.network.interactions['Target']))

    def draw(self, compute_layouts=True, which='all'):
        if which == 'all':
            which = {'network', 't-sne'}
        elif isinstance(which, str):
            which = set((which,))

        worker = None
        if 'network' in which:
            if not compute_layouts and self.network.graph.network_layout is not None:
                worker = self.prepare_draw_network_worker(layout=self.network.graph.network_layout)
            else:
                worker = self.prepare_draw_network_worker()

        if 't-sne' in which:
            layout = None

            def draw_tsne():
                worker = self.prepare_draw_tsne_worker(layout=layout)
                self._workers.add(worker)

            if not compute_layouts and self.network.graph.tsne_layout is not None:
                layout = self.network.graph.tsne_layout

            if worker is not None:
                worker.finished.connect(draw_tsne)
            else:
                draw_tsne()

        if worker is not None:
            self._workers.add(worker)

        self.update_search_menu()

    def apply_layout(self, type_, layout):
        if type_ == 'network':
            self.gvNetwork.scene().setLayout(layout)
            self.network.graph.network_layout = layout
        elif type_ == 't-sne':
            self.gvTSNE.scene().setLayout(layout)
            self.network.graph.tsne_layout = layout

    def prepare_draw_network_worker(self, layout=None):
        self.gvNetwork.scene().clear()

        interactions = self.network.interactions

        widths = np.array(interactions['Cosine'])
        min_ = max(0, widths.min() - 0.1)
        if min_ != widths.max():
            widths = (config.RADIUS - 1) * (widths - min_) / (widths.max() - min_) + 1
        else:
            widths = config.RADIUS

        self.network.graph.es['__weight'] = interactions['Cosine']
        self.network.graph.es['__width'] = widths

        # Add nodes
        nodes = self.gvNetwork.scene().addNodes(self.network.graph.vs.indices)

        # Add edges
        edges_attr = [(e.index, nodes[e.source], nodes[e.target], e['__weight'], e['__width'])
                      for e in self.network.graph.es if not e.is_loop()]
        self.gvNetwork.scene().addEdges(*zip(*edges_attr))

        if layout is None:
            # Compute layout
            def process_finished():
                layout = worker.result()
                if layout is not None:
                    self.apply_layout('network', layout)

            worker = workers.NetworkWorker(self.network.graph)
            worker.finished.connect(process_finished)

            return worker
        else:
            worker = workers.GenericWorker(self.apply_layout, 'network', layout)
            return worker

    def prepare_draw_tsne_worker(self, layout=None):
        self.gvTSNE.scene().clear()

        # Add nodes
        self.gvTSNE.scene().addNodes(self.network.graph.vs.indices)

        if layout is None:
            # Compute layout
            def process_finished():
                layout = worker.result()
                if layout is not None:
                    self.apply_layout('t-sne', layout)

            worker = workers.TSNEWorker(self.network.scores, self.network.options.tsne)
            worker.finished.connect(process_finished)

            return worker
        else:
            worker = workers.GenericWorker(self.apply_layout, 't-sne', layout)
            return worker

    def prepare_compute_scores_worker(self, spectra, use_multiprocessing):
        def error(e):
            if e.__class__ == OSError:
                QMessageBox.warning(self, None, str(e))
            else:
                raise e

        worker = workers.ComputeScoresWorker(spectra, use_multiprocessing, self.network.options.cosine)
        worker.error.connect(error)

        return worker

    def prepare_read_mgf_worker(self, mgf_filename, metadata_filename=None,
                                metadata_options=workers.ReadMetadataOptions()):
        worker = workers.ReadMGFWorker(mgf_filename, self.network.options.cosine)

        def file_read():
            nonlocal worker
            self.tvNodes.model().sourceModel().beginResetModel()
            self.network.spectra = worker.result()
            self.tvNodes.model().sourceModel().endResetModel()
            multiprocess = len(self.network.spectra) > 1000  # TODO: Tune this, arbitrary decision
            worker = self.prepare_compute_scores_worker(self.network.spectra, multiprocess)
            if worker is not None:
                worker.finished.connect(scores_computed)
                self._workers.add(worker)

        def error(e):
            if e.__class__ == PyteomicsError:
                QMessageBox.warning(self, None, e.message)

        def scores_computed():
            nonlocal worker
            self.tvEdges.model().sourceModel().beginResetModel()
            self.network.scores = worker.result()
            self.network.interactions = None
            self.tvEdges.model().sourceModel().endResetModel()
            self.create_graph()
            self.draw()
            if metadata_filename is not None:
                worker = self.prepare_read_metadata_worker(metadata_filename, metadata_options)
                if worker is not None:
                    self._workers.add(worker)

        worker.finished.connect(file_read)
        worker.error.connect(error)
        return worker

    def prepare_read_metadata_worker(self, filename, options):
        def file_read():
            nonlocal worker
            self.tvNodes.model().sourceModel().beginResetModel()
            self.network.infos = worker.result()  # TODO: Append metadata instead of overriding
            self.has_unsaved_changes = True
            self.tvNodes.model().sourceModel().endResetModel()

        def error(e):
            QMessageBox.warning(self, None, str(e))

        worker = workers.ReadMetadataWorker(filename, options)
        worker.finished.connect(file_read)
        worker.error.connect(error)

        return worker

    def prepare_save_project_worker(self, fname):
        """Save current project to a file for future access"""

        def process_finished():
            self.fname = fname
            self.has_unsaved_changes = False

        def error(e):
            if e.__class__ == PermissionError:
                QMessageBox.warning(self, None, str(e))
            else:
                raise e

        worker = workers.SaveProjectWorker(fname, self.network.graph, self.network, self.network.options)
        worker.finished.connect(process_finished)
        worker.error.connect(error)

        return worker

    def prepare_load_project_worker(self, fname):
        """Load project from a previously saved file"""

        def process_finished():
            self.sliderNetworkScale.resetValue()
            self.sliderTSNEScale.resetValue()

            self.tvNodes.model().sourceModel().beginResetModel()
            self.network = worker.result()
            self.tvNodes.model().sourceModel().endResetModel()

            # Draw
            self.draw(compute_layouts=False)

            # Save filename and set window title
            self.fname = fname
            self.has_unsaved_changes = False

        def error(e):
            if isinstance(e, FileNotFoundError):
                QMessageBox.warning(self, None, f"File '{self.filename}' not found.")
            elif isinstance(e, errors.UnsupportedVersionError):
                QMessageBox.warning(self, None, str(e))
            elif isinstance(e, KeyError):
                QMessageBox.critical(self, None, str(e))
            else:
                raise e

        worker = workers.LoadProjectWorker(fname)
        worker.finished.connect(process_finished)
        worker.error.connect(error)

        return worker
