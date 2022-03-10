# -*- coding: utf-8 -*-

# Form implementation generated from reading ui file 'E:\git\metgem\metgem_app\ui\widgets\cosine_options_widget.ui',
# licensing of 'E:\git\metgem\metgem_app\ui\widgets\cosine_options_widget.ui' applies.
#
# Created: Sat Mar  5 14:43:01 2022
#      by: pyside2-uic  running on PySide2 5.13.2
#
# WARNING! All changes made in this file will be lost!

from PySide2 import QtCore, QtGui, QtWidgets

class Ui_gbCosineOptions(object):
    def setupUi(self, gbCosineOptions):
        gbCosineOptions.setObjectName("gbCosineOptions")
        gbCosineOptions.resize(376, 219)
        self.gridLayout = QtWidgets.QGridLayout(gbCosineOptions)
        self.gridLayout.setObjectName("gridLayout")
        self.spinMinMatchedPeaks = QtWidgets.QSpinBox(gbCosineOptions)
        self.spinMinMatchedPeaks.setEnabled(True)
        self.spinMinMatchedPeaks.setMaximum(100)
        self.spinMinMatchedPeaks.setProperty("value", 4)
        self.spinMinMatchedPeaks.setObjectName("spinMinMatchedPeaks")
        self.gridLayout.addWidget(self.spinMinMatchedPeaks, 2, 1, 1, 1)
        self.label_6 = QtWidgets.QLabel(gbCosineOptions)
        self.label_6.setObjectName("label_6")
        self.gridLayout.addWidget(self.label_6, 2, 0, 1, 1)
        self.label_3 = QtWidgets.QLabel(gbCosineOptions)
        font = QtGui.QFont()
        font.setItalic(False)
        self.label_3.setFont(font)
        self.label_3.setObjectName("label_3")
        self.gridLayout.addWidget(self.label_3, 1, 0, 1, 1)
        self.spinMZTolerance = QtWidgets.QDoubleSpinBox(gbCosineOptions)
        self.spinMZTolerance.setEnabled(True)
        self.spinMZTolerance.setPrefix("")
        self.spinMZTolerance.setSuffix("")
        self.spinMZTolerance.setMaximum(100.0)
        self.spinMZTolerance.setSingleStep(0.01)
        self.spinMZTolerance.setProperty("value", 0.02)
        self.spinMZTolerance.setObjectName("spinMZTolerance")
        self.gridLayout.addWidget(self.spinMZTolerance, 1, 1, 1, 1)
        self.gbFiltering = QtWidgets.QGroupBox(gbCosineOptions)
        self.gbFiltering.setCheckable(True)
        self.gbFiltering.setObjectName("gbFiltering")
        self.verticalLayout = QtWidgets.QVBoxLayout(self.gbFiltering)
        self.verticalLayout.setObjectName("verticalLayout")
        self.horizontalLayout_3 = QtWidgets.QHBoxLayout()
        self.horizontalLayout_3.setObjectName("horizontalLayout_3")
        self.chkUseParentFiltering = QtWidgets.QCheckBox(self.gbFiltering)
        self.chkUseParentFiltering.setChecked(True)
        self.chkUseParentFiltering.setObjectName("chkUseParentFiltering")
        self.horizontalLayout_3.addWidget(self.chkUseParentFiltering)
        self.spinParentFilterTolerance = QtWidgets.QSpinBox(self.gbFiltering)
        self.spinParentFilterTolerance.setEnabled(True)
        self.spinParentFilterTolerance.setPrefix("")
        self.spinParentFilterTolerance.setMaximum(100)
        self.spinParentFilterTolerance.setProperty("value", 17)
        self.spinParentFilterTolerance.setObjectName("spinParentFilterTolerance")
        self.horizontalLayout_3.addWidget(self.spinParentFilterTolerance)
        self.lblParentFiltering = QtWidgets.QLabel(self.gbFiltering)
        self.lblParentFiltering.setObjectName("lblParentFiltering")
        self.horizontalLayout_3.addWidget(self.lblParentFiltering)
        spacerItem = QtWidgets.QSpacerItem(40, 20, QtWidgets.QSizePolicy.Expanding, QtWidgets.QSizePolicy.Minimum)
        self.horizontalLayout_3.addItem(spacerItem)
        self.verticalLayout.addLayout(self.horizontalLayout_3)
        self.horizontalLayout = QtWidgets.QHBoxLayout()
        self.horizontalLayout.setObjectName("horizontalLayout")
        self.chkUseMinIntensityFiltering = QtWidgets.QCheckBox(self.gbFiltering)
        self.chkUseMinIntensityFiltering.setChecked(False)
        self.chkUseMinIntensityFiltering.setObjectName("chkUseMinIntensityFiltering")
        self.horizontalLayout.addWidget(self.chkUseMinIntensityFiltering)
        self.spinMinIntensity = QtWidgets.QSpinBox(self.gbFiltering)
        self.spinMinIntensity.setEnabled(False)
        self.spinMinIntensity.setMaximum(100)
        self.spinMinIntensity.setObjectName("spinMinIntensity")
        self.horizontalLayout.addWidget(self.spinMinIntensity)
        self.lblMinIntensityFiltering = QtWidgets.QLabel(self.gbFiltering)
        self.lblMinIntensityFiltering.setObjectName("lblMinIntensityFiltering")
        self.horizontalLayout.addWidget(self.lblMinIntensityFiltering)
        spacerItem1 = QtWidgets.QSpacerItem(40, 20, QtWidgets.QSizePolicy.Expanding, QtWidgets.QSizePolicy.Minimum)
        self.horizontalLayout.addItem(spacerItem1)
        self.verticalLayout.addLayout(self.horizontalLayout)
        self.horizontalLayout_2 = QtWidgets.QHBoxLayout()
        self.horizontalLayout_2.setObjectName("horizontalLayout_2")
        self.chkUseWindowRankFiltering = QtWidgets.QCheckBox(self.gbFiltering)
        self.chkUseWindowRankFiltering.setChecked(True)
        self.chkUseWindowRankFiltering.setObjectName("chkUseWindowRankFiltering")
        self.horizontalLayout_2.addWidget(self.chkUseWindowRankFiltering)
        self.spinMinMatchedPeaksSearch = QtWidgets.QSpinBox(self.gbFiltering)
        self.spinMinMatchedPeaksSearch.setMinimum(1)
        self.spinMinMatchedPeaksSearch.setMaximum(100)
        self.spinMinMatchedPeaksSearch.setProperty("value", 6)
        self.spinMinMatchedPeaksSearch.setObjectName("spinMinMatchedPeaksSearch")
        self.horizontalLayout_2.addWidget(self.spinMinMatchedPeaksSearch)
        self.lblWindowRankFiltering1 = QtWidgets.QLabel(self.gbFiltering)
        self.lblWindowRankFiltering1.setObjectName("lblWindowRankFiltering1")
        self.horizontalLayout_2.addWidget(self.lblWindowRankFiltering1)
        self.spinMatchedPeaksWindow = QtWidgets.QSpinBox(self.gbFiltering)
        self.spinMatchedPeaksWindow.setMinimum(1)
        self.spinMatchedPeaksWindow.setMaximum(500)
        self.spinMatchedPeaksWindow.setSingleStep(50)
        self.spinMatchedPeaksWindow.setProperty("value", 50)
        self.spinMatchedPeaksWindow.setObjectName("spinMatchedPeaksWindow")
        self.horizontalLayout_2.addWidget(self.spinMatchedPeaksWindow)
        self.lblWindowRankFiltering2 = QtWidgets.QLabel(self.gbFiltering)
        self.lblWindowRankFiltering2.setObjectName("lblWindowRankFiltering2")
        self.horizontalLayout_2.addWidget(self.lblWindowRankFiltering2)
        spacerItem2 = QtWidgets.QSpacerItem(40, 20, QtWidgets.QSizePolicy.Expanding, QtWidgets.QSizePolicy.Minimum)
        self.horizontalLayout_2.addItem(spacerItem2)
        self.verticalLayout.addLayout(self.horizontalLayout_2)
        self.gridLayout.addWidget(self.gbFiltering, 6, 0, 1, 3)
        spacerItem3 = QtWidgets.QSpacerItem(40, 20, QtWidgets.QSizePolicy.Expanding, QtWidgets.QSizePolicy.Minimum)
        self.gridLayout.addItem(spacerItem3, 1, 2, 2, 1)
        self.chkMS1Data = QtWidgets.QCheckBox(gbCosineOptions)
        self.chkMS1Data.setObjectName("chkMS1Data")
        self.gridLayout.addWidget(self.chkMS1Data, 0, 0, 1, 1)

        self.retranslateUi(gbCosineOptions)
        QtCore.QMetaObject.connectSlotsByName(gbCosineOptions)

    def retranslateUi(self, gbCosineOptions):
        gbCosineOptions.setTitle(QtWidgets.QApplication.translate("gbCosineOptions", "Cosine Score Computing", None, -1))
        self.label_6.setText(QtWidgets.QApplication.translate("gbCosineOptions", "Minimum Matched Peaks", None, -1))
        self.label_3.setText(QtWidgets.QApplication.translate("gbCosineOptions", "<i>m/z</i> Tolerance", None, -1))
        self.gbFiltering.setTitle(QtWidgets.QApplication.translate("gbCosineOptions", "Filtering", None, -1))
        self.chkUseParentFiltering.setText(QtWidgets.QApplication.translate("gbCosineOptions", "Keep peaks outside of the ±", None, -1))
        self.spinParentFilterTolerance.setSuffix(QtWidgets.QApplication.translate("gbCosineOptions", " Th", None, -1))
        self.lblParentFiltering.setText(QtWidgets.QApplication.translate("gbCosineOptions", "window", None, -1))
        self.chkUseMinIntensityFiltering.setText(QtWidgets.QApplication.translate("gbCosineOptions", "Keep peaks above", None, -1))
        self.spinMinIntensity.setSuffix(QtWidgets.QApplication.translate("gbCosineOptions", "%", None, -1))
        self.lblMinIntensityFiltering.setText(QtWidgets.QApplication.translate("gbCosineOptions", "of maximum", None, -1))
        self.chkUseWindowRankFiltering.setText(QtWidgets.QApplication.translate("gbCosineOptions", "Keep each peak in top", None, -1))
        self.lblWindowRankFiltering1.setText(QtWidgets.QApplication.translate("gbCosineOptions", "in the ±", None, -1))
        self.spinMatchedPeaksWindow.setSuffix(QtWidgets.QApplication.translate("gbCosineOptions", " Th", None, -1))
        self.lblWindowRankFiltering2.setText(QtWidgets.QApplication.translate("gbCosineOptions", "window", None, -1))
        self.chkMS1Data.setText(QtWidgets.QApplication.translate("gbCosineOptions", "Treat as &MS1 Data", None, -1))

