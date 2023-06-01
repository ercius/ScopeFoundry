from __future__ import division, print_function, absolute_import

from pathlib import Path
import functools

from ScopeFoundry import BaseApp
from ScopeFoundry.helper_funcs import load_qt_ui_file, sibling_path,\
    load_qt_ui_from_pkg
from ScopeFoundry.widgets import RegionSlicer
from collections import OrderedDict
#import os
from qtpy import QtCore, QtWidgets, QtGui
import pyqtgraph as pg
import pyqtgraph.dockarea as dockarea
import numpy as np
from ScopeFoundry.logged_quantity import LQCollection
from scipy.stats import spearmanr
import argparse
import time
import h5py
from datetime import datetime

import imageio.v3 as iio
import ncempy

class DataBrowser(BaseApp):
    
    name = "DataBrowser"
    
    def __init__(self, argv):
        BaseApp.__init__(self, argv)
        self.setup()
        parser = argparse.ArgumentParser()
        for lq in self.settings.as_list():
            parser.add_argument("--" + lq.name)
        args = parser.parse_args()
        for lq in self.settings.as_list():
            if lq.name in args:
                val = getattr(args,lq.name)
                if val is not None:
                    lq.update_value(val)
        
        
    def setup(self):

        #self.ui = load_qt_ui_file(sibling_path(__file__, "data_browser.ui"))
        self.ui = load_qt_ui_from_pkg('ScopeFoundry', 'data_browser.ui')
        self.ui.show()
        self.ui.raise_()
        
        self.ui.setWindowTitle("ScopeFoundry: NCEM Data Browser")
        self.ui.setWindowIcon(QtGui.QIcon('scopefoundry_logo2C_1024.png'))
        
        self.views = OrderedDict()        
        self.current_view = None        

        self.settings.New('data_filename', dtype='file')
        self.settings.New('browse_dir', dtype='file', is_dir=True, initial='/')
        self.settings.New('file_filter', dtype=str, initial='*.*,')
        
        self.settings.data_filename.add_listener(self.on_change_data_filename)

        self.settings.New('auto_select_view',dtype=bool, initial=False)

        self.settings.New('view_name', dtype=str, initial='0', choices=('0',))
        
        # UI Connections
        self.settings.data_filename.connect_to_browse_widgets(self.ui.data_filename_lineEdit, 
                                                              self.ui.data_filename_browse_pushButton)
        self.settings.browse_dir.connect_to_browse_widgets(self.ui.browse_dir_lineEdit, 
                                                              self.ui.browse_dir_browse_pushButton)
        self.settings.view_name.connect_bidir_to_widget(self.ui.view_name_comboBox)
        self.settings.file_filter.connect_bidir_to_widget(self.ui.file_filter_lineEdit)
        
        # file system tree
        self.fs_model = QtWidgets.QFileSystemModel()
        self.fs_model.setRootPath(QtCore.QDir.currentPath())
        self.ui.treeView.setModel(self.fs_model)
        self.ui.treeView.setIconSize(QtCore.QSize(16,16))
        self.ui.treeView.setSortingEnabled(True)

        self.tree_selectionModel = self.ui.treeView.selectionModel()
        self.tree_selectionModel.selectionChanged.connect(self.on_treeview_selection_change)

        self.settings.browse_dir.add_listener(self.on_change_browse_dir)
        self.settings['browse_dir'] = Path.home()

        # set views
        self.load_view(ncemView(self))
        self.load_view(imageioView(self))
        self.load_view(MetadataView(self))

        self.settings.view_name.add_listener(self.on_change_view_name)
        self.settings['view_name'] = "ncem_view"
        
        self.settings.file_filter.add_listener(self.on_change_file_filter)

        self.ui.console_pushButton.clicked.connect(self.console_widget.show)
        self.ui.log_pushButton.clicked.connect(self.logging_widget.show)
        self.ui.show()

    def load_view(self, new_view):
        print("loading view", repr(new_view.name))
        
        #instantiate view
        #new_view = ViewClass(self)
        
        self.log.debug('load_view called {}'.format(new_view))
        # add to views dict
        self.views[new_view.name] = new_view
        
        self.ui.dataview_groupBox.layout().addWidget(new_view.ui)
        new_view.ui.hide()
        
        # update choices for view_name
        self.settings.view_name.change_choice_list(list(self.views.keys()))
        self.log.debug('load_view done {}'.format(new_view))
        return new_view

    def on_change_data_filename(self):
        fname = Path(self.settings['data_filename'])
        if fname == "0":
            print("initial file 0")
            return
        else:
            print("file", fname)
        if not self.settings['auto_select_view']:
            self.current_view.on_change_data_filename(fname)
        else:
            view_name = self.auto_select_view(fname)
            if self.current_view is None or view_name != self.current_view.name:
                # update view (automatically calls on_change_data_filename)
                self.settings['view_name'] = view_name
            else:
                # force update
                if fname.is_file():
                    self.current_view.on_change_data_filename(fname)

    @QtCore.Slot()
    def on_change_browse_dir(self):
        self.log.debug("on_change_browse_dir")
        self.ui.treeView.setRootIndex(self.fs_model.index(self.settings['browse_dir']))
        self.fs_model.setRootPath(self.settings['browse_dir'])

    
    def on_change_file_filter(self):
        self.log.debug("on_change_file_filter")
        filter_str = self.settings['file_filter']
        if filter_str == "":
            filter_str = "*"
            self.settings['file_filter'] = "*"
        filter_str_list = [x.strip() for x in filter_str.split(',')]
        self.log.debug(filter_str_list)
        self.fs_model.setNameFilters(filter_str_list)
                    
    def on_change_view_name(self):
        #print('on_change_view_name')
        previous_view = self.current_view
        
        self.current_view = self.views[self.settings['view_name']]
    
        # hide current view 
        # (handle the initial case where previous_view is None )
        if previous_view:
            previous_view.ui.hide() 
        else:
            self.ui.dataview_placeholder.hide()
        
        # show new view
        self.current_view.ui.show()
        
        # set datafile for new (current) view
        fname = Path(self.settings['data_filename'])
        if  fname.is_file():
            self.current_view.on_change_data_filename(self.settings['data_filename'])

    def on_treeview_selection_change(self, sel, desel):
        fname = self.fs_model.filePath(self.tree_selectionModel.currentIndex())
        self.settings['data_filename'] = Path(fname)
