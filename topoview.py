import math, sys
from time import time
import numpy as np
from pointio import io_npy
from ma_util import MAHelper
from povi import App
from graph import *

from povi import App

from PyQt5 import uic
from PyQt5.QtCore import Qt
from PyQt5.QtWidgets import QWidget, QToolBox

# todo:
# - clipping planes

class MatApp(App):

    def __init__(self, ma, args=[]):
        super(MatApp, self).__init__(args)
        self.ma = ma
        self.graph_programs = []
        self.segment_filter = ma.D['ma_segment']>0
        self.radius_value = 150.

        self.viewerWindow.visibility_toggle_listeners.append(self.set_layer_visibility)

    def run(self):
        self.dialog = ToolsDialog(self)
        self.draw_graphs()
        self.update_radius(150.)
        self.dialog.show()
        super(MatApp, self).run()

    def filter_linkcount(self, value):
        f = ma.D['seg_link_adj'][:,2] >= value
        self.viewerWindow.data_programs['Adjacency relations'].updateAttributes(filter=np.repeat(f,2))
        # f = ma.D['seg_link_flip'][:,2] >= value
        # self.viewerWindow.data_programs['Flip relations'].updateAttributes(filter=np.repeat(f,2))
        self.viewerWindow.render()

    def set_layer_visibility(self, name, is_visible):
        items = self.dialog.ui.listWidget_layers.findItems(name,Qt.MatchExactly)
        for item in items:
            item.setSelected(is_visible)

    def set_layer_selection(self):
        selected_names = [item.data(0) for item in self.dialog.ui.listWidget_layers.selectedItems()]
        for name, program in self.viewerWindow.data_programs.iteritems():
            if name in selected_names:
                program.is_visible = True
            elif not name.startswith('graph'):
                program.is_visible = False
        self.viewerWindow.render()

    def filter_component_all(self, toggle):
        for gp in self.graph_programs:
            gp.is_visible = True
        self.viewerWindow.data_programs['Surface points'].updateAttributes()
        self.update_radius(self.radius_value)
        if toggle==True:
            self.filter_component(index=self.dialog.ui.comboBox_component.currentIndex())

    def filter_component(self, index):
        for gp in self.graph_programs:
            gp.is_visible = False
        self.graph_programs[index].is_visible = True
        
        g = self.graph_programs[self.dialog.ui.comboBox_component.currentIndex()].graph
        segment_ids = [n.segment_id for n in g.nodes]
        self.viewerWindow.center_view(np.mean([ma.segment_centers_dict[i][1] for i in segment_ids], axis=0))
        self.viewerWindow.render()

        f = np.in1d(self.ma.D['ma_segment'], segment_ids)
        if f.sum() <1:return
        # update mat points
        self.viewerWindow.data_programs['MAT points'].updateAttributes(filter=f)
        self.viewerWindow.data_programs['Bisectors'].updateAttributes(filter=np.repeat(f,2))
        self.viewerWindow.data_programs['Primary spokes'].updateAttributes(filter=np.repeat(f,2))
        self.viewerWindow.data_programs['Secondary spokes'].updateAttributes(filter=np.repeat(f,2))
        # update coords
        # find indices of all surface points related to these mat points
        f_s1 = np.concatenate([np.arange(self.ma.m), np.arange(self.ma.m)])
        f_s1 = f_s1[f]
        f_s2 = self.ma.D['ma_qidx'][f]
        self.viewerWindow.data_programs['Surface points'].updateAttributes(filter=np.concatenate([f_s1,f_s2]))
        
        
        self.viewerWindow.render()

    def update_radius(self, value):
        self.radius_value = value
        self.radius_filter = self.ma.D['ma_radii'] <= self.radius_value 
        f=np.logical_and(self.segment_filter, self.radius_filter)
        self.viewerWindow.data_programs['MAT points'].updateAttributes(filter=f)
        self.viewerWindow.data_programs['Bisectors'].updateAttributes(filter=np.repeat(f,2))
        f=np.repeat(f,2)
        self.viewerWindow.data_programs['Primary spokes'].updateAttributes(filter=f)
        self.viewerWindow.data_programs['Secondary spokes'].updateAttributes(filter=f)
        self.viewerWindow.render()
        return

    def draw_graphs(self):
        for i, gp in enumerate(self.graph_programs):
            gp.delete()
            self.data_programs.pop(gp.name)
        self.dialog.ui.comboBox_component.clear()
        self.dialog.ui.groupBox_component.setChecked(False)
        self.filter_component_all(False)
        self.graph_programs = []

        min_count = self.dialog.ui.spinBox_linkcount.value()
        self.graphs = get_graphs(self.ma.D, min_count)

        i=0
        for g in self.graphs:
            adj_rel_start = []
            adj_rel_end = []

            if 0<len(g.edges):#<1000:
                for e in g.edges:
                    adj_rel_start.append(ma.segment_centers_dict[e.start.segment_id][1])
                    adj_rel_end.append(ma.segment_centers_dict[e.end.segment_id][1])
                # import ipdb; ipdb.set_trace()
                # color = np.random.rand(3)
                # color[np.random.random_integers(0,2)] = np.random.uniform(0.5,1.0,1)
                color = np.random.uniform(0.3,1.0,3)
                p = self.add_data_source_line(
                    name = 'graph {}'.format(i),
                    coords_start = np.array(adj_rel_start),
                    coords_end = np.array(adj_rel_end),
                    color = tuple(color),
                    is_visible=True
                )
                i+=1
                p.graph = g
                self.graph_programs.append(p)
        self.viewerWindow.render()

        # populate comboBox_component
        self.dialog.ui.comboBox_component.insertItems(0, [gp.name for gp in self.graph_programs])


