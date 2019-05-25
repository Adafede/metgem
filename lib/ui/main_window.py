import csv
import io
from typing import List, Callable

from .. import config, ui, utils, workers, errors
from ..utils.network import Network
from ..logger import get_logger, debug

import os
import sys
import json
import zipfile
import subprocess

import requests

import numpy as np
import igraph as ig
import sqlalchemy

from PyQt5.QtWidgets import (QDialog, QFileDialog, QMessageBox, QWidget, QMenu, QActionGroup,
                             QAction, QDockWidget, qApp, QWidgetAction, QTableView, QComboBox, QToolBar, QSplitter,
                             QGraphicsLineItem, QApplication, QGraphicsView, QLineEdit)
from PyQt5.QtCore import QSettings, Qt, QCoreApplication
from PyQt5.QtGui import QPainter, QImage, QCursor, QColor, QKeyEvent, QIcon, QFontMetrics, QFont, QPen, QKeySequence

from PyQt5 import uic

from PyQtNetworkView import NetworkScene, style_from_css, style_to_cytoscape, disable_opengl

from libmetgem import human_readable_data


UI_FILE = os.path.join(os.path.dirname(__file__), 'main_window.ui')
MainWindowUI, MainWindowBase = uic.loadUiType(UI_FILE, from_imports='lib.ui', import_from='lib.ui')


COLUMN_MAPPING_PIE_CHARTS = 0
COLUMN_MAPPING_LABELS = 1
COLUMN_MAPPING_NODES_SIZES = 2