#        print( 'on_treeview_selection_change' , fname, sel, desel)

    def auto_select_view(self, fname):
        """return the name of the last supported view for the given fname"""
        for view_name, view in list(self.views.items())[::-1]:
            if view.is_file_supported(fname):
                return view_name
        # return default file_info view if no others work
        return 'ncem_view'
        

class DataBrowserView(QtCore.QObject):
    """ Abstract class for DataBrowser Views"""
    
    def __init__(self, databrowser):
        QtCore.QObject.__init__(self)
        self.databrowser =  databrowser
        self.settings = LQCollection()
        self.setup()
        
    def setup(self):
        pass
        # create view with no data file

    def on_change_data_filename(self, fname=None):
        pass
        # load data file
        
        # update display
        
    def is_file_supported(self, fname):
        """ returns whether view can handle file, should return False early to avoid
         too much computation when selecting a file
         """
        return False

class imageioView(DataBrowserView):

    # This name is used in the GUI for the DataBrowser
    name = 'imageio_imread_view'
    
    def setup(self):
        # create the GUI and viewer settings, runs once at program start up
        # self.ui should be a QWidget of some sort, here we use a pyqtgraph ImageView
        self.ui = self.imview = pg.ImageView()

    def is_file_supported(self, fname):
    	 # Tells the DataBrowser whether this plug-in would likely be able
    	 # to read the given file name
    	 # here we are using the file extension to make a guess
        ext = fname.suffix
        return ext.lower() in ['.png', '.tif', '.tiff', '.jpg']

    def on_change_data_filename(self, fname):
        #  A new file has been selected by the user, load and display it
        try:
            self.data = iio.imread(fname)
            self.imview.setImage(self.data.swapaxes(0, 1))
        except Exception as err:
        	# When a failure to load occurs, zero out image
        	# and show error message
            self.imview.setImage(np.zeros((10,10)))
            self.databrowser.ui.statusbar.showMessage(
            	"failed to load %s:\n%s" %(fname, err))
            raise(err)

class ncemView(DataBrowserView):
    """ Data browser for common NCEM file types
    
    """

    # This name is used in the GUI for the DataBrowser
    name = 'ncem_view'
    
    def setup(self):
        """ create the GUI and viewer settings, runs once at program start up
            self.ui should be a QWidget of some sort, here we use a pyqtgraph ImageView
        """
        self.ui = self.imview = pg.ImageView()

    def is_file_supported(self, fname):
        """ Tells the DataBrowser whether this plug-in would likely be able
         to read the given file name
         here we are using the file extension to make a guess
        """
        ext = fname.suffix
        return ext.lower() in ['.dm3', '.dm4', '.mrc', '.ali', '.rec', '.emd']

    def on_change_data_filename(self, fname):
        """  A new file has been selected by the user, load and display it
        """
        try:
            self.data = np.squeeze(ncempy.read(fname)['data'])
            if self.data.ndim == 4:
                print(f'Warning: Reducing {self.data.ndim}-D data to 3-D.')
                self.data = self.data[0,:,:,:]
            self.imview.setImage(self.data)
        except Exception as err:
        	# When a failure to load occurs, zero out image
        	# and show error message
            self.imview.setImage(np.zeros((10,10)))
            self.databrowser.ui.statusbar.showMessage(
            	f'failed to load {fname}:\n{err}')
            raise(err)