class ToolsDialog(QWidget):
    def __init__(self, app, parent=None):
        super(ToolsDialog, self).__init__(parent)
        self.ui = uic.loadUi('tools.ui', self)
        self.app = app

        # populate datalayers list
        # print self.app.viewerWindow.data_programs.keys()
        l=[]
        for program_name in self.app.viewerWindow.data_programs.keys():
            if not program_name.startswith('graph'):
                l.append(program_name)
        self.ui.listWidget_layers.addItems(l)

        self.ui.doubleSpinBox_filterRadius.valueChanged.connect(self.app.update_radius)
        self.ui.spinBox_linkcount.valueChanged.connect(self.app.filter_linkcount)
        self.ui.pushButton_regraph.clicked.connect(self.app.draw_graphs)
        self.ui.groupBox_component.clicked.connect(self.app.filter_component_all)
        self.ui.comboBox_component.activated.connect(self.app.filter_component)
        self.ui.listWidget_layers.itemSelectionChanged.connect(self.app.set_layer_selection)
        # import ipdb; ipdb.set_trace()

    def slot_tcount(self, value):
        print 'tcount', value

# INFILE = 'data/scan_npy'
# INFILE = "/Users/ravi/git/masbcpp/rdam_blokken_npy"
INFILE = "/Volumes/Data/Data/pointcloud/AHN2_matahn_samples/ringdijk_opmeer_npy"
# INFILE = "/Volumes/Data/Data/pointcloud/AHN2_matahn_samples/denhaag_a12_npy"

def timeit(func):
    t0 = time()
    r = func()
    print("Executed function %s took %f s" % (func.__name__, time()-t0))
    return r

def assign_seg_point():
    """find for each coord the set of segments it is linked to"""
    pdict = {}

    for i, segment in enumerate(ma.D['ma_segment']):
        coord_id = i# % ma.m
        fp = coord_id
        fq = ma.D['ma_qidx'][coord_id]

        for idx in [fp,fq]:
            if pdict.has_key(idx):
                pdict[idx].add(segment)
            else:
                pdict[idx] = set([segment])
    del pdict[-1]

    datadict['segment_count'] = np.array([ len(s) for s in pdict.values() ], dtype=np.int32)
    io_npy.write_npy(INFILE, datadict, ['segment_count'])

def count_refs():
    """count the number of times each coord is used as feature point for a medial ball"""

    pdict = {}
    for i in np.arange(ma.m*2):
        coord_id = i# % ma.m
        fp = coord_id %ma.m
        fq = ma.D['ma_qidx'][coord_id]

        for idx in [fp,fq]:
            if pdict.has_key(idx):
                pdict[idx] += 1
            else:
                pdict[idx] = 1
    del pdict[-1]

    return np.array(pdict.values(), dtype=np.int32)

def compute_segment_centers():
    """Compute avarage coordinate for each segment"""

    segment_dict = {}
    # segment_point_sums = {}
    for i, segment in enumerate(ma.D['ma_segment']):
        # slicing is not copying!
        if segment_dict.has_key(segment):
            segment_dict[segment][0] += 1
            segment_dict[segment][1] += ma.D['ma_coords'][i]
        else:
            segment_dict[segment] = [1, np.copy(ma.D['ma_coords'][i])]

    for key, value in segment_dict.iteritems():
        segment_dict[key][1] = value[1]/value[0]

    
    return segment_dict