# noinspection PyCallByClass,PyArgumentList
class MainWindow(MainWindowBase, MainWindowUI):

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

        self._logger = get_logger()

        # Keep track of unsaved changes
        self._has_unsaved_changes = False

        # Opened file
        self.fname = None

        # Workers' references
        self._workers = workers.WorkerSet(self, ui.ProgressDialog(self))

        # Setup User interface
        if not config.get_use_opengl_flag():
            disable_opengl(True)
        self.setupUi(self)
        self.gvNetwork.setScene(NetworkScene())
        self.gvNetwork.setFocus()
        self.gvTSNE.setScene(NetworkScene())

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

        # Arrange dock widgets
        self.tabifyDockWidget(self.dockNodes, self.dockEdges)
        self.tabifyDockWidget(self.dockEdges, self.dockSpectra)
        self.dockNodes.raise_()

        # Create node mappings toolbar button's menus
        menu = QMenu()
        menu.addAction(self.actionUseColumnForLabels)
        menu.addAction(self.actionResetLabelMapping)
        self.btUseColumnForLabels.setMenu(menu)
        self.btUseColumnForLabels.setDefaultAction(self.actionUseColumnForLabels)

        menu = QMenu()
        menu.addAction(self.actionUseColumnsForPieCharts)
        menu.addAction(self.actionResetColorMapping)
        self.btUseColumnsForPieCharts.setMenu(menu)
        self.btUseColumnsForPieCharts.setDefaultAction(self.actionUseColumnsForPieCharts)

        menu = QMenu()
        menu.addAction(self.actionUseColumnForNodesSizes)
        menu.addAction(self.actionResetSizeMapping)
        self.btUseColumnForNodesSizes.setMenu(menu)
        self.btUseColumnForNodesSizes.setDefaultAction(self.actionUseColumnForNodesSizes)

        # Reorganise export as image actions
        export_button = ui.widgets.ToolBarMenu()
        export_button.setDefaultAction(self.actionExportAsImage)
        export_button.addAction(self.actionExportAsImage)
        export_button.addAction(self.actionExportCurrentViewAsImage)
        self.tbExport.insertWidget(self.actionExportAsImage, export_button)
        self.tbExport.removeAction(self.actionExportAsImage)
        self.tbExport.removeAction(self.actionExportCurrentViewAsImage)

        # Reorganize export metadata actions
        export_button = ui.widgets.ToolBarMenu()
        export_button.setDefaultAction(self.actionExportMetadata)
        export_button.addAction(self.actionExportMetadata)
        export_button.addAction(self.actionExportDatabaseResults)
        self.tbExport.insertWidget(self.actionExportMetadata, export_button)
        self.tbExport.removeAction(self.actionExportMetadata)
        self.tbExport.removeAction(self.actionExportDatabaseResults)

        color_button = ui.widgets.ColorPicker(self.actionSetNodesColor, color_group='Node', default_color=Qt.blue)
        self.tbNetwork.insertWidget(self.actionSetNodesColor, color_button)
        self.tbNetwork.removeAction(self.actionSetNodesColor)

        size_combo = QComboBox(self.tbNetwork)
        size_combo.setFixedSize(self.tbNetwork.height() + 60, self.tbNetwork.height())
        size_combo.setEditable(True)
        size_combo.setInsertPolicy(QComboBox.NoInsert)
        items = [str(x) for x in range(10, 101, 10)]
        size_combo.addItems(items)
        size_combo.setCurrentText(str(config.RADIUS))
        size_combo.setCurrentIndex(items.index(str(config.RADIUS)))
        size_combo.setStatusTip(self.actionSetNodesSize.statusTip())
        size_combo.setToolTip(self.actionSetNodesSize.toolTip())
        edit = QLineEdit()
        size_action = edit.addAction(self.actionSetNodesSize.icon(), QLineEdit.LeadingPosition)
        size_combo.setLineEdit(edit)
        self.tbNetwork.insertWidget(self.actionSetNodesSize, size_combo)
        self.tbNetwork.removeAction(self.actionSetNodesSize)

        # Send Scale sliders to a toolbutton menu
        for widget, button in {(self.sliderNetworkScale, self.btNetworkRuler),
                               (self.sliderTSNEScale, self.btTSNERuler)}:
            menu = QMenu()
            action = QWidgetAction(self)
            action.setDefaultWidget(widget)
            menu.addAction(action)
            button.setMenu(menu)

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

            self.jupyter_dock_widget = QDockWidget()
            self.jupyter_dock_widget.setObjectName('jupyter')
            self.jupyter_dock_widget.setWindowTitle('Jupyter Console')
            self.jupyter_dock_widget.setWidget(self.jupyter_widget)

            self.addDockWidget(Qt.TopDockWidgetArea, self.jupyter_dock_widget)
            kernel_manager.kernel.shell.push({'app': qApp, 'win': self})

            # Fix issue with Jupyter 5.0+, see https://github.com/ipython/ipykernel/pull/376
            if hasattr(kernel_manager.kernel, '_abort_queue'):
                kernel_manager.kernel._abort_queues = kernel_manager.kernel._abort_queue

        # Connect events
        self.tvNodes.customContextMenuRequested.connect(self.on_nodes_table_contextmenu)
        self.tvEdges.customContextMenuRequested.connect(self.on_edges_table_contextmenu)
        self.actionUseColumnForLabels.triggered.connect(
            lambda: self.on_use_columns_for(COLUMN_MAPPING_LABELS))
        self.actionResetLabelMapping.triggered.connect(lambda: self.set_nodes_label(None))
        self.actionUseColumnsForPieCharts.triggered.connect(
            lambda: self.on_use_columns_for(COLUMN_MAPPING_PIE_CHARTS))
        self.actionResetColorMapping.triggered.connect(lambda: self.set_nodes_pie_chart_values(None))
        self.actionUseColumnForNodesSizes.triggered.connect(
            lambda: self.on_use_columns_for(COLUMN_MAPPING_NODES_SIZES))
        self.actionResetSizeMapping.triggered.connect(lambda: self.set_nodes_sizes_values(None))

        for view in (self.gvNetwork, self.gvTSNE):
            view.scene().selectionChanged.connect(self.on_scene_selection_changed)
            view.focusedIn.connect(lambda: self.on_scene_selection_changed(update_view=False))
            view.scene().pieChartsVisibilityChanged.connect(
                lambda visibility: self.actionSetPieChartsVisibility.setChecked(visibility))

        self.actionQuit.triggered.connect(self.close)
        self.actionAbout.triggered.connect(lambda: ui.AboutDialog().exec_())
        self.actionAboutQt.triggered.connect(lambda: QMessageBox.aboutQt(self))
        self.actionProcessFile.triggered.connect(self.on_process_file_triggered)
        self.actionImportMetadata.triggered.connect(self.on_import_metadata_triggered)
        self.actionImportGroupMapping.triggered.connect(self.on_import_group_mapping_triggered)
        self.actionCurrentParameters.triggered.connect(self.on_current_parameters_triggered)
        self.actionPreferences.triggered.connect(self.on_preferences_triggered)
        self.actionResetLayout.triggered.connect(self.reset_layout)
        self.actionOpenUserFolder.triggered.connect(self.on_open_user_folder_triggered)
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

        self.actionViewMiniMap.triggered.connect(self.on_switch_minimap_visibility)
        qApp.focusChanged.connect(self.on_focus_changed)
        self.actionViewSpectrum.triggered.connect(lambda: self.on_show_spectrum_triggered('show'))
        self.actionViewCompareSpectrum.triggered.connect(lambda: self.on_show_spectrum_triggered('compare'))

        self.actionFullScreen.triggered.connect(self.on_full_screen_triggered)
        self.actionHideSelected.triggered.connect(lambda: self.current_view.scene().hideSelectedItems())
        self.actionShowAll.triggered.connect(lambda: self.current_view.scene().showAllItems())
        self.actionHideIsolatedNodes.triggered.connect(lambda: self.draw(compute_layouts=False))
        color_button.colorSelected.connect(self.on_set_selected_nodes_color)
        size_combo.currentIndexChanged['QString'].connect(self.on_set_selected_nodes_size)
        size_action.triggered.connect(lambda: self.on_set_selected_nodes_size(size_combo.currentText()))
        self.actionNeighbors.triggered.connect(
            lambda: self.on_select_first_neighbors_triggered(self.current_view.scene().selectedNodes()))
        self.actionSetPieChartsVisibility.toggled.connect(self.on_set_pie_charts_visibility_toggled)
        self.actionExportToCytoscape.triggered.connect(self.on_export_to_cytoscape_triggered)
        self.actionExportAsImage.triggered.connect(lambda: self.on_export_as_image_triggered('full'))
        self.actionExportCurrentViewAsImage.triggered.connect(lambda: self.on_export_as_image_triggered('current'))
        self.actionExportMetadata.triggered.connect(self.on_export_metadata)
        self.actionExportDatabaseResults.triggered.connect(self.on_export_db_results)

        self.actionDownloadDatabases.triggered.connect(self.on_download_databases_triggered)
        self.actionImportUserDatabase.triggered.connect(self.on_import_user_database_triggered)
        self.actionViewDatabases.triggered.connect(self.on_view_databases_triggered)

        self.actionLockCurrentView.triggered.connect(self.on_lock_current_view_triggered)
        self.btNetworkLock.toggled.connect(lambda x: self.gvNetwork.scene().lock(x))
        self.btTSNELock.toggled.connect(lambda x: self.gvTSNE.scene().lock(x))
        self.gvNetwork.scene().locked.connect(self.on_scene_locked)
        self.gvTSNE.scene().locked.connect(self.on_scene_locked)

        self.btNetworkOptions.clicked.connect(lambda: self.on_edit_options_triggered('network'))
        self.btTSNEOptions.clicked.connect(lambda: self.on_edit_options_triggered('t-sne'))

        self.dockNodes.visibilityChanged.connect(lambda v: self.update_search_menu(self.tvNodes) if v else None)
        self.dockEdges.visibilityChanged.connect(lambda v: self.update_search_menu(self.tvEdges) if v else None)
        self.dockSpectra.visibilityChanged.connect(lambda v: self.update_search_menu(self.tvNodes) if v else None)

        self.sliderNetworkScale.valueChanged.connect(lambda val: self.on_scale_changed('network', val))
        self.sliderTSNEScale.valueChanged.connect(lambda val: self.on_scale_changed('t-sne', val))

        self.tvNodes.viewDetailsClicked.connect(self.on_view_details_clicked)
        self.tvNodes.model().dataChanged.connect(self.on_nodes_table_data_changed)

        # Add a menu to show/hide toolbars
        popup_menu = self.createPopupMenu()
        popup_menu.setTitle("Toolbars")
        self.menuView.addMenu(popup_menu)

        # Populate list of recently opened projects
        menu = QMenu()
        self.recent_projects = []

        self.actionRecentProjects.setMenu(menu)
        for i in range(10):
            action = QAction(self)
            action.setVisible(False)
            action.triggered.connect(self.on_open_recent_project_triggered)
            menu.addAction(action)
        menu.addSeparator()
        action = QAction("&Clear menu", self)
        action.triggered.connect(lambda: self.update_recent_projects(clear=True))
        menu.addAction(action)

        # Build research bar
        self._last_table = self.tvNodes
        self.update_search_menu()

    @debug
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

    # noinspection PyAttributeOutsideInit
    @network.setter
    def network(self, network):
        network.infosAboutToChange.connect(self.tvNodes.model().sourceModel().beginResetModel)
        network.infosChanged.connect(self.tvNodes.model().sourceModel().endResetModel)
        network.interactionsAboutToChange.connect(self.tvEdges.model().sourceModel().beginResetModel)
        network.interactionsChanged.connect(self.tvEdges.model().sourceModel().endResetModel)

        self.tvNodes.setColumnHidden(1, network.db_results is None or len(network.db_results) == 0)

        self._network = network

    @debug
    def nodes_selection(self):
        selected_indexes = self.tvNodes.model().mapSelectionToSource(
            self.tvNodes.selectionModel().selection()).indexes()
        return {index.row() for index in selected_indexes}

    @debug
    def edges_selection(self):
        selected_indexes = self.tvEdges.model().mapSelectionToSource(
            self.tvEdges.selectionModel().selection()).indexes()
        return {index.row() for index in selected_indexes}

    @debug
    def load_project(self, filename):
        self.reset_project()
        worker = self.prepare_load_project_worker(filename)
        if worker is not None:
            self._workers.add(worker)

    @debug
    def save_project(self, filename):
        worker = self.prepare_save_project_worker(filename)
        if worker is not None:
            self._workers.add(worker)

    @debug
    def reset_project(self):
        self.fname = None
        self.has_unsaved_changes = False
        try:
            self.network.spectra.close()
        except AttributeError:
            pass
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

    @debug
    def update_search_menu(self, table: QTableView=None):
        if table is None:
            table = self._last_table

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
        group.triggered.connect(lambda act: table.model().setFilterKeyColumn(act.data() - 1))
        model.setFilterKeyColumn(-1)

        self._last_table = table

    def update_recent_projects(self, add_fname=None, remove_fname=None, clear=False):
        if clear:
            self.recent_projects = []
        elif remove_fname is not None:
            try:
                self.recent_projects.remove(remove_fname)
            except ValueError:
                pass

        if add_fname is not None:
            try:
                self.recent_projects.remove(add_fname)
            except ValueError:
                pass
            self.recent_projects.insert(0, add_fname)

        self.recent_projects = self.recent_projects[:10]

        actions = self.actionRecentProjects.menu().actions()
        for i, act in enumerate(actions):
            if act.isSeparator():
                break

            try:
                fname = self.recent_projects[i]
                act.setText(f"{i+1} | {fname}")
                act.setData(fname)
                act.setVisible(True)
            except IndexError:
                act.setVisible(False)

    def on_lock_current_view_triggered(self):
        """Switch lock mode of network views"""

        if self.current_view == self.gvTSNE:
            self.btTSNELock.setChecked(not self.btTSNELock.isChecked())
        else:
            self.btNetworkLock.setChecked(not self.btNetworkLock.isChecked())

    def on_scene_locked(self, locked: bool=True, scene=None):
        scene = scene if scene is not None else self.sender()
        locked = self.btTSNELock.isChecked() if scene == self.gvTSNE.scene() else self.btNetworkLock.isChecked()
        self.actionLockCurrentView.setChecked(locked)
        self.actionLockCurrentView.setText(f"{'Unlock' if locked else 'Lock'} Current View")

    def keyPressEvent(self, event: QKeyEvent):
        widget = QApplication.focusWidget()

        if event.matches(QKeySequence.NextChild):
            # Navigate between GraphicsViews
            if self.gvNetwork.hasFocus():
                self.gvTSNE.setFocus(Qt.TabFocusReason)
            else:
                self.gvNetwork.setFocus(Qt.TabFocusReason)

        elif widget is not None:
            if isinstance(widget, QGraphicsView):
                # Copy image to clipboard
                event_without_shift = QKeyEvent(event.type(), event.key(), event.modifiers() ^ Qt.ShiftModifier)
                if event.matches(QKeySequence.Copy) or event_without_shift.matches(QKeySequence.Copy):
                    type_ = 'full' if event.modifiers() & Qt.ShiftModifier else 'current'
                    self.on_export_as_image_triggered(type_, to_clipboard=True)
            elif isinstance(widget, QTableView) and event.matches(QKeySequence.Copy):
                # Copy data to clipboard
                selection = widget.selectedIndexes()
                if selection is not None:
                    rows = sorted(index.row() for index in selection)
                    first_row = rows[0]
                    columns = sorted(index.column() for index in selection)
                    first_column = columns[0]
                    rowcount = rows[-1] - first_row + 1
                    colcount = columns[-1] - first_column + 1
                    selected_columns = widget.selectionModel().selectedColumns()
                    add_header = len(selected_columns) > 0

                    if add_header:
                        rowcount += 1

                    table = [[''] * colcount for _ in range(rowcount)]

                    if add_header:
                        table[0] = [widget.model().headerData(c.column(), Qt.Horizontal) for c in selected_columns]

                    for index in selection:
                        row = index.row() - first_row + add_header
                        column = index.column() - first_column
                        table[row][column] = index.data()

                    stream = io.StringIO()
                    csv.writer(stream, delimiter='\t').writerows(table)
                    QApplication.clipboard().setText(stream.getvalue())

    def showEvent(self, event):
        super().showEvent(event)
        if not hasattr(self, '_first_show'):
            self.load_settings()
            self._first_show = False
        self.gvNetwork.setMinimumHeight(self.height() / 2)

    def resizeEvent(self, event):
        super().resizeEvent(event)
        self.gvNetwork.setMinimumWidth(self.width() / 3)
        self.gvTSNE.setMinimumWidth(self.width() / 3)

    def closeEvent(self, event):
        if not config.get_debug_flag():
            reply = self.confirm_save_changes()
            if reply == QMessageBox.Cancel:
                event.ignore()
                return

        if not config.get_debug_flag() and self._workers:
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

    # noinspection PyUnusedLocal
    @debug
    def on_focus_changed(self, old: QWidget, now: QWidget):
        if now in (self.gvNetwork, self.gvTSNE):
            self.actionViewMiniMap.setChecked(self.current_view.minimap.isVisible())
            self.on_scene_locked(scene=now.scene())

    @debug
    def on_switch_minimap_visibility(self, *args):
        view = self.current_view
        visible = view.minimap.isVisible()
        view.minimap.setVisible(not visible)
        self.actionViewMiniMap.setChecked(not visible)

    @debug
    def on_scene_selection_changed(self, update_view=True):
        view = self.current_view
        nodes_idx = [item.index() for item in view.scene().selectedNodes()]
        edges_idx = [item.index() for item in view.scene().selectedEdges()]
        self.tvNodes.model().setSelection(nodes_idx)
        self.tvEdges.model().setSelection(edges_idx)

        if update_view and self.actionLinkViews.isChecked():
            if view == self.gvNetwork:
                with utils.SignalBlocker(self.gvTSNE.scene()):
                    self.gvTSNE.scene().setNodesSelection(nodes_idx)
            elif view == self.gvTSNE:
                with utils.SignalBlocker(self.gvNetwork.scene()):
                    self.gvNetwork.scene().setNodesSelection(nodes_idx)

    @debug
    def on_set_selected_nodes_color(self, color: QColor):
        for scene in (self.gvNetwork.scene(), self.gvTSNE.scene()):
            scene.setSelectedNodesColor(color)

        self.network.graph.vs['__color'] = self.gvNetwork.scene().nodesColors()
        self.has_unsaved_changes = True

    @debug
    def on_set_selected_nodes_size(self, text: str):
        try:
            size = int(text)
        except ValueError:
            return

        for scene in (self.gvNetwork.scene(), self.gvTSNE.scene()):
            scene.setSelectedNodesRadius(size)

        self.network.graph.vs['__size'] = self.gvNetwork.scene().nodesRadii()
        self.has_unsaved_changes = True

    @debug
    def on_do_search(self, *args):
        if self._last_table is None:
            return
        self._last_table.model().setFilterRegExp(str(self.leSearch.text()))

    @debug
    def on_new_project_triggered(self, *args):
        reply = self.confirm_save_changes()

        if reply != QMessageBox.Cancel:
            self.reset_project()

        return reply

    @debug
    def on_open_recent_project_triggered(self, *args):
        action = self.sender()
        if action is not None:
            self.load_project(action.data())

    @debug
    def on_open_project_triggered(self, *args):
        reply = self.confirm_save_changes()
        if reply == QMessageBox.Cancel:
            return

        dialog = QFileDialog(self)
        dialog.setFileMode(QFileDialog.ExistingFile)
        dialog.setNameFilters([f"{QCoreApplication.applicationName()} Files (*{config.FILE_EXTENSION})",
                               "All files (*.*)"])
        if dialog.exec_() == QDialog.Accepted:
            filename = dialog.selectedFiles()[0]
            self.load_project(filename)

    @debug
    def on_save_project_triggered(self, *args):
        if self.fname is None:
            self.on_save_project_as_triggered()
        else:
            self.save_project(self.fname)

    @debug
    def on_save_project_as_triggered(self, *args):
        dialog = QFileDialog(self)
        dialog.setAcceptMode(QFileDialog.AcceptSave)
        dialog.setNameFilters([f"{QCoreApplication.applicationName()} Files (*{config.FILE_EXTENSION})",
                               "All files (*.*)"])
        if dialog.exec_() == QDialog.Accepted:
            filename = dialog.selectedFiles()[0]
            self.save_project(filename)

    @debug
    def on_set_pie_charts_visibility_toggled(self, visibility):
        for view in (self.gvNetwork, self.gvTSNE):
            scene = view.scene()
            scene.setPieChartsVisibility(visibility)
            view.updateVisibleItems()

    @debug
    def on_export_to_cytoscape_triggered(self, *args):
        try:
            from py2cytoscape.data.cyrest_client import CyRestClient
            from py2cytoscape import cyrest

            view = self.current_view

            cy = CyRestClient()

            self._logger.debug('Creating exportable copy of the graph object')
            g = self.network.graph.copy()

            try:
                g.es['cosine'] = g.es['__weight']
                g.es['interaction'] = 'interacts with'
                g.es['name'] = [f"{e.source} (interacts with) {e.target}" for e in g.es]
            except KeyError:
                pass

            for attr in g.vs.attributes():
                if attr.startswith('__'):
                    del g.vs[attr]
                else:
                    g.vs[attr] = [str(x+1) for x in g.vs[attr]]
            if view == self.gvTSNE:
                g.delete_edges(g.es)  # in a t-SNE layout, edges does not makes any sense
            else:
                g.delete_edges([edge for edge in g.es if edge.is_loop()])
                for attr in g.es.attributes():
                    if attr.startswith('__'):
                        del g.es[attr]

            # cy.session.delete()
            self._logger.debug('CyREST: Creating network')
            g_cy = cy.network.create_from_igraph(g)

            self._logger.debug('CyREST: Set layout')
            layout = np.empty((g.vcount(), 2))
            for item in view.scene().nodes():
                layout[item.index()] = (item.x(), item.y())
            positions = [(suid, x, y) for suid, (x, y) in zip(g_cy.get_nodes()[::-1], layout)]
            cy.layout.apply_from_presets(network=g_cy, positions=positions)

            self._logger.debug('CyREST: Set style')
            style_js = style_to_cytoscape(view.scene().networkStyle())
            style = cy.style.create(style_js['title'], style_js)
            cy.style.apply(style, g_cy)

            # Fit view to content
            cyrest.cyclient().view.fit_content()
        except (ConnectionRefusedError, requests.ConnectionError):
            QMessageBox.information(self, None,
                                    'Please launch Cytoscape before trying to export.')
            self._logger.error('Cytoscape was not launched.')
        except json.decoder.JSONDecodeError:
            QMessageBox.information(self, None,
                                    'Cytoscape was not ready to receive data. Please try again.')
            self._logger.error('Cytoscape was not ready to receive data.')
        except ImportError:
            QMessageBox.information(self, None,
                                    ('py2tocytoscape is required for this action '
                                     'https://pypi.python.org/pypi/py2cytoscape).'))
            self._logger.error('py2cytoscape not found.')
        except requests.exceptions.HTTPError as e:
            QMessageBox.warning(self, None, 'The following error occurred during export to Cytoscape: {str(e)}')
            e.strerror
            self._logger.error(f'py2cytoscape HTTPError: {str(e)}')

    @debug
    def on_export_as_image_triggered(self, type_, to_clipboard=False):
        view = self.current_view

        if to_clipboard:
            filename = '__clipboard__'
            filter_ = ''
        else:
            filter_ = ["PNG - Portable Network Graphics (*.png)",
                       "JPEG - Joint Photographic Experts Group (*.jpeg)",
                       "SVG - Scalable Vector Graphics (*.svg)",
                       "BMP - Windows Bitmap (*.bmp)"]
            if type_ == 'current':
                filter_.remove("SVG - Scalable Vector Graphics (*.svg)")

            filename, filter_ = QFileDialog.getSaveFileName(self, "Save image",
                                                            filter=";;".join(filter_))

        if filename:
            if filter_.endswith("(*.svg)"):
                try:
                    from PyQt5.QtSvg import QSvgGenerator
                except ImportError:
                    QMessageBox.warning(self, None, 'QtSvg was not found on your system. It is needed for SVG export.')
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
                fmt = QImage.Format_ARGB32 if use_transparency else QImage.Format_RGB32
                size = rect.size() * 4 if type_ == 'current' else rect.size()
                image = QImage(size, fmt)
                image.fill(Qt.transparent) if use_transparency else image.fill(Qt.white)
                painter = QPainter(image)
                painter.setRenderHint(QPainter.Antialiasing)
                view.render(painter, source=rect) if type_ == 'current' else view.scene().render(painter)

                if to_clipboard:
                    QApplication.clipboard().setImage(image)
                else:
                    image.save(filename)

    @debug
    def on_export_metadata(self, *args):
        filter_ = ["CSV - Comma Separated Values (*.csv)",
                   "TSV - Tab Separated Values (*.tsv)"]

        filename, filter_ = QFileDialog.getSaveFileName(self, "Export metadata",
                                                        filter=";;".join(filter_))

        if filename:
            sep = '\t' if filter_.endswith("(*.tsv)") else ','

            worker = self.prepare_export_metadata_worker(filename, self.tvNodes.model().sourceModel(), sep)
            if worker is not None:
                self._workers.add(worker)

    @debug
    def on_export_db_results(self, *args):
        filter_ = ["YAML - YAML Ain't Markup Language (*.yaml)",
                   "JSON - JavaScript Notation Object (*.json)"]

        filename, filter_ = QFileDialog.getSaveFileName(self, "Export Database Results",
                                                        filter=";;".join(filter_))

        if filename:
            fmt = 'json' if filter_.endswith("(*.json)") else 'yaml'
            worker = self.prepare_export_db_results_worker(filename, self.tvNodes.model().sourceModel(), fmt=fmt)
            if worker is not None:
                self._workers.add(worker)

    @debug
    def on_show_spectrum_triggered(self, type_, node=None, node_idx=None):
        if getattr(self.network, 'spectra', None) is not None:
            try:
                if node_idx is None:
                    if node is None:
                        # No node specified, try to get it from current view's selection
                        node = self.current_view.scene().selectedNodes()[0]
                    node_idx = node.index()

                data = human_readable_data(self.network.spectra[node_idx])

                mz_parent = self.network.mzs[node_idx]
            except IndexError:
                pass
            except KeyError:
                QMessageBox.warning(self, None, 'Selected spectrum does not exists.')
            else:
                # Set data as first or second spectrum
                if type_ == 'compare':
                    score = self.network.scores[self.cvSpectrum.spectrum1_index, node_idx] \
                        if self.cvSpectrum.spectrum1_index is not None else None
                    set_spectrum = self.cvSpectrum.set_spectrum2
                else:
                    score = self.network.scores[node_idx, self.cvSpectrum.spectrum2_index] \
                        if self.cvSpectrum.spectrum2_index is not None else None
                    set_spectrum = self.cvSpectrum.set_spectrum1
                if score is not None:
                    self.cvSpectrum.set_title(f'Score: {score:.4f}')
                set_spectrum(data, node_idx, mz_parent)

                # Show spectrum tab
                self.dockSpectra.show()
                self.dockSpectra.raise_()

    @debug
    def on_select_first_neighbors_triggered(self, nodes, *args):
        view = self.current_view
        neighbors = [v.index for node in nodes for v in self.network.graph.vs[node.index()].neighbors()]
        if view == self.gvNetwork:
            self.gvNetwork.scene().setNodesSelection(neighbors)
        elif view == self.gvTSNE:
            self.gvTSNE.scene().setNodesSelection(neighbors)

    @debug
    def on_use_columns_for(self, type_):
        if self.tvNodes.model().columnCount() <= 1:
            return

        selected_columns_indexes = self.tvNodes.selectionModel().selectedColumns(0)
        len_ = len(selected_columns_indexes)

        if type_ == COLUMN_MAPPING_LABELS:
            if len_ == 0:
                return
            elif len_ > 1:
                QMessageBox.information(self, None, "Please select only one column.")
            else:
                id_ = selected_columns_indexes[0].column()
                self.set_nodes_label(id_)
                self.has_unsaved_changes = True
        elif type_ == COLUMN_MAPPING_PIE_CHARTS:
            dialog = ui.ColorMappingDialog(self.tvNodes.model(), selected_columns_indexes)
            if dialog.exec_() == QDialog.Accepted:
                columns, colors = dialog.getValues()
                self.set_nodes_pie_chart_values(columns, colors)
                self.has_unsaved_changes = True
        elif type_ == COLUMN_MAPPING_NODES_SIZES:
            if len_ > 1:
                QMessageBox.information(self, None, "Please select only one column.")
            else:
                id_ = selected_columns_indexes[0].column() if len_ > 0 else -1
                dialog = ui.SizeMappingDialog(self.tvNodes.model(), id_)
                if dialog.exec_() == QDialog.Accepted:
                    id_, func = dialog.getValues()
                    if id_ > 0:
                        self.set_nodes_sizes_values(id_, func)
                self.has_unsaved_changes = True

    @debug
    def on_nodes_table_contextmenu(self, event):
        column_index = self.tvNodes.columnAt(event.x())
        row_index = self.tvNodes.rowAt(event.y())
        if column_index != -1 and row_index != -1:
            model = self.tvNodes.model()
            node_idx = model.mapToSource(model.index(row_index, column_index)).row()
            menu = QMenu(self)
            action = QAction(QIcon(":/icons/images/highlight-yellow.svg"), "Highlight selected nodes", self)
            action.triggered.connect(self.highlight_selected_nodes)
            menu.addAction(action)
            action = QAction(self.actionViewSpectrum.icon(), "View Spectrum", self)
            action.triggered.connect(lambda: self.on_show_spectrum_triggered('show', node_idx=node_idx))
            menu.addAction(action)
            action = QAction(self.actionViewCompareSpectrum.icon(), "Compare Spectrum", self)
            action.triggered.connect(lambda: self.on_show_spectrum_triggered('compare', node_idx=node_idx))
            menu.addAction(action)
            action = QAction(QIcon(":/icons/images/library-query.svg"), "Find standards in library", self)
            action.triggered.connect(lambda: self.on_query_databases('standards'))
            menu.addAction(action)
            action = QAction(QIcon(":/icons/images/library-query-analogs.svg"), "Find analogs in library", self)
            action.triggered.connect(lambda: self.on_query_databases('analogs'))
            menu.addAction(action)
            menu.popup(QCursor.pos())

    @debug
    def on_nodes_table_data_changed(self, *args):
        self.has_unsaved_changes = True

    @debug
    def on_edges_table_contextmenu(self, event):
        column_index = self.tvEdges.columnAt(event.x())
        row_index = self.tvEdges.rowAt(event.y())
        if column_index != -1 and row_index != -1:
            menu = QMenu(self)
            action = QAction(QIcon(":/icons/images/highlight-red.svg"), "Highlight selected edges", self)
            action.triggered.connect(self.highlight_selected_edges)
            menu.addAction(action)
            action = QAction(QIcon(":/icons/images/highlight-yellow.svg"), "Highlight nodes from selected edges", self)
            action.triggered.connect(self.highlight_nodes_from_selected_edges)
            menu.addAction(action)
            menu.popup(QCursor.pos())

    @debug
    def on_query_databases(self, type_='standards'):
        selected_idx = self.nodes_selection()
        if not selected_idx:
            return
        options = workers.QueryDatabasesOptions()
        options.analog_search = (type_ == 'analogs')

        try:
            dialog = ui.QueryDatabasesDialog(self, options=options)
            if dialog.exec_() == QDialog.Accepted:
                options = dialog.getValues()
                worker = self.prepare_query_database_worker(selected_idx, options)
                if worker is not None:
                    self._workers.add(worker)
        except FileNotFoundError:
            QMessageBox.warning(self, None, "No database found. Please download at least one database.")

    @debug
    def on_current_parameters_triggered(self, *args):
        dialog = ui.CurrentParametersDialog(self, options=self.network.options)
        dialog.exec_()

    @debug
    def on_preferences_triggered(self, *args):
        dialog = ui.SettingsDialog(self)
        if dialog.exec_() == QDialog.Accepted:
            style = dialog.getValues()
            self.gvNetwork.scene().setNetworkStyle(style)
            self.gvTSNE.scene().setNetworkStyle(style)

    @debug
    def on_open_user_folder_triggered(self, *args):
        if sys.platform.startswith('win'):
            os.startfile(config.USER_PATH)
        elif sys.platform.startswith('darwin'):
            subprocess.Popen(["open", config.USER_PATH])
        else:
            subprocess.Popen(["xdg-open", config.USER_PATH])

    @debug
    def on_full_screen_triggered(self, *args):
        if not self.isFullScreen():
            self.setWindowFlags(Qt.Window)
            self.showFullScreen()
        else:
            self.setWindowFlags(Qt.Widget)
            self.showNormal()

    @debug
    def on_process_file_triggered(self, *args):
        reply = self.confirm_save_changes()
        if reply == QMessageBox.Cancel:
            return

        dialog = ui.ProcessDataDialog(self, options=self.network.options)
        if dialog.exec_() == QDialog.Accepted:
            self.reset_project()

            process_file, use_metadata, metadata_file, metadata_options, \
                compute_options, tsne_options, network_options = dialog.getValues()
            self.network.options.cosine = compute_options
            self.network.options.tsne = tsne_options
            self.network.options.network = network_options

            worker = self.prepare_read_mgf_worker(process_file, metadata_file, metadata_options)
            if worker is not None:
                self._workers.add(worker)

    @debug
    def on_import_metadata_triggered(self, *args):
        dialog = ui.ImportMetadataDialog(self)
        if dialog.exec_() == QDialog.Accepted:
            metadata_filename, options = dialog.getValues()
            worker = self.prepare_read_metadata_worker(metadata_filename, options)
            if worker is not None:
                self._workers.add(worker)

    @debug
    def on_import_group_mapping_triggered(self, *args):
        dialog = QFileDialog(self)
        dialog.setFileMode(QFileDialog.ExistingFile)
        dialog.setNameFilters(["Text Files (*.txt; *.csv; *.tsv)", "All files (*.*)"])
        if dialog.exec_() == QDialog.Accepted:
            filename = dialog.selectedFiles()[0]
            worker = self.prepare_read_group_mapping_worker(filename)
            if worker is not None:
                self._workers.add(worker)

    @debug
    def on_edit_options_triggered(self, type_):
        if hasattr(self.network, 'scores'):
            if type_ == 'network':
                dialog = ui.EditNetworkOptionsDialog(self, options=self.network.options)
                if dialog.exec_() == QDialog.Accepted:
                    options = dialog.getValues()
                    if options != self.network.options.network:
                        self.network.options.network = options
                        self.network.interactions = None
                        self.has_unsaved_changes = True

                        self.draw(which='network', keep_vertices=True)
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

    @debug
    def on_download_databases_triggered(self, *args):
        dialog = ui.DownloadDatabasesDialog(self, base_path=config.DATABASES_PATH)
        dialog.exec_()

    @debug
    def on_import_user_database_triggered(self, *args):
        dialog = ui.ImportUserDatabaseDialog(self, base_path=config.DATABASES_PATH)
        dialog.exec_()

    @debug
    def on_view_databases_triggered(self, *args):
        path = config.SQL_PATH
        if os.path.exists(path) and os.path.isfile(path) and os.path.getsize(path) > 0:
            dialog = ui.ViewDatabasesDialog(self, base_path=config.DATABASES_PATH)
            dialog.exec_()
        else:
            QMessageBox.information(self, None, "No databases found, please download one or more database first.")

    @debug
    def on_scale_changed(self, type_, scale):
        if type_ == 'network':
            self.gvNetwork.scene().setScale(scale / self.sliderNetworkScale.defaultValue())
        elif type_ == 't-sne':
            self.gvTSNE.scene().setScale(scale / self.sliderNetworkScale.defaultValue())
            self.draw_tsne_line(getattr(self.network.graph, 'tsne_layout', None),
                                getattr(self.network, 'tsne_isolated_nodes', None))

    @debug
    def on_view_details_clicked(self, row: int, selection: dict):
        if selection:
            path = config.SQL_PATH
            if os.path.exists(path) and os.path.isfile(path) and os.path.getsize(path) > 0:
                spectrum = human_readable_data(self.network.spectra[row])
                dialog = ui.ViewStandardsResultsDialog(self, spectrum=spectrum,
                                                       selection=selection, base_path=config.DATABASES_PATH)
                if dialog.exec_() == QDialog.Accepted:
                    current = dialog.getValues()
                    if current is not None:
                        self.network.db_results[row]['current'] = current
                        self.has_unsaved_changes = True
            else:
                QMessageBox.information(self, None, "No databases found, please download one or more database first.")

    @debug
    def confirm_save_changes(self):
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

        return reply

    @debug
    def highlight_selected_nodes(self, *args):
        selected = self.nodes_selection()
        with utils.SignalBlocker(self.gvNetwork.scene(), self.gvTSNE.scene()):
            self.gvNetwork.scene().setNodesSelection(selected)
            self.gvTSNE.scene().setNodesSelection(selected)

    @debug
    def highlight_selected_edges(self, *args):
        selected = self.edges_selection()
        with utils.SignalBlocker(self.gvNetwork.scene(), self.gvTSNE.scene()):
            self.gvNetwork.scene().setEdgesSelection(selected)

    @debug
    def highlight_nodes_from_selected_edges(self, *args):
        selected = self.edges_selection()
        model = self.tvEdges.model().sourceModel()
        sel = set()
        for row in selected:
            source = model.index(row, 0).data() - 1
            dest = model.index(row, 1).data() - 1
            sel.add(source)
            sel.add(dest)

        with utils.SignalBlocker(self.gvNetwork.scene(), self.gvTSNE.scene()):
            self.gvNetwork.scene().setNodesSelection(sel)

    @debug
    def set_nodes_label(self, column_id):
        model = self.tvNodes.model().sourceModel()
        for column in range(model.columnCount()):
            font = model.headerData(column, Qt.Horizontal, role=Qt.FontRole)
            if font is not None and font.overline():
                model.setHeaderData(column, Qt.Horizontal, None, role=Qt.FontRole)

        if column_id is not None:
            font = model.headerData(column_id, Qt.Horizontal, role=Qt.FontRole)
            font = font if font is not None else QFont()
            font.setOverline(True)
            model.setHeaderData(column_id, Qt.Horizontal, font, role=Qt.FontRole)

            self.gvNetwork.scene().setLabelsFromModel(model, column_id, ui.widgets.LabelRole)
            self.gvTSNE.scene().setLabelsFromModel(model, column_id, ui.widgets.LabelRole)
            self.network.columns_mappings['label'] = column_id
        else:
            self.gvNetwork.scene().resetLabels()
            self.gvTSNE.scene().resetLabels()
            try:
                del self.network.columns_mappings['label']
            except KeyError:
                pass

        self.has_unsaved_changes = True

    @debug
    def set_nodes_pie_chart_values(self, column_ids, colors: List[QColor]=()):
        model = self.tvNodes.model().sourceModel()
        if column_ids is not None:
            if len(colors) < len(column_ids):
                QMessageBox.critical(self, None, "There is more columns selected than colors available.")
                return

            for column in range(model.columnCount()):
                model.setHeaderData(column, Qt.Horizontal, None, role=ui.widgets.metadata.ColorMarkRole)

            save_colors = []
            for column, color in zip(column_ids, colors):
                color = QColor(color)
                save_colors.append(color)
                model.setHeaderData(column, Qt.Horizontal, color, role=ui.widgets.metadata.ColorMarkRole)

            for view in (self.gvNetwork, self.gvTSNE):
                scene = view.scene()
                scene.setPieColors(colors)
                scene.setPieChartsFromModel(model, column_ids)
                scene.setPieChartsVisibility(True)

            self.network.columns_mappings['pies'] = (column_ids, save_colors)
        else:
            for column in range(model.columnCount()):
                model.setHeaderData(column, Qt.Horizontal, None, role=ui.widgets.metadata.ColorMarkRole)
            for view in (self.gvNetwork, self.gvTSNE):
                view.scene().resetPieCharts()
            try:
                del self.network.columns_mappings['pies']
            except KeyError:
                pass

        self.has_unsaved_changes = True

    @debug
    def set_nodes_sizes_values(self, column_id, func: Callable=None):
        model = self.tvNodes.model().sourceModel()
        for column in range(model.columnCount()):
            font = model.headerData(column, Qt.Horizontal, role=Qt.FontRole)
            if font is not None and font.underline():
                model.setHeaderData(column, Qt.Horizontal, None, role=Qt.FontRole)

        if column_id is not None:
            font = model.headerData(column_id, Qt.Horizontal, role=Qt.FontRole)
            font = font if font is not None else QFont()
            font.setUnderline(True)
            model.setHeaderData(column_id, Qt.Horizontal, font, role=Qt.FontRole)

            for view in (self.gvNetwork, self.gvTSNE):
                scene = view.scene()
                scene.setNodesRadiiFromModel(model, column_id, Qt.DisplayRole, func)
            self.network.columns_mappings['size'] = (column_id, func)
        else:
            for view in (self.gvNetwork, self.gvTSNE):
                view.scene().resetNodesRadii()
            try:
                del self.network.columns_mappings['size']
            except KeyError:
                pass

        self.has_unsaved_changes = True

    @debug
    def save_settings(self):
        settings = QSettings()

        settings.beginGroup('MainWindow')
        settings.setValue('Geometry', self.saveGeometry())
        settings.setValue('State', self.saveState())
        if self.recent_projects:
            settings.setValue('RecentProjects', self.recent_projects)
        settings.endGroup()

    @debug
    def load_settings(self):
        settings = QSettings()
        settings.beginGroup('MainWindow')
        setting = settings.value('Geometry')
        if setting is not None:
            self.restoreGeometry(setting)
        setting = settings.value('State')
        if setting is not None:
            self.restoreState(setting)
        self.recent_projects = settings.value('RecentProjects', type=list)
        self.update_recent_projects()
        settings.endGroup()

        settings.beginGroup('NetworkView')
        setting = settings.value('style', None)
        style = style_from_css(setting)
        self.gvNetwork.scene().setNetworkStyle(style)
        self.gvTSNE.scene().setNetworkStyle(style)
        settings.endGroup()

    @debug
    def reset_layout(self, *args):
        for w in self.findChildren(QDockWidget):
            self.removeDockWidget(w)
            w.setVisible(True)
            if w.objectName() == "jupyter":
                self.addDockWidget(Qt.TopDockWidgetArea, w)
            else:
                self.addDockWidget(Qt.BottomDockWidgetArea, w)
            w.setFloating(False)

        self.tabifyDockWidget(self.dockNodes, self.dockEdges)
        self.tabifyDockWidget(self.dockEdges, self.dockSpectra)
        self.dockNodes.raise_()

        # Make sure all toolbars are visible
        for w in self.findChildren(QToolBar):
            if w.objectName() != "":
                w.setVisible(True)
                self.addToolBar(w)

        for w in self.findChildren(QSplitter):
            w.refresh()
            w.setSizes(w.sizes())

    @debug
    def draw(self, compute_layouts=True, which='all', keep_vertices=False):
        if which == 'all':
            which = {'network', 't-sne'}
        elif isinstance(which, str):
            which = {which}

        def draw_network():
            isolated_nodes = np.where(np.asarray(self.network.graph.degree()) <= 2)[0]
            if not compute_layouts and self.network.graph.network_layout is not None:
                network_worker = self.prepare_draw_network_worker(layout=self.network.graph.network_layout,
                                                                  isolated_nodes=isolated_nodes)
            else:
                network_worker = self.prepare_draw_network_worker(isolated_nodes=isolated_nodes)

            if 't-sne' in which:
                network_worker.finished.connect(draw_tsne)

            self._workers.add(network_worker)

        def draw_tsne():
            if not compute_layouts and self.network.graph.tsne_layout is not None:
                tsne_worker = self.prepare_draw_tsne_worker(layout=self.network.graph.tsne_layout,
                                                            isolated_nodes=getattr(self.network, 'tsne_isolated_nodes', None))
            else:
                tsne_worker = self.prepare_draw_tsne_worker(isolated_nodes=getattr(self.network, 'tsne_isolated_nodes', None))
            self._workers.add(tsne_worker)

        if 'network' in which:
            if self.network.interactions is None:
                worker = self.prepare_generate_network_worker(keep_vertices)
                worker.finished.connect(draw_network)
                self._workers.add(worker)
            else:
                draw_network()
        elif 't-sne' in which:
            draw_tsne()

        self.update_search_menu()

    @debug
    def apply_layout(self, type_, layout, isolated_nodes=None):
        hide_isolated_nodes = self.actionHideIsolatedNodes.isChecked()

        if type_ == 'network':
            self.gvNetwork.scene().setLayout(layout, isolated_nodes=isolated_nodes if hide_isolated_nodes else None)
            self.network.graph.network_layout = layout
            self.gvNetwork.scene().lock(self.btNetworkLock.isChecked())
        elif type_ == 't-sne':
            self.gvTSNE.scene().setLayout(layout, isolated_nodes=isolated_nodes if hide_isolated_nodes else None)
            self.network.tsne_isolated_nodes = isolated_nodes
            self.gvTSNE.scene().lock(self.btTSNELock.isChecked())
            self.draw_tsne_line(layout, isolated_nodes)

            self.network.graph.tsne_layout = layout

    @debug
    def draw_tsne_line(self, layout, isolated_nodes=None):
        hide_isolated_nodes = self.actionHideIsolatedNodes.isChecked()

        # Remove line separating isolated nodes from others
        line = getattr(self.network.graph, 'tsne_layout_line', None)
        if line is not None and isinstance(line, QGraphicsLineItem):
            self.gvTSNE.scene().removeItem(line)

        # Add a new line if needed
        if not hide_isolated_nodes and isolated_nodes is not None:
            try:
                scale = self.gvTSNE.scene().scale()
                l = layout[isolated_nodes]
                x1 = l.min(axis=0)[0] - 5 * config.RADIUS
                x2 = l.max(axis=0)[0] + 5 * config.RADIUS
                y = l.max(axis=1)[1] - 5 * config.RADIUS
                width = 5 * scale
                self.network.graph.tsne_layout_line = self.gvTSNE.scene().addLine(x1 * scale, y * scale,
                                                                                  x2 * scale, y * scale,
                                                                                  pen=QPen(Qt.gray, width))
            except ValueError:
                pass

    @debug
    def update_columns_mappings(self):
        columns_mappings = getattr(self.network, 'columns_mappings', {})

        id_ = columns_mappings.get('label', None)
        if id_ is not None:
            self.set_nodes_label(id_)

        try:
            ids, colors = columns_mappings.get('pies', (None, None))
        except TypeError:
            pass
        else:
            if ids is not None and colors is not None:
                self.set_nodes_pie_chart_values(ids, colors)

        try:
            id_, func = columns_mappings.get('size', (None, None))
        except TypeError:
            pass
        else:
            if id_ is not None and func is not None:
                 self.set_nodes_sizes_values(id_, func)

    @debug
    def prepare_apply_network_layout_worker(self, layout=None, isolated_nodes=None):
        if layout is None:
            # Compute layout
            def process_finished():
                computed_layout, _ = worker.result()
                if computed_layout is not None:
                    self.apply_layout('network', computed_layout, isolated_nodes)

            worker = workers.NetworkWorker(self.network.graph, self.gvNetwork.scene().nodesRadii())
            worker.finished.connect(process_finished)
        else:
            worker = workers.GenericWorker(self.apply_layout, 'network', layout, isolated_nodes)
        return worker

    @debug
    def prepare_apply_tsne_layout_worker(self, layout=None, isolated_nodes=None):
        if layout is None:
            # Compute layout
            def process_finished():
                computed_layout, isolated_nodes = worker.result()
                if computed_layout is not None:
                    self.apply_layout('t-sne', computed_layout, isolated_nodes)

            worker = workers.TSNEWorker(self.network.scores, self.network.options.tsne)
            worker.finished.connect(process_finished)

            return worker
        else:
            worker = workers.GenericWorker(self.apply_layout, 't-sne', layout, isolated_nodes)
            return worker

    @debug
    def prepare_generate_network_worker(self, keep_vertices=False):
        def interactions_generated():
            nonlocal worker
            interactions, graph = worker.result()
            self.network.interactions = interactions
            self.network.graph = graph

        worker = workers.GenerateNetworkWorker(self.network.scores, self.network.mzs, self.network.graph,
                                               self.network.options.network, keep_vertices=keep_vertices)
        worker.finished.connect(interactions_generated)

        return worker

    @debug
    def prepare_draw_network_worker(self, layout=None, isolated_nodes=None):
        scene = self.gvNetwork.scene()
        scene.removeAllEdges()

        # Add nodes
        nodes = scene.nodes()
        num_nodes = len(nodes)
        if num_nodes == 0:
            colors = self.network.graph.vs['__color'] \
                if '__color' in self.network.graph.vs.attributes() else []

            radii = self.network.graph.vs['__size'] \
                if '__size' in self.network.graph.vs.attributes() else []

            nodes = scene.addNodes(self.network.graph.vs['name'], colors=colors, radii=radii)

        # Add edges
        edges_attr = [(e.index, nodes[e.source], nodes[e.target], e['__width'])
                      for e in self.network.graph.es if not e.is_loop()]
        if edges_attr:
            scene.addEdges(*zip(*edges_attr))

        worker = self.prepare_apply_network_layout_worker(layout, isolated_nodes)
        return worker

    @debug
    def prepare_draw_tsne_worker(self, layout=None, isolated_nodes=None):
        scene = self.gvTSNE.scene()

        # Add nodes
        num_nodes = len(scene.nodes())
        if num_nodes == 0:
            colors = self.network.graph.vs['__color'] \
                if '__color' in self.network.graph.vs.attributes() else []

            radii = self.network.graph.vs['__size'] \
                if '__size' in self.network.graph.vs.attributes() else []

            scene.addNodes(self.network.graph.vs['name'], colors=colors, radii=radii)

        worker = self.prepare_apply_tsne_layout_worker(layout, isolated_nodes)
        return worker

    @debug
    def prepare_compute_scores_worker(self, spectra, use_multiprocessing):
        def error(e):
            if isinstance(e, OSError):
                QMessageBox.warning(self, None, str(e))
            if isinstance(e, MemoryError):
                QMessageBox.critical(self, None, "Not enough memory was available to compute scores matrix.")
            else:
                raise e

        worker = workers.ComputeScoresWorker(spectra, use_multiprocessing, self.network.options.cosine)
        worker.error.connect(error)

        return worker

    @debug
    def prepare_read_mgf_worker(self, mgf_filename, metadata_filename=None,
                                metadata_options=workers.ReadMetadataOptions()):
        worker = workers.ReadDataWorker(mgf_filename, self.network.options.cosine)

        def file_read():
            nonlocal worker
            self.tvNodes.model().sourceModel().beginResetModel()
            self.network.mzs, self.network.spectra = worker.result()
            self.tvNodes.model().sourceModel().endResetModel()
            worker = self.prepare_compute_scores_worker(self.network.mzs, self.network.spectra)
            if worker is not None:
                worker.finished.connect(scores_computed)
                self._workers.add(worker)

        def error(e):
            if isinstance(e, KeyError) and e.args[0] in ("pepmass", "precursormz"):
                QMessageBox.warning(self, None, "File format is incorrect. At least one scan has no parent's "
                                                "m/z defined.")
            elif isinstance(e, NotImplementedError):
                QMessageBox.warning(self, None, "File format is not supported.")
            elif hasattr(e, 'message'):
                QMessageBox.warning(self, None, e.message)
            else:
                QMessageBox.warning(self, None, str(e))

        def scores_computed():
            nonlocal worker
            self.tvEdges.model().sourceModel().beginResetModel()
            self.network.scores = worker.result()
            self.network.interactions = None
            self.tvEdges.model().sourceModel().endResetModel()
            self.draw()
            if metadata_filename is not None:
                worker = self.prepare_read_metadata_worker(metadata_filename, metadata_options)
                if worker is not None:
                    self._workers.add(worker)

        worker.finished.connect(file_read)
        worker.error.connect(error)
        return worker

    @debug
    def prepare_read_metadata_worker(self, filename, options):
        def file_read():
            nonlocal worker
            model = self.tvNodes.model().sourceModel()
            model.beginResetModel()
            self.network.infos = worker.result()  # TODO: Append metadata instead of overriding
            self.network.mappings = {}
            self.has_unsaved_changes = True
            self.set_nodes_pie_chart_values(None)
            self.set_nodes_sizes_values(None)
            self.set_nodes_label(None)
            model.endResetModel()

        def error(e):
            message = str(e).strip("\n")
            QMessageBox.warning(self, None, "Metadata were not imported because the following error occurred:\n"
                                            f"\"{message}\".\n"
                                            "Your metadata file might be corrupted/invalid.")

        worker = workers.ReadMetadataWorker(filename, options)
        worker.finished.connect(file_read)
        worker.error.connect(error)

        return worker

    @debug
    def prepare_save_project_worker(self, fname):
        """Save current project to a file for future access"""

        def process_finished():
            # Save filename and set window title
            self.fname = fname
            self.has_unsaved_changes = False

            # Update list of recent projects
            self.update_recent_projects(fname)

        def error(e):
            if isinstance(e, PermissionError):
                QMessageBox.warning(self, None, str(e))
            else:
                raise e

        worker = workers.SaveProjectWorker(fname, self.network.graph, self.network, self.network.options,
                                           original_fname=self.fname)
        worker.finished.connect(process_finished)
        worker.error.connect(error)

        return worker

    @debug
    def prepare_load_project_worker(self, fname):
        """Load project from a previously saved file"""

        def process_finished():
            self.sliderNetworkScale.resetValue()
            self.sliderTSNEScale.resetValue()

            self.tvNodes.model().sourceModel().beginResetModel()
            self.tvEdges.model().sourceModel().beginResetModel()
            self.network = worker.result()
            self.tvNodes.model().sourceModel().endResetModel()
            self.tvEdges.model().sourceModel().endResetModel()

            # Draw
            self.draw(compute_layouts=False)

            self.update_columns_mappings()

            # Save filename and set window title
            self.fname = fname
            self.has_unsaved_changes = False

            # Update list of recent projects
            self.update_recent_projects(fname)

        def error(e):
            if isinstance(e, FileNotFoundError):
                QMessageBox.warning(self, None, f"File '{fname}' not found.")
                self.update_recent_projects(remove_fname=fname)
            elif isinstance(e, errors.UnsupportedVersionError):
                QMessageBox.warning(self, None, str(e))
            elif isinstance(e, KeyError):
                QMessageBox.critical(self, None, str(e))
            elif isinstance(e, zipfile.BadZipFile):
                QMessageBox.warning(self, None,
                                    f"Selected file is not a valid {QCoreApplication.applicationName()} file")
            else:
                raise e

        worker = workers.LoadProjectWorker(fname)
        worker.finished.connect(process_finished)
        worker.error.connect(error)

        return worker

    @debug
    def prepare_query_database_worker(self, indices, options):
        if (getattr(self.network, 'mzs', None) is None or getattr(self.network, 'spectra', None) is None
                or not os.path.exists(config.SQL_PATH)):
            return
        mzs = [self.network.mzs[index] for index in indices]
        spectra = [self.network.spectra[index] for index in indices]
        worker = workers.QueryDatabasesWorker(indices, mzs, spectra, options)

        def query_finished():
            nonlocal worker
            result = worker.result()
            if result:
                self.tvNodes.model().sourceModel().beginResetModel()
                type_ = "analogs" if options.analog_search else "standards"
                # Update db_results with these new results
                num_results = 0
                for row in result:
                    if result[row][type_]:
                        num_results += len(result[row][type_])
                        if row in self.network.db_results:
                            self.network.db_results[row][type_] = result[row][type_]
                        else:
                            self.network.db_results[row] = {type_: result[row][type_]}
                    elif row in self.network.db_results and type_ in self.network.db_results[row]:
                        del self.network.db_results[row][type_]
                self.has_unsaved_changes = True
                self.tvNodes.model().sourceModel().endResetModel()

                # Show column if db_results is not empty
                was_hidden = self.tvNodes.isColumnHidden(1)
                self.tvNodes.setColumnBlinking(1, True)
                self.tvNodes.setColumnHidden(1, self.network.db_results is None or len(self.network.db_results) == 0)
                if was_hidden:
                    fm = QFontMetrics(self.tvNodes.font())
                    width = fm.width(self.tvNodes.model().headerData(1, Qt.Horizontal)) + 36
                    self.tvNodes.setColumnWidth(1, width)

                QMessageBox.information(self, None, f'{num_results} results found.')
            else:
                QMessageBox.warning(self, None, 'No results found.')

        def error(e):
            if isinstance(e, sqlalchemy.exc.OperationalError):
                QMessageBox.warning(self, None, 'You have to download at least one database before trying to query it.')

        worker.started.connect(lambda: self.tvNodes.setColumnBlinking(1, False))
        worker.finished.connect(query_finished)
        worker.error.connect(error)
        return worker

    @debug
    def prepare_read_group_mapping_worker(self, filename):
        worker = workers.ReadGroupMappingWorker(filename)

        def finished():
            nonlocal worker
            result = worker.result()
            self.tvNodes.model().sourceModel().beginResetModel()
            self.network.mappings = result
            self.has_unsaved_changes = True
            self.tvNodes.model().sourceModel().endResetModel()

        def error(e):
            if isinstance(e, ValueError):
                QMessageBox.warning(self, None, "Group mapping file format was not recognized.")
            elif isinstance(e, FileNotFoundError):
                QMessageBox.warning(self, None, "Group mapping file does not exist.")
            else:
                QMessageBox.warning(self, None,
                                    f"Group mapping was not loaded because the following error occurred: {str(e)}")

        worker.finished.connect(finished)
        worker.error.connect(error)
        return worker

    @debug
    def prepare_export_metadata_worker(self, filename, model, sep):
        worker = workers.ExportMetadataWorker(filename, model, sep)

        def finished():
            QMessageBox.information(self, None, f"Metadata were successfully exported to \"{filename}\".")

        def error(e):
            QMessageBox.warning(self, None,
                                f"Metadata were not exported because the following error occurred: {str(e)})")

        worker.finished.connect(finished)
        worker.error.connect(error)
        return worker

    @debug
    def prepare_export_db_results_worker(self, filename, model, fmt):
        worker = workers.ExportDbResultsWorker(filename, model, fmt)

        def finished():
            QMessageBox.information(self, None, f"Database results were successfully exported to \"{filename}\".")

        def error(e):
            QMessageBox.warning(self, None,
                                f"Database results were not exported because the following error occurred: {str(e)})")

        worker.finished.connect(finished)
        worker.error.connect(error)
        return worker
