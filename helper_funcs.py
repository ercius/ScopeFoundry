from PySide import QtCore, QtGui, QtUiTools
from collections import OrderedDict
import os

class OrderedAttrDict(object):

    def __init__(self):
        self._odict = OrderedDict()
        
    def add(self, name, obj):
        self._odict[name] = obj
        self.__dict__[name] = obj
        return obj
    
    
    def keys(self):
        return self._odict.keys()
    def values(self):
        return self._odict.values()
    def items(self):
        return self._odict.items()
    
    def __len__(self):
        return len(self._odict)
    
    def __getitem__(self, key):
        return self._odict[key]
    
    def __contains__(self, k):
        return self._odict.__contains__(k)

def sibling_path(a, b):
    return os.path.join(os.path.dirname(a), b)


def load_qt_ui_file(ui_filename):
    ui_loader = QtUiTools.QUiLoader()
    ui_file = QtCore.QFile(ui_filename)
    ui_file.open(QtCore.QFile.ReadOnly)
    ui = ui_loader.load(ui_file)
    ui_file.close()
    return ui

def confirm_on_close(widget, title="Close ScopeFoundry?", message="Do you wish to shut down ScopeFoundry?", func_on_close=None):
    widget.closeEventEater = CloseEventEater(title, message, func_on_close)
    widget.installEventFilter(widget.closeEventEater)
    
class CloseEventEater(QtCore.QObject):
    
    def __init__(self, title="Close ScopeFoundry?", message="Do you wish to shut down ScopeFoundry?", func_on_close=None):
        QtCore.QObject.__init__(self)
        self.title = title
        self.message = message
        self.func_on_close = func_on_close
    
    def eventFilter(self, obj, event):
        if event.type() == QtCore.QEvent.Close:
            # eat close event
            print "close"
            reply = QtGui.QMessageBox.question(None, 
                                               self.title, 
                                               self.message,
                                               QtGui.QMessageBox.Yes, QtGui.QMessageBox.No)
            if reply == QtGui.QMessageBox.Yes:
                print "closing"
                if self.func_on_close:
                    self.func_on_close()
                QtGui.QApplication.quit()
                event.accept()
            else:
                event.ignore()
            return True
        else:
            # standard event processing            
            return QtCore.QObject.eventFilter(self,obj, event)
        
def replace_widget_in_layout(old_widget, new_widget, retain_font=True, retain_sizePolicy=True, retain_size=True):
    """
    Replace a widget with a new widget instance in an existing layout.
    
    returns new_widget
    
    Useful for replacing placeholder widgets created with QtCreator 
    with custom widgets
    Note: currently works for widgets in  QGridLayouts only
    
    inspiration from:
    -- http://stackoverflow.com/questions/4625102/how-to-replace-a-widget-with-another-using-qt
    -- http://stackoverflow.com/questions/24189202/how-to-get-the-row-column-location-of-a-widget-in-a-qgridlayout
    """
    
    # find position of old_widget
    layout = old_widget.parentWidget().layout()
    index = layout.indexOf(old_widget)
    row, column, rowSpan, colSpan = layout.getItemPosition(index)
    

    # transfer retained attributes of old_widget to  new_widget
    if retain_font:
        new_widget.setFont(old_widget.font())
    if retain_sizePolicy:
        new_widget.setSizePolicy(old_widget.sizePolicy())
    if retain_size:
        new_widget.setMinimumSize(old_widget.minimumSize())
        new_widget.setMaximumSize(old_widget.maximumSize())
    
    # remove old widget
    layout.removeWidget(old_widget)
    old_widget.close()


    # add new widget
    layout.addWidget(new_widget, row, column, rowSpan, colSpan)
    layout.update()
    
    
    
    return new_widget