def view(ma):
    # ref_count = timeit(count_refs)
    min_link_adj = 5
    max_r=190.
    segment_centers_dict = timeit(compute_segment_centers)
    ma.segment_centers_dict = segment_centers_dict

    seg_centers = np.array([v[1] for v in segment_centers_dict.values()], dtype=np.float32)
    seg_cnts = np.array([v[0] for v in segment_centers_dict.values()], dtype=np.float32)
    seg_ids = np.array([k for k in segment_centers_dict.keys()], dtype=np.float32)

    flip_rel_start = np.zeros((len(ma.D['seg_link_flip']),3), dtype=np.float32)
    flip_rel_end = np.zeros((len(ma.D['seg_link_flip']),3), dtype=np.float32)
    i=0
    for s,e in ma.D['seg_link_flip'][:,:2]:
        flip_rel_start[i] = segment_centers_dict[s][1]
        flip_rel_end[i] = segment_centers_dict[e][1]
        i+=1

    adj_rel_start = np.zeros((len(ma.D['seg_link_adj']),3), dtype=np.float32)
    adj_rel_end = np.zeros((len(ma.D['seg_link_adj']),3), dtype=np.float32)
    i=0
    # f = ma.D['seg_link_adj'][:,2] > min_link_adj
    for s,e in ma.D['seg_link_adj'][:,:2]:
        adj_rel_start[i] = segment_centers_dict[s][1]
        adj_rel_end[i] = segment_centers_dict[e][1]
        i+=1
    
    c = MatApp(ma)

    c.add_data_source(
        name = 'Surface points',
        opts=['splat_disk', 'with_normals'],
        points=ma.D['coords'], normals=ma.D['normals'],
    )

    if ma.D.has_key('ma_segment'):
        # f = np.logical_and(ma.D['ma_radii'][:ma.m] < max_r, ma.D['ma_segment'][:ma.m]>0)
        # c.add_data_source(
        #     opts=['splat_point', 'with_intensity'],
        #     points=ma.D['ma_coords'][:ma.m][f], 
        #     category=ma.D['ma_segment'][:ma.m][f].astype(np.float32),
        #     colormap='random'
        # )
        # f = np.logical_and(ma.D['ma_radii'][ma.m:] < max_r, ma.D['ma_segment'][ma.m:]>0)
        # c.add_data_source(
        #     opts=['splat_point', 'with_intensity'],
        #     points=ma.D['ma_coords'][ma.m:][f], 
        #     category=ma.D['ma_segment'][ma.m:][f].astype(np.float32),
        #     colormap='random'
        # )
        # f = np.logical_and(ma.D['ma_radii'] < max_r, ma.D['ma_segment']>0)
        c.add_data_source(
            name = 'MAT points',
            opts=['splat_point', 'with_intensity'],
            points=ma.D['ma_coords'], 
            category=ma.D['ma_segment'].astype(np.float32),
            colormap='random'
        )

    
        f = np.logical_and(ma.D['ma_radii'] < max_r, ma.D['ma_segment']==0)
        c.add_data_source(
            name = 'MAT points remainder',
            opts = ['splat_point', 'blend'],
            points=ma.D['ma_coords'][f]
        )
    else:
        f = ma.D['ma_radii_in'] < max_r
        c.add_data_source(
            opts = ['splat_point', 'blend'],
            points=ma.D['ma_coords_in'][f]
        )
        f = ma.D['ma_radii_out'] < max_r
        c.add_data_source(
            opts = ['splat_point', 'blend'],
            points=ma.D['ma_coords_out'][f]
        )

    f = seg_cnts!=1
    c.add_data_source(
        name = 'Segment centers',
        opts = ['splat_point'],
        points = seg_centers[f]
    )
    if len(flip_rel_start)>0:
        c.add_data_source_line(
            name = 'Flip relations',
            coords_start = flip_rel_start,
            coords_end = flip_rel_end
        )

    if len(adj_rel_start)>0:
        f = seg_cnts!=1
        c.add_data_source_line(
            name = 'Adjacency relations',
            coords_start = adj_rel_start,
            coords_end = adj_rel_end,
            color = (0,1,0)
        )

    # f = ref_count > 20
    # c.add_data_source(
    #   opts = ['splat_point', 'fixed_color'],
    #   points = ma.D['coords'][f],
    #   # intensity = np.clip(ref_count,0,15).astype(np.float32)[f]
    #   color = (1,1,1)
    # )

    # f = ma.D['ma_radii'] < max_r
    c.add_data_source_line(
      name = 'Bisectors',
      coords_start = ma.D['ma_coords'],
      coords_end = ma.D['ma_bisec']+ma.D['ma_coords']
    )
    c.add_data_source_line(
      name = 'Primary spokes',
      coords_start = ma.D['ma_coords'],
      coords_end = np.concatenate([ma.D['coords'],ma.D['coords']])
    )
    c.add_data_source_line(
      name = 'Secondary spokes',
      coords_start = ma.D['ma_coords'],
      coords_end = np.concatenate([ma.D['coords'][ma.D['ma_qidx_in']],ma.D['coords'][ma.D['ma_qidx_out']]])
    )


    c.run()

if __name__ == '__main__':
    if len(sys.argv)>1:
        INFILE = sys.argv[-1]
    # import ipdb;ipdb.set_trace()
    datadict = io_npy.read_npy(INFILE)
    ma = MAHelper(datadict, origin=True)

    view(ma)
