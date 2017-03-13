###############################################################################
#   volumina: volume slicing and editing library
#
#       Copyright (C) 2011-2014, the ilastik developers
#                                <team@ilastik.org>
#
# This program is free software; you can redistribute it and/or
# modify it under the terms of the Lesser GNU General Public License
# as published by the Free Software Foundation; either version 2.1
# of the License, or (at your option) any later version.
#
# This program is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE. See the
# GNU Lesser General Public License for more details.
#
# See the files LICENSE.lgpl2 and LICENSE.lgpl3 for full text of the
# GNU Lesser General Public License version 2.1 and 3 respectively.
# This information is also available on the ilastik web site at:
#		   http://ilastik.org/license/
###############################################################################
import os
import collections
from functools import partial

import numpy

from PyQt4 import uic
from PyQt4.QtCore import Qt, QObject, QEvent
from PyQt4.QtGui import QDialog, QValidator, QDialogButtonBox

try:
    from lazyflow.graph import Operator, InputSlot, OutputSlot
    _has_lazyflow = True
except:
    _has_lazyflow = False

#**************************************************************************
# Model operator interface ABC
#**************************************************************************
if _has_lazyflow:
    class ExportOperatorABC(Operator):
        """
        The export dialog is designed to work with any operator that satisfies this ABC interface.
        """
        # Operator.__metaclass__ already inherits ABCMeta
        # __metaclass__ = ABCMeta
        
        # The original image, which we'll transform and export.
        Input = InputSlot()
    
        # See OpFormattedDataExport for details
        TransactionSlot = InputSlot()
    
        # Subregion params
        RegionStart = InputSlot(optional=True)
        RegionStop = InputSlot(optional=True)
    
        # Normalization params    
        InputMin = InputSlot(optional=True)
        InputMax = InputSlot(optional=True)
        ExportMin = InputSlot(optional=True)
        ExportMax = InputSlot(optional=True)
    
        ExportDtype = InputSlot(optional=True)
        OutputAxisOrder = InputSlot(optional=True)
        
        # File settings
        OutputFilenameFormat = InputSlot(value='RESULTS_{roi}') # A format string allowing {roi}, {x_start}, {x_stop}, etc.
        OutputInternalPath = InputSlot(value='exported_data')
        OutputFormat = InputSlot(value='hdf5')
    
        ConvertedImage = OutputSlot() # Preprocessed image, BEFORE axis reordering
        ImageToExport = OutputSlot() # Preview of the pre-processed image that will be exported
        ExportPath = OutputSlot() # Location of the saved file after export is complete.
        FormatSelectionErrorMsg = OutputSlot()
    
        @classmethod
        def __subclasshook__(cls, C):
            # Must have all the required input and output slots.
            if cls is ExportOperatorABC:
                for slot in cls.inputSlots:
                    if not hasattr(C, slot.name) or not isinstance(getattr(C, slot.name), InputSlot):
                        return False
                for slot in cls.outputSlots:
                    if not hasattr(C, slot.name) or not isinstance(getattr(C, slot.name), OutputSlot):
                        return False
                return True
            return NotImplemented