class MetadataView(DataBrowserView):
    """ A viewer to read meta data from a file and display it as text.
    
    """
    name = 'metadata_info'
    
    def setup(self):
        self.ui = QtWidgets.QTextEdit("File metadata")
    
    @staticmethod
    @functools.lru_cache(maxsize=10, typed=False)
    def get_dm_metadata(fname):
        metaData = {}
        with ncempy.io.dm.fileDM(fname, on_memory=True) as dm1:
            # Only keep the most useful tags as meta data
            for kk, ii in dm1.allTags.items():
                # Most useful starting tags
                prefix1 = 'ImageList.{}.ImageTags.'.format(dm1.numObjects)
                prefix2 = 'ImageList.{}.ImageData.'.format(dm1.numObjects)
                pos1 = kk.find(prefix1)
                pos2 = kk.find(prefix2)
                if pos1 > -1:
                    sub = kk[pos1 + len(prefix1):]
                    metaData[sub] = ii
                elif pos2 > -1:
                    sub = kk[pos2 + len(prefix2):]
                    metaData[sub] = ii

                # Remove unneeded keys
                for jj in list(metaData):
                    if jj.find('frame sequence') > -1:
                        del metaData[jj]
                    elif jj.find('Private') > -1:
                        del metaData[jj]
                    elif jj.find('Reference Images') > -1:
                        del metaData[jj]
                    elif jj.find('Frame.Intensity') > -1:
                        del metaData[jj]
                    elif jj.find('Area.Transform') > -1:
                        del metaData[jj]
                    elif jj.find('Parameters.Objects') > -1:
                        del metaData[jj]
                    elif jj.find('Device.Parameters') > -1:
                        del metaData[jj]

            # Store the X and Y pixel size, offset and unit
            try:
                metaData['PhysicalSizeX'] = metaData['Calibrations.Dimension.1.Scale']
                metaData['PhysicalSizeXOrigin'] = metaData['Calibrations.Dimension.1.Origin']
                metaData['PhysicalSizeXUnit'] = metaData['Calibrations.Dimension.1.Units']
                metaData['PhysicalSizeY'] = metaData['Calibrations.Dimension.2.Scale']
                metaData['PhysicalSizeYOrigin'] = metaData['Calibrations.Dimension.2.Origin']
                metaData['PhysicalSizeYUnit'] = metaData['Calibrations.Dimension.2.Units']
            except:
                metaData['PhysicalSizeX'] = 1
                metaData['PhysicalSizeXOrigin'] = 0
                metaData['PhysicalSizeXUnit'] = ''
                metaData['PhysicalSizeY'] = 1
                metaData['PhysicalSizeYOrigin'] = 0
                metaData['PhysicalSizeYUnit'] = ''

        return metaData
    
    @staticmethod
    @functools.lru_cache(maxsize=10, typed=False)
    def get_mrc_metadata(path):
        metaData = {}

        # Open file and parse the header
        with ncempy.io.mrc.fileMRC(path) as mrc1:
            pass

        # Save most useful metaData
        metaData['axisOrientations'] = mrc1.axisOrientations  # meta data information from the mrc header
        metaData['cellAngles'] = mrc1.cellAngles

        if hasattr(mrc1, 'FEIinfo'):
            # add in the special FEIinfo if it exists
            try:
                metaData.update(mrc1.FEIinfo)
            except TypeError:
                pass

        # Store the X and Y pixel size, offset and unit
        # Test for bad pixel sizes which happens often
        if mrc1.voxelSize[2] > 0:
            metaData['PhysicalSizeX'] = mrc1.voxelSize[2] * 1e-10  # change Angstroms to meters
            metaData['PhysicalSizeXOrigin'] = 0
            metaData['PhysicalSizeXUnit'] = 'm'
        else:
            metaData['PhysicalSizeX'] = 1
            metaData['PhysicalSizeXOrigin'] = 0
            metaData['PhysicalSizeXUnit'] = ''
        if mrc1.voxelSize[1] > 0:
            metaData['PhysicalSizeY'] = mrc1.voxelSize[1] * 1e-10  # change Angstroms to meters
            metaData['PhysicalSizeYOrigin'] = 0
            metaData['PhysicalSizeYUnit'] = 'm'
        else:
            metaData['PhysicalSizeY'] = 1
            metaData['PhysicalSizeYOrigin'] = 0
            metaData['PhysicalSizeYUnit'] = ''

        metaData['FileName'] = path

        rawtltName = Path(path).with_suffix('.rawtlt')
        if rawtltName.exists():
            with open(rawtltName, 'r') as f1:
                tilts = map(float, f1)
            metaData['tilt angles'] = tilts

        FEIparameters = Path(path).with_suffix('.txt')
        if FEIparameters.exists():
            with open(FEIparameters, 'r') as f2:
                lines = f2.readlines()
            pp1 = list([ii[18:].strip().split(':')] for ii in lines[3:-1])
            pp2 = {}
            for ll in pp1:
                try:
                    pp2[ll[0]] = float(ll[1])
                except:
                    pass  # skip lines with no data
            metaData.update(pp2)

        return metaData
    
    @staticmethod
    @functools.lru_cache(maxsize=10, typed=False)
    def get_emd_metadata(path):
        metaData = {}
        with ncempy.io.emd.fileEMD(path) as emd0:        
            metaData.update(emd0.user.attrs)
            metaData.update(emd0.microscope.attrs)
            metaData.update(emd0.sample.attrs)
            dims = emd0.get_emddims(emd0.list_emds[0])
            dimX = dims[-1]
            dimY = dims[-2]
            metaData['PhysicalSizeX'] = dimX[0][1] - dimX[0][0]
            metaData['PhysicalSizeXOrigin'] = dimX[0][0]
            metaData['PhysicalSizeXUnit'] = dimX[2].replace('_', '')
            metaData['PhysicalSizeY'] = dimY[0][1] - dimY[0][0]
            metaData['PhysicalSizeYOrigin'] = dimY[0][0]
            metaData['PhysicalSizeYUnit'] = dimY[2].replace('_', '')
        return metaData


    @staticmethod
    @functools.lru_cache(maxsize=10, typed=False)
    def get_velox_metadata(path):
        import json
        metaData = {}
        with ncempy.io.emdVelox.fileEMDVelox(path) as f0:
            dataGroup = emd_obj.list_data[0]
            dataset0 = dataGroup['Data']

            # Convert JSON metadata to dict
            mData = emd_obj.list_data[0]['Metadata'][:, 0]
            validMetaDataIndex = npwhere(mData > 0)  # find valid metadata
            mData = mData[validMetaDataIndex].tostring()  # change to string
            mDataS = json.loads(mData.decode('utf-8', 'ignore'))  # load UTF-8 string as JSON and output dict
            metaData['pixel sizes'] = []
            metaData['pixel units'] = []
            try:
                # Store the X and Y pixel size, offset and unit
                metaData['PhysicalSizeX'] = float(mDataS['BinaryResult']['PixelSize']['width'])
                metaData['PhysicalSizeXOrigin'] = float(mDataS['BinaryResult']['Offset']['x'])
                metaData['PhysicalSizeXUnit'] = mDataS['BinaryResult']['PixelUnitX']
                metaData['PhysicalSizeY'] = float(mDataS['BinaryResult']['PixelSize']['height'])
                metaData['PhysicalSizeYOrigin'] = float(mDataS['BinaryResult']['Offset']['y'])
                metaData['PhysicalSizeYUnit'] = mDataS['BinaryResult']['PixelUnitY']
            except:
                metaData['PhysicalSizeX'] = 1
                metaData['PhysicalSizeXOrigin'] = 0
                metaData['PhysicalSizeXUnit'] = ''
                metaData['PhysicalSizeY'] = 1
                metaData['PhysicalSizeYOrigin'] = 0
                metaData['PhysicalSizeYUnit'] = ''

            metaData.update(mDataS)

            metaData['shape'] = dataset0.shape
    
    def on_change_data_filename(self, fname):
        ext = Path(fname).suffix
        
        meta_data = {'file name': str(fname)}
        if ext in ('.dm3', '.dm4'):
            meta_data = self.get_dm_metadata(fname)
        elif ext in ('.mrc', '.rec', '.ali'):
            meta_data = self.get_mrc_metadata(fname)
        elif ext in ('.emd',):
            with ncempy.io.emd.fileEMD(fname) as emd0:
                if len(emd0.list_emds) > 0:
                    meta_data = self.get_emd_metadata(fname)
                else:
                    meta_data = self.get_velox_metadata(fname)
        
        txt = f'file name = {fname}\n'
        for k, v in meta_data.items():
            line = f'{k} = {v}\n'
            txt += line
        self.ui.setText(txt)
        
    def is_file_supported(self, fname):
        ext = fname.suffix
        return ext.lower() in ('.dm3', '.dm4', '.mrc', '.ali', '.rec')

if __name__ == '__main__':
    import sys
    
    app = DataBrowser(sys.argv)
    #app.load_view(HyperSpectralBaseView(app))

    sys.exit(app.exec_())
    