#**************************************************************************
# DataExportOptionsDlg
#**************************************************************************
class PluginExportOptionsDlg(QDialog):
    
    def __init__(self, parent, opDataExport):
        """
        Constructor.
        
        :param parent: The parent widget
        :param opDataExport: The operator to configure.  The operator is manipulated LIVE, so supply a 
                             temporary operator that can be discarded in case the user clicked 'cancel'.
                             If the user clicks 'OK', then copy the slot settings from the temporary op to your real one.
        """
        global _has_lazyflow
        assert _has_lazyflow, "This widget requires lazyflow."
        super( PluginExportOptionsDlg, self ).__init__(parent)
        uic.loadUi( os.path.splitext(__file__)[0] + '.ui', self )

        self._opDataExport = opDataExport
        assert isinstance( opDataExport, ExportOperatorABC ), \
            "Cannot use {} as an export operator.  "\
            "It doesn't match the required interface".format( type(opDataExport) )

        self._okay_conditions = {}

        # Connect the 'transaction slot'.
        # All slot changes will occur immediately
        opDataExport.TransactionSlot.setValue(True)

        # Init child widgets
        self._initMetaInfoWidgets()
        self._initFileOptionsWidget()

        # See self.eventFilter()
        self.installEventFilter(self)

    def eventFilter(self, watched, event):
        # Ignore 'enter' keypress events, since the user may just be entering settings.
        # The user must manually click the 'OK' button to close the dialog.
        if watched == self and \
           event.type() == QEvent.KeyPress and \
           ( event.key() == Qt.Key_Enter or event.key() == Qt.Key_Return):
            return True
        return False

    def _set_okay_condition(self, name, status):
        self._okay_conditions[name] = status
        all_okay = all( self._okay_conditions.values() )
        self.buttonBox.button(QDialogButtonBox.Ok).setEnabled( all_okay )

    #**************************************************************************
    # Input/Output Meta-info (display only)
    #**************************************************************************
    def _initMetaInfoWidgets(self):
        ## Input/output meta-info display widgets
        opDataExport = self._opDataExport
        self.outputMetaInfoWidget.initSlot( opDataExport.ImageToExport )

    #**************************************************************************
    # File format and options
    #**************************************************************************
    def _initFileOptionsWidget(self):
        opDataExport = self._opDataExport
        # blockwiseHdf5OptionsWidget = SingleFileExportOptionsWidget( self, "json", "Blockwise Volume description (*.json)" )
        # blockwiseHdf5OptionsWidget.initSlot( opDataExport.OutputFilenameFormat )
        # self._format_option_editors['blockwise hdf5'] = blockwiseHdf5OptionsWidget
        self.exportFileOptionsWidget.initSlot( opDataExport.OutputFilenameFormat, '' )

        # def set_okay_from_format_error(error_msg):
        #     self._set_okay_condition('file format', error_msg == "")
        # self.exportFileOptionsWidget.formatValidityChange.connect( set_okay_from_format_error )
        # self.exportFileOptionsWidget.pathValidityChange.connect( partial(self._set_okay_condition, 'file path') )

        # self.exportFileOptionsWidget.initExportOp( opDataExport )
        # def set_okay_from_format_error(error_msg):
        #     self._set_okay_condition('file format', error_msg == "")
        # self.exportFileOptionsWidget.formatValidityChange.connect( set_okay_from_format_error )
        # self.exportFileOptionsWidget.pathValidityChange.connect( partial(self._set_okay_condition, 'file path') )
        
#**************************************************************************
# Helper functions
#**************************************************************************
def default_drange(dtype):
    if numpy.issubdtype(dtype, numpy.integer):
        return dtype_limits(dtype)
    if numpy.issubdtype(dtype, numpy.floating):
        return (0.0, 1.0)
    raise RuntimeError( "Unknown dtype: {}".format( dtype ) )

def dtype_limits(dtype):
    if numpy.issubdtype(dtype, numpy.integer):
        return (numpy.iinfo(dtype).min, numpy.iinfo(dtype).max)
    if numpy.issubdtype(dtype, numpy.floating):
        return (numpy.finfo(dtype).min, numpy.finfo(dtype).max)
    raise RuntimeError( "Unknown dtype: {}".format( dtype ) )

#**************************************************************************
# Quick debug
#**************************************************************************
if __name__ == "__main__":
    import vigra
    from PyQt4.QtGui import QApplication
    from lazyflow.graph import Graph
    from lazyflow.operators.ioOperators import OpFormattedDataExport

    data = numpy.zeros( (10,20,30,3), dtype=numpy.float32 )
    data = vigra.taggedView(data, 'xyzc')

    op = OpFormattedDataExport( graph=Graph() )
    op.Input.setValue( data )
    op.TransactionSlot.setValue(True)

    app = QApplication([])
    w = DataExportOptionsDlg(None, op)
    w.show()
    
    app.exec_()